"""Data loading and preprocessing for RadiantCare Clinical Dashboard."""

import gc
import os
import threading
import time as _time
import pandas as pd
from functools import lru_cache
from pathlib import Path

from config.settings import DATA_DIR, DATA_COMPLETE, DATA_INCREMENTAL, DATA_LOOKUP, DATA_CACHE


# ---------------------------------------------------------------------------
# Memory-conscious caching for the heavy loaders.
#
# Background: a Railway hobby-plan dashboard pays per minutely-GB of RSS.
# The 4 monster datasets (billing, treatment_detail, downtime_gaps, workflow)
# account for >90% of dataframe memory. A plain @lru_cache pins them in RAM
# forever; a TTL cache lets idle datasets fall out and the OS reclaim pages.
# Categorical dtypes shrink the held footprint of the surviving frames 2-5x.
# ---------------------------------------------------------------------------


import re as _re_loader

# Columns whose names match this pattern are treated as identifiers / join
# keys and skipped from categorical encoding even when their cardinality is
# low enough to qualify. CategoricalIndex breaks several pandas merge/join
# code paths (KeyError: slice(None, None, None) etc.) and the dictionary-
# encoding savings on ID columns are minimal anyway because every value is
# unique-ish.
_KEY_COLUMN_RE = _re_loader.compile(
    r"(?:^|[A-Z_])(?:id|mrn|key|hash|guid|uuid|rowid|uniquerow)$"
    r"|^(?:CourseName|SessionUniqueID|UniqueRowID|PatientMRN|PatientId)$",
    _re_loader.IGNORECASE,
)


def _categorize_low_cardinality(df, ratio_threshold=0.5, max_unique=1000):
    """No-op: dictionary-encoding is disabled to prevent CategoricalIndex
    bugs in downstream pivot/join/fillna code paths.

    Categorical encoding saved roughly 240 MB across the big-four datasets
    but produced a steady stream of latent bugs (KeyError: slice(...) in
    merge.py, fillna(unknown_category) on grid sanitization, etc.) that
    only surface on specific pages and only after a parquet round-trip.
    The TTL eviction on heavy loaders provides the actual memory headroom
    we need without changing dtypes.

    The `_KEY_COLUMN_RE`, ratio_threshold, and max_unique parameters are
    kept for reference / future re-enablement under a feature flag — they
    document the rules we'd reapply if categorical encoding ever returns.
    """
    return df


# malloc_trim hint after eviction — tells glibc to return freed heap pages
# to the OS. Without this, RSS often stays high even after the DataFrame is
# garbage-collected, defeating the purpose of the TTL.
def _malloc_trim():
    try:
        import ctypes
        ctypes.CDLL("libc.so.6").malloc_trim(0)
    except Exception:
        pass


class _TTLEntry:
    """Single-value TTL cache, thread-safe, with touch-on-access."""

    def __init__(self, ttl_seconds):
        self.ttl = ttl_seconds
        self._df = None
        self._expiry = 0.0
        self._lock = threading.Lock()

    def get_or_load(self, loader):
        # Fast path — no need to lock if already populated and unexpired.
        df = self._df
        if df is not None and _time.monotonic() < self._expiry:
            self._expiry = _time.monotonic() + self.ttl
            return df
        with self._lock:
            df = self._df
            now = _time.monotonic()
            if df is not None and now < self._expiry:
                self._expiry = now + self.ttl
                return df
            df = loader()
            self._df = df
            self._expiry = _time.monotonic() + self.ttl
            return df

    def maybe_evict(self):
        """Drop the held DataFrame if its TTL has expired. Returns True if evicted."""
        if self._df is None:
            return False
        if _time.monotonic() < self._expiry:
            return False
        with self._lock:
            if self._df is not None and _time.monotonic() >= self._expiry:
                self._df = None
                return True
        return False

    def clear(self):
        with self._lock:
            self._df = None
            self._expiry = 0.0


_TTL_REGISTRY = []  # all _TTLEntry / _TTLDictEntry instances, for the sweeper


class _TTLDictEntry:
    """Touch-on-access TTL eviction for an externally-owned dict cache.

    Used for derived caches that hold multiple correlated values
    (e.g., {"df": ..., "gap_evt": ..., "fd_evt": ...}). Caller calls .touch()
    on every cache hit or populate so the TTL window resets on activity.
    The sweeper resets all values to None after the TTL expires.
    """

    def __init__(self, cache_dict, ttl_seconds):
        self.cache = cache_dict
        self.ttl = ttl_seconds
        self._expiry = 0.0
        self._lock = threading.Lock()

    def touch(self):
        self._expiry = _time.monotonic() + self.ttl

    def maybe_evict(self):
        if not any(v is not None for v in self.cache.values()):
            return False
        if _time.monotonic() < self._expiry:
            return False
        with self._lock:
            if _time.monotonic() < self._expiry:
                return False
            for k in list(self.cache.keys()):
                self.cache[k] = None
            return True


def register_ttl_dict(cache_dict, ttl_seconds=None):
    """Register a dict-style cache for TTL eviction by the global sweeper.

    Returns a _TTLDictEntry — callers must invoke `.touch()` on each cache
    hit or write so the TTL window resets on activity. Without touch the
    sweeper will evict on the next pass after `ttl_seconds`.
    """
    if ttl_seconds is None:
        env_ttl = os.environ.get("LOADER_TTL_SECONDS", "").strip()
        ttl_seconds = int(env_ttl) if env_ttl.isdigit() else 1800
    entry = _TTLDictEntry(cache_dict, ttl_seconds)
    _TTL_REGISTRY.append(entry)
    return entry


