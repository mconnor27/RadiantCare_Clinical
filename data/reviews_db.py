"""Persistence for CPT audit reviews and related admin data.

Supports two backends:
  - SQLite (default) — ``PROJECT_ROOT/reviews.db``, used for local dev.
  - Postgres (when ``REVIEWS_DB_URL`` or ``DATABASE_URL`` is set to a
    postgres:// URL) — used in production on Railway → Supabase.

The two dialects are bridged by a thin connection wrapper so the ~45
functions below keep their ``with _connect() as conn: conn.execute(...)``
style unchanged. Placeholder and conflict-syntax differences are handled
transparently by ``_translate()``.

Thread-safe — each call opens and closes its own connection.
"""

import os
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from config.settings import PROJECT_ROOT

DB_PATH = PROJECT_ROOT / "reviews.db"

_DB_URL = (os.environ.get("REVIEWS_DB_URL") or os.environ.get("DATABASE_URL") or "").strip()
_USE_POSTGRES = _DB_URL.startswith(("postgresql://", "postgres://", "postgresql+"))
_PG_SCHEMA = os.environ.get("REVIEWS_DB_SCHEMA", "clinical")

if _USE_POSTGRES:
    import psycopg2
    from psycopg2.extras import RealDictCursor


# ---------------------------------------------------------------------------
# Schema — two dialect variants
# ---------------------------------------------------------------------------

