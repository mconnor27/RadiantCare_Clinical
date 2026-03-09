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
    DEPARTMENTS, DEPARTMENT_COLORS, MACHINE_MAP, CHART_COLORWAY,
    PRIMARY, DEFAULT_LAYOUT, FONT_FAMILY,
)
from components.filter_bar import filter_bar, department_chips
from components.kpi_card import kpi_card
from components.chart_settings import chart_settings_popover
from utils.charts import apply_default_layout, empty_figure, dept_color

dash.register_page(__name__, path="/operations", name="Operations", order=1)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MACHINES = ["TrueBeamNorth", "21EX", "21iX_CEN", "21iX_AB"]


# ---------------------------------------------------------------------------
# Filter Bar Components
# ---------------------------------------------------------------------------

def _machine_select():
    """Machine multi-select dropdown."""
    return dmc.MultiSelect(
        id="operations-filter-machine",
        data=[{"value": m, "label": m} for m in MACHINES],
        placeholder="All Machines",
        clearable=True,
        size="sm",
        w=280,
    )


def _ops_filter_bar():
    """Operations page filter bar with department chips, machine select, and smoothing slider."""
    return dmc.Paper(
        children=[
            dmc.Group(
                children=[
                    department_chips("operations"),
                    _machine_select(),
                    dmc.Group(gap=8, align="center", children=[
                        dmc.Text("Smoothing", size="sm", c="#9CA3AF", fw=500),
                        dmc.Slider(
                            id="ops-filter-smoothing",
                            min=0, max=1, step=0.01, value=0.7,
                            size="xs", w=120,
                            showLabelOnHover=False,
                            updatemode="drag",
                        ),
                    ]),
                ],
                gap="lg",
                wrap="wrap",
            ),
        ],
        p="sm",
        px="md",
        radius="md",
        shadow="xs",
        withBorder=True,
    )


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
                dmc.Title("Operations", order=2, className="page-title"),
                _ops_filter_bar(),
            ],
        ),

        # Hidden dummy inputs for filter bar IDs required by other pages/callbacks
        dcc.Store(id="operations-filter-daterange", data=None),
        dcc.Store(id="operations-filter-physician", data=None),
        dcc.Store(id="operations-filter-date-preset", data=None),

        # KPI row — 6 cards: Today, Lacey Hours, Centralia Hours, Aberdeen Hours, Avg Volume, New Starts
        dmc.Grid(
            id="ops-kpi-row",
            gutter=16,
            children=[
                dmc.GridCol(id="ops-kpi-today", span={"base": 6, "sm": 4, "md": 2}),
                dmc.GridCol(id="ops-kpi-hours-lacey", span={"base": 6, "sm": 4, "md": 2}),
                dmc.GridCol(id="ops-kpi-hours-centralia", span={"base": 6, "sm": 4, "md": 2}),
                dmc.GridCol(id="ops-kpi-hours-aberdeen", span={"base": 6, "sm": 4, "md": 2}),
                dmc.GridCol(id="ops-kpi-lead-times", span={"base": 6, "sm": 4, "md": 2}),
                dmc.GridCol(id="ops-kpi-new-starts", span={"base": 6, "sm": 4, "md": 2}),
            ],
        ),

        # Charts row: Treatment Appointments (half) + Upcoming Heatmap (half)
        dmc.Grid(
            gutter=16,
            children=[
                # Treatment Appointments (completed)
                dmc.GridCol(
                    span={"base": 12, "md": 6},
                    children=dmc.Paper(
                        children=[
                            dmc.Group(
                                justify="space-between", mb="sm",
                                children=[
                                    dmc.Text("Treatments", size="sm", fw=500, c="#6B7280"),
                                    dmc.Group(gap="xs", align="center", children=[
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
                                        chart_settings_popover(
                                            "ops-volume",
                                            chart_types=[
                                                {"value": "area", "label": "Area"},
                                                {"value": "line", "label": "Line"},
                                                {"value": "bar", "label": "Bar"},
                                            ],
                                            show_smooth=True,
                                            smooth_max=30,
                                            smooth_default=7,
                                        ),
                                    ]),
                                ],
                            ),
                            dmc.Box(
                                pos="relative",
                                children=[
                                    dmc.LoadingOverlay(
                                        id="ops-volume-loading",
                                        visible=False,
                                        loaderProps={"type": "dots", "color": "#7C2A83"},
                                        overlayProps={"radius": "sm", "blur": 2},
                                    ),
                                    dcc.Graph(
                                        id="ops-chart-volume",
                                        config={
                                            "displayModeBar": False,
                                            "scrollZoom": False,
                                            "doubleClick": "reset",
                                        },
                                        style={"height": "380px"}
                                    ),
                                ],
                            ),
                        ],
                        p="sm", radius="md", shadow="xs", withBorder=True, h="466px",
                    ),
                ),
                # Upcoming 2 Weeks Heatmap
                dmc.GridCol(
                    span={"base": 12, "md": 6},
                    children=dmc.Paper(
                        children=[
                            dmc.Group(
                                justify="space-between", mb="sm",
                                children=[
                                    dmc.Text("Upcoming 2 Weeks — Schedule & Availability", size="sm", fw=500, c="#6B7280"),
                                ],
                            ),
                            dmc.Box(
                                pos="relative",
                                children=[
                                    dmc.LoadingOverlay(
                                        id="ops-heatmap-loading",
                                        visible=False,
                                        loaderProps={"type": "dots", "color": "#7C2A83"},
                                        overlayProps={"radius": "sm", "blur": 2},
                                    ),
                                    dcc.Graph(
                                        id="ops-chart-heatmap",
                                        config={"displayModeBar": False},
                                        style={"height": "380px"}
                                    ),
                                ],
                            ),
                        ],
                        p="sm", radius="md", shadow="xs", withBorder=True, h="466px",
                    ),
                ),
            ],
        ),

        # Operating Hours Ribbon (full-width)
        dmc.Paper(
            children=[
                dmc.Group(
                    justify="space-between", mb="sm",
                    children=[
                        dmc.Group(gap="sm", align="center", children=[
                            dmc.Text("Operating Hours by Site", size="sm", fw=500, c="#6B7280"),
                            dmc.SegmentedControl(
                                id="ops-ribbon-site",
                                data=[
                                    {"value": "all", "label": "All"},
                                    {"value": "Lacey", "label": "Lacey"},
                                    {"value": "Centralia", "label": "Centralia"},
                                    {"value": "Aberdeen", "label": "Aberdeen"},
                                ],
                                value="all",
                                size="xs",
                            ),
                        ]),
                        dmc.Group(gap="xs", align="center", children=[
                            dmc.SegmentedControl(
                                id="ops-ribbon-range",
                                data=[
                                    {"value": "thisweek", "label": "This Week"},
                                    {"value": "30", "label": "30d"},
                                    {"value": "60", "label": "60d"},
                                    {"value": "90", "label": "90d"},
                                    {"value": "180", "label": "6mo"},
                                    {"value": "365", "label": "1y"},
                                    {"value": "0", "label": "All"},
                                ],
                                value="thisweek",
                                size="xs",
                            ),
                            chart_settings_popover(
                                "ops-ribbon",
                                chart_types=[
                                    {"value": "ribbon", "label": "Ribbon"},
                                    {"value": "line", "label": "Line"},
                                    {"value": "bar", "label": "Bar"},
                                ],
                                show_smooth=True,
                                smooth_max=14,
                                smooth_default=0,
                            ),
                        ]),
                    ],
                ),
                dmc.Box(
                    pos="relative",
                    children=[
                        dmc.LoadingOverlay(
                            id="ops-ribbon-loading",
                            visible=False,
                            loaderProps={"type": "dots", "color": "#7C2A83"},
                            overlayProps={"radius": "sm", "blur": 2},
                        ),
                        dcc.Graph(
                            id="ops-chart-ribbon",
                            config={
                                "displayModeBar": False,
                                "scrollZoom": False,
                                "doubleClick": "reset",
                            }
                        ),
                    ],
                ),
            ],
            p="md", radius="md", shadow="xs", withBorder=True,
        ),

        # Resource Utilization Chart (full-width)
        dmc.Paper(
            children=[
                dmc.Group(
                    justify="space-between", mb="sm",
                    children=[
                        dmc.Group(gap="sm", align="center", children=[
                            dmc.Text("Resource Utilization", size="sm", fw=500, c="#6B7280"),
                            dmc.SegmentedControl(
                                id="ops-efficiency-agg",
                                data=[
                                    {"value": "D", "label": "Daily"},
                                    {"value": "W", "label": "Weekly"},
                                    {"value": "M", "label": "Monthly"},
                                ],
                                value="D",
                                size="xs",
                            ),
                        ]),
                        dmc.Group(gap="xs", align="center", children=[
                            dmc.SegmentedControl(
                                id="ops-efficiency-range",
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
                            chart_settings_popover(
                                "ops-efficiency",
                                chart_types=[
                                    {"value": "line", "label": "Line"},
                                    {"value": "area", "label": "Area"},
                                    {"value": "bar", "label": "Bar"},
                                ],
                                show_smooth=True,
                                smooth_max=30,
                                smooth_default=7,
                            ),
                        ]),
                    ],
                ),
                dmc.Box(
                    pos="relative",
                    children=[
                        dmc.LoadingOverlay(
                            id="ops-efficiency-loading",
                            visible=False,
                            loaderProps={"type": "dots", "color": "#7C2A83"},
                            overlayProps={"radius": "sm", "blur": 2},
                        ),
                        dcc.Graph(
                            id="ops-chart-efficiency",
                            config={
                                "displayModeBar": False,
                                "scrollZoom": False,
                                "doubleClick": "reset",
                            },
                            style={"height": "380px"},
                        ),
                    ],
                ),
            ],
            p="md", radius="md", shadow="xs", withBorder=True,
        ),

        # Daily Detail Table (full-width)
        dmc.Paper(
            children=[
                dmc.Group(
                    justify="space-between", mb="sm", wrap="wrap", gap="sm",
                    children=[
                        dmc.Text("Daily Detail", size="sm", fw=500, c="#6B7280"),
                        dmc.Group(gap="md", align="center", children=[
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
                            dmc.Button(
                                "Export CSV",
                                id="ops-table-export",
                                size="compact-xs",
                                variant="light",
                                leftSection=dmc.Text("↓", size="xs"),
                            ),
                        ]),
                    ],
                ),
                dag.AgGrid(
                    id="ops-table",
                    columnDefs=[],  # Will be set by callback
                    defaultColDef={"resizable": True, "sortable": True, "filter": True},
                    dashGridOptions={"pagination": True, "paginationPageSize": 50},
                    style={"height": 800},
                    className="ag-theme-quartz",
                ),
            ],
            p="md", radius="md", shadow="xs", withBorder=True,
        ),

        # Interval for periodic refresh
        dcc.Interval(id="ops-interval", interval=300_000, n_intervals=0),

        # Stores for clientside rendering
        dcc.Store(id="ops-store-volume"),
        dcc.Store(id="ops-store-ribbon"),
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

        # Date filter
        dv = dv[(dv["ScheduledDate"] >= start) & (dv["ScheduledDate"] <= end)]
        if dv.empty:
            return None

        # Period aggregation
        dv["period"] = dv["ScheduledDate"].dt.to_period(agg).dt.to_timestamp()
        if agg == "D":
            dv = dv[dv["ScheduledDate"].dt.weekday < 5]

        # Sum minutes per period per resource, then compute ratio
        grouped = dv.groupby(["period", "Resource"]).agg(
            actual=("ActualActiveMinutes", "sum"),
            scheduled=("ScheduledActiveMinutes", "sum"),
        ).reset_index()
        grouped["utilization"] = np.where(
            grouped["scheduled"] > 0,
            (grouped["actual"] / grouped["scheduled"]) * 100,
            np.nan,
        )
        # Cap at 150% — anything higher is bad data (e.g. ActualActiveMinutes = 230k)
        grouped["utilization"] = grouped["utilization"].clip(upper=150)

        all_periods = sorted(grouped["period"].unique())
        date_range = [d.isoformat() for d in all_periods]

        # Build series for each resource that has meaningful data
        series = []
        for resource in all_resources:
            res_data = grouped[grouped["Resource"] == resource].set_index("period")["utilization"]
            non_null = res_data.dropna()
            if non_null.empty or len(non_null) < 5:
                continue  # Skip resources with too little data (e.g. CT_CEN, 6EX)
            res_data = res_data.reindex(all_periods, fill_value=0)
            series.append({
                "name": resource,
                "values": [round(v, 1) if pd.notna(v) and v > 0 else 0 for v in res_data.tolist()],
                "color": _RESOURCE_COLORS.get(resource, CHART_COLORWAY[0]),
            })

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
    """Prepare treatment volume data for clientside rendering."""
    from data.loader import load_daily_volume

    try:
        dv = load_daily_volume()

        # Filter to departments with machine sub-filter for Lacey
        sites = departments if departments else DEPARTMENTS
        dv_machine_depts, _, machine_active = _machine_dept_values(machines)
        if machine_active and "Lacey" in sites:
            dv_eff = [s for s in sites if s != "Lacey"] + dv_machine_depts
            dv = dv[dv["Department"].isin(dv_eff)].copy()
            dv.loc[dv["Department"].isin(dv_machine_depts), "Department"] = "Lacey"
        else:
            dv = dv[dv["Department"].isin(sites)]

        # Date filter
        dv = dv[(dv["ScheduledDate"] >= start) & (dv["ScheduledDate"] <= end)]

        if dv.empty:
            return None

        # Aggregate by period
        dv = dv.copy()
        dv["period"] = dv["ScheduledDate"].dt.to_period(agg).dt.to_timestamp()

        # Filter out weekends for daily view
        if agg == "D":
            dv = dv[dv["ScheduledDate"].dt.weekday < 5]

        # Aggregate and build series
        count_col = "AppointmentCount" if "AppointmentCount" in dv.columns else dv.select_dtypes(include='number').columns[0]
        grouped = dv.groupby(["period", "Department"])[count_col].sum().reset_index()

        # Get all unique periods
        all_periods = sorted(grouped["period"].unique())
        date_range = [d.isoformat() for d in all_periods]

        series = []
        for site in sites:
            site_data = grouped[grouped["Department"] == site].set_index("period")[count_col]
            site_data = site_data.reindex(all_periods, fill_value=0)
            series.append({
                "name": site,
                "values": site_data.tolist(),
                "color": dept_color(site),
            })

        return {
            "chartId": "ops-chart-volume",
            "dates": date_range,
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
    Output("ops-kpi-lead-times", "children"),
    Output("ops-kpi-new-starts", "children"),
    Output("ops-store-kpi-sparklines", "data"),
    Input("ops-interval", "n_intervals"),
    Input("operations-filter-department", "value"),
    Input("operations-filter-machine", "value"),
)
def update_kpis(_n, departments, machines):
    """Compute all 6 KPI cards with fixed 30-day sparklines."""
    from data.loader import load_daily_volume, load_treatment, load_clinic_visits, load_simulations

    sparkline_data = {}

    try:
        dv = load_daily_volume()
        tx = load_treatment()
    except Exception:
        dv = pd.DataFrame()
        tx = pd.DataFrame()

    # Filter departments + machine sub-filter for Lacey
    sites = departments if departments else DEPARTMENTS
    dv_machine_depts, tx_machine_depts, machine_active = _machine_dept_values(machines)

    if not dv.empty and "Department" in dv.columns:
        if machine_active and "Lacey" in sites:
            dv_eff = [s for s in sites if s != "Lacey"] + dv_machine_depts
            dv_filtered = dv[dv["Department"].isin(dv_eff)].copy()
            dv_filtered.loc[dv_filtered["Department"].isin(dv_machine_depts), "Department"] = "Lacey"
        else:
            dv_filtered = dv[dv["Department"].isin(sites)]
    else:
        dv_filtered = dv

    if not tx.empty and "Department" in tx.columns:
        if machine_active and "Lacey" in sites:
            tx_eff = [s for s in sites if s != "Lacey"] + tx_machine_depts
            tx_filtered = tx[tx["Department"].isin(tx_eff)].copy()
            tx_filtered.loc[tx_filtered["Department"].isin(tx_machine_depts), "Department"] = "Lacey"
        else:
            tx_sites = [d for d in tx["Department"].unique() if d in sites]
            tx_filtered = tx[tx["Department"].isin(tx_sites)]
    else:
        tx_filtered = tx

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

    # ── 5. Scheduling Lead Times (consult + sim) ────────────────────
    try:
        cv = load_clinic_visits()
        sims_data = load_simulations()
    except Exception:
        cv = pd.DataFrame()
        sims_data = pd.DataFrame()

    # Filter consults by department; sims always in Lacey so leave unfiltered
    if departments:
        if not cv.empty and "Department" in cv.columns:
            cv = cv[cv["Department"].isin(sites)]

    def _calc_lead(df, date_col="ScheduledDateTime"):
        """Compute lead_days column and return filtered df."""
        if df.empty or date_col not in df.columns or "AppointmentCreatedDate" not in df.columns:
            return pd.DataFrame()
        out = df[df["AppointmentCreatedDate"].notna()].copy()
        if out.empty:
            return out
        out["lead_days"] = (out[date_col] - out["AppointmentCreatedDate"]).dt.days
        return out[out["lead_days"] >= 0]

    cv_lead = _calc_lead(cv)
    sim_lead = _calc_lead(sims_data)

    # Value: median lead time for FUTURE-scheduled appointments (snapshot)
    future_cv = cv_lead[cv_lead["ScheduledDateTime"] > actual_today] if not cv_lead.empty else pd.DataFrame()
    future_sim = sim_lead[sim_lead["ScheduledDateTime"] > actual_today] if not sim_lead.empty else pd.DataFrame()

    c_med = future_cv["lead_days"].median() if not future_cv.empty else None
    s_med = future_sim["lead_days"].median() if not future_sim.empty else None

    c_str = f"C:{c_med:.0f}d" if c_med is not None else "C:--"
    s_str = f"S:{s_med:.0f}d" if s_med is not None else "S:--"
    lead_value = f"{c_str}  {s_str}"

    # Trend: past 30d consult lead median vs prior 30d median
    lead_trend_text = None
    lead_trend_dir = None
    cv_ref = cv_lead["ScheduledDateTime"].dt.normalize().max() if not cv_lead.empty else actual_today
    if not cv_lead.empty:
        curr_30d = cv_lead[
            (cv_lead["ScheduledDateTime"] >= cv_ref - timedelta(days=29)) &
            (cv_lead["ScheduledDateTime"] <= cv_ref)
        ]
        prior_30d = cv_lead[
            (cv_lead["ScheduledDateTime"] >= cv_ref - timedelta(days=59)) &
            (cv_lead["ScheduledDateTime"] <= cv_ref - timedelta(days=30))
        ]
        curr_med = curr_30d["lead_days"].median() if not curr_30d.empty else None
        prior_med = prior_30d["lead_days"].median() if not prior_30d.empty else None
        pt, td, _ = _trend(curr_med, prior_med, invert=True)
        if pt:
            lead_trend_text = f"{pt} vs prior 30d"
            lead_trend_dir = td

    # Sparkline: daily consult lead median over past 30 days
    if not cv_lead.empty:
        sp_start = cv_ref - timedelta(days=30)
        cl_spark = cv_lead[
            (cv_lead["ScheduledDateTime"] >= sp_start) &
            (cv_lead["ScheduledDateTime"] <= cv_ref)
        ]
        if not cl_spark.empty:
            daily_lead = cl_spark.groupby(
                cl_spark["ScheduledDateTime"].dt.normalize()
            )["lead_days"].median().sort_index()
            if not daily_lead.empty:
                sparkline_data["lead"] = {
                    "labels": [d.isoformat() for d in daily_lead.index],
                    "values": [round(v, 1) for v in daily_lead.tolist()],
                    "color": CHART_COLORWAY[1],
                    "hover_fmt": "%{x|%b %d}: %{y:.0f}d<extra></extra>",
                }

    kpi_lead = kpi_card(
        "Scheduling Lead", lead_value,
        value_detail="future scheduled",
        trend_text=lead_trend_text,
        trend_direction=lead_trend_dir,
        accent_color=CHART_COLORWAY[1],
        sparkline_id="ops-spark-lead",
    )

    # ── 6. New Starts (7d rolling, 30d sparkline) ────────────────────
    ns_col = None
    if not tx_filtered.empty and "ScheduledDate" in tx_filtered.columns:
        ns_col = next((c for c in tx_filtered.columns if "NewStarts" in c and "Course" in c), None)

    if ns_col and not tx_filtered.empty:
        tx_last = tx_filtered["ScheduledDate"].max()

        # Value: rolling 7-day total
        ns_start = tx_last - timedelta(days=6)
        tx_7d = tx_filtered[
            (tx_filtered["ScheduledDate"] >= ns_start) &
            (tx_filtered["ScheduledDate"] <= tx_last)
        ]
        total_starts = int(tx_7d[ns_col].sum())

        # Per-site breakdown
        site_breakdown = []
        for site in DEPARTMENTS:
            if site not in sites:
                continue
            site_tx = tx_7d[tx_7d["Department"] == site]
            site_ns = int(site_tx[ns_col].sum()) if not site_tx.empty else 0
            site_breakdown.append(f"{site[0]}:{site_ns}")
        ns_detail = "  ".join(site_breakdown) if site_breakdown else None

        # Trend: 7d vs prior 7d
        prior_7d_start = tx_last - timedelta(days=13)
        prior_7d_end = tx_last - timedelta(days=7)
        tx_prior_7d = tx_filtered[
            (tx_filtered["ScheduledDate"] >= prior_7d_start) &
            (tx_filtered["ScheduledDate"] <= prior_7d_end)
        ]
        prior_starts = int(tx_prior_7d[ns_col].sum()) if not tx_prior_7d.empty else None
        ns_trend_text = None
        ns_trend_dir = None
        pt, td, _ = _trend(total_starts, prior_starts)
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
            "New Starts (7d)", str(total_starts),
            value_detail=ns_detail,
            trend_text=ns_trend_text,
            trend_direction=ns_trend_dir,
            accent_color=CHART_COLORWAY[4],
            sparkline_id="ops-spark-newstarts",
        )
    else:
        kpi_new = kpi_card("New Starts", "N/A")

    return (
        kpi_today,
        site_hours_cards.get("Lacey", kpi_card("Lacey Hours", "N/A")),
        site_hours_cards.get("Centralia", kpi_card("Centralia Hours", "N/A")),
        site_hours_cards.get("Aberdeen", kpi_card("Aberdeen Hours", "N/A")),
        kpi_lead,
        kpi_new,
        sparkline_data,
    )


