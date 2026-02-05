"""Workflow page — Sankey pipeline, stage duration violins, pipeline trend."""

import dash
import dash_mantine_components as dmc
from dash import callback, Input, Output, dcc
import plotly.graph_objects as go
import pandas as pd
import numpy as np
from datetime import timedelta

from config.settings import CHART_COLORWAY, DEFAULT_LAYOUT, FONT_FAMILY
from components.filter_bar import (
    filter_bar, date_presets, department_chips, physician_select, date_range_picker,
)
from components.kpi_card import kpi_card
from utils.charts import apply_default_layout, empty_figure

dash.register_page(__name__, path="/workflow", name="Workflow", order=2)

# Stage definitions
STAGES = ["Consult", "Simulation", "Draw Volumes", "Isodose Plan", "Review Plan", "First Treatment"]
STAGE_DATE_COLS = [
    "ScheduledDateTime", "SimulationDate", "DrawVolumesCompletedDate",
    "IsodosePlanCompletedDate", "ReviewPlanCompletedDate", "FirstTreatmentDate",
]
INTER_STAGE_LABELS = ["Consult→Sim", "Sim→Draw", "Draw→Isodose", "Isodose→Review", "Review→Treatment"]

layout = dmc.Stack(
    gap="md",
    children=[
        dmc.Title("Workflow", order=2, c="#7C2A83", ta="center", fw=700, py="sm"),
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

        # KPI row
        dmc.Grid(id="wf-kpi-row", gutter="md", children=[
            dmc.GridCol(id="wf-kpi-consult-sim", span={"base": 6, "md": 3}),
            dmc.GridCol(id="wf-kpi-sim-tx", span={"base": 6, "md": 3}),
            dmc.GridCol(id="wf-kpi-total", span={"base": 6, "md": 3}),
            dmc.GridCol(id="wf-kpi-pipeline", span={"base": 6, "md": 3}),
        ]),

        # Sankey — full width
        dmc.Paper(
            children=[
                dmc.Text("Patient Treatment Pipeline", size="sm", fw=500, c="#6B7280", mb="sm"),
                dcc.Graph(id="wf-chart-sankey", config={"displayModeBar": False}),
            ],
            p="md", radius="md", shadow="xs", withBorder=True,
        ),

        # Violin + Trend side by side
        dmc.Grid(gutter="md", children=[
            dmc.GridCol(
                dmc.Paper(
                    children=[
                        dmc.Text("Stage Duration (days)", size="sm", fw=500, c="#6B7280", mb="sm"),
                        dcc.Graph(id="wf-chart-violin", config={"displayModeBar": False}),
                    ],
                    p="md", radius="md", shadow="xs", withBorder=True,
                ),
                span={"base": 12, "md": 6},
            ),
            dmc.GridCol(
                dmc.Paper(
                    children=[
                        dmc.Text("Pipeline Trend (monthly median)", size="sm", fw=500, c="#6B7280", mb="sm"),
                        dcc.Graph(id="wf-chart-trend", config={"displayModeBar": False}),
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
                ]),
                dmc.Box(id="wf-table-container"),
            ],
            p="md", radius="md", shadow="xs", withBorder=True,
        ),

        dcc.Interval(id="wf-interval", interval=300_000, n_intervals=0),
    ],
)


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
    Output("wf-chart-trend", "figure"),
    Output("wf-table-container", "children"),
    Input("wf-interval", "n_intervals"),
    Input("workflow-filter-department", "value"),
    Input("workflow-filter-date-preset", "value"),
    Input("workflow-filter-daterange", "value"),
    Input("workflow-filter-physician", "value"),
    Input("workflow-filter-diagnosis", "value"),
)
def update_workflow(_n, departments, date_preset, daterange, physicians, diagnosis):
    from data.loader import load_workflow
    import dash_ag_grid as dag

    try:
        wf = load_workflow()
    except Exception:
        empty = empty_figure("Workflow data unavailable")
        na = kpi_card("—", "N/A")
        return na, na, na, na, empty, empty, empty, []

    # Date filtering — explicit range overrides preset
    today = pd.Timestamp.now().normalize()
    if daterange and len(daterange) == 2 and daterange[0] and daterange[1]:
        start = pd.Timestamp(daterange[0])
        end = pd.Timestamp(daterange[1])
    elif date_preset == "ytd":
        start = pd.Timestamp(today.year, 1, 1)
        end = today
    elif date_preset == "12mo":
        start = today - timedelta(days=365)
        end = today
    else:
        start = pd.Timestamp("2020-01-01")
        end = today

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

    # --- KPIs ---
    def safe_median(col):
        if col in wf_period.columns:
            vals = pd.to_numeric(wf_period[col], errors="coerce").dropna()
            return f"{vals.median():.0f}" if len(vals) > 0 else "N/A"
        return "N/A"

    kpi_cs = kpi_card("Consult→Sim (median days)", safe_median("DaysToSimulation"))
    kpi_st = kpi_card("Sim→Treatment (median days)", safe_median("DaysFromReviewToTreatment"))

    if "ScheduledDateTime" in wf_period.columns and "FirstTreatmentDate" in wf_period.columns:
        total_days = (wf_period["FirstTreatmentDate"] - wf_period["ScheduledDateTime"]).dt.days.dropna()
        total_median = f"{total_days.median():.0f}" if len(total_days) > 0 else "N/A"
    else:
        total_median = "N/A"
    kpi_total = kpi_card("Total Pipeline (median days)", total_median)

    pipeline_count = len(wf_period[wf_period["FirstTreatmentDate"].isna()]) if "FirstTreatmentDate" in wf_period.columns else 0
    kpi_pipe = kpi_card("In Pipeline", str(pipeline_count))

    # --- Sankey ---
    fig_sankey = _build_sankey(wf_period)

    # --- Violin ---
    fig_violin = _build_violin(wf_period)

    # --- Trend ---
    fig_trend = _build_trend(wf_period)

    # --- Detail table ---
    table_cols = []
    for col in ["PatientFullName", "ScheduledDateTime", "SimulationDate",
                 "DaysToSimulation", "DrawVolumesCompletedDate",
                 "IsodosePlanCompletedDate", "ReviewPlanCompletedDate",
                 "FirstTreatmentDate"]:
        if col in wf_period.columns:
            table_cols.append(col)

    if table_cols:
        table_df = wf_period[table_cols].head(200).copy()
        for c in table_df.select_dtypes(include=["datetime64"]).columns:
            table_df[c] = table_df[c].dt.strftime("%m/%d/%Y")
        table_df = table_df.fillna("—")

        table = dag.AgGrid(
            id="wf-detail-grid",
            rowData=table_df.to_dict("records"),
            columnDefs=[{"field": c, "headerName": c.replace("CompletedDate", "").replace("DateTime", "")} for c in table_cols],
            defaultColDef={"sortable": True, "filter": True, "resizable": True},
            dashGridOptions={"pagination": True, "paginationPageSize": 25, "domLayout": "autoHeight"},
            className="ag-theme-alpine",
        )
    else:
        table = dmc.Text("No workflow data available", c="#9CA3AF", ta="center", py="xl")

    return kpi_cs, kpi_st, kpi_total, kpi_pipe, fig_sankey, fig_violin, fig_trend, table


