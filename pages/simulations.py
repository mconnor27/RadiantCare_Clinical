"""Simulations page — volume trends, timing intervals, schedule ribbons, detail grid."""

import dash
import dash_mantine_components as dmc
from dash import callback, Input, Output, State, dcc, clientside_callback, ClientsideFunction
import dash_ag_grid as dag
import plotly.graph_objects as go
import pandas as pd
import numpy as np
from datetime import timedelta

from config.settings import (
    DEPARTMENTS, DEPARTMENT_COLORS, CHART_COLORWAY,
    PRIMARY, FONT_FAMILY,
)
from components.filter_bar import (
    filter_bar, date_presets, date_range_picker, department_chips, physician_select,
)
from components.kpi_card import kpi_card
from components.chart_settings import chart_settings_popover
from utils.charts import apply_default_layout, empty_figure

dash.register_page(__name__, path="/simulations", name="Simulations", order=4)

PAGE_ID = "sim"


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------
layout = dmc.Stack(
    gap=16,
    className="page-content",
    children=[
        dmc.Title("Simulations", order=2, className="page-title"),

        # Filter bar
        filter_bar("sim", children=[
            date_presets("sim"),
            date_range_picker("sim"),
            department_chips("sim"),
            physician_select("sim"),
            dmc.MultiSelect(
                id="sim-filter-simtype",
                placeholder="Sim Type",
                data=[],
                clearable=True,
                size="sm",
                w=220,
            ),
            dmc.ChipGroup(
                children=[
                    dmc.Chip("Completed", value="completed", size="sm", variant="filled"),
                    dmc.Chip("All", value="all", size="sm", variant="filled"),
                ],
                id="sim-filter-status",
                value="all",
                multiple=False,
            ),
        ]),

        # KPI row — 5 cards with sparklines
        dmc.Grid(id="sim-kpi-row", gutter="md", children=[
            dmc.GridCol(id="sim-kpi-total", span={"base": 6, "md": 2.4}),
            dmc.GridCol(id="sim-kpi-consult-sim", span={"base": 6, "md": 2.4}),
            dmc.GridCol(id="sim-kpi-sim-tx", span={"base": 6, "md": 2.4}),
            dmc.GridCol(id="sim-kpi-consult-tx", span={"base": 6, "md": 2.4}),
            dmc.GridCol(id="sim-kpi-resim", span={"base": 6, "md": 2.4}),
        ]),

        # Row 1: Volume Trend + Timing Intervals (half-width each)
        dmc.Grid(gutter="md", children=[
            dmc.GridCol(
                dmc.Paper(
                    children=[
                        dmc.Group(
                            justify="space-between", mb="sm",
                            children=[
                                dmc.Text("Simulation Volume Trend", size="sm", fw=500, c="#6B7280"),
                                dmc.Group(gap="xs", align="center", children=[
                                    dmc.SegmentedControl(
                                        id="sim-volume-agg",
                                        data=[
                                            {"value": "W", "label": "Weekly"},
                                            {"value": "M", "label": "Monthly"},
                                        ],
                                        value="W", size="xs",
                                    ),
                                    chart_settings_popover(
                                        "sim-volume",
                                        chart_types=[
                                            {"value": "bar", "label": "Bar"},
                                            {"value": "area", "label": "Area"},
                                            {"value": "line", "label": "Line"},
                                        ],
                                        show_smooth=True,
                                        smooth_max=12,
                                        smooth_default=0,
                                    ),
                                ]),
                            ],
                        ),
                        dmc.Box(
                            pos="relative",
                            children=[
                                dmc.LoadingOverlay(
                                    id="sim-volume-loading",
                                    visible=False,
                                    loaderProps={"type": "dots", "color": "#7C2A83"},
                                    overlayProps={"radius": "sm", "blur": 2},
                                ),
                                dcc.Graph(id="sim-chart-volume", config={"displayModeBar": False}),
                            ],
                        ),
                    ],
                    p="md", radius="md", shadow="xs", withBorder=True,
                ),
                span={"base": 12, "md": 6},
            ),
            dmc.GridCol(
                dmc.Paper(
                    children=[
                        dmc.Group(
                            justify="space-between", mb="sm",
                            children=[
                                dmc.Text("Timing Intervals (monthly median)", size="sm", fw=500, c="#6B7280"),
                                chart_settings_popover(
                                    "sim-timing",
                                    chart_types=[
                                        {"value": "line", "label": "Line"},
                                        {"value": "area", "label": "Area"},
                                    ],
                                    show_smooth=True,
                                    smooth_max=6,
                                    smooth_default=2,
                                ),
                            ],
                        ),
                        dmc.Box(
                            pos="relative",
                            children=[
                                dmc.LoadingOverlay(
                                    id="sim-timing-loading",
                                    visible=False,
                                    loaderProps={"type": "dots", "color": "#7C2A83"},
                                    overlayProps={"radius": "sm", "blur": 2},
                                ),
                                dcc.Graph(id="sim-chart-timing", config={"displayModeBar": False}),
                            ],
                        ),
                    ],
                    p="md", radius="md", shadow="xs", withBorder=True,
                ),
                span={"base": 12, "md": 6},
            ),
        ]),

        # Row 2: Sim Type Distribution + Schedule Ribbon (half-width each)
        dmc.Grid(gutter="md", children=[
            dmc.GridCol(
                dmc.Paper(
                    children=[
                        dmc.Text("Sim Type Distribution", size="sm", fw=500, c="#6B7280", mb="sm"),
                        dmc.Box(
                            pos="relative",
                            children=[
                                dmc.LoadingOverlay(id="sim-dist-loading", visible=False, loaderProps={"type": "dots", "color": "#7C2A83"}),
                                dcc.Graph(id="sim-chart-distribution", config={"displayModeBar": False}),
                            ],
                        ),
                    ],
                    p="md", radius="md", shadow="xs", withBorder=True,
                ),
                span={"base": 12, "md": 6},
            ),
            dmc.GridCol(
                dmc.Paper(
                    children=[
                        dmc.Group(
                            justify="space-between", mb="sm",
                            children=[
                                dmc.Text("Simulation Schedule Ribbon", size="sm", fw=500, c="#6B7280"),
                                chart_settings_popover(
                                    "sim-ribbon",
                                    chart_types=[
                                        {"value": "ribbon", "label": "Ribbon"},
                                        {"value": "line", "label": "Line"},
                                    ],
                                    show_smooth=True,
                                    smooth_max=14,
                                    smooth_default=3,
                                ),
                            ],
                        ),
                        dmc.Box(
                            pos="relative",
                            children=[
                                dmc.LoadingOverlay(id="sim-ribbon-loading", visible=False, loaderProps={"type": "dots", "color": "#7C2A83"}),
                                dcc.Graph(id="sim-chart-ribbon", config={"displayModeBar": False}),
                            ],
                        ),
                    ],
                    p="md", radius="md", shadow="xs", withBorder=True,
                ),
                span={"base": 12, "md": 6},
            ),
        ]),

        # Detail table — full width
        dmc.Paper(
            children=[
                dmc.Group(justify="space-between", mb="sm", children=[
                    dmc.Text("Simulation Detail", size="sm", fw=500, c="#6B7280"),
                    dmc.Button("Export CSV", id="sim-table-export", size="compact-xs", variant="light"),
                ]),
                dag.AgGrid(
                    id="sim-detail-grid",
                    columnDefs=[],
                    rowData=[],
                    defaultColDef={"sortable": True, "filter": True, "resizable": True},
                    dashGridOptions={"pagination": True, "paginationPageSize": 50},
                    style={"height": 400},
                    className="ag-theme-quartz",
                ),
            ],
            p="md", radius="md", shadow="xs", withBorder=True,
        ),

        dcc.Interval(id="sim-interval", interval=300_000, n_intervals=0),

        # Stores for clientside rendering
        dcc.Store(id="sim-store-volume"),
        dcc.Store(id="sim-store-timing"),
        dcc.Store(id="sim-store-ribbon"),
        dcc.Store(id="sim-store-kpi-sparklines"),
    ],
)