# ---------------------------------------------------------------------------
# Clientside callbacks for KPI sparklines (with smoothing)
# ---------------------------------------------------------------------------

# Today's Treatments sparkline
clientside_callback(
    ClientsideFunction(namespace="sparklines", function_name="smoothOpsToday"),
    Output("ops-spark-today", "figure"),
    Input("ops-store-kpi-sparklines", "data"),
    Input("ops-filter-smoothing", "value"),
)

# Site hours sparklines (duration in hours)
clientside_callback(
    ClientsideFunction(namespace="sparklines", function_name="smoothOpsHoursLacey"),
    Output("ops-spark-hours-lacey", "figure"),
    Input("ops-store-kpi-sparklines", "data"),
    Input("ops-filter-smoothing", "value"),
)

clientside_callback(
    ClientsideFunction(namespace="sparklines", function_name="smoothOpsHoursCentralia"),
    Output("ops-spark-hours-centralia", "figure"),
    Input("ops-store-kpi-sparklines", "data"),
    Input("ops-filter-smoothing", "value"),
)

clientside_callback(
    ClientsideFunction(namespace="sparklines", function_name="smoothOpsHoursAberdeen"),
    Output("ops-spark-hours-aberdeen", "figure"),
    Input("ops-store-kpi-sparklines", "data"),
    Input("ops-filter-smoothing", "value"),
)

