"""Machine Performance page — monitor treatment machine errors, MU delivery
discrepancies, and recovery times across all treatment machines."""

import dash
import dash_mantine_components as dmc
import dash_ag_grid as dag
from dash import callback, Input, Output, dcc
import plotly.graph_objects as go
import pandas as pd
import numpy as np
from datetime import timedelta

from config.settings import (
    DEPARTMENT_COLORS, CHART_COLORWAY, PRIMARY,
    DEFAULT_LAYOUT, FONT_FAMILY, NEUTRAL,
    DEFAULT_COLUMN_DEFS, DEFAULT_GRID_OPTIONS,
)
from components.kpi_card import kpi_card
from utils.charts import apply_default_layout, empty_figure

dash.register_page(__name__, path="/machines", name="Machines", order=8)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MACHINE_DEPT = {
    "21EX": "Lacey",
    "TrueBeamNorth": "Lacey",
    "21iX_CEN": "Centralia",
    "21iX_AB": "Aberdeen",
}

MACHINE_COLORS = {
    "21EX": DEPARTMENT_COLORS["Lacey"],
    "TrueBeamNorth": DEPARTMENT_COLORS["Lacey"],
    "21iX_CEN": DEPARTMENT_COLORS["Centralia"],
    "21iX_AB": DEPARTMENT_COLORS["Aberdeen"],
}


def _machine_color(machine):
    """Return color for a machine based on its department mapping."""
    return MACHINE_COLORS.get(machine, CHART_COLORWAY[0])


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
                dmc.Title("Machine Performance", order=2, className="page-title"),
                dmc.Paper(
                    children=[
                        dmc.Group(
                            children=[
                                dmc.Group(gap=8, align="center", children=[
                                    dmc.Text("Period", size="sm", c="#9CA3AF", fw=500),
                                    dmc.SegmentedControl(
                                        id="machines-filter-date-preset",
                                        data=[
                                            {"value": "ytd", "label": "YTD"},
                                            {"value": "12mo", "label": "12 mo"},
                                            {"value": "all", "label": "All"},
                                        ],
                                        value="12mo", size="sm",
                                    ),
                                ]),
                                dmc.Group(gap=8, align="center", children=[
                                    dmc.Text("Machine", size="sm", c="#9CA3AF", fw=500),
                                    dmc.ChipGroup(
                                        id="machines-filter-machine",
                                        children=[
                                            dmc.Chip("21EX", value="21EX", color="blue", variant="filled", size="sm"),
                                            dmc.Chip("21iX_CEN", value="21iX_CEN", color="red", variant="filled", size="sm"),
                                            dmc.Chip("21iX_AB", value="21iX_AB", color="green", variant="filled", size="sm"),
                                        ],
                                        value=["21EX", "21iX_CEN", "21iX_AB"],
                                        multiple=True,
                                    ),
                                ]),
                                dmc.Group(gap=8, align="center", children=[
                                    dmc.Text("Field Type", size="sm", c="#9CA3AF", fw=500),
                                    dmc.SegmentedControl(
                                        id="machines-filter-field-category",
                                        data=[
                                            {"value": "all", "label": "All"},
                                            {"value": "DynamicMLC", "label": "DynamicMLC"},
                                            {"value": "Arc", "label": "Arc"},
                                        ],
                                        value="all", size="sm",
                                    ),
                                ]),
                            ],
                            gap="lg", wrap="wrap",
                        ),
                    ],
                    p="sm", px="md", radius="md", shadow="xs", withBorder=True,
                ),
            ],
        ),

        # ---- KPI row ----
        dmc.Grid(
            id="machines-kpi-row",
            gutter=16,
            children=[],
        ),

        # ---- Chart row 1: Error Count by Machine + Error Trend ----
        dmc.Grid(
            id="machines-charts-row1",
            gutter=16,
            children=[],
        ),

        # ---- Chart row 2: MU Delivery Analysis + Recovery Time Distribution ----
        dmc.Grid(
            id="machines-charts-row2",
            gutter=16,
            children=[],
        ),

        # ---- Detail table ----
        dmc.Paper(
            id="machines-table-container",
            children=[
                dmc.Text("Loading...", c="#9CA3AF", ta="center", py="xl"),
            ],
            p="sm", radius="md", shadow="xs", withBorder=True,
        ),

        # Interval for periodic refresh
        dcc.Interval(id="machines-interval", interval=300_000, n_intervals=0),
    ],
)


