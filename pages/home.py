"""Home page — executive summary with sparkline KPI cards and rolling census charts."""

import dash
import dash_mantine_components as dmc
from dash import callback, Input, Output, State, dcc, html, clientside_callback, ClientsideFunction
from dash_iconify import DashIconify
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from functools import lru_cache

from config.settings import (
    DEPARTMENTS, DEPARTMENT_COLORS, CHART_COLORWAY, PRIMARY,
    DEFAULT_LAYOUT, FONT_FAMILY, SEMANTIC_COLORS, PRIOR_PERIOD_COLORS,
)
from components.filter_bar import department_chips
from components.outlier_panel import outlier_panel, register_outlier_callbacks
from components.kpi_card import kpi_card, kpi_placeholder
from components.chart_card import chart_card, register_chart_callbacks
from components.hours_ribbon import hours_ribbon_card, register_hours_ribbon_callbacks
from utils.charts import apply_default_layout, empty_figure, dept_color, smooth_limits
from statsmodels.nonparametric.smoothers_lowess import lowess as _lowess

PAGE_ID = "home"
_CAP_CONSULT_LEAD = 30   # > 30 days booking-to-consult = outlier
_CAP_SIM_LEAD = 21       # > 21 days booking-to-sim = outlier


# ---------------------------------------------------------------------------
# Double-import guard
# ---------------------------------------------------------------------------
# Dash's page-importer uses spec.loader.exec_module() which re-executes the
# module body even if Python already has it in sys.modules (via an earlier
# `from pages.home import …` elsewhere, e.g. pages/home_mobile.py). Without
# this guard, every @callback and clientside_callback in this file gets
# registered twice on the second pass, producing "Duplicate callback outputs"
# errors across the entire home page. We detect the second pass by checking
# the live Dash app's callback_map for a stable home-page output, then
# neuter `callback` and `clientside_callback` for the rest of this pass so
# only function/helper definitions are rebound.
try:
    # `dash.callback` writes to the GLOBAL maps at decoration time; the
    # per-app ``callback_map`` isn't populated until ``_setup_server()``
    # runs, so checking that attribute always returns False on re-exec.
    from dash._callback import GLOBAL_CALLBACK_MAP as _GLOBAL_CB_MAP
    _already_registered = "home-tx-trend-store.data" in _GLOBAL_CB_MAP
except Exception:
    _already_registered = False

if _already_registered:
    def _noop_callback(*args, **kwargs):
        if len(args) == 1 and callable(args[0]):
            return args[0]
        def _decorator(fn):
            return fn
        return _decorator
    callback = _noop_callback          # type: ignore[assignment]
    clientside_callback = _noop_callback  # type: ignore[assignment]


def _apply_loess(series, frac):
    """Apply LOESS smoothing to a pandas Series."""
    if frac <= 0 or len(series) < 4:
        return series
    x_num = np.arange(len(series))
    smoothed = _lowess(series.values.astype(float), x_num, frac=frac, return_sorted=False)
    return pd.Series(smoothed, index=series.index)


def _clean_spark(series, biz_days_only=True, frac=0.2):
    """Clean sparkline series: filter non-business days, apply LOESS smoothing."""
    if biz_days_only and hasattr(series.index, 'weekday'):
        series = series[series.index.weekday < 5]
        series = series[series > 0]
    return _apply_loess(series, frac)


_ATTENDED_EXCLUDE_STATUSES = frozenset({"Cancelled", "Cancelled - Patient No-Show", "Deleted"})


def _classify_consults(cv):
    """Filter a clinic-visit dataframe to rows where VisitType == "Consult".

    Uses the exact classifier from the clinic-visits page so both pages count
    consults identically. Lazy import avoids circular-import issues at module
    load; the function is cheap once imported.
    """
    if cv.empty or "ActivityName" not in cv.columns:
        return cv.iloc[0:0]
    from pages.clinic_visits import _classify_visit_type
    return cv[cv.apply(_classify_visit_type, axis=1) == "Consult"]


def _apply_attended_filter(df):
    """Mirror clinic_visits.py default Status="Attended" rule: drop cancelled /
    no-show / deleted, plus any Open rows dated on/after the latest data export
    (future-scheduled — hasn't happened yet). Keeps past-dated Opens, which are
    consults that happened but never got their status flipped to Completed.
    """
    if df.empty or "Status" not in df.columns:
        return df
    from pages.clinic_visits import _get_cv_export_date
    out = df[~df["Status"].isin(_ATTENDED_EXCLUDE_STATUSES)]
    export_date = _get_cv_export_date()
    if export_date is not None and "ScheduledDateTime" in out.columns:
        future_open = (out["Status"] == "Open") & (out["ScheduledDateTime"].dt.normalize() >= export_date)
        out = out[~future_open]
    return out


# Simulation scope — match simulations.py "Initial Simulations" / "Total Simulations" KPIs.
# "initial" = Initial + Stereotactic (aligns with sim page's Initial KPI).
# "all"     = every sim activity except HOLD/MD-needed placeholders (aligns with
#             sim page's Total KPI and its _SIM_TYPE_EXCLUDE set).
_SIM_SCOPE_EXCLUDE = frozenset({"HOLD SIM TIME", "MD Needed in Sim"})


def _filter_sims_scope(sims, scope):
    """Apply sim-scope filter to an ActivityName column. Returns filtered df."""
    if sims.empty or "ActivityName" not in sims.columns:
        return sims
    if scope == "initial":
        return sims[
            sims["ActivityName"].str.contains("Initial", case=False, na=False) |
            sims["ActivityName"].str.contains("Stereotactic Simulation", case=False, na=False)
        ]
    # "all": blacklist placeholder activities, keep everything else.
    return sims[~sims["ActivityName"].isin(_SIM_SCOPE_EXCLUDE)]


dash.register_page(__name__, path="/", name="Home", order=0)


# ---------------------------------------------------------------------------
# Home metric charts — 4 metrics × 2 rows (trend + cumulative)
# ---------------------------------------------------------------------------

_DIM_DEPT_MD = [
    {"value": "total", "label": "Total"},
    {"value": "department", "label": "Dept"},
    {"value": "physician", "label": "MD"},
]
_DIM_DEPT_DX = [
    {"value": "total", "label": "Total"},
    {"value": "department", "label": "Dept"},
    {"value": "diagnosis", "label": "Dx"},
]

_HOME_METRICS = [
    # (metric_id, title_base, dim_options, trend_defaults)
    # trend_defaults: dim / agg / chart_type / stack applied to the trend card
    # (cum card uses the same dim/agg but its own chart_type=line default).
    ("tx",       "Treatments",   _DIM_DEPT_MD, {"dim": "department", "agg": "W", "chart_type": "area", "stack": "stacked"}),
    ("consults", "New Consults", _DIM_DEPT_MD, {"dim": "physician",  "agg": "M", "chart_type": "bar",  "stack": "stacked"}),
    ("sims",     "Simulations",  _DIM_DEPT_MD, {"dim": "total",      "agg": "W", "chart_type": "area", "stack": "stacked"}),
    ("refs",     "Referrals",    _DIM_DEPT_DX, {"dim": "department", "agg": "M", "chart_type": "bar",  "stack": "stacked"}),
]

_AGG_DATA = [
    {"value": "D", "label": "D"},
    {"value": "W", "label": "W"},
    {"value": "M", "label": "M"},
]


def _metric_card_col(metric_id, title, dim_options, is_cumulative, defaults=None):
    """Build one chart-card GridCol for the home metric grid."""
    defaults = defaults or {}
    row = "cum" if is_cumulative else "trend"
    cid = f"home-chart-{metric_id}-{row}"
    sid = f"home-{metric_id}-{row}"
    label = ("Cumulative " if is_cumulative else "") + title
    chart_types = [
        {"value": "area", "label": "Area"},
        {"value": "line", "label": "Line"},
        {"value": "bar",  "label": "Bar"},
    ]
    # Shared trend/cum: same dim + agg defaults per column. Chart type/smoothing
    # differ — cum defaults to a LOESS-smoothed line, trend uses the per-metric
    # trend_default chart type.
    dim_default = defaults.get("dim") or next(
        (o["value"] for o in dim_options if o["value"] == "department"),
        dim_options[0]["value"],
    )
    agg_default = defaults.get("agg", "W")
    if is_cumulative:
        smooth_kwargs = dict(smooth_min=0, smooth_max=1, smooth_step=0.05, smooth_default=0.1)
        chart_type_default = "line"
    else:
        smooth_kwargs = dict(smooth_min=0, smooth_max=50, smooth_step=1, smooth_default=5)
        chart_type_default = defaults.get("chart_type", "area")
    return dmc.GridCol(
        span={"base": 12, "sm": 6, "md": 3},
        children=chart_card(
            cid, label,
            settings_id=sid,
            chart_types=chart_types,
            chart_type_default=chart_type_default,
            show_smooth=True,
            # Cum cards are unidimensional (single "Total" slice per year) —
            # Stacked/Grouped has nothing to group. The dispatcher forces
            # stacked internally so per-bar total annotations still render.
            show_grouping=not is_cumulative,
            show_prior_periods=is_cumulative,
            prior_periods_default=3,
            show_project_toggle=is_cumulative,
            project_toggle_default=True,
            paper_height="400px",
            extra_controls_left=[
                dmc.SegmentedControl(
                    id=f"{sid}-dim", data=dim_options,
                    value=dim_default, size="xs",
                ),
            ],
            extra_controls=[
                dmc.SegmentedControl(
                    id=f"{sid}-agg", data=_AGG_DATA, value=agg_default, size="xs",
                ),
            ],
            **smooth_kwargs,
        ),
    )


# ---------------------------------------------------------------------------
# Helper: Operating Hours Ribbon Data (for clientside smoothing)
# ---------------------------------------------------------------------------