_SCHEMA_SQLITE = """
CREATE TABLE IF NOT EXISTS cpt_reviews (
    session_id  TEXT PRIMARY KEY,
    status      TEXT NOT NULL,
    reviewer    TEXT NOT NULL DEFAULT '',
    updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS cpt_course_reviews (
    course_key  TEXT PRIMARY KEY,
    status      TEXT NOT NULL,
    reviewer    TEXT NOT NULL DEFAULT '',
    updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS referring_physicians (
    npi           TEXT NOT NULL,
    address_key   TEXT NOT NULL DEFAULT '',
    display_name  TEXT,
    specialty     TEXT,
    institution   TEXT,
    address       TEXT,
    city          TEXT,
    state         TEXT,
    zip_code      TEXT,
    address_source TEXT NOT NULL DEFAULT '',
    source        TEXT NOT NULL DEFAULT 'manual',
    reviewed      INTEGER NOT NULL DEFAULT 0,
    merged_into_address_key TEXT,
    merged_into_npi TEXT,
    updated_at    TEXT NOT NULL,
    updated_by    TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (npi, address_key)
);

CREATE TABLE IF NOT EXISTS institutions (
    name          TEXT PRIMARY KEY,
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS institution_aliases (
    alias         TEXT PRIMARY KEY,
    canonical     TEXT NOT NULL,
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS diagnosis_taxonomy (
    category      TEXT NOT NULL,
    subcategory   TEXT NOT NULL,
    sort_order    INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (category, subcategory)
);

CREATE TABLE IF NOT EXISTS diagnosis_overrides (
    icd_code      TEXT PRIMARY KEY,
    category      TEXT NOT NULL,
    subcategory   TEXT NOT NULL DEFAULT '',
    source        TEXT NOT NULL DEFAULT 'manual',
    reviewed      INTEGER NOT NULL DEFAULT 0,
    updated_at    TEXT NOT NULL,
    updated_by    TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS insurance_rates (
    payor         TEXT PRIMARY KEY,
    rate_method   TEXT NOT NULL DEFAULT 'pct_medicare',
    em_cf         REAL,
    other_cf      REAL,
    pct_medicare  REAL NOT NULL DEFAULT 100.0,
    effective_date TEXT,
    source        TEXT NOT NULL DEFAULT 'manual',
    notes         TEXT NOT NULL DEFAULT '',
    updated_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS insurance_rate_history (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    payor         TEXT NOT NULL,
    effective_date TEXT NOT NULL,
    end_date      TEXT,
    rate_method   TEXT NOT NULL DEFAULT 'pct_medicare',
    em_cf         REAL,
    other_cf      REAL,
    pct_medicare  REAL NOT NULL DEFAULT 100.0,
    source        TEXT NOT NULL DEFAULT 'manual',
    notes         TEXT NOT NULL DEFAULT '',
    updated_at    TEXT NOT NULL,
    UNIQUE(payor, effective_date)
);

CREATE TABLE IF NOT EXISTS payor_mappings (
    raw_name            TEXT PRIMARY KEY,
    standardized_payor  TEXT NOT NULL DEFAULT '',
    broad_category      TEXT NOT NULL DEFAULT 'Other/Unknown',
    phdsc_category      TEXT NOT NULL DEFAULT '9',
    reviewed            INTEGER NOT NULL DEFAULT 0,
    ai_explanation      TEXT NOT NULL DEFAULT '',
    updated_at          TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS revenue_adj_settings (
    key   TEXT PRIMARY KEY,
    value REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS app_settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

# Postgres schema matches SQLite on purpose (same data types: TEXT/INTEGER/REAL)
# except AUTOINCREMENT → SERIAL. Keeps row data interchangeable.
_SCHEMA_POSTGRES = _SCHEMA_SQLITE.replace(
    "id            INTEGER PRIMARY KEY AUTOINCREMENT",
    "id            SERIAL PRIMARY KEY",
)


# ---------------------------------------------------------------------------
# Postgres connection wrapper — makes psycopg2 behave like sqlite3.Connection
# for the tight call-site vocabulary used by this module.
# ---------------------------------------------------------------------------

_PLACEHOLDER_RE = re.compile(r"(?<!%)\?")  # match lone ? placeholders


def _translate(sql: str) -> str:
    """SQLite → Postgres SQL translation for the patterns this file uses."""
    # ? placeholders → %s
    sql = _PLACEHOLDER_RE.sub("%s", sql)
    # INSERT OR IGNORE → INSERT ... ON CONFLICT DO NOTHING
    if "INSERT OR IGNORE" in sql:
        sql = sql.replace("INSERT OR IGNORE", "INSERT")
        if " ON CONFLICT " not in sql.upper():
            sql = sql.rstrip().rstrip(";") + " ON CONFLICT DO NOTHING"
    return sql


class _PgCursorWrap:
    def __init__(self, cur):
        self._cur = cur

    def fetchone(self):
        return self._cur.fetchone()

    def fetchall(self):
        return self._cur.fetchall()

    @property
    def rowcount(self):
        return self._cur.rowcount


class _PgConnWrapper:
    """Mimics sqlite3.Connection: context manager commits/rolls back,
    ``.execute(sql, params)`` returns something with fetchone/fetchall/rowcount,
    and ``.executescript(sql)`` runs a multi-statement DDL string."""

    def __init__(self, conn):
        self._conn = conn

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc is None:
            self._conn.commit()
        else:
            self._conn.rollback()
        self._conn.close()
        return False

    def execute(self, sql, params=()):
        cur = self._conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(_translate(sql), params)
        return _PgCursorWrap(cur)

    def executescript(self, script: str):
        # Split on ; and run each non-empty statement. Safe for our schema
        # where no statement contains a semicolon inside a string literal.
        stmts = [s.strip() for s in script.split(";") if s.strip()]
        cur = self._conn.cursor()
        for stmt in stmts:
            cur.execute(_translate(stmt))
        cur.close()


def _connect():
    if _USE_POSTGRES:
        conn = psycopg2.connect(_DB_URL)
        with conn.cursor() as cur:
            cur.execute(f'SET search_path TO "{_PG_SCHEMA}", public')
        return _PgConnWrapper(conn)

    # SQLite (default, local dev)
    conn = sqlite3.connect(str(DB_PATH), timeout=5)
    conn.execute("PRAGMA journal_mode=WAL")  # better concurrent reads
    conn.row_factory = sqlite3.Row
    return conn


# ---------------------------------------------------------------------------
# Ensure tables + apply lightweight column migrations
# ---------------------------------------------------------------------------

def _ensure_table():
    if _USE_POSTGRES:
        # Postgres: CREATE TABLE IF NOT EXISTS handles fresh installs; for
        # tables that pre-exist with an older shape, add new columns via
        # idempotent ALTER ... ADD COLUMN IF NOT EXISTS.
        with _connect() as conn:
            conn.executescript(_SCHEMA_POSTGRES)
            conn.execute(
                "ALTER TABLE payor_mappings ADD COLUMN IF NOT EXISTS "
                "ai_explanation TEXT NOT NULL DEFAULT ''"
            )
            conn.execute(
                "ALTER TABLE referring_physicians ADD COLUMN IF NOT EXISTS "
                "merged_into_address_key TEXT"
            )
            # Earlier migration made this NOT NULL DEFAULT '' which collided with
            # the empty-string sentinel — make nullable + backfill blanks to NULL
            # so non-tombstones become distinguishable from empty-survivor tombstones.
            conn.execute(
                "ALTER TABLE referring_physicians ALTER COLUMN "
                "merged_into_address_key DROP NOT NULL"
            )
            conn.execute(
                "ALTER TABLE referring_physicians ALTER COLUMN "
                "merged_into_address_key DROP DEFAULT"
            )
            conn.execute(
                "UPDATE referring_physicians SET merged_into_address_key = NULL "
                "WHERE merged_into_address_key = ''"
            )
            # Recover orphan tombstones: rows with source='merge' but
            # merged_into=NULL are from a pre-fix code path where the survivor's
            # address_key arrived as None. Set merged_into='' so they redirect
            # to the empty-addr_key survivor (which was the actual survivor for
            # all observed cases). Idempotent — only touches NULLs.
            conn.execute(
                "UPDATE referring_physicians SET merged_into_address_key = '' "
                "WHERE source = 'merge' AND merged_into_address_key IS NULL"
            )
            conn.execute(
                "ALTER TABLE referring_physicians ADD COLUMN IF NOT EXISTS "
                "display_name TEXT"
            )
            # Cross-NPI merge support: when set on a tombstone, the redirect
            # points to a DIFFERENT NPI (not just a different address_key on
            # the same provider). NULL means same-NPI tombstone (legacy).
            conn.execute(
                "ALTER TABLE referring_physicians ADD COLUMN IF NOT EXISTS "
                "merged_into_npi TEXT"
            )
        return

    # SQLite path (unchanged behaviour)
    with _connect() as conn:
        conn.executescript(_SCHEMA_SQLITE)
        cols = [r[1] for r in conn.execute("PRAGMA table_info(diagnosis_overrides)").fetchall()]
        if "reviewed" not in cols:
            conn.execute("ALTER TABLE diagnosis_overrides ADD COLUMN reviewed INTEGER NOT NULL DEFAULT 0")
        rp_cols = [r[1] for r in conn.execute("PRAGMA table_info(referring_physicians)").fetchall()]
        for col, default in [("address", ""), ("city", ""), ("state", ""), ("zip_code", ""), ("address_source", "")]:
            if col not in rp_cols:
                conn.execute(f"ALTER TABLE referring_physicians ADD COLUMN {col} TEXT NOT NULL DEFAULT '{default}'")
        # Nullable columns — see Postgres branch above for why merged_into needs NULL semantics.
        if "merged_into_address_key" not in rp_cols:
            conn.execute("ALTER TABLE referring_physicians ADD COLUMN merged_into_address_key TEXT")
        else:
            # Backfill any '' sentinel to NULL on existing local DBs. SQLite
            # can't drop a NOT NULL constraint without a full table rebuild;
            # if the column is still NOT NULL from the old shape, the UPDATE
            # errors — swallow it so local dev keeps booting. Prod (Postgres)
            # handled the constraint drop above.
            try:
                conn.execute(
                    "UPDATE referring_physicians SET merged_into_address_key = NULL "
                    "WHERE merged_into_address_key = ''"
                )
            except Exception:
                pass
            try:
                conn.execute(
                    "UPDATE referring_physicians SET merged_into_address_key = '' "
                    "WHERE source = 'merge' AND merged_into_address_key IS NULL"
                )
            except Exception:
                pass
        if "display_name" not in rp_cols:
            conn.execute("ALTER TABLE referring_physicians ADD COLUMN display_name TEXT")
        if "merged_into_npi" not in rp_cols:
            conn.execute("ALTER TABLE referring_physicians ADD COLUMN merged_into_npi TEXT")
        pm_cols = [r[1] for r in conn.execute("PRAGMA table_info(payor_mappings)").fetchall()]
        if "phdsc_category" not in pm_cols:
            conn.execute("ALTER TABLE payor_mappings ADD COLUMN phdsc_category TEXT NOT NULL DEFAULT '9'")
        if "ai_explanation" not in pm_cols:
            conn.execute("ALTER TABLE payor_mappings ADD COLUMN ai_explanation TEXT NOT NULL DEFAULT ''")


# Run once on import
_ensure_table()


def set_review(session_id: str, status: str, reviewer: str = "") -> None:
    """Insert or update a review for a session."""
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        conn.execute(
            """INSERT INTO cpt_reviews (session_id, status, reviewer, updated_at)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(session_id) DO UPDATE SET
                   status = excluded.status,
                   reviewer = excluded.reviewer,
                   updated_at = excluded.updated_at""",
            (str(session_id), status, reviewer, now),
        )


def remove_review(session_id: str) -> None:
    """Remove a review (undo)."""
    with _connect() as conn:
        conn.execute("DELETE FROM cpt_reviews WHERE session_id = ?", (str(session_id),))


def get_all_reviews() -> dict[str, str]:
    """Return {session_id: status} for all reviewed sessions."""
    with _connect() as conn:
        rows = conn.execute("SELECT session_id, status FROM cpt_reviews").fetchall()
    return {r["session_id"]: r["status"] for r in rows}


def get_review_details() -> list[dict]:
    """Return full review records with timestamps."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT session_id, status, reviewer, updated_at FROM cpt_reviews ORDER BY updated_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Course-level reviews
