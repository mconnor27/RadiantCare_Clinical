"""Plans page -- fraction progress, technique usage, plan status."""

import dash
import dash_mantine_components as dmc
import dash_ag_grid as dag
from dash import callback, Input, Output, dcc
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
import numpy as np
from datetime import timedelta

from config.settings import (
    PHYSICIANS, DEPARTMENTS, DEPARTMENT_COLORS, CHART_COLORWAY, PRIMARY,
    DEFAULT_LAYOUT, FONT_FAMILY, SEMANTIC_COLORS, NEUTRAL,
    DEFAULT_COLUMN_DEFS, DEFAULT_GRID_OPTIONS,
)
from components.filter_bar import filter_bar, date_presets, department_chips, physician_select
from components.kpi_card import kpi_card
from utils.charts import apply_default_layout, empty_figure, dept_color, color_for_index

dash.register_page(__name__, path="/plans", name="Plans", order=10)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _preset_start(last_date, preset):
    """Compute period start date from a preset string (data-relative)."""
    if preset == "ytd":
        return pd.Timestamp(last_date.year, 1, 1)
    elif preset == "12mo":
        return last_date - timedelta(days=365)
    else:  # "all"
        return pd.Timestamp.min


def _load_and_prepare():
    """Load plans data and add computed columns."""
    from data.loader import load_plans

    df = load_plans()
    if df.empty:
        return df

    # Exclude "Do Not Use" plans
    if "PlanSetupId" in df.columns:
        df = df[~df["PlanSetupId"].str.contains("DNU", case=False, na=False)]

    # Computed columns
    df["PctComplete"] = (
        df["NoFractionsDelivered"]
        / df["NoFractionsPlanned"].replace(0, np.nan)
        * 100
    ).round(1)
    df["IsActive"] = df["NoFractionsRemaining"].fillna(0) > 0

    return df


def _apply_filters(df, date_preset, departments, physicians, status):
    """Apply all filter bar selections to the dataframe."""
    if df.empty:
        return df

    # Date filter (based on PlanCreationDate)
    if "PlanCreationDate" in df.columns:
        last_date = df["PlanCreationDate"].dt.normalize().max()
        start = _preset_start(last_date, date_preset)
        if start != pd.Timestamp.min:
            df = df[df["PlanCreationDate"] >= start]

    # Department filter
    if departments and "Department" in df.columns:
        df = df[df["Department"].isin(departments)]

    # Physician filter
    if physicians and "TreatingPhysician" in df.columns:
        df = df[df["TreatingPhysician"].isin(physicians)]

    # Status filter
    if status == "active":
        df = df[df["IsActive"] == True]  # noqa: E712
    elif status == "completed":
        df = df[df["IsActive"] == False]  # noqa: E712

    return df


# ---------------------------------------------------------------------------
# Chart builders
# ---------------------------------------------------------------------------

def _build_fraction_progress(df):
    """Horizontal bar chart showing delivered vs remaining for active plans."""
    active = df[df["IsActive"] == True].copy()  # noqa: E712
    if active.empty:
        return empty_figure("No active plans for selected filters")

    # Sort by remaining fractions descending, take top 20
    active = active.nlargest(20, "NoFractionsRemaining")
    # Reverse for bottom-up display (largest at top)
    active = active.iloc[::-1]

    # Build label: patient name + plan
    active["Label"] = (
        active["PatientFullName"].fillna("Unknown")
        + " - "
        + active["PlanSetupId"].fillna("")
    )

    fig = go.Figure()

    # Delivered bars
    fig.add_trace(go.Bar(
        y=active["Label"],
        x=active["NoFractionsDelivered"].fillna(0),
        name="Delivered",
        orientation="h",
        marker_color=CHART_COLORWAY[1],
        hovertemplate="%{y}<br>Delivered: %{x}<extra></extra>",
    ))

    # Remaining bars
    fig.add_trace(go.Bar(
        y=active["Label"],
        x=active["NoFractionsRemaining"].fillna(0),
        name="Remaining",
        orientation="h",
        marker_color=CHART_COLORWAY[1],
        marker_opacity=0.3,
        hovertemplate="%{y}<br>Remaining: %{x}<extra></extra>",
    ))

    apply_default_layout(fig)
    fig.update_layout(
        barmode="stack",
        height=380,
        margin=dict(l=160, r=8, t=8, b=32),
        xaxis_title="Fractions",
        yaxis=dict(tickfont=dict(size=10)),
        legend=dict(
            orientation="h", yanchor="bottom", y=1.02,
            xanchor="left", x=0, font=dict(size=11),
        ),
    )
    return fig