def _prepare_hours_data(departments, days_back=30):
    """Prepare raw operating hours data for clientside smoothing.

    Returns dict with:
    - series: [{name, dates, startHours, endHours, color, isFuture}...]
    - yAxis: {min, max, tickvals, ticktext}
    - todayIdx: index of today in the date sequence (for vertical line)
    """
    from data.loader import load_daily_volume, load_daily_volume_future

    try:
        dv_past = load_daily_volume()
        dv_future = load_daily_volume_future()

        sites = departments if departments else DEPARTMENTS

        # Filter to site-level departments only
        dv_past = dv_past[dv_past["Department"].isin(sites)]
        dv_future = dv_future[dv_future["Department"].isin(sites)]

        if dv_past.empty:
            return None

        # Filter past data by days_back (0 = all data)
        last_date = dv_past["ScheduledDate"].max()
        if days_back > 0:
            start_date = last_date - timedelta(days=days_back)
            dv_past = dv_past[dv_past["ScheduledDate"] >= start_date]

        # Limit future data to 2 weeks
        today = pd.Timestamp.now(tz="America/Los_Angeles").normalize().tz_localize(None)
        two_weeks_ahead = today + timedelta(days=14)
        dv_future = dv_future[dv_future["ScheduledDate"] <= two_weeks_ahead]

        def _parse_time_to_hour(time_str):
            """Convert time string like '08:30:00' to decimal hour (8.5)."""
            if pd.isna(time_str) or time_str is None or time_str == "":
                return None
            try:
                parts = str(time_str).split(":")
                return int(parts[0]) + int(parts[1]) / 60
            except (ValueError, IndexError):
                return None

        def _process_dv(dv_df, is_future=False):
            """Process daily volume dataframe into series data."""
            # Filter out weekends
            dv_df = dv_df[dv_df["ScheduledDate"].dt.weekday < 5].copy()
            results = []

            for site in sites:
                site_data = dv_df[dv_df["Department"] == site].copy()
                if site_data.empty:
                    continue

                # Prefer actual times, fall back to scheduled
                if "FirstActualStart" in site_data.columns and "FirstScheduledStart" in site_data.columns:
                    site_data["start_str"] = site_data["FirstActualStart"].fillna(site_data["FirstScheduledStart"])
                elif "FirstScheduledStart" in site_data.columns:
                    site_data["start_str"] = site_data["FirstScheduledStart"]
                else:
                    continue

                if "LastActualEnd" in site_data.columns and "LastScheduledEnd" in site_data.columns:
                    site_data["end_str"] = site_data["LastActualEnd"].fillna(site_data["LastScheduledEnd"])
                elif "LastScheduledEnd" in site_data.columns:
                    site_data["end_str"] = site_data["LastScheduledEnd"]
                else:
                    continue

                # Convert time strings to decimal hours
                site_data["start_hour"] = site_data["start_str"].apply(_parse_time_to_hour)
                site_data["end_hour"] = site_data["end_str"].apply(_parse_time_to_hour)

                # Drop rows with no valid times (zero days)
                site_data = site_data.dropna(subset=["start_hour", "end_hour"])
                # Also filter out days where start >= end (no real activity)
                site_data = site_data[site_data["end_hour"] > site_data["start_hour"]]
                if site_data.empty:
                    continue
                site_data = site_data.sort_values("ScheduledDate")

                # Include appointment counts for calendar hover/annotations
                counts = []
                if "AppointmentCount" in site_data.columns:
                    counts = site_data["AppointmentCount"].fillna(0).astype(int).tolist()

                results.append({
                    "name": site,
                    "dates": [d.isoformat() for d in site_data["ScheduledDate"]],
                    "startHours": site_data["start_hour"].tolist(),
                    "endHours": site_data["end_hour"].tolist(),
                    "counts": counts,
                    "color": dept_color(site),
                    "isFuture": is_future,
                })

            return results

        # Process past and future separately
        past_series = _process_dv(dv_past, is_future=False)
        future_series = _process_dv(dv_future, is_future=True)

        # Calculate y-axis range from PAST data only
        all_start_hours = []
        all_end_hours = []
        for s in past_series:
            all_start_hours.extend(s["startHours"])
            all_end_hours.extend(s["endHours"])

        if all_start_hours and all_end_hours:
            min_hour = min(all_start_hours)
            max_hour = max(all_end_hours)
            y_min = np.floor(min_hour * 2) / 2  # Round down to nearest 0.5
            y_max = np.ceil(max_hour * 2) / 2   # Round up to nearest 0.5
            # Add small padding
            y_min = max(0, y_min - 0.5)
            y_max = min(24, y_max + 0.5)
        else:
            y_min, y_max = 6, 20  # Fallback

        # Generate tick values and labels
        tick_interval = 1 if (y_max - y_min) <= 6 else 2
        tick_start = int(np.ceil(y_min / tick_interval) * tick_interval)
        tick_end = int(np.floor(y_max / tick_interval) * tick_interval)
        tickvals = list(range(tick_start, tick_end + 1, tick_interval))
        ticktext = []
        for h in tickvals:
            if h == 0:
                ticktext.append("12am")
            elif h < 12:
                ticktext.append(f"{h}am")
            elif h == 12:
                ticktext.append("12pm")
            else:
                ticktext.append(f"{h - 12}pm")

        return {
            "pastSeries": past_series,
            "futureSeries": future_series,
            "yAxis": {
                "min": y_min,
                "max": y_max,
                "tickvals": tickvals,
                "ticktext": ticktext,
            },
            "today": today.isoformat(),
            "height": 380,
        }

    except Exception:
        return None


# ---------------------------------------------------------------------------
# Helper: Slot Availability Calendar (Dual - Exam & Sim)
# ---------------------------------------------------------------------------

