"""Data loading and preprocessing for RadiantCare Clinical Dashboard."""

import pandas as pd
from functools import lru_cache
from pathlib import Path

from config.settings import DATA_DIR, DATA_COMPLETE, DATA_INCREMENTAL, DATA_LOOKUP, DATA_CACHE


# ---------------------------------------------------------------------------
# Parquet cache — avoids re-parsing CSVs on every app restart.
# The cache dir is created lazily; each dataset gets a .parquet file that is
# invalidated when any source CSV is newer.
# ---------------------------------------------------------------------------

def _parquet_cache_path(name):
    """Return the parquet cache file path for a dataset name."""
    DATA_CACHE.mkdir(exist_ok=True)
    return DATA_CACHE / f"{name}.parquet"


def _source_mtime(paths):
    """Return the newest mtime across a list of Paths."""
    if not paths:
        return 0
    return max(p.stat().st_mtime for p in paths if p.exists())


def _read_parquet_cache(name, source_paths):
    """Read from parquet cache if it's newer than all source files.

    Returns the cached DataFrame or None if cache is stale/missing.
    """
    pq = _parquet_cache_path(name)
    if not pq.exists():
        return None
    try:
        pq_mtime = pq.stat().st_mtime
        if pq_mtime > _source_mtime(source_paths):
            return pd.read_parquet(pq, engine="pyarrow")
    except Exception:
        pass
    return None


def _write_parquet_cache(name, df):
    """Write a DataFrame to the parquet cache."""
    if df.empty:
        return
    try:
        pq = _parquet_cache_path(name)
        df.to_parquet(pq, engine="pyarrow", compression="zstd")
    except Exception:
        pass  # Cache write failure is non-fatal


def _source_files_for_incremental(folder, base_name):
    """List source CSV paths for an incremental dataset."""
    folder = Path(folder)
    return sorted(folder.glob(f"{base_name}_*.csv"))


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


# Generic physician names used in ARIA for site-level placeholders
_GENERIC_PHYSICIAN_MAP = {
    "Physician, Aberdeen": "Aberdeen MD",
    "Physician, Centralia": "Centralia MD",
}


def _rename_generic_physicians(df):
    """Replace generic 'Physician, Site' entries with 'Site MD, ' in physician columns.

    This ensures legend labels show 'Aberdeen MD' / 'Centralia MD' instead of
    the ambiguous 'Physician' after the standard split-on-comma display logic.
    Skips 'Specialty' columns to avoid corrupting actual specialty values.
    """
    phys_cols = [c for c in df.columns
                 if "Physician" in c and "Specialty" not in c]
    for col in phys_cols:
        if df[col].dtype == object:
            df[col] = df[col].replace(_GENERIC_PHYSICIAN_MAP)
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

    Reads files matching ``base_name_yyyymmdd.csv`` (date-suffixed
    increments), concatenates them in date order, and deduplicates by
    *dedup_key*.  The row from the latest-dated file wins, **except**
    referring-physician columns are preserved: if an earlier file has a
    non-null referring value and a later file has null, the earlier value
    is kept.

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

    # Gather date-suffixed increments (base_name_yyyymmdd.csv)
    files = []
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
    _src = _source_files_for_incremental(DATA_INCREMENTAL / "TreatmentDetail", "Treatment - Detail")
    cached = _read_parquet_cache("TreatmentDetail", _src)
    if cached is not None:
        return cached
    df = _load_incremental(DATA_INCREMENTAL / "TreatmentDetail", "Treatment - Detail", "SessionUniqueID")
    df = _normalize_columns(df, {
        "TreatmentDate": "ScheduledDateTime",
        "PatientMRN": "PatientId",
        "PatientName": "PatientFullName",
    })
    df = _clean_department(df)
    df = _parse_dates(df, ["ScheduledDateTime", "AppointmentDateTime",
                           "TreatmentStartTime", "TreatmentEndTime"])
    _composite = ["PatientId", "ScheduledDateTime", "Machine", "FractionNumber", "CourseName"]
    _usable = [c for c in _composite if c in df.columns]
    if _usable:
        df = df.drop_duplicates(subset=_usable, keep="last")
    df = _rename_generic_physicians(df)
    _write_parquet_cache("TreatmentDetail", df)
    return df


@lru_cache(maxsize=1)
def load_daily_volume():
    """Load Daily Volume - Past.csv.

    Columns: Location→Department, Date→ScheduledDate,
    FirstScheduledStart, LastScheduledEnd, AppointmentCount,
    FirstActualStart, LastActualEnd
    """
    src = DATA_COMPLETE / "Daily Volume - Past.csv"
    cached = _read_parquet_cache("DailyVolumePast", [src])
    if cached is not None:
        return cached
    df = _read_csv_safe(src)
    df = _normalize_columns(df, {"Location": "Department", "Site": "Department", "Date": "ScheduledDate"})
    df = _clean_department(df)
    df = _reshape_daily_volume(df)
    df = _parse_dates(df, ["ScheduledDate"])
    _write_parquet_cache("DailyVolumePast", df)
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
def load_daily_volume_by_resource():
    """Load Daily Volume - Past.csv at resource (machine) granularity.

    Keeps Treatment + Simulation Category rows with Resource as the key.
    Used by Operations efficiency chart.
    """
    df = _read_csv_safe(DATA_COMPLETE / "Daily Volume - Past.csv")
    df = _normalize_columns(df, {"Date": "ScheduledDate"})
    df = _parse_dates(df, ["ScheduledDate"])
    # Keep only rows with a specific Resource (drop aggregate/Total rows)
    df = df[df["Resource"].notna() & (df["Category"] != "Total")]
    return df