# ---------------------------------------------------------------------------
# Helper: Date Filter
# ---------------------------------------------------------------------------

def _get_date_range(date_preset, date_range, last_date):
    """Calculate start/end based on preset or explicit range."""
    if date_range and len(date_range) == 2 and date_range[0] and date_range[1]:
        return pd.Timestamp(date_range[0]), pd.Timestamp(date_range[1])
    elif date_preset == "ytd":
        return pd.Timestamp(last_date.year, 1, 1), last_date
    elif date_preset == "12mo":
        return last_date - timedelta(days=365), last_date
    else:
        return pd.Timestamp("2020-01-01"), last_date


# ---------------------------------------------------------------------------
# Callback: populate sim type options
# ---------------------------------------------------------------------------

@callback(
    Output("sim-filter-simtype", "data"),
    Input("sim-interval", "n_intervals"),
)
def populate_simtype_options(_n):
    """Populate sim type filter with unique ActivityName values."""
    try:
        from data.loader import load_simulations
        df = load_simulations()
        if "ActivityName" in df.columns:
            types = sorted(df["ActivityName"].dropna().unique().tolist())
            return [{"value": t, "label": t} for t in types]
    except Exception:
        pass
    return []


# ---------------------------------------------------------------------------
# Main callback
# ---------------------------------------------------------------------------

