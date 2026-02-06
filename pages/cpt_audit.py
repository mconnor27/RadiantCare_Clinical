"""CPT Audit page — 2026 CPT coding compliance tracking."""

import dash
import dash_mantine_components as dmc
from dash import callback, Input, Output, dcc
import dash_ag_grid as dag
import plotly.graph_objects as go
import pandas as pd
from datetime import timedelta

from config.settings import (
    DEPARTMENTS, DEPARTMENT_COLORS, PRIMARY, NEUTRAL,
    SEMANTIC_COLORS, CHART_COLORWAY,
)
from components.filter_bar import filter_bar, date_presets, department_chips
from components.kpi_card import kpi_card
from utils.charts import apply_default_layout, empty_figure

dash.register_page(__name__, path="/cpt-audit", name="CPT Audit", order=12)

# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------
layout = dmc.Stack(
    gap=16,
    className="page-content",
    children=[
        dmc.Title("CPT Audit", order=2, className="page-title"),
        filter_bar("cpt", children=[
            date_presets("cpt"),
            department_chips("cpt"),
            dmc.SegmentedControl(
                id="cpt-filter-result",
                data=[
                    {"value": "all", "label": "All"},
                    {"value": "pass", "label": "Pass"},
                    {"value": "fail", "label": "Fail"},
                ],
                value="all", size="sm",
            ),
        ]),

        # KPI row
        dmc.Grid(id="cpt-kpi-row", gutter="md", children=[
            dmc.GridCol(id="cpt-kpi-total", span={"base": 6, "md": 2.4}),
            dmc.GridCol(id="cpt-kpi-passrate", span={"base": 6, "md": 2.4}),
            dmc.GridCol(id="cpt-kpi-failcount", span={"base": 6, "md": 2.4}),
            dmc.GridCol(id="cpt-kpi-patients", span={"base": 6, "md": 2.4}),
            dmc.GridCol(id="cpt-kpi-common", span={"base": 6, "md": 2.4}),
        ]),

        # Charts row 1: By department + Trend
        dmc.Grid(gutter="md", children=[
            dmc.GridCol(
                dmc.Paper(
                    children=[
                        dmc.Text("Pass/Fail by Department", size="sm", fw=500, c=NEUTRAL["text_secondary"], mb="sm"),
                        dmc.Box(
                            pos="relative",
                            children=[
                                dmc.LoadingOverlay(id="cpt-dept-loading", visible=False, loaderProps={"type": "dots", "color": PRIMARY}),
                                dcc.Graph(id="cpt-chart-department", config={"displayModeBar": False}, style={"height": "320px"}),
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
                        dmc.Text("Compliance Trend", size="sm", fw=500, c=NEUTRAL["text_secondary"], mb="sm"),
                        dmc.Box(
                            pos="relative",
                            children=[
                                dmc.LoadingOverlay(id="cpt-trend-loading", visible=False, loaderProps={"type": "dots", "color": PRIMARY}),
                                dcc.Graph(id="cpt-chart-trend", config={"displayModeBar": False}, style={"height": "320px"}),
                            ],
                        ),
                    ],
                    p="md", radius="md", shadow="xs", withBorder=True,
                ),
                span={"base": 12, "md": 6},
            ),
        ]),

        # Charts row 2: By technique + Mismatch breakdown
        dmc.Grid(gutter="md", children=[
            dmc.GridCol(
                dmc.Paper(
                    children=[
                        dmc.Text("Failures by Technique", size="sm", fw=500, c=NEUTRAL["text_secondary"], mb="sm"),
                        dmc.Box(
                            pos="relative",
                            children=[
                                dmc.LoadingOverlay(id="cpt-tech-loading", visible=False, loaderProps={"type": "dots", "color": PRIMARY}),
                                dcc.Graph(id="cpt-chart-technique", config={"displayModeBar": False}, style={"height": "320px"}),
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
                        dmc.Text("Top CPT Mismatches", size="sm", fw=500, c=NEUTRAL["text_secondary"], mb="sm"),
                        dmc.Box(
                            pos="relative",
                            children=[
                                dmc.LoadingOverlay(id="cpt-mismatch-loading", visible=False, loaderProps={"type": "dots", "color": PRIMARY}),
                                dcc.Graph(id="cpt-chart-mismatch", config={"displayModeBar": False}, style={"height": "320px"}),
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
                dmc.Group([
                    dmc.Text("CPT Audit Detail", size="sm", fw=500, c=NEUTRAL["text_secondary"]),
                    dmc.ActionIcon(
                        dmc.Text("CSV", size="xs", fw=600),
                        id="cpt-table-export",
                        variant="subtle", color="gray", size="sm",
                    ),
                ], justify="space-between", mb="sm"),
                dmc.Box(id="cpt-table-container"),
            ],
            p="md", radius="md", shadow="xs", withBorder=True,
        ),

        dcc.Interval(id="cpt-interval", interval=300_000, n_intervals=0),
    ],
)


# ---------------------------------------------------------------------------
# Callbacks
# ---------------------------------------------------------------------------
@callback(
    Output("cpt-kpi-total", "children"),
    Output("cpt-kpi-passrate", "children"),
    Output("cpt-kpi-failcount", "children"),
    Output("cpt-kpi-patients", "children"),
    Output("cpt-kpi-common", "children"),
    Output("cpt-chart-department", "figure"),
    Output("cpt-chart-trend", "figure"),
    Output("cpt-chart-technique", "figure"),
    Output("cpt-chart-mismatch", "figure"),
    Output("cpt-table-container", "children"),
    Output("cpt-dept-loading", "visible"),
    Output("cpt-trend-loading", "visible"),
    Output("cpt-tech-loading", "visible"),
    Output("cpt-mismatch-loading", "visible"),
    Input("cpt-interval", "n_intervals"),
    Input("cpt-filter-date-preset", "value"),
    Input("cpt-filter-department", "value"),
    Input("cpt-filter-result", "value"),
)
def update_cpt_audit(_n, date_preset, departments, result_filter):
    from data.loader import load_cpt_audit

    empty = empty_figure("CPT Audit data unavailable")
    na_kpi = kpi_card("—", "N/A")
    loading_off = False

    try:
        cpt = load_cpt_audit()
    except Exception:
        return (na_kpi,) * 5 + (empty,) * 4 + ([],) + (loading_off,) * 4

    # Date filtering
    if "TreatmentDate" in cpt.columns:
        cpt["TreatmentDate"] = pd.to_datetime(cpt["TreatmentDate"], errors="coerce")
        last_date = cpt["TreatmentDate"].max()
    else:
        last_date = pd.Timestamp.now().normalize()

    if date_preset == "ytd":
        start = pd.Timestamp(last_date.year, 1, 1)
    elif date_preset == "12mo":
        start = last_date - timedelta(days=365)
    else:
        start = last_date - timedelta(days=90)

    # Filter
    df = cpt.copy()
    if "TreatmentDate" in df.columns:
        df = df[(df["TreatmentDate"] >= start) & (df["TreatmentDate"] <= last_date)]

    if departments and "Department" in df.columns:
        df = df[df["Department"].isin(departments)]

    # Result filter
    if result_filter == "pass" and "AuditResult" in df.columns:
        df = df[df["AuditResult"] == "PASS"]
    elif result_filter == "fail" and "AuditResult" in df.columns:
        df = df[df["AuditResult"] == "FAIL"]

    if df.empty:
        return (na_kpi,) * 5 + (empty,) * 4 + ([],) + (loading_off,) * 4

    # --- KPIs ---
    total = len(df)
    pass_count = (df["AuditResult"] == "PASS").sum() if "AuditResult" in df.columns else 0
    fail_count = (df["AuditResult"] == "FAIL").sum() if "AuditResult" in df.columns else 0
    pass_rate = (pass_count / total * 100) if total > 0 else 0

    # Unique patients with failures
    if "PatientId" in df.columns and "AuditResult" in df.columns:
        fail_patients = df[df["AuditResult"] == "FAIL"]["PatientId"].nunique()
    else:
        fail_patients = 0

    # Most common mismatch
    common_mismatch = "—"
    if "CPT_Correct" in df.columns and "CPT_Billed" in df.columns and "AuditResult" in df.columns:
        failures = df[df["AuditResult"] == "FAIL"]
        if not failures.empty:
            mismatch_counts = failures.groupby(["CPT_Correct", "CPT_Billed"]).size()
            if len(mismatch_counts) > 0:
                top = mismatch_counts.idxmax()
                common_mismatch = f"{top[0]}→{top[1]}"

    kpi_total = kpi_card("Total Sessions", f"{total:,}", accent_color=PRIMARY)
    kpi_passrate = kpi_card(
        "Pass Rate", f"{pass_rate:.1f}%",
        accent_color=SEMANTIC_COLORS["success"] if pass_rate >= 95 else SEMANTIC_COLORS["warning"],
    )
    kpi_failcount = kpi_card("Failures", f"{fail_count:,}", accent_color=SEMANTIC_COLORS["error"] if fail_count > 0 else None)
    kpi_patients = kpi_card("Patients w/ Failures", f"{fail_patients:,}")
    kpi_common = kpi_card("Most Common Error", common_mismatch)

    # --- Charts ---
    fig_dept = _build_department_chart(df)
    fig_trend = _build_trend_chart(df)
    fig_tech = _build_technique_chart(df)
    fig_mismatch = _build_mismatch_chart(df)

    # --- Table ---
    table = _build_table(df)

    return (
        kpi_total, kpi_passrate, kpi_failcount, kpi_patients, kpi_common,
        fig_dept, fig_trend, fig_tech, fig_mismatch, table,
        False, False, False, False,
    )


def _build_department_chart(df):
    """Stacked bar chart of pass/fail by department."""
    if "Department" not in df.columns or "AuditResult" not in df.columns:
        return empty_figure("No department data")

    pivot = df.groupby(["Department", "AuditResult"]).size().unstack(fill_value=0)

    fig = go.Figure()

    result_colors = {
        "PASS": SEMANTIC_COLORS["success"],
        "FAIL": SEMANTIC_COLORS["error"],
    }

    for result in ["PASS", "FAIL"]:
        if result in pivot.columns:
            fig.add_trace(go.Bar(
                x=pivot.index,
                y=pivot[result],
                name=result,
                marker_color=result_colors.get(result, PRIMARY),
            ))

    apply_default_layout(fig, barmode="stack", height=320)
    fig.update_layout(yaxis_title="Sessions", margin=dict(l=48, r=16, t=16, b=48))
    return fig


def _build_trend_chart(df):
    """Line chart of pass rate over time."""
    if "TreatmentDate" not in df.columns or "AuditResult" not in df.columns:
        return empty_figure("No trend data")

    df = df.copy()
    df["week"] = df["TreatmentDate"].dt.to_period("W").dt.start_time

    weekly = df.groupby("week").apply(
        lambda x: (x["AuditResult"] == "PASS").sum() / len(x) * 100 if len(x) > 0 else 0
    ).reset_index(name="pass_rate")

    fig = go.Figure(go.Scatter(
        x=weekly["week"],
        y=weekly["pass_rate"],
        mode="lines+markers",
        line=dict(color=PRIMARY, width=2),
        marker=dict(size=5),
    ))

    apply_default_layout(fig, height=320)
    fig.update_layout(
        yaxis_title="Pass Rate %",
        yaxis_range=[0, 105],
        margin=dict(l=48, r=16, t=16, b=48),
    )
    return fig


def _build_technique_chart(df):
    """Bar chart of failures by technique."""
    if "RxTechnique_Day" not in df.columns or "AuditResult" not in df.columns:
        return empty_figure("No technique data")

    failures = df[df["AuditResult"] == "FAIL"]
    if failures.empty:
        return empty_figure("No failures to display")

    tech_counts = failures["RxTechnique_Day"].value_counts().head(10)

    fig = go.Figure(go.Bar(
        x=tech_counts.index,
        y=tech_counts.values,
        marker_color=SEMANTIC_COLORS["error"],
    ))

    apply_default_layout(fig, height=320)
    fig.update_layout(yaxis_title="Failures", margin=dict(l=48, r=16, t=16, b=48))
    return fig


def _build_mismatch_chart(df):
    """Horizontal bar chart of top CPT mismatches."""
    if "CPT_Correct" not in df.columns or "CPT_Billed" not in df.columns or "AuditResult" not in df.columns:
        return empty_figure("No mismatch data")

    failures = df[df["AuditResult"] == "FAIL"]
    if failures.empty:
        return empty_figure("No failures to display")

    mismatch_counts = failures.groupby(["CPT_Correct", "CPT_Billed"]).size().reset_index(name="count")
    mismatch_counts = mismatch_counts.nlargest(10, "count")
    mismatch_counts["label"] = mismatch_counts["CPT_Correct"] + " → " + mismatch_counts["CPT_Billed"]
    mismatch_counts = mismatch_counts.sort_values("count", ascending=True)

    fig = go.Figure(go.Bar(
        x=mismatch_counts["count"],
        y=mismatch_counts["label"],
        orientation="h",
        marker_color=CHART_COLORWAY[0],
    ))

    apply_default_layout(fig, height=320)
    fig.update_layout(xaxis_title="Count", margin=dict(l=140, r=16, t=16, b=48))
    return fig


def _build_table(df):
    """Build AG Grid table of CPT audit records."""
    if df.empty:
        return dmc.Text("No CPT audit data available", c=NEUTRAL["text_muted"], ta="center", py="xl")

    display_cols = [
        {"field": "TreatmentDate", "headerName": "Date"},
        {"field": "PatientId", "headerName": "Patient"},
        {"field": "Department", "headerName": "Dept"},
        {"field": "Machine", "headerName": "Machine"},
        {"field": "RxTechnique_Day", "headerName": "Technique"},
        {"field": "CPT_Correct", "headerName": "Correct CPT"},
        {"field": "CPT_Billed", "headerName": "Billed CPT"},
        {"field": "AuditResult", "headerName": "Result", "cellStyle": {
            "styleConditions": [
                {"condition": "params.value === 'PASS'", "style": {"color": SEMANTIC_COLORS["success"], "fontWeight": "600"}},
                {"condition": "params.value === 'FAIL'", "style": {"color": SEMANTIC_COLORS["error"], "fontWeight": "600"}},
            ],
        }},
    ]

    # Filter to only existing columns
    existing_cols = [c for c in display_cols if c["field"] in df.columns]

    table_df = df.head(500).copy()
    if "TreatmentDate" in table_df.columns and pd.api.types.is_datetime64_any_dtype(table_df["TreatmentDate"]):
        table_df["TreatmentDate"] = table_df["TreatmentDate"].dt.strftime("%m/%d/%Y")
    table_df = table_df.fillna("—")

    return dag.AgGrid(
        id="cpt-detail-grid",
        rowData=table_df.to_dict("records"),
        columnDefs=existing_cols,
        defaultColDef={"sortable": True, "filter": True, "resizable": True},
        dashGridOptions={"pagination": True, "paginationPageSize": 25, "domLayout": "autoHeight"},
        className="ag-theme-alpine",
    )
