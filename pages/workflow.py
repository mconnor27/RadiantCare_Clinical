"""Workflow page — Sankey pipeline, stage duration violins, pipeline trend."""

import dash
import dash_mantine_components as dmc
from dash import callback, Input, Output, State, dcc, clientside_callback, ClientsideFunction
import dash_ag_grid as dag
import plotly.graph_objects as go
import pandas as pd
import numpy as np
from datetime import timedelta

from config.settings import CHART_COLORWAY, DEFAULT_LAYOUT, FONT_FAMILY, PRIMARY
from components.filter_bar import (
    filter_bar, date_presets, department_chips, physician_select, date_range_picker,
)
from components.kpi_card import kpi_card
from components.chart_settings import chart_settings_popover
from utils.charts import apply_default_layout, empty_figure

dash.register_page(__name__, path="/workflow", name="Workflow", order=2)

# Stage definitions
STAGES = ["Consult", "Simulation", "Draw Volumes", "Isodose Plan", "Review Plan", "First Treatment"]
STAGE_DATE_COLS = [
    "ScheduledDateTime", "SimulationDate", "DrawVolumesCompletedDate",
    "IsodosePlanCompletedDate", "ReviewPlanCompletedDate", "FirstTreatmentDate",
]
INTER_STAGE_LABELS = ["Consult→Sim", "Sim→Draw", "Draw→Isodose", "Isodose→Review", "Review→Treatment"]


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
                dmc.Title("Workflow", order=2, className="page-title"),
                filter_bar("workflow", children=[
                    date_presets("workflow"),
                    date_range_picker("workflow"),
                    department_chips("workflow"),
                    physician_select("workflow"),
                    dmc.MultiSelect(
                        id="workflow-filter-diagnosis",
                        placeholder="Diagnosis",
                        data=[],
                        clearable=True,
                        size="sm",
                        w=200,
                    ),
                ]),
            ],
        ),

        # KPI row — 4 cards with sparklines
        dmc.Grid(id="wf-kpi-row", gutter="md", children=[
            dmc.GridCol(id="wf-kpi-consult-sim", span={"base": 6, "md": 3}),
            dmc.GridCol(id="wf-kpi-sim-tx", span={"base": 6, "md": 3}),
            dmc.GridCol(id="wf-kpi-total", span={"base": 6, "md": 3}),
            dmc.GridCol(id="wf-kpi-pipeline", span={"base": 6, "md": 3}),
        ]),

        # Sankey — full width
        dmc.Paper(
            children=[
                dmc.Group(
                    justify="space-between", mb="sm",
                    children=[
                        dmc.Text("Patient Treatment Pipeline", size="sm", fw=500, c="#6B7280"),
                    ],
                ),
                dmc.Box(
                    pos="relative",
                    children=[
                        dmc.LoadingOverlay(
                            id="wf-sankey-loading",
                            visible=False,
                            loaderProps={"type": "dots", "color": "#7C2A83"},
                            overlayProps={"radius": "sm", "blur": 2},
                        ),
                        dcc.Graph(id="wf-chart-sankey", config={"displayModeBar": False}),
                    ],
                ),
            ],
            p="md", radius="md", shadow="xs", withBorder=True,
        ),

        # Violin + Trend side by side
        dmc.Grid(gutter="md", children=[
            dmc.GridCol(
                dmc.Paper(
                    children=[
                        dmc.Text("Stage Duration (days)", size="sm", fw=500, c="#6B7280", mb="sm"),
                        dmc.Box(
                            pos="relative",
                            children=[
                                dmc.LoadingOverlay(
                                    id="wf-violin-loading",
                                    visible=False,
                                    loaderProps={"type": "dots", "color": "#7C2A83"},
                                    overlayProps={"radius": "sm", "blur": 2},
                                ),
                                dcc.Graph(id="wf-chart-violin", config={"displayModeBar": False}),
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
                                dmc.Text("Pipeline Trend (monthly median)", size="sm", fw=500, c="#6B7280"),
                                chart_settings_popover(
                                    "wf-trend",
                                    chart_types=[
                                        {"value": "line", "label": "Line"},
                                        {"value": "area", "label": "Area"},
                                    ],
                                    show_smooth=True,
                                    smooth_max=12,
                                    smooth_default=3,
                                ),
                            ],
                        ),
                        dmc.Box(
                            pos="relative",
                            children=[
                                dmc.LoadingOverlay(
                                    id="wf-trend-loading",
                                    visible=False,
                                    loaderProps={"type": "dots", "color": "#7C2A83"},
                                    overlayProps={"radius": "sm", "blur": 2},
                                ),
                                dcc.Graph(id="wf-chart-trend", config={"displayModeBar": False}),
                            ],
                        ),
                    ],
                    p="md", radius="md", shadow="xs", withBorder=True,
                ),
                span={"base": 12, "md": 6},
            ),
        ]),

        # Detail table
        dmc.Paper(
            children=[
                dmc.Group(justify="space-between", mb="sm", children=[
                    dmc.Text("Patient Pipeline Detail", size="sm", fw=500, c="#6B7280"),
                    dmc.Button(
                        "Export CSV",
                        id="wf-table-export",
                        size="compact-xs",
                        variant="light",
                    ),
                ]),
                dag.AgGrid(
                    id="wf-detail-grid",
                    columnDefs=[],
                    rowData=[],
                    defaultColDef={"sortable": True, "filter": True, "resizable": True},
                    dashGridOptions={"pagination": True, "paginationPageSize": 25},
                    style={"height": 400},
                    className="ag-theme-quartz",
                ),
            ],
            p="md", radius="md", shadow="xs", withBorder=True,
        ),

        dcc.Interval(id="wf-interval", interval=300_000, n_intervals=0),

        # Stores for clientside rendering
        dcc.Store(id="wf-store-trend"),
        dcc.Store(id="wf-store-kpi-sparklines"),
    ],
)


