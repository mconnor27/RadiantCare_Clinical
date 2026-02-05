"""Data loading and preprocessing for RadiantCare Clinical Dashboard."""

import pandas as pd
from functools import lru_cache
from pathlib import Path

from config.settings import DATA_COMPLETE, DATA_INCREMENTAL, DATA_LOOKUP


def _read_csv_safe(path, **kwargs):
    """Read a CSV, handling ARIA footer rows.

    ARIA reports append metadata footer rows after a blank line separator.
    We need CSV-aware blank line detection because quoted fields can contain
    embedded newlines.  Strategy: read with pandas first, then drop any
    trailing all-NaN rows (footer artifacts).
    """
    if not path.exists():
        return pd.DataFrame()

    kwargs.setdefault("encoding", "utf-8-sig")
    kwargs.setdefault("on_bad_lines", "skip")
    kwargs.setdefault("low_memory", False)
    df = pd.read_csv(path, **kwargs)

    # Drop trailing rows where every value is NaN (ARIA footer artifacts)
    while len(df) > 0 and df.iloc[-1].isna().all():
        df = df.iloc[:-1]
    return df


def _normalize_columns(df, renames):
    """Rename columns to match expected names across the app."""
    mapping = {old: new for old, new in renames.items() if old in df.columns and new not in df.columns}
    return df.rename(columns=mapping)


def _clean_department(df):
    """Strip leading * from department names."""
    if "Department" in df.columns:
        df["Department"] = df["Department"].str.replace("*", "", regex=False).str.strip()
    return df


def _filter_test_patients(df):
    """Exclude test/dummy patients."""
    id_col = next((c for c in ["PatientId", "PatientMRN"] if c in df.columns), None)
    name_col = next((c for c in ["PatientFullName", "PatientName"] if c in df.columns), None)

    if id_col is None and name_col is None:
        return df

    mask = pd.Series(False, index=df.index)
    if id_col:
        mask |= df[id_col].astype(str).str.contains(
            "astro|test", case=False, na=False
        )
    if name_col:
        mask |= df[name_col].str.lower().str.startswith("zzz", na=False)
        mask |= df[name_col].str.startswith("Test,", na=False)
    return df[~mask].copy()


def _parse_dates(df, cols):
    """Parse date columns, coercing errors."""
    for col in cols:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")
    return df


# ---------------------------------------------------------------------------
# Public loaders — one per data source
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def load_treatment():
    """Load Treatment.csv — daily aggregated data per location.

    Columns: Location→Department, Date→ScheduledDate, CompletedAppointments,
    UniquePatients, UniquePlans, NewStarts_*, Fields_*, Patients_*, Plans_*
    """
    df = _read_csv_safe(DATA_INCREMENTAL / "Treatment" / "Treatment.csv")
    df = _normalize_columns(df, {"Location": "Department", "Date": "ScheduledDate"})
    df = _clean_department(df)
    df = _parse_dates(df, ["ScheduledDate"])
    return df


@lru_cache(maxsize=1)
def load_treatment_detail():
    """Load Treatment - Detail.csv — per-session treatment records.

    Columns: TreatmentDate→ScheduledDateTime, PatientMRN→PatientId,
    PatientName→PatientFullName, Machine, Department, TreatingPhysician, etc.
    """
    df = _read_csv_safe(DATA_INCREMENTAL / "TreatmentDetail" / "Treatment - Detail.csv")
    df = _normalize_columns(df, {
        "TreatmentDate": "ScheduledDateTime",
        "PatientMRN": "PatientId",
        "PatientName": "PatientFullName",
    })
    df = _clean_department(df)
    df = _filter_test_patients(df)
    df = _parse_dates(df, ["ScheduledDateTime", "AppointmentDateTime",
                           "TreatmentStartTime", "TreatmentEndTime"])
    return df


@lru_cache(maxsize=1)
def load_daily_volume():
    """Load Daily Volume - Past.csv.

    Columns: Location→Department, Date→ScheduledDate,
    FirstScheduledStart, LastScheduledEnd, AppointmentCount,
    FirstActualStart, LastActualEnd
    """
    df = _read_csv_safe(DATA_COMPLETE / "Daily Volume - Past.csv")
    df = _normalize_columns(df, {"Location": "Department", "Date": "ScheduledDate"})
    df = _clean_department(df)
    df = _parse_dates(df, ["ScheduledDate"])
    return df