def _build_technique_donut(df):
    """Donut chart of treatment technique distribution."""
    if df.empty or "TreatmentTechnique" not in df.columns:
        return empty_figure("No technique data available")

    tech_counts = df["TreatmentTechnique"].fillna("Unknown").value_counts()
    if tech_counts.empty:
        return empty_figure("No technique data available")

    colors = [color_for_index(i) for i in range(len(tech_counts))]

    fig = go.Figure(go.Pie(
        labels=tech_counts.index.tolist(),
        values=tech_counts.values.tolist(),
        hole=0.5,
        marker=dict(colors=colors),
        textinfo="label+percent",
        textposition="outside",
        hovertemplate="%{label}: %{value} plans (%{percent})<extra></extra>",
    ))

    apply_default_layout(fig)
    fig.update_layout(
        height=380,
        margin=dict(l=8, r=8, t=8, b=8),
        showlegend=False,
    )
    return fig


def _build_plans_over_time(df):
    """Bar chart of plans created per month, colored by technique."""
    if df.empty or "PlanCreationDate" not in df.columns:
        return empty_figure("No plan creation data available")

    df_valid = df[df["PlanCreationDate"].notna()].copy()
    if df_valid.empty:
        return empty_figure("No plan creation data available")

    df_valid["Month"] = df_valid["PlanCreationDate"].dt.to_period("M").dt.to_timestamp()
    df_valid["Technique"] = df_valid["TreatmentTechnique"].fillna("Unknown")

    monthly = (
        df_valid.groupby(["Month", "Technique"])
        .size()
        .reset_index(name="Count")
    )

    techniques = monthly["Technique"].unique().tolist()

    fig = go.Figure()
    for i, tech in enumerate(techniques):
        tech_data = monthly[monthly["Technique"] == tech]
        fig.add_trace(go.Bar(
            x=tech_data["Month"],
            y=tech_data["Count"],
            name=tech,
            marker_color=color_for_index(i),
            hovertemplate="%{x|%b %Y}<br>%{fullData.name}: %{y}<extra></extra>",
        ))

    apply_default_layout(fig)
    fig.update_layout(
        barmode="stack",
        height=380,
        xaxis_title=None,
        yaxis_title="Plans Created",
        legend=dict(
            orientation="h", yanchor="bottom", y=1.02,
            xanchor="left", x=0, font=dict(size=11),
        ),
    )
    return fig


def _build_duration_box(df):
    """Box plot of treatment duration by technique (completed plans only)."""
    completed = df[df["IsActive"] == False].copy()  # noqa: E712
    if completed.empty or "TreatmentDurationDays" not in completed.columns:
        return empty_figure("No completed plan data for duration analysis")

    completed = completed[completed["TreatmentDurationDays"].notna()]
    completed["Technique"] = completed["TreatmentTechnique"].fillna("Unknown")
    if completed.empty:
        return empty_figure("No duration data available")

    techniques = completed["Technique"].unique().tolist()

    fig = go.Figure()
    for i, tech in enumerate(techniques):
        tech_data = completed[completed["Technique"] == tech]
        fig.add_trace(go.Box(
            y=tech_data["TreatmentDurationDays"],
            name=tech,
            marker_color=color_for_index(i),
            boxmean=True,
            hoverinfo="y+name",
        ))

    apply_default_layout(fig)
    fig.update_layout(
        height=380,
        yaxis_title="Duration (days)",
        showlegend=False,
    )
    return fig