def _ttl_cache(ttl_seconds=1800):
    """Decorator: TTL-cache the result of a no-arg function.

    Default TTL is 30 minutes. After expiry the next call re-runs the
    underlying loader (which itself reads the parquet cache off disk in
    1-2s — much cheaper than holding ~500MB in RAM 24/7).
    """
    # Allow override via env so we can tune without code change.
    env_ttl = os.environ.get("LOADER_TTL_SECONDS", "").strip()
    if env_ttl.isdigit():
        ttl_seconds = int(env_ttl)

    def deco(fn):
        entry = _TTLEntry(ttl_seconds)
        _TTL_REGISTRY.append(entry)

        def wrapper():
            return entry.get_or_load(fn)

        wrapper.cache_clear = entry.clear
        wrapper._ttl_entry = entry
        return wrapper

    return deco


def _ttl_sweep_loop(interval_seconds=300):
    """Background thread: periodically evict expired TTL entries and trim heap.

    Without an active sweeper, an entry stays in memory until the next time
    its loader is called. For datasets that go idle for hours, the sweeper
    is what actually frees the pages.
    """
    while True:
        try:
            _time.sleep(interval_seconds)
            evicted = sum(1 for e in _TTL_REGISTRY if e.maybe_evict())
            if evicted:
                gc.collect()
                _malloc_trim()
        except Exception:
            # Sweeper must never crash the worker thread.
            continue


# Start the sweeper exactly once per process.
_SWEEPER_STARTED = False
_SWEEPER_LOCK = threading.Lock()


def _start_sweeper_once():
    global _SWEEPER_STARTED
    if _SWEEPER_STARTED:
        return
    with _SWEEPER_LOCK:
        if _SWEEPER_STARTED:
            return
        # Disable in test/profile contexts via env if needed.
        if os.environ.get("LOADER_TTL_DISABLE_SWEEPER", "").strip().lower() in ("1", "true", "yes"):
            _SWEEPER_STARTED = True
            return
        t = threading.Thread(
            target=_ttl_sweep_loop,
            name="loader-ttl-sweeper",
            daemon=True,
        )
        t.start()
        _SWEEPER_STARTED = True


_start_sweeper_once()


# ---------------------------------------------------------------------------
# Parquet cache — avoids re-parsing CSVs on every app restart.
# The cache dir is created lazily; each dataset gets a .parquet file that is
# invalidated when any source CSV is newer.
# ---------------------------------------------------------------------------

def _parquet_cache_path(name):
    """Return the parquet cache file path for a dataset name."""
    DATA_CACHE.mkdir(exist_ok=True)
    return DATA_CACHE / f"{name}.parquet"


# Bump when the on-disk parquet format changes (dtype shifts, schema changes,
# etc.) — old caches with mismatched signatures get rebuilt on next load.
_PARQUET_FORMAT_VERSION = "v4-no-categorical"


def _source_signature(source_paths, extra=""):
    """A stable fingerprint of the source files (size + ns mtime).

    ``extra`` lets callers fold non-file state into the signature (e.g. a
    DB-backed override fingerprint), so the cache invalidates when that
    state changes even though the underlying CSV/xlsx hasn't.
    """
    parts = [f"fmt={_PARQUET_FORMAT_VERSION}"]
    for p in sorted(source_paths or [], key=lambda x: str(x)):
        if p.exists():
            st = p.stat()
            parts.append(f"{p.name}|{st.st_size}|{st.st_mtime_ns}")
        else:
            parts.append(f"{p.name}|missing")
    if extra:
        parts.append(f"extra={extra}")
    return "|".join(parts)


def _read_parquet_cache(name, source_paths, extra=""):
    """Return the cached DataFrame iff its sidecar matches the live sources.

    The mtime of the parquet file itself is unreliable: docker layer COPYs
    and tarball extractions reset mtimes in ways that don't track content.
    Instead we write a `<name>.sig` sidecar at parquet-write time and
    compare that to a freshly-computed signature here.
    """
    pq = _parquet_cache_path(name)
    sig_file = pq.with_suffix(".sig")
    if not pq.exists() or not sig_file.exists():
        return None
    try:
        if sig_file.read_text() == _source_signature(source_paths, extra):
            return pd.read_parquet(pq, engine="pyarrow")
    except Exception:
        pass
    return None


def _write_parquet_cache(name, df, source_paths=None, extra=""):
    """Write a DataFrame to the parquet cache and stamp a signature sidecar."""
    if df.empty:
        return
    try:
        pq = _parquet_cache_path(name)
        df.to_parquet(pq, engine="pyarrow", compression="zstd")
        sig_file = pq.with_suffix(".sig")
        if source_paths is not None:
            sig_file.write_text(_source_signature(source_paths, extra))
        elif sig_file.exists():
            sig_file.unlink()
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

@_ttl_cache()
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


@_ttl_cache()
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
    df = _categorize_low_cardinality(df)
    _write_parquet_cache("TreatmentDetail", df, _src)
    return df


@_ttl_cache()
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
    _write_parquet_cache("DailyVolumePast", df, [src])
    return df


@_ttl_cache()
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


@_ttl_cache()
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


def _availability_r2_config():
    """Return (account_id, access_key, secret_key, bucket, key) or None.

    All five must be present for the live-refresh path to be considered
    configured. Falls back to the bundled R2 creds (R2_ACCOUNT_ID etc.)
    so a single R2 token can cover both the daily tarball and the live
    Availability feed; bucket/key default to the same conventions.
    """
    account_id = os.environ.get("R2_ACCOUNT_ID", "").strip()
    access_key = os.environ.get("R2_ACCESS_KEY_ID", "").strip()
    secret_key = os.environ.get("R2_SECRET_ACCESS_KEY", "").strip()
    bucket = (
        os.environ.get("R2_AVAILABILITY_BUCKET", "").strip()
        or os.environ.get("R2_BUCKET", "").strip()
        or "radiantcare-sanitized"
    )
    key = os.environ.get("R2_AVAILABILITY_KEY", "").strip()
    if not (account_id and access_key and secret_key and bucket and key):
        return None
    return account_id, access_key, secret_key, bucket, key