# ---------------------------------------------------------------------------
# Helper: Date Range
# ---------------------------------------------------------------------------

def _get_date_range(date_preset, daterange, last_date):
    """Calculate start/end based on preset or explicit range."""
    if daterange and len(daterange) == 2 and daterange[0] and daterange[1]:
        return pd.Timestamp(daterange[0]), pd.Timestamp(daterange[1])
    elif date_preset == "ytd":
        return pd.Timestamp(last_date.year, 1, 1), last_date
    elif date_preset == "12mo":
        return last_date - timedelta(days=365), last_date
    else:
        return pd.Timestamp("2020-01-01"), last_date


# ---------------------------------------------------------------------------
# Callbacks
# ---------------------------------------------------------------------------

@callback(
    Output("workflow-filter-diagnosis", "data"),
    Input("wf-interval", "n_intervals"),
)
def populate_diagnosis_options(_n):
    """Populate diagnosis filter with unique values from workflow data."""
    try:
        from data.loader import load_workflow
        wf = load_workflow()
        if "DiagnosisDescriptions" in wf.columns:
            diags = sorted(wf["DiagnosisDescriptions"].dropna().unique().tolist())
            return [{"value": d, "label": d} for d in diags[:100]]
    except Exception:
        pass
    return []


@callback(
    Output("wf-kpi-consult-sim", "children"),
    Output("wf-kpi-sim-tx", "children"),
    Output("wf-kpi-total", "children"),
    Output("wf-kpi-pipeline", "children"),
    Output("wf-chart-sankey", "figure"),
    Output("wf-chart-violin", "figure"),
    Output("wf-store-trend", "data"),
    Output("wf-detail-grid", "rowData"),
    Output("wf-detail-grid", "columnDefs"),
    Output("wf-store-kpi-sparklines", "data"),
    Input("wf-interval", "n_intervals"),
    Input("workflow-filter-department", "value"),
    Input("workflow-filter-date-preset", "value"),
    Input("workflow-filter-daterange", "value"),
    Input("workflow-filter-physician", "value"),
    Input("workflow-filter-diagnosis", "value"),
    running=[
        (Output("wf-sankey-loading", "visible"), True, False),
        (Output("wf-violin-loading", "visible"), True, False),
        (Output("wf-trend-loading", "visible"), True, False),
    ],
)
def update_workflow(_n, departments, date_preset, daterange, physicians, diagnosis):
    from data.loader import load_workflow

    try:
        wf = load_workflow()
    except Exception:
        empty = empty_figure("Workflow data unavailable")
        na = kpi_card("—", "N/A")
        return na, na, na, na, empty, empty, None, [], [], {}

    if wf.empty:
        empty = empty_figure("No workflow data")
        na = kpi_card("—", "N/A")
        return na, na, na, na, empty, empty, None, [], [], {}

    # Get date range
    last_date = wf["ScheduledDateTime"].max() if "ScheduledDateTime" in wf.columns else pd.Timestamp.now().normalize()
    start, end = _get_date_range(date_preset, daterange, last_date)

    # Apply filters
    if departments and "Department" in wf.columns:
        wf = wf[wf["Department"].isin(departments)]

    if physicians:
        phys_col = next((c for c in ["TreatingPhysician", "AppointmentPhysician"] if c in wf.columns), None)
        if phys_col:
            wf = wf[wf[phys_col].isin(physicians)]

    if diagnosis and "DiagnosisDescriptions" in wf.columns:
        wf = wf[wf["DiagnosisDescriptions"].isin(diagnosis)]

    if "ScheduledDateTime" in wf.columns:
        wf_period = wf[(wf["ScheduledDateTime"] >= start) & (wf["ScheduledDateTime"] <= end)]
    else:
        wf_period = wf

    sparkline_data = {}

    # --- KPIs with sparklines ---
    def safe_median(col):
        if col in wf_period.columns:
            vals = pd.to_numeric(wf_period[col], errors="coerce").dropna()
            return vals.median() if len(vals) > 0 else None
        return None

    def build_sparkline(col, color):
        if col not in wf_period.columns or "ScheduledDateTime" not in wf_period.columns:
            return None
        temp = wf_period[["ScheduledDateTime", col]].copy()
        temp[col] = pd.to_numeric(temp[col], errors="coerce")
        temp = temp.dropna()
        if temp.empty:
            return None
        temp["month"] = temp["ScheduledDateTime"].dt.to_period("M").dt.to_timestamp()
        monthly = temp.groupby("month")[col].median()
        return {
            "labels": [d.isoformat() for d in monthly.index],
            "values": monthly.tolist(),
            "color": color,
        }

    cs_median = safe_median("DaysToSimulation")
    cs_spark = build_sparkline("DaysToSimulation", CHART_COLORWAY[0])
    if cs_spark:
        sparkline_data["consult_sim"] = cs_spark
    kpi_cs = kpi_card(
        "Consult→Sim (median days)",
        f"{cs_median:.0f}" if cs_median else "N/A",
        accent_color=CHART_COLORWAY[0],
        sparkline_id="wf-spark-consult-sim",
    )

    st_median = safe_median("DaysFromReviewToTreatment")
    st_spark = build_sparkline("DaysFromReviewToTreatment", CHART_COLORWAY[1])
    if st_spark:
        sparkline_data["sim_tx"] = st_spark
    kpi_st = kpi_card(
        "Review→Tx (median days)",
        f"{st_median:.0f}" if st_median else "N/A",
        accent_color=CHART_COLORWAY[1],
        sparkline_id="wf-spark-sim-tx",
    )

    # Total pipeline
    if "ScheduledDateTime" in wf_period.columns and "FirstTreatmentDate" in wf_period.columns:
        wf_period = wf_period.copy()
        wf_period["total_days"] = (wf_period["FirstTreatmentDate"] - wf_period["ScheduledDateTime"]).dt.days
        total_days = wf_period["total_days"].dropna()
        total_median = total_days.median() if len(total_days) > 0 else None
        if not total_days.empty:
            wf_period["month"] = wf_period["ScheduledDateTime"].dt.to_period("M").dt.to_timestamp()
            monthly_total = wf_period.groupby("month")["total_days"].median()
            sparkline_data["total"] = {
                "labels": [d.isoformat() for d in monthly_total.index],
                "values": monthly_total.tolist(),
                "color": CHART_COLORWAY[2],
            }
    else:
        total_median = None
    kpi_total = kpi_card(
        "Total Pipeline (median days)",
        f"{total_median:.0f}" if total_median else "N/A",
        accent_color=CHART_COLORWAY[2],
        sparkline_id="wf-spark-total",
    )

    pipeline_count = len(wf_period[wf_period["FirstTreatmentDate"].isna()]) if "FirstTreatmentDate" in wf_period.columns else 0
    kpi_pipe = kpi_card("In Pipeline", str(pipeline_count), accent_color=PRIMARY)

    # --- Charts ---
    fig_sankey = _build_sankey(wf_period)
    fig_violin = _build_violin(wf_period)
    trend_data = _prepare_trend_data(wf_period)

    # --- Detail table ---
    row_data, col_defs = _build_table_data(wf_period)

    return kpi_cs, kpi_st, kpi_total, kpi_pipe, fig_sankey, fig_violin, trend_data, row_data, col_defs, sparkline_data


