"""OTV Audit page — on-treatment visit compliance and billing audit."""

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

dash.register_page(__name__, path="/otv-audit", name="OTV Audit", order=11)

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
                dmc.Title("OTV Audit", order=2, className="page-title"),
                filter_bar("otv", children=[
                    date_presets("otv"),
                    department_chips("otv"),
                ]),
            ],
        ),

        # KPI row
        dmc.Grid(id="otv-kpi-row", gutter="md", children=[
            dmc.GridCol(id="otv-kpi-total", span={"base": 6, "md": 2.4}),
            dmc.GridCol(id="otv-kpi-compliance", span={"base": 6, "md": 2.4}),
            dmc.GridCol(id="otv-kpi-extra", span={"base": 6, "md": 2.4}),
            dmc.GridCol(id="otv-kpi-toofew", span={"base": 6, "md": 2.4}),
            dmc.GridCol(id="otv-kpi-discrepancy", span={"base": 6, "md": 2.4}),
        ]),

        # Charts row 1: By department + Trend
        dmc.Grid(gutter="md", children=[
            dmc.GridCol(
                dmc.Paper(
                    children=[
                        dmc.Text("Compliance by Department", size="sm", fw=500, c=NEUTRAL["text_secondary"], mb="sm"),
                        dmc.Box(
                            pos="relative",
                            children=[
                                dmc.LoadingOverlay(id="otv-dept-loading", visible=False, loaderProps={"type": "dots", "color": PRIMARY}),
                                dcc.Graph(id="otv-chart-department", config={"displayModeBar": False}, style={"height": "320px"}),
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
                                dmc.LoadingOverlay(id="otv-trend-loading", visible=False, loaderProps={"type": "dots", "color": PRIMARY}),
                                dcc.Graph(id="otv-chart-trend", config={"displayModeBar": False}, style={"height": "320px"}),
                            ],
                        ),
                    ],
                    p="md", radius="md", shadow="xs", withBorder=True,
                ),
                span={"base": 12, "md": 6},
            ),
        ]),

        # Charts row 2: Distribution + Discrepancy histogram
        dmc.Grid(gutter="md", children=[
            dmc.GridCol(
                dmc.Paper(
                    children=[
                        dmc.Text("Audit Result Distribution", size="sm", fw=500, c=NEUTRAL["text_secondary"], mb="sm"),
                        dmc.Box(
                            pos="relative",
                            children=[
                                dmc.LoadingOverlay(id="otv-dist-loading", visible=False, loaderProps={"type": "dots", "color": PRIMARY}),
                                dcc.Graph(id="otv-chart-distribution", config={"displayModeBar": False}, style={"height": "320px"}),
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
                        dmc.Text("Discrepancy Distribution", size="sm", fw=500, c=NEUTRAL["text_secondary"], mb="sm"),
                        dmc.Box(
                            pos="relative",
                            children=[
                                dmc.LoadingOverlay(id="otv-hist-loading", visible=False, loaderProps={"type": "dots", "color": PRIMARY}),
                                dcc.Graph(id="otv-chart-histogram", config={"displayModeBar": False}, style={"height": "320px"}),
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
                    dmc.Text("OTV Audit Detail", size="sm", fw=500, c=NEUTRAL["text_secondary"]),
                    dmc.ActionIcon(
                        dmc.Text("CSV", size="xs", fw=600),
                        id="otv-table-export",
                        variant="subtle", color="gray", size="sm",
                    ),
                ], justify="space-between", mb="sm"),
                dmc.Box(id="otv-table-container"),
            ],
            p="md", radius="md", shadow="xs", withBorder=True,
        ),

        dcc.Interval(id="otv-interval", interval=300_000, n_intervals=0),
    ],
)


# ---------------------------------------------------------------------------
# Callbacks
# ---------------------------------------------------------------------------
@callback(
    Output("otv-kpi-total", "children"),
    Output("otv-kpi-compliance", "children"),
    Output("otv-kpi-extra", "children"),
    Output("otv-kpi-toofew", "children"),
    Output("otv-kpi-discrepancy", "children"),
    Output("otv-chart-department", "figure"),
    Output("otv-chart-trend", "figure"),
    Output("otv-chart-distribution", "figure"),
    Output("otv-chart-histogram", "figure"),
    Output("otv-table-container", "children"),
    Output("otv-dept-loading", "visible"),
    Output("otv-trend-loading", "visible"),
    Output("otv-dist-loading", "visible"),
    Output("otv-hist-loading", "visible"),
    Input("otv-interval", "n_intervals"),
    Input("otv-filter-date-preset", "value"),
    Input("otv-filter-department", "value"),
)
def update_otv_audit(_n, date_preset, departments):
    from data.loader import load_otvs

    empty = empty_figure("OTV Audit data unavailable")
    na_kpi = kpi_card("—", "N/A")
    loading_off = False

    try:
        otv = load_otvs()
    except Exception:
        return (na_kpi,) * 5 + (empty,) * 4 + ([],) + (loading_off,) * 4

    # Date filtering
    date_col = "LastTreatmentDate" if "LastTreatmentDate" in otv.columns else "FirstTreatmentDate"
    if date_col in otv.columns:
        otv[date_col] = pd.to_datetime(otv[date_col], errors="coerce")
        last_date = otv[date_col].max()
    else:
        last_date = pd.Timestamp.now().normalize()

    if date_preset == "ytd":
        start = pd.Timestamp(last_date.year, 1, 1)
    elif date_preset == "12mo":
        start = last_date - timedelta(days=365)
    else:
        start = last_date - timedelta(days=90)

    # Filter
    df = otv.copy()
    if date_col in df.columns:
        df = df[(df[date_col] >= start) & (df[date_col] <= last_date)]

    if departments and "Department" in df.columns:
        df = df[df["Department"].isin(departments)]

    if df.empty:
        return (na_kpi,) * 5 + (empty,) * 4 + ([],) + (loading_off,) * 4

    # --- KPIs ---
    total = len(df)
    ok_count = (df["AuditResult"] == "OK").sum() if "AuditResult" in df.columns else 0
    extra_count = (df["AuditResult"] == "Extra Visit(s)").sum() if "AuditResult" in df.columns else 0
    toofew_count = (df["AuditResult"] == "Too Few").sum() if "AuditResult" in df.columns else 0
    compliance_rate = (ok_count / total * 100) if total > 0 else 0

    # Discrepancy calculation
    if "ManagementCPTs_Total" in df.columns and "AllowedOTVs" in df.columns:
        df["Discrepancy"] = df["ManagementCPTs_Total"] - df["AllowedOTVs"]
        non_ok = df[df["AuditResult"] != "OK"]
        avg_discrepancy = non_ok["Discrepancy"].mean() if len(non_ok) > 0 else 0
    else:
        avg_discrepancy = 0

    kpi_total = kpi_card("Total Courses", f"{total:,}", accent_color=PRIMARY)
    kpi_compliance = kpi_card(
        "Compliance Rate", f"{compliance_rate:.1f}%",
        accent_color=SEMANTIC_COLORS["success"] if compliance_rate >= 90 else SEMANTIC_COLORS["warning"],
    )
    kpi_extra = kpi_card("Extra Visits", f"{extra_count:,}", accent_color=SEMANTIC_COLORS["warning"])
    kpi_toofew = kpi_card("Too Few Visits", f"{toofew_count:,}", accent_color=SEMANTIC_COLORS["error"])
    kpi_discrepancy = kpi_card("Avg Discrepancy", f"{avg_discrepancy:+.1f}")

    # --- Charts ---
    fig_dept = _build_department_chart(df)
    fig_trend = _build_trend_chart(df, date_col)
    fig_dist = _build_distribution_chart(df)
    fig_hist = _build_histogram(df)

    # --- Table ---
    table = _build_table(df)

    return (
        kpi_total, kpi_compliance, kpi_extra, kpi_toofew, kpi_discrepancy,
        fig_dept, fig_trend, fig_dist, fig_hist, table,
        False, False, False, False,
    )


def _build_department_chart(df):
    """Stacked bar chart of audit results by department."""
    if "Department" not in df.columns or "AuditResult" not in df.columns:
        return empty_figure("No department data")

    pivot = df.groupby(["Department", "AuditResult"]).size().unstack(fill_value=0)

    fig = go.Figure()

    result_colors = {
        "OK": SEMANTIC_COLORS["success"],
        "Extra Visit(s)": SEMANTIC_COLORS["warning"],
        "Too Few": SEMANTIC_COLORS["error"],
    }

    for result in ["OK", "Extra Visit(s)", "Too Few"]:
        if result in pivot.columns:
            fig.add_trace(go.Bar(
                x=pivot.index,
                y=pivot[result],
                name=result,
                marker_color=result_colors.get(result, PRIMARY),
            ))

    apply_default_layout(fig, barmode="stack", height=320)
    fig.update_layout(yaxis_title="Courses", margin=dict(l=48, r=16, t=16, b=48))
    return fig


def _build_trend_chart(df, date_col):
    """Line chart of compliance rate over time."""
    if date_col not in df.columns or "AuditResult" not in df.columns:
        return empty_figure("No trend data")

    df = df.copy()
    df["month"] = df[date_col].dt.to_period("M").dt.to_timestamp()

    monthly = df.groupby("month").apply(
        lambda x: (x["AuditResult"] == "OK").sum() / len(x) * 100 if len(x) > 0 else 0
    ).reset_index(name="compliance")

    fig = go.Figure(go.Scatter(
        x=monthly["month"],
        y=monthly["compliance"],
        mode="lines+markers",
        line=dict(color=PRIMARY, width=2),
        marker=dict(size=6),
    ))

    apply_default_layout(fig, height=320)
    fig.update_layout(
        yaxis_title="Compliance %",
        yaxis_range=[0, 105],
        margin=dict(l=48, r=16, t=16, b=48),
    )
    return fig


def _build_distribution_chart(df):
    """Pie chart of audit result distribution."""
    if "AuditResult" not in df.columns:
        return empty_figure("No audit data")

    counts = df["AuditResult"].value_counts()

    result_colors = {
        "OK": SEMANTIC_COLORS["success"],
        "Extra Visit(s)": SEMANTIC_COLORS["warning"],
        "Too Few": SEMANTIC_COLORS["error"],
    }
    colors = [result_colors.get(r, PRIMARY) for r in counts.index]

    fig = go.Figure(go.Pie(
        labels=counts.index,
        values=counts.values,
        marker_colors=colors,
        hole=0.4,
        textinfo="label+percent",
        textposition="outside",
    ))

    apply_default_layout(fig, height=320)
    fig.update_layout(
        showlegend=False,
        margin=dict(l=16, r=16, t=16, b=16),
    )
    return fig


def _build_histogram(df):
    """Histogram of discrepancy values."""
    if "Discrepancy" not in df.columns:
        if "ManagementCPTs_Total" in df.columns and "AllowedOTVs" in df.columns:
            df = df.copy()
            df["Discrepancy"] = df["ManagementCPTs_Total"] - df["AllowedOTVs"]
        else:
            return empty_figure("No discrepancy data")

    fig = go.Figure(go.Histogram(
        x=df["Discrepancy"],
        nbinsx=20,
        marker_color=PRIMARY,
        opacity=0.8,
    ))

    # Add zero line
    fig.add_vline(x=0, line_dash="dash", line_color=SEMANTIC_COLORS["success"],
                  annotation_text="Target")

    apply_default_layout(fig, height=320)
    fig.update_layout(
        xaxis_title="Discrepancy (Actual - Allowed)",
        yaxis_title="Courses",
        margin=dict(l=48, r=16, t=16, b=48),
    )
    return fig


def _build_table(df):
    """Build AG Grid table of OTV audit records."""
    if df.empty:
        return dmc.Text("No OTV audit data available", c=NEUTRAL["text_muted"], ta="center", py="xl")

    display_cols = [
        {"field": "PatientName", "headerName": "Patient"},
        {"field": "CourseId", "headerName": "Course"},
        {"field": "Department", "headerName": "Department"},
        {"field": "FirstTreatmentDate", "headerName": "First Tx"},
        {"field": "LastTreatmentDate", "headerName": "Last Tx"},
        {"field": "PrescribedFractions", "headerName": "Rx Fx"},
        {"field": "AllowedOTVs", "headerName": "Allowed"},
        {"field": "ManagementCPTs_Total", "headerName": "Actual"},
        {"field": "AuditResult", "headerName": "Result", "cellStyle": {
            "styleConditions": [
                {"condition": "params.value === 'OK'", "style": {"color": SEMANTIC_COLORS["success"], "fontWeight": "600"}},
                {"condition": "params.value === 'Extra Visit(s)'", "style": {"color": SEMANTIC_COLORS["warning"], "fontWeight": "600"}},
                {"condition": "params.value === 'Too Few'", "style": {"color": SEMANTIC_COLORS["error"], "fontWeight": "600"}},
            ],
        }},
    ]

    # Filter to only existing columns
    existing_cols = [c for c in display_cols if c["field"] in df.columns]

    table_df = df.head(500).copy()
    for c in ["FirstTreatmentDate", "LastTreatmentDate"]:
        if c in table_df.columns and pd.api.types.is_datetime64_any_dtype(table_df[c]):
            table_df[c] = table_df[c].dt.strftime("%m/%d/%Y")
    table_df = table_df.fillna("—")

    return dag.AgGrid(
        id="otv-detail-grid",
        rowData=table_df.to_dict("records"),
        columnDefs=existing_cols,
        defaultColDef={"sortable": True, "filter": True, "resizable": True},
        dashGridOptions={"pagination": True, "paginationPageSize": 25, "domLayout": "autoHeight"},
        className="ag-theme-alpine",
    )