def _load_availability_from_r2():
    """Pull the latest Availability CSV from R2. Returns DataFrame or None.

    Returns None on any failure (missing config, network error, parse error)
    so the caller can fall back to disk. Errors are printed once and not
    raised — a stale-but-served disk snapshot beats a 500 page.
    """
    cfg = _availability_r2_config()
    if cfg is None:
        return None
    account_id, access_key, secret_key, bucket, key = cfg
    try:
        import boto3
        from botocore.config import Config as _BotoConfig
        from io import BytesIO

        endpoint = f"https://{account_id}.r2.cloudflarestorage.com"
        s3 = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name="auto",
            config=_BotoConfig(
                signature_version="s3v4",
                s3={"addressing_style": "path"},
                retries={"max_attempts": 2, "mode": "standard"},
                connect_timeout=10,
                read_timeout=30,
            ),
        )
        resp = s3.get_object(Bucket=bucket, Key=key)
        body = resp["Body"].read()
        # Try pyarrow first (matches _read_csv_safe semantics on bytes).
        try:
            df = pd.read_csv(BytesIO(body), encoding="utf-8-sig", engine="pyarrow")
        except Exception:
            df = pd.read_csv(
                BytesIO(body), encoding="utf-8-sig",
                on_bad_lines="skip", low_memory=False,
            )
        # Drop trailing all-NaN rows (ARIA footer artifacts).
        while len(df) > 0 and df.iloc[-1].isna().all():
            df = df.iloc[:-1]
        return df
    except Exception as exc:
        print(f"[availability] R2 fetch failed (key={key}): {exc}")
        return None


def _load_availability_from_disk():
    """Read Availability from the local Complete folder.

    Single canonical Availability.csv — full-refresh snapshot, not
    date-suffixed.
    """
    canonical = DATA_COMPLETE / "Availability.csv"
    if canonical.exists():
        return _read_csv_safe(canonical)
    return pd.DataFrame()


# Availability gets its own short TTL (default 5 min) — independent of
# LOADER_TTL_SECONDS, which targets the heavy clinical datasets. Override
# with AVAILABILITY_TTL_SECONDS for tuning the live-feed cache window.
_AVAILABILITY_TTL = int(
    os.environ.get("AVAILABILITY_TTL_SECONDS", "").strip() or "300"
)
_AVAILABILITY_ENTRY = _TTLEntry(_AVAILABILITY_TTL)
_TTL_REGISTRY.append(_AVAILABILITY_ENTRY)


def _availability_inner():
    df = _load_availability_from_r2()
    if df is None or df.empty:
        df = _load_availability_from_disk()
    if df is None or df.empty:
        return pd.DataFrame()
    df = _normalize_columns(df, {"DepartmentName": "Department"})
    df = _clean_department(df)
    df = _parse_dates(df, ["AppointmentDateTime", "ScheduledEndTime"])
    if "AppointmentDateTime" in df.columns:
        df["SlotDate"] = df["AppointmentDateTime"].dt.normalize()
    # AppointmentNotes is only consulted as a boolean (is the slot blocked /
    # reserved by the front desk?) — the text itself is never rendered.
    # Derive HasNote here and drop the source column so neither this process
    # nor anything downstream ever holds the free-text PHI.
    if "AppointmentNotes" in df.columns:
        df["HasNote"] = (
            df["AppointmentNotes"].fillna("").astype(str).str.strip() != ""
        )
        df = df.drop(columns=["AppointmentNotes"])
    elif "HasNote" not in df.columns:
        df["HasNote"] = False
    return df


def load_availability():
    """Load the latest Availability snapshot.

    Two-tier source resolution:
      1. R2 live feed — when R2_AVAILABILITY_KEY (and R2 creds) are set,
         pulls the canonical CSV from R2 on every cache miss. Power Automate
         overwrites that object on each email export (~30-60 min cadence).
      2. Disk — single Availability.csv from the Complete folder
         (full-refresh snapshot, not date-suffixed).

    Cached for AVAILABILITY_TTL_SECONDS (default 300s). The TTL sweeper
    handles eviction so an idle dashboard isn't holding a stale snapshot
    indefinitely.
    """
    return _AVAILABILITY_ENTRY.get_or_load(_availability_inner)


load_availability.cache_clear = _AVAILABILITY_ENTRY.clear


# ---------------------------------------------------------------------------
# ScheduleUpcoming — successor to Availability for the forward-looking
# schedule views (Home, Operations, Scheduling). Same shape concept (one
# row per slot, two-month forward window) but covers BOTH open holds and
# already-booked appointments in a single feed, and with no AppointmentNotes
# (no PHI) so the path is simpler:
#
#   - Local: Complete/ScheduleUpcoming.csv (full-refresh snapshot)
#   - Production: ARIA writes the CSV directly to R2; the loader fetches
#     it on each cache miss. There is NO sanitize step and NO inclusion
#     in the daily tarball — the live R2 object is the source of truth.
# ---------------------------------------------------------------------------