@callback(
    Output("sim-kpi-total", "children"),
    Output("sim-kpi-consult-sim", "children"),
    Output("sim-kpi-sim-tx", "children"),
    Output("sim-kpi-consult-tx", "children"),
    Output("sim-kpi-resim", "children"),
    Output("sim-store-volume", "data"),
    Output("sim-store-timing", "data"),
    Output("sim-chart-distribution", "figure"),
    Output("sim-store-ribbon", "data"),
    Output("sim-detail-grid", "rowData"),
    Output("sim-detail-grid", "columnDefs"),
    Output("sim-store-kpi-sparklines", "data"),
    Input("sim-interval", "n_intervals"),
    Input("sim-volume-agg", "value"),
    Input("sim-filter-department", "value"),
    Input("sim-filter-physician", "value"),
    Input("sim-filter-date-preset", "value"),
    Input("sim-filter-daterange", "value"),
    Input("sim-filter-simtype", "value"),
    Input("sim-filter-status", "value"),
    running=[
        (Output("sim-volume-loading", "visible"), True, False),
        (Output("sim-timing-loading", "visible"), True, False),
        (Output("sim-dist-loading", "visible"), True, False),
        (Output("sim-ribbon-loading", "visible"), True, False),
    ],
)
def update_simulations(_n, agg, departments, physicians, date_preset, date_range, sim_types, status):
    from data.loader import load_simulations

    na_card = kpi_card("--", "N/A")
    empty = empty_figure()

    try:
        df = load_simulations()
    except Exception:
        return (na_card,) * 5 + (None, None, empty, None, [], [], {})

    if df.empty:
        return (na_card,) * 5 + (None, None, empty, None, [], [], {})

    # Apply filters
    if departments and "Department" in df.columns:
        df = df[df["Department"].isin(departments)]

    if physicians and "SupervisingPhysician" in df.columns:
        df = df[df["SupervisingPhysician"].isin(physicians)]

    if sim_types and "ActivityName" in df.columns:
        df = df[df["ActivityName"].isin(sim_types)]

    if status == "completed" and "Status" in df.columns:
        df = df[df["Status"].str.lower() == "completed"]

    # Keep unfiltered-by-date copy for the ribbon (spans all historical data)
    df_all_dates = df.copy()

    # Apply date filter
    last_date = df["ScheduledDateTime"].max() if "ScheduledDateTime" in df.columns else pd.Timestamp.now().normalize()
    start, end = _get_date_range(date_preset, date_range, last_date)

    if "ScheduledDateTime" in df.columns:
        df = df[(df["ScheduledDateTime"] >= start) & (df["ScheduledDateTime"] <= end)]

    if df.empty:
        return (na_card,) * 5 + (None, None, empty, None, [], [], {})

    sparkline_data = {}

    # --- KPIs with sparklines ---
    kpi_total_card = kpi_card("Total Simulations", f"{len(df):,}", accent_color=PRIMARY, sparkline_id="sim-spark-total")

    # Build sparkline for total
    if "ScheduledDateTime" in df.columns:
        df_temp = df.copy()
        df_temp["week"] = df_temp["ScheduledDateTime"].dt.to_period("W").dt.to_timestamp()
        weekly = df_temp.groupby("week").size()
        if len(weekly) > 2:
            sparkline_data["total"] = {
                "labels": [d.isoformat() for d in weekly.index],
                "values": weekly.tolist(),
                "color": PRIMARY,
            }

    def _median_days(col):
        if col in df.columns:
            vals = pd.to_numeric(df[col], errors="coerce").dropna()
            if len(vals) > 0:
                return vals.median()
        return None

    def build_interval_sparkline(col, color):
        if col not in df.columns or "ScheduledDateTime" not in df.columns:
            return None
        temp = df[["ScheduledDateTime", col]].copy()
        temp[col] = pd.to_numeric(temp[col], errors="coerce")
        temp = temp.dropna()
        if temp.empty:
            return None
        temp["month"] = temp["ScheduledDateTime"].dt.to_period("M").dt.to_timestamp()
        monthly = temp.groupby("month")[col].median()
        if len(monthly) < 2:
            return None
        return {
            "labels": [d.isoformat() for d in monthly.index],
            "values": monthly.tolist(),
            "color": color,
        }

    cs_median = _median_days("DaysFromClinicExamToSimulation")
    cs_spark = build_interval_sparkline("DaysFromClinicExamToSimulation", CHART_COLORWAY[1])
    if cs_spark:
        sparkline_data["consult_sim"] = cs_spark
    kpi_cs = kpi_card(
        "Median Consult-to-Sim",
        f"{cs_median:.1f} days" if cs_median else "N/A",
        accent_color=CHART_COLORWAY[1],
        sparkline_id="sim-spark-consult-sim",
    )

    st_median = _median_days("DaysFromSimToTreatment")
    st_spark = build_interval_sparkline("DaysFromSimToTreatment", CHART_COLORWAY[2])
    if st_spark:
        sparkline_data["sim_tx"] = st_spark
    kpi_st = kpi_card(
        "Median Sim-to-Treatment",
        f"{st_median:.1f} days" if st_median else "N/A",
        accent_color=CHART_COLORWAY[2],
        sparkline_id="sim-spark-sim-tx",
    )

    ct_median = _median_days("DaysFromClinicExamToTreatment")
    kpi_ct = kpi_card(
        "Median Consult-to-Treatment",
        f"{ct_median:.1f} days" if ct_median else "N/A",
        accent_color=CHART_COLORWAY[3],
    )

    # Re-Sim Rate
    if "ActivityName" in df.columns:
        resim_count = df["ActivityName"].str.contains("Re-Simulation", case=False, na=False).sum()
        total_count = len(df)
        resim_pct = f"{(resim_count / total_count * 100):.1f}%" if total_count > 0 else "N/A"
    else:
        resim_pct = "N/A"
    kpi_resim_card = kpi_card("Re-Sim Rate", resim_pct, accent_color=CHART_COLORWAY[4])

    # --- Data for clientside charts ---
    volume_data = _prepare_volume_data(df, agg)
    timing_data = _prepare_timing_data(df)
    ribbon_data = _prepare_ribbon_data(df_all_dates)

    # Distribution chart (server-side)
    fig_distribution = _build_type_distribution(df)

    # --- Detail table ---
    row_data, col_defs = _build_detail_table(df)

    return (
        kpi_total_card, kpi_cs, kpi_st, kpi_ct, kpi_resim_card,
        volume_data, timing_data, fig_distribution, ribbon_data,
        row_data, col_defs, sparkline_data,
    )


