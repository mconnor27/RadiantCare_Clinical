#!/usr/bin/env python3
"""Look up patients by ICD code across all datasets.

Usage:
    python tools/icd_lookup.py D49.7
    python tools/icd_lookup.py M61          # prefix match
    python tools/icd_lookup.py 728.13 M61   # multiple codes
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
from data.loader import (
    load_treatment_detail, load_clinic_visits, load_simulations,
    load_courses, load_workflow, load_diagnosis,
)
from utils.diagnosis_categories import build_code_to_category

DATASETS = [
    ("Treatment Detail", load_treatment_detail),
    ("Clinic Visits",    load_clinic_visits),
    ("Simulations",      load_simulations),
    ("Courses",          load_courses),
    ("Workflow",         load_workflow),
]

def search(codes):
    # Build regex: exact or prefix
    pattern = "|".join(c.replace(".", r"\.") for c in codes)

    # Show lookup info first
    diag = load_diagnosis()
    c2c = build_code_to_category(diag) if diag is not None else {}
    if diag is not None:
        lookup_matches = diag[diag["DiagnosisCode"].astype(str).str.match(f"^({pattern})", na=False)]
        if len(lookup_matches):
            print(f"\n{'='*90}")
            print(f"  LOOKUP — {len(lookup_matches)} matching codes")
            print(f"{'='*90}")
            for _, r in lookup_matches.sort_values("DiagnosisCode").iterrows():
                code = str(r["DiagnosisCode"])
                cat = c2c.get(code, "Uncategorized")
                print(f"  {code:14s} {int(r['PatientCount']):5d} pts  {cat:28s} {r['DiagnosisDescription']}")

    # Search each dataset
    total_patients = set()
    for label, loader in DATASETS:
        try:
            df = loader()
        except Exception as e:
            print(f"\n{label}: error loading — {e}")
            continue
        if df is None or "DiagnosisCodes" not in df.columns:
            continue

        matches = df[df["DiagnosisCodes"].astype(str).str.contains(pattern, na=False, regex=True)]
        if len(matches) == 0:
            continue

        print(f"\n{'='*90}")
        print(f"  {label} — {len(matches)} rows")
        print(f"{'='*90}")

        has_name = "PatientFullName" in matches.columns
        has_dept = "Department" in matches.columns
        has_date = "ScheduledDateTime" in matches.columns
        has_course_date = "CourseStartDate" in matches.columns

        for pid in matches["PatientId"].unique():
            sub = matches[matches["PatientId"] == pid]
            raw_name = sub["PatientFullName"].iloc[0] if has_name else None
            name = str(raw_name) if pd.notna(raw_name) else str(pid)
            raw_dept = sub["Department"].iloc[0] if has_dept else None
            dept = str(raw_dept) if pd.notna(raw_dept) else "?"
            all_codes = sub["DiagnosisCodes"].iloc[0]
            total_patients.add(pid)

            if has_date:
                dates = sub["ScheduledDateTime"].sort_values()
                date_range = f"{dates.min().date()}–{dates.max().date()}"
            elif has_course_date:
                dates = sub["CourseStartDate"].sort_values()
                date_range = f"{dates.min().date()}–{dates.max().date()}"
            else:
                date_range = "?"

            print(f"  {name:28s} {dept:12s} {date_range:25s} {len(sub):4d} rows  Codes: {all_codes}")

    print(f"\n  Total unique patients: {len(total_patients)}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    search(sys.argv[1:])
