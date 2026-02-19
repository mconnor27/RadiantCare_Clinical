"""Data loading and preprocessing for RadiantCare Clinical Dashboard."""

import pandas as pd
from functools import lru_cache
from pathlib import Path

from config.settings import DATA_COMPLETE, DATA_INCREMENTAL, DATA_LOOKUP


def _read_csv_safe(path, **kwargs):
    """Read a CSV, trying pyarrow first for speed (~3x faster).

    Falls back to the default C engine for files with embedded newlines
    or other quirks that pyarrow's stricter parser rejects.

    ARIA reports append metadata footer rows after a blank line separator;
    trailing all-NaN rows are dropped automatically.
    """
    if not path.exists():
        return pd.DataFrame()

    encoding = kwargs.pop("encoding", "utf-8-sig")

    # Fast path: pyarrow engine
    try:
        df = pd.read_csv(path, encoding=encoding, engine="pyarrow")
    except Exception:
        # Fallback for CSVs with embedded newlines, bad rows, etc.
        df = pd.read_csv(
            path, encoding=encoding,
            on_bad_lines="skip", low_memory=False, **kwargs,
        )

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


def _reshape_daily_volume(df):
    """Reshape new Daily Volume CSV format to match the old Location-based layout.

    Old format: one row per Location (department name OR machine name) per date.
    New format: rows broken out by Category (Treatment/Simulation/Total) and
    Resource (machine name or None for aggregate).

    We keep Treatment rows only and recreate machine-name Department entries
    so that downstream machine-level filtering (Lacey → TrueBeamNorth / 21EX)
    continues to work.
    """
    if "Category" not in df.columns or "Resource" not in df.columns:
        return df

    df = df[df["Category"] == "Treatment"].copy()

    # Rows with Resource=None are department aggregates
    agg_rows = df[df["Resource"].isna()]
    # Rows with a specific Resource are machine-level
    machine_rows = df[df["Resource"].notna()]

    # Create machine-as-department rows (Resource value becomes Department)
    machine_as_dept = machine_rows.copy()
    machine_as_dept["Department"] = machine_as_dept["Resource"]

    # Departments that lack an aggregate row need one synthesised from machines
    depts_with_agg = set(agg_rows["Department"].unique()) if not agg_rows.empty else set()
    missing = set(df["Department"].unique()) - depts_with_agg

    # Time columns that need min/max aggregation (not sum)
    _start_cols = ["FirstScheduledStart", "FirstActualStart"]
    _end_cols = ["LastScheduledEnd", "LastActualEnd"]

    new_aggs = []
    for dept in missing:
        rows = machine_rows[machine_rows["Department"] == dept]
        if rows.empty:
            continue
        num_cols = rows.select_dtypes(include="number").columns.tolist()
        grouped = rows.groupby("ScheduledDate", as_index=False)[num_cols].sum()
        # Aggregate time strings: earliest start, latest end per day
        for col in _start_cols:
            if col in rows.columns:
                grouped[col] = rows.groupby("ScheduledDate")[col].min().values
        for col in _end_cols:
            if col in rows.columns:
                grouped[col] = rows.groupby("ScheduledDate")[col].max().values
        grouped["Department"] = dept
        new_aggs.append(grouped)

    parts = [p for p in [agg_rows, machine_as_dept] + new_aggs if not p.empty]
    result = pd.concat(parts, ignore_index=True) if parts else df
    result = result.drop(columns=["Category", "Resource"], errors="ignore")
    return result


def _parse_dates(df, cols):
    """Parse date columns, coercing errors.

    Auto-detects the ARIA date format from the first non-null value so
    pandas can use its fast C parser instead of falling back to the
    per-row dateutil path (which is ~17x slower on large datasets).
    """
    _FMT_DATE = "%m/%d/%Y"
    _FMT_DATETIME = "%m/%d/%Y %I:%M:%S %p"

    for col in cols:
        if col not in df.columns:
            continue
        non_null = df[col].dropna()
        if non_null.empty:
            continue
        sample = non_null.iloc[0]
        if isinstance(sample, str):
            fmt = _FMT_DATETIME if " " in sample.strip() else _FMT_DATE
            df[col] = pd.to_datetime(df[col], format=fmt, errors="coerce")
        else:
            # Already parsed or non-string — let pandas handle it
            df[col] = pd.to_datetime(df[col], errors="coerce")
    return df


