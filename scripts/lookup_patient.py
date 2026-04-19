#!/usr/bin/env python3
"""Reverse-lookup a 6-char PatientCode (shown in CPT Audit / OTV Audit grids)
back to the real patient name + MRN.

Requires the same PHI_SALT used to produce the sanitized dataset AND access
to the raw Lookup - Patients.csv. Run on your local machine only — this
script must never be deployed to the cloud host.

Usage:
    PHI_SALT=<same-salt> python scripts/lookup_patient.py A7F2B3 B891C4
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import DATA_DIR_RAW
from data.sanitize.core import load_salt, short_patient_code


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("Usage: PHI_SALT=<salt> python scripts/lookup_patient.py <code> [<code>...]")
        return 2

    codes = [c.strip().upper() for c in argv[1:]]
    salt = load_salt()

    src = DATA_DIR_RAW / "Lookup" / "Lookup - Patients.csv"
    if not src.exists():
        print(f"ERROR: raw Lookup - Patients file not found at {src}")
        return 2

    import pandas as pd

    try:
        df = pd.read_csv(src, encoding="utf-8-sig", engine="pyarrow")
    except Exception:
        df = pd.read_csv(src, encoding="utf-8-sig", on_bad_lines="skip", low_memory=False)

    if "PatientId" not in df.columns:
        print("ERROR: expected PatientId column in Lookup - Patients.csv")
        return 2

    # Compute short code for every row, then match
    df["_code"] = df["PatientId"].map(lambda v: short_patient_code(v, salt))
    targets = set(codes)
    hits = df[df["_code"].isin(targets)].copy()

    print(f"Looking up {len(codes)} code(s) against {len(df):,} patients...")
    print()

    if hits.empty:
        print("No matches. (Confirm PHI_SALT matches the one used for sanitization.)")
        return 1

    for code in codes:
        match = hits[hits["_code"] == code]
        if match.empty:
            print(f"  {code}  <no match>")
            continue
        for _, row in match.iterrows():
            name = row.get("PatientName", "?")
            mrn = row.get("PatientId", "?")
            first = row.get("FirstAppointment", "")
            last = row.get("LastAppointment", "")
            dept = row.get("Department", "")
            print(f"  {code}  {mrn}  {name:32s}  dept={dept!s:12s}  appts {first} → {last}")

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