# ---------------------------------------------------------------------------
# Clientside callbacks for sparklines
# ---------------------------------------------------------------------------

clientside_callback(
    """function(data, _trigger) {
        if (!data || !data.consult_sim) return window.dash_clientside.no_update;
        var spark = data.consult_sim;
        return {
            data: [{x: spark.labels, y: spark.values, mode: "lines", line: {color: spark.color, width: 1.5}}],
            layout: {margin: {l: 0, r: 0, t: 0, b: 0}, height: 34, plot_bgcolor: "rgba(0,0,0,0)", paper_bgcolor: "rgba(0,0,0,0)", xaxis: {visible: false}, yaxis: {visible: false}, showlegend: false, hovermode: "x"}
        };
    }""",
    Output("wf-spark-consult-sim", "figure"),
    Input("wf-store-kpi-sparklines", "data"),
    Input("workflow-filter-date-preset", "value"),
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
    Output("wf-spark-sim-tx", "figure"),
    Input("wf-store-kpi-sparklines", "data"),
    Input("workflow-filter-date-preset", "value"),
)

clientside_callback(
    """function(data, _trigger) {
        if (!data || !data.total) return window.dash_clientside.no_update;
        var spark = data.total;
        return {
            data: [{x: spark.labels, y: spark.values, mode: "lines", line: {color: spark.color, width: 1.5}}],
            layout: {margin: {l: 0, r: 0, t: 0, b: 0}, height: 34, plot_bgcolor: "rgba(0,0,0,0)", paper_bgcolor: "rgba(0,0,0,0)", xaxis: {visible: false}, yaxis: {visible: false}, showlegend: false, hovermode: "x"}
        };
    }""",
    Output("wf-spark-total", "figure"),
    Input("wf-store-kpi-sparklines", "data"),
    Input("workflow-filter-date-preset", "value"),
)