# ---------------------------------------------------------------------------
# Clientside callbacks for charts
# ---------------------------------------------------------------------------

clientside_callback(
    ClientsideFunction(namespace="census", function_name="smoothChartWithType"),
    Output("sim-chart-volume", "figure"),
    Input("sim-store-volume", "data"),
    Input("sim-volume-settings-smooth", "value"),
    Input("sim-volume-settings-type", "value"),
    State("sim-chart-volume", "figure"),
)

clientside_callback(
    ClientsideFunction(namespace="census", function_name="smoothChartWithType"),
    Output("sim-chart-timing", "figure"),
    Input("sim-store-timing", "data"),
    Input("sim-timing-settings-smooth", "value"),
    Input("sim-timing-settings-type", "value"),
    State("sim-chart-timing", "figure"),
)

clientside_callback(
    ClientsideFunction(namespace="hoursRibbon", function_name="smoothChartWithType"),
    Output("sim-chart-ribbon", "figure"),
    Input("sim-store-ribbon", "data"),
    Input("sim-ribbon-settings-smooth", "value"),
    Input("sim-ribbon-settings-type", "value"),
)


# ---------------------------------------------------------------------------
# Clientside callbacks for KPI sparklines
# ---------------------------------------------------------------------------

clientside_callback(
    """function(data, _trigger) {
        if (!data || !data.total) return window.dash_clientside.no_update;
        var spark = data.total;
        return {
            data: [{x: spark.labels, y: spark.values, mode: "lines", line: {color: spark.color, width: 1.5}}],
            layout: {margin: {l: 0, r: 0, t: 0, b: 0}, height: 34, plot_bgcolor: "rgba(0,0,0,0)", paper_bgcolor: "rgba(0,0,0,0)", xaxis: {visible: false}, yaxis: {visible: false}, showlegend: false, hovermode: "x"}
        };
    }""",
    Output("sim-spark-total", "figure"),
    Input("sim-store-kpi-sparklines", "data"),
    Input("sim-filter-date-preset", "value"),
)

