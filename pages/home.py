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

from config.settings import (
    DEPARTMENTS, DEPARTMENT_COLORS, CHART_COLORWAY, PRIMARY,
    DEFAULT_LAYOUT, FONT_FAMILY, SEMANTIC_COLORS,
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


import re

# Regex patterns for consult classification (compiled once at module level)
_FOLLOWUP_PATTERNS = re.compile(
    r"follow[\s-]?up|re[\s-]?eval|followup|reeval|\bphone\b|\btelephone\b|f/u|review|discuss|go\s+over",
    re.IGNORECASE
)
_NEWPATIENT_PATTERNS = re.compile(r"working\s+chart|bookmarked", re.IGNORECASE)
_EXPLICIT_CONSULT_NAMES = {"consult", "consult - special request", "consult- add on"}


def _is_consult(row):
    """Classify a clinic visit row as consult (True) or follow-up (False).

    Priority-based decision tree from legacy logic:
    1. Duration > 60 minutes → Consult
    2. ActivityName is explicit consult type → Consult (unless note matches follow-up pattern)
    3. Virtual Consult/Follow Up with duration < 60 → check notes, default Follow-Up
    4. Virtual Consult/Follow Up with duration = 60 → check notes, default Consult
    5. Any other activity type → Consult (fallback)
    """
    activity = str(row.get("ActivityName", "")).strip().lower()
    duration = row.get("DurationMinutes", 0) or 0
    notes = str(row.get("AppointmentNotes", "") or "")

    # Rule 1: Long appointments are consults
    if duration > 60:
        return True

    # Rule 2: Explicit consult activity names
    if activity in _EXPLICIT_CONSULT_NAMES:
        # Unless notes indicate follow-up
        if _FOLLOWUP_PATTERNS.search(notes):
            return False
        return True

    # Rule 3 & 4: Virtual Consult/Follow Up — ambiguous, check duration + notes
    if "virtual" in activity and "consult" in activity:
        if duration < 60:
            # Default to follow-up unless new patient indicators present
            if _NEWPATIENT_PATTERNS.search(notes):
                return True
            return False
        elif duration == 60:
            # Default to consult unless follow-up indicators present
            if _FOLLOWUP_PATTERNS.search(notes):
                return False
            return True
        else:
            # duration > 60 already handled above
            return True

    # Rule 5: Fallback — if "consult" in name but not matched above, treat as consult
    if "consult" in activity:
        return True

    # Not a consult activity
    return False


dash.register_page(__name__, path="/", name="Home", order=0)


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
        today = pd.Timestamp.now().normalize()
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

def _build_availability_calendar(departments, consults_only=True):
    """Build 4-week availability calendar with Exam and Sim side by side.

    Layout: Mon-Fri as columns (like a calendar), weeks as rows.
    Shows % booked (scheduled / total capacity) for each day.
    Green (<50%), Yellow (50-80%), Red (>80%)
    Includes median lead time for future scheduled appointments.

    Args:
        departments: list of departments to filter by, or None/empty for all.
        consults_only: if True, filter consult calendar to Consult activities only.
    """
    from data.loader import load_availability, load_clinic_visits, load_simulations

    try:
        today = pd.Timestamp.now().normalize()
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
            """Build z-data grid only."""
            z = []
            for week_start in weeks:
                row = []
                for day_idx in range(5):
                    td = week_start + timedelta(days=day_idx)
                    row.append(pct_series[td] if td in pct_series.index else None)
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

        # Create subplots - two heatmaps side by side
        exam_title = "Consults" if consults_only else "All Clinic Visits"
        fig = make_subplots(
            rows=1, cols=2,
            subplot_titles=[exam_title, "Simulations"],
            horizontal_spacing=0.12,
        )

        colorscale = [
            [0, "#4CAF50"],       # Green - wide open
            [0.50, "#8BC34A"],    # Light green - half full
            [0.75, "#FFC107"],    # Amber - filling up
            [0.90, "#FF9800"],    # Orange - almost full
            [1, "#D32F2F"],       # Dark red - no availability
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

        exam_labels = _cell_labels(exam_pct, exam_scheduled, exam_total)
        sim_labels = _cell_labels(sim_pct, sim_scheduled, sim_total)

        # Exam heatmap
        fig.add_trace(go.Heatmap(
            z=exam_z,
            x=x_labels,
            y=y_labels_exam,
            colorscale=colorscale,
            zmin=0, zmax=100,
            text=exam_hover,
            hovertemplate="%{text}<extra></extra>",
            showscale=False,
        ), row=1, col=1)

        # Sim heatmap
        fig.add_trace(go.Heatmap(
            z=sim_z,
            x=x_labels,
            y=y_labels_sim,
            colorscale=colorscale,
            zmin=0, zmax=100,
            text=sim_hover,
            hovertemplate="%{text}<extra></extra>",
            showscale=False,
        ), row=1, col=2)

        # Add lead time annotations at bottom
        annotations = list(fig.layout.annotations)  # Keep subplot titles
        # Move subplot titles up
        for ann in annotations:
            ann.y = 1.08
            ann.font = dict(size=12, color="#374151")

        # Overlay cell labels as annotations
        for row_idx, week_start in enumerate(weeks):
            for col_idx in range(5):
                for subplot_col, labels, ylbls in [
                    (1, exam_labels, y_labels_exam),
                    (2, sim_labels, y_labels_sim),
                ]:
                    label = labels[row_idx][col_idx]
                    if not label:
                        continue
                    is_full = label == "Full"
                    ax_suffix = "" if subplot_col == 1 else "2"
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
        for lead, xref, yref in [
            (exam_lead, "x domain", "y domain"),
            (sim_lead, "x2 domain", "y2 domain"),
        ]:
            if lead is not None:
                label = "Today" if lead == 0 else f"{lead}d out"
                annotations.append(dict(
                    text=f"Next available: {label}",
                    xref=xref, yref=yref,
                    x=0.5, y=-0.06,
                    showarrow=False,
                    font=dict(size=13, color="#6B7280"),
                    xanchor="center",
                ))

        fig.update_layout(
            height=380,
            font=dict(family=FONT_FAMILY, size=11),
            plot_bgcolor="#FFFFFF",
            paper_bgcolor="#FFFFFF",
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
        fig.update_xaxes(side="top", tickfont=dict(size=10))
        fig.update_yaxes(tickfont=dict(size=10), autorange="reversed")

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
                                        {"value": "today", "label": "Today"},
                                        {"value": "week", "label": "7 Days"},
                                        {"value": "month", "label": "30 Days"},
                                        {"value": "quarter", "label": "3 Mo"},
                                        {"value": "12mo", "label": "12 Mo"},
                                        {"value": "lastyear", "label": "Last Year"},
                                        {"value": "ytd", "label": "YTD"},
                                    ],
                                    value="ytd", size="sm",
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

        # Census charts — side by side
        dmc.Grid(
            gutter=16,
            children=[
                dmc.GridCol(
                    span={"base": 12, "md": 6},
                    children=chart_card(
                        "home-chart-physician",
                        "Active Patients by Physician",
                        settings_id="home-md",
                        chart_types=[
                            {"value": "area", "label": "Area"},
                            {"value": "line", "label": "Line"},
                            {"value": "bar", "label": "Bar"},
                        ],
                        smooth_max=50, smooth_default=15,
                        extra_controls=[
                            dmc.SegmentedControl(
                                id="home-md-agg",
                                data=[
                                    {"value": "D", "label": "Daily"},
                                    {"value": "W", "label": "Weekly"},
                                    {"value": "M", "label": "Monthly"},
                                ],
                                value="D", size="xs",
                            ),
                            dmc.SegmentedControl(
                                id="home-md-range",
                                data=[
                                    {"value": "30", "label": "30d"},
                                    {"value": "60", "label": "60d"},
                                    {"value": "90", "label": "90d"},
                                    {"value": "180", "label": "6mo"},
                                    {"value": "365", "label": "1y"},
                                    {"value": "0", "label": "All"},
                                ],
                                value="90", size="xs",
                            ),
                        ],
                    ),
                ),
                dmc.GridCol(
                    span={"base": 12, "md": 6},
                    children=chart_card(
                        "home-chart-site",
                        "Treatments by Site",
                        settings_id="home-site",
                        chart_types=[
                            {"value": "area", "label": "Area"},
                            {"value": "line", "label": "Line"},
                            {"value": "bar", "label": "Bar"},
                        ],
                        smooth_max=50, smooth_default=15,
                        extra_controls=[
                            dmc.SegmentedControl(
                                id="home-site-agg",
                                data=[
                                    {"value": "D", "label": "Daily"},
                                    {"value": "W", "label": "Weekly"},
                                    {"value": "M", "label": "Monthly"},
                                ],
                                value="D", size="xs",
                            ),
                            dmc.SegmentedControl(
                                id="home-site-range",
                                data=[
                                    {"value": "30", "label": "30d"},
                                    {"value": "60", "label": "60d"},
                                    {"value": "90", "label": "90d"},
                                    {"value": "180", "label": "6mo"},
                                    {"value": "365", "label": "1y"},
                                    {"value": "0", "label": "All"},
                                ],
                                value="90", size="xs",
                            ),
                        ],
                    ),
                ),
            ],
        ),

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

        # Stores for raw census data (clientside smoothing)
        dcc.Store(id="home-store-md-census"),
        dcc.Store(id="home-store-site-census"),

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
        "today": "Today", "week": "7 Days",
        "month": "30 Days", "quarter": "3 Mo",
        "12mo": "12 Mo", "lastyear": "Last Year", "ytd": "YTD",
    }
    TREND_LABELS = {
        "today": "vs yesterday", "week": "vs prior 7d",
        "month": "vs prior 30d", "quarter": "vs prior 3 mo",
        "12mo": "vs prior 12 mo", "lastyear": "vs prior year",
        "ytd": "vs prior year",
    }
    period_label = PERIOD_LABELS.get(date_preset, "YTD")
    trend_label = TREND_LABELS.get(date_preset, "vs prior")

    # Store raw sparkline data for clientside smoothing
    sparkline_data = {}

    def _spark_start(last_date, preset):
        """Compute sparkline start date (different from KPI range start)."""
        if preset == "ytd":
            return pd.Timestamp(last_date.year, 1, 1)
        if preset == "lastyear":
            return pd.Timestamp(last_date.year - 1, 1, 1)
        lookbacks = {"today": 14, "week": 28, "month": 60, "quarter": 120, "12mo": 365}
        return last_date - timedelta(days=lookbacks.get(preset, 365))

    def _preset_start(last_date, preset):
        if preset == "today":
            return last_date
        elif preset == "week":
            return last_date - timedelta(days=6)  # Rolling 7 days
        elif preset == "month":
            return last_date - timedelta(days=29)  # Rolling 30 days
        elif preset == "quarter":
            return last_date - timedelta(days=89)  # Rolling 90 days (~3 months)
        elif preset == "12mo":
            return last_date - timedelta(days=365)
        elif preset == "lastyear":
            return pd.Timestamp(last_date.year - 1, 1, 1)
        else:  # ytd
            return pd.Timestamp(last_date.year, 1, 1)

    def _preset_end(last_date, preset):
        """End date for the current period (only differs for lastyear)."""
        if preset == "lastyear":
            return pd.Timestamp(last_date.year - 1, 12, 31)
        return last_date

    def _prior_range(last_date, preset):
        if preset == "today":
            d = last_date - timedelta(days=1)
            return d, d
        elif preset == "week":
            # Rolling: prior 7 days before the current 7-day window
            return last_date - timedelta(days=13), last_date - timedelta(days=7)
        elif preset == "month":
            # Rolling: prior 30 days before the current 30-day window
            return last_date - timedelta(days=59), last_date - timedelta(days=30)
        elif preset == "quarter":
            # Rolling: prior 90 days before the current 90-day window
            return last_date - timedelta(days=179), last_date - timedelta(days=90)
        elif preset == "12mo":
            return last_date - timedelta(days=730), last_date - timedelta(days=366)
        elif preset == "lastyear":
            return pd.Timestamp(last_date.year - 2, 1, 1), pd.Timestamp(last_date.year - 2, 12, 31)
        else:  # ytd
            try:
                pe = pd.Timestamp(last_date.year - 1, last_date.month, last_date.day)
            except ValueError:
                pe = pd.Timestamp(last_date.year - 1, last_date.month, 28)
            return pd.Timestamp(last_date.year - 1, 1, 1), pe

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
            # Include NaN departments (new patients without treatment history yet)
            sims = sims[sims["Department"].isin(departments) | sims["Department"].isna()]
        # Filter to countable simulation activities only
        if not sims.empty and "ActivityName" in sims.columns:
            if sims_scope == "initial":
                sims = sims[
                    sims["ActivityName"].str.contains("Initial", case=False, na=False) |
                    sims["ActivityName"].str.contains("Stereotactic Simulation", case=False, na=False)
                ]
            else:  # "all"
                sims = sims[
                    sims["ActivityName"].str.contains("Initial", case=False, na=False) |
                    sims["ActivityName"].str.contains("Stereotactic Simulation", case=False, na=False) |
                    sims["ActivityName"].str.contains("Re-Simulation", case=False, na=False) |
                    sims["ActivityName"].str.contains("Decub", case=False, na=False)
                ]
        # Filter to completed or billed simulations only
        if not sims.empty:
            completed = sims["Status"].str.contains("Completed", case=False, na=False) if "Status" in sims.columns else pd.Series(False, index=sims.index)
            billed = sims["ProcedureCodes"].notna() & (sims["ProcedureCodes"].astype(str).str.strip() != "") if "ProcedureCodes" in sims.columns else pd.Series(False, index=sims.index)
            sims = sims[completed | billed]
    except Exception:
        sims = pd.DataFrame()
    try:
        cv = load_clinic_visits()
        if departments and "Department" in cv.columns:
            # Include NaN departments (new patients without treatment history yet)
            cv = cv[cv["Department"].isin(departments) | cv["Department"].isna()]
        # Apply consult classification logic (duration + activity name + notes)
        if "ActivityName" in cv.columns:
            consults = cv[cv.apply(_is_consult, axis=1)]
        else:
            consults = pd.DataFrame()
        # Filter to completed or billed consults
        if not consults.empty:
            completed = consults["Status"].str.contains("Completed", case=False, na=False) if "Status" in consults.columns else pd.Series(False, index=consults.index)
            billed = consults["ProcedureCodes"].notna() & (consults["ProcedureCodes"].astype(str).str.strip() != "") if "ProcedureCodes" in consults.columns else pd.Series(False, index=consults.index)
            consults = consults[completed | billed]
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
)