# ---------------------------------------------------------------------------
# Clientside callback for trend chart
# ---------------------------------------------------------------------------

clientside_callback(
    ClientsideFunction(namespace="census", function_name="smoothChartWithType"),
    Output("wf-chart-trend", "figure"),
    Input("wf-store-trend", "data"),
    Input("wf-trend-settings-smooth", "value"),
    Input("wf-trend-settings-type", "value"),
    State("wf-chart-trend", "figure"),
)


# ---------------------------------------------------------------------------
# Settings panel toggle
# ---------------------------------------------------------------------------

@callback(
    Output("wf-trend-settings-panel", "style"),
    Input("wf-trend-settings-btn", "n_clicks"),
    State("wf-trend-settings-panel", "style"),
    prevent_initial_call=True,
)
def toggle_trend_settings(n, style):
    if not n:
        return style
    current = style or {}
    is_hidden = current.get("display") == "none"
    return {"display": "block"} if is_hidden else {"display": "none"}


# ---------------------------------------------------------------------------
# Chart builders
# ---------------------------------------------------------------------------

def _build_sankey(wf):
    """Build a Sankey diagram of the treatment pipeline."""
    if wf.empty:
        return empty_figure("No workflow data")

    stage_cols = [c for c in STAGE_DATE_COLS if c in wf.columns]
    if len(stage_cols) < 2:
        return empty_figure("Insufficient workflow columns")

    n_stages = len(stage_cols)
    total_consults = int(wf[stage_cols[0]].notna().sum())
    if total_consults == 0:
        return empty_figure("No consult data")

    # Build node labels with counts and percentages
    node_labels = []
    node_colors = []
    for i, col in enumerate(stage_cols):
        count = int(wf[col].notna().sum())
        pct = count / total_consults * 100
        stage_name = STAGES[i] if i < len(STAGES) else f"Stage {i}"
        node_labels.append(f"{stage_name}\n{count:,} ({pct:.0f}%)")
        node_colors.append(CHART_COLORWAY[i % len(CHART_COLORWAY)])

    # Add single "Pending" node
    pending_idx = n_stages
    node_labels.append("Pending")
    node_colors.append("#D1D5DB")

    sources, targets, values, link_colors = [], [], [], []

    for i in range(n_stages - 1):
        reached_current = wf[stage_cols[i]].notna()
        reached_next = wf[stage_cols[i + 1]].notna()
        progressed = int((reached_current & reached_next).sum())
        pending = int((reached_current & ~reached_next).sum())

        if progressed > 0:
            sources.append(i)
            targets.append(i + 1)
            values.append(progressed)
            c = CHART_COLORWAY[i % len(CHART_COLORWAY)]
            hex_c = c.lstrip("#")
            r, g, b = int(hex_c[0:2], 16), int(hex_c[2:4], 16), int(hex_c[4:6], 16)
            link_colors.append(f"rgba({r},{g},{b},0.3)")

        if pending > 0:
            sources.append(i)
            targets.append(pending_idx)
            values.append(pending)
            link_colors.append("rgba(209,213,219,0.4)")

    fig = go.Figure(go.Sankey(
        node=dict(pad=20, thickness=30, label=node_labels, color=node_colors),
        link=dict(source=sources, target=targets, value=values, color=link_colors),
    ))
    fig.update_layout(
        height=450,
        font=dict(family=FONT_FAMILY, size=12),
        margin=dict(l=20, r=20, t=20, b=20),
        paper_bgcolor="#FFFFFF",
    )
    return fig


