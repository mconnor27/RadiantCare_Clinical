"""OTVs page — weekly check volume, physician workload, and coverage analysis."""

import dash
import dash_mantine_components as dmc
from dash import callback, Input, Output, dcc
import dash_ag_grid as dag
import plotly.graph_objects as go
import pandas as pd
from datetime import timedelta

from config.settings import (
    DEPARTMENTS, DEPARTMENT_COLORS, PRIMARY, NEUTRAL,
    SEMANTIC_COLORS, PHYSICIANS,
)
from components.filter_bar import filter_bar, date_presets, department_chips, physician_select
from components.kpi_card import kpi_card
from utils.charts import apply_default_layout, empty_figure

dash.register_page(__name__, path="/otvs", name="OTVs", order=6)

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
                dmc.Title("OTVs", order=2, className="page-title"),
                filter_bar("otvs", children=[
                    date_presets("otvs"),
                    department_chips("otvs"),
                    physician_select("otvs"),
                ]),
            ],
        ),

        # KPI row
        dmc.Grid(id="otvs-kpi-row", gutter="md", children=[
            dmc.GridCol(id="otvs-kpi-total", span={"base": 6, "md": 2.4}),
            dmc.GridCol(id="otvs-kpi-patients", span={"base": 6, "md": 2.4}),
            dmc.GridCol(id="otvs-kpi-avg", span={"base": 6, "md": 2.4}),
            dmc.GridCol(id="otvs-kpi-self-rate", span={"base": 6, "md": 2.4}),
            dmc.GridCol(id="otvs-kpi-physicians", span={"base": 6, "md": 2.4}),
        ]),

        # Charts row 1: Weekly Volume + Volume by Physician
        dmc.Grid(gutter="md", children=[
            dmc.GridCol(
                dmc.Paper(
                    children=[
                        dmc.Text("Weekly Visit Volume", size="sm", fw=500,
                                 c=NEUTRAL["text_secondary"], mb="sm"),
                        dmc.Box(
                            pos="relative",
                            children=[
                                dmc.LoadingOverlay(id="otvs-volume-loading", visible=False,
                                                   loaderProps={"type": "dots", "color": PRIMARY}),
                                dcc.Graph(id="otvs-chart-volume",
                                          config={"displayModeBar": False},
                                          style={"height": "320px"}),
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
                        dmc.Text("Volume by Physician", size="sm", fw=500,
                                 c=NEUTRAL["text_secondary"], mb="sm"),
                        dmc.Box(
                            pos="relative",
                            children=[
                                dmc.LoadingOverlay(id="otvs-physician-loading", visible=False,
                                                   loaderProps={"type": "dots", "color": PRIMARY}),
                                dcc.Graph(id="otvs-chart-physician",
                                          config={"displayModeBar": False},
                                          style={"height": "320px"}),
                            ],
                        ),
                    ],
                    p="md", radius="md", shadow="xs", withBorder=True,
                ),
                span={"base": 12, "md": 6},
            ),
        ]),

        # Charts row 2: Volume by Department + Coverage Heatmap
        dmc.Grid(gutter="md", children=[
            dmc.GridCol(
                dmc.Paper(
                    children=[
                        dmc.Text("Volume by Department", size="sm", fw=500,
                                 c=NEUTRAL["text_secondary"], mb="sm"),
                        dmc.Box(
                            pos="relative",
                            children=[
                                dmc.LoadingOverlay(id="otvs-dept-loading", visible=False,
                                                   loaderProps={"type": "dots", "color": PRIMARY}),
                                dcc.Graph(id="otvs-chart-dept",
                                          config={"displayModeBar": False},
                                          style={"height": "320px"}),
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
                        dmc.Text("Coverage Analysis", size="sm", fw=500,
                                 c=NEUTRAL["text_secondary"], mb="sm"),
                        dmc.Box(
                            pos="relative",
                            children=[
                                dmc.LoadingOverlay(id="otvs-coverage-loading", visible=False,
                                                   loaderProps={"type": "dots", "color": PRIMARY}),
                                dcc.Graph(id="otvs-chart-coverage",
                                          config={"displayModeBar": False},
                                          style={"height": "320px"}),
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
                    dmc.Text("Weekly Visit Detail", size="sm", fw=500,
                             c=NEUTRAL["text_secondary"]),
                    dmc.ActionIcon(
                        dmc.Text("CSV", size="xs", fw=600),
                        id="otvs-table-export",
                        variant="subtle", color="gray", size="sm",
                    ),
                ], justify="space-between", mb="sm"),
                dmc.Box(id="otvs-table-container"),
            ],
            p="md", radius="md", shadow="xs", withBorder=True,
        ),

        dcc.Interval(id="otvs-interval", interval=300_000, n_intervals=0),
    ],
)


# ---------------------------------------------------------------------------
# Callbacks
# ---------------------------------------------------------------------------
_N_LOADING = 4  # volume, physician, dept, coverage


@callback(
    Output("otvs-kpi-total", "children"),
    Output("otvs-kpi-patients", "children"),
    Output("otvs-kpi-avg", "children"),
    Output("otvs-kpi-self-rate", "children"),
    Output("otvs-kpi-physicians", "children"),
    Output("otvs-chart-volume", "figure"),
    Output("otvs-chart-physician", "figure"),
    Output("otvs-chart-dept", "figure"),
    Output("otvs-chart-coverage", "figure"),
    Output("otvs-table-container", "children"),
    Output("otvs-volume-loading", "visible"),
    Output("otvs-physician-loading", "visible"),
    Output("otvs-dept-loading", "visible"),
    Output("otvs-coverage-loading", "visible"),
    Input("otvs-interval", "n_intervals"),
    Input("otvs-filter-date-preset", "value"),
    Input("otvs-filter-department", "value"),
    Input("otvs-filter-physician", "value"),
)
def update_otvs(_n, date_preset, departments, physicians):
    from data.loader import load_weekly_visits

    empty = empty_figure("No data available")
    na_kpi = kpi_card("--", "N/A")

    try:
        weekly = load_weekly_visits()
    except Exception:
        return (na_kpi,) * 5 + (empty,) * 4 + ([],) + (False,) * _N_LOADING

    if weekly.empty:
        return (na_kpi,) * 5 + (empty,) * 4 + ([],) + (False,) * _N_LOADING

    # --- Date range ---
    date_col = "AppointmentDateTime"
    if date_col not in weekly.columns:
        return (na_kpi,) * 5 + (empty,) * 4 + ([],) + (False,) * _N_LOADING

    last_date = weekly[date_col].max()

    if date_preset == "ytd":
        start = pd.Timestamp(last_date.year, 1, 1)
    elif date_preset == "12mo":
        start = last_date - timedelta(days=365)
    else:
        start = pd.Timestamp("2000-01-01")

    # --- Filter ---
    df = weekly.copy()
    df = df[(df[date_col] >= start) & (df[date_col] <= last_date)]

    if departments and "Department" in df.columns:
        df = df[df["Department"].isin(departments)]

    if physicians:
        phy_mask = pd.Series(False, index=df.index)
        for col in ["TreatingPhysician", "AppointmentPhysician"]:
            if col in df.columns:
                phy_mask |= df[col].isin(physicians)
        df = df[phy_mask]

    if df.empty:
        return (na_kpi,) * 5 + (empty,) * 4 + ([],) + (False,) * _N_LOADING

    # --- KPIs ---
    total_checks = len(df)
    unique_patients = df["PatientId"].nunique() if "PatientId" in df.columns else 0
    avg_per_patient = total_checks / unique_patients if unique_patients > 0 else 0

    # Self-coverage rate: how often the treating physician does their own check
    if (
        "TreatingPhysician" in df.columns
        and "AppointmentPhysician" in df.columns
    ):
        matched = df.dropna(subset=["TreatingPhysician", "AppointmentPhysician"])
        self_checks = (matched["TreatingPhysician"] == matched["AppointmentPhysician"]).sum()
        self_rate = (self_checks / len(matched) * 100) if len(matched) > 0 else 0
    else:
        self_rate = 0

    active_physicians = 0
    if "AppointmentPhysician" in df.columns:
        active_physicians = df["AppointmentPhysician"].nunique()

    kpi_total = kpi_card("Weekly Checks", f"{total_checks:,}", accent_color=PRIMARY)
    kpi_patients = kpi_card("Unique Patients", f"{unique_patients:,}",
                            accent_color=SEMANTIC_COLORS["info"])
    kpi_avg = kpi_card("Avg Checks / Patient", f"{avg_per_patient:.1f}",
                       accent_color=SEMANTIC_COLORS["info"])
    kpi_self = kpi_card(
        "Self-Coverage Rate", f"{self_rate:.0f}%",
        accent_color=(SEMANTIC_COLORS["success"] if self_rate >= 70
                      else SEMANTIC_COLORS["warning"]),
    )
    kpi_physicians_card = kpi_card("Active Physicians", f"{active_physicians}",
                                   accent_color=PRIMARY)

    # --- Charts ---
    fig_volume = _build_volume_chart(df, date_col)
    fig_physician = _build_physician_chart(df)
    fig_dept = _build_dept_chart(df)
    fig_coverage = _build_coverage_chart(df)

    # --- Table ---
    table = _build_table(df)

    return (
        kpi_total, kpi_patients, kpi_avg, kpi_self, kpi_physicians_card,
        fig_volume, fig_physician, fig_dept, fig_coverage,
        table,
        False, False, False, False,
    )


# ---------------------------------------------------------------------------
# Chart builders
# ---------------------------------------------------------------------------
def _build_volume_chart(df, date_col):
    """Stacked bar chart of weekly visit volume by department over time."""
    if df.empty or date_col not in df.columns:
        return empty_figure("No weekly visit data")

    df = df.copy()
    df["week"] = df[date_col].dt.to_period("W").dt.to_timestamp()

    fig = go.Figure()

    if "Department" in df.columns:
        weekly_counts = df.groupby(["week", "Department"]).size().unstack(fill_value=0)
        for dept in DEPARTMENTS:
            if dept in weekly_counts.columns:
                fig.add_trace(go.Bar(
                    x=weekly_counts.index,
                    y=weekly_counts[dept],
                    name=dept,
                    marker_color=DEPARTMENT_COLORS.get(dept, PRIMARY),
                ))
    else:
        weekly_counts = df.groupby("week").size()
        fig.add_trace(go.Bar(
            x=weekly_counts.index,
            y=weekly_counts.values,
            marker_color=PRIMARY,
        ))

    apply_default_layout(fig, barmode="stack", height=320)
    fig.update_layout(
        yaxis_title="Weekly Checks",
        margin=dict(l=48, r=16, t=16, b=48),
    )
    return fig


def _build_physician_chart(df):
    """Bar chart of visit count by appointment physician."""
    if df.empty or "AppointmentPhysician" not in df.columns:
        return empty_figure("No physician data")

    counts = (
        df["AppointmentPhysician"]
        .dropna()
        .value_counts()
        .head(10)
        .sort_values()
    )

    if counts.empty:
        return empty_figure("No physician data")

    # Use short last names for display
    short_names = [n.split(",")[0] for n in counts.index]

    fig = go.Figure(go.Bar(
        x=counts.values,
        y=short_names,
        orientation="h",
        marker_color=PRIMARY,
    ))
    apply_default_layout(fig, height=320)
    fig.update_layout(
        xaxis_title="Weekly Checks",
        margin=dict(l=100, r=16, t=16, b=48),
    )
    return fig


def _build_dept_chart(df):
    """Donut chart of visit volume by department."""
    if df.empty or "Department" not in df.columns:
        return empty_figure("No department data")

    counts = df["Department"].value_counts()
    colors = [DEPARTMENT_COLORS.get(d, PRIMARY) for d in counts.index]

    fig = go.Figure(go.Pie(
        labels=counts.index,
        values=counts.values,
        marker_colors=colors,
        hole=0.4,
        textinfo="label+percent+value",
        textposition="outside",
    ))
    apply_default_layout(fig, height=320)
    fig.update_layout(showlegend=False, margin=dict(l=16, r=16, t=16, b=16))
    return fig


def _build_coverage_chart(df):
    """Heatmap of treating physician vs appointment physician."""
    if df.empty:
        return empty_figure("No weekly visit data")

    if "TreatingPhysician" not in df.columns or "AppointmentPhysician" not in df.columns:
        return empty_figure("Physician columns not available")

    coverage = (
        df.groupby(["TreatingPhysician", "AppointmentPhysician"])
        .size()
        .unstack(fill_value=0)
    )

    if coverage.empty:
        return empty_figure("No coverage data")

    # Filter to known physicians
    rows = [p for p in PHYSICIANS if p in coverage.index]
    cols = [p for p in PHYSICIANS if p in coverage.columns]

    if not rows or not cols:
        return empty_figure("No physician coverage data")

    coverage = coverage.loc[rows, cols]

    # Short last names for axis labels
    short_rows = [r.split(",")[0] for r in rows]
    short_cols = [c.split(",")[0] for c in cols]

    fig = go.Figure(go.Heatmap(
        x=short_cols,
        y=short_rows,
        z=coverage.values,
        colorscale="Blues",
        text=coverage.values,
        texttemplate="%{text}",
        textfont={"size": 12},
        hovertemplate=(
            "Treating: %{y}<br>Appointment: %{x}<br>Count: %{z}<extra></extra>"
        ),
    ))
    apply_default_layout(fig, height=320)
    fig.update_layout(
        xaxis_title="Appointment Physician",
        yaxis_title="Treating Physician",
        margin=dict(l=100, r=16, t=16, b=80),
    )
    return fig


# ---------------------------------------------------------------------------
# Table builder
# ---------------------------------------------------------------------------
def _build_table(df):
    """AG Grid table of weekly visit records."""
    if df.empty:
        return dmc.Text("No weekly visit data available",
                        c=NEUTRAL["text_muted"], ta="center", py="xl")

    display_cols = [
        {"field": "PatientFullName", "headerName": "Patient"},
        {"field": "AppointmentDateTime", "headerName": "Date"},
        {"field": "Department", "headerName": "Department"},
        {"field": "AppointmentPhysician", "headerName": "Appt Physician"},
        {"field": "TreatingPhysician", "headerName": "Treating Physician"},
        {"field": "ActivityName", "headerName": "Activity"},
        {"field": "ProcedureCodes", "headerName": "CPT"},
        {"field": "DurationMinutes", "headerName": "Duration (min)"},
    ]

    existing_cols = [c for c in display_cols if c["field"] in df.columns]

    table_df = df.head(500).copy()
    if "AppointmentDateTime" in table_df.columns and pd.api.types.is_datetime64_any_dtype(table_df["AppointmentDateTime"]):
        table_df["AppointmentDateTime"] = table_df["AppointmentDateTime"].dt.strftime("%m/%d/%Y %I:%M %p")
    table_df = table_df.fillna("--")

    return dag.AgGrid(
        id="otvs-detail-grid",
        rowData=table_df.to_dict("records"),
        columnDefs=existing_cols,
        defaultColDef={"sortable": True, "filter": True, "resizable": True},
        dashGridOptions={
            "pagination": True,
            "paginationPageSize": 25,
            "domLayout": "autoHeight",
        },
        className="ag-theme-alpine",
    )
