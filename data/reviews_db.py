"""SQLite-backed persistence for CPT audit reviews.

Stores review decisions (OK / Fixed) with reviewer and timestamp.
The database file lives alongside the project at PROJECT_ROOT/reviews.db.
Thread-safe — each call opens and closes its own connection.
"""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from config.settings import PROJECT_ROOT

DB_PATH = PROJECT_ROOT / "reviews.db"

_SCHEMA = """
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
    specialty     TEXT,
    institution   TEXT,
    address       TEXT,
    city          TEXT,
    state         TEXT,
    zip_code      TEXT,
    address_source TEXT NOT NULL DEFAULT '',
    source        TEXT NOT NULL DEFAULT 'manual',
    reviewed      INTEGER NOT NULL DEFAULT 0,
    updated_at    TEXT NOT NULL,
    updated_by    TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (npi, address_key)
);

CREATE TABLE IF NOT EXISTS institutions (
    name          TEXT PRIMARY KEY,
    created_at    TEXT NOT NULL
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
"""


def _connect():
    conn = sqlite3.connect(str(DB_PATH), timeout=5)
    conn.execute("PRAGMA journal_mode=WAL")  # better concurrent reads
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_table():
    with _connect() as conn:
        conn.executescript(_SCHEMA)
        # Migration: add reviewed column to diagnosis_overrides if missing
        cols = [r[1] for r in conn.execute("PRAGMA table_info(diagnosis_overrides)").fetchall()]
        if "reviewed" not in cols:
            conn.execute("ALTER TABLE diagnosis_overrides ADD COLUMN reviewed INTEGER NOT NULL DEFAULT 0")
        # Migration: add address columns to referring_physicians if missing
        rp_cols = [r[1] for r in conn.execute("PRAGMA table_info(referring_physicians)").fetchall()]
        for col, default in [("address", ""), ("city", ""), ("state", ""), ("zip_code", ""), ("address_source", "")]:
            if col not in rp_cols:
                conn.execute(f"ALTER TABLE referring_physicians ADD COLUMN {col} TEXT NOT NULL DEFAULT '{default}'")


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
) -> None:
    """Insert or update a referring physician override."""
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        existing = conn.execute(
            "SELECT specialty, institution, address, city, state, zip_code, address_source "
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
        conn.execute(
            """INSERT INTO referring_physicians
               (npi, address_key, specialty, institution, address, city, state, zip_code, address_source, source, updated_at, updated_by)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                   updated_by     = excluded.updated_by""",
            (str(npi), address_key, specialty, institution,
             address or "", city or "", state or "", zip_code or "",
             address_source or "", source, now, updated_by),
        )


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


def get_all_referring_overrides() -> dict[str, dict]:
    """Return {npi|address_key: {specialty, institution, address fields, source, reviewed}}."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT npi, address_key, specialty, institution, "
            "address, city, state, zip_code, address_source, source, reviewed "
            "FROM referring_physicians"
        ).fetchall()
    return {
        f"{r['npi']}|{r['address_key']}": {
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


def referring_table_is_empty() -> bool:
    """Check if the referring_physicians table has any rows."""
    with _connect() as conn:
        row = conn.execute("SELECT COUNT(*) AS cnt FROM referring_physicians").fetchone()
    return row["cnt"] == 0


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
    """Rename an institution — propagates to all referring_physicians rows.

    Returns the number of physician rows updated.
    """
    new_name = new_name.strip()
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        # Update all physician rows
        cur = conn.execute(
            "UPDATE referring_physicians SET institution = ?, updated_at = ? WHERE institution = ?",
            (new_name, now, old_name),
        )
        count = cur.rowcount
        # Rename the institution record
        conn.execute("DELETE FROM institutions WHERE name = ?", (old_name,))
        conn.execute(
            "INSERT OR IGNORE INTO institutions (name, created_at) VALUES (?, ?)",
            (new_name, now),
        )
    return count


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