def _load_incremental(folder, base_name, dedup_key):
    """Load and merge all incremental CSV files from a folder.

    Reads base_name.csv, base_name_1.csv, base_name_2.csv, etc.,
    concatenates them in numeric order, and deduplicates by *dedup_key*.
    The row from the highest-numbered file wins, **except** referring-
    physician columns are preserved: if an earlier file has a non-null
    referring value and a later file has null, the earlier value is kept.

    Parameters
    ----------
    folder : Path
        Directory containing the incremental CSV files.
    base_name : str
        Base filename without extension (e.g., "Treatment", "Clinic Visits").
    dedup_key : str or list[str]
        Column name(s) to deduplicate on.
    """
    folder = Path(folder)
    key_cols = [dedup_key] if isinstance(dedup_key, str) else list(dedup_key)

    # Gather base file + numbered increments
    files = []
    base_path = folder / f"{base_name}.csv"
    if base_path.exists():
        files.append((0, base_path))
    for f in folder.glob(f"{base_name}_*.csv"):
        suffix = f.stem[len(base_name) + 1:]
        try:
            files.append((int(suffix), f))
        except ValueError:
            continue

    if not files:
        return pd.DataFrame()

    files.sort(key=lambda x: x[0])

    # Read each file, tagging with source order
    dfs = []
    for order, fpath in files:
        df = _read_csv_safe(fpath)
        if not df.empty:
            df["_file_order"] = order
            dfs.append(df)

    if not dfs:
        return pd.DataFrame()

    combined = pd.concat(dfs, ignore_index=True)

    # If key columns are missing, return as-is (can't deduplicate)
    if not all(c in combined.columns for c in key_cols):
        return combined.drop(columns=["_file_order"], errors="ignore")

    combined = combined.sort_values("_file_order")

    # Preserve referring-physician columns: forward-fill within each key
    # group so a non-null value from an earlier file isn't lost when a
    # later file has null/blank.
    ref_cols = [c for c in combined.columns if c.lower().startswith("referring")]
    if ref_cols:
        for col in ref_cols:
            if combined[col].dtype == object:
                combined[col] = combined[col].replace(
                    r"^\s*$", pd.NA, regex=True
                )
        combined[ref_cols] = combined.groupby(key_cols)[ref_cols].ffill()

    # Keep the newest row per key
    combined = combined.drop_duplicates(subset=key_cols, keep="last")
    combined = combined.drop(columns=["_file_order"])
    return combined


@lru_cache(maxsize=1)
def _patient_department_map():
    """Build PatientId → Department lookup from Treatment Detail.

    Used to add Department to datasets that lack it (Simulations, Workflow).
    """
    td = load_treatment_detail()
    if td.empty or "PatientId" not in td.columns or "Department" not in td.columns:
        return pd.DataFrame(columns=["PatientId", "Department"])
    # Take the most common department per patient
    dept_map = (
        td.groupby("PatientId")["Department"]
        .agg(lambda x: x.value_counts().index[0])
        .reset_index()
    )
    return dept_map


# ---------------------------------------------------------------------------
# Public loaders — one per data source
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def load_treatment():
    """Load Treatment.csv — daily aggregated data per location.

    Columns: Location→Department, Date→ScheduledDate, CompletedAppointments,
    UniquePatients, UniquePlans, NewStarts_*, Fields_*, Patients_*, Plans_*
    """
    df = _load_incremental(DATA_INCREMENTAL / "Treatment", "Treatment", ["Location", "Date"])
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
    df = _load_incremental(DATA_INCREMENTAL / "TreatmentDetail", "Treatment - Detail", "SessionUniqueID")
    df = _normalize_columns(df, {
        "TreatmentDate": "ScheduledDateTime",
        "PatientMRN": "PatientId",
        "PatientName": "PatientFullName",
    })
    df = _clean_department(df)
    df = _parse_dates(df, ["ScheduledDateTime", "AppointmentDateTime",
                           "TreatmentStartTime", "TreatmentEndTime"])
    # Secondary dedup: ARIA incremental exports can regenerate different
    # SessionUniqueIDs for the same treatment session, so fall back to a
    # stable composite key.  Safe to keep after the extraction is fixed
    # (will be a no-op once SessionUniqueIDs are stable).
    _composite = ["PatientId", "ScheduledDateTime", "Machine", "FractionNumber", "CourseName"]
    _usable = [c for c in _composite if c in df.columns]
    if _usable:
        df = df.drop_duplicates(subset=_usable, keep="last")
    return df