# ---------------------------------------------------------------------------
# Helper: Build charts
# ---------------------------------------------------------------------------

def _build_error_count_chart(df):
    """Bar chart of error count by machine, colored by department."""
    if df.empty:
        return empty_figure("No error data for selected filters")

    counts = df.groupby("Machine").size().reset_index(name="Errors")
    counts = counts.sort_values("Errors", ascending=False)

    fig = go.Figure()
    for _, row in counts.iterrows():
        machine = row["Machine"]
        fig.add_trace(go.Bar(
            x=[machine],
            y=[row["Errors"]],
            name=machine,
            marker_color=_machine_color(machine),
            hovertemplate="%{x}<br>Errors: %{y:,}<extra></extra>",
            showlegend=False,
        ))

    fig.update_layout(height=380, bargap=0.3)
    fig.update_yaxes(title_text="Error Count")
    apply_default_layout(fig)
    return fig


def _build_error_trend_chart(df):
    """Line chart of error trend over time, one line per machine."""
    if df.empty:
        return empty_figure("No error data for selected filters")

    df = df.copy()
    # Determine aggregation frequency based on date range
    date_range_days = (df["Date"].max() - df["Date"].min()).days
    if date_range_days > 180:
        df["Period"] = df["Date"].dt.to_period("M").dt.start_time
        period_label = "Month"
    else:
        df["Period"] = df["Date"].dt.to_period("W").dt.start_time
        period_label = "Week"

    trend = df.groupby(["Period", "Machine"]).size().reset_index(name="Errors")

    fig = go.Figure()
    machines = sorted(trend["Machine"].unique())
    for machine in machines:
        m_data = trend[trend["Machine"] == machine].sort_values("Period")
        fig.add_trace(go.Scatter(
            x=m_data["Period"],
            y=m_data["Errors"],
            mode="lines+markers",
            name=machine,
            line=dict(color=_machine_color(machine), width=2),
            marker=dict(size=5),
            hovertemplate=f"{machine}<br>%{{x|%b %d, %Y}}<br>Errors: %{{y:,}}<extra></extra>",
        ))

    fig.update_layout(height=380)
    fig.update_xaxes(title_text=period_label)
    fig.update_yaxes(title_text="Error Count")
    apply_default_layout(fig)
    return fig


def _build_mu_scatter(df):
    """Scatter plot of PlannedMU vs DeliveredMU with 45-degree reference line."""
    if df.empty or "PlannedMU" not in df.columns or "DeliveredMU" not in df.columns:
        return empty_figure("No MU data for selected filters")

    plot_df = df.dropna(subset=["PlannedMU", "DeliveredMU"])
    if plot_df.empty:
        return empty_figure("No MU data for selected filters")

    fig = go.Figure()

    # Add a 45-degree reference line
    mu_max = max(plot_df["PlannedMU"].max(), plot_df["DeliveredMU"].max()) * 1.05
    mu_min = min(plot_df["PlannedMU"].min(), plot_df["DeliveredMU"].min()) * 0.95
    fig.add_trace(go.Scatter(
        x=[mu_min, mu_max],
        y=[mu_min, mu_max],
        mode="lines",
        line=dict(color="#D1D5DB", width=1, dash="dash"),
        showlegend=False,
        hoverinfo="skip",
    ))

    # Add points per machine
    machines = sorted(plot_df["Machine"].unique())
    for machine in machines:
        m_data = plot_df[plot_df["Machine"] == machine]
        fig.add_trace(go.Scatter(
            x=m_data["PlannedMU"],
            y=m_data["DeliveredMU"],
            mode="markers",
            name=machine,
            marker=dict(
                color=_machine_color(machine),
                size=5,
                opacity=0.6,
            ),
            hovertemplate=(
                f"{machine}<br>"
                "Planned: %{x:.1f} MU<br>"
                "Delivered: %{y:.1f} MU<br>"
                "<extra></extra>"
            ),
        ))

    fig.update_layout(height=380)
    fig.update_xaxes(title_text="Planned MU")
    fig.update_yaxes(title_text="Delivered MU")
    apply_default_layout(fig)
    return fig