# Scheduling Lead sparkline (consult lead daily median)
clientside_callback(
    ClientsideFunction(namespace="sparklines", function_name="smoothOpsLead"),
    Output("ops-spark-lead", "figure"),
    Input("ops-store-kpi-sparklines", "data"),
    Input("ops-filter-smoothing", "value"),
)

# New Starts sparkline (daily)
clientside_callback(
    ClientsideFunction(namespace="sparklines", function_name="smoothOpsNewStarts"),
    Output("ops-spark-newstarts", "figure"),
    Input("ops-store-kpi-sparklines", "data"),
    Input("ops-filter-smoothing", "value"),
)


# ---------------------------------------------------------------------------
# Volume Chart Callback — outputs raw data to store
# ---------------------------------------------------------------------------

@callback(
    Output("ops-store-volume", "data"),
    Input("ops-interval", "n_intervals"),
    Input("ops-volume-agg", "value"),
    Input("operations-filter-department", "value"),
    Input("operations-filter-machine", "value"),
    running=[(Output("ops-volume-loading", "visible"), True, False)],
)
def update_volume_data(_n, agg, departments, machines):
    """Load ALL treatment volume data to store (time window applied clientside)."""
    from data.loader import load_daily_volume

    try:
        dv = load_daily_volume()
        if dv.empty:
            return None

        # Always load all data - time window will be applied clientside for initial view
        start = dv["ScheduledDate"].min()
        last_date = dv["ScheduledDate"].max()
        result = _prepare_volume_data(departments, machines, agg, start, last_date)

        # Debug logging
        return result
    except Exception:
        return None