@lru_cache(maxsize=1)
def load_daily_volume():
    """Load Daily Volume - Past.csv.

    Columns: Location→Department, Date→ScheduledDate,
    FirstScheduledStart, LastScheduledEnd, AppointmentCount,
    FirstActualStart, LastActualEnd
    """
    df = _read_csv_safe(DATA_COMPLETE / "Daily Volume - Past.csv")
    df = _normalize_columns(df, {"Location": "Department", "Site": "Department", "Date": "ScheduledDate"})
    df = _clean_department(df)
    df = _reshape_daily_volume(df)
    df = _parse_dates(df, ["ScheduledDate"])
    return df


@lru_cache(maxsize=1)
def load_daily_volume_future():
    """Load Daily Volume - Future.csv.

    Same structure as Daily Volume - Past.
    """
    df = _read_csv_safe(DATA_COMPLETE / "Daily Volume - Future.csv")
    df = _normalize_columns(df, {"Location": "Department", "Site": "Department", "Date": "ScheduledDate"})
    df = _clean_department(df)
    df = _reshape_daily_volume(df)
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
    df = _load_incremental(DATA_INCREMENTAL / "ClinicVisits", "Clinic Visits", "UniqueRowID")
    df = _normalize_columns(df, {
        "DepartmentName": "Department",
        "ActivityStatus": "Status",
    })
    df = _clean_department(df)
    df = _parse_dates(df, ["ScheduledDateTime", "AppointmentCreatedDate"])
    return df


@lru_cache(maxsize=1)
def load_simulations():
    """Load Simulations.csv.

    No Department column in source data.
    Has ActivityStatus (not Status) for filtering.
    """
    df = _load_incremental(DATA_INCREMENTAL / "Simulations", "Simulations", "UniqueRowID")
    df = _normalize_columns(df, {"ActivityStatus": "Status"})
    df = _parse_dates(df, ["ScheduledDateTime", "AppointmentCreatedDate",
                           "PriorClinicExamAppointmentDate", "FirstTreatmentDate"])
    # Add Department from Treatment Detail (source CSV has none)
    if "Department" not in df.columns and "PatientId" in df.columns:
        dept_map = _patient_department_map()
        if not dept_map.empty:
            df = df.merge(dept_map, on="PatientId", how="left")
    df = _clean_department(df)
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
    df = _load_incremental(DATA_INCREMENTAL / "Workflow", "Workflow", "UniqueRowID")
    df = _normalize_columns(df, {
        "SimulationDateTime": "SimulationDate",
        "DrawCompletedDateTime": "DrawVolumesCompletedDate",
        "IsodosePlanCompletedDateTime": "IsodosePlanCompletedDate",
        "ReviewPlanCompletedDateTime": "ReviewPlanCompletedDate",
    })
    df = _parse_dates(df, [
        "ScheduledDateTime", "SimulationDate",
        "DrawVolumesCompletedDate", "IsodosePlanCompletedDate",
        "ReviewPlanCompletedDate", "FirstTreatmentDate",
    ])
    # Add Department from Treatment Detail (source CSV has none)
    if "Department" not in df.columns and "PatientId" in df.columns:
        dept_map = _patient_department_map()
        if not dept_map.empty:
            df = df.merge(dept_map, on="PatientId", how="left")
    df = _clean_department(df)
    return df


@lru_cache(maxsize=1)
def load_tasks():
    """Load Tasks.csv.

    Columns: PatientName→PatientFullName
    """
    df = _read_csv_safe(DATA_COMPLETE / "Tasks.csv")
    df = _normalize_columns(df, {"PatientName": "PatientFullName"})
    df = _parse_dates(df, ["StartDateTime", "DueDateTime", "CompletedDateTime"])
    if "UniqueRowID" in df.columns:
        df = df.drop_duplicates(subset=["UniqueRowID"], keep="last")
    return df