@lru_cache(maxsize=1)
def load_availability():
    """Load the most recent Availability snapshot.

    Availability files are full snapshots (not deltas), so only the latest
    file should be used — older files contain stale slot states.

    Columns: DepartmentName→Department, AppointmentDateTime→SlotDate,
    Category, ScheduledEndTime, DurationMinutes, ActivityName, etc.
    """
    folder = DATA_INCREMENTAL / "Availability"
    files = []
    for f in folder.glob("Availability_*.csv"):
        suffix = f.stem[len("Availability") + 1:]
        try:
            files.append((int(suffix), f))
        except ValueError:
            continue
    if not files:
        return pd.DataFrame()
    files.sort(key=lambda x: x[0])
    df = _read_csv_safe(files[-1][1])  # Latest file only
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

    Columns: DepartmentName→Department, ActivityStatus→Status.
    Includes SimulationStatus, SimActivityName, ModalityType for pipeline tracking.
    """
    _src = _source_files_for_incremental(DATA_INCREMENTAL / "ClinicVisits", "Clinic Visits")
    cached = _read_parquet_cache("ClinicVisits", _src)
    if cached is not None:
        return cached
    df = _load_incremental(DATA_INCREMENTAL / "ClinicVisits", "Clinic Visits", "UniqueRowID")
    df = _normalize_columns(df, {
        "DepartmentName": "Department",
        "ActivityStatus": "Status",
    })
    df = _clean_department(df)
    df = _parse_dates(df, ["ScheduledDateTime", "AppointmentCreatedDate",
                           "SimulationDateTime"])
    df = _rename_generic_physicians(df)
    _write_parquet_cache("ClinicVisits", df)
    return df


@lru_cache(maxsize=1)
def load_simulations():
    """Load Simulations.csv.

    Department now included in source. ActivityStatus→Status for filtering.
    """
    _src = _source_files_for_incremental(DATA_INCREMENTAL / "Simulations", "Simulations")
    cached = _read_parquet_cache("Simulations", _src)
    if cached is not None:
        return cached
    df = _load_incremental(DATA_INCREMENTAL / "Simulations", "Simulations", "UniqueRowID")
    df = _normalize_columns(df, {"ActivityStatus": "Status"})
    df = _parse_dates(df, ["ScheduledDateTime", "AppointmentCreatedDate",
                           "PriorClinicExamAppointmentDate", "FirstTreatmentDate",
                           "ScheduledTreatmentDate"])
    # Department is now in source; fall back to Treatment Detail map if missing
    if "Department" not in df.columns and "PatientId" in df.columns:
        dept_map = _patient_department_map()
        if not dept_map.empty:
            df = df.merge(dept_map, on="PatientId", how="left")
    df = _clean_department(df)
    df = _rename_generic_physicians(df)
    _write_parquet_cache("Simulations", df)
    return df


@lru_cache(maxsize=1)
def load_workflow():
    """Load Workflow.csv — stage-based format.

    Each row is one workflow stage (Exam, Simulation, Draw, ContourReview,
    Isodose, ReviewPlan, Treatment). Department now included in source.
    """
    _src = _source_files_for_incremental(DATA_INCREMENTAL / "Workflow", "Workflow")
    cached = _read_parquet_cache("Workflow", _src)
    if cached is not None:
        return cached
    df = _load_incremental(
        DATA_INCREMENTAL / "Workflow", "Workflow",
        ["UniqueRowID", "StageName", "StageOccurrence"],
    )
    df = _parse_dates(df, [
        "StageDateTime", "StageEndDateTime", "StageDueDateTime",
        "StageCreationDateTime", "BaselineDateTime", "ExamDateTime",
    ])
    if "Department" not in df.columns and "PatientId" in df.columns:
        dept_map = _patient_department_map()
        if not dept_map.empty:
            df = df.merge(dept_map, on="PatientId", how="left")
    df = _clean_department(df)
    df = _rename_generic_physicians(df)
    _write_parquet_cache("Workflow", df)
    return df


@lru_cache(maxsize=1)
def load_tasks():
    """Load Tasks.csv.

    Columns: PatientName→PatientFullName.
    Includes simulation linkage columns for draw/review turnaround analysis.
    """
    _src = DATA_COMPLETE / "Tasks.csv"
    cached = _read_parquet_cache("Tasks", [_src])
    if cached is not None:
        return cached
    df = _read_csv_safe(_src)
    df = _normalize_columns(df, {"PatientName": "PatientFullName"})
    df = _parse_dates(df, [
        "StartDateTime", "DueDateTime", "CompletedDateTime",
        "PriorStepBaseline",
        "DrawCreationDateTime", "SimulationDateTime",
        "SimScheduledEndDateTime", "SimActualEndDateTime",
    ])
    if "UniqueRowID" in df.columns:
        df = df.drop_duplicates(subset=["UniqueRowID"], keep="last")
    df = _rename_generic_physicians(df)
    _write_parquet_cache("Tasks", df)
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
    _src = _source_files_for_incremental(DATA_INCREMENTAL / "WeeklyVisits", "Weekly Visits")
    cached = _read_parquet_cache("WeeklyVisits", _src)
    if cached is not None:
        return cached
    df = _load_incremental(DATA_INCREMENTAL / "WeeklyVisits", "Weekly Visits", "UniqueRowID")
    df = _normalize_columns(df, {"DepartmentName": "Department"})
    df = _clean_department(df)
    df = _parse_dates(df, ["AppointmentDateTime"])
    _write_parquet_cache("WeeklyVisits", df)
    return df


@lru_cache(maxsize=1)
def load_courses():
    """Load Courses.csv.

    Columns: CourseStartDateTime→CourseStartDate, Departments→Department
    (takes first department if comma-separated), PatientName→PatientFullName
    """
    _src = _source_files_for_incremental(DATA_INCREMENTAL / "Courses", "Courses")
    cached = _read_parquet_cache("Courses", _src)
    if cached is not None:
        return cached
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
    df = _rename_generic_physicians(df)
    _write_parquet_cache("Courses", df)
    return df


@lru_cache(maxsize=1)
def load_plans():
    """Load Plans.csv.

    Columns: Departments→Department (comma-separated, take first),
    PatientName→PatientFullName
    """
    _src = _source_files_for_incremental(DATA_INCREMENTAL / "Plans", "Plans")
    cached = _read_parquet_cache("Plans", _src)
    if cached is not None:
        return cached
    df = _load_incremental(DATA_INCREMENTAL / "Plans", "Plans", "UniqueRowID")
    df = _normalize_columns(df, {"PatientName": "PatientFullName"})
    # Departments is sometimes comma-separated; take the first one
    if "Departments" in df.columns and "Department" not in df.columns:
        df["Department"] = df["Departments"].str.split(",").str[0].str.strip()
    df = _clean_department(df)
    df = _parse_dates(df, ["PlanCreationDate", "CourseStartDateTime",
                           "FirstTreatmentDate", "LastTreatmentDate"])
    df = _rename_generic_physicians(df)
    _write_parquet_cache("Plans", df)
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
def load_downtime_gaps():
    """Load Machine Downtime - Gaps incremental files.

    Pre-computed inter-treatment gaps with confidence scoring,
    cancellation counts, reroute detection, and corroborating signals.
    Columns: RowKey, RowType (Gap/FullDay/EndOfDay/StartOfDay), Site, Machine,
    DowntimeDate, GapStartTime, GapEndTime, GapMinutes,
    GapClassification, DowntimeConfidence, CancelledInGap,
    MachineErrorsNearGap, RerouteMachine, PatientOutcome, etc.
    """
    _src = sorted((DATA_INCREMENTAL / "MachineDowntimeGaps").glob("*.csv"))
    cached = _read_parquet_cache("DowntimeGaps", _src)
    if cached is not None:
        return cached
    df = _load_incremental(
        DATA_INCREMENTAL / "MachineDowntimeGaps",
        "Machine Downtime - Gaps",
        "RowKey",
    )
    df = _parse_dates(df, ["DowntimeDate"])
    # Convert mixed-type object columns to strings for parquet compatibility
    pq_df = df.copy()
    for col in pq_df.columns:
        if pq_df[col].dtype == object:
            pq_df[col] = pq_df[col].astype(str).replace({"None": "", "nan": ""})
    _write_parquet_cache("DowntimeGaps", pq_df)
    return df


_FIELDS_USECOLS = [
    "RecordType", "Site", "Machine", "ActivityDate", "StartTime", "EndTime",
    "DurationSeconds", "PatientId", "PatientName", "CourseId", "FieldId",
    "FractionNumber", "PlannedMU", "DeliveredMU", "FieldStatus",
    "TerminationStatus", "FieldCategory", "ImageType",
]


def load_downtime_fields_for_date(target_date):
    """Load Machine Downtime - Fields, filtered to a single date.

    Scans ALL incremental files (not just the latest) since each file
    is a date-range snapshot and older dates only exist in older files.
    Only loads essential columns via usecols for reduced memory.

    Parameters
    ----------
    target_date : str or pd.Timestamp
        Date to filter to.  Accepts MM/DD/YYYY string or Timestamp.
    """
    if hasattr(target_date, "strftime"):
        target_date = target_date.strftime("%m/%d/%Y")
    folder = DATA_INCREMENTAL / "MachineDowntimeFields"
    files = sorted(
        folder.glob("Machine Downtime - Fields_*.csv"),
        key=lambda f: f.stem.rsplit("_", 1)[-1],
    )
    if not files:
        return pd.DataFrame()

    # Scan files from newest to oldest; stop once we find the target date.
    # usecols passed as a callable so sanitized (PHI_MODE) files that drop
    # columns like PatientName don't raise.
    wanted = set(_FIELDS_USECOLS)
    usecols = lambda c: c in wanted
    for fpath in reversed(files):
        try:
            df = pd.read_csv(
                fpath, usecols=usecols,
                encoding="utf-8-sig", engine="pyarrow",
            )
        except Exception:
            df = pd.read_csv(
                fpath, usecols=usecols,
                encoding="utf-8-sig", on_bad_lines="skip", low_memory=False,
            )

        matched = df[df["ActivityDate"] == target_date]
        if not matched.empty:
            return matched.copy()

    return pd.DataFrame(columns=_FIELDS_USECOLS)


_IMAGING_USECOLS = [
    "RecordType", "Site", "Machine", "ActivityDate", "PatientId",
    "FieldId", "StartTime",
]


def _dedup_rapid_images(df):
    """Collapse rapid-fire image records into single acquisitions.

    Some machines (notably the 21EX) logged individual CBCT projections
    as separate Image rows ~1-2 seconds apart. Normal multi-CBCT gaps
    are 30+ seconds. This groups image records for the same patient/
    machine/day and collapses sequences <30s apart into one row.
    Treatment rows pass through unchanged.
    """
    import datetime

    tx = df[df["RecordType"] == "Treatment"]
    imgs = df[df["RecordType"] != "Treatment"].copy()
    if imgs.empty:
        return df

    # Build a seconds-since-midnight column for gap detection
    def _to_seconds(t):
        if isinstance(t, datetime.time):
            return t.hour * 3600 + t.minute * 60 + t.second
        return 0

    imgs["_secs"] = imgs["StartTime"].apply(_to_seconds)
    imgs = imgs.sort_values(["ActivityDate", "PatientId", "Machine", "_secs"])

    # Detect group boundaries: new group when patient/machine/day changes
    # or gap >= 30 seconds
    diff_pat = imgs["PatientId"] != imgs["PatientId"].shift()
    diff_machine = imgs["Machine"] != imgs["Machine"].shift()
    diff_day = imgs["ActivityDate"] != imgs["ActivityDate"].shift()
    gap = imgs["_secs"].diff().abs() >= 30
    imgs["_grp"] = (diff_pat | diff_machine | diff_day | gap).cumsum()

    # Keep first row of each group (the acquisition start)
    deduped = imgs.groupby("_grp").first().reset_index(drop=True)
    deduped = deduped.drop(columns=["_secs"], errors="ignore")

    return pd.concat([tx, deduped], ignore_index=True)


def load_downtime_fields_imaging():
    """Load imaging and treatment records from Machine Downtime - Fields.

    Returns a DataFrame with columns: RecordType, Site, Machine,
    ActivityDate, PatientId, FieldId, StartTime.
    RecordType values: Image (CBCT), PortFilm, Treatment.
    Deduplicates on (ActivityDate, PatientId, FieldId, StartTime),
    then collapses rapid-fire image records (<30s apart) into single
    acquisitions.
    """
    folder = DATA_INCREMENTAL / "MachineDowntimeFields"
    files = sorted(
        folder.glob("Machine Downtime - Fields_*.csv"),
        key=lambda f: f.stem.rsplit("_", 1)[-1],
    )
    if not files:
        return pd.DataFrame(columns=_IMAGING_USECOLS)

    dfs = []
    for fpath in files:
        try:
            df = pd.read_csv(
                fpath, usecols=_IMAGING_USECOLS,
                encoding="utf-8-sig", engine="pyarrow",
            )
        except Exception:
            df = pd.read_csv(
                fpath, usecols=_IMAGING_USECOLS,
                encoding="utf-8-sig", on_bad_lines="skip", low_memory=False,
            )
        # Keep only imaging + treatment rows to reduce memory
        df = df[df["RecordType"].isin(["Image", "PortFilm", "Treatment"])]
        if not df.empty:
            dfs.append(df)

    if not dfs:
        return pd.DataFrame(columns=_IMAGING_USECOLS)

    combined = pd.concat(dfs, ignore_index=True)
    combined.drop_duplicates(
        subset=["ActivityDate", "PatientId", "FieldId", "StartTime"],
        keep="last", inplace=True,
    )
    combined = _parse_dates(combined, ["ActivityDate"])
    combined = _dedup_rapid_images(combined)
    return combined


def load_machine_downtime():
    """Deprecated — use load_downtime_gaps() instead."""
    return load_downtime_gaps()


@lru_cache(maxsize=1)
def load_machine_statistics():
    """Load Machine Statistics.csv — lifetime and yearly stats per linac.

    Sections: 1-All Data, 2-All Data by Year, 3-Real Patients, 4-Real Patients by Year.
    Columns: Section, Machine, DataYear, TotalFields, TotalDose_Gy,
    TotalFractions, AvgDosePerFx_Gy, TotalSessions, TotalPatients,
    OperatingLife, MostRecentTreatment.
    """
    df = _read_csv_safe(DATA_COMPLETE / "Machine Statistics.csv")
    df = _parse_dates(df, ["OperatingLife", "MostRecentTreatment"])
    # DataYear is numeric (year int) for by-year sections, blank for lifetime
    if "DataYear" in df.columns:
        df["DataYear"] = pd.to_numeric(df["DataYear"], errors="coerce")
    return df


@lru_cache(maxsize=1)
def load_billing():
    """Load Billing.csv.

    Columns: DepartmentName→Department.
    Includes ActivityCategory, billing workflow status columns, etc.
    """
    _src = _source_files_for_incremental(DATA_INCREMENTAL / "Billing", "Billing")
    cached = _read_parquet_cache("Billing", _src)
    if cached is not None:
        return cached
    df = _load_incremental(DATA_INCREMENTAL / "Billing", "Billing", "UniqueRowID")
    df = _normalize_columns(df, {"DepartmentName": "Department"})
    df = _clean_department(df)
    df = _parse_dates(df, ["DateOfService", "ActivityDateTime"])
    df = _rename_generic_physicians(df)
    _write_parquet_cache("Billing", df)
    return df


@lru_cache(maxsize=1)
def load_pluvicto_workflow():
    """Load Pluvicto-specific workflow chains from Workflow CSV.

    Filters Workflow data to ModalityType == 'Pluvicto' for the Procedures
    page Pluvicto patient queue grid.
    """
    wf = load_workflow()
    if "ModalityType" not in wf.columns:
        return pd.DataFrame()
    mask = wf["ModalityType"].str.strip().str.upper() == "PLUVICTO"
    return wf[mask].copy()


@lru_cache(maxsize=1)
def load_procedures():
    """Load Procedures.csv — ancillary procedures (SpaceOAR, Lupron, etc.).

    Columns: DepartmentName→Department.
    """
    df = _load_incremental(DATA_INCREMENTAL / "Procedures", "Procedures", "UniqueRowID")
    df = _normalize_columns(df, {"DepartmentName": "Department"})
    df = _clean_department(df)
    df = _parse_dates(df, ["ScheduledDateTime", "AppointmentCreatedDate"])
    df = _rename_generic_physicians(df)
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
def load_referrals():
    """Load the Referrals Report Excel file.

    Source: Referrals_Report_RadiantCare_All_*.xlsx. Each export is a snapshot
    of the full referral list, so multiple files may exist. Concatenate all
    matches in chronological order and dedupe on `Referral ID` keeping the
    latest row — preserves any referrals dropped from a newer snapshot while
    letting newer exports overwrite status/date updates.

    Columns include MRN (patient ID matching CV PatientId), DOB, and
    Rfl Prim Dx (structured primary diagnosis from referral).
    """
    import glob as _glob

    pattern = str(DATA_DIR / "Referrals_Report_RadiantCare_All_*.xlsx")
    matches = sorted(_glob.glob(pattern))
    if not matches:
        return pd.DataFrame()

    src_paths = [Path(m) for m in matches]
    cached = _read_parquet_cache("Referrals", src_paths)
    if cached is not None:
        return cached

    frames = [pd.read_excel(m) for m in matches]
    df = pd.concat(frames, ignore_index=True)
    if "Referral ID" in df.columns:
        df = df.drop_duplicates(subset=["Referral ID"], keep="last").reset_index(drop=True)

    # Parse date columns
    date_cols = ["Created", "Expires", "First Appt", "Assigned On",
                 "Final Status Date", "Authorized On", "DOB"]
    for col in date_cols:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")

    # Normalise MRN to nullable integer (matches CV PatientId)
    if "MRN" in df.columns:
        df["MRN"] = pd.to_numeric(df["MRN"], errors="coerce").astype("Int64")

    # --- Preprocess referring departments ---
    if "Referred by Department" in df.columns:
        dept = df["Referred by Department"]
        # Strip "DO NOT USE - " prefix
        dept = dept.str.replace(r"^DO NOT USE\s*-\s*", "", regex=True)
        # Remap known renames
        _DEPT_RENAMES = {
            "PMG SW WA CENTRALIA UROLOGY": "PMG SW WA OLYMPIA UROLOGY",
            "PMG SW WA HAWKS PRAIRIE IM": "PMG SW WA HAWKS PRAIRIE FM",
            "PMG SW WA CENTRALIA INT MED": "PMG SW WA CENTRALIA INT MED RHC",
            "PMG SW WA SOUTH SOUND INT MED": "PMG SW WA CENTRALIA INT MED RHC",
        }
        dept = dept.replace(_DEPT_RENAMES)
        # Flag internal referrals (from our own RadiantCare departments)
        df["Referred by Department"] = dept
        df["InternalReferral"] = dept.str.contains(
            r"WCH PRCS.*RADIANTCARE|WCH PRCS.*INFUSION",
            case=False, na=False,
        )

    # --- Enrich with specialty from Referring Lookup ---
    if "Referred by Provider" in df.columns:
        _lookup = load_referring()
        if not _lookup.empty and "DoctorFullName" in _lookup.columns:
            import re as _re2

            _cred_re = _re2.compile(
                r",?\s*(?:MD|DO|ARNP|PA-C|PA|NP|FNP|FACS|PhD|DPM|DDS|DMD|FACP)"
                r"(?:\s+(?:MD|DO|ARNP|PA-C|PA|NP|FNP|FACS|PhD))*\.?\s*$",
                _re2.IGNORECASE,
            )
            # Suffixes/titles that are not part of the last name
            _suffix_re = _re2.compile(
                r"\s+(?:III|II|IV|Jr\.?|Sr\.?|PT|OT|RN|LPN|CNA|LCSW|MSW"
                r"|Speech\s+Therapist|Physician\s+Assistant|Nurse\s+Practitioner)\s*$",
                _re2.IGNORECASE,
            )

            def _norm_ref(name):
                if pd.isna(name) or not str(name).strip():
                    return None
                s = _cred_re.sub("", str(name)).strip().strip(",").strip()
                s = _suffix_re.sub("", s).strip()
                parts = s.split()
                if len(parts) < 2:
                    return parts[0].upper() if parts else None
                return f"{parts[-1].upper()}, {parts[0].upper()}"

            def _norm_lookup(name):
                if pd.isna(name) or not str(name).strip():
                    return None
                parts = str(name).strip().split(",")
                if len(parts) >= 2:
                    first_part = parts[1].strip()
                    first = first_part.split()[0].upper() if first_part else ""
                    last = parts[0].strip().upper()
                    return f"{last}, {first}" if first else last
                return str(name).strip().upper()

            df["_prov_key"] = df["Referred by Provider"].apply(_norm_ref)
            _lookup["_prov_key"] = _lookup["DoctorFullName"].apply(_norm_lookup)
            # When multiple lookup rows share the same key (e.g. two
            # "Edward Kim"s), prefer the row whose specialty is not
            # "Unknown" and that has an institution listed.
            _lk = _lookup[["_prov_key", "DoctorId", "DoctorSpecialty", "DoctorInstitution"]].copy()
            _lk["_rank"] = (
                (_lk["DoctorSpecialty"].fillna("Unknown").ne("Unknown")).astype(int)
                + _lk["DoctorInstitution"].notna().astype(int)
            )
            _lk = _lk.sort_values("_rank", ascending=False).drop_duplicates("_prov_key")
            _lk = _lk.drop(columns=["_rank"])

            df = df.merge(_lk, on="_prov_key", how="left")
            df = df.drop(columns=["_prov_key"])

            # Normalise specialty: fix typos, merge variants
            _SPEC_MAP = {
                # Medical Oncology
                "Medical Onoclogy": "Medical Oncology",
                "Medical Oncologist": "Medical Oncology",
                "Hematology/Oncology": "Medical Oncology",
                "Hematology-Oncogology": "Medical Oncology",
                "Hematology/ Medical Oncology": "Medical Oncology",
                "Hematology/Medical Oncology": "Medical Oncology",
                "Hematology and Oncology": "Medical Oncology",
                "Internal Medicine Hematology & Oncology": "Medical Oncology",
                "Oncology and Hematology": "Medical Oncology",
                "Hematology": "Medical Oncology",
                "Oncologist": "Medical Oncology",
                "Medical oncology": "Medical Oncology",
                "Medical  Oncology": "Medical Oncology",
                "Med Onc": "Medical Oncology",
                "Neuro Oncology": "Neuro-Oncology",
                "Neuro-Oncology": "Neuro-Oncology",
                "Ophthalomology Oncology": "Medical Oncology",
                "Prostate Oncology": "Urology",
                "Urologic Oncology": "Urology",
                "Orthopaedic Oncology": "Orthopedic Oncology",
                "Orthopeadic Oncology": "Orthopedic Oncology",
                # Radiation Oncology
                "Radiation Onocology": "Radiation Oncology",
                "Resident-Radiation Onc": "Radiation Oncology",
                # Pulmonary
                "Pulmonary Disease": "Pulmonary Medicine",
                "Pulmonary": "Pulmonary Medicine",
                "Interventional Pulmonology": "Pulmonary Medicine",
                "Infectious Disease & Pulmonary Disease": "Pulmonary Medicine",
                # Primary Care / Family Medicine
                "Family Practice": "Primary Care",
                "family Medicine": "Primary Care",
                "Family medicine": "Primary Care",
                "Family Practie": "Primary Care",
                "FAMILY PRACTICE": "Primary Care",
                "Family Medicine w/ OB": "Primary Care",
                "Family Practice/Palliative Care": "Primary Care",
                "General Practice": "Primary Care",
                "PCP": "Primary Care",
                "Sports Medicine (Family Practice)": "Primary Care",
                # Internal Medicine
                "Family Practice/Internal Medicine": "Internal Medicine",
                "Endocrinology/Internal Medicine": "Internal Medicine",
                "Internal Medicine/Pulmonology": "Pulmonary Medicine",
                "Internal Medicine/Nephrology": "Nephrology",
                "Endocrinology, Diabetes, and Metabolism": "Endocrinology",
                # Surgery variants
                "Gerneral Surgery": "General Surgery",
                "Surgery": "General Surgery",
                "Surgeon": "General Surgery",
                "Surgery- Surgical Oncology": "Surgical Oncology",
                # ENT
                "Otolaryngology, Facial plastic reconstructive surgery": "Otolaryngology",
                "ENT/Otolaryngology": "Otolaryngology",
                "ENT/Aberdeen": "Otolaryngology",
                "ENT- Group Health": "Otolaryngology",
                "Otology/Neurotology": "Otolaryngology",
                "Head and Neck Surgery": "Otolaryngology",
                # GYN
                "GYN Oncologist": "Gynecologic Oncology",
                "Gynecological Oncology": "Gynecologic Oncology",
                "Gyn Onc": "Gynecologic Oncology",
                "Gynecologic Oncology, Obstetrics and Gynecology": "Gynecologic Oncology",
                "General/GYN": "OB/GYN",
                # Colorectal
                "Colon & rectal surgery": "Colorectal Surgery",
                "Colon Rectal Surgeon": "Colorectal Surgery",
                "Colorectal surgery": "Colorectal Surgery",
                # Dermatology
                "Derm": "Dermatology",
                "Dermatopathology (Pathology)": "Dermatology",
                # Neurology
                "Nuerology": "Neurology",
                # Neurosurgery
                "Neurosurgery (UWMC)": "Neurosurgery",
                # Cardiology
                "cardiology": "Cardiology",
                "Cardiologist": "Cardiology",
                "Interventional Cardiology": "Cardiology",
                "Cardiovascular Disease": "Cardiology",
                # Orthopedics
                "Orthopeadic": "Orthopedics",
                "Orthopedic Surgery": "Orthopedics",
                "Orthopaedic Surgery": "Orthopedics",
                # Ophthalmology
                "Ophthalmoogy": "Ophthalmology",
                # PA / NP / Resident
                "physician Assistant": "PA/NP",
                "Physician assistant": "PA/NP",
                "Physician Assitant": "PA/NP",
                "PA": "PA/NP",
                "PA-C": "PA/NP",
                "Nurse Practioner": "PA/NP",
                "ARNP": "PA/NP",
                "D.O": "Primary Care",
                # Other
                "Pediatric Hematology Oncology": "Pediatric Oncology",
                "Emergency": "Emergency Medicine",
                "Emergency medicine": "Emergency Medicine",
                "Palliative Medicine": "Palliative Care",
                "Hospitalist": "Hospital Medicine",
                "GASTROENTEROLOGY": "Gastroenterology",
                "Unspecified": "Unknown",
                "Acute Care": "Hospital Medicine",
                "Physical Medicine and Rehabilitation": "PM&R",
                "Spinal Cord Injury Medicine (Physical Medicine and Rehab.)": "PM&R",
                "Transplant Hepatology": "Hepatology",
                "Plastic and Reconstructive Surgery": "Plastic Surgery",
                "Interventional Radiology": "Radiology",
                "Summit Pacific Mark Reed Healthcare Clinic": "Primary Care",
                "Military Health Care": "Primary Care",
                # More variants found in data
                "Otalaryngology": "Otolaryngology",
                "Otolaryngology/Facial Plastic Surgery": "Otolaryngology",
                "General and Minimally Invasive Surgery": "General Surgery",
                "Pulmonary Disease and Critical Care Medicine": "Pulmonary Medicine",
                "Family Nurse Practitioner": "PA/NP",
                "Medical Oncology/Hemotology": "Medical Oncology",
                "Medical Oncology & Hematology": "Medical Oncology",
                "Oncology Hematology": "Medical Oncology",
                "Rad Oncology": "Radiation Oncology",
                "Dermatology and Skin Oncology": "Dermatology",
                "Internal Medicine/Pediatrics": "Internal Medicine",
                "GYN": "OB/GYN",
                "GYN Oncology": "Gynecologic Oncology",
                "Ophthalomology": "Ophthalmology",
                "DO": "Primary Care",
                "Neuroradiology": "Radiology",
                "Orthopeadic Surgeon": "Orthopedics",
                "Orthopaedics": "Orthopedics",
                "Neurolosurgery": "Neurosurgery",
                "Resident": "Resident",
                "Oral and Maxillofacial Surgery": "Oral Surgery",
                "Dentistry and Maxillofacial Surgery": "Oral Surgery",
                "Dentistry (Periodontics)": "Oral Surgery",
                "Oral Surgeon": "Oral Surgery",
                "Surgery, Surgical Oncology": "Surgical Oncology",
                "Vascular and interventional Radiology": "Radiology",
                "Acupuncture": "Alternative Medicine",
                "Occupational Therapy": "Other",
                "Critical Care Medicine": "Hospital Medicine",
                "Anesthesiology": "Other",
                "Geriatric Medicine": "Internal Medicine",
                "Urologist": "Urology",
                "Breast Cancer Surgeon": "Breast Surgery",
                "Hematology & Oncology": "Medical Oncology",
                "Hematology oncology": "Medical Oncology",
                "MD": "Unknown",
                "Oncology": "Medical Oncology",
                "Neuro-oncology": "Neuro-Oncology",
                "Gynecology": "OB/GYN",
                "Pediatric Medicine": "Pediatrics",
                "Med Onc/Hematology": "Medical Oncology",
                "Family Medicine": "Primary Care",
                "Pulmonology": "Pulmonary Medicine",
                "Colon and Rectal Surgery": "Colorectal Surgery",
                "Physician Assistant": "PA/NP",
            }
            if "DoctorSpecialty" in df.columns:
                df["DoctorSpecialty"] = df["DoctorSpecialty"].replace(_SPEC_MAP)
                # Case-insensitive regex pass for remaining variants
                _SPEC_REGEX = [
                    (r"(?i)^medical\s*onc", "Medical Oncology"),
                    (r"(?i)^radiation\s*onc", "Radiation Oncology"),
                    (r"(?i)^urol", "Urology"),
                    (r"(?i)^gynecol.*onc", "Gynecologic Oncology"),
                    (r"(?i)^obstetrics|^ob/?gyn", "Obstetrics & Gynecology"),
                    (r"(?i)^neuro.*surg|^neurological\s*surg", "Neurological Surgery"),
                    (r"(?i)^cardiothoracic", "Thoracic & Cardiac Surgery"),
                    (r"(?i)^vascular\s*surg", "General Surgery"),
                ]
                import re as _re3
                for pat, repl in _SPEC_REGEX:
                    mask = df["DoctorSpecialty"].str.match(pat, na=False)
                    df.loc[mask, "DoctorSpecialty"] = repl

                # Final normalisation: map DoctorSpecialty to DeptSpecialty
                # categories (ABMS-aligned) so both columns use the same set
                _DOC_TO_DEPT = {
                    # Direct renames to ABMS categories
                    "Primary Care": "Family Medicine",
                    "Pulmonary Medicine": "Pulmonary Disease",
                    "Neurosurgery": "Neurological Surgery",
                    "Colorectal Surgery": "Colon & Rectal Surgery",
                    "Thoracic Surgery": "Thoracic & Cardiac Surgery",
                    "Cardiac Surgery": "Thoracic & Cardiac Surgery",
                    "Cardiology": "Cardiovascular Disease",
                    "Palliative Care": "Hospice & Palliative Medicine",
                    "OB/GYN": "Obstetrics & Gynecology",
                    "Orthopedics": "Orthopaedic Surgery",
                    "Orthopedic Oncology": "Orthopaedic Surgery",
                    "PM&R": "Physical Medicine & Rehabilitation",
                    "ENT": "Otolaryngology",
                    "Vascular Surgery": "General Surgery",
                    "Surgical Oncology": "General Surgery",
                    "Plastic Surgery": "General Surgery",
                    # Merge small categories
                    "PA/NP": "Unknown",
                    "Nurse Practitioner": "Unknown",
                    "Resident": "Unknown",
                    "Neuro-Oncology": "Neurology",
                    "Hematalogy & Oncology": "Medical Oncology",
                    "Nephrology": "Internal Medicine",
                    "Hepatology": "Internal Medicine",
                    "Ophthalmology": "Ophthalmology",  # keep
                    "Dermatology": "Dermatology",      # keep
                    "Gynecologic Oncology": "Gynecologic Oncology",  # keep (onc)
                    "Oral Surgery": "Otolaryngology",
                    "Radiology": "Radiology",
                    "Pain Management": "Physical Medicine & Rehabilitation",
                    "Podiatry": "Other",
                    "Hospital Medicine": "Hospital Medicine",
                }
                if "DoctorSpecialty" in df.columns:
                    df["DoctorSpecialty"] = df["DoctorSpecialty"].replace(_DOC_TO_DEPT)

            # Infer specialty from department name when lookup missed.
            # Also build DeptSpecialty for ALL rows (dept-derived, independent
            # of provider lookup) since dept specialty is often more accurate
            # than provider specialty for referral source analysis.
            #
            # Categories based on ABMS member boards, kept sparse with
            # oncology-relevant subspecialties preserved.
            _DEPT_SPEC = [
                # Oncology subspecialties (keep granular)
                (r"MED(?:ICAL)?\s*ONC|PROVIDER ONCOLOGY|ONCOLOGY(?!.*RADIAT)", "Medical Oncology"),
                (r"RADIATION|RADIOSURGERY|RADIANTCARE", "Radiation Oncology"),
                (r"PRCS\s+(?:LACEY|CENTRALIA|ABERDEEN)\b", "Medical Oncology"),
                (r"GYN ONCOLOGY", "Gynecologic Oncology"),
                (r"BREAST SURGERY", "Breast Surgery"),
                # Surgical specialties
                (r"GEN SURG", "General Surgery"),
                (r"CARDIAC SURGERY", "Thoracic & Cardiac Surgery"),
                (r"THORACIC", "Thoracic & Cardiac Surgery"),
                (r"COLORECTAL|COLON AND RECTAL", "Colon & Rectal Surgery"),
                (r"NEUROSURGERY", "Neurological Surgery"),
                (r"PROVIDER SURGICAL|INTRA OP", "General Surgery"),
                # Medical specialties
                (r"UROLOGY", "Urology"),
                (r"PULMONARY|LUNG NODULE|PULMONOLOGY", "Pulmonary Disease"),
                (r"NEUROLOGY|NEURO TRAUMA", "Neurology"),
                (r"GASTROENTEROLOGY", "Gastroenterology"),
                (r"ENDOCRINE", "Endocrinology"),
                (r"CARDIO(?!.*SURG)", "Cardiovascular Disease"),
                (r"ORTHOPEDICS", "Orthopaedic Surgery"),
                (r"OPHTHALMOLOGY", "Ophthalmology"),
                (r"HEAD AND NECK", "Otolaryngology"),
                # OB/GYN
                (r"OBGYN|WOMEN CTR", "Obstetrics & Gynecology"),
                # Primary Care / FM / IM
                (r"FAM MED|FAMILY MED|FAMILY MEDICINE", "Family Medicine"),
                (r"PRIMARY CARE|WELLNESS CLINIC", "Family Medicine"),
                (r"PRCS\s", "Family Medicine"),
                (r"INT MED", "Internal Medicine"),
                (r"65 PLUS", "Internal Medicine"),
                # Hospital-based
                (r"EMERGENCY", "Emergency Medicine"),
                (r"IMMEDIATE CARE", "Emergency Medicine"),
                (r"PALLIATIVE", "Hospice & Palliative Medicine"),
                (r"PROGRESSIVE CARE|MEDICAL TELEMETRY|ICU", "Hospital Medicine"),
                (r"INFUSION", "Infusion Services"),
                (r"CENTRALIZED CARE", "Internal Medicine"),
                (r"RADIOLOGY", "Radiology"),
                (r"PROVIDER MED SURG", "Hospital Medicine"),
                (r"HAWKS PRAIRIE", "Family Medicine"),
                (r"PANORAMA", "Internal Medicine"),
                (r"PHY MED", "Physical Medicine & Rehabilitation"),
            ]
            # Build DeptSpecialty for all rows
            if "Referred by Department" in df.columns:
                df["DeptSpecialty"] = None
                dept_all = df["Referred by Department"].fillna("")
                for pattern, spec in _DEPT_SPEC:
                    mask = dept_all.str.contains(pattern, case=False, na=False) & df["DeptSpecialty"].isna()
                    df.loc[mask, "DeptSpecialty"] = spec

            # Cross-fill: DoctorSpecialty ↔ DeptSpecialty where one is missing
            if "DoctorSpecialty" in df.columns and "DeptSpecialty" in df.columns:
                needs_doc = df["DoctorSpecialty"].isna()
                df.loc[needs_doc, "DoctorSpecialty"] = df.loc[needs_doc, "DeptSpecialty"]
                needs_dept = df["DeptSpecialty"].isna()
                df.loc[needs_dept, "DeptSpecialty"] = df.loc[needs_dept, "DoctorSpecialty"]

    # --- Provider-level overrides for ambiguous lookup matches ---
    # Applied after all specialty normalization and cross-fill.
    if "Referred by Provider" in df.columns:
        _PROVIDER_OVERRIDES = {
            "Edward Y Kim": ("Radiation Oncology", "UWMC"),
            "Edward J Kim": ("Radiation Oncology", "UWMC"),
        }
        for prov_name, (spec, inst) in _PROVIDER_OVERRIDES.items():
            mask = df["Referred by Provider"].str.startswith(prov_name, na=False)
            if mask.any():
                df.loc[mask, "DoctorSpecialty"] = spec
                df.loc[mask, "DoctorInstitution"] = inst
                if "DeptSpecialty" in df.columns:
                    df.loc[mask, "DeptSpecialty"] = spec

    # --- Apply SQLite referring physician overrides (final authority) ---
    if "DoctorId" in df.columns:
        try:
            from data.reviews_db import get_all_referring_overrides, _addr_key
            _overrides = get_all_referring_overrides()
            if _overrides:
                # Build composite key in the dataframe to match overrides
                _npi_col = df["DoctorId"].dropna().astype(int).astype(str)
                _city = df.get("Referring Provider City", pd.Series("", index=df.index)).fillna("").astype(str)
                _state = df.get("Referring Provider State", pd.Series("", index=df.index)).fillna("").astype(str)
                _zip = df.get("Referring Provider Zip Code", pd.Series("", index=df.index)).fillna("").astype(str)
                _ak = pd.Series(
                    [_addr_key(c, s, z) for c, s, z in zip(_city, _state, _zip)],
                    index=df.index,
                )
                _row_key = _npi_col + "|" + _ak
                for key, vals in _overrides.items():
                    mask = _row_key == key
                    if not mask.any():
                        # Fall back to NPI-only match if address_key is empty
                        npi_part = key.split("|")[0]
                        if "|" in key and key.split("|", 1)[1] == "":
                            mask = _npi_col == npi_part
                    if not mask.any():
                        continue
                    idx = mask[mask].index
                    if vals.get("specialty"):
                        df.loc[idx, "DoctorSpecialty"] = vals["specialty"]
                        if "DeptSpecialty" in df.columns:
                            df.loc[idx, "DeptSpecialty"] = vals["specialty"]
                    if vals.get("institution"):
                        df.loc[idx, "DoctorInstitution"] = vals["institution"]
        except Exception:
            pass

    # --- Normalise referring provider names (strip credential suffixes) ---
    if "Referred by Provider" in df.columns:
        # Preserve original name with credentials for search/display
        df["Referred by Provider Raw"] = df["Referred by Provider"].copy()
        import re as _re
        _CRED = _re.compile(
            r",?\s*(?:MD|DO|ARNP|PA-C|PA|NP|FNP|FACS|PhD|DPM|DDS|DMD|FACP)"
            r"(?:\s+(?:MD|DO|ARNP|PA-C|PA|NP|FNP|FACS|PhD))*\.?\s*$",
            _re.IGNORECASE,
        )
        df["Referred by Provider"] = (
            df["Referred by Provider"]
            .str.replace(_CRED, "", regex=True)
            .str.strip()
            .str.strip(",")
            .str.strip()
        )

    _write_parquet_cache("Referrals", df)
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
def load_rvu_lookup():
    """Load CMS Physician Fee Schedule RVU lookup (all years 2015-2026).

    Returns DataFrame with columns: HCPCS, MOD, Description, wRVU,
    NonFac_PE_RVU, Fac_PE_RVU, MP_RVU, NonFac_Total_RVU, Fac_Total_RVU, Year.
    MOD is '' for Global, 'TC' for Technical, '26' for Professional.
    """
    path = Path(__file__).parent / "rvu_files" / "rvu_lookup.csv"
    df = pd.read_csv(path, low_memory=False)
    df["HCPCS"] = df["HCPCS"].astype(str).str.strip()
    df["MOD"] = df["MOD"].fillna("").astype(str).str.strip()
    df["MOD"] = df["MOD"].replace("nan", "")
    df["Year"] = pd.to_numeric(df["Year"], errors="coerce").astype("Int64")
    for col in ("wRVU", "NonFac_PE_RVU", "Fac_PE_RVU", "MP_RVU",
                "NonFac_Total_RVU", "Fac_Total_RVU"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
    return df


@lru_cache(maxsize=1)
def load_gpci():
    """Load GPCI values for Rest of Washington (Locality 99), 2015-2026.

    Returns dict keyed by year: {year: (Work_GPCI, PE_GPCI, MP_GPCI)}.
    """
    path = Path(__file__).parent / "rvu_files" / "gpci_rest_of_wa.csv"
    df = pd.read_csv(path)
    return {
        int(r["Year"]): (r["Work_GPCI"], r["PE_GPCI"], r["MP_GPCI"])
        for _, r in df.iterrows()
    }


@lru_cache(maxsize=1)
def load_opps_lookup():
    """Load CMS OPPS Addendum B payment rates (2024-2026).

    Returns DataFrame with columns: HCPCS, Description, StatusIndicator,
    APC, RelativeWeight, PaymentRate, Year.
    PaymentRate is the national unadjusted Medicare OPPS payment per unit.
    """
    path = Path(__file__).parent / "opps_files" / "opps_lookup.csv"
    df = pd.read_csv(path, low_memory=False)
    df["HCPCS"] = df["HCPCS"].astype(str).str.strip()
    df["Year"] = pd.to_numeric(df["Year"], errors="coerce").astype("Int64")
    df["PaymentRate"] = pd.to_numeric(df["PaymentRate"], errors="coerce").fillna(0)
    df["APC"] = pd.to_numeric(df["APC"], errors="coerce")
    df["RelativeWeight"] = pd.to_numeric(df["RelativeWeight"], errors="coerce").fillna(0)
    return df


@lru_cache(maxsize=1)
def load_opps_params():
    """Load OPPS payment parameters for Providence Centralia (CCN 500019).

    Returns dict keyed by year: {year: (OPPS_CF, WageIndex, LaborShare, SCH_Adj)}.
    Covers 2024-2026.  Both Lacey and Centralia use this parent hospital.
    """
    path = Path(__file__).parent / "opps_files" / "opps_params.csv"
    df = pd.read_csv(path)
    return {
        int(r["Year"]): (r["OPPS_CF"], r["WageIndex"], r["LaborShare"], r["SCH_Adj"])
        for _, r in df.iterrows()
    }


@lru_cache(maxsize=1)
def load_physician_schedule():
    """Load Physician Schedule.csv.

    DepartmentName (with * prefix) now in source.
    """
    df = _read_csv_safe(DATA_COMPLETE / "Physician Schedule.csv")
    df = _normalize_columns(df, {"DepartmentName": "Department"})
    df = _clean_department(df)
    df = _parse_dates(df, ["ScheduledDate"])
    df = df.rename(columns={
        "ScheduledDate": "Date",
        "PhysicianName": "Physician",
        "ActivityName": "Status",
    })
    df = _rename_generic_physicians(df)
    return df


def clear_cache():
    """Clear all cached data (call after data refresh)."""
    from utils.geocoding import load_geocode_cache
    from utils.holidays import clear_holidays_cache
    import shutil

    for fn in [
        _patient_department_map,
        load_treatment, load_treatment_detail, load_daily_volume,
        load_daily_volume_future, load_daily_volume_by_resource,
        load_availability, load_clinic_visits,
        load_simulations, load_workflow, load_tasks, load_otvs,
        load_weekly_visits, load_courses, load_plans, load_machines,
        load_downtime_gaps,
        load_billing, load_cpt_audit, load_procedures, load_machine_statistics,
        load_patients,
        load_referrals,
        load_referring, load_diagnosis, load_physician_schedule,
        load_geocode_cache,
    ]:
        fn.cache_clear()
    clear_holidays_cache()
    # Clear parquet cache so next load rebuilds from source CSVs
    if DATA_CACHE.exists():
        shutil.rmtree(DATA_CACHE, ignore_errors=True)