# Clientside callback for volume chart smoothing with chart type and time window
clientside_callback(
    ClientsideFunction(namespace="census", function_name="smoothChartWithTypeAndRange"),
    Output("ops-chart-volume", "figure"),
    Input("ops-store-volume", "data"),
    Input("ops-volume-settings-smooth", "value"),
    Input("ops-volume-settings-type", "value"),
    Input("ops-volume-range", "value"),
    State("ops-chart-volume", "figure"),
)


# Dynamically adjust smoothing slider range based on selected time window
# ~1/3 of visible weekday data points gives useful max without over-smoothing
_SMOOTH_MAX_JS = """
function(rangeDays, currentVal) {
    var map = {'thisweek': 3, '30': 7, '60': 15, '90': 22, '180': 40, '365': 50, '0': 50};
    var newMax = map[rangeDays] || 50;
    var clamped = Math.min(currentVal || 0, newMax);
    return [newMax, clamped];
}
"""

clientside_callback(
    _SMOOTH_MAX_JS,
    Output("ops-volume-settings-smooth", "max"),
    Output("ops-volume-settings-smooth", "value"),
    Input("ops-volume-range", "value"),
    State("ops-volume-settings-smooth", "value"),
)

clientside_callback(
    _SMOOTH_MAX_JS,
    Output("ops-ribbon-settings-smooth", "max"),
    Output("ops-ribbon-settings-smooth", "value"),
    Input("ops-ribbon-range", "value"),
    State("ops-ribbon-settings-smooth", "value"),
)


