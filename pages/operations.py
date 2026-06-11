"""Operations page — daily treatment operations view with volume trends, operating hours ribbons, and availability heatmaps."""

import dash
import dash_mantine_components as dmc
from dash import callback, Input, Output, State, dcc, clientside_callback, ClientsideFunction
import dash_ag_grid as dag
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

from config.settings import (
    DEPARTMENTS, DEPARTMENT_COLORS, MACHINE_MAP, RETIRED_MACHINES,
    CHART_COLORWAY, PRIMARY, DEFAULT_LAYOUT, FONT_FAMILY,
)
from components.kpi_card import kpi_card, kpi_placeholder
from components.chart_card import chart_card, register_chart_callbacks
from components.hours_ribbon import hours_ribbon_card, register_hours_ribbon_callbacks
from components.detail_table import detail_table
from dash_iconify import DashIconify
from utils.charts import apply_default_layout, empty_figure, dept_color, smooth_limits, full_period_range

dash.register_page(__name__, path="/operations", name="Operations", order=1)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MACHINES = ["TrueBeamNorth", "21EX", "21iX_CEN", "21iX_AB"]


# ---------------------------------------------------------------------------
# Filter Bar Components
# ---------------------------------------------------------------------------



# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------

layout = dmc.Stack(
    gap=16,
    className="page-content",
    children=[
        # Non-sticky header for operations — no filter bar to share the
        # sticky zone. The page-level CSS on <html data-page="operations">
        # (set by the route-watcher in assets/02_theme.js) also unfixes the
        # global controls strip so the icons scroll up with the page and sit
        # inline with the smoothing slider on first view.
        dmc.Box(
            pos="relative",
            pb=0,
            style={"gap": 0},
            children=[
                dmc.Title("Operations", order=2, className="page-title"),
                dmc.Group(
                    gap=8, align="center",
                    style={"position": "absolute", "right": 300, "bottom": 6},
                    children=[
                        dmc.Text("Smoothing", size="xs", c="#9CA3AF", fw=500),
                        dmc.Slider(
                            id="ops-filter-smoothing",
                            min=0, max=1, step=0.01, value=0.7,
                            size="xs", w=100,
                            showLabelOnHover=False,
                            updatemode="drag",
                        ),
                    ],
                ),
            ],
        ),

        # Hidden inputs for filter IDs required by callbacks (no visible filter bar)
        dcc.Store(id="operations-filter-department", data=None),
        dcc.Store(id="operations-filter-machine", data=None),

        # KPI row — 7 cards (negative margin to close gap left by missing filter bar)
        dmc.Grid(
            gutter=16,
            columns=7,
            mt=-8,
            children=[
                dmc.GridCol(kpi_placeholder(), id="ops-kpi-today", span={"base": 7, "sm": 2, "md": 1}),
                dmc.GridCol(kpi_placeholder(), id="ops-kpi-hours-lacey", span={"base": 7, "sm": 2, "md": 1}),
                dmc.GridCol(kpi_placeholder(), id="ops-kpi-hours-centralia", span={"base": 7, "sm": 2, "md": 1}),
                dmc.GridCol(kpi_placeholder(), id="ops-kpi-hours-aberdeen", span={"base": 7, "sm": 2, "md": 1}),
                dmc.GridCol(kpi_placeholder(), id="ops-kpi-consult-lead", span={"base": 7, "sm": 2, "md": 1}),
                dmc.GridCol(kpi_placeholder(), id="ops-kpi-sim-lead", span={"base": 7, "sm": 2, "md": 1}),
                dmc.GridCol(kpi_placeholder(), id="ops-kpi-new-starts", span={"base": 7, "sm": 2, "md": 1}),
            ],
        ),

        # Charts row: Treatment Appointments (half) + Upcoming Heatmap (half)
        dmc.Grid(
            gutter=16,
            children=[
                # Treatment Appointments (completed)
                dmc.GridCol(
                    span={"base": 12, "md": 6},
                    children=chart_card(
                        "ops-chart-volume",
                        "Treatments",
                        settings_id="ops-volume",
                        chart_types=[
                            {"value": "area", "label": "Area"},
                            {"value": "line", "label": "Line"},
                            {"value": "bar", "label": "Bar"},
                        ],
                        show_smooth=True,
                        smooth_max=30,
                        smooth_default=7,
                        extra_controls=[
                            dmc.SegmentedControl(
                                id="ops-volume-agg",
                                data=[
                                    {"value": "D", "label": "Daily"},
                                    {"value": "W", "label": "Weekly"},
                                    {"value": "M", "label": "Monthly"},
                                ],
                                value="D",
                                size="xs",
                            ),
                            dmc.SegmentedControl(
                                id="ops-volume-range",
                                data=[
                                    {"value": "30", "label": "30d"},
                                    {"value": "60", "label": "60d"},
                                    {"value": "90", "label": "90d"},
                                    {"value": "180", "label": "6mo"},
                                    {"value": "365", "label": "1y"},
                                    {"value": "0", "label": "All"},
                                ],
                                value="90",
                                size="xs",
                            ),
                        ],
                    ),
                ),
                # Upcoming 2 Weeks Heatmap
                dmc.GridCol(
                    span={"base": 12, "md": 6},
                    children=chart_card(
                        "ops-chart-heatmap",
                        "Upcoming 4 Weeks — Schedule & Availability",
                        show_settings=False,
                        show_smooth=False,
                        graph_config={"displayModeBar": False},
                        extra_controls=[
                            dmc.SegmentedControl(
                                id="ops-heatmap-scope",
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

        # Operating Hours Ribbon (half) + Resource Utilization (half)
        dmc.Grid(
            gutter=16,
            children=[
                # Operating Hours Ribbon
                dmc.GridCol(
                    span={"base": 12, "md": 6},
                    children=hours_ribbon_card("ops", card_height="466px"),
                ),
                # Resource Utilization
                dmc.GridCol(
                    span={"base": 12, "md": 6},
                    children=chart_card(
                        "ops-chart-efficiency",
                        "Resource Utilization",
                        settings_id="ops-efficiency",
                        chart_types=[
                            {"value": "line", "label": "Line"},
                            {"value": "area", "label": "Area"},
                            {"value": "bar", "label": "Bar"},
                        ],
                        show_smooth=True,
                        smooth_max=30,
                        smooth_default=15,
                        show_grouping=False,
                        paper_style={"overflow": "visible"},
                        extra_controls_left=[
                            dmc.SegmentedControl(
                                id="ops-efficiency-metric",
                                data=[
                                    {"value": "utilization", "label": "Util %"},
                                    {"value": "minutes", "label": "Active Min"},
                                    {"value": "beam", "label": "Beam On"},
                                ],
                                value="beam",
                                size="xs",
                            ),
                            dmc.Tooltip(
                                label=dmc.Stack(gap=2, children=[
                                    dmc.Text("Active Min*: Total minutes from setup imaging to last treated field", size="xs"),
                                    dmc.Text("Util %: Active Min / Scheduled Appt Duration", size="xs"),
                                    dmc.Text("Beam On: Sum of elapsed time for all treated fields", size="xs"),
                                    dmc.Text("* = Available Oct 6, 2025 to present", size="xs", fs="italic", c="dimmed"),
                                ]),
                                position="top",
                                withArrow=True,
                                openDelay=150,
                                multiline=True,
                                w=340,
                                children=DashIconify(
                                    icon="mdi:information-outline",
                                    width=16, color="#9CA3AF",
                                    style={"cursor": "help"},
                                ),
                            ),
                        ],
                        extra_controls=[
                            dmc.SegmentedControl(
                                id="ops-efficiency-agg",
                                data=[
                                    {"value": "D", "label": "Daily"},
                                    {"value": "W", "label": "Weekly"},
                                    {"value": "M", "label": "Monthly"},
                                ],
                                value="W",
                                size="xs",
                            ),
                            dmc.SegmentedControl(
                                id="ops-efficiency-range",
                                data=[
                                    {"value": "30", "label": "30d"},
                                    {"value": "90", "label": "90d"},
                                    {"value": "365", "label": "1y"},
                                    {"value": "0", "label": "All"},
                                ],
                                value="365",
                                size="xs",
                            ),
                        ],
                        sub_header=dmc.Group(
                            gap=6, mb=4, style={"position": "relative", "zIndex": 2},
                            children=dmc.ChipGroup(
                                id="ops-efficiency-machines",
                                children=[
                                    dmc.Chip("TrueBeam", value="TrueBeamNorth", size="xs", variant="filled", color="#1976D2"),
                                    dmc.Chip("21EX", value="21EX", size="xs", variant="filled", color="#64B5F6"),
                                    dmc.Chip("21iX CEN", value="21iX_CEN", size="xs", variant="filled", color="red"),
                                    dmc.Chip("21iX AB", value="21iX_AB", size="xs", variant="filled", color="green"),
                                ],
                                value=["TrueBeamNorth", "21EX", "21iX_CEN", "21iX_AB"],
                                multiple=True,
                            ),
                        ),
                    ),
                ),
            ],
        ),

        # Daily Detail Table (full-width, collapsible)
        detail_table(
            "ops-table",
            title="Daily Detail",
            export_id="ops-table-export",
            extra_controls=[
                dmc.Group(gap="xs", align="center", children=[
                    dmc.Text("Include Future", size="xs", c="#6B7280"),
                    dmc.Switch(
                        id="ops-table-include-future",
                        checked=True,
                        size="sm",
                    ),
                ]),
                dmc.SegmentedControl(
                    id="ops-table-view-by",
                    data=[
                        {"value": "location", "label": "By Location"},
                        {"value": "machine", "label": "By Machine"},
                    ],
                    value="location",
                    size="xs",
                ),
            ],
        ),

        # Schedule data updates live; rest of operations is daily. 15-min
        # cadence keeps the live schedule fresh without spamming re-renders.
        dcc.Interval(id="ops-interval", interval=900_000, n_intervals=0),

        # Stores for clientside rendering
        dcc.Store(id="ops-store-volume"),
        dcc.Store(id="ops-store-efficiency"),
        dcc.Store(id="ops-store-kpi-sparklines"),
    ],
)



# ---------------------------------------------------------------------------
# Helper: Operating Hours Data (for clientside smoothing)
# ---------------------------------------------------------------------------

def _prepare_hours_data(departments, machines, days_back=90, aggregate_weekly=False):
    """Prepare raw operating hours data for clientside smoothing.

    Args:
        departments: List of departments to include
        machines: List of machines for Lacey filtering
        days_back: Number of days to include (0 = all data)
        aggregate_weekly: If True, aggregate data by week instead of day
    """
    from data.loader import load_daily_volume, load_daily_volume_future

    try:
        dv_past = load_daily_volume()
        dv_future = load_daily_volume_future()

        sites = departments if departments else DEPARTMENTS

        # Machine sub-filter for Lacey
        dv_machine_depts, _, machine_active = _machine_dept_values(machines)
        if machine_active and "Lacey" in sites:
            dv_eff = [s for s in sites if s != "Lacey"] + dv_machine_depts
            dv_past = dv_past[dv_past["Department"].isin(dv_eff)].copy()
            dv_past.loc[dv_past["Department"].isin(dv_machine_depts), "Department"] = "Lacey"
            dv_future = dv_future[dv_future["Department"].isin(dv_eff)].copy()
            dv_future.loc[dv_future["Department"].isin(dv_machine_depts), "Department"] = "Lacey"
        else:
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

        def _vec_time_to_hour(series):
            """Vectorized: convert time strings like '08:30:00' to decimal hours."""
            s = series.astype(str)
            parts = s.str.split(":", n=2, expand=True)
            if parts.shape[1] < 2:
                return pd.Series(np.nan, index=series.index)
            hours = pd.to_numeric(parts[0], errors="coerce")
            mins = pd.to_numeric(parts[1], errors="coerce")
            result = hours + mins / 60
            result[series.isna() | (series == "") | (series == "None")] = np.nan
            return result

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

                # Convert time strings to decimal hours (vectorized)
                site_data["start_hour"] = _vec_time_to_hour(site_data["start_str"])
                site_data["end_hour"] = _vec_time_to_hour(site_data["end_str"])

                # Drop rows with no valid times
                site_data = site_data.dropna(subset=["start_hour", "end_hour"])
                site_data = site_data[site_data["end_hour"] > site_data["start_hour"]]
                if site_data.empty:
                    continue
                site_data = site_data.sort_values("ScheduledDate")

                # Aggregate by week if requested
                if aggregate_weekly:
                    site_data["week_start"] = site_data["ScheduledDate"] - pd.to_timedelta(site_data["ScheduledDate"].dt.weekday, unit='D')
                    weekly = site_data.groupby("week_start").agg({
                        "start_hour": "min",
                        "end_hour": "max",
                    }).reset_index()
                    weekly = weekly.rename(columns={"week_start": "ScheduledDate"})
                    site_data = weekly

                # Include appointment counts for calendar hover info
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
            y_min = np.floor(min_hour * 2) / 2
            y_max = np.ceil(max_hour * 2) / 2
            y_min = max(0, y_min - 0.5)
            y_max = min(24, y_max + 0.5)
        else:
            y_min, y_max = 6, 20

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
# Helper: Resource Utilization Data (for clientside smoothing)
# ---------------------------------------------------------------------------

# Machine → department for filtering; sim resources mapped separately
_RESOURCE_DEPT = {}
for _dept, _machines in MACHINE_MAP.items():
    for _m in _machines:
        _RESOURCE_DEPT[_m] = _dept
_SIM_RESOURCES = ["CT_Sim", "CT_CEN"]

# Colors: department color for treatment machines, colorway for sim resources
_RESOURCE_COLORS = {
    "TrueBeamNorth": "#1976D2",   # Lacey darker blue
    "21EX": "#64B5F6",            # Lacey lighter blue
    "21iX_CEN": DEPARTMENT_COLORS["Centralia"],
    "21iX_AB": DEPARTMENT_COLORS["Aberdeen"],
    "CT_Sim": CHART_COLORWAY[4],  # orange
    "CT_CEN": CHART_COLORWAY[5],  # cyan
}


def _prepare_efficiency_data(departments, machines, agg, start, end):
    """Prepare resource utilization data (Actual/Scheduled active minutes) for clientside rendering."""
    from data.loader import load_daily_volume_by_resource

    try:
        dv = load_daily_volume_by_resource()
        if dv.empty:
            return None

        # Determine which resources to include based on department filter
        sites = departments if departments else DEPARTMENTS

        # Treatment resources: filter by department selection + machine sub-filter
        tx_resources = []
        for site in sites:
            tx_resources.extend(MACHINE_MAP.get(site, []))

        # Apply machine sub-filter for Lacey (only if strict subset selected)
        lacey_machines = set(MACHINE_MAP.get("Lacey", []))
        if machines and "Lacey" in sites:
            selected_lacey = lacey_machines & set(machines)
            if selected_lacey and selected_lacey != lacey_machines:
                tx_resources = [r for r in tx_resources if r not in lacey_machines or r in selected_lacey]

        # Sim resources: always include (not department-specific)
        all_resources = tx_resources + _SIM_RESOURCES

        # Filter data
        dv = dv[dv["Resource"].isin(all_resources)].copy()

        # Need both columns for the ratio
        for col in ["ScheduledActiveMinutes", "ActualActiveMinutes"]:
            if col not in dv.columns:
                return None

        # ActualActiveMinutes only accurate from 2025-10-06 onward
        _ACTIVE_MIN_CUTOFF = pd.Timestamp("2025-10-06")
        dv.loc[dv["ScheduledDate"] < _ACTIVE_MIN_CUTOFF, "ActualActiveMinutes"] = np.nan

        # Date filter
        dv = dv[(dv["ScheduledDate"] >= start) & (dv["ScheduledDate"] <= end)]
        if dv.empty:
            return None

        # Period aggregation
        dv["period"] = dv["ScheduledDate"].dt.to_period(agg).dt.to_timestamp()
        if agg == "D":
            dv = dv[dv["ScheduledDate"].dt.weekday < 5]

        # Sum minutes per period per resource, then compute ratio
        agg_dict = {
            "ActualActiveMinutes": ("ActualActiveMinutes", "sum"),
            "ScheduledActiveMinutes": ("ScheduledActiveMinutes", "sum"),
        }
        if "BeamOnMinutes" in dv.columns:
            agg_dict["BeamOnMinutes"] = ("BeamOnMinutes", "sum")
        grouped = dv.groupby(["period", "Resource"]).agg(**agg_dict).reset_index()
        grouped.rename(columns={"ActualActiveMinutes": "actual", "ScheduledActiveMinutes": "scheduled"}, inplace=True)
        grouped["utilization"] = np.where(
            grouped["scheduled"] > 0,
            (grouped["actual"] / grouped["scheduled"]) * 100,
            np.nan,
        )
        # Cap at 150% — anything higher is bad data (e.g. ActualActiveMinutes = 230k)
        grouped["utilization"] = grouped["utilization"].clip(upper=150)

        all_periods = full_period_range(grouped["period"], agg)
        date_range = [d.isoformat() for d in all_periods]

        # Build series for each resource that has meaningful data
        series = []
        for resource in all_resources:
            res_grp = grouped[grouped["Resource"] == resource].set_index("period")
            res_data = res_grp["utilization"]
            non_null = res_data.dropna()
            if non_null.empty or len(non_null) < 5:
                continue  # Skip resources with too little data (e.g. CT_CEN, 6EX)

            # Find machine go-live: first period with actual data
            first_period = non_null.index.min()

            # ActualActiveMinutes only accurate from Oct 6 2025 onward;
            # values/rawMinutes use the later of go-live and cutoff,
            # beamMinutes is unaffected and still uses first_period.
            _ACTIVE_MIN_CUTOFF = pd.Timestamp("2025-10-06")
            active_start = max(first_period, _ACTIVE_MIN_CUTOFF)

            # Reindex to all periods (NaN for missing)
            res_data_full = res_data.reindex(all_periods)
            res_minutes_full = res_grp["actual"].reindex(all_periods)

            # None before active_start (no trace drawn), 0 for post-start gaps
            values = []
            raw_minutes = []
            for p, util_val, min_val in zip(all_periods, res_data_full, res_minutes_full):
                if p < active_start:
                    values.append(None)
                    raw_minutes.append(None)
                else:
                    # Utilization is a ratio — empty periods stay None, never fake 0
                    if pd.isna(util_val):
                        values.append(None)
                    else:
                        values.append(round(util_val, 1) if util_val > 0 else 0)
                    raw_minutes.append(round(min_val, 1) if pd.notna(min_val) else 0)

            entry = {
                "name": resource,
                "values": values,
                "rawMinutes": raw_minutes,
                "color": _RESOURCE_COLORS.get(resource, CHART_COLORWAY[0]),
            }
            if "BeamOnMinutes" in res_grp.columns:
                beam_full = res_grp["BeamOnMinutes"].reindex(all_periods)
                entry["beamMinutes"] = [
                    None if p < first_period else (round(v, 1) if pd.notna(v) else 0)
                    for p, v in zip(all_periods, beam_full)
                ]
            series.append(entry)

        if not series:
            return None

        return {
            "chartId": "ops-chart-efficiency",
            "dates": date_range,
            "series": series,
            "height": 380,
            "yTitle": "Utilization %",
            "stacked": False,
        }

    except Exception:
        return None


# ---------------------------------------------------------------------------
# Helper: Treatment Volume Data (for clientside smoothing)
# ---------------------------------------------------------------------------

def _prepare_volume_data(departments, machines, agg, start, end):
    """Prepare treatment volume data for clientside rendering (with future projections)."""
    from data.loader import load_daily_volume, load_daily_volume_future

    try:
        dv = load_daily_volume()
        dv_future = load_daily_volume_future()

        # Filter to departments with machine sub-filter for Lacey
        sites = departments if departments else DEPARTMENTS
        dv_machine_depts, _, machine_active = _machine_dept_values(machines)

        def _apply_machine_filter(df):
            if machine_active and "Lacey" in sites:
                dv_eff = [s for s in sites if s != "Lacey"] + dv_machine_depts
                df = df[df["Department"].isin(dv_eff)].copy()
                df.loc[df["Department"].isin(dv_machine_depts), "Department"] = "Lacey"
            else:
                df = df[df["Department"].isin(sites)]
            return df

        dv = _apply_machine_filter(dv)
        dv_future = _apply_machine_filter(dv_future)

        # Date filter (past data only — future handled separately)
        dv = dv[(dv["ScheduledDate"] >= start) & (dv["ScheduledDate"] <= end)]

        if dv.empty:
            return None

        count_col = "AppointmentCount" if "AppointmentCount" in dv.columns else dv.select_dtypes(include='number').columns[0]

        # --- Past data ---
        dv = dv.copy()
        dv["period"] = dv["ScheduledDate"].dt.to_period(agg).dt.to_timestamp()
        if agg == "D":
            dv = dv[dv["ScheduledDate"].dt.weekday < 5]

        grouped = dv.groupby(["period", "Department"])[count_col].sum().reset_index()

        # Filter to active days (total > 0) to remove holidays
        all_periods = full_period_range(grouped["period"], agg)
        if agg == "D":
            total_per_period = grouped.groupby("period")[count_col].sum()
            active_periods = total_per_period[total_per_period > 0].index
            all_periods = sorted(set(all_periods) & set(active_periods))

        # --- Future data ---
        today = pd.Timestamp.now().normalize()
        last_past = dv["ScheduledDate"].max()
        future_start = last_past + timedelta(days=1)
        future_end_limit = last_past + timedelta(days=14)

        dv_future = dv_future[
            (dv_future["ScheduledDate"] > last_past) &
            (dv_future["ScheduledDate"] <= future_end_limit)
        ]

        future_periods = []
        future_grouped = pd.DataFrame()
        if not dv_future.empty:
            dv_future = dv_future.copy()
            dv_future["period"] = dv_future["ScheduledDate"].dt.to_period(agg).dt.to_timestamp()
            if agg == "D":
                dv_future = dv_future[dv_future["ScheduledDate"].dt.weekday < 5]
            future_grouped = dv_future.groupby(["period", "Department"])[count_col].sum().reset_index()

            future_periods = sorted(future_grouped["period"].unique())
            # Exclude periods already in past
            past_period_set = set(all_periods)
            future_periods = [p for p in future_periods if p not in past_period_set]
            # Filter to active days
            if agg == "D" and future_periods:
                ft = future_grouped.groupby("period")[count_col].sum()
                active_future = ft[ft > 0].index
                future_periods = sorted(set(future_periods) & set(active_future))

        # Build series
        series = []
        for site in sites:
            # Past values
            site_data = grouped[grouped["Department"] == site].set_index("period")[count_col]
            site_data = site_data.reindex(all_periods, fill_value=0)

            # Future values
            if future_periods and not future_grouped.empty:
                site_future = future_grouped[future_grouped["Department"] == site].set_index("period")[count_col]
                site_future = site_future.reindex(future_periods, fill_value=0)
            else:
                site_future = pd.Series([], dtype=float)

            series.append({
                "name": site,
                "values": site_data.tolist(),
                "futureValues": site_future.tolist(),
                "color": dept_color(site),
            })

        return {
            "chartId": "ops-chart-volume",
            "dates": [d.isoformat() for d in all_periods],
            "futureDates": [d.isoformat() for d in future_periods],
            "series": series,
            "height": 380,
            "yTitle": "Appointments",
        }

    except Exception:
        return None


# ---------------------------------------------------------------------------
# KPI Callback — outputs cards + raw sparkline data
# ---------------------------------------------------------------------------

def _fmt_time(time_str):
    """Convert HH:MM(:SS) time string to compact display like '7:30a' or '4:45p'."""
    if pd.isna(time_str) or not time_str:
        return None
    try:
        parts = str(time_str).split(":")
        h, m = int(parts[0]), int(parts[1])
        suffix = "a" if h < 12 else "p"
        display_h = h if h <= 12 else h - 12
        if display_h == 0:
            display_h = 12
        return f"{display_h}:{m:02d}{suffix}"
    except (ValueError, IndexError):
        return None


def _time_to_hours(time_str):
    """Convert HH:MM(:SS) time string to decimal hours."""
    if pd.isna(time_str) or not time_str:
        return None
    try:
        parts = str(time_str).split(":")
        return int(parts[0]) + int(parts[1]) / 60
    except (ValueError, IndexError):
        return None


# ---------------------------------------------------------------------------
# Trend helper
# ---------------------------------------------------------------------------

def _trend(curr, prior, invert=False):
    """Return (pct_text, direction, prior_value) for trend display."""
    if prior is None or prior == 0:
        return None, None, None
    pct = (curr - prior) / prior * 100
    direction = ("down" if pct > 0 else "up") if invert else ("up" if pct > 0 else "down")
    return f"{abs(pct):.0f}%", direction, prior


def _machine_dept_values(machines):
    """Return (dv_depts, tx_depts, is_active) for Lacey machine-level filtering.

    Only activates when a strict SUBSET of Lacey machines is selected.
    Returns department values in Daily Volume and Treatment naming conventions.
    """
    lacey_machines = set(MACHINE_MAP["Lacey"])
    if not machines:
        return [], [], False


# ---------------------------------------------------------------------------
# Common filter inputs / unpack / load-and-filter
# ---------------------------------------------------------------------------

_OPS_FILTER_INPUTS = [
    Input("ops-interval", "n_intervals"),
    Input("operations-filter-department", "value"),
    Input("operations-filter-machine", "value"),
]


def _unpack_ops_filter_args(args):
    """Unpack the 3 common filter args into a dict for _load_and_filter_ops."""
    _n, departments, machines = args[:3]
    return dict(departments=departments, machines=machines)


def _load_and_filter_ops(departments, machines):
    """Load core operations datasets, apply department/machine filters.

    Returns a dict with filtered dataframes and computed filter metadata,
    or None if all data is empty.
    """
    from data.loader import load_daily_volume, load_treatment

    try:
        dv = load_daily_volume().copy()
        tx = load_treatment().copy()
    except Exception:
        dv = pd.DataFrame()
        tx = pd.DataFrame()

    if dv.empty and tx.empty:
        return None

    sites = departments if departments else DEPARTMENTS
    dv_machine_depts, tx_machine_depts, machine_active = _machine_dept_values(machines)

    # Filter daily volume
    if not dv.empty and "Department" in dv.columns:
        if machine_active and "Lacey" in sites:
            dv_eff = [s for s in sites if s != "Lacey"] + dv_machine_depts
            dv = dv[dv["Department"].isin(dv_eff)].copy()
            dv.loc[dv["Department"].isin(dv_machine_depts), "Department"] = "Lacey"
        else:
            dv = dv[dv["Department"].isin(sites)]

    # Filter treatment
    if not tx.empty and "Department" in tx.columns:
        if machine_active and "Lacey" in sites:
            tx_eff = [s for s in sites if s != "Lacey"] + tx_machine_depts
            tx = tx[tx["Department"].isin(tx_eff)].copy()
            tx.loc[tx["Department"].isin(tx_machine_depts), "Department"] = "Lacey"
        else:
            tx_sites = [d for d in tx["Department"].unique() if d in sites]
            tx = tx[tx["Department"].isin(tx_sites)]

    return {
        "dv": dv,
        "tx": tx,
        "sites": sites,
        "machines": machines,
        "departments": departments,
        "dv_machine_depts": dv_machine_depts,
        "tx_machine_depts": tx_machine_depts,
        "machine_active": machine_active,
    }
    selected_lacey = lacey_machines & set(machines)
    if not selected_lacey or selected_lacey == lacey_machines:
        return [], [], False
    dv_depts = list(selected_lacey)
    tx_depts = [f"Lacey - {m}" for m in selected_lacey]
    return dv_depts, tx_depts, True


@callback(
    Output("ops-kpi-today", "children"),
    Output("ops-kpi-hours-lacey", "children"),
    Output("ops-kpi-hours-centralia", "children"),
    Output("ops-kpi-hours-aberdeen", "children"),
    Output("ops-kpi-consult-lead", "children"),
    Output("ops-kpi-sim-lead", "children"),
    Output("ops-kpi-new-starts", "children"),
    Output("ops-store-kpi-sparklines", "data"),
    *_OPS_FILTER_INPUTS,
)
def update_kpis(*args):
    """Compute all 6 KPI cards with fixed 30-day sparklines."""
    from data.loader import load_daily_volume, load_clinic_visits, load_simulations

    ctx = _unpack_ops_filter_args(args)
    data = _load_and_filter_ops(**ctx)

    sparkline_data = {}

    na_card = kpi_card("--", "N/A")
    empty_kpis = (na_card,) * 7 + ({},)
    if data is None:
        return empty_kpis

    dv_filtered = data["dv"]
    tx_filtered = data["tx"]
    sites = data["sites"]
    machines = ctx["machines"]
    dv_machine_depts = data["dv_machine_depts"]
    machine_active = data["machine_active"]

    # Need unfiltered dv for per-site hours (all sites, not just selected)
    try:
        dv = load_daily_volume()
    except Exception:
        dv = pd.DataFrame()

    actual_today = pd.Timestamp.now().normalize()
    last_date = dv_filtered["ScheduledDate"].max() if not dv_filtered.empty and "ScheduledDate" in dv_filtered.columns else actual_today
    is_lagged = last_date.normalize() != actual_today

    # ── 1. Today's Treatments ──────────────────────────────────────────
    if not dv_filtered.empty:
        today_data = dv_filtered[dv_filtered["ScheduledDate"] == last_date]
        today_count = int(today_data["AppointmentCount"].sum()) if "AppointmentCount" in today_data.columns else 0

        label = "Today's Treatments"
        # Per-site breakdown
        site_parts = []
        if "AppointmentCount" in today_data.columns:
            for s in DEPARTMENTS:
                if s not in sites:
                    continue
                s_count = int(today_data[today_data["Department"] == s]["AppointmentCount"].sum())
                site_parts.append(f"{s[0]}:{s_count}")
        breakdown = "  ".join(site_parts) if site_parts else ""
        if is_lagged:
            detail = f"({last_date.strftime('%b %-d')})  {breakdown}".strip()
        else:
            detail = breakdown or None

        # Sparkline: daily totals over prior 30 days (weekdays only)
        sp_start = last_date - timedelta(days=30)
        spark_data = dv_filtered[
            (dv_filtered["ScheduledDate"] >= sp_start) &
            (dv_filtered["ScheduledDate"] <= last_date) &
            (dv_filtered["ScheduledDate"].dt.weekday < 5)
        ]
        daily_totals = spark_data.groupby("ScheduledDate")["AppointmentCount"].sum()
        sparkline_data["today"] = {
            "labels": [d.isoformat() for d in daily_totals.index],
            "values": daily_totals.tolist(),
            "color": PRIMARY,
        }

        # Trend: today vs 30d average
        avg_30d = daily_totals.mean() if not daily_totals.empty else None
        trend_text = None
        trend_dir = None
        if avg_30d and avg_30d > 0:
            pct = (today_count - avg_30d) / avg_30d * 100
            trend_text = f"{abs(pct):.0f}% vs avg"
            trend_dir = "up" if pct > 0 else "down"

        kpi_today = kpi_card(
            label, f"{today_count:,}",
            value_detail=detail,
            trend_text=trend_text,
            trend_direction=trend_dir,
            accent_color=PRIMARY,
            sparkline_id="ops-spark-today",
        )
    else:
        kpi_today = kpi_card("Today's Treatments", "N/A")

    # ── 2–4. Site Operating Hours ──────────────────────────────────────
    site_hours_cards = {}
    for site in DEPARTMENTS:
        site_key = site.lower()
        color = DEPARTMENT_COLORS.get(site, PRIMARY)

        if dv.empty:
            site_hours_cards[site] = kpi_card(f"{site} Hours", "N/A", accent_color=color)
            continue

        if site == "Lacey" and machine_active:
            site_dv = dv[dv["Department"].isin(dv_machine_depts)]
        else:
            site_dv = dv[dv["Department"] == site]
        if site_dv.empty:
            site_hours_cards[site] = kpi_card(f"{site} Hours", "N/A", accent_color=color)
            continue

        site_last = site_dv["ScheduledDate"].max()
        site_today_data = site_dv[site_dv["ScheduledDate"] == site_last]

        # Card value: SCHEDULED times (the plan for the day)
        sched_start_col = "FirstScheduledStart" if "FirstScheduledStart" in site_today_data.columns else None
        sched_end_col = "LastScheduledEnd" if "LastScheduledEnd" in site_today_data.columns else None

        start_str = site_today_data[sched_start_col].dropna().iloc[0] if sched_start_col and not site_today_data[sched_start_col].dropna().empty else None
        end_str = site_today_data[sched_end_col].dropna().iloc[0] if sched_end_col and not site_today_data[sched_end_col].dropna().empty else None

        start_fmt = _fmt_time(start_str)
        end_fmt = _fmt_time(end_str)
        start_hrs = _time_to_hours(start_str)
        end_hrs = _time_to_hours(end_str)

        if start_fmt and end_fmt and start_hrs is not None and end_hrs is not None:
            value = f"{start_fmt} – {end_fmt}"
            duration = round(end_hrs - start_hrs, 1)
            hrs_detail = f"{duration} hrs"
        else:
            value = "No data"
            hrs_detail = None

        # Sparkline: ACTUAL duration over prior 30 days (weekdays only)
        sp_start = site_last - timedelta(days=30)
        spark_site = site_dv[
            (site_dv["ScheduledDate"] >= sp_start) &
            (site_dv["ScheduledDate"] <= site_last) &
            (site_dv["ScheduledDate"].dt.weekday < 5)
        ].copy()

        if "FirstActualStart" in spark_site.columns and "LastActualEnd" in spark_site.columns:
            spark_site["_s_hr"] = spark_site["FirstActualStart"].apply(_time_to_hours)
            spark_site["_e_hr"] = spark_site["LastActualEnd"].apply(_time_to_hours)
        else:
            spark_site["_s_hr"] = None
            spark_site["_e_hr"] = None

        spark_site = spark_site.dropna(subset=["_s_hr", "_e_hr"])
        spark_site["_dur"] = spark_site["_e_hr"] - spark_site["_s_hr"]
        spark_site = spark_site[spark_site["_dur"] > 0]

        if not spark_site.empty:
            spark_dur = spark_site.groupby("ScheduledDate")["_dur"].max().sort_index()
            sparkline_data[f"hours_{site_key}"] = {
                "labels": [d.isoformat() for d in spark_dur.index],
                "values": [round(v, 2) for v in spark_dur.tolist()],
                "color": color,
                "hover_fmt": "%{x|%b %d}: %{y:.1f} hrs<extra></extra>",
            }

        site_hours_cards[site] = kpi_card(
            f"{site} Hours", value,
            trend_text=hrs_detail,
            accent_color=color,
            sparkline_id=f"ops-spark-hours-{site_key}",
        )

    # ── 5a–5b. Scheduling Lead Times (separate consult + sim cards) ──
    try:
        cv = load_clinic_visits()
        sims_data = load_simulations()
    except Exception:
        cv = pd.DataFrame()
        sims_data = pd.DataFrame()

    # Filter consults by department; sims always in Lacey so leave unfiltered
    departments = ctx["departments"]
    if departments:
        if not cv.empty and "Department" in cv.columns:
            cv = cv[cv["Department"].isin(sites)]

    def _calc_lead(df, date_col="ScheduledDateTime", max_days=30):
        """Compute lead_days column and return filtered df."""
        if df.empty or date_col not in df.columns or "AppointmentCreatedDate" not in df.columns:
            return pd.DataFrame()
        out = df[df["AppointmentCreatedDate"].notna()].copy()
        if out.empty:
            return out
        out["lead_days"] = (out[date_col] - out["AppointmentCreatedDate"]).dt.days
        return out[(out["lead_days"] >= 0) & (out["lead_days"] <= max_days)]

    def _lead_card(lead_df, label, store_key, spark_id, color, tooltip_text):
        """Build a single scheduling lead KPI card with trend + sparkline."""
        from dash_iconify import DashIconify

        # Value: median lead for future-scheduled appointments
        future = lead_df[lead_df["ScheduledDateTime"] > actual_today] if not lead_df.empty else pd.DataFrame()
        med = future["lead_days"].median() if not future.empty else None
        value = f"{med:.0f}d" if med is not None else "--"

        # Trend + sparkline use AppointmentCreatedDate (when booked)
        # so we measure "how far out were bookings made" over time
        t_text, t_dir = None, None
        if not lead_df.empty and "AppointmentCreatedDate" in lead_df.columns:
            created = lead_df[lead_df["AppointmentCreatedDate"].notna()].copy()
            created["_created_day"] = created["AppointmentCreatedDate"].dt.normalize()
            ref = created["_created_day"].max()

            # Trend: bookings created in past 30d vs prior 30d
            curr = created[
                (created["_created_day"] >= ref - timedelta(days=29)) &
                (created["_created_day"] <= ref)
            ]
            prior = created[
                (created["_created_day"] >= ref - timedelta(days=59)) &
                (created["_created_day"] <= ref - timedelta(days=30))
            ]
            c_m = curr["lead_days"].median() if not curr.empty else None
            p_m = prior["lead_days"].median() if not prior.empty else None
            pt, td, _ = _trend(c_m, p_m, invert=True)
            if pt:
                t_text = f"{pt} vs prior 30d"
                t_dir = td

            # Sparkline: daily median lead by creation date over past 30 days
            sp = created[
                (created["_created_day"] >= ref - timedelta(days=30)) &
                (created["_created_day"] <= ref)
            ]
            if not sp.empty:
                daily = sp.groupby("_created_day")["lead_days"].median().sort_index()
                if not daily.empty:
                    sparkline_data[store_key] = {
                        "labels": [d.isoformat() for d in daily.index],
                        "values": [round(v, 1) for v in daily.tolist()],
                        "color": color,
                        "hover_fmt": "%{x|%b %d}: %{y:.0f}d<extra></extra>",
                    }

        info_icon = dmc.Tooltip(
            label=tooltip_text,
            position="top",
            withArrow=True,
            multiline=True,
            w=220,
            children=DashIconify(
                icon="mdi:information-outline",
                width=16, color="#9CA3AF",
                style={"cursor": "help"},
            ),
        )

        return kpi_card(
            label, value,
            trend_text=t_text,
            trend_direction=t_dir,
            accent_color=color,
            sparkline_id=spark_id,
            header_control=info_icon,
        )

    cv_lead = _calc_lead(cv, max_days=30)
    sim_lead = _calc_lead(sims_data, max_days=21)

    kpi_consult_lead = _lead_card(
        cv_lead, "Consult Lead", "consult_lead", "ops-spark-consult-lead", CHART_COLORWAY[1],
        "Forward-looking: median days from booking to appointment for consults not yet occurred. Excludes >30d. Trend and sparkline track by booking creation date.",
    )
    kpi_sim_lead = _lead_card(
        sim_lead, "Sim Lead", "sim_lead", "ops-spark-sim-lead", CHART_COLORWAY[2],
        "Forward-looking: median days from booking to appointment for sims not yet occurred. Excludes >21d. Trend and sparkline track by booking creation date.",
    )

    # ── 6. New Starts — future 7d value, past trend/sparkline ────────
    from data.loader import load_daily_volume_future as _load_dv_future

    # --- Future value: upcoming 7 days from Daily Volume Future ---
    try:
        dv_fut = _load_dv_future()
    except Exception:
        dv_fut = pd.DataFrame()

    future_ns_total = 0
    future_ns_detail = None
    if not dv_fut.empty and "NewStartCount" in dv_fut.columns and "ScheduledDate" in dv_fut.columns:
        fut_start = actual_today + timedelta(days=1)
        fut_end = actual_today + timedelta(days=7)
        dv_fut_7d = dv_fut[
            (dv_fut["ScheduledDate"] >= fut_start) &
            (dv_fut["ScheduledDate"] <= fut_end)
        ]
        # Apply department filter
        if machine_active and "Lacey" in sites:
            dv_eff_fut = [s for s in sites if s != "Lacey"] + dv_machine_depts
            dv_fut_7d = dv_fut_7d[dv_fut_7d["Department"].isin(dv_eff_fut)].copy()
            dv_fut_7d.loc[dv_fut_7d["Department"].isin(dv_machine_depts), "Department"] = "Lacey"
        else:
            dv_fut_7d = dv_fut_7d[dv_fut_7d["Department"].isin(sites)]

        future_ns_total = int(dv_fut_7d["NewStartCount"].sum())
        # Per-site breakdown
        site_breakdown = []
        for site in DEPARTMENTS:
            if site not in sites:
                continue
            s_ns = int(dv_fut_7d[dv_fut_7d["Department"] == site]["NewStartCount"].sum())
            site_breakdown.append(f"{site[0]}:{s_ns}")
        future_ns_detail = "  ".join(site_breakdown) if site_breakdown else None

    # --- Trend + sparkline: past data from Treatment.csv ---
    ns_col = None
    if not tx_filtered.empty and "ScheduledDate" in tx_filtered.columns:
        ns_col = next((c for c in tx_filtered.columns if "NewStarts" in c and "Course" in c), None)

    ns_trend_text = None
    ns_trend_dir = None
    if ns_col and not tx_filtered.empty:
        tx_last = tx_filtered["ScheduledDate"].max()

        # Trend: most recent 7d vs prior 7d
        ns_start = tx_last - timedelta(days=6)
        tx_7d = tx_filtered[
            (tx_filtered["ScheduledDate"] >= ns_start) &
            (tx_filtered["ScheduledDate"] <= tx_last)
        ]
        recent_starts = int(tx_7d[ns_col].sum())

        prior_7d_start = tx_last - timedelta(days=13)
        prior_7d_end = tx_last - timedelta(days=7)
        tx_prior_7d = tx_filtered[
            (tx_filtered["ScheduledDate"] >= prior_7d_start) &
            (tx_filtered["ScheduledDate"] <= prior_7d_end)
        ]
        prior_starts = int(tx_prior_7d[ns_col].sum()) if not tx_prior_7d.empty else None
        pt, td, _ = _trend(recent_starts, prior_starts)
        if pt:
            ns_trend_text = f"{pt} vs prior 7d"
            ns_trend_dir = td

        # Sparkline: daily new starts over prior 30 days
        sp_start = tx_last - timedelta(days=30)
        tx_spark = tx_filtered[
            (tx_filtered["ScheduledDate"] >= sp_start) &
            (tx_filtered["ScheduledDate"] <= tx_last)
        ]
        daily_ns = tx_spark.groupby("ScheduledDate")[ns_col].sum().sort_index()
        sparkline_data["newstarts"] = {
            "labels": [d.isoformat() for d in daily_ns.index],
            "values": daily_ns.tolist(),
            "color": CHART_COLORWAY[4],
        }

    kpi_new = kpi_card(
        "New Starts (next 7d)", str(future_ns_total),
        value_detail=future_ns_detail or "upcoming",
        trend_text=ns_trend_text,
        trend_direction=ns_trend_dir,
        accent_color=CHART_COLORWAY[4],
        sparkline_id="ops-spark-newstarts",
    ) if future_ns_total > 0 or ns_col else kpi_card("New Starts", "N/A")

    return (
        kpi_today,
        site_hours_cards.get("Lacey", kpi_card("Lacey Hours", "N/A")),
        site_hours_cards.get("Centralia", kpi_card("Centralia Hours", "N/A")),
        site_hours_cards.get("Aberdeen", kpi_card("Aberdeen Hours", "N/A")),
        kpi_consult_lead,
        kpi_sim_lead,
        kpi_new,
        sparkline_data,
    )


# ---------------------------------------------------------------------------
# Clientside callbacks for KPI sparklines (with smoothing)
# ---------------------------------------------------------------------------

# Today's Treatments sparkline
clientside_callback("""function() {
        var fig = window.dash_clientside.sparklines.smoothOpsToday.apply(null, arguments);
        return window.dash_clientside.chartDeferred.wrap("ops-spark-today", fig);
    }""",
    Output("ops-spark-today", "figure"),
    Input("ops-store-kpi-sparklines", "data"),
    Input("ops-filter-smoothing", "value"),
    prevent_initial_call=True,
)

# Site hours sparklines (duration in hours)
clientside_callback("""function() {
        var fig = window.dash_clientside.sparklines.smoothOpsHoursLacey.apply(null, arguments);
        return window.dash_clientside.chartDeferred.wrap("ops-spark-hours-lacey", fig);
    }""",
    Output("ops-spark-hours-lacey", "figure"),
    Input("ops-store-kpi-sparklines", "data"),
    Input("ops-filter-smoothing", "value"),
    prevent_initial_call=True,
)

clientside_callback("""function() {
        var fig = window.dash_clientside.sparklines.smoothOpsHoursCentralia.apply(null, arguments);
        return window.dash_clientside.chartDeferred.wrap("ops-spark-hours-centralia", fig);
    }""",
    Output("ops-spark-hours-centralia", "figure"),
    Input("ops-store-kpi-sparklines", "data"),
    Input("ops-filter-smoothing", "value"),
    prevent_initial_call=True,
)

clientside_callback("""function() {
        var fig = window.dash_clientside.sparklines.smoothOpsHoursAberdeen.apply(null, arguments);
        return window.dash_clientside.chartDeferred.wrap("ops-spark-hours-aberdeen", fig);
    }""",
    Output("ops-spark-hours-aberdeen", "figure"),
    Input("ops-store-kpi-sparklines", "data"),
    Input("ops-filter-smoothing", "value"),
    prevent_initial_call=True,
)

# Consult Lead sparkline
clientside_callback("""function() {
        var fig = window.dash_clientside.sparklines.smoothOpsConsultLead.apply(null, arguments);
        return window.dash_clientside.chartDeferred.wrap("ops-spark-consult-lead", fig);
    }""",
    Output("ops-spark-consult-lead", "figure"),
    Input("ops-store-kpi-sparklines", "data"),
    Input("ops-filter-smoothing", "value"),
    prevent_initial_call=True,
)

# Sim Lead sparkline
clientside_callback("""function() {
        var fig = window.dash_clientside.sparklines.smoothOpsSimLead.apply(null, arguments);
        return window.dash_clientside.chartDeferred.wrap("ops-spark-sim-lead", fig);
    }""",
    Output("ops-spark-sim-lead", "figure"),
    Input("ops-store-kpi-sparklines", "data"),
    Input("ops-filter-smoothing", "value"),
    prevent_initial_call=True,
)

# New Starts sparkline (daily)
clientside_callback("""function() {
        var fig = window.dash_clientside.sparklines.smoothOpsNewStarts.apply(null, arguments);
        return window.dash_clientside.chartDeferred.wrap("ops-spark-newstarts", fig);
    }""",
    Output("ops-spark-newstarts", "figure"),
    Input("ops-store-kpi-sparklines", "data"),
    Input("ops-filter-smoothing", "value"),
    prevent_initial_call=True,
)


# ---------------------------------------------------------------------------
# Volume Chart Callback — outputs raw data to store
# ---------------------------------------------------------------------------

@callback(
    Output("ops-store-volume", "data"),
    *_OPS_FILTER_INPUTS,
    Input("ops-volume-agg", "value"),
    running=[(Output("ops-chart-volume-loading", "visible"), True, False)],
)
def update_volume_data(*args):
    """Load ALL treatment volume data to store (time window applied clientside)."""
    from data.loader import load_daily_volume

    ctx = _unpack_ops_filter_args(args)
    agg = args[3]

    try:
        dv = load_daily_volume()
        if dv.empty:
            return None

        start = dv["ScheduledDate"].min()
        last_date = dv["ScheduledDate"].max()
        return _prepare_volume_data(ctx["departments"], ctx["machines"], agg, start, last_date)
    except Exception:
        return None


# Clientside callback for volume chart smoothing with chart type and time window
clientside_callback("""function() {
        return window.dash_clientside.census.smoothChartWithTypeAndRange.apply(null, arguments);
    }""",
    Output("ops-chart-volume", "figure"),
    Input("ops-store-volume", "data"),
    Input("ops-volume-settings-smooth", "value"),
    Input("ops-volume-settings-type", "value"),
    Input("ops-volume-range", "value"),
    Input("ops-volume-settings-stack", "value"),
    State("ops-chart-volume", "figure"),
    prevent_initial_call=True,
)

# Dynamic y-axis rescaling on pan for volume chart
clientside_callback(
    ClientsideFunction(namespace="censusYAxis", function_name="updateOnPan"),
    Output("ops-chart-volume", "figure", allow_duplicate=True),
    Input("ops-chart-volume", "relayoutData"),
    State("ops-chart-volume", "figure"),
    State("ops-store-volume", "data"),
    State("ops-volume-settings-type", "value"),
    State("ops-volume-settings-stack", "value"),
    prevent_initial_call=True,
)


# Disable Daily aggregation for bar charts with long ranges (volume)
clientside_callback(
    ClientsideFunction(namespace="barAggGuard", function_name="update"),
    Output("ops-volume-agg", "data"),
    Output("ops-volume-agg", "value"),
    Input("ops-volume-settings-type", "value"),
    Input("ops-volume-range", "value"),
    State("ops-volume-agg", "value"),
    prevent_initial_call=True,
)



@callback(
    Output("ops-volume-settings-smooth", "max"),
    Output("ops-volume-settings-smooth", "value"),
    Input("ops-volume-range", "value"),
    State("ops-volume-settings-smooth", "value"),
)
def update_volume_smooth_slider(range_days, current_value):
    return smooth_limits(range_days, current_value)


# ---------------------------------------------------------------------------
# Heatmap Callback — combines future schedule + availability
# ---------------------------------------------------------------------------

@callback(
    Output("ops-chart-heatmap", "figure"),
    *_OPS_FILTER_INPUTS,
    Input("ops-heatmap-scope", "value"),
    Input("global-theme-store", "data"),
    running=[(Output("ops-chart-heatmap-loading", "visible"), True, False)],
)
def update_heatmap(*args):
    """Build combined heatmap of treatment schedule + exam/sim availability."""
    from data.loader import load_daily_volume_future, load_schedule_upcoming, load_clinic_visits, load_simulations

    ctx = _unpack_ops_filter_args(args)
    scope = args[3]
    theme = args[4] if len(args) > 4 else "light"
    is_dark = (theme or "light") == "dark"
    departments = ctx["departments"]
    machines = ctx["machines"]
    consults_only = scope != "all"

    try:
        dv = load_daily_volume_future()
        avail = load_schedule_upcoming()
        cv = load_clinic_visits()
        sims_all = load_simulations()

        today = pd.Timestamp.now(tz="America/Los_Angeles").normalize().tz_localize(None)
        four_weeks = today + timedelta(days=28)

        # Filter future volume — Department column has machine names after reshape
        dv = dv[(dv["ScheduledDate"] >= today) & (dv["ScheduledDate"] <= four_weeks)]
        sites = departments if departments else DEPARTMENTS

        # Derive machines from selected departments (exclude retired)
        machines_to_show = []
        for s in sites:
            machines_to_show.extend(m for m in MACHINE_MAP.get(s, []) if m not in RETIRED_MACHINES)
        if not machines_to_show:
            machines_to_show = [m for m in MACHINES if m not in RETIRED_MACHINES]

        exam_suffix = "Consult" if consults_only else "Exam"
        exam_labels = [f"{site} {exam_suffix}" for site in sites]
        n_machines = len(machines_to_show)
        n_exams = len(exam_labels)
        n_sim = 1

        # Generate date range (next 28 calendar days, weekdays only)
        date_range = pd.date_range(today, four_weeks, freq="D")
        date_range = date_range[date_range.weekday < 5]
        # Compact labels: just day number, hover has full detail
        x_date_labels = [f"{d.day}" for d in date_range]
        x_day_labels = [d.strftime('%a') for d in date_range]
        x_hover_labels = [f"{d.strftime('%a')} {d.month}/{d.day}" for d in date_range]
        n_dates = len(date_range)

        # ── Machines: appointment counts (purple heatmap) ──────────────
        z_machines = np.zeros((n_machines, n_dates))
        if not dv.empty and "AppointmentCount" in dv.columns:
            for i, machine in enumerate(machines_to_show):
                machine_data = dv[dv["Department"] == machine]
                for j, date in enumerate(date_range):
                    day_data = machine_data[machine_data["ScheduledDate"] == date]
                    z_machines[i, j] = int(day_data["AppointmentCount"].sum()) if not day_data.empty else 0

        # ── Exams & Sims: availability (green→red heatmap) ────────────
        avail_future = avail[
            (avail["SlotDate"] >= today) & (avail["SlotDate"] <= four_weeks)
        ] if not avail.empty and "SlotDate" in avail.columns else pd.DataFrame()

        # 8:00 AM 30-min sim warmup placeholders are dropped at the loader
        # layer (see _schedule_upcoming_inner). Only the lunch hold
        # (hour=12) is filtered here at the page level.
        if not avail_future.empty and "Category" in avail_future.columns:
            _is_sim = avail_future["Category"].str.contains("Simulation", case=False, na=False)
            _hour = avail_future["AppointmentDateTime"].dt.hour
            avail_future = avail_future[~(_is_sim & (_hour == 12))]

        # Exam availability: open holds per dept per day
        exam_avail = avail_future[
            avail_future["Category"].str.contains("Exam", case=False, na=False)
        ] if not avail_future.empty and "Category" in avail_future.columns else pd.DataFrame()
        if consults_only and not exam_avail.empty and "ActivityName" in exam_avail.columns:
            exam_avail = exam_avail[exam_avail["ActivityName"].str.contains("Consult", case=False, na=False)]

        # Scheduled exams (clinic visits, exclude cancelled)
        cv_future = cv[
            (cv["ScheduledDateTime"] >= today) & (cv["ScheduledDateTime"] <= four_weeks)
        ] if not cv.empty and "ScheduledDateTime" in cv.columns else pd.DataFrame()
        if not cv_future.empty and "Status" in cv_future.columns:
            cv_future = cv_future[~cv_future["Status"].str.contains("Cancel|Deleted", case=False, na=False)]
        if consults_only and not cv_future.empty and "ActivityName" in cv_future.columns:
            cv_future = cv_future[cv_future["ActivityName"].str.contains("Consult", case=False, na=False)]
        if departments and not cv_future.empty and "Department" in cv_future.columns:
            cv_future = cv_future[cv_future["Department"].isin(sites)]

        # Sim availability: open holds per day
        sim_avail = avail_future[
            avail_future["Category"].str.contains("Simulation", case=False, na=False)
        ] if not avail_future.empty and "Category" in avail_future.columns else pd.DataFrame()

        # Scheduled sims (exclude cancelled)
        sims_future = sims_all[
            (sims_all["ScheduledDateTime"] >= today) & (sims_all["ScheduledDateTime"] <= four_weeks)
        ] if not sims_all.empty and "ScheduledDateTime" in sims_all.columns else pd.DataFrame()
        if not sims_future.empty and "Status" in sims_future.columns:
            sims_future = sims_future[~sims_future["Status"].str.contains("Cancel|Deleted", case=False, na=False)]

        # Build exam matrices: z_pct (for color), text (cell label), hover text
        z_exam_pct = np.full((n_exams, n_dates), 100.0)
        text_exams = np.full((n_exams, n_dates), "", dtype=object)
        hover_exams = np.full((n_exams, n_dates), "", dtype=object)

        for dept_i, dept in enumerate(sites):
            dept_exam_open = exam_avail[exam_avail["Department"] == dept] if not exam_avail.empty and "Department" in exam_avail.columns else exam_avail
            if not dept_exam_open.empty and "SlotTaken" in dept_exam_open.columns:
                dept_open_only = dept_exam_open[dept_exam_open["SlotTaken"] != "Yes"]
            else:
                dept_open_only = dept_exam_open

            dept_cv = cv_future[cv_future["Department"] == dept] if not cv_future.empty and "Department" in cv_future.columns else cv_future

            for j, date in enumerate(date_range):
                day_open = dept_open_only[dept_open_only["SlotDate"] == date] if not dept_open_only.empty else pd.DataFrame()
                open_count = len(day_open)
                sched_count = len(dept_cv[dept_cv["ScheduledDateTime"].dt.normalize() == date]) if not dept_cv.empty else 0
                total = sched_count + open_count
                pct = (sched_count / total * 100) if total > 0 else 100
                z_exam_pct[dept_i, j] = pct

                # Extract physician names from open slots
                mds = []
                if not day_open.empty and "AssignedResource" in day_open.columns:
                    for res in day_open["AssignedResource"].dropna().unique():
                        if "," in str(res):
                            mds.append(res.split(",")[0].strip())
                md_str = ", ".join(sorted(set(mds)))

                if total == 0:
                    text_exams[dept_i, j] = "—"
                    hover_exams[dept_i, j] = f"{x_hover_labels[j]}: no slots"
                elif open_count == 0:
                    text_exams[dept_i, j] = "Full"
                    hover_exams[dept_i, j] = f"{x_hover_labels[j]}: {sched_count}/{total} — Full"
                else:
                    text_exams[dept_i, j] = str(open_count)
                    detail = f"{open_count} open — {md_str}" if md_str else f"{open_count} open"
                    hover_exams[dept_i, j] = f"{x_hover_labels[j]}: {sched_count}/{total}<br>{detail}"

        # Build sim matrix
        z_sim_pct = np.full((n_sim, n_dates), 100.0)
        text_sim = np.full((n_sim, n_dates), "", dtype=object)
        hover_sim = np.full((n_sim, n_dates), "", dtype=object)

        if not sim_avail.empty and "SlotTaken" in sim_avail.columns:
            sim_open_only = sim_avail[sim_avail["SlotTaken"] != "Yes"]
        else:
            sim_open_only = sim_avail

        for j, date in enumerate(date_range):
            open_count = len(sim_open_only[sim_open_only["SlotDate"] == date]) if not sim_open_only.empty else 0
            sched_count = len(sims_future[sims_future["ScheduledDateTime"].dt.normalize() == date]) if not sims_future.empty else 0
            total = sched_count + open_count
            pct = (sched_count / total * 100) if total > 0 else 100
            z_sim_pct[0, j] = pct
            if total == 0:
                text_sim[0, j] = "—"
                hover_sim[0, j] = f"{x_hover_labels[j]}: no slots"
            elif open_count == 0:
                text_sim[0, j] = "Full"
                hover_sim[0, j] = f"{x_hover_labels[j]}: {sched_count}/{total} — Full"
            else:
                text_sim[0, j] = str(open_count)
                hover_sim[0, j] = f"{x_hover_labels[j]}: {sched_count}/{total}<br>{open_count} open"

        # ── Build figure ──────────────────────────────────────────────
        fig = make_subplots(
            rows=3, cols=1,
            shared_xaxes=True,
            vertical_spacing=0.06,
            row_heights=[n_machines, max(n_exams, 1), n_sim],
        )

        # Machines: purple heatmap. Theme-aware so the visual hierarchy
        # reads "more = louder" in both modes:
        #   light: near-white tint → deep brand purple (low cells recede).
        #   dark : dim purple-charcoal → bright brand purple (low cells
        #          blend with the dark card; high cells pop).
        # Without this swap the light-mode scale leaves zero-value cells
        # blazing white in dark mode while busy cells go dark and disappear.
        if is_dark:
            purple_cs = [[0, "#3A2540"], [1, "#CD8AD0"]]
            high_text = "#1F1226"   # near-black-purple, readable on bright cells
            low_text  = "#E5BCE9"   # bright tint, readable on dim cells
            text_threshold = 0.65   # cells stay dark longer in this gradient
        else:
            purple_cs = [[0, "#F3E8F5"], [1, "#7C2A83"]]
            high_text = "white"
            low_text  = "#4A1F50"
            text_threshold = 0.45
        machine_zmax = float(z_machines.max()) if z_machines.max() > 0 else 1
        text_machines = np.where(np.isnan(z_machines), "", z_machines.astype(int).astype(str))
        # Per-cell text color array. Plotly.js accepts a 2D array for
        # heatmap.textfont.color (one entry per cell), but Plotly Python's
        # validator rejects arrays at trace-construction time. Workaround:
        # build the trace with a single color so it validates, then patch
        # the figure dict before returning so the array reaches the browser.
        norm_machines = (
            z_machines / machine_zmax if machine_zmax > 0 else z_machines * 0
        )
        # Light cells get dark text, darker cells stay light. NaN cells
        # render no text so their color is moot.
        machine_text_colors = np.where(
            norm_machines >= text_threshold, high_text, low_text
        ).tolist()
        hover_cd = np.tile(x_hover_labels, (n_machines, 1))
        fig.add_trace(go.Heatmap(
            z=z_machines,
            x=x_date_labels,
            y=machines_to_show,
            customdata=hover_cd,
            colorscale=purple_cs,
            zmin=0, zmax=machine_zmax,
            text=text_machines,
            texttemplate="%{text}",
            textfont={"size": 9, "color": "white"},
            hovertemplate="<b>%{y}</b><br>%{customdata}: %{z:.0f} appts<extra></extra>",
            showscale=False,
        ), row=1, col=1)
        # Track the machine trace index so the dict patch below knows which
        # entry to mutate. It's the first trace added, but compute it
        # explicitly in case the layout above changes.
        machines_trace_idx = len(fig.data) - 1

        # Exams + Sims: green→red heatmap (% booked)
        avail_cs = [
            [0, "#4CAF50"],       # Green - wide open
            [0.50, "#8BC34A"],    # Light green
            [0.75, "#FFC107"],    # Amber
            [0.90, "#FF9800"],    # Orange
            [1, "#D32F2F"],       # Red - full
        ]

        fig.add_trace(go.Heatmap(
            z=z_exam_pct,
            x=x_date_labels,
            y=exam_labels,
            colorscale=avail_cs,
            zmin=0, zmax=100,
            text=text_exams,
            texttemplate="%{text}",
            textfont={"size": 11, "color": "#1F2937"},
            customdata=hover_exams,
            hovertemplate="<b>%{y}</b><br>%{customdata}<extra></extra>",
            showscale=False,
        ), row=2, col=1)

        fig.add_trace(go.Heatmap(
            z=z_sim_pct,
            x=x_date_labels,
            y=["Simulation"],
            colorscale=avail_cs,
            zmin=0, zmax=100,
            text=text_sim,
            texttemplate="%{text}",
            textfont={"size": 11, "color": "#1F2937"},
            customdata=hover_sim,
            hovertemplate="<b>%{y}</b><br>%{customdata}<extra></extra>",
            showscale=False,
        ), row=3, col=1)

        # Day-of-week annotations below the bottom subplot. Theme-aware
        # font color so the letters (and the month/day labels above) stay
        # legible in dark mode — the hardcoded light-mode greys (#6B7280
        # / #9CA3AF) aren't in the theme sweeper's remap table, so they'd
        # otherwise render as dim grey on the dark card.
        day_label_color = "#C8CAD2" if is_dark else "#6B7280"
        week_label_color = "#AAADB7" if is_dark else "#9CA3AF"
        annotations = []
        num_cols = len(x_day_labels)
        for i, day_label in enumerate(x_day_labels):
            x_pos = (i + 0.5) / num_cols
            annotations.append(dict(
                x=x_pos,
                y=-0.01,
                text=day_label[:1],  # Single letter: M, T, W, T, F
                xref="x domain",
                yref="paper",
                showarrow=False,
                font=dict(size=9, color=day_label_color),
                xanchor="center",
                yanchor="top",
            ))

        # Week start annotations (month/day) above each Monday
        for i, d in enumerate(date_range):
            if d.weekday() == 0:  # Monday
                x_pos = (i + 0.5) / num_cols
                annotations.append(dict(
                    x=x_pos,
                    y=1.02,
                    text=f"{d.month}/{d.day}",
                    xref="x domain",
                    yref="paper",
                    showarrow=False,
                    font=dict(size=9, color=week_label_color, weight="bold"),
                    xanchor="center",
                    yanchor="bottom",
                ))

        # Vertical week separators (span full height via paper coords)
        shapes = []
        for i, d in enumerate(date_range):
            if d.weekday() == 4 and i < len(date_range) - 1:
                shapes.append(dict(
                    type="line",
                    x0=i + 0.5, x1=i + 0.5,
                    y0=0, y1=1,
                    line=dict(color="#FFFFFF", width=2),
                    xref="x", yref="paper",
                ))

        # 1px border around each subplot group
        n_cols = len(date_range)
        for group_i, n_rows, yref in [
            (1, n_machines, "y"),
            (2, n_exams, "y2"),
            (3, n_sim, "y3"),
        ]:
            shapes.append(dict(
                type="rect",
                x0=-0.5, x1=n_cols - 0.5,
                y0=-0.5, y1=n_rows - 0.5,
                line=dict(color="#D1D5DB", width=1),
                fillcolor="rgba(0,0,0,0)",
                xref="x", yref=yref,
            ))

        fig.update_layout(
            height=380,
            font=dict(family=FONT_FAMILY, size=10),
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            margin=dict(l=76, r=8, t=24, b=16),
            annotations=annotations,
            shapes=shapes,
            hoverlabel=dict(
                bgcolor="white",
                bordercolor="#D1D5DB",
                font=dict(family=FONT_FAMILY, size=11, color="#374151"),
                align="left",
            ),
        )

        # Style each subplot's axes — hide x tick labels, use annotations instead
        fig.update_xaxes(showticklabels=False, row=1, col=1)
        for row_i in range(1, 4):
            fig.update_yaxes(
                autorange="reversed",
                tickfont=dict(size=9),
                row=row_i, col=1,
            )
            if row_i > 1:
                fig.update_xaxes(showticklabels=False, row=row_i, col=1)

        # Patch per-cell text color into the machines heatmap. We do this on
        # the dict (not the Figure) because Plotly Python's validator rejects
        # arrays for heatmap.textfont.color even though Plotly.js accepts
        # them. Returning a plain dict from the callback bypasses revalidation
        # — Dash serializes it directly to the browser.
        fig_dict = fig.to_dict()
        try:
            fig_dict["data"][machines_trace_idx]["textfont"]["color"] = machine_text_colors
        except (KeyError, IndexError):
            pass
        return fig_dict

    except Exception:
        return empty_figure("Unable to load schedule data")


# ---------------------------------------------------------------------------
# Operating Hours — reusable component callbacks + server data
# ---------------------------------------------------------------------------

register_hours_ribbon_callbacks("ops")

@callback(
    Output("ops-store-hours", "data"),
    *_OPS_FILTER_INPUTS,
    Input("ops-hours-site", "value"),
    running=[(Output("ops-hours-loading", "visible"), True, False)],
)
def update_hours_data(*args):
    """Load operating hours data to store."""
    ctx = _unpack_ops_filter_args(args)
    site_filter = args[3]

    if site_filter and site_filter != "all":
        sites = [site_filter]
    else:
        sites = ctx["departments"] if ctx["departments"] else None
    result = _prepare_hours_data(sites, ctx["machines"], days_back=0, aggregate_weekly=False)
    if result:
        result["height"] = 380
    return result

# Clientside callback to attach heatmap hover highlight
clientside_callback(
    ClientsideFunction(namespace="heatmapHover", function_name="init"),
    Output("ops-chart-heatmap", "className"),
    Input("ops-chart-heatmap", "figure"),
    prevent_initial_call=True,
)


# ---------------------------------------------------------------------------
# Efficiency Chart Callback — outputs raw data to store
# ---------------------------------------------------------------------------

@callback(
    Output("ops-store-efficiency", "data"),
    *_OPS_FILTER_INPUTS,
    Input("ops-efficiency-agg", "value"),
    running=[(Output("ops-chart-efficiency-loading", "visible"), True, False)],
)
def update_efficiency_data(*args):
    """Load resource utilization data to store (time window applied clientside)."""
    from data.loader import load_daily_volume_by_resource

    ctx = _unpack_ops_filter_args(args)
    agg = args[3]

    try:
        dv = load_daily_volume_by_resource()
        if dv.empty:
            return None
        start = dv["ScheduledDate"].min()
        last_date = dv["ScheduledDate"].max()
        return _prepare_efficiency_data(ctx["departments"], ctx["machines"], agg, start, last_date)
    except Exception:
        return None


# Clientside callback for efficiency chart with machine filter + metric toggle
clientside_callback("""function() {
        var fig = window.dash_clientside.efficiency.renderWithFilters.apply(null, arguments);
        return window.dash_clientside.chartDeferred.wrap("ops-chart-efficiency", fig);
    }""",
    Output("ops-chart-efficiency", "figure"),
    Input("ops-store-efficiency", "data"),
    Input("ops-efficiency-settings-smooth", "value"),
    Input("ops-efficiency-settings-type", "value"),
    Input("ops-efficiency-range", "value"),
    Input("ops-efficiency-machines", "value"),
    Input("ops-efficiency-metric", "value"),
    State("ops-chart-efficiency", "figure"),
    prevent_initial_call=True,
)

# Dynamic y-axis rescaling on pan for efficiency chart
clientside_callback(
    ClientsideFunction(namespace="efficiency", function_name="updateOnPan"),
    Output("ops-chart-efficiency", "figure", allow_duplicate=True),
    Input("ops-chart-efficiency", "relayoutData"),
    State("ops-chart-efficiency", "figure"),
    State("ops-store-efficiency", "data"),
    State("ops-efficiency-machines", "value"),
    State("ops-efficiency-metric", "value"),
    State("ops-efficiency-settings-type", "value"),
    prevent_initial_call=True,
)

@callback(
    Output("ops-efficiency-settings-smooth", "max"),
    Output("ops-efficiency-settings-smooth", "value"),
    Input("ops-efficiency-range", "value"),
    State("ops-efficiency-settings-smooth", "value"),
)
def update_efficiency_smooth_slider(range_days, current_value):
    return smooth_limits(range_days, current_value)

# Disable Daily aggregation for bar charts with long ranges (efficiency)
clientside_callback(
    ClientsideFunction(namespace="barAggGuard", function_name="update"),
    Output("ops-efficiency-agg", "data"),
    Output("ops-efficiency-agg", "value"),
    Input("ops-efficiency-settings-type", "value"),
    Input("ops-efficiency-range", "value"),
    State("ops-efficiency-agg", "value"),
    prevent_initial_call=True,
)



# ---------------------------------------------------------------------------
# Daily Detail Table Column Definitions Callback
# ---------------------------------------------------------------------------

@callback(
    Output("ops-table", "columnDefs"),
    Input("ops-table-view-by", "value"),
)
def update_table_columns(view_by):
    """Update column headers based on view mode."""
    location_header = "Machine" if view_by == "machine" else "Location"

    return [
        {"field": "Date", "width": 110},
        {"field": "Location", "headerName": location_header, "width": 130},
        {"field": "Appts", "headerName": "Appts", "type": "numericColumn", "width": 80},
        {"field": "Completed", "type": "numericColumn", "width": 100},
        {"field": "Patients", "type": "numericColumn", "width": 90},
        {"field": "Plans", "type": "numericColumn", "width": 80},
        {"field": "New Starts", "type": "numericColumn", "width": 100},
        {"field": "Sched Start", "width": 105},
        {"field": "Sched End", "width": 95},
        {"field": "Actual Start", "width": 105},
        {"field": "Actual End", "width": 95},
        {"field": "Dur (hrs)", "type": "numericColumn", "width": 90},
        {"field": "Sched Min", "type": "numericColumn", "width": 95},
        {"field": "Actual Min", "type": "numericColumn", "width": 95},
        {"field": "Beam Min", "type": "numericColumn", "width": 90},
        {"field": "Appt Min", "type": "numericColumn", "width": 85},
    ]


# ---------------------------------------------------------------------------
# Daily Detail Table Data Callback
# ---------------------------------------------------------------------------

@callback(
    Output("ops-table", "rowData"),
    *_OPS_FILTER_INPUTS,
    Input("ops-volume-range", "value"),
    Input("ops-table-include-future", "checked"),
    Input("ops-table-view-by", "value"),
)
def update_table(*args):
    """Build daily detail table data with optional future data and machine-level detail."""
    from data.loader import load_daily_volume, load_daily_volume_future, load_treatment

    ctx = _unpack_ops_filter_args(args)
    range_days = args[3]
    include_future = args[4]
    view_by = args[5]
    departments = ctx["departments"]
    machines = ctx["machines"]

    try:
        dv_past = load_daily_volume()
        dv_future = load_daily_volume_future() if include_future else pd.DataFrame()
        tx = load_treatment()

        if dv_past.empty and dv_future.empty:
            return []

        # Combine past and future data
        dv = pd.concat([dv_past, dv_future], ignore_index=True) if not dv_past.empty and not dv_future.empty else (dv_past if not dv_past.empty else dv_future)

        last_date_past = dv_past["ScheduledDate"].max() if not dv_past.empty else pd.Timestamp.now().normalize()
        today = pd.Timestamp.now().normalize()

        # For range calculation, use last_date_past for historical data
        # For future data, include up to 14 days ahead if enabled
        days = int(range_days) if range_days else 90

        if days > 0:
            start = last_date_past - timedelta(days=days - 1)
            end = (today + timedelta(days=14)) if include_future else last_date_past
        else:
            start = dv["ScheduledDate"].min()
            end = dv["ScheduledDate"].max()

        # Filter departments + machine sub-filter for Lacey
        sites = departments if departments else DEPARTMENTS
        dv_machine_depts, tx_machine_depts, machine_active = _machine_dept_values(machines)

        # When viewing by machine, don't aggregate - show machine names directly
        if view_by == "machine":
            # Build list of departments as they appear in the data
            dept_list = []
            for site in sites:
                if site == "Lacey":
                    # Add Lacey machines (filtered by machine selector if active)
                    if machine_active:
                        dept_list.extend(dv_machine_depts)
                    else:
                        dept_list.extend(["TrueBeamNorth", "21EX"])
                elif site == "Centralia":
                    dept_list.append("Centralia")  # Data has "Centralia", not machine name
                elif site == "Aberdeen":
                    dept_list.append("Aberdeen")  # Data has "Aberdeen", not machine name

            # Filter data to selected departments
            dv = dv[dv["Department"].isin(dept_list)].copy()

            # Rename to machine names for display
            dv.loc[dv["Department"] == "Centralia", "Department"] = "21iX_CEN"
            dv.loc[dv["Department"] == "Aberdeen", "Department"] = "21iX_AB"

            if not tx.empty and "Department" in tx.columns:
                # Treatment data uses "Lacey - TrueBeamNorth" format for Lacey machines
                tx_machine_list = []
                for site in sites:
                    if site == "Lacey":
                        if machine_active:
                            tx_machine_list.extend([f"Lacey - {m}" for m in dv_machine_depts])
                        else:
                            tx_machine_list.extend(["Lacey - TrueBeamNorth", "Lacey - 21EX"])
                    elif site == "Centralia":
                        tx_machine_list.append("21iX_CEN")
                    elif site == "Aberdeen":
                        tx_machine_list.append("21iX_AB")
                tx = tx[tx["Department"].isin(tx_machine_list)]
        else:
            # View by location - aggregate machines to department level
            if machine_active and "Lacey" in sites:
                dv_eff = [s for s in sites if s != "Lacey"] + dv_machine_depts
                dv = dv[dv["Department"].isin(dv_eff)].copy()
                dv.loc[dv["Department"].isin(dv_machine_depts), "Department"] = "Lacey"
            else:
                dv = dv[dv["Department"].isin(sites)]

            # Apply machine filtering to treatment data as well
            if not tx.empty and "Department" in tx.columns:
                if machine_active and "Lacey" in sites:
                    tx_eff = [s for s in sites if s != "Lacey"] + tx_machine_depts
                    tx = tx[tx["Department"].isin(tx_eff)].copy()
                    tx.loc[tx["Department"].isin(tx_machine_depts), "Department"] = "Lacey"
                else:
                    tx_sites = [d for d in tx["Department"].unique() if d in sites]
                    tx = tx[tx["Department"].isin(tx_sites)]

        # Date filter
        dv = dv[(dv["ScheduledDate"] >= start) & (dv["ScheduledDate"] <= end)]

        if dv.empty:
            return []

        # Build row data
        rows = []
        for _, row in dv.iterrows():
            date_str = row["ScheduledDate"].strftime("%Y-%m-%d") if pd.notna(row["ScheduledDate"]) else ""
            dept = row.get("Department", "")
            appts_val = row.get("AppointmentCount", 0)
            appts = int(appts_val) if pd.notna(appts_val) else 0

            # Parse all 4 time fields separately
            sched_start = row.get("FirstScheduledStart", "")
            sched_end = row.get("LastScheduledEnd", "")
            actual_start = row.get("FirstActualStart", "")
            actual_end = row.get("LastActualEnd", "")

            # Calculate duration (prefer actual, fallback to scheduled for future dates)
            duration = None
            try:
                # Use actual times if available, otherwise use scheduled times
                start_time = actual_start if (actual_start and not pd.isna(actual_start)) else sched_start
                end_time = actual_end if (actual_end and not pd.isna(actual_end)) else sched_end

                # Only calculate if both times are valid
                if start_time and end_time and not pd.isna(start_time) and not pd.isna(end_time):
                    s_parts = str(start_time).split(":")
                    e_parts = str(end_time).split(":")
                    s_hr = int(s_parts[0]) + int(s_parts[1]) / 60
                    e_hr = int(e_parts[0]) + int(e_parts[1]) / 60
                    duration = round(e_hr - s_hr, 1)
            except Exception:
                pass

            # Format time strings, ensuring NaN/empty values show as blank
            def format_time(time_val):
                if pd.isna(time_val) or not time_val or str(time_val).strip() == "":
                    return None
                return str(time_val)[:5]

            # Minute columns from Daily Volume
            sched_active = row.get("ScheduledActiveMinutes", None)
            actual_active = row.get("ActualActiveMinutes", None)
            beam_on = row.get("BeamOnMinutes", None)
            appt_actual = row.get("ApptActualMinutes", None)

            def fmt_min(v):
                if pd.isna(v) or v is None:
                    return None
                return int(round(v))

            # Treatment data fields
            new_starts = 0
            completed = 0
            unique_pts = 0
            unique_plans = 0
            if not tx.empty and "ScheduledDate" in tx.columns and row["ScheduledDate"] <= today:
                tx_dept = dept
                if view_by == "machine":
                    if dept in ["TrueBeamNorth", "21EX"]:
                        tx_dept = f"Lacey - {dept}"
                tx_row = tx[(tx["ScheduledDate"] == row["ScheduledDate"]) & (tx["Department"] == tx_dept)]
                if not tx_row.empty:
                    completed = int(tx_row["CompletedAppointments"].sum()) if "CompletedAppointments" in tx_row.columns else 0
                    unique_pts = int(tx_row["UniquePatients"].sum()) if "UniquePatients" in tx_row.columns else 0
                    unique_plans = int(tx_row["UniquePlans"].sum()) if "UniquePlans" in tx_row.columns else 0
                    ns_col = next((c for c in tx_row.columns if "NewStarts" in c and "Course" in c), None)
                    if ns_col:
                        new_starts = int(tx_row[ns_col].sum())

            rows.append({
                "Date": date_str,
                "Location": dept,
                "Appts": appts,
                "Completed": completed or None,
                "Patients": unique_pts or None,
                "Plans": unique_plans or None,
                "New Starts": new_starts or None,
                "Sched Start": format_time(sched_start),
                "Sched End": format_time(sched_end),
                "Actual Start": format_time(actual_start),
                "Actual End": format_time(actual_end),
                "Dur (hrs)": duration,
                "Sched Min": fmt_min(sched_active),
                "Actual Min": fmt_min(actual_active),
                "Beam Min": fmt_min(beam_on),
                "Appt Min": fmt_min(appt_actual),
            })

        return sorted(rows, key=lambda x: x["Date"], reverse=True)

    except Exception:
        return []


# ---------------------------------------------------------------------------
# Chart Card Callbacks (settings toggle + PNG export)
# ---------------------------------------------------------------------------

register_chart_callbacks([("ops-volume", "ops-chart-volume", "ops-store-volume"), ("ops-efficiency", "ops-chart-efficiency")])


# ---------------------------------------------------------------------------
# Table CSV Export
# ---------------------------------------------------------------------------

clientside_callback(
    """function(n) {
        if (!n) return window.dash_clientside.no_update;
        gridExportCsv('ops-table', 'daily_detail.csv');
        return window.dash_clientside.no_update;
    }""",
    Output("ops-table-export", "n_clicks"),
    Input("ops-table-export", "n_clicks"),
    prevent_initial_call=True,
)