def _build_availability_calendar(departments, consults_only=True, view="both"):
    """Build 4-week availability calendar with Exam and Sim side by side.

    Layout: Mon-Fri as columns (like a calendar), weeks as rows.
    Shows % booked (scheduled / total capacity) for each day.
    Green (<50%), Yellow (50-80%), Red (>80%)
    Includes median lead time for future scheduled appointments.

    Args:
        departments: list of departments to filter by, or None/empty for all.
        consults_only: if True, filter consult calendar to Consult activities only.
        view: "both" (default, side-by-side), "consults" (exam only), or "sims".
    """
    from data.loader import load_availability, load_clinic_visits, load_simulations

    try:
        today = pd.Timestamp.now(tz="America/Los_Angeles").normalize().tz_localize(None)
        four_weeks = today + timedelta(days=28)

        # Load open holds from Availability (only unfilled slots)
        avail = load_availability()
        if "SlotTaken" in avail.columns:
            avail = avail[avail["SlotTaken"] != "Yes"]
        # Drop non-bookable sim holds: 8:00 AM 30-min setup slot + lunch holds
        _is_sim = avail["Category"].str.contains("Simulation", case=False, na=False)
        _hour = avail["AppointmentDateTime"].dt.hour
        _minute = avail["AppointmentDateTime"].dt.minute
        _dur = avail["DurationMinutes"]
        avail = avail[~(_is_sim & (
            ((_hour == 8) & (_minute == 0) & (_dur == 30)) |
            (_hour == 12)
        ))]
        avail_future = avail[
            (avail["SlotDate"] >= today) &
            (avail["SlotDate"] <= four_weeks)
        ]
        # Department filter applies to exams only (sims are one location)
        if departments and "Department" in avail_future.columns:
            avail_future_dept = avail_future[avail_future["Department"].isin(departments)]
        else:
            avail_future_dept = avail_future

        # Load clinic visits for exams (department-filtered, exclude cancelled/deleted)
        cv = load_clinic_visits()
        if "Status" in cv.columns:
            cv = cv[~cv["Status"].str.contains("Cancel|Deleted", case=False, na=False)]
        if departments and "Department" in cv.columns:
            cv = cv[cv["Department"].isin(departments) | cv["Department"].isna()]
        cv_future = cv[
            (cv["ScheduledDateTime"] >= today) &
            (cv["ScheduledDateTime"] <= four_weeks)
        ]
        if consults_only and "ActivityName" in cv_future.columns:
            cv_future = cv_future[
                cv_future["ActivityName"].str.contains("Consult", case=False, na=False)
            ]

        # Load simulations (no department filter — one location, exclude cancelled/deleted)
        sims = load_simulations()
        if "Status" in sims.columns:
            sims = sims[~sims["Status"].str.contains("Cancel|Deleted", case=False, na=False)]
        sims_future = sims[
            (sims["ScheduledDateTime"] >= today) &
            (sims["ScheduledDateTime"] <= four_weeks)
        ]

        # Calculate scheduled counts
        exam_scheduled = cv_future.groupby(cv_future["ScheduledDateTime"].dt.normalize()).size()
        sim_scheduled = sims_future.groupby(sims_future["ScheduledDateTime"].dt.normalize()).size()

        # Open holds by category — exams use dept filter, sims do not
        exam_avail = avail_future_dept[
            avail_future_dept["Category"].str.contains("Exam", case=False, na=False)
        ]
        if consults_only and "ActivityName" in exam_avail.columns:
            exam_avail = exam_avail[
                exam_avail["ActivityName"].str.contains("Consult", case=False, na=False)
            ]
        exam_open = exam_avail.groupby("SlotDate").size()
        sim_open = avail_future[
            avail_future["Category"].str.contains("Simulation", case=False, na=False)
        ].groupby("SlotDate").size()

        # Next available open slot (days from today)
        exam_lead = None
        if not exam_open.empty:
            future_open = [d for d in exam_open[exam_open > 0].index if d >= today]
            if future_open:
                exam_lead = (min(future_open) - today).days

        sim_lead = None
        if not sim_open.empty:
            future_open = [d for d in sim_open[sim_open > 0].index if d >= today]
            if future_open:
                sim_lead = (min(future_open) - today).days

        # Generate date range (weekdays only)
        date_range = pd.bdate_range(today, four_weeks)

        # Align series to date range
        exam_scheduled = exam_scheduled.reindex(date_range, fill_value=0)
        sim_scheduled = sim_scheduled.reindex(date_range, fill_value=0)
        exam_open = exam_open.reindex(date_range, fill_value=0)
        sim_open = sim_open.reindex(date_range, fill_value=0)

        # Calculate % booked
        exam_total = exam_scheduled + exam_open
        sim_total = sim_scheduled + sim_open
        exam_pct = (exam_scheduled / exam_total.replace(0, 1) * 100).clip(0, 100)
        sim_pct = (sim_scheduled / sim_total.replace(0, 1) * 100).clip(0, 100)
        exam_pct = exam_pct.where(exam_total > 0, 100)
        sim_pct = sim_pct.where(sim_total > 0, 100)

        # Group dates by week (for row labels)
        weeks = []
        current_week_start = None
        for dt in date_range:
            week_start = dt - timedelta(days=dt.weekday())
            if week_start != current_week_start:
                weeks.append(week_start)
                current_week_start = week_start

        # Build calendar grids - TRANSPOSED: weeks as rows, Mon-Fri as columns
        x_labels = ["Mon", "Tue", "Wed", "Thu", "Fri"]

        # Compute weekly scheduled/total summaries
        def _week_summary(sched_series, total_series, week_start):
            ws = wt = 0
            for d in range(5):
                td = week_start + timedelta(days=d)
                ws += int(sched_series.get(td, 0))
                wt += int(total_series.get(td, 0))
            return ws, wt

        y_labels_exam = []
        y_labels_sim = []
        for ws in weeks:
            base = f"Wk {ws.strftime('%m/%d')}"
            es, et = _week_summary(exam_scheduled, exam_total, ws)
            ss, st = _week_summary(sim_scheduled, sim_total, ws)
            y_labels_exam.append(f"{base}<br><span style='font-size:9px;color:#6B7280'>{es}/{et}</span>")
            y_labels_sim.append(f"{base}<br><span style='font-size:9px;color:#6B7280'>{ss}/{st}</span>")

        # Pre-compute per-site exam detail for rich tooltips
        all_sites = departments if departments else list(DEPARTMENTS)

        # Per-date, per-department open exam slots with physician names
        _exam_detail = {}
        if not exam_avail.empty and "Department" in exam_avail.columns:
            for (dt, dept), grp in exam_avail.groupby(["SlotDate", "Department"]):
                if dt not in _exam_detail:
                    _exam_detail[dt] = {}
                mds = []
                if "AssignedResource" in grp.columns:
                    for res in grp["AssignedResource"].dropna().unique():
                        # Resources with a comma are physician names ("Last, First")
                        if "," in str(res):
                            mds.append(res.split(",")[0].strip())
                _exam_detail[dt][dept] = {"open": len(grp), "mds": sorted(set(mds))}

        # Per-date, per-department scheduled exam counts
        _exam_sched_dept = {}
        if not cv_future.empty and "Department" in cv_future.columns:
            cv_dated = cv_future.copy()
            cv_dated["_date"] = cv_dated["ScheduledDateTime"].dt.normalize()
            for (dt, dept), grp in cv_dated.groupby(["_date", "Department"]):
                if dt not in _exam_sched_dept:
                    _exam_sched_dept[dt] = {}
                _exam_sched_dept[dt][dept] = len(grp)

        def _build_z(pct_series):
            """Build z-data grid. Empty cells use -1 sentinel so the extended
            colorscale renders them transparent instead of Plotly's NaN hatch."""
            z = []
            for week_start in weeks:
                row = []
                for day_idx in range(5):
                    td = week_start + timedelta(days=day_idx)
                    row.append(pct_series[td] if td in pct_series.index else -1)
                z.append(row)
            return z

        def _exam_hover_grid(pct_series, sched_series, total_series):
            """Build rich exam hover text with per-site physician breakdown."""
            hover = []
            for week_start in weeks:
                row = []
                for day_idx in range(5):
                    td = week_start + timedelta(days=day_idx)
                    if td not in pct_series.index:
                        row.append("")
                        continue
                    pct = pct_series[td]
                    sched = int(sched_series.get(td, 0))
                    total = int(total_series.get(td, 0))
                    lines = [f"<b>{td.strftime('%a %b %d')}</b> — {sched}/{total} ({pct:.0f}%)"]
                    day_detail = _exam_detail.get(td, {})
                    for site in all_sites:
                        info = day_detail.get(site)
                        if info and info["open"] > 0:
                            md_str = ", ".join(info["mds"])
                            lines.append(f"{site}: {md_str}" if md_str else f"{site}: {info['open']} open")
                        elif _exam_sched_dept.get(td, {}).get(site, 0) > 0:
                            lines.append(f"{site}: Full")
                        else:
                            lines.append(f"{site}: —")
                    row.append("<br>".join(lines))
                hover.append(row)
            return hover

        def _sim_hover_grid(pct_series, sched_series, total_series):
            """Build sim hover text."""
            hover = []
            for week_start in weeks:
                row = []
                for day_idx in range(5):
                    td = week_start + timedelta(days=day_idx)
                    if td not in pct_series.index:
                        row.append("")
                        continue
                    pct = pct_series[td]
                    sched = int(sched_series.get(td, 0))
                    total = int(total_series.get(td, 0))
                    remaining = max(0, total - sched)
                    day_label = td.strftime("%a %b %d")
                    if remaining > 0:
                        row.append(f"<b>{day_label}</b> — {sched}/{total} ({pct:.0f}%)<br>{remaining} open")
                    else:
                        row.append(f"<b>{day_label}</b> — {sched}/{total} ({pct:.0f}%)<br>Full")
                hover.append(row)
            return hover

        exam_z = _build_z(exam_pct)
        sim_z = _build_z(sim_pct)
        exam_hover = _exam_hover_grid(exam_pct, exam_scheduled, exam_total)
        sim_hover = _sim_hover_grid(sim_pct, sim_scheduled, sim_total)

        # Determine which panels to render
        exam_title = "Consults" if consults_only else "All Clinic Visits"
        panels = []
        if view in ("both", "consults"):
            panels.append(("exam", exam_title, exam_z, y_labels_exam, exam_hover,
                           exam_pct, exam_scheduled, exam_total, exam_lead))
        if view in ("both", "sims"):
            panels.append(("sim", "Simulations", sim_z, y_labels_sim, sim_hover,
                           sim_pct, sim_scheduled, sim_total, sim_lead))
        if not panels:
            panels.append(("exam", exam_title, exam_z, y_labels_exam, exam_hover,
                           exam_pct, exam_scheduled, exam_total, exam_lead))

        # Skip subplot titles for single-panel view — caller's toggle/header is enough
        fig = make_subplots(
            rows=1, cols=len(panels),
            subplot_titles=[p[1] for p in panels] if len(panels) > 1 else None,
            horizontal_spacing=0.12,
        )

        # Colorscale spans z=-1..100. The -1 sentinel maps to transparent so
        # cells outside the data window render as blank (no cross-hatch pattern
        # Plotly applies to NaN by default). Remapped stops:
        #   -1  -> 0.0000   (transparent)
        #    0  -> 0.0099   (green)
        #   50  -> 0.5050   (light green)
        #   75  -> 0.7525   (amber)
        #   90  -> 0.9010   (orange)
        #  100  -> 1.0000   (red)
        colorscale = [
            [0.0000, "rgba(0,0,0,0)"],
            [0.0099, "rgba(0,0,0,0)"],
            [0.0099, "#4CAF50"],
            [0.5050, "#8BC34A"],
            [0.7525, "#FFC107"],
            [0.9010, "#FF9800"],
            [1.0000, "#D32F2F"],
        ]

        def _cell_labels(pct_series, sched_series, total_series):
            """Build text grid showing open slot count or 'Full'."""
            labels = []
            for week_start in weeks:
                row = []
                for day_idx in range(5):
                    target_date = week_start + timedelta(days=day_idx)
                    if target_date in pct_series.index:
                        total = int(total_series.get(target_date, 0))
                        sched = int(sched_series.get(target_date, 0))
                        remaining = max(0, total - sched)
                        if total == 0 or remaining == 0:
                            row.append("Full")
                        else:
                            row.append(str(remaining))
                    else:
                        row.append("")
                labels.append(row)
            return labels

        # Build traces per panel
        panel_labels = []
        for col_i, (_, _, z, ylbls, hover, pct_s, sched_s, total_s, _lead) in enumerate(panels, start=1):
            fig.add_trace(go.Heatmap(
                z=z, x=x_labels, y=ylbls,
                colorscale=colorscale, zmin=-1, zmax=100,
                text=hover, hovertemplate="%{text}<extra></extra>",
                hoverongaps=False,
                showscale=False,
            ), row=1, col=col_i)
            panel_labels.append(_cell_labels(pct_s, sched_s, total_s))

        # Add lead time annotations at bottom
        annotations = list(fig.layout.annotations)  # Keep subplot titles
        for ann in annotations:
            ann.y = 1.08
            # No explicit color — inherit from layout.font.color so the
            # theme-swap clientside callback can flip light/dark.
            ann.font = dict(size=12)

        # Overlay cell labels as annotations
        for col_i, ((_, _, _, ylbls, _, _, _, _, _), labels_grid) in enumerate(zip(panels, panel_labels), start=1):
            ax_suffix = "" if col_i == 1 else str(col_i)
            for row_idx, week_start in enumerate(weeks):
                for col_idx in range(5):
                    label = labels_grid[row_idx][col_idx]
                    if not label:
                        continue
                    is_full = label == "Full"
                    annotations.append(dict(
                        text=f"<b>{label}</b>" if is_full else label,
                        xref=f"x{ax_suffix}",
                        yref=f"y{ax_suffix}",
                        x=x_labels[col_idx],
                        y=ylbls[row_idx],
                        showarrow=False,
                        font=dict(
                            size=10 if is_full else 11,
                            color="#FFFFFF" if is_full else "rgba(0,0,0,0.6)",
                            family=FONT_FAMILY,
                        ),
                    ))

        # Add next-available annotation below each chart
        for col_i, (_, _, _, _, _, _, _, _, lead) in enumerate(panels, start=1):
            if lead is None:
                continue
            ax_suffix = "" if col_i == 1 else str(col_i)
            label = "Today" if lead == 0 else f"{lead}d out"
            annotations.append(dict(
                text=f"Next available: {label}",
                xref=f"x{ax_suffix} domain", yref=f"y{ax_suffix} domain",
                x=0.5, y=-0.06,
                showarrow=False,
                font=dict(size=13, color="#6B7280"),
                xanchor="center",
            ))

        fig.update_layout(
            height=380,
            font=dict(family=FONT_FAMILY, size=11),
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            margin=dict(l=45, r=8, t=50, b=32),
            annotations=annotations,
            hoverlabel=dict(
                bgcolor="white",
                bordercolor="#D1D5DB",
                font=dict(family=FONT_FAMILY, size=11, color="#374151"),
                align="left",
            ),
        )

        # Style both axes - time flows top to bottom (earliest week at top)
        fig.update_xaxes(
            side="top", tickfont=dict(size=10),
            showline=False, showgrid=False, zeroline=False, ticks="",
        )
        fig.update_yaxes(
            tickfont=dict(size=10), autorange="reversed",
            showline=False, showgrid=False, zeroline=False, ticks="",
        )

        return fig

    except Exception:
        return empty_figure("Error loading availability data")


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------
layout = dmc.Stack(
    gap=16,
    className="page-content",
    children=[
        # Sticky header with title and filter bar
        dmc.Box(
            className="page-sticky-header",
            children=[
                dmc.Title("Home", order=2, className="page-title"),

                # Filter bar — date presets + smoothing slider
                dmc.Paper(
                    children=[
                        dmc.Group(
                            children=[
                                dmc.SegmentedControl(
                                    id="home-filter-date-preset",
                                    data=[
                                        {"value": "30d",          "label": "30 d"},
                                        {"value": "3mo",          "label": "3 mo"},
                                        {"value": "6mo",          "label": "6 mo"},
                                        {"value": "12mo",         "label": "12 mo"},
                                        {"value": "last_year",    "label": "Last Year"},
                                        {"value": "ytd",          "label": "YTD"},
                                        {"value": "current_year", "label": "Current Year"},
                                        {"value": "this_month",   "label": "This Month"},
                                        {"value": "last_month",   "label": "Last Month"},
                                        {"value": "all",          "label": "All"},
                                    ],
                                    value="current_year", size="sm",
                                ),
                                department_chips("home"),
                                outlier_panel(PAGE_ID, transitions=[
                                    ("Consult Lead Time", _CAP_CONSULT_LEAD),
                                    ("Sim Lead Time", _CAP_SIM_LEAD),
                                ]),
                                dmc.Group(gap=8, align="center", children=[
                                    dmc.Text("Smoothing", size="sm", c="#9CA3AF", fw=500),
                                    dmc.Slider(
                                        id="home-filter-smoothing",
                                        min=0, max=1, step=0.01, value=0.4,
                                        size="xs", w=120,
                                        showLabelOnHover=False,
                                        updatemode="drag",
                                    ),
                                ]),
                            ],
                            gap="lg", wrap="wrap",
                        ),
                    ],
                    p="sm", px="md", radius="md", shadow="xs", withBorder=True,
                ),
            ],
        ),

        # KPI row — 5 cards with sparklines
        dmc.Grid(
            id="home-kpi-row",
            gutter=16,
            children=[
                dmc.GridCol(kpi_placeholder(), id="home-kpi-consults-week", span={"base": 12, "sm": 6, "md": 2.4}),
                dmc.GridCol(kpi_placeholder(), id="home-kpi-sims-week", span={"base": 12, "sm": 6, "md": 2.4}),
                dmc.GridCol(kpi_placeholder(), id="home-kpi-tx-today", span={"base": 12, "sm": 6, "md": 2.4}),
                dmc.GridCol(kpi_placeholder(), id="home-kpi-consult-lead", span={"base": 12, "sm": 6, "md": 2.4}),
                dmc.GridCol(kpi_placeholder(), id="home-kpi-sim-lead", span={"base": 12, "sm": 6, "md": 2.4}),
            ],
        ),

        # Metric charts — trend row + cumulative row
        dmc.Grid(gutter=16, children=[
            _metric_card_col(m, title, dims, is_cumulative=False, defaults=defaults)
            for m, title, dims, defaults in _HOME_METRICS
        ]),
        dmc.Grid(gutter=16, children=[
            _metric_card_col(m, title, dims, is_cumulative=True, defaults=defaults)
            for m, title, dims, defaults in _HOME_METRICS
        ]),

        # Operating hours + Availability row
        dmc.Grid(
            gutter=16, align="stretch",
            children=[
                # Left: Operating Hours Ribbon
                dmc.GridCol(
                    span={"base": 12, "md": 6},
                    children=hours_ribbon_card("home", card_height="466px"),
                ),
                # Right: Availability Calendar
                dmc.GridCol(
                    span={"base": 12, "md": 6},
                    children=chart_card(
                        "home-chart-availability",
                        "Slot Availability (4 Weeks)",
                        settings_id="home-avail",
                        chart_types=None,
                        show_smooth=False,
                        show_grouping=False,
                        paper_height="466px",
                        extra_controls_left=[
                            dmc.SegmentedControl(
                                id="home-avail-scope",
                                data=[
                                    {"value": "consults", "label": "Consults"},
                                    {"value": "all", "label": "All"},
                                ],
                                value="consults", size="xs",
                            ),
                        ],
                    ),
                ),
            ],
        ),

        # Interval for periodic refresh
        dcc.Interval(id="home-interval", interval=300_000, n_intervals=0),

        # Stores for raw metric data (one per card: 4 trend + 4 cumulative)
        *[dcc.Store(id=f"home-{m}-{row}-store")
          for m, _, _, _ in _HOME_METRICS for row in ("trend", "cum")],
        # Shared "Prior Periods" value — any cum card's slider writes here and
        # every cum card's render + slider reads from it, keeping the whole row in sync.
        dcc.Store(id="home-cum-prior-store", data=3),

        # Store for KPI sparkline data (clientside smoothing)
        dcc.Store(id="home-store-kpi-sparklines"),

        # Store for sims scope toggle (bridges dynamically-created control → callback)
        dcc.Store(id="home-store-sims-scope", data="initial"),
    ],
)