# ---------------------------------------------------------------------------
# Heatmap Callback — combines future schedule + availability
# ---------------------------------------------------------------------------

@callback(
    Output("ops-chart-heatmap", "figure"),
    Input("ops-interval", "n_intervals"),
    Input("operations-filter-department", "value"),
    Input("operations-filter-machine", "value"),
    running=[(Output("ops-heatmap-loading", "visible"), True, False)],
)
def update_heatmap(_n, departments, machines):
    """Build combined heatmap of treatment schedule + exam/sim availability."""
    from data.loader import load_daily_volume_future, load_availability

    try:
        dv = load_daily_volume_future()
        avail = load_availability()

        today = pd.Timestamp.now().normalize()
        two_weeks = today + timedelta(days=14)

        # Filter future volume
        dv = dv[(dv["ScheduledDate"] >= today) & (dv["ScheduledDate"] <= two_weeks)]
        sites = departments if departments else DEPARTMENTS

        # Derive machines from selected departments (heatmap ignores machine filter)
        machines_to_show = []
        for s in sites:
            machines_to_show.extend(MACHINE_MAP.get(s, []))
        if not machines_to_show:
            machines_to_show = MACHINES

        # Include both site-level and machine-level Department values
        dept_filter = list(sites)
        for s in sites:
            dept_filter.extend(MACHINE_MAP.get(s, []))
        dv = dv[dv["Department"].isin(dept_filter)]

        exam_labels = [f"{site} Exam" for site in sites]
        n_machines = len(machines_to_show)
        n_exams = len(exam_labels)
        n_sim = 1

        # Generate date range (next 14 calendar days, weekdays only)
        date_range = pd.date_range(today, two_weeks, freq="D")
        date_range = date_range[date_range.weekday < 5]
        x_date_labels = [f"{d.month}/{d.day}" for d in date_range]
        x_day_labels = [d.strftime('%a') for d in date_range]
        x_hover_labels = [f"{d.strftime('%a')} {d.month}/{d.day}" for d in date_range]

        # Initialize per-group matrices
        z_machines = np.zeros((n_machines, len(date_range)))
        z_exams = np.zeros((n_exams, len(date_range)))
        z_sim = np.zeros((n_sim, len(date_range)))

        # Fill treatment rows — machines
        if not dv.empty and "AppointmentCount" in dv.columns:
            for i, machine in enumerate(machines_to_show):
                machine_data = dv[dv["Department"].str.contains(machine.replace("_", "|"), case=False, na=False)]
                if machine_data.empty and machine in ["TrueBeamNorth", "21EX"]:
                    machine_data = dv[dv["Department"] == "Lacey"]
                elif machine_data.empty and machine == "21iX_CEN":
                    machine_data = dv[dv["Department"] == "Centralia"]
                elif machine_data.empty and machine == "21iX_AB":
                    machine_data = dv[dv["Department"] == "Aberdeen"]

                for j, date in enumerate(date_range):
                    day_data = machine_data[machine_data["ScheduledDate"] == date]
                    z_machines[i, j] = int(day_data["AppointmentCount"].sum()) if not day_data.empty else 0

        # Fill exam availability rows by department
        if not avail.empty and "SlotDate" in avail.columns and "Category" in avail.columns:
            avail_filtered = avail[(avail["SlotDate"] >= today) & (avail["SlotDate"] <= two_weeks)]
            exam_data = avail_filtered[avail_filtered["Category"].str.contains("Exam", case=False, na=False)]
            for dept_i, dept in enumerate(sites):
                dept_exam = exam_data
                if "Department" in exam_data.columns:
                    dept_exam = exam_data[exam_data["Department"] == dept]
                for j, date in enumerate(date_range):
                    z_exams[dept_i, j] = len(dept_exam[dept_exam["SlotDate"] == date])

            # Fill simulation row
            sim_data = avail_filtered[avail_filtered["Category"].str.contains("Simulation", case=False, na=False)]
            for j, date in enumerate(date_range):
                z_sim[0, j] = len(sim_data[sim_data["SlotDate"] == date])

        # Build faceted figure: 3 subplot rows with true vertical gaps
        fig = make_subplots(
            rows=3, cols=1,
            shared_xaxes=True,
            vertical_spacing=0.06,
            row_heights=[n_machines, max(n_exams, 1), n_sim],
        )

        colorscale = [[0, "#F3E8F5"], [1, "#7C2A83"]]
        # Shared zmin/zmax for consistent color mapping across all groups
        z_all = np.concatenate([z_machines.ravel(), z_exams.ravel(), z_sim.ravel()])
        zmax = float(z_all.max()) if len(z_all) and z_all.max() > 0 else 1

        for group_i, (z, labels) in enumerate([
            (z_machines, machines_to_show),
            (z_exams, exam_labels),
            (z_sim, ["Simulation"]),
        ], start=1):
            text_arr = np.where(np.isnan(z), "", z.astype(int).astype(str))
            # customdata: repeat hover labels for each row in this group
            hover_cd = np.tile(x_hover_labels, (len(labels), 1))
            fig.add_trace(go.Heatmap(
                z=z,
                x=x_date_labels,
                y=labels,
                customdata=hover_cd,
                colorscale=colorscale,
                zmin=0,
                zmax=zmax,
                text=text_arr,
                texttemplate="%{text}",
                textfont={"size": 10},
                hovertemplate="<b>%{y}</b><br>%{customdata}: %{z:.0f}<extra></extra>",
                showscale=False,
                connectgaps=False,
            ), row=group_i, col=1)

        # Day-of-week annotations below the bottom subplot
        annotations = []
        num_cols = len(x_day_labels)
        for i, day_label in enumerate(x_day_labels):
            x_pos = (i + 0.5) / num_cols
            annotations.append(dict(
                x=x_pos,
                y=-0.01,
                text=day_label,
                xref="x domain",
                yref="paper",
                showarrow=False,
                font=dict(size=10, color="#6B7280"),
                xanchor="center",
                yanchor="top",
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

        # 1px black border around each subplot group
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
            font=dict(family=FONT_FAMILY, size=11),
            plot_bgcolor="#FFFFFF",
            paper_bgcolor="#FFFFFF",
            margin=dict(l=90, r=16, t=32, b=20),
            annotations=annotations,
            shapes=shapes,
        )

        # Style each subplot's axes
        fig.update_xaxes(side="top", tickangle=0, tickfont=dict(size=10), row=1, col=1)
        for row_i in range(1, 4):
            fig.update_yaxes(
                autorange="reversed",
                tickfont=dict(size=10),
                row=row_i, col=1,
            )
            # Hide x-axis ticks/labels on lower subplots (shared)
            if row_i > 1:
                fig.update_xaxes(showticklabels=False, row=row_i, col=1)

        return fig

    except Exception:
        return empty_figure("Unable to load schedule data")


# ---------------------------------------------------------------------------
# Ribbon Chart Callback — outputs raw data to store
# ---------------------------------------------------------------------------

@callback(
    Output("ops-store-ribbon", "data"),
    Input("ops-interval", "n_intervals"),
    Input("ops-ribbon-site", "value"),
    Input("ops-ribbon-range", "value"),
    Input("operations-filter-department", "value"),
    Input("operations-filter-machine", "value"),
    running=[(Output("ops-ribbon-loading", "visible"), True, False)],
)
def update_ribbon_data(_n, site_filter, range_val, departments, machines):
    """Load operating hours data to store - always daily granularity."""
    # Use chart's own site selector
    if site_filter and site_filter != "all":
        sites = [site_filter]
    else:
        sites = departments if departments else None

    # Always use daily data (no weekly aggregation)
    return _prepare_hours_data(sites, machines, days_back=0, aggregate_weekly=False)


# Clientside callback for ribbon chart smoothing with chart type and time window
clientside_callback(
    ClientsideFunction(namespace="hoursRibbon", function_name="smoothChartWithTypeAndRange"),
    Output("ops-chart-ribbon", "figure"),
    Input("ops-store-ribbon", "data"),
    Input("ops-ribbon-settings-smooth", "value"),
    Input("ops-ribbon-settings-type", "value"),
    Input("ops-ribbon-range", "value"),
)

# Clientside callback for dynamic y-axis scaling on pan
clientside_callback(
    ClientsideFunction(namespace="ribbonYAxis", function_name="updateYAxisOnPan"),
    Output("ops-chart-ribbon", "figure", allow_duplicate=True),
    Input("ops-chart-ribbon", "relayoutData"),
    State("ops-chart-ribbon", "figure"),
    prevent_initial_call=True,
)

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
    Input("ops-interval", "n_intervals"),
    Input("ops-efficiency-agg", "value"),
    Input("operations-filter-department", "value"),
    Input("operations-filter-machine", "value"),
    running=[(Output("ops-efficiency-loading", "visible"), True, False)],
)
def update_efficiency_data(_n, agg, departments, machines):
    """Load resource utilization data to store (time window applied clientside)."""
    from data.loader import load_daily_volume_by_resource

    try:
        dv = load_daily_volume_by_resource()
        if dv.empty:
            return None
        start = dv["ScheduledDate"].min()
        last_date = dv["ScheduledDate"].max()
        return _prepare_efficiency_data(departments, machines, agg, start, last_date)
    except Exception:
        return None


