"""Home page — executive summary with sparkline KPI cards and rolling census charts."""

import dash
import dash_mantine_components as dmc
from dash import callback, Input, Output, State, dcc, clientside_callback, ClientsideFunction
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

from config.settings import (
    PHYSICIANS, DEPARTMENTS, DEPARTMENT_COLORS, CHART_COLORWAY, PRIMARY,
    DEFAULT_LAYOUT, FONT_FAMILY, SEMANTIC_COLORS,
)
from components.filter_bar import department_chips
from components.kpi_card import kpi_card
from components.chart_settings import chart_settings_popover
from utils.charts import apply_default_layout, empty_figure, dept_color
from statsmodels.nonparametric.smoothers_lowess import lowess as _lowess


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

                results.append({
                    "name": site,
                    "dates": [d.isoformat() for d in site_data["ScheduledDate"]],
                    "startHours": site_data["start_hour"].tolist(),
                    "endHours": site_data["end_hour"].tolist(),
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
        }

    except Exception:
        return None


# ---------------------------------------------------------------------------
# Helper: Slot Availability Calendar (Dual - Exam & Sim)
# ---------------------------------------------------------------------------

def _build_availability_calendar(departments):
    """Build 4-week availability calendar with Exam and Sim side by side.

    Layout: Mon-Fri as columns (like a calendar), weeks as rows.
    Shows % booked (scheduled / total capacity) for each day.
    Green (<50%), Yellow (50-80%), Red (>80%)
    Includes median lead time for future scheduled appointments.
    """
    from data.loader import load_availability, load_clinic_visits, load_simulations

    try:
        today = pd.Timestamp.now().normalize()
        four_weeks = today + timedelta(days=28)

        # Load open holds from Availability
        avail = load_availability()
        if departments and "Department" in avail.columns:
            avail = avail[avail["Department"].isin(departments)]
        avail_future = avail[
            (avail["SlotDate"] >= today) &
            (avail["SlotDate"] <= four_weeks)
        ]

        # Load clinic visits for exams
        cv = load_clinic_visits()
        if departments and "Department" in cv.columns:
            cv = cv[cv["Department"].isin(departments) | cv["Department"].isna()]
        cv_future = cv[
            (cv["ScheduledDateTime"] >= today) &
            (cv["ScheduledDateTime"] <= four_weeks)
        ]
        if "ActivityName" in cv_future.columns:
            cv_future = cv_future[
                cv_future["ActivityName"].str.contains("Consult|Follow", case=False, na=False)
            ]

        # Load simulations
        sims = load_simulations()
        if departments and "Department" in sims.columns:
            sims = sims[sims["Department"].isin(departments) | sims["Department"].isna()]
        sims_future = sims[
            (sims["ScheduledDateTime"] >= today) &
            (sims["ScheduledDateTime"] <= four_weeks)
        ]

        # Calculate scheduled counts
        exam_scheduled = cv_future.groupby(cv_future["ScheduledDateTime"].dt.normalize()).size()
        sim_scheduled = sims_future.groupby(sims_future["ScheduledDateTime"].dt.normalize()).size()

        # Open holds by category
        exam_open = avail_future[
            avail_future["Category"].str.contains("Exam", case=False, na=False)
        ].groupby("SlotDate").size()
        sim_open = avail_future[
            avail_future["Category"].str.contains("Simulation", case=False, na=False)
        ].groupby("SlotDate").size()

        # Calculate median lead time for future appointments
        exam_lead = None
        if not cv_future.empty and "AppointmentCreatedDate" in cv_future.columns:
            cv_with_lead = cv_future[cv_future["AppointmentCreatedDate"].notna()].copy()
            if not cv_with_lead.empty:
                cv_with_lead["lead_days"] = (cv_with_lead["ScheduledDateTime"] - cv_with_lead["AppointmentCreatedDate"]).dt.days
                cv_with_lead = cv_with_lead[cv_with_lead["lead_days"] >= 0]
                if not cv_with_lead.empty:
                    exam_lead = cv_with_lead["lead_days"].median()

        sim_lead = None
        if not sims_future.empty and "AppointmentCreatedDate" in sims_future.columns:
            sims_with_lead = sims_future[sims_future["AppointmentCreatedDate"].notna()].copy()
            if not sims_with_lead.empty:
                sims_with_lead["lead_days"] = (sims_with_lead["ScheduledDateTime"] - sims_with_lead["AppointmentCreatedDate"]).dt.days
                sims_with_lead = sims_with_lead[sims_with_lead["lead_days"] >= 0]
                if not sims_with_lead.empty:
                    sim_lead = sims_with_lead["lead_days"].median()

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
        exam_pct = exam_pct.where(exam_total > 0, 50)
        sim_pct = sim_pct.where(sim_total > 0, 50)

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
        y_labels = [f"Wk {ws.strftime('%m/%d')}" for ws in weeks]

        def build_grid(pct_series, sched_series, total_series):
            z_data = []
            hover_data = []
            for week_start in weeks:
                row = []
                row_hover = []
                for day_idx in range(5):
                    target_date = week_start + timedelta(days=day_idx)
                    if target_date in pct_series.index:
                        pct = pct_series[target_date]
                        sched = int(sched_series.get(target_date, 0))
                        total = int(total_series.get(target_date, 0))
                        row.append(pct)
                        row_hover.append(f"{target_date.strftime('%b %d')}<br>{sched}/{total} ({pct:.0f}%)")
                    else:
                        row.append(None)
                        row_hover.append("")
                z_data.append(row)
                hover_data.append(row_hover)
            return z_data, hover_data

        exam_z, exam_hover = build_grid(exam_pct, exam_scheduled, exam_total)
        sim_z, sim_hover = build_grid(sim_pct, sim_scheduled, sim_total)

        # Create subplots - two heatmaps side by side
        fig = make_subplots(
            rows=1, cols=2,
            subplot_titles=["Consults", "Simulations"],
            horizontal_spacing=0.12,
        )

        colorscale = [
            [0, "#4CAF50"],      # Green - plenty available
            [0.5, "#FFC107"],    # Yellow - filling up
            [1, "#F44336"],      # Red - nearly full
        ]

        # Exam heatmap
        fig.add_trace(go.Heatmap(
            z=exam_z,
            x=x_labels,
            y=y_labels,
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
            y=y_labels,
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

        # Add lead time below each chart
        if exam_lead is not None:
            annotations.append(dict(
                text=f"Lead: {exam_lead:.0f} days",
                xref="x domain", yref="y domain",
                x=0.5, y=-0.12,
                showarrow=False,
                font=dict(size=10, color="#6B7280"),
                xanchor="center",
            ))
        if sim_lead is not None:
            annotations.append(dict(
                text=f"Lead: {sim_lead:.0f} days",
                xref="x2 domain", yref="y2 domain",
                x=0.5, y=-0.12,
                showarrow=False,
                font=dict(size=10, color="#6B7280"),
                xanchor="center",
            ))

        fig.update_layout(
            height=380,
            font=dict(family=FONT_FAMILY, size=11),
            plot_bgcolor="#FFFFFF",
            paper_bgcolor="#FFFFFF",
            margin=dict(l=45, r=8, t=50, b=32),
            annotations=annotations,
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
                dmc.GridCol(id="home-kpi-consults-week", span={"base": 12, "sm": 6, "md": 2.4}),
                dmc.GridCol(id="home-kpi-sims-week", span={"base": 12, "sm": 6, "md": 2.4}),
                dmc.GridCol(id="home-kpi-tx-today", span={"base": 12, "sm": 6, "md": 2.4}),
                dmc.GridCol(id="home-kpi-consult-lead", span={"base": 12, "sm": 6, "md": 2.4}),
                dmc.GridCol(id="home-kpi-sim-lead", span={"base": 12, "sm": 6, "md": 2.4}),
            ],
        ),

        # Census charts — side by side
        dmc.Grid(
            gutter=16,
            children=[
                dmc.GridCol(
                    span={"base": 12, "md": 6},
                    children=dmc.Paper(
                        children=[
                            dmc.Group(
                                justify="space-between", mb="sm",
                                children=[
                                    dmc.Text("Active Patients by Physician", size="sm", fw=500, c="#6B7280"),
                                    dmc.Group(gap="xs", align="center", children=[
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
                                        chart_settings_popover(
                                            "home-md",
                                            chart_types=[
                                                {"value": "area", "label": "Area"},
                                                {"value": "line", "label": "Line"},
                                                {"value": "bar", "label": "Bar"},
                                            ],
                                            show_smooth=True,
                                            smooth_max=50,
                                            smooth_default=15,
                                        ),
                                    ]),
                                ],
                            ),
                            dmc.Box(
                                pos="relative",
                                children=[
                                    dmc.LoadingOverlay(
                                        id="home-md-loading",
                                        visible=False,
                                        loaderProps={"type": "dots", "color": "#7C2A83"},
                                        overlayProps={"radius": "sm", "blur": 2},
                                    ),
                                    dcc.Graph(id="home-chart-physician", config={"displayModeBar": False}),
                                ],
                            ),
                        ],
                        p="sm", radius="md", shadow="xs", withBorder=True,
                    ),
                ),
                dmc.GridCol(
                    span={"base": 12, "md": 6},
                    children=dmc.Paper(
                        children=[
                            dmc.Group(
                                justify="space-between", mb="sm",
                                children=[
                                    dmc.Text("Treatments by Site", size="sm", fw=500, c="#6B7280"),
                                    dmc.Group(gap="xs", align="center", children=[
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
                                        chart_settings_popover(
                                            "home-site",
                                            chart_types=[
                                                {"value": "area", "label": "Area"},
                                                {"value": "line", "label": "Line"},
                                                {"value": "bar", "label": "Bar"},
                                            ],
                                            show_smooth=True,
                                            smooth_max=50,
                                            smooth_default=15,
                                        ),
                                    ]),
                                ],
                            ),
                            dmc.Box(
                                pos="relative",
                                children=[
                                    dmc.LoadingOverlay(
                                        id="home-site-loading",
                                        visible=False,
                                        loaderProps={"type": "dots", "color": "#7C2A83"},
                                        overlayProps={"radius": "sm", "blur": 2},
                                    ),
                                    dcc.Graph(id="home-chart-site", config={"displayModeBar": False}),
                                ],
                            ),
                        ],
                        p="sm", radius="md", shadow="xs", withBorder=True,
                    ),
                ),
            ],
        ),

        # Operating hours + Availability row
        dmc.Grid(
            gutter=16,
            children=[
                # Left: Operating Hours Ribbon
                dmc.GridCol(
                    span={"base": 12, "md": 6},
                    children=dmc.Paper(
                        children=[
                            dmc.Group(
                                justify="space-between", mb="sm",
                                children=[
                                    dmc.Group(gap="sm", align="center", children=[
                                        dmc.Text("Operating Hours", size="sm", fw=500, c="#6B7280"),
                                        dmc.SegmentedControl(
                                            id="home-hours-site",
                                            data=[
                                                {"value": "all", "label": "All"},
                                                {"value": "Lacey", "label": "Lacey"},
                                                {"value": "Centralia", "label": "Centralia"},
                                                {"value": "Aberdeen", "label": "Aberdeen"},
                                            ],
                                            value="all", size="xs",
                                        ),
                                    ]),
                                    dmc.Group(gap="xs", align="center", children=[
                                        dmc.SegmentedControl(
                                            id="home-hours-range",
                                            data=[
                                                {"value": "7", "label": "7d"},
                                                {"value": "30", "label": "30d"},
                                                {"value": "60", "label": "60d"},
                                                {"value": "90", "label": "90d"},
                                                {"value": "365", "label": "1y"},
                                                {"value": "0", "label": "All"},
                                            ],
                                            value="30", size="xs",
                                        ),
                                        chart_settings_popover(
                                            "home-hours",
                                            chart_types=[
                                                {"value": "ribbon", "label": "Ribbon"},
                                                {"value": "line", "label": "Line"},
                                                {"value": "bar", "label": "Bar"},
                                            ],
                                            show_smooth=True,
                                            smooth_max=7,
                                            smooth_default=3,
                                        ),
                                    ]),
                                ],
                            ),
                            dmc.Box(
                                pos="relative",
                                children=[
                                    dmc.LoadingOverlay(
                                        id="home-hours-loading",
                                        visible=False,
                                        loaderProps={"type": "dots", "color": "#7C2A83"},
                                        overlayProps={"radius": "sm", "blur": 2},
                                    ),
                                    dcc.Graph(id="home-chart-hours", config={"displayModeBar": False}),
                                ],
                            ),
                        ],
                        p="sm", radius="md", shadow="xs", withBorder=True,
                    ),
                ),
                # Right: Availability Calendar
                dmc.GridCol(
                    span={"base": 12, "md": 6},
                    children=dmc.Paper(
                        children=[
                            dmc.Group(
                                justify="space-between", mb="sm",
                                children=[
                                    dmc.Text("Slot Availability (4 Weeks)", size="sm", fw=500, c="#6B7280"),
                                    chart_settings_popover(
                                        "home-avail",
                                        chart_types=None,
                                        show_smooth=False,
                                    ),
                                ],
                            ),
                            dmc.Box(
                                pos="relative",
                                children=[
                                    dmc.LoadingOverlay(
                                        id="home-avail-loading",
                                        visible=False,
                                        loaderProps={"type": "dots", "color": "#7C2A83"},
                                        overlayProps={"radius": "sm", "blur": 2},
                                    ),
                                    dcc.Graph(id="home-chart-availability", config={"displayModeBar": False}),
                                ],
                            ),
                        ],
                        p="sm", radius="md", shadow="xs", withBorder=True,
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

        # Store for operating hours ribbon (clientside smoothing)
        dcc.Store(id="home-store-hours"),
    ],
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
)
def update_kpis(_n, date_preset, departments):
    """Compute all 5 KPI cards with sparkline IDs (data computed separately)."""
    from data.loader import load_treatment_detail, load_simulations, load_clinic_visits

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
    SPARK_FREQ = {
        "today": "D", "week": "D", "month": "D",
        "quarter": "W", "12mo": "W", "lastyear": "W", "ytd": "W",
    }
    period_label = PERIOD_LABELS.get(date_preset, "YTD")
    trend_label = TREND_LABELS.get(date_preset, "vs prior")
    spark_freq = SPARK_FREQ.get(date_preset, "W")

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
        if spark_freq == "W":
            series = s_data.groupby(s_data[date_col].dt.to_period("W").dt.start_time).size()
        else:
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
        if spark_freq == "W":
            series = s_data.groupby(s_data[date_col].dt.to_period("W").dt.start_time)[lead_col].median()
        else:
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
        # Filter to initial and stereotactic simulations only
        if not sims.empty and "ActivityName" in sims.columns:
            sims = sims[
                sims["ActivityName"].str.contains("Initial", case=False, na=False) |
                sims["ActivityName"].str.contains("Stereotactic Simulation", case=False, na=False)
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
        )
    else:
        kpi_sims = kpi_card("Simulations", "N/A")

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

    # --- 4. Consult Lead Time (days from booking to appointment) ---
    if not consults.empty and "AppointmentCreatedDate" in consults.columns:
        cl = consults[consults["AppointmentCreatedDate"].notna()].copy()
        cl["lead_days"] = (cl["ScheduledDateTime"] - cl["AppointmentCreatedDate"]).dt.days
        cl = cl[cl["lead_days"] >= 0]
        if not cl.empty:
            last_cv = cl["ScheduledDateTime"].dt.normalize().max()
            start = _preset_start(last_cv, date_preset)
            end = _preset_end(last_cv, date_preset)
            curr_data = cl[(cl["ScheduledDateTime"] >= start) & (cl["ScheduledDateTime"] <= end)]
            curr_med = curr_data["lead_days"].median() if len(curr_data) > 0 else 0
            ps, pe = _prior_range(last_cv, date_preset)
            prior_data = cl[(cl["ScheduledDateTime"] >= ps) & (cl["ScheduledDateTime"] <= pe)]
            prior_med = prior_data["lead_days"].median() if len(prior_data) > 0 else None
            pt, t_dir, pv = _trend(curr_med, prior_med, invert=True)
            sparkline_data["consult_lead"] = {
                **_lead_spark_raw(cl, "ScheduledDateTime", "lead_days", last_cv),
                "color": CHART_COLORWAY[4],
                "hover_fmt": "%{x|%b %d}: %{y:.0f} days<extra></extra>",
            }
            kpi_consult_lead = kpi_card(
                f"Consult Lead Time ({period_label})", f"{curr_med:.0f}",
                value_detail="days",
                trend_text=f"{pt} {trend_label} ({pv:.0f}d)" if pt else None,
                trend_direction=t_dir,
                accent_color=CHART_COLORWAY[4],
                sparkline_id="home-spark-consult-lead",
            )
        else:
            kpi_consult_lead = kpi_card("Consult Lead Time", "N/A")
    else:
        kpi_consult_lead = kpi_card("Consult Lead Time", "N/A")

    # --- 5. Sim Lead Time (days from booking to appointment) ---
    if not sims.empty and "AppointmentCreatedDate" in sims.columns:
        sl = sims[sims["AppointmentCreatedDate"].notna()].copy()
        sl["lead_days"] = (sl["ScheduledDateTime"] - sl["AppointmentCreatedDate"]).dt.days
        sl = sl[sl["lead_days"] >= 0]
        if not sl.empty:
            last_sim = sl["ScheduledDateTime"].dt.normalize().max()
            start = _preset_start(last_sim, date_preset)
            end = _preset_end(last_sim, date_preset)
            curr_data = sl[(sl["ScheduledDateTime"] >= start) & (sl["ScheduledDateTime"] <= end)]
            curr_med = curr_data["lead_days"].median() if len(curr_data) > 0 else 0
            ps, pe = _prior_range(last_sim, date_preset)
            prior_data = sl[(sl["ScheduledDateTime"] >= ps) & (sl["ScheduledDateTime"] <= pe)]
            prior_med = prior_data["lead_days"].median() if len(prior_data) > 0 else None
            pt, t_dir, pv = _trend(curr_med, prior_med, invert=True)
            sparkline_data["sim_lead"] = {
                **_lead_spark_raw(sl, "ScheduledDateTime", "lead_days", last_sim),
                "color": CHART_COLORWAY[3],
                "hover_fmt": "%{x|%b %d}: %{y:.0f} days<extra></extra>",
            }
            kpi_sim_lead = kpi_card(
                f"Sim Lead Time ({period_label})", f"{curr_med:.0f}",
                value_detail="days",
                trend_text=f"{pt} {trend_label} ({pv:.0f}d)" if pt else None,
                trend_direction=t_dir,
                accent_color=CHART_COLORWAY[3],
                sparkline_id="home-spark-sim-lead",
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
    Input("home-md-range", "value"),
    Input("home-filter-department", "value"),
    running=[(Output("home-md-loading", "visible"), True, False)],
)
def update_physician_data(_n, range_days, departments):
    from data.loader import load_treatment_detail

    try:
        td = load_treatment_detail()
        if departments and "Department" in td.columns:
            td = td[td["Department"].isin(departments)]
        if td.empty or "ScheduledDateTime" not in td.columns:
            return None

        last_date = td["ScheduledDateTime"].dt.normalize().max()
        days = int(range_days) if int(range_days) > 0 else None
        if days:
            td = td[td["ScheduledDateTime"] >= last_date - timedelta(days=days)]

        # Get physicians dynamically from data, prioritizing the 4 main ones first
        if "TreatingPhysician" in td.columns:
            all_physicians = td["TreatingPhysician"].dropna().unique().tolist()
            # Put main physicians first (in order), then others alphabetically
            main_first = [p for p in PHYSICIANS if p in all_physicians]
            others = sorted([p for p in all_physicians if p not in PHYSICIANS])
            physicians = main_first + others
            # Extend colors if needed
            colors = list(CHART_COLORWAY) * ((len(physicians) // len(CHART_COLORWAY)) + 1)
        else:
            physicians = PHYSICIANS
            colors = CHART_COLORWAY

        return _build_census_data(td, "TreatingPhysician", physicians, colors)
    except Exception:
        return None


# Clientside callback for physician chart smoothing with chart type
clientside_callback(
    ClientsideFunction(namespace="census", function_name="smoothChartWithType"),
    Output("home-chart-physician", "figure"),
    Input("home-store-md-census", "data"),
    Input("home-md-settings-smooth", "value"),
    Input("home-md-settings-type", "value"),
    State("home-chart-physician", "figure"),
)


# ---------------------------------------------------------------------------
# Site Census Callback — outputs raw data to store (treatments with future)
# ---------------------------------------------------------------------------

@callback(
    Output("home-store-site-census", "data"),
    Input("home-interval", "n_intervals"),
    Input("home-site-range", "value"),
    Input("home-filter-department", "value"),
    running=[(Output("home-site-loading", "visible"), True, False)],
)
def update_site_data(_n, range_days, departments):
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

        last_date = dv_past["ScheduledDate"].max()
        days = int(range_days) if int(range_days) > 0 else None
        if days:
            dv_past = dv_past[dv_past["ScheduledDate"] >= last_date - timedelta(days=days)]

        colors = [DEPARTMENT_COLORS.get(d, "#999") for d in sites]
        return _build_treatment_census_data(dv_past, dv_future, sites, colors)
    except Exception:
        return None


# Clientside callback for site chart smoothing with chart type
clientside_callback(
    ClientsideFunction(namespace="census", function_name="smoothChartWithType"),
    Output("home-chart-site", "figure"),
    Input("home-store-site-census", "data"),
    Input("home-site-settings-smooth", "value"),
    Input("home-site-settings-type", "value"),
    State("home-chart-site", "figure"),
)


# ---------------------------------------------------------------------------
# Census data builder (for clientside smoothing)
# ---------------------------------------------------------------------------

def _build_census_data(df, group_col, groups, colors, height=380):
    """Build raw census data dict for clientside smoothing.

    Returns dict with dates, series (name, values, color), height, yTitle.
    """
    df = df.copy()
    df["Date"] = df["ScheduledDateTime"].dt.normalize()

    if group_col not in df.columns:
        return None

    patient_col = next((c for c in ["PatientId", "PatientMRN"] if c in df.columns), None)
    if patient_col is None:
        return None

    # Business days only (no weekends), excluding days with zero total patients
    date_range = pd.bdate_range(df["Date"].min(), df["Date"].max())
    total_per_day = df.groupby("Date")[patient_col].nunique()
    active_days = total_per_day[total_per_day > 0].index
    date_range = date_range[date_range.isin(active_days)]

    # Per-group daily counts
    daily = df.groupby(["Date", group_col])[patient_col].nunique().reset_index(name="count")

    series = []
    for i, grp in enumerate(groups):
        grp_data = daily[daily[group_col] == grp].set_index("Date")["count"]
        grp_data = grp_data.reindex(date_range, fill_value=0)
        display_name = grp.split(",")[0] if "," in grp else grp
        c = colors[i % len(colors)]

        series.append({
            "name": display_name,
            "values": grp_data.tolist(),
            "color": c,
        })

    return {
        "dates": [d.isoformat() for d in date_range],
        "series": series,
        "height": height,
        "yTitle": "Unique Patients",
    }


def _build_treatment_census_data(df_past, df_future, groups, colors, height=380):
    """Build treatment census data with future projections.

    Uses Daily Volume data (AppointmentCount) instead of unique patients.
    Returns dict with dates, futureDates, series (with values and futureValues).
    """
    df_past = df_past.copy()
    df_future = df_future.copy()

    # Aggregate by date and department
    past_daily = df_past.groupby(["ScheduledDate", "Department"])["AppointmentCount"].sum().reset_index()
    future_daily = df_future.groupby(["ScheduledDate", "Department"])["AppointmentCount"].sum().reset_index()

    # Date ranges
    if past_daily.empty:
        return None

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

    series = []
    for i, grp in enumerate(groups):
        # Past values
        grp_past = past_daily[past_daily["Department"] == grp].set_index("ScheduledDate")["AppointmentCount"]
        grp_past = grp_past.reindex(past_dates, fill_value=0)

        # Future values
        if len(future_dates) > 0:
            grp_future = future_daily[future_daily["Department"] == grp].set_index("ScheduledDate")["AppointmentCount"]
            grp_future = grp_future.reindex(future_dates, fill_value=0)
        else:
            grp_future = pd.Series([], dtype=float)

        c = colors[i % len(colors)]
        series.append({
            "name": grp,
            "values": grp_past.tolist(),
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
# Operating Hours Ribbon Callbacks (store + clientside pattern)
# ---------------------------------------------------------------------------

@callback(
    Output("home-hours-settings-smooth", "max"),
    Output("home-hours-settings-smooth", "value"),
    Input("home-hours-range", "value"),
    State("home-hours-settings-smooth", "value"),
)
def update_smooth_slider_range(range_days, current_value):
    """Adjust smoothing slider max based on selected time range."""
    days = int(range_days) if range_days else 30
    # Scale max smoothing window to ~20% of the time range
    # 7d -> max 3, 30d -> max 7, 60d -> max 12, 90d -> max 18, 365d -> max 30, All -> max 50
    if days == 0:  # All
        max_val = 50
    elif days <= 7:
        max_val = 3
    elif days <= 30:
        max_val = 7
    elif days <= 60:
        max_val = 12
    elif days <= 90:
        max_val = 18
    elif days <= 365:
        max_val = 30
    else:
        max_val = 50
    # Clamp current value to new max
    new_value = min(current_value or 0, max_val)
    return max_val, new_value


@callback(
    Output("home-store-hours", "data"),
    Input("home-interval", "n_intervals"),
    Input("home-hours-range", "value"),
    Input("home-hours-site", "value"),
    running=[(Output("home-hours-loading", "visible"), True, False)],
)
def update_hours_data(_n, range_days, site_filter):
    """Load operating hours data to store (smoothing is clientside)."""
    days = int(range_days) if range_days else 30
    # Use chart's own site selector (independent of global filter)
    if site_filter and site_filter != "all":
        sites = [site_filter]
    else:
        sites = None  # All departments
    return _prepare_hours_data(sites, days_back=days)


# Clientside callback for hours ribbon smoothing with chart type
clientside_callback(
    ClientsideFunction(namespace="hoursRibbon", function_name="smoothChartWithType"),
    Output("home-chart-hours", "figure"),
    Input("home-store-hours", "data"),
    Input("home-hours-settings-smooth", "value"),
    Input("home-hours-settings-type", "value"),
)


# ---------------------------------------------------------------------------
# Availability Calendar Callback
# ---------------------------------------------------------------------------

@callback(
    Output("home-chart-availability", "figure"),
    Input("home-interval", "n_intervals"),
    Input("home-filter-department", "value"),
    running=[(Output("home-avail-loading", "visible"), True, False)],
)
def update_availability_calendar(_n, departments):
    """Update slot availability calendar (shows both Exam and Sim)."""
    return _build_availability_calendar(departments)


# ---------------------------------------------------------------------------
# Settings Panel Toggle Callbacks
# ---------------------------------------------------------------------------

@callback(
    Output("home-md-settings-panel", "style"),
    Input("home-md-settings-btn", "n_clicks"),
    State("home-md-settings-panel", "style"),
    prevent_initial_call=True,
)
def toggle_md_settings(n, style):
    if not n:
        return style
    current = style or {}
    is_hidden = current.get("display") == "none"
    return {"display": "block"} if is_hidden else {"display": "none"}


@callback(
    Output("home-site-settings-panel", "style"),
    Input("home-site-settings-btn", "n_clicks"),
    State("home-site-settings-panel", "style"),
    prevent_initial_call=True,
)
def toggle_site_settings(n, style):
    if not n:
        return style
    current = style or {}
    is_hidden = current.get("display") == "none"
    return {"display": "block"} if is_hidden else {"display": "none"}


@callback(
    Output("home-hours-settings-panel", "style"),
    Input("home-hours-settings-btn", "n_clicks"),
    State("home-hours-settings-panel", "style"),
    prevent_initial_call=True,
)
def toggle_hours_settings(n, style):
    if not n:
        return style
    current = style or {}
    is_hidden = current.get("display") == "none"
    return {"display": "block"} if is_hidden else {"display": "none"}


@callback(
    Output("home-avail-settings-panel", "style"),
    Input("home-avail-settings-btn", "n_clicks"),
    State("home-avail-settings-panel", "style"),
    prevent_initial_call=True,
)
def toggle_avail_settings(n, style):
    if not n:
        return style
    current = style or {}
    is_hidden = current.get("display") == "none"
    return {"display": "block"} if is_hidden else {"display": "none"}


# ---------------------------------------------------------------------------
# PNG Export Callbacks (clientside)
# ---------------------------------------------------------------------------

clientside_callback(
    """function(n) {
        if (!n) return window.dash_clientside.no_update;
        var wrapper = document.getElementById('home-chart-physician');
        var graphEl = wrapper ? wrapper.querySelector('.js-plotly-plot') : null;
        if (graphEl) {
            Plotly.downloadImage(graphEl, {format: 'png', width: 1200, height: 600, filename: 'active_patients_by_physician'});
        }
        return window.dash_clientside.no_update;
    }""",
    Output("home-md-settings-export", "n_clicks"),
    Input("home-md-settings-export", "n_clicks"),
    prevent_initial_call=True,
)

clientside_callback(
    """function(n) {
        if (!n) return window.dash_clientside.no_update;
        var wrapper = document.getElementById('home-chart-site');
        var graphEl = wrapper ? wrapper.querySelector('.js-plotly-plot') : null;
        if (graphEl) {
            Plotly.downloadImage(graphEl, {format: 'png', width: 1200, height: 600, filename: 'treatments_by_site'});
        }
        return window.dash_clientside.no_update;
    }""",
    Output("home-site-settings-export", "n_clicks"),
    Input("home-site-settings-export", "n_clicks"),
    prevent_initial_call=True,
)

clientside_callback(
    """function(n) {
        if (!n) return window.dash_clientside.no_update;
        var wrapper = document.getElementById('home-chart-hours');
        var graphEl = wrapper ? wrapper.querySelector('.js-plotly-plot') : null;
        if (graphEl) {
            Plotly.downloadImage(graphEl, {format: 'png', width: 1200, height: 600, filename: 'operating_hours'});
        }
        return window.dash_clientside.no_update;
    }""",
    Output("home-hours-settings-export", "n_clicks"),
    Input("home-hours-settings-export", "n_clicks"),
    prevent_initial_call=True,
)

clientside_callback(
    """function(n) {
        if (!n) return window.dash_clientside.no_update;
        var wrapper = document.getElementById('home-chart-availability');
        var graphEl = wrapper ? wrapper.querySelector('.js-plotly-plot') : null;
        if (graphEl) {
            Plotly.downloadImage(graphEl, {format: 'png', width: 1200, height: 600, filename: 'slot_availability'});
        }
        return window.dash_clientside.no_update;
    }""",
    Output("home-avail-settings-export", "n_clicks"),
    Input("home-avail-settings-export", "n_clicks"),
    prevent_initial_call=True,
)