def _schedule_upcoming_r2_config():
    """Return (account_id, access_key, secret_key, bucket, key) or None.

    R2_SCHEDULE_UPCOMING_KEY is required to opt into the live path; the
    bucket falls back to R2_BUCKET, and the standard R2 creds cover auth.
    """
    account_id = os.environ.get("R2_ACCOUNT_ID", "").strip()
    access_key = os.environ.get("R2_ACCESS_KEY_ID", "").strip()
    secret_key = os.environ.get("R2_SECRET_ACCESS_KEY", "").strip()
    bucket = (
        os.environ.get("R2_SCHEDULE_UPCOMING_BUCKET", "").strip()
        or os.environ.get("R2_BUCKET", "").strip()
        or "radiantcare-sanitized"
    )
    key = os.environ.get("R2_SCHEDULE_UPCOMING_KEY", "").strip()
    if not (account_id and access_key and secret_key and bucket and key):
        return None
    return account_id, access_key, secret_key, bucket, key


# Tracks the source + last-modified timestamp of the most recent successful
# ScheduleUpcoming load, so the scheduling page can show a "Last updated" hint.
# Set by whichever fetch path (R2 / disk) actually returned data.
_SCHEDULE_UPCOMING_META = {"last_modified": None, "source": None}


def _load_schedule_upcoming_from_r2():
    """Pull the latest ScheduleUpcoming CSV from R2. Returns DataFrame or None."""
    cfg = _schedule_upcoming_r2_config()
    if cfg is None:
        return None
    account_id, access_key, secret_key, bucket, key = cfg
    try:
        import boto3
        from botocore.config import Config as _BotoConfig
        from io import BytesIO

        endpoint = f"https://{account_id}.r2.cloudflarestorage.com"
        s3 = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name="auto",
            config=_BotoConfig(
                signature_version="s3v4",
                s3={"addressing_style": "path"},
                retries={"max_attempts": 2, "mode": "standard"},
                connect_timeout=10,
                read_timeout=30,
            ),
        )
        resp = s3.get_object(Bucket=bucket, Key=key)
        body = resp["Body"].read()
        last_modified = resp.get("LastModified")  # tz-aware UTC
        try:
            df = pd.read_csv(BytesIO(body), encoding="utf-8-sig", engine="pyarrow")
        except Exception:
            df = pd.read_csv(
                BytesIO(body), encoding="utf-8-sig",
                on_bad_lines="skip", low_memory=False,
            )
        while len(df) > 0 and df.iloc[-1].isna().all():
            df = df.iloc[:-1]
        _SCHEDULE_UPCOMING_META["last_modified"] = last_modified
        _SCHEDULE_UPCOMING_META["source"] = "r2"
        return df
    except Exception as exc:
        print(f"[schedule_upcoming] R2 fetch failed (key={key}): {exc}")
        return None


def _load_schedule_upcoming_from_disk():
    """Read ScheduleUpcoming.csv from the local Complete folder.

    In PHI_MODE the active DATA_COMPLETE points to the sanitized tree, but
    ScheduleUpcoming bypasses sanitize entirely (the dataset has no PHI —
    no patient names, MRNs, or free-text notes — so there's nothing to
    redact). Falling back to the raw OneDrive Complete folder lets local
    PHI-mode dev work without standing up the production R2 path.
    """
    from config.settings import DATA_DIR_RAW
    candidates = [
        DATA_COMPLETE / "ScheduleUpcoming.csv",
        DATA_DIR_RAW / "Complete" / "ScheduleUpcoming.csv",
    ]
    for path in candidates:
        if path.exists():
            mtime = pd.Timestamp(path.stat().st_mtime, unit="s", tz="UTC")
            _SCHEDULE_UPCOMING_META["last_modified"] = mtime
            _SCHEDULE_UPCOMING_META["source"] = f"disk:{path.name}"
            return _read_csv_safe(path)
    return pd.DataFrame()


def schedule_upcoming_last_modified():
    """Return (timestamp, source_label) for the most recent successful load.

    Timestamp is a tz-aware pandas Timestamp in UTC, or None if no fetch
    has succeeded yet. Source is "r2" or "disk:<filename>".
    """
    return (
        _SCHEDULE_UPCOMING_META["last_modified"],
        _SCHEDULE_UPCOMING_META["source"],
    )


_SCHEDULE_UPCOMING_TTL = int(
    os.environ.get("SCHEDULE_UPCOMING_TTL_SECONDS", "").strip()
    or os.environ.get("AVAILABILITY_TTL_SECONDS", "").strip()
    or "300"
)
_SCHEDULE_UPCOMING_ENTRY = _TTLEntry(_SCHEDULE_UPCOMING_TTL)
_TTL_REGISTRY.append(_SCHEDULE_UPCOMING_ENTRY)