# Clientside callback for efficiency chart smoothing with chart type and time window
clientside_callback(
    ClientsideFunction(namespace="census", function_name="smoothChartWithTypeAndRange"),
    Output("ops-chart-efficiency", "figure"),
    Input("ops-store-efficiency", "data"),
    Input("ops-efficiency-settings-smooth", "value"),
    Input("ops-efficiency-settings-type", "value"),
    Input("ops-efficiency-range", "value"),
    State("ops-chart-efficiency", "figure"),
)

# Dynamically adjust smoothing slider range for efficiency chart
clientside_callback(
    _SMOOTH_MAX_JS,
    Output("ops-efficiency-settings-smooth", "max"),
    Output("ops-efficiency-settings-smooth", "value"),
    Input("ops-efficiency-range", "value"),
    State("ops-efficiency-settings-smooth", "value"),
)


# ---------------------------------------------------------------------------
# Efficiency Settings Panel Toggle
# ---------------------------------------------------------------------------

@callback(
    Output("ops-efficiency-settings-panel", "style"),
    Input("ops-efficiency-settings-btn", "n_clicks"),
    State("ops-efficiency-settings-panel", "style"),
    prevent_initial_call=True,
)
def toggle_efficiency_settings(n, style):
    if not n:
        return style
    current = style or {}
    is_hidden = current.get("display") == "none"
    return {"display": "block"} if is_hidden else {"display": "none"}


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
        {"field": "Date", "sortable": True, "filter": True, "width": 140},
        {"field": "Location", "headerName": location_header, "sortable": True, "filter": True, "width": 160},
        {"field": "Appointments", "sortable": True, "filter": True, "width": 160, "type": "numericColumn"},
        {"field": "Scheduled Start", "sortable": True, "filter": True, "width": 165},
        {"field": "Scheduled End", "sortable": True, "filter": True, "width": 160},
        {"field": "Actual Start", "sortable": True, "filter": True, "width": 145},
        {"field": "Actual End", "sortable": True, "filter": True, "width": 135},
        {"field": "Duration (hrs)", "sortable": True, "filter": True, "width": 150, "type": "numericColumn"},
        {"field": "New Starts", "sortable": True, "filter": True, "width": 130, "type": "numericColumn"},
    ]


