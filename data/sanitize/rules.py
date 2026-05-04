"""Per-dataset PHI sanitization rules.

Each function reads raw CSV/Excel files from raw_root, applies column-level
redaction, and writes the sanitized equivalent to out_root — mirroring the
directory structure so the existing data/loader.py reads the output unchanged.

Return value: a dict summarizing what was done (for the audit log).
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pandas as pd

from data.sanitize.core import (
    add_short_code,
    bucket_age_over_89,
    derive_age_from_dob,
    drop_columns,
    hash_column,
    short_patient_code,
    truncate_zip3,
)
from data.availability_enrichment import enrich as _enrich_availability
from data.clinic_visits_enrichment import enrich as _enrich_clinic_visits


# ---------------------------------------------------------------------------
# Dataset rule table
#
# Each entry describes one dataset. Most follow the same pattern — read CSVs
# matching a glob, drop some columns, hash a patient identifier — so they're
# expressed declaratively here. Datasets that need special handling
# (Lookup - Patients, Referrals, straight copies) have dedicated functions
# below.
# ---------------------------------------------------------------------------

# These are what we drop and hash. Patient names, MRNs/IDs, DOBs,
# free-text notes. Physician names are KEPT per the design decision
# (physicians aren't patients; 4 oncologists are public record).
SIMPLE_RULES: list[dict] = [
    # ---- Incremental CSV sets ----
    {
        "name": "Treatment",
        "subdir": "Incremental/Treatment",
        "pattern": "Treatment_*.csv",
        "drop": [],
        "hash": [],
        "incremental": True,
        "note": "Aggregated daily counts — no PHI columns.",
    },
    {
        "name": "TreatmentDetail",
        "subdir": "Incremental/TreatmentDetail",
        "pattern": "Treatment - Detail_*.csv",
        "drop": ["PatientName"],
        "hash": ["PatientMRN"],
        "incremental": True,
    },
    {
        "name": "Availability",
        "subdir": "Complete",
        "pattern": "Availability.csv",
        "enrich": _enrich_availability,  # AppointmentNotes → HasNote (boolean)
        "drop": ["AppointmentNotes"],
        "hash": [],
        "incremental": False,
    },
    {
        "name": "ClinicVisits",
        "subdir": "Incremental/ClinicVisits",
        "pattern": "Clinic Visits_*.csv",
        "enrich": _enrich_clinic_visits,  # AppointmentNotes → VisitType (categorical)
        "drop": ["PatientFullName", "PatientName", "AppointmentNotes"],
        "hash": ["PatientId"],
        "incremental": True,
    },
    {
        "name": "Simulations",
        "subdir": "Incremental/Simulations",
        "pattern": "Simulations_*.csv",
        "drop": ["PatientFullName", "PatientName", "ActivityNote"],
        "hash": ["PatientId"],
        "incremental": True,
    },
    {
        "name": "Workflow",
        "subdir": "Incremental/Workflow",
        "pattern": "Workflow_*.csv",
        "drop": ["PatientName", "PatientFullName", "ExamNotes"],
        "hash": ["PatientId"],
        "incremental": True,
    },
    {
        "name": "WeeklyVisits",
        "subdir": "Incremental/WeeklyVisits",
        "pattern": "Weekly Visits_*.csv",
        "drop": ["PatientFullName", "PatientName"],
        "hash": ["PatientId"],
        "incremental": True,
    },
    {
        "name": "Courses",
        "subdir": "Incremental/Courses",
        "pattern": "Courses_*.csv",
        "drop": ["PatientName", "PatientFullName"],
        "hash": ["PatientId"],
        "incremental": True,
    },
    {
        "name": "Plans",
        "subdir": "Incremental/Plans",
        "pattern": "Plans_*.csv",
        "drop": ["PatientName", "PatientFullName"],
        "hash": ["PatientId"],
        "incremental": True,
    },
    {
        "name": "Billing",
        "subdir": "Incremental/Billing",
        "pattern": "Billing_*.csv",
        "drop": ["PatientFullName", "PatientName"],
        "hash": ["PatientId"],
        "incremental": True,
    },
    {
        "name": "Procedures",
        "subdir": "Incremental/Procedures",
        "pattern": "Procedures_*.csv",
        "drop": ["PatientFullName", "PatientName", "AppointmentNotes"],
        "hash": ["PatientId"],
        "incremental": True,
    },
    # Machine Downtime - Gaps: no patient columns per loader usecols, but
    # source files may have PatientOutcome free-text — strip to be safe.
    {
        "name": "MachineDowntimeGaps",
        "subdir": "Incremental/MachineDowntimeGaps",
        "pattern": "Machine Downtime - Gaps_*.csv",
        "drop": [],
        "hash": [],
        "incremental": True,
    },
    # Machine Downtime - Fields: has PatientId and PatientName per usecols.
    {
        "name": "MachineDowntimeFields",
        "subdir": "Incremental/MachineDowntimeFields",
        "pattern": "Machine Downtime - Fields_*.csv",
        "drop": ["PatientName"],
        "hash": ["PatientId"],
        "incremental": True,
    },
    # Machine Downtime - Imaging: similar structure
    {
        "name": "MachineDowntimeImaging",
        "subdir": "Incremental/MachineDowntimeImaging",
        "pattern": "Machine Downtime - Imaging_*.csv",
        "drop": ["PatientName"],
        "hash": ["PatientId"],
        "incremental": True,
    },

    # ---- Single-file datasets (Complete/) ----
    {
        "name": "Tasks",
        "subdir": "Complete",
        "pattern": "Tasks.csv",
        "drop": ["PatientName", "PatientFullName"],
        "hash": ["PatientId"],
        "incremental": False,
    },
    {
        "name": "OTVAudit",
        "subdir": "Complete",
        "pattern": "OTV Audit.csv",
        "drop": ["PatientName", "PatientFullName"],
        "hash": ["PatientId"],
        "add_short_code_from": "PatientId",  # preserves pre-hash MRN for reverse lookup
        "incremental": False,
    },
    {
        "name": "MachineErrors",
        "subdir": "Complete",
        "pattern": "Machine Errors.csv",
        "drop": ["PatientName", "PatientFullName"],
        "hash": ["PatientId"],
        "incremental": False,
    },
    {
        "name": "CPTDeliveryAudit",
        "subdir": "Complete",
        "pattern": "2026 CPT Delivery Audit.csv",
        "drop": ["PatientName", "PatientFullName"],
        "hash": ["PatientMRN"],
        "add_short_code_from": "PatientMRN",
        "incremental": False,
    },
    {
        "name": "PhysicianSchedule",
        "subdir": "Complete",
        "pattern": "Physician Schedule.csv",
        "drop": [],
        "hash": [],
        "incremental": False,
        "note": "Physician names are retained per design decision.",
    },
    # Daily Volume files are aggregate-only, no PHI. Copy through.
    {
        "name": "DailyVolumePast",
        "subdir": "Complete",
        "pattern": "Daily Volume - Past.csv",
        "drop": [],
        "hash": [],
        "incremental": False,
    },
    {
        "name": "DailyVolumeFuture",
        "subdir": "Complete",
        "pattern": "Daily Volume - Future.csv",
        "drop": [],
        "hash": [],
        "incremental": False,
    },
    {
        "name": "MachineStatistics",
        "subdir": "Complete",
        "pattern": "Machine Statistics.csv",
        "drop": [],
        "hash": [],
        "incremental": False,
    },

    # ---- Lookup tables ----
    # Lookup - Patients gets its own function below (address/DOB/ZIP handling)
    {
        "name": "LookupReferring",
        "subdir": "Lookup",
        "pattern": "Lookup - Referring.csv",
        "drop": [],
        "hash": [],
        "incremental": False,
        "note": "Referring physicians are public NPPES data — retained in full.",
    },
    {
        "name": "LookupDiagnosis",
        "subdir": "Lookup",
        "pattern": "Lookup - Diagnosis.csv",
        "drop": [],
        "hash": [],
        "incremental": False,
    },
]


# ---------------------------------------------------------------------------
# Generic rule executor
# ---------------------------------------------------------------------------

def _read_csv(path: Path) -> pd.DataFrame:
    """Read a CSV using the same tolerant approach as the app loader."""
    try:
        return pd.read_csv(path, encoding="utf-8-sig", engine="pyarrow")
    except Exception:
        return pd.read_csv(
            path, encoding="utf-8-sig",
            on_bad_lines="skip", low_memory=False,
        )


def _write_csv(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, encoding="utf-8-sig")


def apply_simple_rule(rule: dict, raw_root: Path, out_root: Path, salt: str) -> dict:
    """Apply a declarative rule to every file matching its pattern.

    Returns an audit entry.
    """
    src_dir = raw_root / rule["subdir"]
    out_dir = out_root / rule["subdir"]
    pattern = rule["pattern"]

    files_processed = 0
    rows_in = 0
    rows_out = 0
    dropped_any: list[str] = []

    if not src_dir.exists():
        return {
            "name": rule["name"],
            "files": 0,
            "rows_in": 0,
            "rows_out": 0,
            "dropped": [],
            "hashed": [],
            "note": rule.get("note", ""),
            "status": "skipped (source dir missing)",
        }

    enrich_fn = rule.get("enrich")
    enriched_cols: list[str] = []

    for src_path in sorted(src_dir.glob(pattern)):
        df = _read_csv(src_path)
        rows_in += len(df)

        # Enrich BEFORE dropping — lets the hook derive a non-PHI signal
        # (categorical / boolean / aggregate) from columns that won't
        # survive sanitization.
        if enrich_fn is not None:
            cols_before = set(df.columns)
            df = enrich_fn(df, salt)
            new_cols = [c for c in df.columns if c not in cols_before]
            for c in new_cols:
                if c not in enriched_cols:
                    enriched_cols.append(c)

        dropped = drop_columns(df, rule.get("drop", []))
        for d in dropped:
            if d not in dropped_any:
                dropped_any.append(d)

        # Short code must be derived BEFORE the source column is hashed,
        # since the code is computed from the raw MRN.
        if rule.get("add_short_code_from"):
            add_short_code(df, rule["add_short_code_from"], salt)

        for col in rule.get("hash", []):
            hash_column(df, col, salt)

        rows_out += len(df)
        out_path = out_dir / src_path.name
        _write_csv(df, out_path)
        files_processed += 1

    return {
        "name": rule["name"],
        "files": files_processed,
        "rows_in": rows_in,
        "rows_out": rows_out,
        "dropped": dropped_any,
        "hashed": list(rule.get("hash", [])),
        "enriched": enriched_cols,
        "short_code_from": rule.get("add_short_code_from"),
        "note": rule.get("note", ""),
        "status": "ok" if files_processed > 0 else "no files matched",
    }


# ---------------------------------------------------------------------------
# Special-case dataset functions
# ---------------------------------------------------------------------------

def sanitize_lookup_patients(raw_root: Path, out_root: Path, salt: str) -> dict:
    """Lookup - Patients has the richest PHI: names, DOB, full address.

    Drop: PatientName, PatientAddressLine1, PatientAddressLine2, DateOfBirth,
          OtherInsurers (insurance list can re-identify)
    Hash: PatientId
    Transform: Zip → ZIP3, DOB → AgeAtLoad (capped at 90+)
    Keep: City, County, PrimaryInsurance (coarse), appointment range dates
    """
    src = raw_root / "Lookup" / "Lookup - Patients.csv"
    out = out_root / "Lookup" / "Lookup - Patients.csv"

    if not src.exists():
        return {"name": "LookupPatients", "status": "skipped (source missing)"}

    df = _read_csv(src)
    rows_in = len(df)

    # Derive age BEFORE dropping DOB
    if "DateOfBirth" in df.columns:
        # Use LastAppointment as reference if available, else today
        ref = None
        if "LastAppointment" in df.columns:
            dt = pd.to_datetime(df["LastAppointment"], errors="coerce")
            if dt.notna().any():
                ref = dt.max()
        df["AgeAtLoad"] = derive_age_from_dob(df["DateOfBirth"], ref)

    dropped = drop_columns(df, [
        "PatientName",
        "PatientAddressLine1",
        "PatientAddressLine2",
        "DateOfBirth",
        "OtherInsurers",
    ])

    # ZIP3 masking
    if "Zip" in df.columns:
        df["Zip"] = df["Zip"].map(truncate_zip3)

    hash_column(df, "PatientId", salt)

    _write_csv(df, out)

    return {
        "name": "LookupPatients",
        "files": 1,
        "rows_in": rows_in,
        "rows_out": len(df),
        "dropped": dropped,
        "hashed": ["PatientId"],
        "transforms": [
            "Zip → ZIP3 (Safe Harbor restricted prefixes → '000')",
            "DateOfBirth → AgeAtLoad (capped at 90+)",
        ],
        "status": "ok",
    }


def sanitize_referrals(raw_root: Path, out_root: Path, salt: str) -> dict:
    """Referrals is an xlsx file. Contains MRN, Patient Name, DOB.

    Drop: Patient Name, DOB
    Hash: MRN
    Transform: DOB → AgeAtReferral (before dropping)
    Keep: Referred by Provider, institution, specialty, all referral-lifecycle dates

    Matches only the rad-onc report (filename starts with
    `Referrals_Report_RadiantCare_All_`). The med-onc PRCS report
    (`Referrals_Report_PRCS_*.xlsx`) is handled separately by
    `sanitize_medonc_referrals` — we disambiguate on the filename because
    both arrive in the same OneDrive folder and share the same column
    shape but represent different referral directions (TO rad-onc vs TO
    med-onc).
    """
    import glob as _glob

    pattern = str(raw_root / "Referrals_Report_RadiantCare_All_*.xlsx")
    matches = sorted(_glob.glob(pattern))
    if not matches:
        return {"name": "Referrals", "status": "skipped (no xlsx matched)"}

    files_processed = 0
    rows_in = 0
    rows_out = 0
    dropped_any: list[str] = []

    for src in matches:
        src_path = Path(src)
        df = pd.read_excel(src_path)
        rows_in += len(df)

        if "DOB" in df.columns and "Created" in df.columns:
            ref_dates = pd.to_datetime(df["Created"], errors="coerce")
            ref = ref_dates.max() if ref_dates.notna().any() else None
            df["AgeAtReferral"] = derive_age_from_dob(df["DOB"], ref)

        dropped = drop_columns(df, ["Patient Name", "DOB"])
        for d in dropped:
            if d not in dropped_any:
                dropped_any.append(d)

        hash_column(df, "MRN", salt)

        rows_out += len(df)
        out_path = out_root / src_path.name
        out_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_excel(out_path, index=False)
        files_processed += 1

    return {
        "name": "Referrals",
        "files": files_processed,
        "rows_in": rows_in,
        "rows_out": rows_out,
        "dropped": dropped_any,
        "hashed": ["MRN"],
        "transforms": ["DOB → AgeAtReferral (capped at 90+)"],
        "status": "ok",
    }


def sanitize_medonc_referrals(raw_root: Path, out_root: Path, salt: str) -> dict:
    """Med-Onc PRCS Referrals report — parallel structure to the rad-onc
    referrals file. Distinguished from the rad-onc file purely by filename
    prefix (`Referrals_Report_PRCS_*.xlsx` vs `_RadiantCare_All_*.xlsx`).

    Drop: Patient Name, DOB
    Hash: MRN
    Transform: DOB → AgeAtReferral (before dropping), using the referral's
               Created date as the reference point
    Keep: provider/department/specialty fields, diagnoses, all
          referral-lifecycle dates, referring-provider address fields
          (provider info, not patient PHI)
    """
    import glob as _glob

    pattern = str(raw_root / "Referrals_Report_PRCS_*.xlsx")
    matches = sorted(_glob.glob(pattern))
    if not matches:
        return {"name": "MedOncReferrals", "status": "skipped (no xlsx matched)"}

    files_processed = 0
    rows_in = 0
    rows_out = 0
    dropped_any: list[str] = []

    for src in matches:
        src_path = Path(src)
        df = pd.read_excel(src_path)
        rows_in += len(df)

        if "DOB" in df.columns and "Created" in df.columns:
            ref_dates = pd.to_datetime(df["Created"], errors="coerce")
            ref = ref_dates.max() if ref_dates.notna().any() else None
            df["AgeAtReferral"] = derive_age_from_dob(df["DOB"], ref)

        dropped = drop_columns(df, ["Patient Name", "DOB"])
        for d in dropped:
            if d not in dropped_any:
                dropped_any.append(d)

        hash_column(df, "MRN", salt)

        rows_out += len(df)
        out_path = out_root / src_path.name
        out_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_excel(out_path, index=False)
        files_processed += 1

    return {
        "name": "MedOncReferrals",
        "files": files_processed,
        "rows_in": rows_in,
        "rows_out": rows_out,
        "dropped": dropped_any,
        "hashed": ["MRN"],
        "transforms": ["DOB → AgeAtReferral (capped at 90+)"],
        "status": "ok",
    }


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def sanitize_all(raw_root: Path, out_root: Path, salt: str) -> list[dict]:
    """Run every rule and return the list of audit entries."""
    audit: list[dict] = []

    for rule in SIMPLE_RULES:
        audit.append(apply_simple_rule(rule, raw_root, out_root, salt))

    audit.append(sanitize_lookup_patients(raw_root, out_root, salt))
    audit.append(sanitize_referrals(raw_root, out_root, salt))
    audit.append(sanitize_medonc_referrals(raw_root, out_root, salt))

    return audit