def _build_violin(wf):
    """Violin plots of inter-stage durations."""
    fig = go.Figure()

    pairs = [
        ("DaysToSimulation", "Consult→Sim"),
        ("DaysFromSimToIsodose", "Sim→Isodose"),
        ("DaysFromSimToReview", "Sim→Review"),
        ("DaysFromReviewToTreatment", "Review→Tx"),
    ]

    for col, label in pairs:
        if col in wf.columns:
            vals = pd.to_numeric(wf[col], errors="coerce").dropna()
            if len(vals) > 0:
                fig.add_trace(go.Violin(
                    y=vals, name=label,
                    box_visible=True, meanline_visible=True,
                    fillcolor=CHART_COLORWAY[len(fig.data) % len(CHART_COLORWAY)],
                    opacity=0.7, line_color="#1A1A2E",
                ))

    apply_default_layout(fig, height=350)
    fig.update_layout(yaxis_title="Days", margin=dict(l=48, r=16, t=16, b=48), showlegend=False)
    return fig


def _prepare_trend_data(wf):
    """Prepare trend data for clientside rendering."""
    if "ScheduledDateTime" not in wf.columns or "FirstTreatmentDate" not in wf.columns:
        return None

    wf = wf.copy()
    wf["total_days"] = (wf["FirstTreatmentDate"] - wf["ScheduledDateTime"]).dt.days
    wf["month"] = wf["ScheduledDateTime"].dt.to_period("M").dt.to_timestamp()
    wf = wf.dropna(subset=["total_days"])

    if wf.empty:
        return None

    monthly = wf.groupby("month")["total_days"].median()
    dates = [d.isoformat() for d in monthly.index]

    series = [{
        "name": "Total Pipeline",
        "values": monthly.tolist(),
        "color": CHART_COLORWAY[0],
    }]

    # Add individual stage medians
    for col, label, color_idx in [
        ("DaysToSimulation", "Consult→Sim", 1),
        ("DaysFromReviewToTreatment", "Review→Tx", 2),
    ]:
        if col in wf.columns:
            stage_data = wf.groupby("month")[col].median()
            stage_data = pd.to_numeric(stage_data, errors="coerce")
            series.append({
                "name": label,
                "values": stage_data.reindex(monthly.index, fill_value=0).tolist(),
                "color": CHART_COLORWAY[color_idx],
            })

    return {
        "dates": dates,
        "series": series,
        "height": 350,
        "yTitle": "Median Days",
    }