# ---------------------------------------------------------------------------
# Daily Detail Table Data Callback
# ---------------------------------------------------------------------------

@callback(
    Output("ops-table", "rowData"),
    Input("ops-interval", "n_intervals"),
    Input("ops-volume-range", "value"),
    Input("operations-filter-department", "value"),
    Input("operations-filter-machine", "value"),
    Input("ops-table-include-future", "checked"),
    Input("ops-table-view-by", "value"),
)
def update_table(_n, range_days, departments, machines, include_future, view_by):
    """Build daily detail table data with optional future data and machine-level detail."""
    from data.loader import load_daily_volume, load_daily_volume_future, load_treatment

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
            duration = ""
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

            # Get new starts from treatment data (only for past dates)
            new_starts = 0
            if not tx.empty and "ScheduledDate" in tx.columns and row["ScheduledDate"] <= today:
                # Match department/machine name format in treatment data
                tx_dept = dept
                if view_by == "machine":
                    # Treatment data uses "Lacey - MachineName" for Lacey machines
                    if dept in ["TrueBeamNorth", "21EX"]:
                        tx_dept = f"Lacey - {dept}"
                    # Treatment data uses machine names directly for other sites
                    elif dept in ["21iX_CEN", "21iX_AB"]:
                        tx_dept = dept

                tx_row = tx[(tx["ScheduledDate"] == row["ScheduledDate"]) & (tx["Department"] == tx_dept)]
                ns_col = next((c for c in tx_row.columns if "NewStarts" in c and "Course" in c), None)
                if ns_col and not tx_row.empty:
                    new_starts = int(tx_row[ns_col].sum())

            # Format time strings, ensuring NaN/empty values show as blank
            def format_time(time_val):
                if pd.isna(time_val) or not time_val or str(time_val).strip() == "":
                    return ""
                return str(time_val)[:5]

            rows.append({
                "Date": date_str,
                "Location": dept,
                "Appointments": appts,
                "Scheduled Start": format_time(sched_start),
                "Scheduled End": format_time(sched_end),
                "Actual Start": format_time(actual_start),
                "Actual End": format_time(actual_end),
                "Duration (hrs)": duration,
                "New Starts": new_starts,
            })

        return sorted(rows, key=lambda x: x["Date"], reverse=True)

    except Exception:
        return []