# ---------------------------------------------------------------------------
def _course_key(patient_mrn: str, course_name: str) -> str:
    return f"{patient_mrn}|{course_name}"


def set_course_review(patient_mrn: str, course_name: str, status: str, reviewer: str = "") -> None:
    """Approve an entire patient/course combo."""
    now = datetime.now(timezone.utc).isoformat()
    key = _course_key(patient_mrn, course_name)
    with _connect() as conn:
        conn.execute(
            """INSERT INTO cpt_course_reviews (course_key, status, reviewer, updated_at)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(course_key) DO UPDATE SET
                   status = excluded.status,
                   reviewer = excluded.reviewer,
                   updated_at = excluded.updated_at""",
            (key, status, reviewer, now),
        )


def remove_course_review(patient_mrn: str, course_name: str) -> None:
    """Remove a course-level review (undo)."""
    key = _course_key(patient_mrn, course_name)
    with _connect() as conn:
        conn.execute("DELETE FROM cpt_course_reviews WHERE course_key = ?", (key,))


def get_all_course_reviews() -> dict[str, str]:
    """Return {patient_mrn|course_name: status} for all course-level reviews."""
    with _connect() as conn:
        rows = conn.execute("SELECT course_key, status FROM cpt_course_reviews").fetchall()
    return {r["course_key"]: r["status"] for r in rows}


# ---------------------------------------------------------------------------
# Referring physician overrides
# ---------------------------------------------------------------------------

def _addr_key(city: str = "", state: str = "", zip_code: str = "") -> str:
    """Build a normalized address key from city/state/zip for composite PK."""
    parts = [str(p).strip().upper() for p in (city, state, zip_code) if p and str(p).strip() and str(p) != "nan"]
    return "|".join(parts) if parts else ""


def upsert_referring(
    npi: str,
    address_key: str = "",
    specialty: str | None = None,
    institution: str | None = None,
    address: str | None = None,
    city: str | None = None,
    state: str | None = None,
    zip_code: str | None = None,
    address_source: str | None = None,
    source: str = "manual",
    updated_by: str = "",
    display_name: str | None = None,
) -> None:
    """Insert or update a referring physician override."""
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        existing = conn.execute(
            "SELECT specialty, institution, address, city, state, zip_code, address_source, display_name "
            "FROM referring_physicians WHERE npi = ? AND address_key = ?",
            (str(npi), address_key),
        ).fetchone()
        if existing:
            specialty = specialty if specialty is not None else existing["specialty"]
            institution = institution if institution is not None else existing["institution"]
            address = address if address is not None else existing["address"]
            city = city if city is not None else existing["city"]
            state = state if state is not None else existing["state"]
            zip_code = zip_code if zip_code is not None else existing["zip_code"]
            address_source = address_source if address_source is not None else existing["address_source"]
            display_name = display_name if display_name is not None else existing["display_name"]
        conn.execute(
            """INSERT INTO referring_physicians
               (npi, address_key, specialty, institution, address, city, state, zip_code, address_source, source, updated_at, updated_by, display_name)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(npi, address_key) DO UPDATE SET
                   specialty      = excluded.specialty,
                   institution    = excluded.institution,
                   address        = excluded.address,
                   city           = excluded.city,
                   state          = excluded.state,
                   zip_code       = excluded.zip_code,
                   address_source = excluded.address_source,
                   source         = excluded.source,
                   updated_at     = excluded.updated_at,
                   updated_by     = excluded.updated_by,
                   display_name   = excluded.display_name""",
            (str(npi), address_key, specialty, institution,
             address or "", city or "", state or "", zip_code or "",
             address_source or "", source, now, updated_by, display_name),
        )
    _invalidate_referrals_cache()


def bulk_upsert_referring(records: list[dict]) -> None:
    """Batch insert/update referring physician overrides.

    Each record: {"npi": str, "address_key": str, "specialty": str|None, "institution": str|None, "source": str}
    """
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        for rec in records:
            conn.execute(
                """INSERT INTO referring_physicians (npi, address_key, specialty, institution, source, updated_at, updated_by)
                   VALUES (?, ?, ?, ?, ?, ?, '')
                   ON CONFLICT(npi, address_key) DO UPDATE SET
                       specialty   = COALESCE(excluded.specialty, referring_physicians.specialty),
                       institution = COALESCE(excluded.institution, referring_physicians.institution),
                       source      = excluded.source,
                       updated_at  = excluded.updated_at""",
                (str(rec["npi"]), rec.get("address_key", ""), rec.get("specialty"),
                 rec.get("institution"), rec.get("source", "manual"), now),
            )
    _invalidate_referrals_cache()


def get_all_referring_overrides() -> dict[str, dict]:
    """Return {npi|address_key: {specialty, institution, address fields, source, reviewed}}.

    Excludes merge tombstones (rows with merged_into_address_key set) — those
    aren't real overrides, they're redirect pointers handled separately.
    """
    with _connect() as conn:
        rows = conn.execute(
            "SELECT npi, address_key, display_name, specialty, institution, "
            "address, city, state, zip_code, address_source, source, reviewed "
            "FROM referring_physicians "
            "WHERE merged_into_address_key IS NULL"
        ).fetchall()
    return {
        f"{r['npi']}|{r['address_key']}": {
            "display_name": r["display_name"] or "",
            "specialty": r["specialty"], "institution": r["institution"],
            "address": r["address"], "city": r["city"],
            "state": r["state"], "zip_code": r["zip_code"],
            "address_source": r["address_source"] or "",
            "source": r["source"], "reviewed": bool(r["reviewed"]),
        }
        for r in rows
    }