def _build_table_data(wf):
    """Build table row data and column definitions."""
    table_cols = []
    col_header_map = {
        "PatientFullName": "Patient",
        "ScheduledDateTime": "Consult",
        "SimulationDate": "Simulation",
        "DaysToSimulation": "Days to Sim",
        "DrawVolumesCompletedDate": "Draw",
        "IsodosePlanCompletedDate": "Isodose",
        "ReviewPlanCompletedDate": "Review",
        "FirstTreatmentDate": "First Tx",
    }

    for col in col_header_map:
        if col in wf.columns:
            table_cols.append(col)

    if not table_cols:
        return [], []

    table_df = wf[table_cols].head(200).copy()
    for c in table_df.select_dtypes(include=["datetime64"]).columns:
        table_df[c] = table_df[c].dt.strftime("%m/%d/%Y")
    table_df = table_df.fillna("—")

    col_defs = [{"field": c, "headerName": col_header_map.get(c, c)} for c in table_cols]

    return table_df.to_dict("records"), col_defs


# ---------------------------------------------------------------------------
# PNG Export
# ---------------------------------------------------------------------------

clientside_callback(
    """function(n) {
        if (!n) return window.dash_clientside.no_update;
        var wrapper = document.getElementById('wf-chart-trend');
        var graphEl = wrapper ? wrapper.querySelector('.js-plotly-plot') : null;
        if (graphEl) Plotly.downloadImage(graphEl, {format: 'png', width: 1200, height: 600, filename: 'pipeline_trend'});
        return window.dash_clientside.no_update;
    }""",
    Output("wf-trend-settings-export", "n_clicks"),
    Input("wf-trend-settings-export", "n_clicks"),
    prevent_initial_call=True,
)

clientside_callback(
    """function(n) {
        if (!n) return window.dash_clientside.no_update;
        var gridApi = window.dash_ag_grid && window.dash_ag_grid['wf-detail-grid'];
        if (gridApi && gridApi.api) gridApi.api.exportDataAsCsv({fileName: 'pipeline_detail.csv'});
        return window.dash_clientside.no_update;
    }""",
    Output("wf-table-export", "n_clicks"),
    Input("wf-table-export", "n_clicks"),
    prevent_initial_call=True,
)