def _schedule_upcoming_inner():
    df = _load_schedule_upcoming_from_r2()
    if df is None or df.empty:
        df = _load_schedule_upcoming_from_disk()
    if df is None or df.empty:
        return pd.DataFrame()
    # Normalize source column names to the legacy Availability schema so
    # downstream consumers don't need to learn a second vocabulary:
    #   ActivityCategory  → Category   (Exam / Simulation)
    #   ScheduledDateTime → AppointmentDateTime
    #   DepartmentName    → Department
    df = _normalize_columns(df, {
        "DepartmentName": "Department",
        "ActivityCategory": "Category",
        "ScheduledDateTime": "AppointmentDateTime",
    })
    df = _clean_department(df)
    df = _parse_dates(df, ["AppointmentDateTime", "ScheduledEndTime"])
    if "AppointmentDateTime" in df.columns:
        df["SlotDate"] = df["AppointmentDateTime"].dt.normalize()
    # Cancelled bookings: usually the underlying HOLD slot is still in
    # the extract as a separate Available row (so the cancellation row is
    # redundant and we drop it). But sometimes staff doesn't recreate a
    # placeholder open slot when an appointment cancels — in that case
    # the cancelled row is the ONLY signal that the time block exists,
    # and we restore it as an Available HOLD so the slot doesn't vanish
    # from open-capacity views.
    #
    # Match key: (AppointmentDateTime, AssignedResource) — "is there any
    # non-cancelled row at this time slot for this resource?"
    if "ActivityStatus" in df.columns:
        cancelled_mask = df["ActivityStatus"].astype(str).str.lower() == "cancelled"
        cancelled = df[cancelled_mask].copy()
        rest = df[~cancelled_mask].copy()
        if not cancelled.empty:
            rest_keys = set(zip(
                rest["AppointmentDateTime"],
                rest["AssignedResource"].astype(str),
            ))
            keep = [
                (dt, str(res)) not in rest_keys
                for dt, res in zip(
                    cancelled["AppointmentDateTime"],
                    cancelled["AssignedResource"],
                )
            ]
            survivors = cancelled[keep].copy()
            if not survivors.empty:
                # Restore as Available. Remap ActivityName to its HOLD
                # equivalent so the scheduling page's HOLD-only filter
                # still matches.
                _hold_name_map = {
                    "Consult": "HOLD CONSULT",
                    "Re-eval": "HOLD RE EVAL/2 FOLLOW UPS",
                    "Follow-Up": "HOLD RE EVAL/2 FOLLOW UPS",
                }
                def _to_hold(row):
                    if str(row.get("WorkflowType", "")).lower() == "simulation":
                        return "HOLD SIM TIME"
                    return _hold_name_map.get(row["ActivityName"], row["ActivityName"])
                survivors["ActivityName"] = survivors.apply(_to_hold, axis=1)
                survivors["BookingStatus"] = "Available"
                survivors["ActivityStatus"] = pd.NA
            df = pd.concat([rest, survivors], ignore_index=True)
    # Drop the daily 8:00 AM 30-minute HOLD SIM TIME placeholder that
    # exists only to warm the linac — it's not a bookable slot and would
    # otherwise inflate every "open sim capacity" count and clutter the
    # scheduling calendar.
    if "AppointmentDateTime" in df.columns and "Category" in df.columns:
        is_warmup = (
            (df["Category"].astype(str).str.contains("Simulation", case=False, na=False))
            & (df.get("ActivityName", "").astype(str) == "HOLD SIM TIME")
            & (df["AppointmentDateTime"].dt.hour == 8)
            & (df["AppointmentDateTime"].dt.minute == 0)
            & (df.get("DurationMinutes", 0).fillna(0).astype(int) == 30)
        )
        df = df[~is_warmup]
    # ScheduleUpcoming includes BOTH open holds (BookingStatus="Available")
    # and already-booked appointments (BookingStatus="Booked"). Map that
    # into the legacy SlotTaken Yes/No vocabulary so existing filters
    # (`avail[avail["SlotTaken"] != "Yes"]`) keep meaning "open only" —
    # otherwise booked rows would slip through with SlotTaken=NaN.
    if "BookingStatus" in df.columns:
        booked = df["BookingStatus"].astype(str).str.lower() == "booked"
        df["SlotTaken"] = booked.map({True: "Yes", False: "No"})
    elif "SlotTaken" not in df.columns:
        df["SlotTaken"] = "No"
    # No AppointmentNotes column on this feed — the scheduling page's
    # _blocked_flag() helper falls back to all-False when neither HasNote
    # nor AppointmentNotes is present, which is the correct behavior.
    df["HasNote"] = False
    return df.reset_index(drop=True)


def load_schedule_upcoming():
    """Load the latest ScheduleUpcoming snapshot.

    Successor to load_availability() for forward-looking views. Two-tier
    source resolution:

      1. R2 live feed — when R2_SCHEDULE_UPCOMING_KEY (and R2 creds) are
         set, pulls the canonical CSV from R2 on every cache miss. ARIA
         writes that object directly (no sanitize / no tarball).
      2. Disk — single Complete/ScheduleUpcoming.csv (full-refresh
         snapshot, not date-suffixed).

    Cached for SCHEDULE_UPCOMING_TTL_SECONDS (default 300s; falls back to
    AVAILABILITY_TTL_SECONDS for tuning parity, then 300s). The TTL
    sweeper handles eviction so an idle dashboard isn't holding a stale
    snapshot indefinitely.

    Returned columns are normalized to the legacy Availability schema —
    Department / Category / AppointmentDateTime / SlotDate / SlotTaken
    (Yes/No, derived from BookingStatus) — plus the new BookingStatus,
    WorkflowType, ActivityStatus columns when downstream code wants them.
    """
    return _SCHEDULE_UPCOMING_ENTRY.get_or_load(_schedule_upcoming_inner)


load_schedule_upcoming.cache_clear = _SCHEDULE_UPCOMING_ENTRY.clear


@_ttl_cache()
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
    _write_parquet_cache("ClinicVisits", df, _src)
    return df


@_ttl_cache()
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
    _write_parquet_cache("Simulations", df, _src)
    return df


@_ttl_cache()
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
    df = _categorize_low_cardinality(df)
    _write_parquet_cache("Workflow", df, _src)
    return df


@_ttl_cache()
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
    _write_parquet_cache("Tasks", df, [_src])
    return df


@_ttl_cache()
def load_otvs():
    """Load OTV Audit.csv."""
    df = _read_csv_safe(DATA_COMPLETE / "OTV Audit.csv")
    df = _clean_department(df)
    df = _parse_dates(df, ["FirstTreatmentDate", "LastTreatmentDate"])
    if "UniqueRowID" in df.columns:
        df = df.drop_duplicates(subset=["UniqueRowID"], keep="last")
    return df


@_ttl_cache()
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
    _write_parquet_cache("WeeklyVisits", df, _src)
    return df