def _sims_scope_toggle(current="initial"):
    """Tiny Initial/All toggle for the Simulations KPI card header."""
    return dmc.SegmentedControl(
        id="home-sims-scope",
        data=[
            {"value": "initial", "label": "Initial"},
            {"value": "all", "label": "All"},
        ],
        value=current, size="xs",
    )


# Sync dynamically-created toggle → Store so the KPI callback can read it
clientside_callback(
    """function(v) { return v; }""",
    Output("home-store-sims-scope", "data"),
    Input("home-sims-scope", "value"),
    prevent_initial_call=True,
)


# ---------------------------------------------------------------------------
# KPI Callback — outputs cards + raw sparkline data for clientside smoothing
# ---------------------------------------------------------------------------

@callback(
    Output("home-kpi-consults-week", "children"),
    Output("home-kpi-sims-week", "children"),
    Output("home-kpi-tx-today", "children"),
    Output("home-kpi-consult-lead", "children"),
    Output("home-kpi-sim-lead", "children"),
    Output("home-store-kpi-sparklines", "data"),
    Input("home-interval", "n_intervals"),
    Input("home-filter-date-preset", "value"),
    Input("home-filter-department", "value"),
    Input("home-store-sims-scope", "data"),
    Input(f"{PAGE_ID}-outlier-enabled", "data"),
    Input(f"{PAGE_ID}-outlier-cap-0", "value"),
    Input(f"{PAGE_ID}-outlier-cap-1", "value"),
)
def update_kpis(_n, date_preset, departments, sims_scope,
                outlier_enabled, cap_consult, cap_sim):
    """Compute all 5 KPI cards with sparkline IDs (data computed separately)."""
    from data.loader import load_treatment_detail, load_simulations, load_clinic_visits
    sims_scope = sims_scope or "initial"

    # Resolve outlier caps
    if not outlier_enabled:
        cap_consult = 365
        cap_sim = 365
    else:
        cap_consult = cap_consult or _CAP_CONSULT_LEAD
        cap_sim = cap_sim or _CAP_SIM_LEAD

    PERIOD_LABELS = {
        "12mo": "12 mo", "6mo": "6 mo", "3mo": "3 mo", "30d": "30 days",
        "ytd": "YTD", "current_year": "Current Yr", "last_year": "Last Year",
        "this_month": "This Month", "last_month": "Last Month",
        "all": "All Time",
    }
    TREND_LABELS = {
        "12mo": "vs prior 12 mo", "6mo": "vs prior 6 mo", "3mo": "vs prior 3 mo",
        "30d": "vs prior 30 days", "ytd": "vs prior year",
        "current_year": "vs prior year", "last_year": "vs 2 yrs ago",
        "this_month": "vs last month", "last_month": "vs 2 months ago",
        "all": "",
    }
    period_label = PERIOD_LABELS.get(date_preset, "YTD")
    trend_label = TREND_LABELS.get(date_preset, "vs prior")

    # Store raw sparkline data for clientside smoothing
    sparkline_data = {}

    def _preset_start(last_date, preset):
        return _home_preset_range(last_date, preset)[0]

    def _preset_end(last_date, preset):
        return _home_preset_range(last_date, preset)[1]

    def _spark_start(last_date, preset):
        """Sparkline window: matches the KPI window but caps 'all' at 3 years
        so the sparkline stays legible."""
        if preset == "all":
            return pd.Timestamp(last_date.year - 3, 1, 1)
        return _preset_start(last_date, preset)

    def _prior_range(last_date, preset):
        """Prior-period comparison window. 'all' has no prior — return a window
        that matches zero rows so _trend() emits no trend badge."""
        if preset == "all":
            return pd.Timestamp.min, pd.Timestamp.min
        if preset in ("ytd", "current_year"):
            try:
                pe = pd.Timestamp(last_date.year - 1, last_date.month, last_date.day)
            except ValueError:
                pe = pd.Timestamp(last_date.year - 1, last_date.month, 28)
            return pd.Timestamp(last_date.year - 1, 1, 1), _eod(pe)
        if preset == "last_year":
            return pd.Timestamp(last_date.year - 2, 1, 1), _eod(pd.Timestamp(last_date.year - 2, 12, 31))
        if preset == "this_month":
            lm_end = pd.Timestamp(last_date.year, last_date.month, 1) - pd.Timedelta(days=1)
            return pd.Timestamp(lm_end.year, lm_end.month, 1), _eod(lm_end)
        if preset == "last_month":
            lm_end = pd.Timestamp(last_date.year, last_date.month, 1) - pd.Timedelta(days=1)
            prev_end = pd.Timestamp(lm_end.year, lm_end.month, 1) - pd.Timedelta(days=1)
            return pd.Timestamp(prev_end.year, prev_end.month, 1), _eod(prev_end)
        # Rolling windows — shift back by the window length
        window_days = {"12mo": 365, "6mo": 183, "3mo": 91, "30d": 30}.get(preset, 365)
        cur_start, _ = _home_preset_range(last_date, preset)
        return cur_start - pd.Timedelta(days=window_days), _eod(cur_start - pd.Timedelta(days=1))

    def _trend(curr, prior, invert=False):
        """Return (pct_text, direction, prior_value) for trend display."""
        if prior is None or prior == 0:
            return None, None, None
        pct = (curr - prior) / prior * 100
        direction = ("down" if pct > 0 else "up") if invert else ("up" if pct > 0 else "down")
        return f"{abs(pct):.0f}%", direction, prior

    def _count_spark_raw(df, date_col, last_date):
        """Return raw sparkline data (no smoothing) as {labels, values}."""
        s_start = _spark_start(last_date, date_preset)
        s_end = _preset_end(last_date, date_preset)
        s_data = df[(df[date_col] >= s_start) & (df[date_col] <= s_end)]
        series = s_data.groupby(s_data[date_col].dt.normalize()).size()
        series = series.reindex(pd.date_range(s_start, s_end), fill_value=0)
        # Filter to business days with activity
        if hasattr(series.index, 'weekday'):
            series = series[series.index.weekday < 5]
            series = series[series > 0]
        return {
            "labels": [d.isoformat() for d in series.index],
            "values": series.tolist(),
        }

    def _lead_spark_raw(df, date_col, lead_col, last_date):
        """Return raw lead time sparkline data (no smoothing) as {labels, values}."""
        s_start = _spark_start(last_date, date_preset)
        s_end = _preset_end(last_date, date_preset)
        s_data = df[(df[date_col] >= s_start) & (df[date_col] <= s_end)]
        series = s_data.groupby(s_data[date_col].dt.normalize())[lead_col].median()
        if hasattr(series.index, 'weekday'):
            series = series[series.index.weekday < 5]
        return {
            "labels": [d.isoformat() for d in series.index],
            "values": series.tolist(),
        }

    # Load data once
    try:
        td = load_treatment_detail()
        if departments and "Department" in td.columns:
            td = td[td["Department"].isin(departments)]
    except Exception:
        td = pd.DataFrame()
    try:
        sims = load_simulations()
        if departments and "Department" in sims.columns:
            sims = sims[sims["Department"].isin(departments) | sims["Department"].isna()]
        sims = _filter_sims_scope(sims, sims_scope)
        # Filter to completed or billed simulations only
        if not sims.empty:
            completed = sims["Status"].str.contains("Completed", case=False, na=False) if "Status" in sims.columns else pd.Series(False, index=sims.index)
            billed = sims["ProcedureCodes"].notna() & (sims["ProcedureCodes"].astype(str).str.strip() != "") if "ProcedureCodes" in sims.columns else pd.Series(False, index=sims.index)
            sims = sims[completed | billed]
    except Exception:
        sims = pd.DataFrame()
    try:
        consults = _consults_full()
        if departments and "Department" in consults.columns:
            consults = consults[consults["Department"].isin(departments) | consults["Department"].isna()]
    except Exception:
        consults = pd.DataFrame()

    # --- 1. Consults ---
    if not consults.empty and "ScheduledDateTime" in consults.columns:
        last_cv = consults["ScheduledDateTime"].dt.normalize().max()
        start = _preset_start(last_cv, date_preset)
        end = _preset_end(last_cv, date_preset)
        curr = len(consults[(consults["ScheduledDateTime"] >= start) & (consults["ScheduledDateTime"] <= end)])
        ps, pe = _prior_range(last_cv, date_preset)
        prior = len(consults[(consults["ScheduledDateTime"] >= ps) & (consults["ScheduledDateTime"] <= pe)])
        pt, t_dir, pv = _trend(curr, prior)
        sparkline_data["consults"] = {
            **_count_spark_raw(consults, "ScheduledDateTime", last_cv),
            "color": CHART_COLORWAY[2],
        }
        kpi_consults = kpi_card(
            f"Consults ({period_label})", f"{curr:,}",
            trend_text=f"{pt} {trend_label} ({pv:,.0f})" if pt else None,
            trend_direction=t_dir,
            accent_color=CHART_COLORWAY[2],
            sparkline_id="home-spark-consults",
        )
    else:
        kpi_consults = kpi_card("Consults", "N/A")

    # --- 2. Simulations ---
    # Deduplicate by patient-day (matches simulations.py logic)
    if not sims.empty and "PatientId" in sims.columns and "ScheduledDateTime" in sims.columns:
        sims["_SimDate"] = sims["ScheduledDateTime"].dt.normalize()
        sims = sims.drop_duplicates(subset=["PatientId", "_SimDate"], keep="first")
    if not sims.empty and "ScheduledDateTime" in sims.columns:
        last_sim = sims["ScheduledDateTime"].dt.normalize().max()
        start = _preset_start(last_sim, date_preset)
        end = _preset_end(last_sim, date_preset)
        curr = len(sims[(sims["ScheduledDateTime"] >= start) & (sims["ScheduledDateTime"] <= end)])
        ps, pe = _prior_range(last_sim, date_preset)
        prior = len(sims[(sims["ScheduledDateTime"] >= ps) & (sims["ScheduledDateTime"] <= pe)])
        pt, t_dir, pv = _trend(curr, prior)
        sparkline_data["sims"] = {
            **_count_spark_raw(sims, "ScheduledDateTime", last_sim),
            "color": CHART_COLORWAY[1],
        }
        kpi_sims = kpi_card(
            f"Simulations ({period_label})", f"{curr:,}",
            trend_text=f"{pt} {trend_label} ({pv:,.0f})" if pt else None,
            trend_direction=t_dir,
            accent_color=CHART_COLORWAY[1],
            sparkline_id="home-spark-sims",
            header_control=_sims_scope_toggle(sims_scope),
        )
    else:
        kpi_sims = kpi_card("Simulations", "N/A",
                            header_control=_sims_scope_toggle(sims_scope))

    # --- 3. Treatments ---
    if not td.empty and "ScheduledDateTime" in td.columns:
        last_date = td["ScheduledDateTime"].dt.normalize().max()
        start = _preset_start(last_date, date_preset)
        end = _preset_end(last_date, date_preset)
        curr = len(td[(td["ScheduledDateTime"] >= start) & (td["ScheduledDateTime"] <= end)])
        ps, pe = _prior_range(last_date, date_preset)
        prior = len(td[(td["ScheduledDateTime"] >= ps) & (td["ScheduledDateTime"] <= pe)])
        pt, t_dir, pv = _trend(curr, prior)
        sparkline_data["treatments"] = {
            **_count_spark_raw(td, "ScheduledDateTime", last_date),
            "color": PRIMARY,
        }
        kpi_tx = kpi_card(
            f"Treatments ({period_label})", f"{curr:,}",
            trend_text=f"{pt} {trend_label} ({pv:,.0f})" if pt else None,
            trend_direction=t_dir,
            accent_color=PRIMARY,
            sparkline_id="home-spark-treatments",
        )
    else:
        kpi_tx = kpi_card("Treatments", "N/A", accent_color=PRIMARY)

    # --- 4. Consult Lead Time (anchored on booking date for recency) ---
    if not consults.empty and "AppointmentCreatedDate" in consults.columns:
        cl = consults[consults["AppointmentCreatedDate"].notna()].copy()
        cl["lead_days"] = (cl["ScheduledDateTime"] - cl["AppointmentCreatedDate"]).dt.days
        cl = cl[(cl["lead_days"] >= 0) & (cl["lead_days"] <= cap_consult)]
        if not cl.empty:
            last_booked = cl["AppointmentCreatedDate"].dt.normalize().max()
            start = _preset_start(last_booked, date_preset)
            end = _preset_end(last_booked, date_preset)
            curr_data = cl[(cl["AppointmentCreatedDate"] >= start) & (cl["AppointmentCreatedDate"] <= end)]
            curr_med = curr_data["lead_days"].median() if len(curr_data) > 0 else 0
            ps, pe = _prior_range(last_booked, date_preset)
            prior_data = cl[(cl["AppointmentCreatedDate"] >= ps) & (cl["AppointmentCreatedDate"] <= pe)]
            prior_med = prior_data["lead_days"].median() if len(prior_data) > 0 else None
            pt, t_dir, pv = _trend(curr_med, prior_med, invert=True)
            sparkline_data["consult_lead"] = {
                **_lead_spark_raw(cl, "AppointmentCreatedDate", "lead_days", last_booked),
                "color": CHART_COLORWAY[4],
                "hover_fmt": "%{x|%b %d}: %{y:.0f} days<extra></extra>",
            }
            _consult_info = dmc.Tooltip(
                DashIconify(icon="mdi:information-outline", width=16, color="#9CA3AF", style={"cursor": "help"}),
                label=f"Median days from booking to consult, anchored on booking date. Excludes >{cap_consult}d. Lower = shorter booking horizon.",
                position="top", withArrow=True, multiline=True, w=240,
            )
            kpi_consult_lead = kpi_card(
                f"Consult Lead Time ({period_label})", f"{curr_med:.0f}",
                value_detail="days",
                trend_text=f"{pt} {trend_label} ({pv:.0f}d)" if pt else None,
                trend_direction=t_dir,
                accent_color=CHART_COLORWAY[4],
                sparkline_id="home-spark-consult-lead",
                header_control=_consult_info,
            )
        else:
            kpi_consult_lead = kpi_card("Consult Lead Time", "N/A")
    else:
        kpi_consult_lead = kpi_card("Consult Lead Time", "N/A")

    # --- 5. Sim Lead Time (anchored on booking date for recency) ---
    if not sims.empty and "AppointmentCreatedDate" in sims.columns:
        sl = sims[sims["AppointmentCreatedDate"].notna()].copy()
        sl["lead_days"] = (sl["ScheduledDateTime"] - sl["AppointmentCreatedDate"]).dt.days
        sl = sl[(sl["lead_days"] >= 0) & (sl["lead_days"] <= cap_sim)]
        if not sl.empty:
            last_booked = sl["AppointmentCreatedDate"].dt.normalize().max()
            start = _preset_start(last_booked, date_preset)
            end = _preset_end(last_booked, date_preset)
            curr_data = sl[(sl["AppointmentCreatedDate"] >= start) & (sl["AppointmentCreatedDate"] <= end)]
            curr_med = curr_data["lead_days"].median() if len(curr_data) > 0 else 0
            ps, pe = _prior_range(last_booked, date_preset)
            prior_data = sl[(sl["AppointmentCreatedDate"] >= ps) & (sl["AppointmentCreatedDate"] <= pe)]
            prior_med = prior_data["lead_days"].median() if len(prior_data) > 0 else None
            pt, t_dir, pv = _trend(curr_med, prior_med, invert=True)
            sparkline_data["sim_lead"] = {
                **_lead_spark_raw(sl, "AppointmentCreatedDate", "lead_days", last_booked),
                "color": CHART_COLORWAY[3],
                "hover_fmt": "%{x|%b %d}: %{y:.0f} days<extra></extra>",
            }
            _sim_lead_info = dmc.Tooltip(
                DashIconify(icon="mdi:information-outline", width=16, color="#9CA3AF", style={"cursor": "help"}),
                label=f"Median days from booking to simulation, anchored on booking date. Excludes >{cap_sim}d. Lower = shorter booking horizon.",
                position="top", withArrow=True, multiline=True, w=240,
            )
            kpi_sim_lead = kpi_card(
                f"Sim Lead Time ({period_label})", f"{curr_med:.0f}",
                value_detail="days",
                trend_text=f"{pt} {trend_label} ({pv:.0f}d)" if pt else None,
                trend_direction=t_dir,
                accent_color=CHART_COLORWAY[3],
                sparkline_id="home-spark-sim-lead",
                header_control=_sim_lead_info,
            )
        else:
            kpi_sim_lead = kpi_card("Sim Lead Time", "N/A")
    else:
        kpi_sim_lead = kpi_card("Sim Lead Time", "N/A")

    return kpi_consults, kpi_sims, kpi_tx, kpi_consult_lead, kpi_sim_lead, sparkline_data