def _build_detail_table(df):
    """AG Grid detail table for plan records."""
    if df.empty:
        return dmc.Text("No plan data available", c="#9CA3AF", ta="center", py="xl")

    display_cols = [
        "PatientFullName", "CourseId", "PlanSetupId", "PlanCreationDate",
        "ClinicalStatus", "TreatmentTechnique", "NoFractionsPlanned",
        "NoFractionsDelivered", "NoFractionsRemaining", "PctComplete",
        "TreatmentDurationDays", "Department", "Machines", "PrescriptionSite",
    ]
    # Only include columns that actually exist
    display_cols = [c for c in display_cols if c in df.columns]

    table_df = df[display_cols].copy()

    # Format PlanCreationDate
    if "PlanCreationDate" in table_df.columns:
        table_df["PlanCreationDate"] = table_df["PlanCreationDate"].dt.strftime("%Y-%m-%d")

    col_labels = {
        "PatientFullName": "Patient",
        "CourseId": "Course",
        "PlanSetupId": "Plan Name",
        "PlanCreationDate": "Created",
        "ClinicalStatus": "Status",
        "TreatmentTechnique": "Technique",
        "NoFractionsPlanned": "Planned Fx",
        "NoFractionsDelivered": "Delivered Fx",
        "NoFractionsRemaining": "Remaining Fx",
        "PctComplete": "% Complete",
        "TreatmentDurationDays": "Duration (d)",
        "Department": "Department",
        "Machines": "Machine(s)",
        "PrescriptionSite": "Rx Site",
    }

    column_defs = []
    for col in display_cols:
        col_def = {
            "field": col,
            "headerName": col_labels.get(col, col),
        }
        # Numeric formatting
        if col in ("NoFractionsPlanned", "NoFractionsDelivered",
                    "NoFractionsRemaining", "TreatmentDurationDays"):
            col_def["type"] = "numericColumn"
            col_def["width"] = 110
        elif col == "PctComplete":
            col_def["type"] = "numericColumn"
            col_def["width"] = 110
            col_def["valueFormatter"] = {
                "function": "params.value != null ? params.value + '%' : ''"
            }
            col_def["cellStyle"] = {
                "function": (
                    "params.value > 90"
                    " ? {'color': '#10B981', 'fontWeight': '600'}"
                    " : params.value === 0 || params.value == null"
                    " ? {'color': '#F59E0B', 'fontWeight': '600'}"
                    " : {}"
                )
            }
        elif col == "PatientFullName":
            col_def["width"] = 160
            col_def["pinned"] = "left"
        elif col == "PlanSetupId":
            col_def["width"] = 140
        elif col == "PlanCreationDate":
            col_def["width"] = 110
        elif col == "ClinicalStatus":
            col_def["width"] = 100
        elif col == "TreatmentTechnique":
            col_def["width"] = 100
        elif col == "PrescriptionSite":
            col_def["width"] = 150
        elif col == "Machines":
            col_def["width"] = 140
        column_defs.append(col_def)

    return dag.AgGrid(
        id="plans-detail-grid",
        rowData=table_df.to_dict("records"),
        columnDefs=column_defs,
        defaultColDef=DEFAULT_COLUMN_DEFS,
        dashGridOptions={
            **DEFAULT_GRID_OPTIONS,
            "paginationPageSize": 25,
        },
        style={"height": "500px"},
        className="ag-theme-alpine",
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
                dmc.Title("Plans", order=2, className="page-title"),
                filter_bar(
                    "plans",
                    children=[
                        date_presets("plans"),
                        department_chips("plans"),
                        physician_select("plans"),
                        dmc.SegmentedControl(
                            id="plans-filter-status",
                            data=[
                                {"value": "all", "label": "All"},
                                {"value": "active", "label": "Active"},
                                {"value": "completed", "label": "Completed"},
                            ],
                            value="all",
                            size="sm",
                        ),
                    ],
                ),
            ],
        ),

        # KPI row
        dmc.Grid(
            id="plans-kpi-row",
            gutter=16,
            children=[],
        ),

        # Chart row 1: Fraction Progress + Technique Mix
        dmc.Grid(
            gutter=16,
            children=[
                dmc.GridCol(
                    span={"base": 12, "md": 6},
                    children=dmc.Paper(
                        children=[
                            dmc.Text(
                                "Fraction Progress (Active Plans)",
                                size="sm", fw=500, c="#6B7280", mb="sm",
                            ),
                            dcc.Graph(
                                id="plans-chart-fraction-progress",
                                config={"displayModeBar": False},
                            ),
                        ],
                        p="sm", radius="md", shadow="xs", withBorder=True,
                    ),
                ),
                dmc.GridCol(
                    span={"base": 12, "md": 6},
                    children=dmc.Paper(
                        children=[
                            dmc.Text(
                                "Plan Technique Mix",
                                size="sm", fw=500, c="#6B7280", mb="sm",
                            ),
                            dcc.Graph(
                                id="plans-chart-technique-mix",
                                config={"displayModeBar": False},
                            ),
                        ],
                        p="sm", radius="md", shadow="xs", withBorder=True,
                    ),
                ),
            ],
        ),

        # Chart row 2: Plans Created Over Time + Duration by Technique
        dmc.Grid(
            gutter=16,
            children=[
                dmc.GridCol(
                    span={"base": 12, "md": 6},
                    children=dmc.Paper(
                        children=[
                            dmc.Text(
                                "Plans Created Over Time",
                                size="sm", fw=500, c="#6B7280", mb="sm",
                            ),
                            dcc.Graph(
                                id="plans-chart-created-over-time",
                                config={"displayModeBar": False},
                            ),
                        ],
                        p="sm", radius="md", shadow="xs", withBorder=True,
                    ),
                ),
                dmc.GridCol(
                    span={"base": 12, "md": 6},
                    children=dmc.Paper(
                        children=[
                            dmc.Text(
                                "Treatment Duration by Technique",
                                size="sm", fw=500, c="#6B7280", mb="sm",
                            ),
                            dcc.Graph(
                                id="plans-chart-duration-box",
                                config={"displayModeBar": False},
                            ),
                        ],
                        p="sm", radius="md", shadow="xs", withBorder=True,
                    ),
                ),
            ],
        ),

        # Detail table
        dmc.Paper(
            children=[
                dmc.Group(
                    justify="space-between", mb="sm",
                    children=[
                        dmc.Text("Plan Detail", size="sm", fw=500, c="#6B7280"),
                    ],
                ),
                dmc.Box(id="plans-table-container"),
            ],
            p="sm", radius="md", shadow="xs", withBorder=True,
        ),

        # Interval for periodic refresh
        dcc.Interval(id="plans-interval", interval=300_000, n_intervals=0),
    ],
)