@_ttl_cache()
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
    _write_parquet_cache("Courses", df, _src)
    return df


@_ttl_cache()
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
    _write_parquet_cache("Plans", df, _src)
    return df


@_ttl_cache()
def load_machines():
    """Load Machine Errors.csv.

    No Date column — uses TreatmentStartTime/TreatmentEndTime.
    """
    df = _read_csv_safe(DATA_COMPLETE / "Machine Errors.csv")
    df = _normalize_columns(df, {"PatientName": "PatientFullName"})
    df = _parse_dates(df, ["TreatmentStartTime", "TreatmentEndTime"])
    return df


@_ttl_cache()
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
    # Normalise mixed-type object columns to clean strings in-place — the
    # previous version made a full df.copy() just for the parquet write, which
    # transiently doubled RAM on a 366MB frame.
    for col in df.columns:
        if df[col].dtype == object:
            df[col] = df[col].astype(str).replace({"None": "", "nan": ""})
    df = _categorize_low_cardinality(df)
    _write_parquet_cache("DowntimeGaps", df, _src)
    return df


_FIELDS_USECOLS = [
    "RecordType", "Site", "Machine", "ActivityDate", "StartTime", "EndTime",
    "DurationSeconds", "PatientId", "PatientName", "CourseId", "FieldId",
    "FractionNumber", "PlannedMU", "DeliveredMU", "FieldStatus",
    "TerminationStatus", "FieldCategory", "ImageType",
]


def _fields_files():
    """Return MachineDowntimeFields incremental CSVs sorted oldest→newest."""
    folder = DATA_INCREMENTAL / "MachineDowntimeFields"
    return sorted(
        folder.glob("Machine Downtime - Fields_*.csv"),
        key=lambda f: f.stem.rsplit("_", 1)[-1],
    )


@lru_cache(maxsize=1)
def _downtime_fields_date_index():
    """Map date_str → newest source file containing that date.

    Built once per process and persisted to disk (`.data_cache/MachineDowntimeFields.idx.json`)
    so it survives container restarts. Invalidated when the source file
    list / sizes / mtimes change.

    Why: load_downtime_fields_for_date used to linearly scan all 17 files
    newest→oldest until it found a match. For dates outside the latest
    file that's 3-6s of wasted CSV parsing per drill-down. With the index
    in place, we open exactly one file per date.
    """
    import json

    files = _fields_files()
    if not files:
        return {}

    sig = _source_signature(files)
    idx_path = _parquet_cache_path("MachineDowntimeFields.idx").with_suffix(".json")

    # Try the disk cache first
    if idx_path.exists():
        try:
            payload = json.loads(idx_path.read_text())
            if payload.get("sig") == sig:
                # Resolve file names back to absolute paths
                by_name = {p.name: p for p in files}
                return {d: by_name[n] for d, n in payload.get("index", {}).items()
                        if n in by_name}
        except Exception:
            pass

    # Source files have changed — wipe stale per-date parquet sidecars so
    # subsequent loads rebuild them with current data.
    import shutil
    per_date_dir = _fields_per_date_parquet("dummy").parent
    if per_date_dir.exists():
        try:
            shutil.rmtree(per_date_dir)
        except Exception:
            pass

    # Build: walk files newest→oldest, record each date the first time we see it
    index = {}
    for fpath in reversed(files):
        try:
            dates = pd.read_csv(
                fpath, usecols=["ActivityDate"],
                encoding="utf-8-sig", engine="pyarrow",
            )["ActivityDate"]
        except Exception:
            try:
                dates = pd.read_csv(
                    fpath, usecols=["ActivityDate"],
                    encoding="utf-8-sig", on_bad_lines="skip", low_memory=False,
                )["ActivityDate"]
            except Exception:
                continue
        for d in dates.dropna().unique():
            d = str(d)
            if d not in index:
                index[d] = fpath

    # Persist
    try:
        idx_path.parent.mkdir(parents=True, exist_ok=True)
        idx_path.write_text(json.dumps({
            "sig": sig,
            "index": {d: f.name for d, f in index.items()},
        }))
    except Exception:
        pass

    return index


def _fields_per_date_parquet(target_date_safe):
    """Per-date parquet cache path for downtime fields rows."""
    return DATA_CACHE / "MachineDowntimeFields_per_date" / f"{target_date_safe}.parquet"


@lru_cache(maxsize=256)
def load_downtime_fields_for_date(target_date):
    """Load Machine Downtime - Fields, filtered to a single date.

    Two-tier cache:
      1. Per-date parquet on disk (~few KB each) — survives restarts and
         skips CSV parsing entirely. Invalidated by index signature change.
      2. lru_cache(256) in process — repeated calls within a session are O(1).

    The index built by `_downtime_fields_date_index()` tells us which file
    a date lives in. If the date isn't in the index AND the index is
    populated, we know no file has data for that date → return empty
    immediately (this used to trigger a 5s linear scan of all 17 files).
    """
    if hasattr(target_date, "strftime"):
        target_date = target_date.strftime("%m/%d/%Y")

    wanted = set(_FIELDS_USECOLS)
    usecols = lambda c: c in wanted

    # Tier 1: per-date parquet sidecar
    safe = target_date.replace("/", "-")
    pq_path = _fields_per_date_parquet(safe)
    if pq_path.exists():
        try:
            return pd.read_parquet(pq_path, engine="pyarrow")
        except Exception:
            pass

    def _read(fpath):
        try:
            return pd.read_csv(fpath, usecols=usecols, encoding="utf-8-sig",
                               engine="pyarrow")
        except Exception:
            return pd.read_csv(fpath, usecols=usecols, encoding="utf-8-sig",
                               on_bad_lines="skip", low_memory=False)

    def _persist(matched):
        try:
            pq_path.parent.mkdir(parents=True, exist_ok=True)
            matched.to_parquet(pq_path, engine="pyarrow", compression="zstd")
        except Exception:
            pass

    # Fast path: index lookup
    index = _downtime_fields_date_index()
    if index:
        fpath = index.get(target_date)
        if fpath is None:
            # Index is built and date is absent — no file has data for it.
            # Cache the empty result so we don't re-check.
            empty = pd.DataFrame(columns=_FIELDS_USECOLS)
            _persist(empty)
            return empty
        if fpath.exists():
            df = _read(fpath)
            matched = df[df["ActivityDate"] == target_date].copy()
            _persist(matched)
            return matched

    # Fallback (e.g., index build failed): linear scan
    files = _fields_files()
    if not files:
        return pd.DataFrame(columns=_FIELDS_USECOLS)
    for fpath in reversed(files):
        df = _read(fpath)
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