clientside_callback(
    """function(data, _trigger) {
        if (!data || !data.consult_sim) return window.dash_clientside.no_update;
        var spark = data.consult_sim;
        return {
            data: [{x: spark.labels, y: spark.values, mode: "lines", line: {color: spark.color, width: 1.5}}],
            layout: {margin: {l: 0, r: 0, t: 0, b: 0}, height: 34, plot_bgcolor: "rgba(0,0,0,0)", paper_bgcolor: "rgba(0,0,0,0)", xaxis: {visible: false}, yaxis: {visible: false}, showlegend: false, hovermode: "x"}
        };
    }""",
    Output("sim-spark-consult-sim", "figure"),
    Input("sim-store-kpi-sparklines", "data"),
    Input("sim-filter-date-preset", "value"),
)

clientside_callback(
    """function(data, _trigger) {
        if (!data || !data.sim_tx) return window.dash_clientside.no_update;
        var spark = data.sim_tx;
        return {
            data: [{x: spark.labels, y: spark.values, mode: "lines", line: {color: spark.color, width: 1.5}}],
            layout: {margin: {l: 0, r: 0, t: 0, b: 0}, height: 34, plot_bgcolor: "rgba(0,0,0,0)", paper_bgcolor: "rgba(0,0,0,0)", xaxis: {visible: false}, yaxis: {visible: false}, showlegend: false, hovermode: "x"}
        };
    }""",
    Output("sim-spark-sim-tx", "figure"),
    Input("sim-store-kpi-sparklines", "data"),
    Input("sim-filter-date-preset", "value"),
)


# ---------------------------------------------------------------------------
# Settings panel toggles
# ---------------------------------------------------------------------------

@callback(Output("sim-volume-settings-panel", "style"), Input("sim-volume-settings-btn", "n_clicks"), State("sim-volume-settings-panel", "style"), prevent_initial_call=True)
def toggle_volume_settings(n, style):
    if not n: return style
    return {"display": "block"} if (style or {}).get("display") == "none" else {"display": "none"}

@callback(Output("sim-timing-settings-panel", "style"), Input("sim-timing-settings-btn", "n_clicks"), State("sim-timing-settings-panel", "style"), prevent_initial_call=True)
def toggle_timing_settings(n, style):
    if not n: return style
    return {"display": "block"} if (style or {}).get("display") == "none" else {"display": "none"}

@callback(Output("sim-ribbon-settings-panel", "style"), Input("sim-ribbon-settings-btn", "n_clicks"), State("sim-ribbon-settings-panel", "style"), prevent_initial_call=True)
def toggle_ribbon_settings(n, style):
    if not n: return style
    return {"display": "block"} if (style or {}).get("display") == "none" else {"display": "none"}


# ---------------------------------------------------------------------------
# Data preparation for clientside charts
# ---------------------------------------------------------------------------