# ---------------------------------------------------------------------------
# Main callback
# ---------------------------------------------------------------------------

@callback(
    Output("plans-kpi-row", "children"),
    Output("plans-chart-fraction-progress", "figure"),
    Output("plans-chart-technique-mix", "figure"),
    Output("plans-chart-created-over-time", "figure"),
    Output("plans-chart-duration-box", "figure"),
    Output("plans-table-container", "children"),
    Input("plans-interval", "n_intervals"),
    Input("plans-filter-date-preset", "value"),
    Input("plans-filter-department", "value"),
    Input("plans-filter-physician", "value"),
    Input("plans-filter-status", "value"),
)
def update_plans(_n, date_preset, departments, physicians, status):
    """Update all Plans page components from filters."""
    df = _load_and_prepare()

    if df.empty:
        empty = empty_figure("No plan data available")
        no_data_kpis = [
            dmc.GridCol(
                kpi_card("Active Plans", "N/A"),
                span={"base": 12, "sm": 6, "md": 2.4},
            ),
            dmc.GridCol(
                kpi_card("Total Plans", "N/A"),
                span={"base": 12, "sm": 6, "md": 2.4},
            ),
            dmc.GridCol(
                kpi_card("Median Fx Planned", "N/A"),
                span={"base": 12, "sm": 6, "md": 2.4},
            ),
            dmc.GridCol(
                kpi_card("Avg Fx Remaining", "N/A"),
                span={"base": 12, "sm": 6, "md": 2.4},
            ),
            dmc.GridCol(
                kpi_card("Multi-Machine", "N/A"),
                span={"base": 12, "sm": 6, "md": 2.4},
            ),
        ]
        return (
            no_data_kpis,
            empty, empty, empty, empty,
            dmc.Text("No data available", c="#9CA3AF", ta="center", py="xl"),
        )

    # Apply filters
    filtered = _apply_filters(df, date_preset, departments, physicians, status)

    # -----------------------------------------------------------------------
    # KPI cards
    # -----------------------------------------------------------------------
    active_count = int(filtered["IsActive"].sum()) if not filtered.empty else 0
    total_count = len(filtered)

    median_fx = (
        filtered["NoFractionsPlanned"].median()
        if not filtered.empty and filtered["NoFractionsPlanned"].notna().any()
        else 0
    )

    active_plans = (
        filtered[filtered["IsActive"] == True]  # noqa: E712
        if not filtered.empty
        else pd.DataFrame()
    )
    avg_remaining = (
        active_plans["NoFractionsRemaining"].mean()
        if not active_plans.empty
        and active_plans["NoFractionsRemaining"].notna().any()
        else 0
    )

    multi_machine = 0
    if not filtered.empty and "Machines" in filtered.columns:
        multi_machine = int(
            filtered["Machines"].fillna("").str.contains(",").sum()
        )

    kpis = [
        dmc.GridCol(
            kpi_card(
                "Active Plans", f"{active_count:,}",
                accent_color=CHART_COLORWAY[1],
            ),
            span={"base": 12, "sm": 6, "md": 2.4},
        ),
        dmc.GridCol(
            kpi_card(
                "Total Plans", f"{total_count:,}",
                accent_color=PRIMARY,
            ),
            span={"base": 12, "sm": 6, "md": 2.4},
        ),
        dmc.GridCol(
            kpi_card(
                "Median Fx Planned", f"{median_fx:.0f}",
                accent_color=CHART_COLORWAY[2],
            ),
            span={"base": 12, "sm": 6, "md": 2.4},
        ),
        dmc.GridCol(
            kpi_card(
                "Avg Fx Remaining", f"{avg_remaining:.1f}",
                accent_color=CHART_COLORWAY[4],
            ),
            span={"base": 12, "sm": 6, "md": 2.4},
        ),
        dmc.GridCol(
            kpi_card(
                "Multi-Machine", f"{multi_machine:,}",
                accent_color=CHART_COLORWAY[3],
            ),
            span={"base": 12, "sm": 6, "md": 2.4},
        ),
    ]

    # -----------------------------------------------------------------------
    # Charts
    # -----------------------------------------------------------------------
    fig_fraction = _build_fraction_progress(filtered)
    fig_technique = _build_technique_donut(filtered)
    fig_created = _build_plans_over_time(filtered)
    fig_duration = _build_duration_box(filtered)

    # -----------------------------------------------------------------------
    # Detail table
    # -----------------------------------------------------------------------
    table = _build_detail_table(filtered)

    return kpis, fig_fraction, fig_technique, fig_created, fig_duration, table
