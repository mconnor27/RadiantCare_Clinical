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

def _date_presets_ops():
    """Operations-specific date presets."""
    return dmc.SegmentedControl(
        id="operations-filter-date-preset",
        data=[
            {"value": "today", "label": "Today"},
            {"value": "week", "label": "This Week"},
            {"value": "2weeks", "label": "Next 2 Wks"},
            {"value": "month", "label": "This Month"},
            {"value": "3mo", "label": "3 Mo"},
            {"value": "ytd", "label": "YTD"},
            {"value": "all", "label": "All"},
        ],
        value="3mo",
        size="sm",
    )


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
    """Operations page filter bar with date presets, department chips, and machine select."""
    return dmc.Paper(
        children=[
            dmc.Group(
                children=[
                    _date_presets_ops(),
                    department_chips("operations"),
                    _machine_select(),
                ],
                gap="md",
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
        dmc.Title("Operations", order=2, className="page-title"),
        _ops_filter_bar(),

        # Hidden dummy inputs for filter bar IDs required by other pages
        dcc.Store(id="operations-filter-daterange", data=None),
        dcc.Store(id="operations-filter-physician", data=None),

        # KPI row — 5 cards with sparklines
        dmc.Grid(
            id="ops-kpi-row",
            gutter=16,
            children=[
                dmc.GridCol(id="ops-kpi-today", span={"base": 6, "sm": 4, "md": 2.4}),
                dmc.GridCol(id="ops-kpi-daily-avg", span={"base": 6, "sm": 4, "md": 2.4}),
                dmc.GridCol(id="ops-kpi-next-slot", span={"base": 6, "sm": 4, "md": 2.4}),
                dmc.GridCol(id="ops-kpi-scheduled-week", span={"base": 6, "sm": 4, "md": 2.4}),
                dmc.GridCol(id="ops-kpi-new-starts", span={"base": 6, "sm": 4, "md": 2.4}),
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
                                    dmc.Text("Treatment Appointments (completed)", size="sm", fw=500, c="#6B7280"),
                                    dmc.Group(gap="xs", align="center", children=[
                                        dmc.SegmentedControl(
                                            id="ops-volume-agg",
                                            data=[
                                                {"value": "D", "label": "Daily"},
                                                {"value": "W", "label": "Weekly"},
                                                {"value": "M", "label": "Monthly"},
                                            ],
                                            value="W",
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
                                    dcc.Graph(id="ops-chart-volume", config={"displayModeBar": False}),
                                ],
                            ),
                        ],
                        p="sm", radius="md", shadow="xs", withBorder=True,
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
                                    dcc.Graph(id="ops-chart-heatmap", config={"displayModeBar": False}),
                                ],
                            ),
                        ],
                        p="sm", radius="md", shadow="xs", withBorder=True,
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
                                "ops-ribbon",
                                chart_types=[
                                    {"value": "ribbon", "label": "Ribbon"},
                                    {"value": "line", "label": "Line"},
                                    {"value": "bar", "label": "Bar"},
                                ],
                                show_smooth=True,
                                smooth_max=14,
                                smooth_default=3,
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
                        dcc.Graph(id="ops-chart-ribbon", config={"displayModeBar": False}),
                    ],
                ),
            ],
            p="md", radius="md", shadow="xs", withBorder=True,
        ),

        # Daily Detail Table (full-width)
        dmc.Paper(
            children=[
                dmc.Group(
                    justify="space-between", mb="sm",
                    children=[
                        dmc.Text("Daily Detail", size="sm", fw=500, c="#6B7280"),
                        dmc.Button(
                            "Export CSV",
                            id="ops-table-export",
                            size="compact-xs",
                            variant="light",
                            leftSection=dmc.Text("↓", size="xs"),
                        ),
                    ],
                ),
                dag.AgGrid(
                    id="ops-table",
                    columnDefs=[
                        {"field": "Date", "sortable": True, "filter": True, "width": 120},
                        {"field": "Location", "sortable": True, "filter": True, "width": 120},
                        {"field": "Appointments", "sortable": True, "filter": True, "width": 120, "type": "numericColumn"},
                        {"field": "First Start", "sortable": True, "filter": True, "width": 110},
                        {"field": "Last End", "sortable": True, "filter": True, "width": 110},
                        {"field": "Duration (hrs)", "sortable": True, "filter": True, "width": 120, "type": "numericColumn"},
                        {"field": "New Starts", "sortable": True, "filter": True, "width": 110, "type": "numericColumn"},
                    ],
                    defaultColDef={"resizable": True, "sortable": True, "filter": True},
                    dashGridOptions={"pagination": True, "paginationPageSize": 15},
                    style={"height": 400},
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
        dcc.Store(id="ops-store-kpi-sparklines"),
    ],
)


# ---------------------------------------------------------------------------
# Helper: Date Range Calculation
# ---------------------------------------------------------------------------

def _get_date_range(preset, last_date):
    """Calculate start date based on preset, using last_date as reference."""
    today = last_date
    if preset == "today":
        return today, today
    elif preset == "week":
        return today - timedelta(days=today.weekday()), today
    elif preset == "2weeks":
        return today, today + timedelta(days=14)
    elif preset == "month":
        return today.replace(day=1), today
    elif preset == "3mo":
        return today - timedelta(days=90), today
    elif preset == "ytd":
        return pd.Timestamp(today.year, 1, 1), today
    else:  # all
        return pd.Timestamp("2020-01-01"), today


# ---------------------------------------------------------------------------
# Helper: Operating Hours Data (for clientside smoothing)
# ---------------------------------------------------------------------------

def _prepare_hours_data(departments, machines, days_back=90):
    """Prepare raw operating hours data for clientside smoothing."""
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

                # Drop rows with no valid times
                site_data = site_data.dropna(subset=["start_hour", "end_hour"])
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
# Helper: Treatment Volume Data (for clientside smoothing)
# ---------------------------------------------------------------------------

def _prepare_volume_data(departments, machines, agg, start, end):
    """Prepare treatment volume data for clientside rendering."""
    from data.loader import load_daily_volume

    try:
        dv = load_daily_volume()

        # Filter to departments (site-level only)
        sites = departments if departments else DEPARTMENTS
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

@callback(
    Output("ops-kpi-today", "children"),
    Output("ops-kpi-daily-avg", "children"),
    Output("ops-kpi-next-slot", "children"),
    Output("ops-kpi-scheduled-week", "children"),
    Output("ops-kpi-new-starts", "children"),
    Output("ops-store-kpi-sparklines", "data"),
    Input("ops-interval", "n_intervals"),
    Input("operations-filter-date-preset", "value"),
    Input("operations-filter-department", "value"),
    Input("operations-filter-machine", "value"),
)
def update_kpis(_n, date_preset, departments, machines):
    """Compute all 5 KPI cards with sparkline IDs."""
    from data.loader import load_daily_volume, load_daily_volume_future, load_availability, load_treatment

    sparkline_data = {}

    # Load data
    try:
        dv = load_daily_volume()
        dv_future = load_daily_volume_future()
        avail = load_availability()
        tx = load_treatment()
    except Exception:
        dv = pd.DataFrame()
        dv_future = pd.DataFrame()
        avail = pd.DataFrame()
        tx = pd.DataFrame()

    # Filter departments
    sites = departments if departments else DEPARTMENTS
    if not dv.empty and "Department" in dv.columns:
        dv = dv[dv["Department"].isin(sites)]
    if not dv_future.empty and "Department" in dv_future.columns:
        dv_future = dv_future[dv_future["Department"].isin(sites)]
    if not tx.empty and "Department" in tx.columns:
        tx_sites = [d for d in tx["Department"].unique() if d in sites]
        tx = tx[tx["Department"].isin(tx_sites)]

    today = pd.Timestamp.now().normalize()
    last_date = dv["ScheduledDate"].max() if not dv.empty and "ScheduledDate" in dv.columns else today

    # --- 1. Treatments Today ---
    if not dv.empty:
        today_data = dv[dv["ScheduledDate"] == last_date]
        today_count = int(today_data["AppointmentCount"].sum()) if "AppointmentCount" in today_data.columns else 0

        # Sparkline: last 14 days
        spark_start = last_date - timedelta(days=14)
        spark_data = dv[(dv["ScheduledDate"] >= spark_start) & (dv["ScheduledDate"] <= last_date)]
        spark_data = spark_data[spark_data["ScheduledDate"].dt.weekday < 5]
        daily_totals = spark_data.groupby("ScheduledDate")["AppointmentCount"].sum()
        sparkline_data["today"] = {
            "labels": [d.isoformat() for d in daily_totals.index],
            "values": daily_totals.tolist(),
            "color": PRIMARY,
        }
        kpi_today = kpi_card(
            "Treatments Today", f"{today_count:,}",
            accent_color=PRIMARY,
            sparkline_id="ops-spark-today",
        )
    else:
        kpi_today = kpi_card("Treatments Today", "N/A")

    # --- 2. Avg Daily Volume (30d) ---
    if not dv.empty:
        start_30 = last_date - timedelta(days=30)
        vol_30 = dv[(dv["ScheduledDate"] >= start_30) & (dv["ScheduledDate"] <= last_date)]
        vol_30 = vol_30[vol_30["ScheduledDate"].dt.weekday < 5]
        if not vol_30.empty:
            daily_avg = vol_30.groupby("ScheduledDate")["AppointmentCount"].sum()
            avg_val = round(daily_avg.mean(), 1)
            sparkline_data["avg30"] = {
                "labels": [d.isoformat() for d in daily_avg.index],
                "values": daily_avg.tolist(),
                "color": CHART_COLORWAY[1],
            }
            kpi_avg = kpi_card(
                "Avg Daily Volume (30d)", str(avg_val),
                accent_color=CHART_COLORWAY[1],
                sparkline_id="ops-spark-avg30",
            )
        else:
            kpi_avg = kpi_card("Avg Daily Volume (30d)", "N/A")
    else:
        kpi_avg = kpi_card("Avg Daily Volume (30d)", "N/A")

    # --- 3. Next Available Slot ---
    if not avail.empty and "SlotDate" in avail.columns:
        future_avail = avail[avail["SlotDate"] > today]
        if not future_avail.empty:
            next_slot = future_avail["SlotDate"].min()
            slot_str = next_slot.strftime("%b %d")
            days_out = (next_slot - today).days
            kpi_slot = kpi_card(
                "Next Available Slot", slot_str,
                value_detail=f"({days_out}d)",
                accent_color=CHART_COLORWAY[2],
            )
        else:
            kpi_slot = kpi_card("Next Available Slot", "None")
    else:
        kpi_slot = kpi_card("Next Available Slot", "N/A")

    # --- 4. Scheduled This Week ---
    if not dv_future.empty:
        week_start = today - timedelta(days=today.weekday())
        week_end = week_start + timedelta(days=6)
        week_future = dv_future[(dv_future["ScheduledDate"] >= week_start) & (dv_future["ScheduledDate"] <= week_end)]
        week_count = int(week_future["AppointmentCount"].sum()) if "AppointmentCount" in week_future.columns else 0
        kpi_scheduled = kpi_card(
            "Scheduled This Week", f"{week_count:,}",
            accent_color=CHART_COLORWAY[3],
        )
    else:
        kpi_scheduled = kpi_card("Scheduled This Week", "N/A")

    # --- 5. New Starts This Week ---
    if not tx.empty and "ScheduledDate" in tx.columns:
        week_start = last_date - timedelta(days=last_date.weekday())
        week_end = week_start + timedelta(days=6)
        tx_week = tx[(tx["ScheduledDate"] >= week_start) & (tx["ScheduledDate"] <= week_end)]
        ns_col = next((c for c in tx_week.columns if "NewStarts" in c and "Course" in c), None)
        if ns_col and ns_col in tx_week.columns:
            new_starts = int(tx_week[ns_col].sum())
        else:
            new_starts = 0
        kpi_new = kpi_card(
            "New Starts This Week", str(new_starts),
            accent_color=CHART_COLORWAY[4],
        )
    else:
        kpi_new = kpi_card("New Starts This Week", "N/A")

    return kpi_today, kpi_avg, kpi_slot, kpi_scheduled, kpi_new, sparkline_data


# ---------------------------------------------------------------------------
# Clientside callbacks for KPI sparklines
# ---------------------------------------------------------------------------

clientside_callback(
    """function(data, smoothPct) {
        if (!data || !data.today) return window.dash_clientside.no_update;
        var spark = data.today;
        var color = spark.color || "#7C2A83";
        return {
            data: [{
                x: spark.labels,
                y: spark.values,
                mode: "lines",
                line: {color: color, width: 1.5},
                hovertemplate: "%{x|%b %d}: %{y:,.0f}<extra></extra>"
            }],
            layout: {
                margin: {l: 0, r: 0, t: 0, b: 0},
                height: 34,
                plot_bgcolor: "rgba(0,0,0,0)",
                paper_bgcolor: "rgba(0,0,0,0)",
                xaxis: {visible: false},
                yaxis: {visible: false},
                showlegend: false,
                dragmode: false,
                hovermode: "x"
            }
        };
    }""",
    Output("ops-spark-today", "figure"),
    Input("ops-store-kpi-sparklines", "data"),
    Input("operations-filter-date-preset", "value"),
)

clientside_callback(
    """function(data, smoothPct) {
        if (!data || !data.avg30) return window.dash_clientside.no_update;
        var spark = data.avg30;
        var color = spark.color || "#2196F3";
        return {
            data: [{
                x: spark.labels,
                y: spark.values,
                mode: "lines",
                line: {color: color, width: 1.5},
                hovertemplate: "%{x|%b %d}: %{y:,.0f}<extra></extra>"
            }],
            layout: {
                margin: {l: 0, r: 0, t: 0, b: 0},
                height: 34,
                plot_bgcolor: "rgba(0,0,0,0)",
                paper_bgcolor: "rgba(0,0,0,0)",
                xaxis: {visible: false},
                yaxis: {visible: false},
                showlegend: false,
                dragmode: false,
                hovermode: "x"
            }
        };
    }""",
    Output("ops-spark-avg30", "figure"),
    Input("ops-store-kpi-sparklines", "data"),
    Input("operations-filter-date-preset", "value"),
)


# ---------------------------------------------------------------------------
# Volume Chart Callback — outputs raw data to store
# ---------------------------------------------------------------------------

@callback(
    Output("ops-store-volume", "data"),
    Input("ops-interval", "n_intervals"),
    Input("ops-volume-agg", "value"),
    Input("operations-filter-date-preset", "value"),
    Input("operations-filter-department", "value"),
    Input("operations-filter-machine", "value"),
    running=[(Output("ops-volume-loading", "visible"), True, False)],
)
def update_volume_data(_n, agg, date_preset, departments, machines):
    """Load treatment volume data to store."""
    from data.loader import load_daily_volume

    try:
        dv = load_daily_volume()
        if dv.empty:
            return None

        last_date = dv["ScheduledDate"].max()
        start, end = _get_date_range(date_preset, last_date)
        return _prepare_volume_data(departments, machines, agg, start, end)
    except Exception:
        return None


# Clientside callback for volume chart smoothing with chart type
clientside_callback(
    ClientsideFunction(namespace="census", function_name="smoothChartWithType"),
    Output("ops-chart-volume", "figure"),
    Input("ops-store-volume", "data"),
    Input("ops-volume-settings-smooth", "value"),
    Input("ops-volume-settings-type", "value"),
    State("ops-chart-volume", "figure"),
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
        dv = dv[dv["Department"].isin(sites)]

        # Build treatment rows (by machine if machines filter, else by site)
        machines_to_show = machines if machines else MACHINES
        y_labels = machines_to_show + ["Exam", "Simulation"]

        # Generate date range (next 14 calendar days)
        date_range = pd.date_range(today, two_weeks, freq="D")
        x_labels = [d.strftime("%m/%d %a") for d in date_range]

        # Initialize heatmap matrix
        z_data = np.zeros((len(y_labels), len(date_range)))
        hover_data = [[f"{y}: 0" for _ in date_range] for y in y_labels]

        # Fill treatment rows
        if not dv.empty and "AppointmentCount" in dv.columns:
            for i, machine in enumerate(machines_to_show):
                # Match machine to department or machine-specific data
                machine_data = dv[dv["Department"].str.contains(machine.replace("_", "|"), case=False, na=False)]
                if machine_data.empty and machine in ["TrueBeamNorth", "21EX"]:
                    machine_data = dv[dv["Department"] == "Lacey"]
                elif machine_data.empty and machine == "21iX_CEN":
                    machine_data = dv[dv["Department"] == "Centralia"]
                elif machine_data.empty and machine == "21iX_AB":
                    machine_data = dv[dv["Department"] == "Aberdeen"]

                for j, date in enumerate(date_range):
                    day_data = machine_data[machine_data["ScheduledDate"] == date]
                    count = int(day_data["AppointmentCount"].sum()) if not day_data.empty else 0
                    z_data[i, j] = count
                    hover_data[i][j] = f"{machine}: {count}"

        # Fill availability rows (Exam and Simulation)
        if not avail.empty and "SlotDate" in avail.columns and "Category" in avail.columns:
            avail = avail[(avail["SlotDate"] >= today) & (avail["SlotDate"] <= two_weeks)]

            for cat_idx, category in enumerate(["Exam", "Simulation"]):
                row_idx = len(machines_to_show) + cat_idx
                cat_data = avail[avail["Category"].str.contains(category, case=False, na=False)]
                for j, date in enumerate(date_range):
                    day_data = cat_data[cat_data["SlotDate"] == date]
                    count = len(day_data)
                    z_data[row_idx, j] = count
                    hover_data[row_idx][j] = f"{category}: {count} slots"

        # Build heatmap
        fig = go.Figure(go.Heatmap(
            z=z_data,
            x=x_labels,
            y=y_labels,
            colorscale=[[0, "#F3E8F5"], [1, "#7C2A83"]],
            text=z_data.astype(int).astype(str),
            texttemplate="%{text}",
            textfont={"size": 10},
            hovertemplate="<b>%{y}</b><br>%{x}<br>%{z:.0f}<extra></extra>",
            showscale=False,
        ))

        fig.update_layout(
            height=300,
            font=dict(family=FONT_FAMILY, size=11),
            plot_bgcolor="#FFFFFF",
            paper_bgcolor="#FFFFFF",
            margin=dict(l=100, r=16, t=16, b=48),
            xaxis=dict(side="bottom", tickangle=45),
            yaxis=dict(autorange="reversed"),
        )

        return fig

    except Exception:
        return empty_figure("Unable to load schedule data")


# ---------------------------------------------------------------------------
# Ribbon Chart Callback — outputs raw data to store
# ---------------------------------------------------------------------------

@callback(
    Output("ops-store-ribbon", "data"),
    Input("ops-interval", "n_intervals"),
    Input("ops-ribbon-range", "value"),
    Input("ops-ribbon-site", "value"),
    Input("operations-filter-department", "value"),
    Input("operations-filter-machine", "value"),
    running=[(Output("ops-ribbon-loading", "visible"), True, False)],
)
def update_ribbon_data(_n, range_days, site_filter, departments, machines):
    """Load operating hours data to store."""
    days = int(range_days) if range_days else 90
    # Use chart's own site selector
    if site_filter and site_filter != "all":
        sites = [site_filter]
    else:
        sites = departments if departments else None
    return _prepare_hours_data(sites, machines, days_back=days)


# Clientside callback for ribbon chart smoothing with chart type
clientside_callback(
    ClientsideFunction(namespace="hoursRibbon", function_name="smoothChartWithType"),
    Output("ops-chart-ribbon", "figure"),
    Input("ops-store-ribbon", "data"),
    Input("ops-ribbon-settings-smooth", "value"),
    Input("ops-ribbon-settings-type", "value"),
)


# ---------------------------------------------------------------------------
# Daily Detail Table Callback
# ---------------------------------------------------------------------------

@callback(
    Output("ops-table", "rowData"),
    Input("ops-interval", "n_intervals"),
    Input("operations-filter-date-preset", "value"),
    Input("operations-filter-department", "value"),
    Input("operations-filter-machine", "value"),
)
def update_table(_n, date_preset, departments, machines):
    """Build daily detail table data."""
    from data.loader import load_daily_volume, load_treatment

    try:
        dv = load_daily_volume()
        tx = load_treatment()

        if dv.empty:
            return []

        last_date = dv["ScheduledDate"].max()
        start, end = _get_date_range(date_preset, last_date)

        # Filter
        sites = departments if departments else DEPARTMENTS
        dv = dv[dv["Department"].isin(sites)]
        dv = dv[(dv["ScheduledDate"] >= start) & (dv["ScheduledDate"] <= end)]

        if dv.empty:
            return []

        # Build row data
        rows = []
        for _, row in dv.iterrows():
            date_str = row["ScheduledDate"].strftime("%Y-%m-%d") if pd.notna(row["ScheduledDate"]) else ""
            dept = row.get("Department", "")
            appts = int(row.get("AppointmentCount", 0))

            # Parse times
            start_time = row.get("FirstActualStart") or row.get("FirstScheduledStart", "")
            end_time = row.get("LastActualEnd") or row.get("LastScheduledEnd", "")

            # Calculate duration
            duration = ""
            try:
                if start_time and end_time:
                    s_parts = str(start_time).split(":")
                    e_parts = str(end_time).split(":")
                    s_hr = int(s_parts[0]) + int(s_parts[1]) / 60
                    e_hr = int(e_parts[0]) + int(e_parts[1]) / 60
                    duration = round(e_hr - s_hr, 1)
            except Exception:
                pass

            # Get new starts from treatment data
            new_starts = 0
            if not tx.empty and "ScheduledDate" in tx.columns:
                tx_row = tx[(tx["ScheduledDate"] == row["ScheduledDate"]) & (tx["Department"] == dept)]
                ns_col = next((c for c in tx_row.columns if "NewStarts" in c and "Course" in c), None)
                if ns_col and not tx_row.empty:
                    new_starts = int(tx_row[ns_col].sum())

            rows.append({
                "Date": date_str,
                "Location": dept,
                "Appointments": appts,
                "First Start": str(start_time)[:5] if start_time else "",
                "Last End": str(end_time)[:5] if end_time else "",
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