@lru_cache(maxsize=1)
def load_daily_volume_future():
    """Load Daily Volume - Future.csv.

    Same structure as Daily Volume - Past.
    """
    df = _read_csv_safe(DATA_COMPLETE / "Daily Volume - Future.csv")
    df = _normalize_columns(df, {"Location": "Department", "Date": "ScheduledDate"})
    df = _clean_department(df)
    df = _parse_dates(df, ["ScheduledDate"])
    return df


@lru_cache(maxsize=1)
def load_availability():
    """Load Availability.csv.

    Columns: DepartmentName→Department, AppointmentDateTime→SlotDate,
    Category, ScheduledEndTime, DurationMinutes, ActivityName, etc.
    """
    df = _read_csv_safe(DATA_INCREMENTAL / "Availability" / "Availability.csv")
    df = _normalize_columns(df, {"DepartmentName": "Department"})
    df = _clean_department(df)
    df = _parse_dates(df, ["AppointmentDateTime", "ScheduledEndTime"])
    # Add SlotDate as the date-only portion for filtering
    if "AppointmentDateTime" in df.columns:
        df["SlotDate"] = df["AppointmentDateTime"].dt.normalize()
    return df


@lru_cache(maxsize=1)
def load_clinic_visits():
    """Load Clinic Visits.csv.

    Columns: DepartmentName→Department, ActivityStatus→Status
    """
    df = _read_csv_safe(DATA_INCREMENTAL / "ClinicVisits" / "Clinic Visits.csv")
    df = _normalize_columns(df, {
        "DepartmentName": "Department",
        "ActivityStatus": "Status",
    })
    df = _clean_department(df)
    df = _filter_test_patients(df)
    df = _parse_dates(df, ["ScheduledDateTime", "AppointmentCreatedDate"])
    return df


@lru_cache(maxsize=1)
def load_simulations():
    """Load Simulations.csv.

    No Department column in source data.
    Has ActivityStatus (not Status) for filtering.
    """
    df = _read_csv_safe(DATA_INCREMENTAL / "Simulations" / "Simulations.csv")
    df = _normalize_columns(df, {"ActivityStatus": "Status"})
    df = _clean_department(df)
    df = _filter_test_patients(df)
    df = _parse_dates(df, ["ScheduledDateTime", "AppointmentCreatedDate",
                           "PriorClinicExamAppointmentDate", "FirstTreatmentDate"])
    return df


@lru_cache(maxsize=1)
def load_workflow():
    """Load Workflow.csv.

    Columns: SimulationDateTime→SimulationDate,
    DrawCompletedDateTime→DrawVolumesCompletedDate,
    IsodosePlanCompletedDateTime→IsodosePlanCompletedDate,
    ReviewPlanCompletedDateTime→ReviewPlanCompletedDate
    No Department column in source data.
    """
    df = _read_csv_safe(DATA_INCREMENTAL / "Workflow" / "Workflow.csv")
    df = _normalize_columns(df, {
        "SimulationDateTime": "SimulationDate",
        "DrawCompletedDateTime": "DrawVolumesCompletedDate",
        "IsodosePlanCompletedDateTime": "IsodosePlanCompletedDate",
        "ReviewPlanCompletedDateTime": "ReviewPlanCompletedDate",
    })
    df = _clean_department(df)
    df = _filter_test_patients(df)
    df = _parse_dates(df, [
        "ScheduledDateTime", "SimulationDate",
        "DrawVolumesCompletedDate", "IsodosePlanCompletedDate",
        "ReviewPlanCompletedDate", "FirstTreatmentDate",
    ])
    if "UniqueRowID" in df.columns:
        df = df.drop_duplicates(subset=["UniqueRowID"], keep="last")
    return df


@lru_cache(maxsize=1)
def load_tasks():
    """Load Tasks.csv.

    Columns: PatientName→PatientFullName
    """
    df = _read_csv_safe(DATA_COMPLETE / "Tasks.csv")
    df = _normalize_columns(df, {"PatientName": "PatientFullName"})
    df = _filter_test_patients(df)
    df = _parse_dates(df, ["StartDateTime", "DueDateTime", "CompletedDateTime"])
    if "UniqueRowID" in df.columns:
        df = df.drop_duplicates(subset=["UniqueRowID"], keep="last")
    return df


@lru_cache(maxsize=1)
def load_otvs():
    """Load OTV Audit.csv."""
    df = _read_csv_safe(DATA_COMPLETE / "OTV Audit.csv")
    df = _clean_department(df)
    df = _filter_test_patients(df)
    df = _parse_dates(df, ["OTVDate"])
    if "UniqueRowID" in df.columns:
        df = df.drop_duplicates(subset=["UniqueRowID"], keep="last")
    return df