# ---------------------------------------------------------------------------
# Clientside callbacks for KPI sparklines
# ---------------------------------------------------------------------------

clientside_callback(
    ClientsideFunction(namespace="sparklines", function_name="smoothConsults"),
    Output("home-spark-consults", "figure"),
    Input("home-store-kpi-sparklines", "data"),
    Input("home-filter-smoothing", "value"),
    prevent_initial_call=True,
)

clientside_callback(
    ClientsideFunction(namespace="sparklines", function_name="smoothSims"),
    Output("home-spark-sims", "figure"),
    Input("home-store-kpi-sparklines", "data"),
    Input("home-filter-smoothing", "value"),
    prevent_initial_call=True,
)

clientside_callback(
    ClientsideFunction(namespace="sparklines", function_name="smoothTreatments"),
    Output("home-spark-treatments", "figure"),
    Input("home-store-kpi-sparklines", "data"),
    Input("home-filter-smoothing", "value"),
    prevent_initial_call=True,
)

clientside_callback(
    ClientsideFunction(namespace="sparklines", function_name="smoothConsultLead"),
    Output("home-spark-consult-lead", "figure"),
    Input("home-store-kpi-sparklines", "data"),
    Input("home-filter-smoothing", "value"),
    prevent_initial_call=True,
)