@lru_cache(maxsize=1)
def load_otvs():
    """Load OTV Audit.csv."""
    df = _read_csv_safe(DATA_COMPLETE / "OTV Audit.csv")
    df = _clean_department(df)
    df = _parse_dates(df, ["FirstTreatmentDate", "LastTreatmentDate"])
    if "UniqueRowID" in df.columns:
        df = df.drop_duplicates(subset=["UniqueRowID"], keep="last")
    return df


@lru_cache(maxsize=1)
def load_weekly_visits():
    """Load Weekly Visits.csv."""
    df = _load_incremental(DATA_INCREMENTAL / "WeeklyVisits", "Weekly Visits", "UniqueRowID")
    df = _normalize_columns(df, {"DepartmentName": "Department"})
    df = _clean_department(df)
    df = _parse_dates(df, ["AppointmentDateTime"])
    return df


@lru_cache(maxsize=1)
def load_courses():
    """Load Courses.csv.

    Columns: CourseStartDateTime→CourseStartDate, Departments→Department
    (takes first department if comma-separated), PatientName→PatientFullName
    """
    df = _load_incremental(DATA_INCREMENTAL / "Courses", "Courses", "UniqueRowID")
    df = _normalize_columns(df, {
        "CourseStartDateTime": "CourseStartDate",
        "PatientName": "PatientFullName",
    })
    # Departments is sometimes comma-separated; take the first one
    if "Departments" in df.columns and "Department" not in df.columns:
        df["Department"] = df["Departments"].str.split(",").str[0].str.strip()
    df = _clean_department(df)
    df = _parse_dates(df, ["CourseStartDate", "FirstTreatmentDate", "LastTreatmentDate"])
    return df


@lru_cache(maxsize=1)
def load_plans():
    """Load Plans.csv.

    Columns: Departments→Department (comma-separated, take first),
    PatientName→PatientFullName
    """
    df = _load_incremental(DATA_INCREMENTAL / "Plans", "Plans", "UniqueRowID")
    df = _normalize_columns(df, {"PatientName": "PatientFullName"})
    # Departments is sometimes comma-separated; take the first one
    if "Departments" in df.columns and "Department" not in df.columns:
        df["Department"] = df["Departments"].str.split(",").str[0].str.strip()
    df = _clean_department(df)
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
    df = _load_incremental(DATA_INCREMENTAL / "Billing", "Billing", "UniqueRowID")
    df = _normalize_columns(df, {"DepartmentName": "Department"})
    df = _clean_department(df)
    df = _parse_dates(df, ["DateOfService"])
    return df


@lru_cache(maxsize=1)
def load_cpt_audit():
    """Load 2026 CPT Delivery Audit.csv."""
    df = _read_csv_safe(DATA_COMPLETE / "2026 CPT Delivery Audit.csv")
    df = _clean_department(df)
    df = _parse_dates(df, ["TreatmentDate"])
    return df


@lru_cache(maxsize=1)
def load_patients():
    """Load Lookup - Patients.csv."""
    df = _read_csv_safe(DATA_LOOKUP / "Lookup - Patients.csv")
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
    df = _parse_dates(df, ["ScheduledDate"])
    df = df.rename(columns={
        "ScheduledDate": "Date",
        "PhysicianName": "Physician",
        "ActivityName": "Status",
    })
    # Derive Department from Status (site assignment activities)
    site_map = {"CENTRALIA": "Centralia", "ABERDEEN": "Aberdeen"}
    upper = df["Status"].str.upper()
    df["Department"] = upper.map(site_map)
    df.loc[upper.isin(["ON CALL", "WEEKEND CALL"]), "Department"] = "Lacey"
    return df


def clear_cache():
    """Clear all cached data (call after data refresh)."""
    from utils.geocoding import load_geocode_cache

    for fn in [
        _patient_department_map,
        load_treatment, load_treatment_detail, load_daily_volume,
        load_daily_volume_future, load_availability, load_clinic_visits,
        load_simulations, load_workflow, load_tasks, load_otvs,
        load_weekly_visits, load_courses, load_plans, load_machines,
        load_billing, load_cpt_audit, load_patients, load_referring,
        load_diagnosis, load_physician_schedule,
        load_geocode_cache,
    ]:
        fn.cache_clear()