clientside_callback(
    ClientsideFunction(namespace="sparklines", function_name="smoothSims"),
    Output("home-spark-sims", "figure"),
    Input("home-store-kpi-sparklines", "data"),
    Input("home-filter-smoothing", "value"),
)

clientside_callback(
    ClientsideFunction(namespace="sparklines", function_name="smoothTreatments"),
    Output("home-spark-treatments", "figure"),
    Input("home-store-kpi-sparklines", "data"),
    Input("home-filter-smoothing", "value"),
)

clientside_callback(
    ClientsideFunction(namespace="sparklines", function_name="smoothConsultLead"),
    Output("home-spark-consult-lead", "figure"),
    Input("home-store-kpi-sparklines", "data"),
    Input("home-filter-smoothing", "value"),
)

clientside_callback(
    ClientsideFunction(namespace="sparklines", function_name="smoothSimLead"),
    Output("home-spark-sim-lead", "figure"),
    Input("home-store-kpi-sparklines", "data"),
    Input("home-filter-smoothing", "value"),
)


# ---------------------------------------------------------------------------
# Physician Census Callback — outputs raw data to store
# ---------------------------------------------------------------------------

@callback(
    Output("home-store-md-census", "data"),
    Input("home-interval", "n_intervals"),
    Input("home-filter-department", "value"),
    Input("home-md-agg", "value"),
    running=[(Output("home-chart-physician-loading", "visible"), True, False)],
)
def update_physician_data(_n, departments, agg):
    from data.loader import load_treatment_detail

    try:
        td = load_treatment_detail()
        if departments and "Department" in td.columns:
            td = td[td["Department"].isin(departments)]
        if td.empty or "ScheduledDateTime" not in td.columns:
            return None

        # Get physicians dynamically from data
        if "TreatingPhysician" in td.columns:
            from components.filter_bar import physician_options
            opts = physician_options(td["TreatingPhysician"])
            physicians = [o["value"] for o in opts]
            render_physicians = list(physicians)
            colors = list(CHART_COLORWAY) * ((len(physicians) // len(CHART_COLORWAY)) + 1)
        else:
            physicians = []
            render_physicians = []
            colors = CHART_COLORWAY

        return _build_census_data(
            td,
            "TreatingPhysician",
            physicians,
            colors,
            render_groups=render_physicians,
            agg=agg or "D",
            dynamic_colors=True,
        )
    except Exception:
        return None


# Clientside callback for physician chart smoothing with chart type and range
clientside_callback(
    ClientsideFunction(namespace="census", function_name="smoothChartWithTypeAndRange"),
    Output("home-chart-physician", "figure"),
    Input("home-store-md-census", "data"),
    Input("home-md-settings-smooth", "value"),
    Input("home-md-settings-type", "value"),
    Input("home-md-range", "value"),
    Input("home-md-settings-stack", "value"),
    State("home-chart-physician", "figure"),
)

# Dynamic y-axis rescaling on pan for physician chart
clientside_callback(
    ClientsideFunction(namespace="censusYAxis", function_name="updateOnPan"),
    Output("home-chart-physician", "figure", allow_duplicate=True),
    Input("home-chart-physician", "relayoutData"),
    State("home-chart-physician", "figure"),
    State("home-store-md-census", "data"),
    State("home-md-settings-type", "value"),
    State("home-md-settings-stack", "value"),
    prevent_initial_call=True,
)


# Disable Daily aggregation for bar charts with long ranges (physician)
clientside_callback(
    ClientsideFunction(namespace="barAggGuard", function_name="update"),
    Output("home-md-agg", "data"),
    Output("home-md-agg", "value"),
    Input("home-md-settings-type", "value"),
    Input("home-md-range", "value"),
    State("home-md-agg", "value"),
    prevent_initial_call=True,
)


@callback(
    Output("home-md-settings-smooth", "max"),
    Output("home-md-settings-smooth", "value"),
    Input("home-md-range", "value"),
    State("home-md-settings-smooth", "value"),
)
def update_md_smooth_slider(range_days, current_value):
    """Adjust physician chart smoothing slider for the selected range."""
    return smooth_limits(range_days, current_value)


# ---------------------------------------------------------------------------
# Site Census Callback — outputs raw data to store (treatments with future)
# ---------------------------------------------------------------------------

@callback(
    Output("home-store-site-census", "data"),
    Input("home-interval", "n_intervals"),
    Input("home-filter-department", "value"),
    Input("home-site-agg", "value"),
    running=[(Output("home-chart-site-loading", "visible"), True, False)],
)
def update_site_data(_n, departments, agg):
    from data.loader import load_daily_volume, load_daily_volume_future

    try:
        # Load past and future daily volume data
        dv_past = load_daily_volume()
        dv_future = load_daily_volume_future()

        # Filter to departments only (not machines)
        sites = departments if departments else DEPARTMENTS
        dv_past = dv_past[dv_past["Department"].isin(sites)]
        dv_future = dv_future[dv_future["Department"].isin(sites)]

        if dv_past.empty or "ScheduledDate" not in dv_past.columns:
            return None

        colors = [DEPARTMENT_COLORS.get(d, "#999") for d in sites]
        return _build_treatment_census_data(dv_past, dv_future, sites, colors, agg=agg or "D")
    except Exception:
        return None


# Clientside callback for site chart smoothing with chart type and range
clientside_callback(
    ClientsideFunction(namespace="census", function_name="smoothChartWithTypeAndRange"),
    Output("home-chart-site", "figure"),
    Input("home-store-site-census", "data"),
    Input("home-site-settings-smooth", "value"),
    Input("home-site-settings-type", "value"),
    Input("home-site-range", "value"),
    Input("home-site-settings-stack", "value"),
    State("home-chart-site", "figure"),
)

# Dynamic y-axis rescaling on pan for site chart
clientside_callback(
    ClientsideFunction(namespace="censusYAxis", function_name="updateOnPan"),
    Output("home-chart-site", "figure", allow_duplicate=True),
    Input("home-chart-site", "relayoutData"),
    State("home-chart-site", "figure"),
    State("home-store-site-census", "data"),
    State("home-site-settings-type", "value"),
    State("home-site-settings-stack", "value"),
    prevent_initial_call=True,
)


# Disable Daily aggregation for bar charts with long ranges (site)
clientside_callback(
    ClientsideFunction(namespace="barAggGuard", function_name="update"),
    Output("home-site-agg", "data"),
    Output("home-site-agg", "value"),
    Input("home-site-settings-type", "value"),
    Input("home-site-range", "value"),
    State("home-site-agg", "value"),
    prevent_initial_call=True,
)


@callback(
    Output("home-site-settings-smooth", "max"),
    Output("home-site-settings-smooth", "value"),
    Input("home-site-range", "value"),
    State("home-site-settings-smooth", "value"),
)
def update_site_smooth_slider(range_days, current_value):
    """Adjust site chart smoothing slider for the selected range."""
    return smooth_limits(range_days, current_value)


# ---------------------------------------------------------------------------
# Census data builder (for clientside smoothing)
# ---------------------------------------------------------------------------

def _build_census_data(df, group_col, groups, colors, height=380, render_groups=None, agg="D", dynamic_colors=False):
    """Build raw census data dict for clientside smoothing.

    Returns dict with dates, series (name, values, color), optional renderOrder,
    height, yTitle.

    Args:
        agg: aggregation period — "D" (daily), "W" (weekly), "M" (monthly).
    """
    df = df.copy()
    df["Date"] = df["ScheduledDateTime"].dt.normalize()

    if group_col not in df.columns:
        return None

    patient_col = next((c for c in ["PatientId", "PatientMRN"] if c in df.columns), None)
    if patient_col is None:
        return None

    if agg in ("W", "M"):
        # Aggregate to period — count unique patients per period per group
        df["period"] = df["Date"].dt.to_period(agg).dt.to_timestamp()
        daily = df.groupby(["period", group_col])[patient_col].nunique().reset_index(name="count")
        date_range = sorted(daily["period"].unique())
    else:
        # Daily: business days only, excluding days with zero total patients
        date_range = pd.bdate_range(df["Date"].min(), df["Date"].max())
        total_per_day = df.groupby("Date")[patient_col].nunique()
        active_days = total_per_day[total_per_day > 0].index
        date_range = date_range[date_range.isin(active_days)]
        daily = df.groupby(["Date", group_col])[patient_col].nunique().reset_index(name="count")

    date_col = "period" if agg in ("W", "M") else "Date"

    # First pass: identify groups that have actual data so empty groups
    # don't consume color indices or create phantom stacked-area traces.
    group_data = {}
    for grp in groups:
        grp_raw = daily[daily[group_col] == grp].set_index(date_col)["count"]
        if grp_raw.empty or (grp_raw <= 0).all():
            continue  # skip groups with no positive values anywhere
        group_data[grp] = grp_raw

    # Second pass: build series with sequential color assignment (no gaps).
    series = []
    color_idx = 0
    active_groups = []
    for grp in groups:
        if grp not in group_data:
            continue
        grp_raw = group_data[grp]
        display_name = grp.split(",")[0] if "," in grp else grp
        c = colors[color_idx % len(colors)]
        color_idx += 1

        # None outside active range so traces don't extend before/after data exists
        positive = grp_raw[grp_raw > 0]
        first_active = positive.index.min() if not positive.empty else grp_raw.index.min()
        last_active = positive.index.max() if not positive.empty else grp_raw.index.max()
        grp_full = grp_raw.reindex(date_range)
        values = [
            None if (p < first_active or p > last_active)
            else (int(v) if pd.notna(v) else 0)
            for p, v in zip(date_range, grp_full)
        ]

        series.append({
            "name": display_name,
            "values": values,
            "color": c,
        })
        active_groups.append(grp)

    result = {
        "dates": [d.isoformat() for d in date_range],
        "series": series,
        "renderOrder": [
            grp.split(",")[0] if "," in grp else grp
            for grp in active_groups
        ],
        "height": height,
        "yTitle": "Unique Patients",
    }
    if dynamic_colors:
        result["dynamicColors"] = True
    return result


def _build_treatment_census_data(df_past, df_future, groups, colors, height=380, agg="D"):
    """Build treatment census data with future projections.

    Uses Daily Volume data (AppointmentCount) instead of unique patients.
    Returns dict with dates, futureDates, series (with values and futureValues).

    Args:
        agg: aggregation period — "D" (daily), "W" (weekly), "M" (monthly).
    """
    df_past = df_past.copy()
    df_future = df_future.copy()

    # Aggregate by date and department
    past_daily = df_past.groupby(["ScheduledDate", "Department"])["AppointmentCount"].sum().reset_index()
    future_daily = df_future.groupby(["ScheduledDate", "Department"])["AppointmentCount"].sum().reset_index()

    # Date ranges
    if past_daily.empty:
        return None

    if agg in ("W", "M"):
        # Aggregate to period
        past_daily["period"] = past_daily["ScheduledDate"].dt.to_period(agg).dt.to_timestamp()
        past_daily = past_daily.groupby(["period", "Department"])["AppointmentCount"].sum().reset_index()
        past_dates = sorted(past_daily["period"].unique())

        if not future_daily.empty:
            future_daily["period"] = future_daily["ScheduledDate"].dt.to_period(agg).dt.to_timestamp()
            future_daily = future_daily.groupby(["period", "Department"])["AppointmentCount"].sum().reset_index()
            # Exclude periods already in past
            past_period_set = set(past_dates)
            future_daily = future_daily[~future_daily["period"].isin(past_period_set)]
            future_dates = sorted(future_daily["period"].unique())
        else:
            future_dates = []

        date_col = "period"
    else:
        past_dates = pd.bdate_range(past_daily["ScheduledDate"].min(), past_daily["ScheduledDate"].max())
        # Filter to days with activity
        total_per_day = past_daily.groupby("ScheduledDate")["AppointmentCount"].sum()
        active_days = total_per_day[total_per_day > 0].index
        past_dates = past_dates[past_dates.isin(active_days)]

        # Future dates (next 2 weeks / ~10 business days)
        if not future_daily.empty:
            last_past = past_daily["ScheduledDate"].max()
            future_start = last_past + timedelta(days=1)
            future_end = future_daily["ScheduledDate"].max()
            future_dates = pd.bdate_range(future_start, min(future_end, last_past + timedelta(days=14)))
            # Filter to days with scheduled appointments
            future_totals = future_daily.groupby("ScheduledDate")["AppointmentCount"].sum()
            future_active = future_totals[future_totals > 0].index
            future_dates = future_dates[future_dates.isin(future_active)]
        else:
            future_dates = pd.DatetimeIndex([])

        date_col = "ScheduledDate"

    series = []
    for i, grp in enumerate(groups):
        # Past values — None outside active range so traces don't extend before/after data
        grp_past_raw = past_daily[past_daily["Department"] == grp].set_index(date_col)["AppointmentCount"]
        if not grp_past_raw.empty:
            positive = grp_past_raw[grp_past_raw > 0]
            first_active = positive.index.min() if not positive.empty else grp_past_raw.index.min()
            last_active = positive.index.max() if not positive.empty else grp_past_raw.index.max()
            grp_past_full = grp_past_raw.reindex(past_dates)
            past_values = [
                None if (p < first_active or p > last_active)
                else (int(v) if pd.notna(v) else 0)
                for p, v in zip(past_dates, grp_past_full)
            ]
        else:
            past_values = [None] * len(past_dates)

        # Future values
        if len(future_dates) > 0:
            grp_future = future_daily[future_daily["Department"] == grp].set_index(date_col)["AppointmentCount"]
            grp_future = grp_future.reindex(future_dates, fill_value=0)
        else:
            grp_future = pd.Series([], dtype=float)

        c = colors[i % len(colors)]
        series.append({
            "name": grp,
            "values": past_values,
            "futureValues": grp_future.tolist(),
            "color": c,
        })

    return {
        "dates": [d.isoformat() for d in past_dates],
        "futureDates": [d.isoformat() for d in future_dates],
        "series": series,
        "height": height,
        "yTitle": "Treatments",
    }


# ---------------------------------------------------------------------------
# Operating Hours Ribbon — reusable component callbacks + server data
# ---------------------------------------------------------------------------

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
register_chart_callbacks([
    ("home-md", "home-chart-physician", "home-store-md-census"),
    ("home-site", "home-chart-site", "home-store-site-census"),
    ("home-avail", "home-chart-availability"),
])