clientside_callback(
    ClientsideFunction(namespace="sparklines", function_name="smoothSimLead"),
    Output("home-spark-sim-lead", "figure"),
    Input("home-store-kpi-sparklines", "data"),
    Input("home-filter-smoothing", "value"),
    prevent_initial_call=True,
)


# ---------------------------------------------------------------------------
# Home metric callbacks (4 metrics × 2 rows = 8 cards)
# ---------------------------------------------------------------------------

def _metric_df_tx(departments):
    """Treatment-session per-row dataframe, department-filtered."""
    from data.loader import load_treatment_detail
    td = load_treatment_detail()
    if departments and "Department" in td.columns:
        return td[td["Department"].isin(departments)]
    return td


@lru_cache(maxsize=1)
def _consults_full():
    """Full classified+attended consults frame (all depts). The row-wise
    classifier is the expensive bit — run once, slice downstream."""
    from data.loader import load_clinic_visits
    return _apply_attended_filter(_classify_consults(load_clinic_visits()))


def _metric_df_consults(departments):
    """Consult rows (Attended status) from clinic visits — matches CV page KPI."""
    df = _consults_full()
    if not departments or "Department" not in df.columns:
        return df
    return df[df["Department"].isin(departments) | df["Department"].isna()]


@lru_cache(maxsize=1)
def _sims_full():
    """Full sim frame: scope=all, completed-or-billed, patient-day deduped."""
    from data.loader import load_simulations
    sims = _filter_sims_scope(load_simulations(), "all")
    if not sims.empty:
        completed = sims["Status"].str.contains("Completed", case=False, na=False) if "Status" in sims.columns else pd.Series(False, index=sims.index)
        billed = sims["ProcedureCodes"].notna() & (sims["ProcedureCodes"].astype(str).str.strip() != "") if "ProcedureCodes" in sims.columns else pd.Series(False, index=sims.index)
        sims = sims[completed | billed]
    if not sims.empty and "PatientId" in sims.columns and "ScheduledDateTime" in sims.columns:
        sims = sims.copy()
        sims["_SimDate"] = sims["ScheduledDateTime"].dt.normalize()
        sims = sims.drop_duplicates(subset=["PatientId", "_SimDate"], keep="first")
    return sims


def _metric_df_sims(departments):
    """Simulation rows (completed or billed, sim-like activities), patient-day deduped.

    Uses the "all" scope (blacklist of placeholder activities) so the trend/cum
    chart totals match the simulations page's "Total Simulations" KPI.
    """
    df = _sims_full()
    if not departments or "Department" not in df.columns:
        return df
    return df[df["Department"].isin(departments) | df["Department"].isna()]


@lru_cache(maxsize=1)
def _refs_with_derived_columns():
    """Build the full referrals dataframe with _OurDept and _DxCat added.

    The .apply row-loop is the expensive part — cache it once so the 2+
    store callbacks (trend + cum) and any other consumer share one pass.
    Department filtering is cheap; do it downstream in the non-cached layer.
    """
    from data.loader import load_referrals
    from pages.referrals import _categorise_diagnosis as _ref_dx, _map_to_our_dept as _ref_dept
    refs = load_referrals()
    if refs.empty or "Created" not in refs.columns:
        return refs.iloc[0:0] if not refs.empty else refs
    refs = refs.copy()
    # "Referred to Department" records our site (Lacey/Centralia/Aberdeen);
    # "Referred by Department" is the external referring office and is wrong here.
    if "Referred to Department" in refs.columns:
        refs["_OurDept"] = refs["Referred to Department"].apply(_ref_dept)
    else:
        refs["_OurDept"] = None
    refs["_DxCat"] = refs.apply(
        lambda r: _ref_dx(r.get("Diagnoses"), r.get("Rfl Prim Dx"), r.get("MRN")),
        axis=1,
    )
    return refs


def _metric_df_refs(departments):
    """Referrals with derived _OurDept (our dept mapping) and _DxCat (diagnosis) columns."""
    refs = _refs_with_derived_columns()
    if refs.empty or not departments:
        return refs
    return refs[refs["_OurDept"].isin(departments)]


# (date_col, unique_id_col-or-None, dim→groupcol map, dataframe loader)
# "total" dim is synthesized — builder injects a single-valued column.
# Physician columns chosen to match the dedicated pages + minimise nulls:
#   consults → AppointmentPhysician (CV page uses this; 0 nulls vs 3 for Attending)
#   sims     → ConsultPhysician     (sim page default; 6 nulls vs 25 for Attending)
#   tx       → TreatingPhysician    (0 nulls)
_METRIC_SPECS = {
    "tx":       ("ScheduledDateTime", None,        {"total": "_Total", "department": "Department", "physician": "TreatingPhysician"},   _metric_df_tx),
    "consults": ("ScheduledDateTime", "PatientId", {"total": "_Total", "department": "Department", "physician": "AppointmentPhysician"}, _metric_df_consults),
    "sims":     ("ScheduledDateTime", None,        {"total": "_Total", "department": "Department", "physician": "ConsultPhysician"},    _metric_df_sims),
    "refs":     ("Created",           None,        {"total": "_Total", "department": "_OurDept",   "diagnosis": "_DxCat"},               _metric_df_refs),
}

_METRIC_YTITLE = {
    "tx": "Treatments", "consults": "Consults", "sims": "Simulations", "refs": "Referrals",
}


def _build_metric_census_store(metric_id, departments, dim, agg, date_preset):
    """Build a census-style {dates, series, height, yTitle} dict for a home metric card."""
    spec = _METRIC_SPECS.get(metric_id)
    if spec is None:
        return None
    date_col, unique_col, dim_map, frame_fn = spec

    dim = dim or "department"
    group_col = dim_map.get(dim)
    if group_col is None:
        return None

    try:
        df = frame_fn(departments)
    except Exception:
        return None
    if df is None or df.empty or date_col not in df.columns:
        return None

    df = df[df[date_col].notna()].copy()
    if df.empty:
        return None

    # Filter to the home date-preset range (data-relative)
    last_date = df[date_col].dt.normalize().max()
    start, end = _home_preset_range(last_date, date_preset)
    df = df[(df[date_col] >= start) & (df[date_col] <= end + pd.Timedelta(days=1))]
    if df.empty:
        return None

    # Synthesize the "total" group column
    if dim == "total":
        df["_Total"] = "Total"
    elif group_col not in df.columns:
        return None

    df = df[df[group_col].notna()]
    df["_Date"] = df[date_col].dt.normalize()
    df = df[df[group_col].astype(str).str.strip() != ""]
    if df.empty:
        return None

    agg = agg or "D"
    if agg in ("W", "M"):
        df["_period"] = df["_Date"].dt.to_period(agg).dt.to_timestamp()
        dkey = "_period"
        if unique_col and unique_col in df.columns:
            daily = df.groupby([dkey, group_col])[unique_col].nunique().reset_index(name="count")
        else:
            daily = df.groupby([dkey, group_col]).size().reset_index(name="count")
        date_range = sorted(daily[dkey].unique())
    else:
        dkey = "_Date"
        if unique_col and unique_col in df.columns:
            daily = df.groupby([dkey, group_col])[unique_col].nunique().reset_index(name="count")
        else:
            daily = df.groupby([dkey, group_col]).size().reset_index(name="count")
        if daily.empty:
            return None
        date_range = pd.bdate_range(df["_Date"].min(), df["_Date"].max())
        totals = daily.groupby(dkey)["count"].sum()
        active = totals[totals > 0].index
        date_range = date_range[date_range.isin(active)]

    if len(date_range) == 0:
        return None

    # Order groups by total desc (dominant series first → better stacking)
    totals = daily.groupby(group_col)["count"].sum().sort_values(ascending=False)
    groups = totals.index.tolist()

    is_dept = (dim == "department")
    is_total = (dim == "total")
    series = []
    color_idx = 0
    for grp in groups:
        grp_raw = daily[daily[group_col] == grp].set_index(dkey)["count"]
        if grp_raw.empty or (grp_raw <= 0).all():
            continue
        grp_full = grp_raw.reindex(date_range)
        positive = grp_raw[grp_raw > 0]
        first_active = positive.index.min() if not positive.empty else grp_raw.index.min()
        last_active = positive.index.max() if not positive.empty else grp_raw.index.max()
        values = [
            None if (p < first_active or p > last_active)
            else (int(v) if pd.notna(v) else 0)
            for p, v in zip(date_range, grp_full)
        ]
        name = str(grp)
        display_name = name.split(",")[0] if "," in name else name
        if is_total:
            c = PRIMARY
        elif is_dept:
            c = DEPARTMENT_COLORS.get(name, CHART_COLORWAY[color_idx % len(CHART_COLORWAY)])
        else:
            c = CHART_COLORWAY[color_idx % len(CHART_COLORWAY)]
        color_idx += 1
        series.append({"name": display_name, "values": values, "color": c})

    if not series:
        return None

    result = {
        "dates": [pd.Timestamp(d).isoformat() for d in date_range],
        "series": series,
        "height": 280,
        "yTitle": _METRIC_YTITLE.get(metric_id, "Count"),
    }
    if len(series) <= 1:
        result["hideLegend"] = True
    if not is_dept and not is_total:
        result["dynamicColors"] = True
    return result