def _prepare_volume_data(df, agg):
    """Prepare volume trend data for clientside rendering."""
    if df.empty or "ScheduledDateTime" not in df.columns:
        return None

    df = df.copy()
    df["period"] = df["ScheduledDateTime"].dt.to_period(agg).dt.to_timestamp()

    all_periods = sorted(df["period"].unique())
    dates = [d.isoformat() for d in all_periods]

    series = []
    if "ActivityName" in df.columns:
        sim_types = sorted(df["ActivityName"].dropna().unique().tolist())
        for i, stype in enumerate(sim_types):
            type_data = df[df["ActivityName"] == stype]
            counts = type_data.groupby("period").size().reindex(all_periods, fill_value=0)
            series.append({
                "name": stype,
                "values": counts.tolist(),
                "color": CHART_COLORWAY[i % len(CHART_COLORWAY)],
            })
    else:
        counts = df.groupby("period").size().reindex(all_periods, fill_value=0)
        series.append({
            "name": "Simulations",
            "values": counts.tolist(),
            "color": PRIMARY,
        })

    return {"dates": dates, "series": series, "height": 350, "yTitle": "Simulations"}


def _prepare_timing_data(df):
    """Prepare timing intervals data for clientside rendering."""
    if df.empty or "ScheduledDateTime" not in df.columns:
        return None

    df = df.copy()
    df["month"] = df["ScheduledDateTime"].dt.to_period("M").dt.to_timestamp()

    all_months = sorted(df["month"].unique())
    dates = [d.isoformat() for d in all_months]

    interval_cols = [
        ("DaysFromClinicExamToSimulation", "Consult \u2192 Sim", CHART_COLORWAY[0]),
        ("DaysFromSimToTreatment", "Sim \u2192 Treatment", CHART_COLORWAY[1]),
        ("DaysFromClinicExamToTreatment", "Consult \u2192 Treatment", CHART_COLORWAY[2]),
    ]

    series = []
    for col, label, color in interval_cols:
        if col in df.columns:
            temp = df[["month", col]].copy()
            temp[col] = pd.to_numeric(temp[col], errors="coerce")
            temp = temp.dropna(subset=[col])
            if temp.empty:
                continue
            monthly = temp.groupby("month")[col].median().reindex(all_months, fill_value=None)
            # Fill None with 0 for chart
            values = [v if pd.notna(v) else 0 for v in monthly.tolist()]
            series.append({
                "name": label,
                "values": values,
                "color": color,
            })

    if not series:
        return None

    return {"dates": dates, "series": series, "height": 350, "yTitle": "Median Days"}


def _prepare_ribbon_data(df):
    """Prepare schedule ribbon data for clientside rendering.

    This spans ALL historical data (not just filtered date range).
    """
    if df.empty or "ScheduledDateTime" not in df.columns:
        return None

    df = df.copy()
    df["Date"] = df["ScheduledDateTime"].dt.normalize()
    df["TimeHour"] = df["ScheduledDateTime"].dt.hour + df["ScheduledDateTime"].dt.minute / 60

    # Compute end time from Duration (minutes) if available
    if "Duration" in df.columns:
        dur_minutes = pd.to_numeric(df["Duration"], errors="coerce").fillna(0)
        df["EndHour"] = df["TimeHour"] + dur_minutes / 60
    else:
        df["EndHour"] = df["TimeHour"]

    # Filter to weekdays only
    df = df[df["Date"].dt.weekday < 5]

    daily = df.groupby("Date").agg(
        earliest_start=("TimeHour", "min"),
        latest_end=("EndHour", "max"),
    ).reset_index().sort_values("Date")

    # Clamp values to the display range
    daily["earliest_start"] = daily["earliest_start"].clip(lower=6, upper=20)
    daily["latest_end"] = daily["latest_end"].clip(lower=6, upper=20)

    # Build series for hoursRibbon clientside callback
    series = [{
        "name": "Simulations",
        "dates": [d.isoformat() for d in daily["Date"]],
        "startHours": daily["earliest_start"].tolist(),
        "endHours": daily["latest_end"].tolist(),
        "color": PRIMARY,
        "isFuture": False,
    }]

    # Calculate y-axis range
    min_hour = daily["earliest_start"].min()
    max_hour = daily["latest_end"].max()
    y_min = max(0, np.floor(min_hour) - 0.5)
    y_max = min(24, np.ceil(max_hour) + 0.5)

    tickvals = list(range(int(y_min) + 1, int(y_max), 2))
    ticktext = []
    for h in tickvals:
        if h < 12:
            ticktext.append(f"{h}am")
        elif h == 12:
            ticktext.append("12pm")
        else:
            ticktext.append(f"{h - 12}pm")

    return {
        "pastSeries": series,
        "futureSeries": [],
        "yAxis": {
            "min": y_min,
            "max": y_max,
            "tickvals": tickvals,
            "ticktext": ticktext,
        },
        "today": pd.Timestamp.now().normalize().isoformat(),
    }


