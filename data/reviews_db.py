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
"""


def _connect():
    conn = sqlite3.connect(str(DB_PATH), timeout=5)
    conn.execute("PRAGMA journal_mode=WAL")  # better concurrent reads
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_table():
    with _connect() as conn:
        conn.executescript(_SCHEMA)


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
    source: str = "manual",
    updated_by: str = "",
) -> None:
    """Insert or update a referring physician override."""
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        existing = conn.execute(
            "SELECT specialty, institution FROM referring_physicians WHERE npi = ? AND address_key = ?",
            (str(npi), address_key),
        ).fetchone()
        if existing:
            specialty = specialty if specialty is not None else existing["specialty"]
            institution = institution if institution is not None else existing["institution"]
        conn.execute(
            """INSERT INTO referring_physicians (npi, address_key, specialty, institution, source, updated_at, updated_by)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(npi, address_key) DO UPDATE SET
                   specialty   = excluded.specialty,
                   institution = excluded.institution,
                   source      = excluded.source,
                   updated_at  = excluded.updated_at,
                   updated_by  = excluded.updated_by""",
            (str(npi), address_key, specialty, institution, source, now, updated_by),
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
    """Return {npi|address_key: {specialty, institution, source, reviewed}} for all overrides."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT npi, address_key, specialty, institution, source, reviewed FROM referring_physicians"
        ).fetchall()
    return {
        f"{r['npi']}|{r['address_key']}": {
            "specialty": r["specialty"], "institution": r["institution"],
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
