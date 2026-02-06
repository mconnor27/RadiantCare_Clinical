"""Clinic Visits page — visit volumes, lead times, conversion rates, and detail grid."""

import dash
import dash_mantine_components as dmc
import dash_ag_grid as dag
from dash import callback, Input, Output, State, dcc, clientside_callback, ClientsideFunction
import plotly.graph_objects as go
import pandas as pd
import numpy as np
from datetime import timedelta

from config.settings import (
    DEPARTMENTS, DEPARTMENT_COLORS, PHYSICIANS, CHART_COLORWAY,
    PRIMARY, DEFAULT_LAYOUT, FONT_FAMILY, DEFAULT_COLUMN_DEFS, DEFAULT_GRID_OPTIONS,
)
from components.filter_bar import (
    filter_bar, date_presets, department_chips, physician_select, date_range_picker,
)
from components.kpi_card import kpi_card
from components.chart_settings import chart_settings_popover
from utils.charts import apply_default_layout, empty_figure, dept_color

dash.register_page(__name__, path="/clinic-visits", name="Clinic Visits", order=3)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
VISIT_TYPES = ["All", "Consult", "Follow-Up", "Virtual"]
STATUS_OPTIONS = ["Completed", "Cancelled", "All"]


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------
layout = dmc.Stack(
    gap=16,
    className="page-content",
    children=[
        dmc.Title("Clinic Visits", order=2, className="page-title"),

        # Filter bar
        filter_bar("clinic-visits", children=[
            date_presets("clinic-visits"),
            date_range_picker("clinic-visits"),
            department_chips("clinic-visits"),
            physician_select("clinic-visits"),
            dmc.SegmentedControl(
                id="clinic-visits-filter-visit-type",
                data=[{"value": v, "label": v} for v in VISIT_TYPES],
                value="All",
                size="sm",
            ),
            dmc.SegmentedControl(
                id="clinic-visits-filter-status",
                data=[{"value": s, "label": s} for s in STATUS_OPTIONS],
                value="Completed",
                size="sm",
            ),
        ]),

        # KPI row — 6 cards with sparklines
        dmc.Grid(id="cv-kpi-row", gutter="md", children=[
            dmc.GridCol(id="cv-kpi-total", span={"base": 6, "md": 2}),
            dmc.GridCol(id="cv-kpi-consults", span={"base": 6, "md": 2}),
            dmc.GridCol(id="cv-kpi-followups", span={"base": 6, "md": 2}),
            dmc.GridCol(id="cv-kpi-lead-time", span={"base": 6, "md": 2}),
            dmc.GridCol(id="cv-kpi-sim-conversion", span={"base": 6, "md": 2}),
            dmc.GridCol(id="cv-kpi-days-to-sim", span={"base": 6, "md": 2}),
        ]),

        # Row 1: Visit Volume Trend + Lead Time Trend (half-width each)
        dmc.Grid(gutter="md", children=[
            dmc.GridCol(
                dmc.Paper(
                    children=[
                        dmc.Group(
                            justify="space-between", mb="sm",
                            children=[
                                dmc.Text("Visit Volume Trend", size="sm", fw=500, c="#6B7280"),
                                dmc.Group(gap="xs", align="center", children=[
                                    dmc.SegmentedControl(
                                        id="cv-volume-agg",
                                        data=[
                                            {"value": "W", "label": "Weekly"},
                                            {"value": "M", "label": "Monthly"},
                                        ],
                                        value="W",
                                        size="xs",
                                    ),
                                    chart_settings_popover(
                                        "cv-volume",
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
                                    id="cv-volume-loading",
                                    visible=False,
                                    loaderProps={"type": "dots", "color": "#7C2A83"},
                                    overlayProps={"radius": "sm", "blur": 2},
                                ),
                                dcc.Graph(id="cv-chart-volume", config={"displayModeBar": False}),
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
                                dmc.Text("Lead Time Trend (median days)", size="sm", fw=500, c="#6B7280"),
                                chart_settings_popover(
                                    "cv-lead",
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
                                    id="cv-lead-loading",
                                    visible=False,
                                    loaderProps={"type": "dots", "color": "#7C2A83"},
                                    overlayProps={"radius": "sm", "blur": 2},
                                ),
                                dcc.Graph(id="cv-chart-lead-time", config={"displayModeBar": False}),
                            ],
                        ),
                    ],
                    p="md", radius="md", shadow="xs", withBorder=True,
                ),
                span={"base": 12, "md": 6},
            ),
        ]),

        # Row 2: Consult -> Sim Conversion (full width)
        dmc.Paper(
            children=[
                dmc.Group(
                    justify="space-between", mb="sm",
                    children=[
                        dmc.Text("Consult to Simulation Conversion Rate", size="sm", fw=500, c="#6B7280"),
                        chart_settings_popover(
                            "cv-conversion",
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
                            id="cv-conversion-loading",
                            visible=False,
                            loaderProps={"type": "dots", "color": "#7C2A83"},
                            overlayProps={"radius": "sm", "blur": 2},
                        ),
                        dcc.Graph(id="cv-chart-conversion", config={"displayModeBar": False}),
                    ],
                ),
            ],
            p="md", radius="md", shadow="xs", withBorder=True,
        ),

        # Row 3: Cancel Rate (1/3) + Diagnosis Mix (1/3) + Physician Load (1/3)
        dmc.Grid(gutter="md", children=[
            dmc.GridCol(
                dmc.Paper(
                    children=[
                        dmc.Text("Cancel / No-Show Rate", size="sm", fw=500, c="#6B7280", mb="sm"),
                        dmc.Box(
                            pos="relative",
                            children=[
                                dmc.LoadingOverlay(id="cv-cancel-loading", visible=False, loaderProps={"type": "dots", "color": "#7C2A83"}),
                                dcc.Graph(id="cv-chart-cancel-rate", config={"displayModeBar": False}),
                            ],
                        ),
                    ],
                    p="md", radius="md", shadow="xs", withBorder=True,
                ),
                span={"base": 12, "md": 4},
            ),
            dmc.GridCol(
                dmc.Paper(
                    children=[
                        dmc.Text("Diagnosis Mix (Consults)", size="sm", fw=500, c="#6B7280", mb="sm"),
                        dmc.Box(
                            pos="relative",
                            children=[
                                dmc.LoadingOverlay(id="cv-diagnosis-loading", visible=False, loaderProps={"type": "dots", "color": "#7C2A83"}),
                                dcc.Graph(id="cv-chart-diagnosis", config={"displayModeBar": False}),
                            ],
                        ),
                    ],
                    p="md", radius="md", shadow="xs", withBorder=True,
                ),
                span={"base": 12, "md": 4},
            ),
            dmc.GridCol(
                dmc.Paper(
                    children=[
                        dmc.Text("Physician Visit Load", size="sm", fw=500, c="#6B7280", mb="sm"),
                        dmc.Box(
                            pos="relative",
                            children=[
                                dmc.LoadingOverlay(id="cv-physician-loading", visible=False, loaderProps={"type": "dots", "color": "#7C2A83"}),
                                dcc.Graph(id="cv-chart-physician-load", config={"displayModeBar": False}),
                            ],
                        ),
                    ],
                    p="md", radius="md", shadow="xs", withBorder=True,
                ),
                span={"base": 12, "md": 4},
            ),
        ]),

        # Detail table — full width
        dmc.Paper(
            children=[
                dmc.Group(justify="space-between", mb="sm", children=[
                    dmc.Text("Visit Details", size="sm", fw=500, c="#6B7280"),
                    dmc.Button("Export CSV", id="cv-table-export", size="compact-xs", variant="light"),
                ]),
                dag.AgGrid(
                    id="cv-detail-grid",
                    columnDefs=[],
                    rowData=[],
                    defaultColDef=DEFAULT_COLUMN_DEFS,
                    dashGridOptions=DEFAULT_GRID_OPTIONS,
                    style={"height": 400},
                    className="ag-theme-quartz",
                ),
            ],
            p="md", radius="md", shadow="xs", withBorder=True,
        ),

        dcc.Interval(id="cv-interval", interval=300_000, n_intervals=0),

        # Stores for clientside rendering
        dcc.Store(id="cv-store-volume"),
        dcc.Store(id="cv-store-lead"),
        dcc.Store(id="cv-store-conversion"),
        dcc.Store(id="cv-store-kpi-sparklines"),
    ],
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _classify_visit_type(activity_name):
    """Classify a visit based on ActivityName."""
    if pd.isna(activity_name):
        return "Other"
    name = str(activity_name).lower()
    if "virtual" in name or "tele" in name:
        return "Virtual"
    if "consult" in name:
        return "Consult"
    if "follow" in name or "f/u" in name or "fu " in name:
        return "Follow-Up"
    return "Other"


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


def _apply_filters(df, departments, physicians, visit_type, status, start, end):
    """Apply all filter selections to the clinic visits dataframe."""
    if df.empty:
        return df

    dff = df.copy()

    if "ScheduledDateTime" in dff.columns:
        if start is not None:
            dff = dff[dff["ScheduledDateTime"] >= pd.Timestamp(start)]
        if end is not None:
            dff = dff[dff["ScheduledDateTime"] <= pd.Timestamp(end)]

    if departments and "Department" in dff.columns:
        dff = dff[dff["Department"].isin(departments)]

    if physicians and "AppointmentPhysician" in dff.columns:
        dff = dff[dff["AppointmentPhysician"].isin(physicians)]

    if visit_type and visit_type != "All" and "VisitType" in dff.columns:
        dff = dff[dff["VisitType"] == visit_type]

    if status and status != "All" and "Status" in dff.columns:
        dff = dff[dff["Status"].str.contains(status, case=False, na=False)]

    return dff


# ---------------------------------------------------------------------------
# Main Callback
# ---------------------------------------------------------------------------

@callback(
    Output("cv-kpi-total", "children"),
    Output("cv-kpi-consults", "children"),
    Output("cv-kpi-followups", "children"),
    Output("cv-kpi-lead-time", "children"),
    Output("cv-kpi-sim-conversion", "children"),
    Output("cv-kpi-days-to-sim", "children"),
    Output("cv-store-volume", "data"),
    Output("cv-store-lead", "data"),
    Output("cv-store-conversion", "data"),
    Output("cv-chart-cancel-rate", "figure"),
    Output("cv-chart-diagnosis", "figure"),
    Output("cv-chart-physician-load", "figure"),
    Output("cv-detail-grid", "rowData"),
    Output("cv-detail-grid", "columnDefs"),
    Output("cv-store-kpi-sparklines", "data"),
    Input("cv-interval", "n_intervals"),
    Input("cv-volume-agg", "value"),
    Input("clinic-visits-filter-date-preset", "value"),
    Input("clinic-visits-filter-daterange", "value"),
    Input("clinic-visits-filter-department", "value"),
    Input("clinic-visits-filter-physician", "value"),
    Input("clinic-visits-filter-visit-type", "value"),
    Input("clinic-visits-filter-status", "value"),
    running=[
        (Output("cv-volume-loading", "visible"), True, False),
        (Output("cv-lead-loading", "visible"), True, False),
        (Output("cv-conversion-loading", "visible"), True, False),
        (Output("cv-cancel-loading", "visible"), True, False),
        (Output("cv-diagnosis-loading", "visible"), True, False),
        (Output("cv-physician-loading", "visible"), True, False),
    ],
)
def update_clinic_visits(_n, agg, date_preset, date_range, departments, physicians, visit_type, status):
    from data.loader import load_clinic_visits

    na_kpi = kpi_card("--", "N/A")
    empty = empty_figure()

    try:
        df = load_clinic_visits()
    except Exception:
        return (na_kpi,) * 6 + (None, None, None, empty, empty, empty, [], [], {})

    if df.empty:
        return (na_kpi,) * 6 + (None, None, None, empty, empty, empty, [], [], {})

    # Classify visit types
    if "ActivityName" in df.columns:
        df["VisitType"] = df["ActivityName"].apply(_classify_visit_type)
    else:
        df["VisitType"] = "Other"

    # Get date range
    last_date = df["ScheduledDateTime"].max() if "ScheduledDateTime" in df.columns else pd.Timestamp.now().normalize()
    start, end = _get_date_range(date_preset, date_range, last_date)

    # Apply filters
    dff = _apply_filters(df, departments, physicians, visit_type, status, start, end)
    dff_all_status = _apply_filters(df, departments, physicians, visit_type, "All", start, end)

    sparkline_data = {}

    # ------------------------------------------------------------------
    # KPIs with sparklines
    # ------------------------------------------------------------------
    total_visits = len(dff)
    consult_count = len(dff[dff["VisitType"] == "Consult"]) if "VisitType" in dff.columns else 0
    followup_count = len(dff[dff["VisitType"] == "Follow-Up"]) if "VisitType" in dff.columns else 0

    # Build visit count sparklines
    if "ScheduledDateTime" in dff.columns:
        dff_temp = dff.copy()
        dff_temp["week"] = dff_temp["ScheduledDateTime"].dt.to_period("W").dt.to_timestamp()
        weekly = dff_temp.groupby("week").size()
        if len(weekly) > 2:
            sparkline_data["total"] = {
                "labels": [d.isoformat() for d in weekly.index],
                "values": weekly.tolist(),
                "color": PRIMARY,
            }
        # Consults weekly
        consults_weekly = dff_temp[dff_temp["VisitType"] == "Consult"].groupby("week").size()
        if len(consults_weekly) > 2:
            sparkline_data["consults"] = {
                "labels": [d.isoformat() for d in consults_weekly.index],
                "values": consults_weekly.tolist(),
                "color": CHART_COLORWAY[0],
            }
        # Follow-ups weekly
        followups_weekly = dff_temp[dff_temp["VisitType"] == "Follow-Up"].groupby("week").size()
        if len(followups_weekly) > 2:
            sparkline_data["followups"] = {
                "labels": [d.isoformat() for d in followups_weekly.index],
                "values": followups_weekly.tolist(),
                "color": CHART_COLORWAY[1],
            }

    kpi_total = kpi_card("Total Visits", f"{total_visits:,}", accent_color=PRIMARY, sparkline_id="cv-spark-total")
    kpi_consults = kpi_card("Consults", f"{consult_count:,}", accent_color=CHART_COLORWAY[0], sparkline_id="cv-spark-consults")
    kpi_followups = kpi_card("Follow-Ups", f"{followup_count:,}", accent_color=CHART_COLORWAY[1], sparkline_id="cv-spark-followups")

    # Lead time
    if "DaysFromCreatedToAppt" in dff.columns:
        lead_vals = pd.to_numeric(dff["DaysFromCreatedToAppt"], errors="coerce").dropna()
        lead_time_str = f"{lead_vals.median():.0f}" if len(lead_vals) > 0 else "N/A"
    else:
        lead_time_str = "N/A"
    kpi_lead = kpi_card("Lead Time (median days)", lead_time_str, accent_color=CHART_COLORWAY[2])

    # Sim conversion rate
    consults_df = dff[dff["VisitType"] == "Consult"] if "VisitType" in dff.columns else pd.DataFrame()
    if "HasSimulationWithin180Days" in consults_df.columns and len(consults_df) > 0:
        sim_flag = pd.to_numeric(consults_df["HasSimulationWithin180Days"], errors="coerce").fillna(0)
        sim_rate = sim_flag.mean() * 100
        sim_rate_str = f"{sim_rate:.1f}%"
    else:
        sim_rate_str = "N/A"
    kpi_sim_conv = kpi_card("Sim Conversion Rate", sim_rate_str, accent_color=CHART_COLORWAY[3])

    # Median days to sim
    if "DaysToSimulation" in consults_df.columns and len(consults_df) > 0:
        days_sim = pd.to_numeric(consults_df["DaysToSimulation"], errors="coerce").dropna()
        days_sim_str = f"{days_sim.median():.0f}" if len(days_sim) > 0 else "N/A"
    else:
        days_sim_str = "N/A"
    kpi_days_sim = kpi_card("Median Days to Sim", days_sim_str, accent_color=CHART_COLORWAY[4])

    # ------------------------------------------------------------------
    # Prepare data for clientside charts
    # ------------------------------------------------------------------
    volume_data = _prepare_volume_data(dff, agg)
    lead_data = _prepare_lead_data(dff, departments)
    conversion_data = _prepare_conversion_data(dff, departments)

    # Server-side charts (simpler)
    fig_cancel = _build_cancel_rate(dff_all_status)
    fig_diagnosis = _build_diagnosis_mix(dff)
    fig_physician = _build_physician_load(dff)

    # ------------------------------------------------------------------
    # Detail table
    # ------------------------------------------------------------------
    row_data, col_defs = _build_detail_table(dff)

    return (
        kpi_total, kpi_consults, kpi_followups, kpi_lead, kpi_sim_conv, kpi_days_sim,
        volume_data, lead_data, conversion_data,
        fig_cancel, fig_diagnosis, fig_physician,
        row_data, col_defs, sparkline_data,
    )


# ---------------------------------------------------------------------------
# Clientside callbacks for charts
# ---------------------------------------------------------------------------

clientside_callback(
    ClientsideFunction(namespace="census", function_name="smoothChartWithType"),
    Output("cv-chart-volume", "figure"),
    Input("cv-store-volume", "data"),
    Input("cv-volume-settings-smooth", "value"),
    Input("cv-volume-settings-type", "value"),
    State("cv-chart-volume", "figure"),
)

clientside_callback(
    ClientsideFunction(namespace="census", function_name="smoothChartWithType"),
    Output("cv-chart-lead-time", "figure"),
    Input("cv-store-lead", "data"),
    Input("cv-lead-settings-smooth", "value"),
    Input("cv-lead-settings-type", "value"),
    State("cv-chart-lead-time", "figure"),
)

clientside_callback(
    ClientsideFunction(namespace="census", function_name="smoothChartWithType"),
    Output("cv-chart-conversion", "figure"),
    Input("cv-store-conversion", "data"),
    Input("cv-conversion-settings-smooth", "value"),
    Input("cv-conversion-settings-type", "value"),
    State("cv-chart-conversion", "figure"),
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
    Output("cv-spark-total", "figure"),
    Input("cv-store-kpi-sparklines", "data"),
    Input("clinic-visits-filter-date-preset", "value"),
)

clientside_callback(
    """function(data, _trigger) {
        if (!data || !data.consults) return window.dash_clientside.no_update;
        var spark = data.consults;
        return {
            data: [{x: spark.labels, y: spark.values, mode: "lines", line: {color: spark.color, width: 1.5}}],
            layout: {margin: {l: 0, r: 0, t: 0, b: 0}, height: 34, plot_bgcolor: "rgba(0,0,0,0)", paper_bgcolor: "rgba(0,0,0,0)", xaxis: {visible: false}, yaxis: {visible: false}, showlegend: false, hovermode: "x"}
        };
    }""",
    Output("cv-spark-consults", "figure"),
    Input("cv-store-kpi-sparklines", "data"),
    Input("clinic-visits-filter-date-preset", "value"),
)

clientside_callback(
    """function(data, _trigger) {
        if (!data || !data.followups) return window.dash_clientside.no_update;
        var spark = data.followups;
        return {
            data: [{x: spark.labels, y: spark.values, mode: "lines", line: {color: spark.color, width: 1.5}}],
            layout: {margin: {l: 0, r: 0, t: 0, b: 0}, height: 34, plot_bgcolor: "rgba(0,0,0,0)", paper_bgcolor: "rgba(0,0,0,0)", xaxis: {visible: false}, yaxis: {visible: false}, showlegend: false, hovermode: "x"}
        };
    }""",
    Output("cv-spark-followups", "figure"),
    Input("cv-store-kpi-sparklines", "data"),
    Input("clinic-visits-filter-date-preset", "value"),
)


# ---------------------------------------------------------------------------
# Settings panel toggles
# ---------------------------------------------------------------------------

@callback(Output("cv-volume-settings-panel", "style"), Input("cv-volume-settings-btn", "n_clicks"), State("cv-volume-settings-panel", "style"), prevent_initial_call=True)
def toggle_volume_settings(n, style):
    if not n: return style
    return {"display": "block"} if (style or {}).get("display") == "none" else {"display": "none"}

@callback(Output("cv-lead-settings-panel", "style"), Input("cv-lead-settings-btn", "n_clicks"), State("cv-lead-settings-panel", "style"), prevent_initial_call=True)
def toggle_lead_settings(n, style):
    if not n: return style
    return {"display": "block"} if (style or {}).get("display") == "none" else {"display": "none"}

@callback(Output("cv-conversion-settings-panel", "style"), Input("cv-conversion-settings-btn", "n_clicks"), State("cv-conversion-settings-panel", "style"), prevent_initial_call=True)
def toggle_conversion_settings(n, style):
    if not n: return style
    return {"display": "block"} if (style or {}).get("display") == "none" else {"display": "none"}


# ---------------------------------------------------------------------------
# Data preparation for clientside charts
# ---------------------------------------------------------------------------

def _prepare_volume_data(dff, agg):
    """Prepare volume trend data for clientside rendering."""
    if dff.empty or "ScheduledDateTime" not in dff.columns:
        return None

    dff = dff.copy()
    dff["period"] = dff["ScheduledDateTime"].dt.to_period(agg).dt.to_timestamp()

    type_colors = {
        "Consult": CHART_COLORWAY[0],
        "Follow-Up": CHART_COLORWAY[1],
        "Virtual": CHART_COLORWAY[3],
        "Other": CHART_COLORWAY[4],
    }

    all_periods = sorted(dff["period"].unique())
    dates = [d.isoformat() for d in all_periods]

    series = []
    for vtype in ["Consult", "Follow-Up", "Virtual", "Other"]:
        subset = dff[dff["VisitType"] == vtype]
        if subset.empty:
            continue
        counts = subset.groupby("period").size().reindex(all_periods, fill_value=0)
        series.append({
            "name": vtype,
            "values": counts.tolist(),
            "color": type_colors.get(vtype, CHART_COLORWAY[5]),
        })

    return {"dates": dates, "series": series, "height": 350, "yTitle": "Visits"}


def _prepare_lead_data(dff, departments):
    """Prepare lead time trend data."""
    if dff.empty or "ScheduledDateTime" not in dff.columns or "DaysFromCreatedToAppt" not in dff.columns:
        return None

    dff = dff.copy()
    dff["DaysFromCreatedToAppt"] = pd.to_numeric(dff["DaysFromCreatedToAppt"], errors="coerce")
    dff = dff.dropna(subset=["DaysFromCreatedToAppt"])
    dff["month"] = dff["ScheduledDateTime"].dt.to_period("M").dt.to_timestamp()

    if dff.empty:
        return None

    all_months = sorted(dff["month"].unique())
    dates = [d.isoformat() for d in all_months]

    series = []
    active_depts = dff["Department"].unique() if "Department" in dff.columns else []
    for dept in (departments or DEPARTMENTS):
        if dept not in active_depts:
            continue
        dept_data = dff[dff["Department"] == dept]
        monthly = dept_data.groupby("month")["DaysFromCreatedToAppt"].median().reindex(all_months, fill_value=0)
        series.append({
            "name": dept,
            "values": monthly.tolist(),
            "color": dept_color(dept),
        })

    return {"dates": dates, "series": series, "height": 350, "yTitle": "Median Lead Time (days)"}


def _prepare_conversion_data(dff, departments):
    """Prepare conversion rate data."""
    consults = dff[dff["VisitType"] == "Consult"].copy() if "VisitType" in dff.columns else pd.DataFrame()

    if consults.empty or "HasSimulationWithin180Days" not in consults.columns:
        return None

    consults["HasSimulationWithin180Days"] = pd.to_numeric(consults["HasSimulationWithin180Days"], errors="coerce").fillna(0)
    consults["month"] = consults["ScheduledDateTime"].dt.to_period("M").dt.to_timestamp()

    all_months = sorted(consults["month"].unique())
    dates = [d.isoformat() for d in all_months]

    # Overall line
    monthly_all = consults.groupby("month")["HasSimulationWithin180Days"].mean().reindex(all_months, fill_value=0) * 100

    series = [{
        "name": "Overall",
        "values": monthly_all.tolist(),
        "color": "#1A1A2E",
    }]

    # Per-department lines
    active_depts = consults["Department"].unique() if "Department" in consults.columns else []
    for dept in (departments or DEPARTMENTS):
        if dept not in active_depts:
            continue
        dept_data = consults[consults["Department"] == dept]
        monthly_dept = dept_data.groupby("month")["HasSimulationWithin180Days"].mean().reindex(all_months, fill_value=0) * 100
        series.append({
            "name": dept,
            "values": monthly_dept.tolist(),
            "color": dept_color(dept),
        })

    return {"dates": dates, "series": series, "height": 350, "yTitle": "Conversion Rate (%)"}


# ---------------------------------------------------------------------------
# Server-side chart builders
# ---------------------------------------------------------------------------

def _build_cancel_rate(dff_all):
    """Monthly percentage of cancelled visits."""
    if dff_all.empty or "Status" not in dff_all.columns or "ScheduledDateTime" not in dff_all.columns:
        return empty_figure("Cancel rate data unavailable")

    dff = dff_all.copy()
    dff["month"] = dff["ScheduledDateTime"].dt.to_period("M").dt.to_timestamp()

    monthly_total = dff.groupby("month").size().reset_index(name="total")
    cancelled = dff[dff["Status"].str.lower().str.contains("cancel|no-show|no show", na=False)]
    monthly_cancel = cancelled.groupby("month").size().reset_index(name="cancelled")

    merged = monthly_total.merge(monthly_cancel, on="month", how="left").fillna(0)
    merged["rate"] = (merged["cancelled"] / merged["total"]) * 100

    fig = go.Figure(go.Bar(
        x=merged["month"], y=merged["rate"],
        marker_color=CHART_COLORWAY[2],
        hovertemplate="Month: %{x}<br>Cancel Rate: %{y:.1f}%<extra></extra>",
    ))

    apply_default_layout(fig, height=280)
    fig.update_layout(xaxis_title="Month", yaxis_title="Cancel / No-Show %", margin=dict(l=48, r=16, t=16, b=48))
    return fig


def _build_diagnosis_mix(dff):
    """Horizontal bar chart of consults by diagnosis group."""
    consults = dff[dff["VisitType"] == "Consult"] if "VisitType" in dff.columns else dff

    diag_col = None
    for candidate in ["DiagnosisGroup", "Diagnosis", "DiagnosisCode", "PrimaryDiagnosis"]:
        if candidate in consults.columns:
            diag_col = candidate
            break

    if diag_col is None or consults.empty:
        return empty_figure("Diagnosis data unavailable")

    counts = consults[diag_col].value_counts().head(12)
    if counts.empty:
        return empty_figure("No diagnosis data")

    counts = counts.sort_values(ascending=True)

    fig = go.Figure(go.Bar(
        x=counts.values,
        y=counts.index.astype(str),
        orientation="h",
        marker_color=CHART_COLORWAY[0],
    ))

    apply_default_layout(fig, height=280)
    fig.update_layout(xaxis_title="Consult Count", yaxis_title="", margin=dict(l=140, r=16, t=16, b=48))
    return fig


def _build_physician_load(dff):
    """Grouped bar chart per physician showing consult vs follow-up counts."""
    if dff.empty or "AppointmentPhysician" not in dff.columns or "VisitType" not in dff.columns:
        return empty_figure("Physician load data unavailable")

    consults = dff[dff["VisitType"] == "Consult"]
    followups = dff[dff["VisitType"] == "Follow-Up"]

    consult_counts = consults.groupby("AppointmentPhysician").size()
    followup_counts = followups.groupby("AppointmentPhysician").size()

    all_physicians = sorted(set(consult_counts.index) | set(followup_counts.index))
    if not all_physicians:
        return empty_figure("No physician visit data")

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=[p.split(",")[0] for p in all_physicians],
        y=[consult_counts.get(p, 0) for p in all_physicians],
        name="Consult",
        marker_color=CHART_COLORWAY[0],
    ))
    fig.add_trace(go.Bar(
        x=[p.split(",")[0] for p in all_physicians],
        y=[followup_counts.get(p, 0) for p in all_physicians],
        name="Follow-Up",
        marker_color=CHART_COLORWAY[1],
    ))

    apply_default_layout(fig, barmode="group", height=280)
    fig.update_layout(xaxis_title="", yaxis_title="Visits", margin=dict(l=48, r=16, t=16, b=60), xaxis_tickangle=-30)
    return fig


def _build_detail_table(dff):
    """Build the AG Grid detail table."""
    if dff.empty:
        return [], []

    col_header_map = {
        "PatientFullName": "Patient",
        "ScheduledDateTime": "Scheduled",
        "Department": "Department",
        "AppointmentPhysician": "Physician",
        "VisitType": "Visit Type",
        "Status": "Status",
        "DaysFromCreatedToAppt": "Lead Time (days)",
        "HasSimulationWithin180Days": "Has Sim",
        "DaysToSimulation": "Days to Sim",
    }

    display_cols = [col for col in col_header_map if col in dff.columns]
    if not display_cols:
        return [], []

    table_df = dff[display_cols].head(500).copy()
    for c in table_df.select_dtypes(include=["datetime64"]).columns:
        table_df[c] = table_df[c].dt.strftime("%m/%d/%Y %I:%M %p")
    table_df = table_df.fillna("--")

    col_defs = [{"field": c, "headerName": col_header_map.get(c, c)} for c in display_cols]

    return table_df.to_dict("records"), col_defs


# ---------------------------------------------------------------------------
# PNG Export callbacks
# ---------------------------------------------------------------------------

clientside_callback(
    """function(n) {
        if (!n) return window.dash_clientside.no_update;
        var wrapper = document.getElementById('cv-chart-volume');
        var graphEl = wrapper ? wrapper.querySelector('.js-plotly-plot') : null;
        if (graphEl) Plotly.downloadImage(graphEl, {format: 'png', width: 1200, height: 600, filename: 'visit_volume'});
        return window.dash_clientside.no_update;
    }""",
    Output("cv-volume-settings-export", "n_clicks"),
    Input("cv-volume-settings-export", "n_clicks"),
    prevent_initial_call=True,
)

clientside_callback(
    """function(n) {
        if (!n) return window.dash_clientside.no_update;
        var gridApi = window.dash_ag_grid && window.dash_ag_grid['cv-detail-grid'];
        if (gridApi && gridApi.api) gridApi.api.exportDataAsCsv({fileName: 'clinic_visits.csv'});
        return window.dash_clientside.no_update;
    }""",
    Output("cv-table-export", "n_clicks"),
    Input("cv-table-export", "n_clicks"),
    prevent_initial_call=True,
)