def set_reviewed_bulk(keys: list[tuple[str, str]], reviewed: bool = True) -> int:
    """Mark multiple (npi, address_key) pairs as reviewed/unreviewed.

    Returns number of rows updated.
    """
    now = datetime.now(timezone.utc).isoformat()
    val = 1 if reviewed else 0
    count = 0
    with _connect() as conn:
        for npi, addr_key in keys:
            cur = conn.execute(
                "UPDATE referring_physicians SET reviewed = ?, updated_at = ? WHERE npi = ? AND address_key = ?",
                (val, now, npi, addr_key),
            )
            count += cur.rowcount
    if count:
        _invalidate_referrals_cache()
    return count


def get_referring_institutions() -> list[str]:
    """Return sorted list of distinct non-null institution names (for autocomplete)."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT DISTINCT institution FROM referring_physicians WHERE institution IS NOT NULL AND institution != '' ORDER BY institution"
        ).fetchall()
    return [r["institution"] for r in rows]


def add_referring_address(
    npi: str, address: str = "", city: str = "", state: str = "", zip_code: str = "",
    specialty: str = "", institution: str = "",
) -> str:
    """Add a new address row for an existing NPI. Returns the new address_key."""
    addr_key = _addr_key(city, state, zip_code)
    upsert_referring(
        npi, address_key=addr_key, specialty=specialty or None, institution=institution or None,
        address=address, city=city, state=state, zip_code=zip_code,
        address_source="manual", source="manual",
    )
    return addr_key


def delete_referring(npi: str, address_key: str = "") -> None:
    """Delete a referring physician row."""
    with _connect() as conn:
        conn.execute(
            "DELETE FROM referring_physicians WHERE npi = ? AND address_key = ?",
            (str(npi), address_key),
        )
    _invalidate_referrals_cache()


def merge_referring(
    npi: str,
    survivor_address_key: str,
    loser_address_keys: list[str],
    survivor_defaults: dict | None = None,
    loser_defaults: list[dict] | None = None,
    survivor_npi: str | None = None,
) -> int:
    """Merge multiple (npi, address_key) rows into the survivor.

    - Same-NPI by default: pass ``npi`` as the shared provider ID, and the
      losers are ``[(npi, addr_key), ...]`` for each addr_key in
      ``loser_address_keys``. Survivor is ``(npi, survivor_address_key)``.
    - Cross-NPI: pass ``survivor_npi`` distinct from ``npi`` to merge a
      DIFFERENT-NPI loser into the survivor. The tombstones get
      ``merged_into_npi`` set so the grid/loader redirect remaps both the
      NPI AND the addr_key when aggregating referrals.

    - The survivor row is upserted with merged values: its own non-blank fields
      win; blanks are filled by the first non-blank value from any loser.
    - Each loser gets a TOMBSTONE row (no DELETE) with merged_into_address_key
      and optionally merged_into_npi set. The grid builder skips tombstones in
      the overrides map and uses the merge map to redirect referral aggregation
      so the merge survives reload.

    Returns the number of loser tombstones written.
    """
    npi = str(npi)
    survivor_npi = str(survivor_npi) if survivor_npi else npi
    cross_npi = survivor_npi != npi
    # Coerce None → '' for address keys. Grid rows can carry None when a
    # row's address_key was nullified through Dash JSON serialization; if we
    # let that through, the tombstone INSERT writes merged_into=NULL and the
    # row stops looking like a tombstone (it gets filtered out of the merge map).
    survivor_address_key = survivor_address_key or ""
    loser_address_keys = [k or "" for k in loser_address_keys]
    # For same-NPI merges, drop any loser key equal to the survivor's. For
    # cross-NPI merges keep them — the loser and survivor are different rows.
    losers = (loser_address_keys if cross_npi
              else [k for k in loser_address_keys if k != survivor_address_key])
    if not losers:
        return 0

    fields = ["specialty", "institution", "address", "city", "state", "zip_code"]
    placeholders = ",".join("?" for _ in losers)
    sd = survivor_defaults or {}
    ld_by_key = {(l.get("address_key") or ""): l for l in (loser_defaults or [])}

    with _connect() as conn:
        # Read survivor + losers from DB (may not exist for lookup-only rows).
        survivor_row = conn.execute(
            "SELECT specialty, institution, address, city, state, zip_code, "
            "address_source, source, reviewed "
            "FROM referring_physicians WHERE npi = ? AND address_key = ?",
            (survivor_npi, survivor_address_key),
        ).fetchone()

        loser_rows = conn.execute(
            f"SELECT address_key, specialty, institution, address, city, state, "
            f"zip_code, address_source, reviewed "
            f"FROM referring_physicians WHERE npi = ? AND address_key IN ({placeholders})",
            (npi, *losers),
        ).fetchall()
        db_loser_by_key = {lr["address_key"]: lr for lr in loser_rows}

        # Seed survivor's working values from DB first, fall back to grid defaults.
        def _seed(field: str) -> str:
            if survivor_row is not None and survivor_row[field]:
                return survivor_row[field]
            return sd.get(field, "") or ""

        merged = {f: _seed(f) for f in fields}
        addr_source = _seed("address_source")
        reviewed = bool(
            (survivor_row and survivor_row["reviewed"]) or sd.get("reviewed")
        )

        # Fill blanks from each loser (DB row preferred, grid default fallback).
        for lk in losers:
            db_l = db_loser_by_key.get(lk)
            grid_l = ld_by_key.get(lk, {})

            def _lv(field: str) -> str:
                if db_l is not None and db_l[field]:
                    return db_l[field]
                return grid_l.get(field) or ""

            for f in fields:
                if not merged[f] and _lv(f):
                    merged[f] = _lv(f)
                    if f in ("address", "city", "state", "zip_code") and not addr_source:
                        addr_source = (
                            (db_l["address_source"] if db_l else None)
                            or grid_l.get("address_source")
                            or "manual"
                        )
            if not reviewed:
                if (db_l and db_l["reviewed"]) or grid_l.get("reviewed"):
                    reviewed = True

        now = datetime.now(timezone.utc).isoformat()

        # Upsert survivor with merged fields. INSERT path is required because
        # lookup-only rows have no override row yet.
        conn.execute(
            """INSERT INTO referring_physicians
               (npi, address_key, specialty, institution, address, city, state,
                zip_code, address_source, source, reviewed, updated_at, updated_by)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '')
               ON CONFLICT(npi, address_key) DO UPDATE SET
                   specialty      = excluded.specialty,
                   institution    = excluded.institution,
                   address        = excluded.address,
                   city           = excluded.city,
                   state          = excluded.state,
                   zip_code       = excluded.zip_code,
                   address_source = excluded.address_source,
                   reviewed       = excluded.reviewed,
                   updated_at     = excluded.updated_at""",
            (survivor_npi, survivor_address_key,
             merged["specialty"] or None, merged["institution"] or None,
             merged["address"] or "", merged["city"] or "",
             merged["state"] or "", merged["zip_code"] or "",
             addr_source or "", "manual", 1 if reviewed else 0, now),
        )

        # Tombstone each loser. Keep any existing fields so an unmerge is
        # possible later; only flip merged_into_address_key (and
        # merged_into_npi for cross-NPI merges).
        merged_into_npi_val = survivor_npi if cross_npi else None
        count = 0
        for lk in losers:
            conn.execute(
                """INSERT INTO referring_physicians
                   (npi, address_key, merged_into_address_key, merged_into_npi,
                    source, updated_at, updated_by)
                   VALUES (?, ?, ?, ?, 'merge', ?, '')
                   ON CONFLICT(npi, address_key) DO UPDATE SET
                       merged_into_address_key = excluded.merged_into_address_key,
                       merged_into_npi         = excluded.merged_into_npi,
                       updated_at              = excluded.updated_at""",
                (npi, lk, survivor_address_key, merged_into_npi_val, now),
            )
            count += 1

    _invalidate_referrals_cache()
    return count


def get_referring_merge_map() -> dict[tuple[str, str], tuple[str, str]]:
    """Return {(loser_npi, loser_address_key): (survivor_npi, survivor_address_key)}
    for all merge tombstones. Used by the grid builder and the loader to
    redirect referral aggregation.

    A tombstone row has merged_into_address_key IS NOT NULL. The survivor
    address_key may be '' (when the survivor has no city/state/zip in source).
    `merged_into_npi` is NULL on same-NPI tombstones (most cases) — those
    fall back to the loser's own NPI so the redirect is a simple addr_key swap.
    """
    with _connect() as conn:
        rows = conn.execute(
            "SELECT npi, address_key, merged_into_address_key, merged_into_npi "
            "FROM referring_physicians "
            "WHERE merged_into_address_key IS NOT NULL"
        ).fetchall()
    return {
        (r["npi"], r["address_key"]): (
            r["merged_into_npi"] or r["npi"],
            r["merged_into_address_key"],
        )
        for r in rows
    }


def referring_table_is_empty() -> bool:
    """Check if the referring_physicians table has any rows."""
    with _connect() as conn:
        row = conn.execute("SELECT COUNT(*) AS cnt FROM referring_physicians").fetchone()
    return row["cnt"] == 0


def get_referring_overrides_fingerprint() -> str:
    """Stable fingerprint of the referring_physicians table state.

    Used by the Referrals parquet cache to invalidate when overrides change.
    Backend-agnostic — works with both SQLite and Postgres.
    """
    try:
        with _connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS n, MAX(updated_at) AS ts FROM referring_physicians"
            ).fetchone()
    except Exception:
        return ""
    if not row or not row["n"]:
        return "0|"
    return f"{row['n']}|{row['ts'] or ''}"


def _invalidate_referrals_cache() -> None:
    """Drop the in-memory Referrals TTL cache so the next load sees fresh overrides.

    The on-disk parquet cache is invalidated separately via the override
    fingerprint baked into its signature (see loader._source_signature).
    """
    try:
        from data.loader import load_referrals
        load_referrals.cache_clear()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Institutions (relational entity)
# ---------------------------------------------------------------------------

def get_all_institutions() -> list[str]:
    """Return sorted list of all institution names."""
    with _connect() as conn:
        rows = conn.execute("SELECT name FROM institutions ORDER BY name").fetchall()
    return [r["name"] for r in rows]


def add_institution(name: str) -> None:
    """Add a new institution (no-op if exists)."""
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO institutions (name, created_at) VALUES (?, ?)",
            (name.strip(), now),
        )


def rename_institution(old_name: str, new_name: str) -> int:
    """Rename an institution — propagates to all referring_physicians rows
    AND records a global alias so raw-CSV referrals showing the old name
    get remapped to the new name on the next loader pass.

    Returns the number of physician rows updated.
    """
    new_name = new_name.strip()
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        # Update all physician override rows that explicitly carry the old name.
        cur = conn.execute(
            "UPDATE referring_physicians SET institution = ?, updated_at = ? WHERE institution = ?",
            (new_name, now, old_name),
        )
        count = cur.rowcount
        # Refresh the institution catalog row.
        conn.execute("DELETE FROM institutions WHERE name = ?", (old_name,))
        conn.execute(
            "INSERT OR IGNORE INTO institutions (name, created_at) VALUES (?, ?)",
            (new_name, now),
        )
        # Alias bookkeeping:
        # - Chain existing aliases: any alias whose canonical was the old
        #   name now points to the new name.
        # - Record the rename itself as an alias (old → new) so raw-CSV
        #   referrals showing the old string get remapped on load.
        # - Drop any self-alias that would result (alias == canonical) or
        #   any pre-existing alias whose key is the new name (no longer stale).
        conn.execute(
            "UPDATE institution_aliases SET canonical = ? WHERE canonical = ?",
            (new_name, old_name),
        )
        conn.execute(
            """INSERT INTO institution_aliases (alias, canonical, created_at)
               VALUES (?, ?, ?)
               ON CONFLICT(alias) DO UPDATE SET
                   canonical = excluded.canonical,
                   created_at = excluded.created_at""",
            (old_name, new_name, now),
        )
        conn.execute(
            "DELETE FROM institution_aliases WHERE alias = canonical"
        )
        conn.execute(
            "DELETE FROM institution_aliases WHERE alias = ?",
            (new_name,),
        )
    _invalidate_referrals_cache()
    return count


def get_institution_alias_map() -> dict[str, str]:
    """Return {alias: canonical} for all recorded institution renames.

    Used by the referrals loader to remap raw `DoctorInstitution` strings
    so the trend chart reflects user renames even for referrals whose
    (npi, address_key) doesn't match a stored override row.
    """
    try:
        with _connect() as conn:
            rows = conn.execute(
                "SELECT alias, canonical FROM institution_aliases"
            ).fetchall()
    except Exception:
        return {}
    return {r["alias"]: r["canonical"] for r in rows if r["alias"] and r["canonical"]}


def delete_institution(name: str) -> int:
    """Delete an institution — clears it from all referring_physicians rows.

    Returns the number of physician rows cleared.
    """
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        cur = conn.execute(
            "UPDATE referring_physicians SET institution = NULL, updated_at = ? WHERE institution = ?",
            (now, name),
        )
        count = cur.rowcount
        conn.execute("DELETE FROM institutions WHERE name = ?", (name,))
    _invalidate_referrals_cache()
    return count


def sync_institutions_from_physicians() -> None:
    """Ensure all distinct institution names in referring_physicians exist in institutions table."""
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        conn.execute(
            """INSERT OR IGNORE INTO institutions (name, created_at)
               SELECT DISTINCT institution, ?
               FROM referring_physicians
               WHERE institution IS NOT NULL AND institution != ''""",
            (now,),
        )


# ---------------------------------------------------------------------------
# Diagnosis overrides
# ---------------------------------------------------------------------------

def upsert_diagnosis_override(
    icd_code: str,
    category: str,
    subcategory: str = "",
    source: str = "manual",
    updated_by: str = "",
) -> None:
    """Insert or update a diagnosis category/subcategory override."""
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        conn.execute(
            """INSERT INTO diagnosis_overrides (icd_code, category, subcategory, source, updated_at, updated_by)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(icd_code) DO UPDATE SET
                   category    = excluded.category,
                   subcategory = excluded.subcategory,
                   source      = excluded.source,
                   updated_at  = excluded.updated_at,
                   updated_by  = excluded.updated_by""",
            (icd_code.strip(), category, subcategory, source, now, updated_by),
        )


def bulk_upsert_diagnosis_overrides(records: list[dict]) -> None:
    """Batch insert/update diagnosis overrides.

    Each record: {"icd_code": str, "category": str, "subcategory": str, "source": str}
    """
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        for rec in records:
            conn.execute(
                """INSERT INTO diagnosis_overrides (icd_code, category, subcategory, source, updated_at, updated_by)
                   VALUES (?, ?, ?, ?, ?, '')
                   ON CONFLICT(icd_code) DO UPDATE SET
                       category    = excluded.category,
                       subcategory = excluded.subcategory,
                       source      = excluded.source,
                       updated_at  = excluded.updated_at""",
                (rec["icd_code"].strip(), rec["category"], rec.get("subcategory", ""),
                 rec.get("source", "manual"), now),
            )


def get_all_diagnosis_overrides() -> dict[str, dict]:
    """Return {icd_code: {category, subcategory, source, reviewed}} for all overrides."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT icd_code, category, subcategory, source, reviewed FROM diagnosis_overrides"
        ).fetchall()
    return {
        r["icd_code"]: {
            "category": r["category"],
            "subcategory": r["subcategory"],
            "source": r["source"],
            "reviewed": bool(r["reviewed"]),
        }
        for r in rows
    }


