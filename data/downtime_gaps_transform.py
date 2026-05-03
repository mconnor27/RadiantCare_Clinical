"""Machine downtime gaps transformation pipeline.

Extracted from pages/machines.py so scripts/sanitize.py can pre-build the
parquet cache without importing Dash. The transform turns raw downtime gap
rows into:
  - df         : enriched gap rows (DowntimeType, LocalConfidence, EventNote)
  - gap_evt    : deduped gap/SOD/EOD events with interpolated minutes
  - fd_evt     : deduped FullDay events with interpolated minutes

All three frames are cached in-memory and on disk (parquet sidecar). Cache
invalidates whenever the source CSVs change OR this module changes.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_EVENT_KEYS = ("RowType", "Machine", "DowntimeDate", "GapStartTime")

_CONFIDENCE_ORDER = {"High": 3, "Medium": 2, "Low": 1}

_NOTE_TYPE_MAP = {
    "Machine Down": "Equipment Fault",
    "Component Down": "Equipment Fault",
    "Power": "Equipment Fault",
    "Varian Called": "Vendor Response",
    "Patient Redirected": "Patient Logistics",
}


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def _time_str_to_min(t):
    """Convert HH:MM:SS string to minutes from midnight."""
    if pd.isna(t):
        return None
    s = str(t)[:5]
    parts = s.split(":")
    try:
        return int(parts[0]) * 60 + int(parts[1])
    except (ValueError, IndexError):
        return None


def _get_holidays_set():
    """Get set of holiday dates (schedule-derived + static fallback)."""
    from utils.holidays import get_holidays
    try:
        return get_holidays()
    except Exception:
        return set()


# ---------------------------------------------------------------------------
# Dedup + per-row enrichment
# ---------------------------------------------------------------------------

def _dedup_events(df):
    """Deduplicate to one row per gap event for event-level aggregation.

    The SQL output is dual-grain:
      - A-branch: one row per affected patient (PatientId populated)
      - B-branch: one row per event with no patients (PatientId NULL)

    Event-level columns (GapMinutes, CancelledInGap, MachineErrorsNearGap,
    etc.) carry the same value on every A-branch row for a given gap. Summing
    without deduplication inflates counts by the number of affected patients.

    Propagation rules applied before collapsing:
      - DowntimeNoteMatch: best (first non-null) from any A-branch row
      - LocalConfidence: highest severity from any row in the event group
    """
    if df.empty:
        return df
    keys = [c for c in _EVENT_KEYS if c in df.columns]
    if not keys:
        return df

    df_sorted = df.copy()
    has_note = df_sorted["DowntimeNoteMatch"].notna() if "DowntimeNoteMatch" in df_sorted.columns else pd.Series(False, index=df_sorted.index)
    conf_rank = df_sorted["LocalConfidence"].map(_CONFIDENCE_ORDER).fillna(0) if "LocalConfidence" in df_sorted.columns else pd.Series(0, index=df_sorted.index)
    df_sorted["_note_rank"] = has_note.astype(int)
    df_sorted["_conf_rank"] = conf_rank
    df_sorted = df_sorted.sort_values(["_note_rank", "_conf_rank"], ascending=False)
    deduped = df_sorted.drop_duplicates(subset=keys).drop(columns=["_note_rank", "_conf_rank"])

    return deduped


def _compute_downtime_type(df):
    """Add DowntimeType column derived from DowntimeNoteMatch."""
    if df.empty or "DowntimeNoteMatch" not in df.columns:
        return df
    df = df.copy()
    df["DowntimeType"] = df["DowntimeNoteMatch"].map(_NOTE_TYPE_MAP).fillna("Unclassified")
    return df


def _compute_local_confidence(df):
    """Add LocalConfidence column based on agreed scoring tiers.

    All rows — if the gap detection algorithm found a gap in field records, it is
    real downtime. CompletedInGap reflects scheduling decisions made around the
    outage, not evidence the machine was running. Confidence tiers reflect only
    how certain we are of the cause:

    Gap / StartOfDay / EndOfDay:
      High   — DowntimeNoteMatch is not null
      Medium — LastFieldTerminationStatus == 'MACHINE'
      Low    — everything else

    FullDay rows — CancelledInGap replaces termination status as the Medium signal:
      High   — DowntimeNoteMatch is not null
      Medium — CancelledInGap > 0
      Low    — everything else
    """
    if df.empty:
        return df
    df = df.copy()

    has_note = df["DowntimeNoteMatch"].notna()
    is_fullday = df["RowType"] == "FullDay"
    has_cancellations = df["CancelledInGap"].fillna(0) > 0
    is_machine_term = df.get("LastFieldTerminationStatus", pd.Series("", index=df.index)) == "MACHINE"

    conditions = [
        has_note,
        is_fullday & has_cancellations,
        ~is_fullday & is_machine_term,
    ]
    choices = ["High", "Medium", "Medium"]
    df["LocalConfidence"] = np.select(conditions, choices, default="Low")

    return df


def _propagate_event_note(df):
    """Add EventNote column: the event's best non-null DowntimeNoteMatch broadcast to all rows.

    B-branch rows have null DowntimeNoteMatch in the SQL output. This propagates
    the A-branch note to all rows sharing the same event keys so that the note
    filter operates at the event level (not just on the row that happens to have it).
    Also normalises the string 'None' value (which can appear in the CSV) to NaN.
    """
    if df.empty or "DowntimeNoteMatch" not in df.columns:
        return df
    df = df.copy()
    df["DowntimeNoteMatch"] = df["DowntimeNoteMatch"].replace("None", np.nan)
    evt_keys = [c for c in _EVENT_KEYS if c in df.columns]
    if not evt_keys:
        df["EventNote"] = np.nan
        return df
    best = (
        df[df["DowntimeNoteMatch"].notna()]
        .drop_duplicates(subset=evt_keys)[evt_keys + ["DowntimeNoteMatch"]]
        .rename(columns={"DowntimeNoteMatch": "EventNote"})
    )
    df = df.drop(columns=["EventNote"], errors="ignore")
    if not best.empty:
        df = df.merge(best, on=evt_keys, how="left")
    else:
        df["EventNote"] = np.nan
    return df


# ---------------------------------------------------------------------------
# Interpolation: estimate boundary gap durations from neighboring days
# ---------------------------------------------------------------------------

def _compute_interpolated_gap_minutes(gap_evt, fd_evt):
    """Compute interpolated gap minutes matching the strip's visual rendering.

    Returns a dict: {(Machine, DowntimeDate_str, RowType, GapStartTime_str): minutes}
    """
    from data.loader import load_treatment_detail

    td = load_treatment_detail()
    if td.empty:
        return {}

    td = td.copy()
    td["_date"] = td["ScheduledDateTime"].dt.normalize()
    td["_start_min"] = td["TreatmentStartTime"].dt.hour * 60 + td["TreatmentStartTime"].dt.minute
    td["_end_min"] = td["TreatmentEndTime"].dt.hour * 60 + td["TreatmentEndTime"].dt.minute

    tx_daily = td.groupby(["Machine", "_date"], observed=True).agg(
        ft=("_start_min", "min"),
        lt=("_end_min", "max"),
    ).reset_index()

    machine_tx = {}
    for machine, grp in tx_daily.groupby("Machine", observed=True):
        grp = grp.sort_values("_date")
        dates = grp["_date"].values.astype("datetime64[ns]")
        fts = grp["ft"].values.astype(int)
        lts = grp["lt"].values.astype(int)
        machine_tx[machine] = (dates, fts, lts)

    def _neighbor_interp(machine, target_date):
        if machine not in machine_tx:
            return 480, 1020
        dates, fts, lts = machine_tx[machine]
        td64 = np.datetime64(target_date)
        idx = np.searchsorted(dates, td64)

        prev_ft, prev_lt = (None, None)
        if idx > 0:
            prev_ft, prev_lt = int(fts[idx - 1]), int(lts[idx - 1])

        next_ft, next_lt = (None, None)
        ni = idx
        if ni < len(dates) and dates[ni] == td64:
            ni += 1
        if ni < len(dates):
            next_ft, next_lt = int(fts[ni]), int(lts[ni])

        if prev_ft is not None and next_ft is not None:
            return round((prev_ft + next_ft) / 2), round((prev_lt + next_lt) / 2)
        elif prev_ft is not None:
            return prev_ft, prev_lt
        elif next_ft is not None:
            return next_ft, next_lt
        return 480, 1020

    result = {}

    if not fd_evt.empty:
        for machine, dt in fd_evt[["Machine", "DowntimeDate"]].drop_duplicates().itertuples(index=False):
            dt_n = dt.normalize()
            ds = dt_n.strftime("%Y-%m-%d")
            interp_ft, interp_lt = _neighbor_interp(machine, dt_n)
            result[(machine, ds, "FullDay", "")] = max(0, interp_lt - interp_ft)

    if not gap_evt.empty:
        boundary = gap_evt[gap_evt["RowType"].isin(["EndOfDay", "StartOfDay"])].copy()
        if not boundary.empty:
            boundary["_gs"] = boundary["GapStartTime"].apply(_time_str_to_min)
            boundary["_ge"] = boundary["GapEndTime"].apply(_time_str_to_min)
            for row_type, machine, dt, gs, ge, gs_raw in zip(
                boundary["RowType"], boundary["Machine"], boundary["DowntimeDate"],
                boundary["_gs"], boundary["_ge"], boundary["GapStartTime"],
            ):
                dt_n = dt.normalize()
                ds = dt_n.strftime("%Y-%m-%d")
                gs_str = str(gs_raw)[:8] if pd.notna(gs_raw) else ""
                interp_ft, interp_lt = _neighbor_interp(machine, dt_n)

                if row_type == "EndOfDay" and gs is not None:
                    result[(machine, ds, "EndOfDay", gs_str)] = max(0, interp_lt - int(gs))
                elif row_type == "StartOfDay" and ge is not None:
                    result[(machine, ds, "StartOfDay", gs_str)] = max(0, int(ge) - interp_ft)

    return result


def _apply_interpolated_minutes(gap_evt, fd_evt, interp_map):
    """Apply interpolated minutes to gap and fullday event dataframes."""
    if not gap_evt.empty:
        gap_evt = gap_evt.copy()
        is_boundary = gap_evt["RowType"].isin(["EndOfDay", "StartOfDay"])
        if is_boundary.any():
            # .astype(str) on each piece — Machine and RowType may be Categorical
            # (loader.py categoricalises low-cardinality string columns to save
            # RAM), and Categorical doesn't support `+` string concat.
            keys = (
                gap_evt.loc[is_boundary, "Machine"].astype(str)
                + "|" + gap_evt.loc[is_boundary, "DowntimeDate"].dt.strftime("%Y-%m-%d")
                + "|" + gap_evt.loc[is_boundary, "RowType"].astype(str)
                + "|" + gap_evt.loc[is_boundary, "GapStartTime"].fillna("").astype(str).str[:8]
            )
            flat_map = {f"{m}|{d}|{rt}|{gs}": v for (m, d, rt, gs), v in interp_map.items()
                        if rt in ("EndOfDay", "StartOfDay")}
            gap_evt.loc[is_boundary, "GapMinutes"] = keys.map(flat_map).fillna(
                gap_evt.loc[is_boundary, "GapMinutes"]
            ).astype(float)

    if not fd_evt.empty:
        fd_evt = fd_evt.copy()
        keys = fd_evt["Machine"].astype(str) + "|" + fd_evt["DowntimeDate"].dt.strftime("%Y-%m-%d") + "|FullDay|"
        flat_map = {f"{m}|{d}|FullDay|": v for (m, d, rt, gs), v in interp_map.items() if rt == "FullDay"}
        fd_evt["GapMinutes"] = keys.map(flat_map).fillna(600).astype(float)

    return gap_evt, fd_evt


# ---------------------------------------------------------------------------
# Cached transformed dataset — avoids recomputing on every callback
# ---------------------------------------------------------------------------

_transformed_cache = {"hash": None, "df": None, "gap_evt": None, "fd_evt": None}

# Register the cache for TTL eviction by the loader-sweeper. After idle TTL
# the sweeper resets all keys to None; next call rebuilds from the parquet
# sidecars (~1-2s) instead of holding the transformed gaps + dedup events
# in RAM 24/7.
from data.loader import register_ttl_dict as _register_ttl_dict
_transformed_ttl = _register_ttl_dict(_transformed_cache)


def _transform_source_paths():
    """Source files whose changes invalidate the transformed parquet cache.

    Includes raw downtime gap CSVs and this module — so any change to the
    transformation logic forces a rebuild on next startup.
    """
    from pathlib import Path
    from config.settings import DATA_INCREMENTAL
    paths = sorted((DATA_INCREMENTAL / "MachineDowntimeGaps").glob("*.csv"))
    paths.append(Path(__file__).resolve())
    return paths


def _get_transformed_gaps():
    """Return the fully transformed downtime gaps dataframe, cached across callbacks.

    Two-tier cache:
      1. In-memory dict keyed by id(load_downtime_gaps()).
      2. Three parquet sidecars (transformed/gap_evt/fd_evt) with shared sig —
         survive restarts; invalidated by source file or transform-logic changes.
    """
    from data.loader import load_downtime_gaps, _read_parquet_cache, _write_parquet_cache

    raw = load_downtime_gaps()
    raw_id = id(raw)
    if _transformed_cache["hash"] == raw_id and _transformed_cache["df"] is not None:
        _transformed_ttl.touch()
        return _transformed_cache["df"]

    src_paths = _transform_source_paths()
    df_cached = _read_parquet_cache("DowntimeGaps_transformed", src_paths)
    gap_cached = _read_parquet_cache("DowntimeGaps_gap_evt", src_paths)
    fd_cached = _read_parquet_cache("DowntimeGaps_fd_evt", src_paths)

    if df_cached is not None and gap_cached is not None and fd_cached is not None:
        df = df_cached
        gap_evt = gap_cached
        fd_evt = fd_cached
    else:
        df = _compute_downtime_type(
            _compute_local_confidence(
                _propagate_event_note(raw.copy())
            )
        )
        if "LastFieldPlannedMU" in df.columns and "LastFieldDeliveredMU" in df.columns:
            planned = df["LastFieldPlannedMU"].fillna(0)
            delivered = df["LastFieldDeliveredMU"].fillna(0)
            df["MUDeliveredPct"] = np.where(planned > 0, (delivered / planned * 100).round(1), np.nan)
        gap_rows = df[df["RowType"].isin(["Gap", "StartOfDay", "EndOfDay"])]
        fd_rows = df[df["RowType"] == "FullDay"]
        gap_evt = _dedup_events(gap_rows) if not gap_rows.empty else pd.DataFrame()
        fd_evt = _dedup_events(fd_rows) if not fd_rows.empty else pd.DataFrame()
        if not gap_evt.empty or not fd_evt.empty:
            interp_map = _compute_interpolated_gap_minutes(gap_evt, fd_evt)
            gap_evt, fd_evt = _apply_interpolated_minutes(gap_evt, fd_evt, interp_map)

        # Convert object columns to strings for parquet compatibility
        # (datetime.time objects in mixed-type columns cause pyarrow errors)
        def _prep_for_parquet(frame):
            if frame.empty:
                return frame
            frame = frame.copy()
            for col in frame.columns:
                if frame[col].dtype == object:
                    frame[col] = frame[col].astype(str).replace({"NaT": "", "None": "", "nan": ""})
            return frame
        _write_parquet_cache("DowntimeGaps_transformed", _prep_for_parquet(df), src_paths)
        _write_parquet_cache("DowntimeGaps_gap_evt", _prep_for_parquet(gap_evt), src_paths)
        _write_parquet_cache("DowntimeGaps_fd_evt", fd_evt, src_paths)

    _transformed_cache["hash"] = raw_id
    _transformed_cache["df"] = df
    _transformed_cache["gap_evt"] = gap_evt
    _transformed_cache["fd_evt"] = fd_evt
    _transformed_ttl.touch()
    return df