def _build_sankey(wf):
    """Build a Sankey diagram of the treatment pipeline.

    All stages flow forward or to a single 'Pending' node (gray).
    Node labels show the count and percentage of initial consults.
    """
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

        # Flow to next stage
        if progressed > 0:
            sources.append(i)
            targets.append(i + 1)
            values.append(progressed)
            c = CHART_COLORWAY[i % len(CHART_COLORWAY)]
            hex_c = c.lstrip("#")
            r, g, b = int(hex_c[0:2], 16), int(hex_c[2:4], 16), int(hex_c[4:6], 16)
            link_colors.append(f"rgba({r},{g},{b},0.3)")

        # Flow to single Pending node
        if pending > 0:
            sources.append(i)
            targets.append(pending_idx)
            values.append(pending)
            link_colors.append("rgba(209,213,219,0.4)")

    fig = go.Figure(go.Sankey(
        node=dict(
            pad=20, thickness=30,
            label=node_labels,
            color=node_colors,
        ),
        link=dict(
            source=sources, target=targets,
            value=values, color=link_colors,
        ),
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
    fig.update_layout(
        yaxis_title="Days",
        margin=dict(l=48, r=16, t=16, b=48),
        showlegend=False,
    )
    return fig


def _build_trend(wf):
    """Monthly median pipeline duration trend."""
    if "ScheduledDateTime" not in wf.columns or "FirstTreatmentDate" not in wf.columns:
        return empty_figure()

    wf = wf.copy()
    wf["total_days"] = (wf["FirstTreatmentDate"] - wf["ScheduledDateTime"]).dt.days
    wf["month"] = wf["ScheduledDateTime"].dt.to_period("M").dt.to_timestamp()
    wf = wf.dropna(subset=["total_days"])

    if wf.empty:
        return empty_figure()

    monthly = wf.groupby("month")["total_days"].median().reset_index()

    fig = go.Figure(go.Scatter(
        x=monthly["month"], y=monthly["total_days"],
        mode="lines+markers",
        line=dict(color=CHART_COLORWAY[0], width=2),
        marker=dict(size=5),
        name="Total Pipeline",
    ))

    # Add individual stage medians if available
    for col, label, color_idx in [
        ("DaysToSimulation", "Consult→Sim", 1),
        ("DaysFromReviewToTreatment", "Review→Tx", 2),
    ]:
        if col in wf.columns:
            stage_monthly = wf.groupby("month")[col].median().reset_index()
            stage_monthly[col] = pd.to_numeric(stage_monthly[col], errors="coerce")
            fig.add_trace(go.Scatter(
                x=stage_monthly["month"], y=stage_monthly[col],
                mode="lines", name=label,
                line=dict(color=CHART_COLORWAY[color_idx], width=1.5, dash="dash"),
            ))

    apply_default_layout(fig, height=350)
    fig.update_layout(
        yaxis_title="Median Days",
        margin=dict(l=48, r=16, t=16, b=48),
    )
    return fig