def delete_diagnosis_override(icd_code: str) -> None:
    """Remove a diagnosis override (revert to base mapping)."""
    with _connect() as conn:
        conn.execute("DELETE FROM diagnosis_overrides WHERE icd_code = ?", (icd_code.strip(),))


# ---------------------------------------------------------------------------
# Diagnosis taxonomy
# ---------------------------------------------------------------------------

def get_diagnosis_taxonomy() -> dict[str, list[str]]:
    """Return {category: [subcategory, ...]} from the taxonomy table."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT category, subcategory FROM diagnosis_taxonomy ORDER BY category, sort_order, subcategory"
        ).fetchall()
    result: dict[str, list[str]] = {}
    for r in rows:
        cat = r["category"]
        sub = r["subcategory"]
        if cat not in result:
            result[cat] = []
        result[cat].append(sub)
    return result


def taxonomy_table_row_count() -> int:
    """Return the number of rows in the diagnosis_taxonomy table."""
    with _connect() as conn:
        row = conn.execute("SELECT COUNT(*) AS cnt FROM diagnosis_taxonomy").fetchone()
    return row["cnt"]


def seed_taxonomy(taxonomy: dict[str, list[str]]) -> int:
    """Populate the taxonomy table from a dict. Only inserts missing entries."""
    now = datetime.now(timezone.utc).isoformat()
    count = 0
    with _connect() as conn:
        for cat, subs in taxonomy.items():
            for i, sub in enumerate(subs):
                try:
                    conn.execute(
                        "INSERT INTO diagnosis_taxonomy (category, subcategory, sort_order) VALUES (?, ?, ?)",
                        (cat, sub, i),
                    )
                    count += 1
                except Exception:
                    pass  # Already exists
    return count


def add_taxonomy_entry(category: str, subcategory: str) -> None:
    """Add a new category/subcategory to the taxonomy."""
    with _connect() as conn:
        max_order = conn.execute(
            "SELECT COALESCE(MAX(sort_order), -1) + 1 AS next_order FROM diagnosis_taxonomy WHERE category = ?",
            (category,),
        ).fetchone()["next_order"]
        conn.execute(
            "INSERT OR IGNORE INTO diagnosis_taxonomy (category, subcategory, sort_order) VALUES (?, ?, ?)",
            (category, subcategory, max_order),
        )


def rename_taxonomy_subcategory(category: str, old_sub: str, new_sub: str) -> int:
    """Rename a subcategory within a category. Also updates diagnosis_overrides."""
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        conn.execute(
            "UPDATE diagnosis_taxonomy SET subcategory = ? WHERE category = ? AND subcategory = ?",
            (new_sub, category, old_sub),
        )
        cur = conn.execute(
            "UPDATE diagnosis_overrides SET subcategory = ?, updated_at = ? WHERE category = ? AND subcategory = ?",
            (new_sub, now, category, old_sub),
        )
        return cur.rowcount


def delete_taxonomy_entry(category: str, subcategory: str) -> None:
    """Remove a subcategory from the taxonomy."""
    with _connect() as conn:
        conn.execute(
            "DELETE FROM diagnosis_taxonomy WHERE category = ? AND subcategory = ?",
            (category, subcategory),
        )


def diagnosis_table_row_count() -> int:
    """Return the number of rows in the diagnosis_overrides table."""
    with _connect() as conn:
        row = conn.execute("SELECT COUNT(*) AS cnt FROM diagnosis_overrides").fetchone()
    return row["cnt"]


def set_diagnosis_reviewed_bulk(icd_codes: list[str], reviewed: bool = True) -> int:
    """Mark multiple ICD codes as reviewed/unreviewed. Returns rows updated."""
    now = datetime.now(timezone.utc).isoformat()
    val = 1 if reviewed else 0
    count = 0
    with _connect() as conn:
        for code in icd_codes:
            cur = conn.execute(
                "UPDATE diagnosis_overrides SET reviewed = ?, updated_at = ? WHERE icd_code = ?",
                (val, now, code.strip()),
            )
            count += cur.rowcount
    return count


# ---------------------------------------------------------------------------
# Insurance / payor rate overrides
# ---------------------------------------------------------------------------

def _load_base_payor_rates() -> list[dict]:
    """Load the seed CSV of payor rates (data/payor_rates.csv)."""
    import csv
    csv_path = Path(__file__).parent / "payor_rates.csv"
    if not csv_path.exists():
        return []
    with open(csv_path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def seed_insurance_rates() -> int:
    """Populate insurance_rates + history from CSV if the main table is empty."""
    with _connect() as conn:
        count = conn.execute("SELECT COUNT(*) AS cnt FROM insurance_rates").fetchone()["cnt"]
        if count > 0:
            return 0
    rows = _load_base_payor_rates()
    if not rows:
        return 0
    now = datetime.now(timezone.utc).isoformat()

    # Group rows by canonical payor name (strip year suffixes)
    # Rows with history_only=true go only into history, not the main table
    canonical = {}  # payor -> list of rate dicts
    for r in rows:
        payor = r["payor"].strip()
        canonical.setdefault(payor, []).append(r)

    with _connect() as conn:
        for payor, rate_rows in canonical.items():
            # Sort by effective_date, most recent last
            rate_rows.sort(key=lambda x: x.get("effective_date", ""))

            # The last row is the current rate for the main table
            current = rate_rows[-1]
            conn.execute(
                """INSERT OR IGNORE INTO insurance_rates
                   (payor, rate_method, em_cf, other_cf, pct_medicare,
                    effective_date, source, notes, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    payor,
                    current.get("rate_method", "pct_medicare"),
                    float(current["em_cf"]) if current.get("em_cf") else None,
                    float(current["other_cf"]) if current.get("other_cf") else None,
                    float(current.get("pct_medicare") or 100),
                    current.get("effective_date", ""),
                    current.get("source", "csv"),
                    current.get("notes", ""),
                    now,
                ),
            )

            # All rows go into history
            for r in rate_rows:
                eff = r.get("effective_date", "")
                if not eff:
                    continue
                conn.execute(
                    """INSERT OR IGNORE INTO insurance_rate_history
                       (payor, effective_date, rate_method, em_cf, other_cf,
                        pct_medicare, source, notes, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        payor,
                        eff,
                        r.get("rate_method", "pct_medicare"),
                        float(r["em_cf"]) if r.get("em_cf") else None,
                        float(r["other_cf"]) if r.get("other_cf") else None,
                        float(r.get("pct_medicare") or 100),
                        r.get("source", "csv"),
                        r.get("notes", ""),
                        now,
                    ),
                )

    return len(canonical)


def upsert_insurance_rate(
    payor: str,
    rate_method: str = "pct_medicare",
    em_cf: float | None = None,
    other_cf: float | None = None,
    pct_medicare: float = 100.0,
    effective_date: str = "",
    source: str = "manual",
    notes: str = "",
) -> None:
    """Insert or update a payor's current rate."""
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        conn.execute(
            """INSERT INTO insurance_rates
               (payor, rate_method, em_cf, other_cf, pct_medicare,
                effective_date, source, notes, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(payor) DO UPDATE SET
                   rate_method    = excluded.rate_method,
                   em_cf          = excluded.em_cf,
                   other_cf       = excluded.other_cf,
                   pct_medicare   = excluded.pct_medicare,
                   effective_date = excluded.effective_date,
                   source         = excluded.source,
                   notes          = excluded.notes,
                   updated_at     = excluded.updated_at""",
            (payor.strip(), rate_method, em_cf, other_cf, pct_medicare,
             effective_date, source, notes, now),
        )


def get_all_insurance_rates() -> list[dict]:
    """Return all payor rates as a list of dicts (one per payor)."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT payor, rate_method, em_cf, other_cf, pct_medicare, "
            "effective_date, source, notes, updated_at "
            "FROM insurance_rates ORDER BY payor"
        ).fetchall()
    return [dict(r) for r in rows]


def delete_insurance_rate(payor: str) -> None:
    """Remove a payor rate and its history."""
    with _connect() as conn:
        conn.execute("DELETE FROM insurance_rates WHERE payor = ?", (payor.strip(),))
        conn.execute("DELETE FROM insurance_rate_history WHERE payor = ?", (payor.strip(),))


# ---------------------------------------------------------------------------
# Rate history
# ---------------------------------------------------------------------------

def upsert_rate_history(
    payor: str,
    effective_date: str,
    end_date: str = "",
    rate_method: str = "pct_medicare",
    em_cf: float | None = None,
    other_cf: float | None = None,
    pct_medicare: float = 100.0,
    source: str = "manual",
    notes: str = "",
) -> None:
    """Insert or update a rate history entry."""
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        conn.execute(
            """INSERT INTO insurance_rate_history
               (payor, effective_date, end_date, rate_method, em_cf, other_cf,
                pct_medicare, source, notes, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(payor, effective_date) DO UPDATE SET
                   end_date       = excluded.end_date,
                   rate_method    = excluded.rate_method,
                   em_cf          = excluded.em_cf,
                   other_cf       = excluded.other_cf,
                   pct_medicare   = excluded.pct_medicare,
                   source         = excluded.source,
                   notes          = excluded.notes,
                   updated_at     = excluded.updated_at""",
            (payor.strip(), effective_date, end_date or None, rate_method,
             em_cf, other_cf, pct_medicare, source, notes, now),
        )


def get_rate_history(payor: str) -> list[dict]:
    """Return all rate history entries for a payor, newest first."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT id, payor, effective_date, end_date, rate_method, "
            "em_cf, other_cf, pct_medicare, source, notes, updated_at "
            "FROM insurance_rate_history WHERE payor = ? "
            "ORDER BY effective_date DESC",
            (payor.strip(),),
        ).fetchall()
    return [dict(r) for r in rows]


def delete_rate_history_entry(entry_id: int) -> None:
    """Remove a single rate history entry by id."""
    with _connect() as conn:
        conn.execute("DELETE FROM insurance_rate_history WHERE id = ?", (entry_id,))


def get_rate_at_date(payor: str, service_date: str) -> dict | None:
    """Return the rate in effect for a payor on a given date.

    Looks up the most recent history entry with effective_date <= service_date.
    Falls back to the main insurance_rates table if no history exists.
    """
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM insurance_rate_history "
            "WHERE payor = ? AND effective_date <= ? "
            "ORDER BY effective_date DESC LIMIT 1",
            (payor.strip(), service_date),
        ).fetchone()
        if row:
            return dict(row)
        # Fallback to main table
        row = conn.execute(
            "SELECT * FROM insurance_rates WHERE payor = ?",
            (payor.strip(),),
        ).fetchone()
        return dict(row) if row else None


