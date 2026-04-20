"""One-shot migration: Clinical reviews.db  →  Supabase Postgres `clinical` schema.

Usage:
    PG_URL="postgresql://..."  python scripts/migrate_reviews_to_pg.py
    TARGET_SCHEMA=clinical_test PG_URL=... python scripts/migrate_reviews_to_pg.py

Safety:
  - Destination schema must already exist (created by Phase 2.1).
  - Aborts if any target table already has rows, so rerun requires cleanup.
  - Source reviews.db is opened read-only via URI.
  - Prints row counts per table at the end.
"""

from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path

# Allow running from project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import psycopg2
from psycopg2.extras import execute_values

SQLITE_PATH = PROJECT_ROOT / "reviews.db"
PG_URL = os.environ["PG_URL"]
TARGET_SCHEMA = os.environ.get("TARGET_SCHEMA", "clinical")

TABLES = [
    # (table_name, column list) — order matters for FK-safe insert,
    # but reviews.db has no FKs, so any order works.
    ("cpt_reviews", ["session_id", "status", "reviewer", "updated_at"]),
    ("cpt_course_reviews", ["course_key", "status", "reviewer", "updated_at"]),
    ("referring_physicians", [
        "npi", "address_key", "specialty", "institution", "address", "city",
        "state", "zip_code", "address_source", "source", "reviewed",
        "updated_at", "updated_by",
    ]),
    ("institutions", ["name", "created_at"]),
    ("diagnosis_taxonomy", ["category", "subcategory", "sort_order"]),
    ("diagnosis_overrides", [
        "icd_code", "category", "subcategory", "source", "reviewed",
        "updated_at", "updated_by",
    ]),
    ("insurance_rates", [
        "payor", "rate_method", "em_cf", "other_cf", "pct_medicare",
        "effective_date", "source", "notes", "updated_at",
    ]),
    ("insurance_rate_history", [
        "id", "payor", "effective_date", "end_date", "rate_method",
        "em_cf", "other_cf", "pct_medicare", "source", "notes", "updated_at",
    ]),
    ("payor_mappings", [
        "raw_name", "standardized_payor", "broad_category", "phdsc_category",
        "reviewed", "updated_at",
    ]),
    ("revenue_adj_settings", ["key", "value"]),
]


def main() -> int:
    if not SQLITE_PATH.exists():
        print(f"[migrate] {SQLITE_PATH} not found — nothing to migrate")
        return 0

    print(f"[migrate] source : {SQLITE_PATH}")
    print(f"[migrate] schema : {TARGET_SCHEMA}")

    # Open SQLite read-only
    src = sqlite3.connect(f"file:{SQLITE_PATH}?mode=ro", uri=True)
    src.row_factory = sqlite3.Row

    dst = psycopg2.connect(PG_URL)
    dst_cur = dst.cursor()
    dst_cur.execute(f'SET search_path TO "{TARGET_SCHEMA}", public')

    # Ensure tables exist in destination — call the app's own _ensure_table()
    # with REVIEWS_DB_URL set so it routes to Postgres.
    os.environ["REVIEWS_DB_URL"] = PG_URL
    os.environ["REVIEWS_DB_SCHEMA"] = TARGET_SCHEMA
    # Importing the module triggers _ensure_table() for the Postgres path.
    from data import reviews_db  # noqa: F401
    print("[migrate] tables ensured")

    # Abort if destination has data
    for name, _ in TABLES:
        dst_cur.execute(f'SELECT COUNT(*) FROM "{TARGET_SCHEMA}"."{name}"')
        count = dst_cur.fetchone()[0]
        if count > 0:
            print(f"[migrate] ABORT: {TARGET_SCHEMA}.{name} already has {count} rows.")
            print("  Run: TRUNCATE per-table, or choose a different TARGET_SCHEMA.")
            return 1

    summary: list[tuple[str, int, int]] = []

    for name, cols in TABLES:
        try:
            rows = src.execute(f'SELECT {", ".join(cols)} FROM "{name}"').fetchall()
        except sqlite3.OperationalError as exc:
            print(f"  [warn] source table {name} missing ({exc}); skipping")
            summary.append((name, 0, 0))
            continue

        src_count = len(rows)
        if src_count == 0:
            summary.append((name, 0, 0))
            continue

        col_sql = ", ".join(f'"{c}"' for c in cols)
        values = [tuple(r[c] for c in cols) for r in rows]

        execute_values(
            dst_cur,
            f'INSERT INTO "{TARGET_SCHEMA}"."{name}" ({col_sql}) VALUES %s',
            values,
        )

        dst_cur.execute(f'SELECT COUNT(*) FROM "{TARGET_SCHEMA}"."{name}"')
        dst_count = dst_cur.fetchone()[0]
        mark = "✓" if src_count == dst_count else "✗"
        print(f"  {mark} {name}: {src_count} → {dst_count}")
        summary.append((name, src_count, dst_count))

    # Reset the SERIAL sequence for insurance_rate_history.id so future
    # auto-inserts don't collide with copied IDs.
    dst_cur.execute(f'''
        SELECT setval(
            pg_get_serial_sequence('"{TARGET_SCHEMA}"."insurance_rate_history"', 'id'),
            COALESCE((SELECT MAX(id) FROM "{TARGET_SCHEMA}"."insurance_rate_history"), 0) + 1,
            false
        )
    ''')

    dst.commit()
    dst_cur.close()
    dst.close()
    src.close()

    bad = sum(1 for _, s, d in summary if s != d)
    total_src = sum(s for _, s, _ in summary)
    total_dst = sum(d for _, _, d in summary)
    print(f"\n[migrate] totals: src={total_src} dst={total_dst} ({len(summary)} tables, {bad} mismatches)")
    return 0 if bad == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