@_ttl_cache()
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


@_ttl_cache()
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


@_ttl_cache()
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
    df = _categorize_low_cardinality(df)
    _write_parquet_cache("Billing", df, _src)
    return df


@_ttl_cache()
def load_pluvicto_workflow():
    """Load Pluvicto-specific workflow chains from Workflow CSV.

    Filters Workflow data to ModalityType == 'Pluvicto' for the Procedures
    page Pluvicto patient queue grid.
    """
    wf = load_workflow()
    if "ModalityType" not in wf.columns:
        return pd.DataFrame()
    # ModalityType is now a category; .str works on the underlying values
    # but we cast to string for the comparison to avoid category-mismatch issues.
    mask = wf["ModalityType"].astype(str).str.strip().str.upper() == "PLUVICTO"
    return wf[mask].copy()


@_ttl_cache()
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


@_ttl_cache()
def load_cpt_audit():
    """Load 2026 CPT Delivery Audit.csv."""
    df = _read_csv_safe(DATA_COMPLETE / "2026 CPT Delivery Audit.csv")
    df = _clean_department(df)
    df = _parse_dates(df, ["TreatmentDate"])
    return df


@_ttl_cache()
def load_patients():
    """Load Lookup - Patients.csv."""
    df = _read_csv_safe(DATA_LOOKUP / "Lookup - Patients.csv")
    return df


@_ttl_cache()
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
    # Fold the referring-overrides table fingerprint into the cache signature
    # so saving an override (which doesn't touch the source xlsx) still busts
    # the parquet cache on the next load.
    # The v2 suffix forces a one-time rebuild on deploy: prior to this version
    # the override-apply pass silently swallowed a ValueError on malformed
    # DoctorIds (e.g. "1234567890/Kaise"), so the cached parquets shipped from
    # disk had institution renames missing.
    try:
        from data.reviews_db import get_referring_overrides_fingerprint
        _overrides_fp = "v2|" + get_referring_overrides_fingerprint()
    except Exception:
        _overrides_fp = "v2|"
    cached = _read_parquet_cache("Referrals", src_paths, extra=_overrides_fp)
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
        df["Referred by Department"] = dept
        # Drop self-referrals (RadiantCare → RadiantCare). These are internal
        # handoffs, not true referrals, and distort all funnel/source metrics.
        self_ref_mask = dept.str.contains(r"PRCS.*RADIANTCARE", case=False, na=False)
        if self_ref_mask.any():
            df = df.loc[~self_ref_mask].reset_index(drop=True)

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

            # Normalize DoctorSpecialty via the shared specialty module.
            # All canonicalization (variants, regex fallback, DEPT_BUCKETS
            # roll-ups) lives in config/specialties.py — single source of
            # truth shared with utils/npi_lookup.py and the RPM grid.
            from config.specialties import (
                normalize_specialty as _norm_spec,
                infer_from_department as _infer_dept_spec,
                bucket_to_dept as _bucket_to_dept,
            )
            if "DoctorSpecialty" in df.columns:
                df["DoctorSpecialty"] = (
                    df["DoctorSpecialty"]
                    .map(lambda v: _norm_spec(v) if isinstance(v, str) else v)
                    .map(lambda v: _bucket_to_dept(v) if isinstance(v, str) else v)
                )

            # Build DeptSpecialty for all rows from "Referred by Department".
            # Dept-derived specialty is often more accurate than provider
            # specialty for referral-source analysis.
            if "Referred by Department" in df.columns:
                df["DeptSpecialty"] = (
                    df["Referred by Department"]
                    .fillna("")
                    .map(_infer_dept_spec)
                    .map(lambda v: _bucket_to_dept(v) if isinstance(v, str) else v)
                )

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
                # Build composite key in the dataframe to match overrides.
                # Prefer the proper 10-digit NPI from "Referred By Prov NPI"
                # (the float column ARIA gives us); fall back to a cleaned
                # DoctorId prefix for providers with only a state license or
                # other non-NPI ID. Mirrors _build_rpm_grid_data so override
                # rows the user creates in the manager (keyed on the NPI shown
                # there) actually match here.
                # The old code did .astype(int) on DoctorId, which raised
                # ValueError on values like "1234567890/Kaise" and was caught
                # by the broad except → ALL overrides silently skipped for the
                # whole dataframe.
                _npi_from_col = df.get(
                    "Referred By Prov NPI", pd.Series(pd.NA, index=df.index)
                ).apply(
                    lambda v: str(int(v)) if pd.notna(v) and float(v).is_integer() else ""
                )
                _npi_from_did = (df["DoctorId"].astype(str).str.strip()
                                 .str.split("/", n=1).str[0].str.strip())
                _npi_from_did = _npi_from_did.where(
                    _npi_from_did.str.lower() != "nan", ""
                )
                _npi_col = _npi_from_col.where(_npi_from_col != "", _npi_from_did)
                _city = df.get("Referring Provider City", pd.Series("", index=df.index)).fillna("").astype(str)
                _state = df.get("Referring Provider State", pd.Series("", index=df.index)).fillna("").astype(str)
                _zip = df.get("Referring Provider Zip Code", pd.Series("", index=df.index)).fillna("").astype(str)
                _ak = pd.Series(
                    [_addr_key(c, s, z) for c, s, z in zip(_city, _state, _zip)],
                    index=df.index,
                )
                _row_key = _npi_col + "|" + _ak
                from config.specialties import (
                    normalize_specialty as _norm_ov_spec,
                    bucket_to_dept as _bucket_ov_spec,
                )
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
                        # Normalize stored override value through the same pipeline
                        # used for raw data — protects against legacy loader-canonical
                        # values lingering in the DB before migration.
                        _spec = _bucket_ov_spec(_norm_ov_spec(vals["specialty"]))
                        df.loc[idx, "DoctorSpecialty"] = _spec
                        if "DeptSpecialty" in df.columns:
                            df.loc[idx, "DeptSpecialty"] = _spec
                    if vals.get("institution"):
                        df.loc[idx, "DoctorInstitution"] = vals["institution"]
        except Exception:
            pass

    # --- Apply institution aliases (global string remap) ---
    # When the user renames an institution in the manager, we record the
    # mapping in `institution_aliases`. Applying it here rewrites every raw
    # CSV `DoctorInstitution` value that matches a stale alias so the trend
    # chart and other consumers see the canonical name, regardless of whether
    # an exact-key override exists for each referral.
    if "DoctorInstitution" in df.columns:
        try:
            from data.reviews_db import get_institution_alias_map
            _alias_map = get_institution_alias_map()
            if _alias_map:
                df["DoctorInstitution"] = (
                    df["DoctorInstitution"].astype(object).map(
                        lambda v: _alias_map.get(v, v) if isinstance(v, str) else v
                    )
                )
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

    _write_parquet_cache("Referrals", df, src_paths, extra=_overrides_fp)
    return df