def _build_recovery_box(df):
    """Box plot of recovery time (ElapsedTimeToNextTreatment) per machine."""
    if df.empty or "ElapsedTimeToNextTreatment" not in df.columns:
        return empty_figure("No recovery time data")

    plot_df = df.dropna(subset=["ElapsedTimeToNextTreatment"])
    if plot_df.empty:
        return empty_figure("No recovery time data")

    fig = go.Figure()
    machines = sorted(plot_df["Machine"].unique())
    for machine in machines:
        m_data = plot_df[plot_df["Machine"] == machine]
        fig.add_trace(go.Box(
            y=m_data["ElapsedTimeToNextTreatment"],
            name=machine,
            marker_color=_machine_color(machine),
            boxmean="sd",
            hovertemplate=(
                f"{machine}<br>"
                "%{y:.1f} min<extra></extra>"
            ),
        ))

    fig.update_layout(height=380, showlegend=False)
    fig.update_yaxes(title_text="Recovery Time (min)")
    apply_default_layout(fig)
    return fig


def _wrap_chart(title, figure, chart_id):
    """Wrap a chart figure in the standard Paper container with a title."""
    return dmc.Paper(
        children=[
            dmc.Text(title, size="sm", fw=500, c="#6B7280", mb="sm"),
            dcc.Graph(
                id=chart_id,
                figure=figure,
                config={"displayModeBar": False},
            ),
        ],
        p="sm", radius="md", shadow="xs", withBorder=True,
    )


# ---------------------------------------------------------------------------
# Main Callback
# ---------------------------------------------------------------------------