def _build_current_year_yoy_cumulative(metric_id, departments, n_prior=4):
    """Build a YoY cumulative store in the "prior" mode schema expected by
    window.dash_clientside.cumulative.renderCumulative (matches treatment.py
    and other pages' cumulative charts).

    Current (partial) year + up to N prior full years, all aligned to the
    display year's calendar so prior-year dates map to the same day-of-year.
    """
    spec = _METRIC_SPECS.get(metric_id)
    if spec is None:
        return None
    date_col, unique_col, _dim_map, frame_fn = spec

    try:
        df = frame_fn(departments)
    except Exception:
        return None
    if df is None or df.empty or date_col not in df.columns:
        return None

    df = df[df[date_col].notna()].copy()
    if df.empty:
        return None

    last_date = df[date_col].dt.normalize().max()
    display_year = last_date.year
    year_start = pd.Timestamp(display_year, 1, 1)
    year_end = pd.Timestamp(display_year, 12, 31)
    year_cal = pd.date_range(year_start, year_end, freq="D")
    n_days = len(year_cal)
    day_indices = list(range(n_days))

    # Month-center tick labels (Jan, Feb, …) so each label sits between the
    # month's first and last day rather than left-anchored at day 1.
    tick_positions, tick_labels = [], []
    for month in range(1, 13):
        m_start = pd.Timestamp(display_year, month, 1)
        m_end = m_start + pd.offsets.MonthEnd(0)
        mid = ((m_start - year_start).days + (m_end - year_start).days) / 2
        tick_positions.append(mid)
        tick_labels.append(m_start.strftime("%b"))

    def _shift_to_display(d):
        try:
            return pd.Timestamp(display_year, d.month, d.day)
        except ValueError:
            return None  # Feb 29 in non-leap display year

    def _year_series(year):
        ys = pd.Timestamp(year, 1, 1)
        ye = pd.Timestamp(year, 12, 31)
        year_df = df[(df[date_col] >= ys) & (df[date_col] <= ye)]
        if year_df.empty:
            return None, 0.0
        year_df = year_df.copy()
        year_df["_Date"] = year_df[date_col].dt.normalize()
        if unique_col and unique_col in year_df.columns:
            daily = year_df.groupby("_Date")[unique_col].nunique()
        else:
            daily = year_df.groupby("_Date").size()
        cal = pd.date_range(ys, ye, freq="D")
        daily = daily.reindex(cal, fill_value=0)
        cum = daily.cumsum().astype(float)
        if year == display_year:
            cum = cum.where(cum.index <= last_date)
        shifted = {}
        for d, v in cum.items():
            sd = _shift_to_display(d)
            if sd is not None:
                shifted[sd] = v
        aligned = pd.Series(shifted).reindex(year_cal)
        vals = [None if pd.isna(v) else float(v) for v in aligned]
        total = float(next((v for v in reversed(vals) if v is not None), 0.0))
        return vals, total

    current_vals, current_total = _year_series(display_year)
    if current_vals is None:
        return None

    prior = []
    year_totals = {str(display_year): current_total}
    for offset in range(1, n_prior + 1):
        vals, total = _year_series(display_year - offset)
        if vals is None:
            break
        prior.append({
            "label": str(display_year - offset),
            "values": vals,
            "color": PRIOR_PERIOD_COLORS[min(offset - 1, len(PRIOR_PERIOD_COLORS) - 1)],
        })
        year_totals[str(display_year - offset)] = total

    # Year-end projection: linear extrapolation of YTD pace through Dec 31.
    last_idx = (last_date - year_start).days
    days_elapsed = last_idx + 1
    rate = current_total / days_elapsed if days_elapsed > 0 else 0.0
    projected_end = current_total + rate * (n_days - days_elapsed)
    projected_remainder = max(0.0, projected_end - current_total)
    projection_current = {
        "startIdx": last_idx,
        "startVal": current_total,
        "endIdx": n_days - 1,
        "endVal": projected_end,
    }

    # Bar-mode breakdown: one slice ("Total") across year-periods oldest → newest
    periods_asc = sorted(year_totals.keys())
    y_title = _METRIC_YTITLE.get(metric_id, "Total")
    slice_breakdown = {
        "periods": periods_asc,
        "slices": [{
            "name": y_title,
            "values": [year_totals[p] for p in periods_asc],
            "color": PRIMARY,
        }],
    }

    return {
        "mode": "prior",
        "startDate": year_start.isoformat(),
        "dayIndices": day_indices,
        "tickPositions": tick_positions,
        "tickLabels": tick_labels,
        "current": {
            "label": str(display_year),
            "values": current_vals,
            "color": PRIMARY,
            "endpoint": current_total,
            "projection": projection_current,
        },
        "prior": prior,
        "sliceBreakdown": slice_breakdown,
        "projectionTotal": {
            "periodIdx": periods_asc.index(str(display_year)),
            "remainder": float(projected_remainder),
            "endVal": float(projected_end),
        },
        "periodDays": n_days,
        "maxAvailablePriors": len(prior),
        "hasPartialPrior": False,
        "height": 300,
        "yTitle": y_title,
        "hidePriorEndpointLabels": True,
    }


def _rolling_ticks(start, n_days):
    """Pick tick positions (day indices 0..n_days-1) + labels for a rolling window."""
    if n_days <= 14:
        step, fmt = 1, "%b %d"
    elif n_days <= 45:
        step, fmt = 7, "%b %d"
    elif n_days <= 120:
        step, fmt = 14, "%b %d"
    elif n_days <= 400:
        step, fmt = 30, "%b"
    elif n_days <= 800:
        step, fmt = 60, "%b '%y"
    elif n_days <= 1825:
        step, fmt = 180, "%b '%y"
    else:
        step, fmt = 365, "%Y"
    positions, labels = [], []
    i = 0
    while i < n_days:
        d = start + pd.Timedelta(days=i)
        positions.append(i)
        labels.append(d.strftime(fmt))
        i += step
    return positions, labels


def _rolling_label(start, end, n_days):
    if n_days <= 31:
        return f"{start.strftime('%b %d')}–{end.strftime('%b %d, %Y')}"
    if n_days <= 365:
        return f"{start.strftime('%b %Y')}–{end.strftime('%b %Y')}"
    return f"{start.year}–{end.year}"


def _build_rolling_cumulative(metric_id, departments, date_preset, n_prior=3):
    """Rolling-window prior-mode cumulative store.

    Current window = selected preset's date range. Prior windows = preceding
    same-length windows, aligned on a shared day axis. Output matches
    `renderCumulative` "prior" mode so endpoint annotation + prior-period
    lines render automatically for any preset (except current_year, which has
    its own calendar-year-aligned builder).
    """
    spec = _METRIC_SPECS.get(metric_id)
    if spec is None:
        return None
    date_col, unique_col, _dim_map, frame_fn = spec
    try:
        df = frame_fn(departments)
    except Exception:
        return None
    if df is None or df.empty or date_col not in df.columns:
        return None
    df = df[df[date_col].notna()].copy()
    if df.empty:
        return None

    last_date = df[date_col].dt.normalize().max()
    start_ts, end_ts = _home_preset_range(last_date, date_preset)
    if start_ts is pd.Timestamp.min:
        # "all" — start from the earliest data point; no prior windows exist.
        start = df[date_col].dt.normalize().min()
    else:
        start = start_ts.normalize()
    end = min(last_date, end_ts.normalize())
    n_days = (end - start).days + 1
    if n_days <= 0:
        return None

    def _window_cum(win_start, win_end):
        ws = pd.Timestamp(win_start).normalize()
        we = pd.Timestamp(win_end).normalize()
        sub = df[(df[date_col] >= ws) &
                 (df[date_col] < we + pd.Timedelta(days=1))]
        cal = pd.date_range(ws, we, freq="D")
        if sub.empty:
            return [0.0] * len(cal), 0.0
        dn = sub[date_col].dt.normalize()
        if unique_col and unique_col in sub.columns:
            daily = sub.groupby(dn)[unique_col].nunique()
        else:
            daily = sub.groupby(dn).size()
        daily = daily.reindex(cal, fill_value=0)
        cum = daily.cumsum().astype(float).tolist()
        return cum, (float(cum[-1]) if cum else 0.0)

    current_vals, current_total = _window_cum(start, end)

    prior = []
    first_data = df[date_col].dt.normalize().min()
    priors_start = start
    priors_allowed = (start_ts is not pd.Timestamp.min)

    # YTD: compare against the same calendar span (Jan 1 → same month/day) in
    # prior years instead of rolling backward by n_days. Gives "Jan–Apr 2025
    # vs Jan–Apr 2024" semantics users expect.
    if priors_allowed and date_preset == "ytd":
        cur_year = start.year
        for offset in range(1, n_prior + 1):
            y = cur_year - offset
            try:
                p_start = pd.Timestamp(y, start.month, start.day)
                p_end = pd.Timestamp(y, end.month, end.day)
            except ValueError:
                # Feb 29 in a non-leap prior year — clip to Feb 28.
                p_start = pd.Timestamp(y, 1, 1)
                p_end = pd.Timestamp(y, end.month, min(end.day, 28))
            if p_end < first_data:
                break
            clipped_start = max(p_start, first_data)
            vals, _ = _window_cum(clipped_start, p_end)
            # Length may differ by 1 on leap-year boundaries — align to n_days.
            if len(vals) < n_days:
                vals = vals + [vals[-1] if vals else None] * (n_days - len(vals))
            elif len(vals) > n_days:
                vals = vals[:n_days]
            prior.append({
                "label": str(y),
                "values": vals,
                "color": PRIOR_PERIOD_COLORS[min(offset - 1, len(PRIOR_PERIOD_COLORS) - 1)],
            })
    elif priors_allowed:
        for offset in range(1, n_prior + 1):
            p_end = priors_start - pd.Timedelta(days=1)
            p_start = p_end - pd.Timedelta(days=n_days - 1)
            if p_end < first_data:
                break
            # Clip prior window to available data; left-pad with nulls so
            # day indices align with the current window.
            clipped_start = max(p_start, first_data)
            vals, _ = _window_cum(clipped_start, p_end)
            if len(vals) < n_days:
                vals = [None] * (n_days - len(vals)) + vals
            prior.append({
                "label": _rolling_label(p_start, p_end, n_days),
                "values": vals,
                "color": PRIOR_PERIOD_COLORS[min(offset - 1, len(PRIOR_PERIOD_COLORS) - 1)],
            })
            priors_start = p_start

    tick_positions, tick_labels = _rolling_ticks(start, n_days)
    return {
        "mode": "prior",
        "startDate": pd.Timestamp(start).isoformat(),
        "dayIndices": list(range(n_days)),
        "tickPositions": tick_positions,
        "tickLabels": tick_labels,
        "current": {
            "label": _rolling_label(start, end, n_days),
            "values": current_vals,
            "color": PRIMARY,
            "endpoint": current_total,
        },
        "prior": prior,
        "periodDays": n_days,
        "maxAvailablePriors": len(prior),
        "hasPartialPrior": False,
        "height": 300,
        "yTitle": _METRIC_YTITLE.get(metric_id, "Total"),
        "hidePriorEndpointLabels": True,
    }