# ---------------------------------------------------------------------------
# Payor mappings (raw insurance name → standardized payor + broad category)
# ---------------------------------------------------------------------------

def seed_payor_mappings(rows: list[dict]) -> int:
    """Bulk INSERT OR IGNORE payor mapping rows.

    Each dict must have keys: raw_name, standardized_payor, broad_category.
    Existing mappings are never overwritten.
    """
    if not rows:
        return 0
    now = datetime.now(timezone.utc).isoformat()
    inserted = 0
    with _connect() as conn:
        for r in rows:
            cur = conn.execute(
                """INSERT OR IGNORE INTO payor_mappings
                   (raw_name, standardized_payor, broad_category, reviewed, updated_at)
                   VALUES (?, ?, ?, 0, ?)""",
                (r["raw_name"], r.get("standardized_payor", ""),
                 r.get("broad_category", "Other/Unknown"), now),
            )
            inserted += cur.rowcount
    return inserted


def get_all_payor_mappings() -> list[dict]:
    """Return all payor mappings ordered by raw_name."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT raw_name, standardized_payor, broad_category, phdsc_category, "
            "reviewed, ai_explanation, updated_at "
            "FROM payor_mappings ORDER BY raw_name"
        ).fetchall()
    return [dict(r) for r in rows]


def upsert_payor_mapping(
    raw_name: str,
    standardized_payor: str = "",
    broad_category: str = "Other/Unknown",
    phdsc_category: str = "9",
    reviewed: int = 0,
    ai_explanation: str | None = None,
) -> None:
    """Insert or update a single payor mapping.

    ``ai_explanation=None`` preserves any existing explanation on update;
    pass ``""`` to explicitly clear it.
    """
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        if ai_explanation is None:
            conn.execute(
                """INSERT INTO payor_mappings
                   (raw_name, standardized_payor, broad_category, phdsc_category,
                    reviewed, ai_explanation, updated_at)
                   VALUES (?, ?, ?, ?, ?, '', ?)
                   ON CONFLICT(raw_name) DO UPDATE SET
                       standardized_payor = excluded.standardized_payor,
                       broad_category     = excluded.broad_category,
                       phdsc_category     = excluded.phdsc_category,
                       reviewed           = excluded.reviewed,
                       updated_at         = excluded.updated_at""",
                (raw_name.strip(), standardized_payor, broad_category, phdsc_category,
                 1 if reviewed else 0, now),
            )
        else:
            conn.execute(
                """INSERT INTO payor_mappings
                   (raw_name, standardized_payor, broad_category, phdsc_category,
                    reviewed, ai_explanation, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(raw_name) DO UPDATE SET
                       standardized_payor = excluded.standardized_payor,
                       broad_category     = excluded.broad_category,
                       phdsc_category     = excluded.phdsc_category,
                       reviewed           = excluded.reviewed,
                       ai_explanation     = excluded.ai_explanation,
                       updated_at         = excluded.updated_at""",
                (raw_name.strip(), standardized_payor, broad_category, phdsc_category,
                 1 if reviewed else 0, ai_explanation, now),
            )


def get_payor_mapping_dict() -> dict:
    """Return {raw_name: {"standardized_payor": ..., "broad_category": ..., "phdsc_category": ...}} for fast lookup."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT raw_name, standardized_payor, broad_category, phdsc_category "
            "FROM payor_mappings"
        ).fetchall()
    return {
        r["raw_name"]: {
            "standardized_payor": r["standardized_payor"],
            "broad_category": r["broad_category"],
            "phdsc_category": r["phdsc_category"],
        }
        for r in rows
    }