@callback(
    Output("machines-kpi-row", "children"),
    Output("machines-charts-row1", "children"),
    Output("machines-charts-row2", "children"),
    Output("machines-table-container", "children"),
    Input("machines-interval", "n_intervals"),
    Input("machines-filter-date-preset", "value"),
    Input("machines-filter-machine", "value"),
    Input("machines-filter-field-category", "value"),
)
def update_machines(_n, date_preset, machines, field_category):
    from data.loader import load_machines

    df = load_machines()
    if df.empty:
        empty_kpis = [
            dmc.GridCol(kpi_card("Total Errors", "N/A"), span={"base": 12, "sm": 6, "md": 2.4}),
            dmc.GridCol(kpi_card("Avg Errors/Day", "N/A"), span={"base": 12, "sm": 6, "md": 2.4}),
            dmc.GridCol(kpi_card("Median Recovery", "N/A"), span={"base": 12, "sm": 6, "md": 2.4}),
            dmc.GridCol(kpi_card("Worst Machine", "N/A"), span={"base": 12, "sm": 6, "md": 2.4}),
            dmc.GridCol(kpi_card("Avg MU Deficit", "N/A"), span={"base": 12, "sm": 6, "md": 2.4}),
        ]
        empty_msg = empty_figure("No machine error data available")
        return (
            empty_kpis,
            [dmc.GridCol(_wrap_chart("Error Count by Machine", empty_msg, "machines-chart-error-count"), span={"base": 12, "md": 6}),
             dmc.GridCol(_wrap_chart("Error Trend", empty_msg, "machines-chart-error-trend"), span={"base": 12, "md": 6})],
            [dmc.GridCol(_wrap_chart("MU Delivery Analysis", empty_msg, "machines-chart-mu-scatter"), span={"base": 12, "md": 6}),
             dmc.GridCol(_wrap_chart("Recovery Time Distribution", empty_msg, "machines-chart-recovery"), span={"base": 12, "md": 6})],
            dmc.Text("No data available", c="#9CA3AF", ta="center", py="xl"),
        )

    # ---- Add computed columns ----
    df["Date"] = df["TreatmentStartTime"].dt.normalize()
    df["MU_Deficit_Pct"] = (
        (df["PlannedMU"] - df["DeliveredMU"]) / df["PlannedMU"] * 100
    ).clip(lower=0)

    # ---- Date filtering (data-relative) ----
    last_date = df["Date"].max()
    if date_preset == "ytd":
        start = pd.Timestamp(last_date.year, 1, 1)
    elif date_preset == "12mo":
        start = last_date - timedelta(days=365)
    else:  # "all"
        start = df["Date"].min()
    df = df[df["Date"] >= start]

    # ---- Machine filter ----
    if machines:
        df = df[df["Machine"].isin(machines)]

    # ---- Field category filter ----
    if field_category and field_category != "all":
        df = df[df["FieldCategory"] == field_category]

    # Guard against fully-filtered-out data
    if df.empty:
        empty_kpis = [
            dmc.GridCol(kpi_card("Total Errors", "0"), span={"base": 12, "sm": 6, "md": 2.4}),
            dmc.GridCol(kpi_card("Avg Errors/Day", "0"), span={"base": 12, "sm": 6, "md": 2.4}),
            dmc.GridCol(kpi_card("Median Recovery", "N/A"), span={"base": 12, "sm": 6, "md": 2.4}),
            dmc.GridCol(kpi_card("Worst Machine", "N/A"), span={"base": 12, "sm": 6, "md": 2.4}),
            dmc.GridCol(kpi_card("Avg MU Deficit", "N/A"), span={"base": 12, "sm": 6, "md": 2.4}),
        ]
        empty_msg = empty_figure("No data for selected filters")
        return (
            empty_kpis,
            [dmc.GridCol(_wrap_chart("Error Count by Machine", empty_msg, "machines-chart-error-count"), span={"base": 12, "md": 6}),
             dmc.GridCol(_wrap_chart("Error Trend", empty_msg, "machines-chart-error-trend"), span={"base": 12, "md": 6})],
            [dmc.GridCol(_wrap_chart("MU Delivery Analysis", empty_msg, "machines-chart-mu-scatter"), span={"base": 12, "md": 6}),
             dmc.GridCol(_wrap_chart("Recovery Time Distribution", empty_msg, "machines-chart-recovery"), span={"base": 12, "md": 6})],
            dmc.Text("No data for selected filters", c="#9CA3AF", ta="center", py="xl"),
        )

    # ---- KPIs ----
    total_errors = len(df)
    distinct_days = df["Date"].nunique()
    avg_errors_day = total_errors / distinct_days if distinct_days > 0 else 0

    recovery_vals = df["ElapsedTimeToNextTreatment"].dropna()
    median_recovery = recovery_vals.median() if len(recovery_vals) > 0 else None

    worst_machine_series = df.groupby("Machine").size()
    worst_machine = worst_machine_series.idxmax() if len(worst_machine_series) > 0 else "N/A"

    mu_deficit_vals = df["MU_Deficit_Pct"].dropna()
    avg_mu_deficit = mu_deficit_vals.mean() if len(mu_deficit_vals) > 0 else None

    kpi_children = [
        dmc.GridCol(
            kpi_card(
                "Total Errors", f"{total_errors:,}",
                accent_color=CHART_COLORWAY[2],
            ),
            span={"base": 12, "sm": 6, "md": 2.4},
        ),
        dmc.GridCol(
            kpi_card(
                "Avg Errors/Day", f"{avg_errors_day:.1f}",
                accent_color=CHART_COLORWAY[4],
            ),
            span={"base": 12, "sm": 6, "md": 2.4},
        ),
        dmc.GridCol(
            kpi_card(
                "Median Recovery",
                f"{median_recovery:.1f} min" if median_recovery is not None else "N/A",
                accent_color=CHART_COLORWAY[1],
            ),
            span={"base": 12, "sm": 6, "md": 2.4},
        ),
        dmc.GridCol(
            kpi_card(
                "Worst Machine", worst_machine,
                accent_color=_machine_color(worst_machine) if worst_machine != "N/A" else PRIMARY,
            ),
            span={"base": 12, "sm": 6, "md": 2.4},
        ),
        dmc.GridCol(
            kpi_card(
                "Avg MU Deficit",
                f"{avg_mu_deficit:.1f}%" if avg_mu_deficit is not None else "N/A",
                accent_color=CHART_COLORWAY[3],
            ),
            span={"base": 12, "sm": 6, "md": 2.4},
        ),
    ]

    # ---- Charts ----
    chart_error_count = _build_error_count_chart(df)
    chart_error_trend = _build_error_trend_chart(df)
    chart_mu_scatter = _build_mu_scatter(df)
    chart_recovery = _build_recovery_box(df)

    charts_row1 = [
        dmc.GridCol(
            _wrap_chart("Error Count by Machine", chart_error_count, "machines-chart-error-count"),
            span={"base": 12, "md": 6},
        ),
        dmc.GridCol(
            _wrap_chart("Error Trend", chart_error_trend, "machines-chart-error-trend"),
            span={"base": 12, "md": 6},
        ),
    ]

    charts_row2 = [
        dmc.GridCol(
            _wrap_chart("MU Delivery Analysis", chart_mu_scatter, "machines-chart-mu-scatter"),
            span={"base": 12, "md": 6},
        ),
        dmc.GridCol(
            _wrap_chart("Recovery Time Distribution", chart_recovery, "machines-chart-recovery"),
            span={"base": 12, "md": 6},
        ),
    ]

    # ---- Detail table ----
    df["Department"] = df["Machine"].map(MACHINE_DEPT)

    table_df = df.sort_values("TreatmentStartTime", ascending=False).copy()
    table_df["DateTime"] = table_df["TreatmentStartTime"].dt.strftime("%Y-%m-%d %H:%M")
    table_df["PatientDisplay"] = table_df["PatientFullName"].fillna("Unknown")
    table_df["MU_Deficit_Display"] = table_df["MU_Deficit_Pct"].round(2)
    table_df["PlannedMU_Display"] = table_df["PlannedMU"].round(1)
    table_df["DeliveredMU_Display"] = table_df["DeliveredMU"].round(1)
    table_df["RecoveryTime"] = table_df["ElapsedTimeToNextTreatment"].round(1)

    records = table_df[[
        "DateTime", "PatientDisplay", "Machine", "PlanName", "FieldId",
        "FractionNumber", "PlannedMU_Display", "DeliveredMU_Display",
        "MU_Deficit_Display", "FieldCategory", "RecoveryTime",
    ]].to_dict("records")

    column_defs = [
        {"field": "DateTime", "headerName": "Date/Time", "width": 150},
        {"field": "PatientDisplay", "headerName": "Patient", "width": 160},
        {"field": "Machine", "headerName": "Machine", "width": 120},
        {"field": "PlanName", "headerName": "Plan", "width": 140},
        {"field": "FieldId", "headerName": "Field", "width": 100},
        {"field": "FractionNumber", "headerName": "Fraction", "width": 90, "type": "numericColumn"},
        {"field": "PlannedMU_Display", "headerName": "Planned MU", "width": 110, "type": "numericColumn",
         "valueFormatter": {"function": "d3.format(',.1f')(params.value)"}},
        {"field": "DeliveredMU_Display", "headerName": "Delivered MU", "width": 120, "type": "numericColumn",
         "valueFormatter": {"function": "d3.format(',.1f')(params.value)"}},
        {"field": "MU_Deficit_Display", "headerName": "MU Deficit (%)", "width": 120, "type": "numericColumn",
         "valueFormatter": {"function": "d3.format('.2f')(params.value) + '%'"}},
        {"field": "FieldCategory", "headerName": "Field Category", "width": 130},
        {"field": "RecoveryTime", "headerName": "Recovery (min)", "width": 120, "type": "numericColumn",
         "valueFormatter": {"function": "params.value != null ? d3.format('.1f')(params.value) : ''"}},
    ]

    table = dmc.Stack(
        gap="sm",
        children=[
            dmc.Text("Error Detail", size="sm", fw=500, c="#6B7280"),
            dag.AgGrid(
                id="machines-detail-table",
                rowData=records,
                columnDefs=column_defs,
                defaultColDef=DEFAULT_COLUMN_DEFS,
                dashGridOptions={**DEFAULT_GRID_OPTIONS},
                style={"height": "500px"},
            ),
        ],
    )

    return kpi_children, charts_row1, charts_row2, table