# Med-onc site departments (the five PRCS sites referrals go TO).
_MEDONC_SITES = ("LACEY", "CENTRALIA", "ABERDEEN", "YELM", "SHELTON")


@_ttl_cache()
def load_medonc_referrals():
    """Load the Medical Oncology (PRCS) Referrals Report Excel file.

    Source: Referrals_Report_PRCS_*.xlsx — referrals TO medical oncology
    across the five PRCS sites (Lacey, Centralia, Aberdeen, Yelm, Shelton).
    Used to analyze cross-referral patterns (which med-onc patients also
    reach RadiantCare) and to spot potential under-referral to rad-onc.

    Filters applied:
      - Drop rows with no oncologic diagnosis (`Onc Dx == "No onc dx"` or null)
      - Drop self-referrals from the same five med-onc sites (med-onc → med-onc)
      - Drop referrals from RadiantCare (rad-onc → med-onc handoffs are not
        the signal we care about here)

    Parses date columns and normalizes MRN to Int64 (joins to rad-onc data
    via load_referrals() MRN and clinic-visits PatientId).
    """
    import glob as _glob

    pattern = str(DATA_DIR / "Referrals_Report_PRCS_*.xlsx")
    matches = sorted(_glob.glob(pattern))
    if not matches:
        return pd.DataFrame()

    src_paths = [Path(m) for m in matches]
    cached = _read_parquet_cache("MedOncReferrals", src_paths)
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

    # Normalize MRN for joining to rad-onc data
    if "MRN" in df.columns:
        df["MRN"] = pd.to_numeric(df["MRN"], errors="coerce").astype("Int64")

    # --- Filter: non-oncologic diagnoses ---
    if "Onc Dx" in df.columns:
        has_onc = df["Onc Dx"].notna() & (df["Onc Dx"].astype(str).str.strip() != "No onc dx")
        df = df.loc[has_onc].reset_index(drop=True)

    # --- Filter: self-referrals (same med-onc sites) and RadiantCare referrals ---
    if "Referred by Department" in df.columns:
        # Strip "DO NOT USE - " prefix (same convention as load_referrals)
        df["Referred by Department"] = df["Referred by Department"].astype("string").str.replace(
            r"^DO NOT USE\s*-\s*", "", regex=True
        )
        by_dept = df["Referred by Department"].fillna("")
        sites_pat = "|".join(_MEDONC_SITES)
        self_ref = by_dept.str.contains(
            rf"PRCS\s+(?:{sites_pat})(?:\s|$)", case=False, regex=True, na=False
        )
        radcare = by_dept.str.contains("RADIANTCARE", case=False, na=False)
        df = df.loc[~(self_ref | radcare)].reset_index(drop=True)

    # --- Normalize "Referred to Department" to short site name ---
    if "Referred to Department" in df.columns:
        def _short_site(s):
            if pd.isna(s):
                return None
            s_upper = str(s).upper()
            for site in _MEDONC_SITES:
                if site in s_upper:
                    return site.title()
            return None
        df["ReferredToSite"] = df["Referred to Department"].map(_short_site)

    # Alias ICD-10 codes to "DiagnosisCodes" so the standard diagnosis
    # accordion filter (which expects comma-separated ICD-10s in a
    # "DiagnosisCodes" column) works on this dataset.
    if "ICD-10 Diagnosis Code" in df.columns:
        df["DiagnosisCodes"] = df["ICD-10 Diagnosis Code"]

    _write_parquet_cache("MedOncReferrals", df, src_paths)
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