def rename_standardized_payor(old_name: str, new_name: str) -> int:
    """Rename a standardized payor across all mapping rows. Returns count updated."""
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        cur = conn.execute(
            "UPDATE payor_mappings SET standardized_payor = ?, updated_at = ? "
            "WHERE standardized_payor = ?",
            (new_name.strip(), now, old_name.strip()),
        )
        return cur.rowcount


def delete_standardized_payor(name: str) -> int:
    """Clear a standardized payor from all mapping rows (sets to empty). Returns count updated."""
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        cur = conn.execute(
            "UPDATE payor_mappings SET standardized_payor = '', updated_at = ? "
            "WHERE standardized_payor = ?",
            (now, name.strip()),
        )
        return cur.rowcount


def get_standardized_payor_counts() -> list[dict]:
    """Return [{name, mapping_count}] for all distinct standardized payors."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT standardized_payor AS name, COUNT(*) AS mapping_count "
            "FROM payor_mappings WHERE standardized_payor != '' "
            "GROUP BY standardized_payor ORDER BY standardized_payor"
        ).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Revenue adjustment settings (category multipliers + realization factor)
# ---------------------------------------------------------------------------

_REVENUE_ADJ_DEFAULTS = {
    "enabled": 0,
    "realization": 90,
    "ar_lag": 30,
    "ar_lag_enabled": 0,
    "mult_Medicare": 100,
    "mult_Medicaid": 90,
    "mult_Private": 130,
    "mult_Military/VA": 100,
    "mult_Workers Comp": 125,
    "mult_Tribal/IHS": 100,
    "mult_Self Pay": 50,
    "mult_Other/Unknown": 100,
}


def get_revenue_adj_settings() -> dict[str, float]:
    """Return all revenue adjustment settings, filling in defaults."""
    result = dict(_REVENUE_ADJ_DEFAULTS)
    with _connect() as conn:
        rows = conn.execute("SELECT key, value FROM revenue_adj_settings").fetchall()
    for r in rows:
        result[r["key"]] = r["value"]
    return result


def save_revenue_adj_settings(settings: dict[str, float]) -> None:
    """Upsert revenue adjustment settings."""
    with _connect() as conn:
        for k, v in settings.items():
            conn.execute(
                "INSERT INTO revenue_adj_settings (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (k, float(v)),
            )


# ---------------------------------------------------------------------------
# Generic string-valued app settings (model picks, feature toggles, etc.)
# Distinct from revenue_adj_settings (REAL only) so we can store text values.
# ---------------------------------------------------------------------------

def get_app_setting(key: str, default: str = "") -> str:
    """Return a single app setting, or ``default`` if not set."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT value FROM app_settings WHERE key = ?", (key,)
        ).fetchone()
    return row["value"] if row else default


def set_app_setting(key: str, value: str) -> None:
    """Upsert one app setting."""
    with _connect() as conn:
        conn.execute(
            "INSERT INTO app_settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, str(value)),
        )
