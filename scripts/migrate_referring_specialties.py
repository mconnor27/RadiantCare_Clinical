"""One-shot migration: rewrite referring_physicians.specialty to ABMS canonical names.

The DB used to store loader-canonical names ("Family Medicine", "Obstetrics &
Gynecology", "Orthopaedic Surgery", etc.) that diverged from the ABMS canonical
list in config/specialties.py. This script translates every stored value via
normalize_specialty() and DEPT_BUCKETS, then UPDATEs the column.

Usage:
    # Dry-run (default) — reports what would change without writing.
    .venv/bin/python scripts/migrate_referring_specialties.py

    # Apply changes.
    .venv/bin/python scripts/migrate_referring_specialties.py --commit

Works against both backends:
    - SQLite (default, reviews.db at project root)
    - Postgres (when REVIEWS_DB_URL or DATABASE_URL is set)

Safe to run multiple times. Rows already in canonical form are left alone.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

# Allow running from project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config.specialties import ABMS_SPECIALTIES, normalize_specialty, bucket_to_dept
from data.reviews_db import _connect, _USE_POSTGRES


def _canonicalize(value: str) -> str:
    """Run a stored specialty through the unified normalize + bucket pipeline."""
    if not value:
        return value
    return bucket_to_dept(normalize_specialty(value))


def _classify(distinct: Counter) -> tuple[list, list, list]:
    """Bucket distinct stored values into (no_change, will_rename, leftovers)."""
    no_change, will_rename, leftovers = [], [], []
    abms_set = set(ABMS_SPECIALTIES)
    for value, count in distinct.most_common():
        new = _canonicalize(value)
        if new == value and new in abms_set:
            no_change.append((value, count))
        elif new != value and new in abms_set:
            will_rename.append((value, new, count))
        else:
            # normalize_specialty returned the input unchanged AND it's not in ABMS
            leftovers.append((value, count))
    return no_change, will_rename, leftovers


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument(
        "--commit",
        action="store_true",
        help="Perform the UPDATE. Default is dry-run.",
    )
    args = ap.parse_args()

    backend = "Postgres" if _USE_POSTGRES else "SQLite"
    print(f"\n=== Referring-physician specialty migration ({backend}) ===\n")

    with _connect() as conn:
        rows = conn.execute(
            "SELECT specialty FROM referring_physicians "
            "WHERE specialty IS NOT NULL AND specialty != ''"
        ).fetchall()

    if not rows:
        print("No rows with a specialty value — nothing to migrate.")
        return 0

    distinct = Counter(r["specialty"] for r in rows)
    no_change, will_rename, leftovers = _classify(distinct)

    total_rows = sum(distinct.values())
    print(f"Total rows with a specialty: {total_rows}")
    print(f"Distinct values:             {len(distinct)}\n")

    print(f"=== Already canonical ({len(no_change)} values, "
          f"{sum(c for _, c in no_change)} rows) ===")
    for v, c in no_change:
        print(f"  {c:>5}  {v}")

    print(f"\n=== Will be renamed ({len(will_rename)} values, "
          f"{sum(c for _, _, c in will_rename)} rows) ===")
    for old, new, c in will_rename:
        print(f"  {c:>5}  {old!r:<55}  →  {new!r}")

    print(f"\n=== Unmapped — left alone ({len(leftovers)} values, "
          f"{sum(c for _, c in leftovers)} rows) ===")
    for v, c in leftovers:
        print(f"  {c:>5}  {v!r}")

    if not args.commit:
        print("\n(Dry-run — pass --commit to apply the renames.)\n")
        return 0

    if not will_rename:
        print("\nNothing to apply.\n")
        return 0

    print("\nApplying renames...")
    updated = 0
    with _connect() as conn:
        for old, new, _ in will_rename:
            cur = conn.execute(
                "UPDATE referring_physicians SET specialty = ? WHERE specialty = ?",
                (new, old),
            )
            updated += cur.rowcount
    print(f"Done — {updated} rows updated.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
