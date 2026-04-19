#!/usr/bin/env python3
"""Build the PHI-sanitized mirror of the AURA reports directory.

Reads the raw data from DATA_DIR_RAW (OneDrive path) and writes de-identified
copies to DATA_DIR_SANITIZED, mirroring the folder structure exactly so the
existing data/loader.py reads the output unchanged when PHI_MODE=true.

Usage:
    PHI_SALT=<long-random-hex> python scripts/sanitize.py

The salt must match across runs so PatientId hashes remain stable across
incremental refreshes. Store it in your local .env file (gitignored).
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import DATA_DIR_RAW, DATA_DIR_SANITIZED
from data.sanitize.core import load_salt
from data.sanitize.rules import sanitize_all


def _fmt_row(entry: dict) -> str:
    name = entry.get("name", "?")
    status = entry.get("status", "")
    files = entry.get("files", 0)
    rin = entry.get("rows_in", 0)
    rout = entry.get("rows_out", 0)
    dropped = ",".join(entry.get("dropped", []) or []) or "-"
    hashed = ",".join(entry.get("hashed", []) or []) or "-"
    short = entry.get("short_code_from") or "-"
    return (
        f"  {name:24s} {status:18s} files={files:<3d} "
        f"rows={rin:>9,}→{rout:>9,}  "
        f"dropped=[{dropped}]  hashed=[{hashed}]  code_from={short}"
    )


def main() -> int:
    salt = load_salt()

    raw = DATA_DIR_RAW
    out = DATA_DIR_SANITIZED

    if not raw.exists():
        print(f"ERROR: raw data dir does not exist: {raw}")
        return 2

    print(f"Raw:       {raw}")
    print(f"Sanitized: {out}")
    print(f"Salt:      {len(salt)} chars loaded from PHI_SALT")
    print()

    out.mkdir(parents=True, exist_ok=True)

    t0 = time.time()
    audit = sanitize_all(raw, out, salt)
    elapsed = time.time() - t0

    print("Per-dataset summary:")
    for entry in audit:
        print(_fmt_row(entry))
    print()

    # Totals
    total_files = sum(e.get("files", 0) for e in audit)
    total_in = sum(e.get("rows_in", 0) for e in audit)
    total_out = sum(e.get("rows_out", 0) for e in audit)
    print(
        f"Totals: {total_files} files, "
        f"{total_in:,} rows in → {total_out:,} rows out, "
        f"{elapsed:.1f}s"
    )

    # Write audit JSON (without salt, safe to keep alongside sanitized data)
    audit_path = out / "_sanitize_audit.json"
    audit_path.write_text(json.dumps({
        "raw_root": str(raw),
        "sanitized_root": str(out),
        "elapsed_seconds": round(elapsed, 2),
        "datasets": audit,
    }, indent=2, default=str))
    print(f"Audit log: {audit_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