# ---------------------------------------------------------------------------
# Settings Panel Toggle Callbacks
# ---------------------------------------------------------------------------

@callback(
    Output("ops-volume-settings-panel", "style"),
    Input("ops-volume-settings-btn", "n_clicks"),
    State("ops-volume-settings-panel", "style"),
    prevent_initial_call=True,
)
def toggle_volume_settings(n, style):
    if not n:
        return style
    current = style or {}
    is_hidden = current.get("display") == "none"
    return {"display": "block"} if is_hidden else {"display": "none"}


@callback(
    Output("ops-ribbon-settings-panel", "style"),
    Input("ops-ribbon-settings-btn", "n_clicks"),
    State("ops-ribbon-settings-panel", "style"),
    prevent_initial_call=True,
)
def toggle_ribbon_settings(n, style):
    if not n:
        return style
    current = style or {}
    is_hidden = current.get("display") == "none"
    return {"display": "block"} if is_hidden else {"display": "none"}


# ---------------------------------------------------------------------------
# PNG Export Callbacks
# ---------------------------------------------------------------------------

clientside_callback(
    """function(n) {
        if (!n) return window.dash_clientside.no_update;
        var wrapper = document.getElementById('ops-chart-volume');
        var graphEl = wrapper ? wrapper.querySelector('.js-plotly-plot') : null;
        if (graphEl) {
            Plotly.downloadImage(graphEl, {format: 'png', width: 1200, height: 600, filename: 'treatment_appointments'});
        }
        return window.dash_clientside.no_update;
    }""",
    Output("ops-volume-settings-export", "n_clicks"),
    Input("ops-volume-settings-export", "n_clicks"),
    prevent_initial_call=True,
)

clientside_callback(
    """function(n) {
        if (!n) return window.dash_clientside.no_update;
        var wrapper = document.getElementById('ops-chart-ribbon');
        var graphEl = wrapper ? wrapper.querySelector('.js-plotly-plot') : null;
        if (graphEl) {
            Plotly.downloadImage(graphEl, {format: 'png', width: 1200, height: 600, filename: 'operating_hours'});
        }
        return window.dash_clientside.no_update;
    }""",
    Output("ops-ribbon-settings-export", "n_clicks"),
    Input("ops-ribbon-settings-export", "n_clicks"),
    prevent_initial_call=True,
)

clientside_callback(
    """function(n) {
        if (!n) return window.dash_clientside.no_update;
        var wrapper = document.getElementById('ops-chart-efficiency');
        var graphEl = wrapper ? wrapper.querySelector('.js-plotly-plot') : null;
        if (graphEl) {
            Plotly.downloadImage(graphEl, {format: 'png', width: 1200, height: 600, filename: 'resource_utilization'});
        }
        return window.dash_clientside.no_update;
    }""",
    Output("ops-efficiency-settings-export", "n_clicks"),
    Input("ops-efficiency-settings-export", "n_clicks"),
    prevent_initial_call=True,
)


# ---------------------------------------------------------------------------
# Table CSV Export
# ---------------------------------------------------------------------------

clientside_callback(
    """function(n) {
        if (!n) return window.dash_clientside.no_update;
        var gridApi = window.dash_ag_grid['ops-table'];
        if (gridApi && gridApi.api) {
            gridApi.api.exportDataAsCsv({fileName: 'daily_detail.csv'});
        }
        return window.dash_clientside.no_update;
    }""",
    Output("ops-table-export", "n_clicks"),
    Input("ops-table-export", "n_clicks"),
    prevent_initial_call=True,
)