@lru_cache(maxsize=1)
def load_weekly_visits():
    """Load Weekly Visits.csv."""
    df = _read_csv_safe(DATA_INCREMENTAL / "WeeklyVisits" / "Weekly Visits.csv")
    df = _clean_department(df)
    df = _filter_test_patients(df)
    df = _parse_dates(df, ["VisitDate"])
    if "UniqueRowID" in df.columns:
        df = df.drop_duplicates(subset=["UniqueRowID"], keep="last")
    return df


@lru_cache(maxsize=1)
def load_courses():
    """Load Courses.csv.

    Columns: CourseStartDateTime→CourseStartDate, Departments→Department
    (takes first department if comma-separated), PatientName→PatientFullName
    """
    df = _read_csv_safe(DATA_INCREMENTAL / "Courses" / "Courses.csv")
    df = _normalize_columns(df, {
        "CourseStartDateTime": "CourseStartDate",
        "PatientName": "PatientFullName",
    })
    # Departments is sometimes comma-separated; take the first one
    if "Departments" in df.columns and "Department" not in df.columns:
        df["Department"] = df["Departments"].str.split(",").str[0].str.strip()
    df = _clean_department(df)
    df = _filter_test_patients(df)
    df = _parse_dates(df, ["CourseStartDate", "FirstTreatmentDate", "LastTreatmentDate"])
    return df


@lru_cache(maxsize=1)
def load_plans():
    """Load Plans.csv.

    Columns: Departments→Department (comma-separated, take first),
    PatientName→PatientFullName
    """
    df = _read_csv_safe(DATA_INCREMENTAL / "Plans" / "Plans.csv")
    df = _normalize_columns(df, {"PatientName": "PatientFullName"})
    # Departments is sometimes comma-separated; take the first one
    if "Departments" in df.columns and "Department" not in df.columns:
        df["Department"] = df["Departments"].str.split(",").str[0].str.strip()
    df = _clean_department(df)
    df = _filter_test_patients(df)
    df = _parse_dates(df, ["PlanCreationDate", "CourseStartDateTime",
                           "FirstTreatmentDate", "LastTreatmentDate"])
    return df


@lru_cache(maxsize=1)
def load_machines():
    """Load Machine Errors.csv.

    No Date column — uses TreatmentStartTime/TreatmentEndTime.
    """
    df = _read_csv_safe(DATA_COMPLETE / "Machine Errors.csv")
    df = _normalize_columns(df, {"PatientName": "PatientFullName"})
    df = _parse_dates(df, ["TreatmentStartTime", "TreatmentEndTime"])
    return df


@lru_cache(maxsize=1)
def load_billing():
    """Load Billing.csv.

    Columns: DepartmentName→Department
    """
    df = _read_csv_safe(DATA_INCREMENTAL / "Billing" / "Billing.csv")
    df = _normalize_columns(df, {"DepartmentName": "Department"})
    df = _clean_department(df)
    df = _filter_test_patients(df)
    df = _parse_dates(df, ["DateOfService"])
    return df


@lru_cache(maxsize=1)
def load_patients():
    """Load Lookup - Patients.csv."""
    df = _read_csv_safe(DATA_LOOKUP / "Lookup - Patients.csv")
    df = _filter_test_patients(df)
    return df


@lru_cache(maxsize=1)
def load_referring():
    """Load Lookup - Referring.csv."""
    return _read_csv_safe(DATA_LOOKUP / "Lookup - Referring.csv")


@lru_cache(maxsize=1)
def load_diagnosis():
    """Load Lookup - Diagnosis.csv."""
    return _read_csv_safe(DATA_LOOKUP / "Lookup - Diagnosis.csv")


@lru_cache(maxsize=1)
def load_physician_schedule():
    """Load Physician Schedule.csv."""
    df = _read_csv_safe(DATA_COMPLETE / "Physician Schedule.csv")
    df = _parse_dates(df, ["ScheduleDate"])
    return df


def clear_cache():
    """Clear all cached data (call after data refresh)."""
    for fn in [
        load_treatment, load_treatment_detail, load_daily_volume,
        load_daily_volume_future, load_availability, load_clinic_visits,
        load_simulations, load_workflow, load_tasks, load_otvs,
        load_weekly_visits, load_courses, load_plans, load_machines,
        load_billing, load_patients, load_referring, load_diagnosis,
        load_physician_schedule,
    ]:
        fn.cache_clear()