def _build_type_distribution(df):
    """Horizontal bar chart of counts by ActivityName."""
    if df.empty or "ActivityName" not in df.columns:
        return empty_figure("No sim type data available")

    counts = df["ActivityName"].value_counts().sort_values(ascending=True)

    colors = [CHART_COLORWAY[i % len(CHART_COLORWAY)] for i in range(len(counts))]

    fig = go.Figure(go.Bar(
        x=counts.values,
        y=counts.index,
        orientation="h",
        marker_color=colors,
        text=counts.values,
        textposition="auto",
    ))

    apply_default_layout(fig, height=max(280, len(counts) * 30 + 60))
    fig.update_layout(xaxis_title="Count", yaxis_title="", margin=dict(l=180, r=16, t=16, b=48))
    return fig


def _build_detail_table(df):
    """Build AG Grid table data and column definitions."""
    display_cols = [
        "ScheduledDateTime", "Department", "SupervisingPhysician",
        "ActivityName", "Duration", "PatientFullName",
        "DaysFromClinicExamToSimulation", "DaysFromSimToTreatment",
        "DaysFromClinicExamToTreatment",
    ]

    available_cols = [c for c in display_cols if c in df.columns]

    if not available_cols:
        return [], []

    table_df = df[available_cols].head(200).copy()

    for c in table_df.select_dtypes(include=["datetime64"]).columns:
        table_df[c] = table_df[c].dt.strftime("%m/%d/%Y %I:%M %p")

    table_df = table_df.fillna("\u2014")

    header_map = {
        "ScheduledDateTime": "Scheduled",
        "Department": "Department",
        "SupervisingPhysician": "Physician",
        "ActivityName": "Sim Type",
        "Duration": "Duration (min)",
        "PatientFullName": "Patient",
        "DaysFromClinicExamToSimulation": "Consult\u2192Sim (days)",
        "DaysFromSimToTreatment": "Sim\u2192Tx (days)",
        "DaysFromClinicExamToTreatment": "Consult\u2192Tx (days)",
    }

    col_defs = [{"field": c, "headerName": header_map.get(c, c)} for c in available_cols]

    return table_df.to_dict("records"), col_defs


# ---------------------------------------------------------------------------
# PNG Export callbacks
# ---------------------------------------------------------------------------

clientside_callback(
    """function(n) {
        if (!n) return window.dash_clientside.no_update;
        var wrapper = document.getElementById('sim-chart-volume');
        var graphEl = wrapper ? wrapper.querySelector('.js-plotly-plot') : null;
        if (graphEl) Plotly.downloadImage(graphEl, {format: 'png', width: 1200, height: 600, filename: 'simulation_volume'});
        return window.dash_clientside.no_update;
    }""",
    Output("sim-volume-settings-export", "n_clicks"),
    Input("sim-volume-settings-export", "n_clicks"),
    prevent_initial_call=True,
)

clientside_callback(
    """function(n) {
        if (!n) return window.dash_clientside.no_update;
        var gridApi = window.dash_ag_grid && window.dash_ag_grid['sim-detail-grid'];
        if (gridApi && gridApi.api) gridApi.api.exportDataAsCsv({fileName: 'simulations.csv'});
        return window.dash_clientside.no_update;
    }""",
    Output("sim-table-export", "n_clicks"),
    Input("sim-table-export", "n_clicks"),
    prevent_initial_call=True,
)