def _register_metric_callbacks(metric_id, row, is_cumulative):
    """Wire one card's data callback + render + axis callbacks."""
    sid = f"home-{metric_id}-{row}"
    cid = f"home-chart-{metric_id}-{row}"
    store_id = f"home-{metric_id}-{row}-store"

    @callback(
        Output(store_id, "data"),
        Input("home-interval", "n_intervals"),
        Input("home-filter-date-preset", "value"),
        Input("home-filter-department", "value"),
        Input(f"{sid}-dim", "value"),
        Input(f"{sid}-agg", "value"),
        running=[(Output(f"{cid}-loading", "visible"), True, False)],
    )
    def _update_store(_n, date_preset, departments, dim, agg):
        if is_cumulative and date_preset == "current_year":
            return _build_current_year_yoy_cumulative(metric_id, departments)
        if is_cumulative:
            # All other presets: rolling-window prior-mode store so the cum
            # card renders a single purple total with endpoint annotation and
            # N prior windows behind it. Falls back to a total slice-mode
            # store if the rolling builder returns nothing (e.g. empty data).
            store = _build_rolling_cumulative(metric_id, departments, date_preset)
            if store is not None:
                return store
            return _build_metric_census_store(metric_id, departments, "total", "D", date_preset)
        return _build_metric_census_store(metric_id, departments, dim, agg, date_preset)

    _update_store.__name__ = f"update_{metric_id}_{row}_store"

    if is_cumulative:
        clientside_callback(
            ClientsideFunction(namespace="census", function_name="homeCumulative"),
            Output(cid, "figure"),
            Input(store_id, "data"),
            Input(f"{sid}-settings-smooth", "value"),
            Input(f"{sid}-settings-type", "value"),
            Input("home-cum-prior-store", "data"),
            Input(f"{sid}-project", "checked"),
            State(cid, "figure"),
            prevent_initial_call=True,
        )
        # Projection toggle is only relevant in current_year preset.
        clientside_callback(
            """function(preset) {
                return preset === "current_year" ? {} : {"display": "none"};
            }""",
            Output(f"{sid}-project-wrap", "style"),
            Input("home-filter-date-preset", "value"),
        )
        # Each card's slider publishes to the shared store so any card drives
        # the whole cumulative row.
        clientside_callback(
            "function(v) { return v; }",
            Output("home-cum-prior-store", "data", allow_duplicate=True),
            Input(f"{sid}-settings-prior-periods", "value"),
            prevent_initial_call=True,
        )
        # Store writes back to keep other cards' sliders visually in sync.
        clientside_callback(
            "function(v) { return v; }",
            Output(f"{sid}-settings-prior-periods", "value", allow_duplicate=True),
            Input("home-cum-prior-store", "data"),
            prevent_initial_call=True,
        )
    else:
        clientside_callback(
            ClientsideFunction(namespace="census", function_name="homeTrend"),
            Output(cid, "figure"),
            Input(store_id, "data"),
            Input(f"{sid}-settings-smooth", "value"),
            Input(f"{sid}-settings-type", "value"),
            Input(f"{sid}-settings-stack", "value"),
            State(cid, "figure"),
            prevent_initial_call=True,
        )
        clientside_callback(
            ClientsideFunction(namespace="censusYAxis", function_name="updateOnPan"),
            Output(cid, "figure", allow_duplicate=True),
            Input(cid, "relayoutData"),
            State(cid, "figure"),
            State(store_id, "data"),
            State(f"{sid}-settings-type", "value"),
            State(f"{sid}-settings-stack", "value"),
            prevent_initial_call=True,
        )


_SLICE_CLASS_JS = """function(val) {
    return (val && val !== "total") ? "slice-group-active" : "slice-total-active";
}"""
_HIDE_STACK_JS = """function(sliceVal, chartType) {
    var single = !sliceVal || sliceVal === "total";
    return (single || chartType === "line") ? {"display": "none"} : {};
}"""


for _m, _t, _d, _defaults in _HOME_METRICS:
    _register_metric_callbacks(_m, "trend", is_cumulative=False)
    _register_metric_callbacks(_m, "cum",   is_cumulative=True)

    for _row in ("trend", "cum"):
        _sid = f"home-{_m}-{_row}"
        # Dim visual: slice-total-active / slice-group-active className
        clientside_callback(
            _SLICE_CLASS_JS,
            Output(f"{_sid}-dim", "className"),
            Input(f"{_sid}-dim", "value"),
        )

    # Trend cards only: hide Stacked/Grouped when Total dim or Line chart
    _trend_sid = f"home-{_m}-trend"
    clientside_callback(
        _HIDE_STACK_JS,
        Output(f"{_trend_sid}-settings-stack-wrap", "style", allow_duplicate=True),
        Input(f"{_trend_sid}-dim", "value"),
        Input(f"{_trend_sid}-settings-type", "value"),
        prevent_initial_call="initial_duplicate",
    )

    # Cum cards are always total-only (single purple line) regardless of
    # preset — hide the dim/agg toggles in every preset. They only apply to
    # the paired trend card; the store builder forces dim="total", agg="D"
    # on the cumulative side.
    _cum_sid = f"home-{_m}-cum"
    clientside_callback(
        """function(_preset) { return {"display": "none"}; }""",
        Output(f"{_cum_sid}-dim", "style"),
        Input("home-filter-date-preset", "value"),
    )
    clientside_callback(
        """function(_preset) { return {"display": "none"}; }""",
        Output(f"{_cum_sid}-agg", "style"),
        Input("home-filter-date-preset", "value"),
    )


def _eod(ts):
    """End-of-day for `ts` so `<= end` covers the entire calendar date.

    `last_date` here comes from `ScheduledDateTime.dt.normalize().max()` — midnight
    of the last day with activity. A naive `<= last_date` check would drop every
    appointment scheduled after midnight on that day.
    """
    if ts is None or ts is pd.Timestamp.min:
        return ts
    return ts.normalize() + pd.Timedelta(days=1) - pd.Timedelta(microseconds=1)


def _home_preset_range(last_date, preset):
    """Return (start_ts, end_ts) for the home date-preset, data-relative.

    End timestamp is end-of-day so same-day rows after midnight are included.

    Home shares the 9 standard presets used by filter-bar pages:
    12mo / 6mo / 3mo / 30d / ytd / last_year / this_month / last_month / all.
    """
    preset = preset or "ytd"
    if preset == "all":
        return pd.Timestamp.min, _eod(last_date)
    if preset in ("ytd", "current_year"):
        # Data filter is identical — the full-year x-axis framing for
        # current_year lives in the cumulative renderer, not here.
        return pd.Timestamp(last_date.year, 1, 1), _eod(last_date)
    if preset == "last_year":
        return pd.Timestamp(last_date.year - 1, 1, 1), _eod(pd.Timestamp(last_date.year - 1, 12, 31))
    if preset == "this_month":
        return pd.Timestamp(last_date.year, last_date.month, 1), _eod(last_date)
    if preset == "last_month":
        lm_end = pd.Timestamp(last_date.year, last_date.month, 1) - pd.Timedelta(days=1)
        return pd.Timestamp(lm_end.year, lm_end.month, 1), _eod(lm_end)
    if preset == "6mo":
        return last_date - pd.DateOffset(months=6), _eod(last_date)
    if preset == "3mo":
        return last_date - pd.DateOffset(months=3), _eod(last_date)
    if preset == "30d":
        return last_date - pd.Timedelta(days=30), _eod(last_date)
    # 12mo (default)
    return last_date - pd.DateOffset(months=12), _eod(last_date)


# ---------------------------------------------------------------------------
# Operating Hours Ribbon — reusable component callbacks + server data
# ---------------------------------------------------------------------------

if not _already_registered:
    register_hours_ribbon_callbacks("home")
    register_outlier_callbacks(PAGE_ID, n_transitions=2, defaults=[_CAP_CONSULT_LEAD, _CAP_SIM_LEAD])

@callback(
    Output("home-store-hours", "data"),
    Input("home-interval", "n_intervals"),
    Input("home-hours-site", "value"),
    running=[(Output("home-hours-loading", "visible"), True, False)],
)
def update_hours_data(_n, site_filter):
    """Load ALL operating hours data to store (range applied clientside)."""
    if site_filter and site_filter != "all":
        sites = [site_filter]
    else:
        sites = None
    return _prepare_hours_data(sites, days_back=0)


# ---------------------------------------------------------------------------
# Availability Calendar Callback
# ---------------------------------------------------------------------------

@callback(
    Output("home-chart-availability", "figure"),
    Input("home-interval", "n_intervals"),
    Input("home-filter-department", "value"),
    Input("home-avail-scope", "value"),
    running=[(Output("home-chart-availability-loading", "visible"), True, False)],
)
def update_availability_calendar(_n, departments, scope):
    """Update slot availability calendar (shows both Exam and Sim)."""
    consults_only = scope != "all"
    return _build_availability_calendar(departments, consults_only=consults_only)


# Hover highlight on availability heatmap cells
clientside_callback(
    ClientsideFunction(namespace="heatmapHover", function_name="initHome"),
    Output("home-chart-availability", "className"),
    Input("home-chart-availability", "figure"),
    prevent_initial_call=True,
)


# ---------------------------------------------------------------------------
# Settings Panel Toggle Callbacks
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Settings toggle + PNG export (clientside via shared helpers)
# ---------------------------------------------------------------------------
if not _already_registered:
    _home_chart_registry = []
    for _m, _t, _d, _defaults in _HOME_METRICS:
        _home_chart_registry.append((f"home-{_m}-trend", f"home-chart-{_m}-trend", f"home-{_m}-trend-store"))
        # Cum cards have show_grouping=False (see chart_card call above) — no
        # stack-wrap element in DOM, so tell register_chart_callbacks to skip
        # that Output (batched callbacks can't tolerate missing outputs).
        _home_chart_registry.append({
            "sid": f"home-{_m}-cum",
            "gid": f"home-chart-{_m}-cum",
            "store_id": f"home-{_m}-cum-store",
            "show_grouping": False,
        })
    _home_chart_registry.append(("home-avail", "home-chart-availability"))
    register_chart_callbacks(_home_chart_registry)
