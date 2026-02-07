"""Courses page -- treatment course tracking: status, technique mix, duration, fraction tracking."""

import dash
import dash_mantine_components as dmc
import dash_ag_grid as dag
from dash import callback, Input, Output, State, dcc, clientside_callback, ClientsideFunction
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
from components.chart_settings import chart_settings_popover
from utils.charts import apply_default_layout, empty_figure, dept_color, color_for_index

dash.register_page(__name__, path="/courses", name="Courses", order=9)


# ---------------------------------------------------------------------------
# Status colors
# ---------------------------------------------------------------------------
STATUS_COLORS = {
    "ACTIVE": SEMANTIC_COLORS["info"],       # #3B82F6
    "COMPLETED": SEMANTIC_COLORS["success"],  # #10B981
}


# ---------------------------------------------------------------------------
# Helper: Date range from preset
# ---------------------------------------------------------------------------

def _preset_start(last_date, preset):
    """Calculate start date based on preset, relative to last data date."""
    if preset == "ytd":
        return pd.Timestamp(last_date.year, 1, 1)
    elif preset == "12mo":
        return last_date - timedelta(days=365)
    else:  # all
        return pd.Timestamp("2000-01-01")


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
                dmc.Title("Courses", order=2, className="page-title"),
                dmc.Paper(
                    children=[
                        dmc.Group(
                            children=[
                                date_presets("courses"),
                                department_chips("courses"),
                                physician_select("courses"),
                                dmc.SegmentedControl(
                                    id="courses-filter-status",
                                    data=[
                                        {"value": "all", "label": "All"},
                                        {"value": "ACTIVE", "label": "Active"},
                                        {"value": "COMPLETED", "label": "Completed"},
                                    ],
                                    value="all",
                                    size="sm",
                                ),
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
                ),
            ],
        ),

        # KPI row -- 5 cards
        dmc.Grid(
            id="courses-kpi-row",
            gutter=16,
            children=[
                dmc.GridCol(id="courses-kpi-active", span={"base": 6, "sm": 4, "md": 2.4}),
                dmc.GridCol(id="courses-kpi-completed", span={"base": 6, "sm": 4, "md": 2.4}),
                dmc.GridCol(id="courses-kpi-median-duration", span={"base": 6, "sm": 4, "md": 2.4}),
                dmc.GridCol(id="courses-kpi-median-fractions", span={"base": 6, "sm": 4, "md": 2.4}),
                dmc.GridCol(id="courses-kpi-multisite", span={"base": 6, "sm": 4, "md": 2.4}),
            ],
        ),

        # Charts container
        dmc.Stack(id="courses-charts", gap=16),

        # Detail table container
        dmc.Stack(id="courses-table-container", gap=0),

        # Interval for periodic refresh
        dcc.Interval(id="courses-interval", interval=300_000, n_intervals=0),
    ],
)


# ---------------------------------------------------------------------------
# Main Callback
# ---------------------------------------------------------------------------

@callback(
    Output("courses-kpi-row", "children"),
    Output("courses-charts", "children"),
    Output("courses-table-container", "children"),
    Input("courses-interval", "n_intervals"),
    Input("courses-filter-date-preset", "value"),
    Input("courses-filter-department", "value"),
    Input("courses-filter-physician", "value"),
    Input("courses-filter-status", "value"),
)
def update_courses(_n, date_preset, departments, physicians, status):
    from data.loader import load_courses

    df = load_courses()

    if df.empty:
        empty_kpis = [
            dmc.GridCol(kpi_card("Active Courses", "N/A"), span={"base": 6, "sm": 4, "md": 2.4}),
            dmc.GridCol(kpi_card("Completed", "N/A"), span={"base": 6, "sm": 4, "md": 2.4}),
            dmc.GridCol(kpi_card("Median Duration", "N/A"), span={"base": 6, "sm": 4, "md": 2.4}),
            dmc.GridCol(kpi_card("Median Fractions", "N/A"), span={"base": 6, "sm": 4, "md": 2.4}),
            dmc.GridCol(kpi_card("Multi-Site Courses", "N/A"), span={"base": 6, "sm": 4, "md": 2.4}),
        ]
        return empty_kpis, [], []

    # ------------------------------------------------------------------
    # Apply filters
    # ------------------------------------------------------------------

    # Department filter
    if departments and "Department" in df.columns:
        df = df[df["Department"].isin(departments)]

    # Physician filter (TreatingPhysician)
    if physicians and "TreatingPhysician" in df.columns:
        df = df[df["TreatingPhysician"].isin(physicians)]

    # Date filtering (data-relative)
    if "CourseStartDate" in df.columns and df["CourseStartDate"].notna().any():
        last_date = df["CourseStartDate"].dt.normalize().max()
    else:
        last_date = pd.Timestamp.now().normalize()
    start_date = _preset_start(last_date, date_preset)

    # For period-scoped data (charts, completed count), filter by CourseStartDate
    if "CourseStartDate" in df.columns:
        df_period = df[df["CourseStartDate"] >= start_date]
    else:
        df_period = df

    # Status filter (applied after date filter for charts/table; active count uses all data)
    if status and status != "all" and "ClinicalStatus" in df.columns:
        df_status = df_period[df_period["ClinicalStatus"] == status]
    else:
        df_status = df_period

    # ------------------------------------------------------------------
    # KPIs
    # ------------------------------------------------------------------

    # 1. Active Courses -- count across ALL data (not date-filtered),
    #    respecting dept/physician filters only
    if "ClinicalStatus" in df.columns:
        active_count = int((df["ClinicalStatus"] == "ACTIVE").sum())
    else:
        active_count = 0
    kpi_active = kpi_card(
        "Active Courses",
        f"{active_count:,}",
        accent_color=STATUS_COLORS["ACTIVE"],
    )

    # 2. Completed (period) -- count completed in the filtered period
    if "ClinicalStatus" in df_period.columns:
        completed_count = int((df_period["ClinicalStatus"] == "COMPLETED").sum())
    else:
        completed_count = 0
    period_label = {"ytd": "YTD", "12mo": "12 Mo", "all": "All"}.get(date_preset, "12 Mo")
    kpi_completed = kpi_card(
        f"Completed ({period_label})",
        f"{completed_count:,}",
        accent_color=STATUS_COLORS["COMPLETED"],
    )

    # 3. Median Duration -- for completed courses in the period
    completed_df = (
        df_period[df_period["ClinicalStatus"] == "COMPLETED"]
        if "ClinicalStatus" in df_period.columns
        else df_period
    )
    if "TreatmentDurationDays" in completed_df.columns and not completed_df.empty:
        dur_vals = completed_df["TreatmentDurationDays"].dropna()
        median_dur = dur_vals.median() if not dur_vals.empty else 0
        kpi_median_dur = kpi_card(
            "Median Duration",
            f"{median_dur:.0f}",
            value_detail="days",
            accent_color=CHART_COLORWAY[4],
        )
    else:
        kpi_median_dur = kpi_card("Median Duration", "N/A")

    # 4. Median Fractions -- FractionsPrescribed for the period
    if "FractionsPrescribed" in df_period.columns and not df_period.empty:
        frac_vals = df_period["FractionsPrescribed"].dropna()
        median_frac = frac_vals.median() if not frac_vals.empty else 0
        kpi_median_frac = kpi_card(
            "Median Fractions",
            f"{median_frac:.0f}",
            accent_color=CHART_COLORWAY[5],
        )
    else:
        kpi_median_frac = kpi_card("Median Fractions", "N/A")

    # 5. Multi-Site Courses -- where Departments column contains a comma
    if "Departments" in df_period.columns and not df_period.empty:
        multisite_count = int(df_period["Departments"].dropna().str.contains(",").sum())
    else:
        multisite_count = 0
    kpi_multisite = kpi_card(
        "Multi-Site Courses",
        f"{multisite_count:,}",
        accent_color=CHART_COLORWAY[6],
    )

    kpi_children = [
        dmc.GridCol(kpi_active, span={"base": 6, "sm": 4, "md": 2.4}),
        dmc.GridCol(kpi_completed, span={"base": 6, "sm": 4, "md": 2.4}),
        dmc.GridCol(kpi_median_dur, span={"base": 6, "sm": 4, "md": 2.4}),
        dmc.GridCol(kpi_median_frac, span={"base": 6, "sm": 4, "md": 2.4}),
        dmc.GridCol(kpi_multisite, span={"base": 6, "sm": 4, "md": 2.4}),
    ]

    # ------------------------------------------------------------------
    # Charts
    # ------------------------------------------------------------------
    chart_children = []

    # --- Row 1: Course Volume Trend + Technique Mix -----------------------
    row1_charts = []

    # Chart 1: Course Volume Trend (stacked bar by ClinicalStatus, monthly)
    if "CourseStartDate" in df_status.columns and not df_status.empty:
        chart_df = df_status.copy()
        chart_df["Month"] = chart_df["CourseStartDate"].dt.to_period("M").dt.to_timestamp()

        if "ClinicalStatus" in chart_df.columns:
            volume = (
                chart_df.groupby(["Month", "ClinicalStatus"])
                .size()
                .reset_index(name="Count")
            )
            fig_volume = go.Figure()

            for stat in ["COMPLETED", "ACTIVE"]:
                stat_data = volume[volume["ClinicalStatus"] == stat]
                if not stat_data.empty:
                    fig_volume.add_trace(go.Bar(
                        x=stat_data["Month"],
                        y=stat_data["Count"],
                        name=stat.title(),
                        marker_color=STATUS_COLORS.get(stat, CHART_COLORWAY[0]),
                        hovertemplate=(
                            "%{x|%b %Y}: %{y}<extra>" + stat.title() + "</extra>"
                        ),
                    ))

            fig_volume.update_layout(barmode="stack", height=380)
            apply_default_layout(fig_volume)
            fig_volume.update_layout(xaxis_title="", yaxis_title="Courses")
        else:
            volume = chart_df.groupby("Month").size().reset_index(name="Count")
            fig_volume = go.Figure(go.Bar(
                x=volume["Month"],
                y=volume["Count"],
                marker_color=PRIMARY,
                hovertemplate="%{x|%b %Y}: %{y}<extra></extra>",
            ))
            fig_volume.update_layout(height=380)
            apply_default_layout(fig_volume)
    else:
        fig_volume = empty_figure("No course data for selected filters")
        fig_volume.update_layout(height=380)

    row1_charts.append(
        dmc.GridCol(
            span={"base": 12, "md": 6},
            children=dmc.Paper(
                children=[
                    dmc.Text(
                        "Course Volume Trend",
                        size="sm", fw=500, c="#6B7280", mb="sm",
                    ),
                    dcc.Graph(figure=fig_volume, config={"displayModeBar": False}),
                ],
                p="sm", radius="md", shadow="xs", withBorder=True,
            ),
        )
    )

    # Chart 2: Technique Mix (donut)
    if "TreatmentTechniques" in df_status.columns and not df_status.empty:
        techniques = df_status["TreatmentTechniques"].dropna().str.split(",")
        tech_list = []
        for t_list in techniques:
            for t in t_list:
                stripped = t.strip()
                if stripped:
                    tech_list.append(stripped)

        if tech_list:
            tech_counts = pd.Series(tech_list).value_counts().head(10)
            fig_technique = go.Figure(go.Pie(
                labels=tech_counts.index.tolist(),
                values=tech_counts.values.tolist(),
                hole=0.45,
                marker=dict(colors=CHART_COLORWAY[: len(tech_counts)]),
                textinfo="label+percent",
                textposition="outside",
                hovertemplate=(
                    "<b>%{label}</b><br>Count: %{value}<br>"
                    "%{percent}<extra></extra>"
                ),
            ))
            fig_technique.update_layout(height=380, showlegend=False)
            apply_default_layout(fig_technique)
            fig_technique.update_layout(
                margin=dict(l=20, r=20, t=20, b=20),
                showlegend=False,
            )
        else:
            fig_technique = empty_figure("No technique data available")
            fig_technique.update_layout(height=380)
    else:
        fig_technique = empty_figure("No technique data available")
        fig_technique.update_layout(height=380)

    row1_charts.append(
        dmc.GridCol(
            span={"base": 12, "md": 6},
            children=dmc.Paper(
                children=[
                    dmc.Text(
                        "Technique Mix",
                        size="sm", fw=500, c="#6B7280", mb="sm",
                    ),
                    dcc.Graph(figure=fig_technique, config={"displayModeBar": False}),
                ],
                p="sm", radius="md", shadow="xs", withBorder=True,
            ),
        )
    )

    chart_children.append(dmc.Grid(gutter=16, children=row1_charts))

    # --- Row 2: Treatment Site Distribution + Duration Distribution -------
    row2_charts = []

    # Chart 3: Treatment Site Distribution (horizontal bar, top 15)
    if "PrescriptionSites" in df_status.columns and not df_status.empty:
        sites_series = df_status["PrescriptionSites"].dropna()
        if not sites_series.empty:
            site_counts = sites_series.value_counts().head(15).sort_values(ascending=True)
            fig_sites = go.Figure(go.Bar(
                y=site_counts.index.tolist(),
                x=site_counts.values.tolist(),
                orientation="h",
                marker_color=PRIMARY,
                hovertemplate="<b>%{y}</b><br>Count: %{x}<extra></extra>",
            ))
            fig_sites.update_layout(height=380)
            apply_default_layout(fig_sites)
            fig_sites.update_layout(
                yaxis_title="",
                xaxis_title="Courses",
                margin=dict(l=160, r=8, t=8, b=32),
            )
        else:
            fig_sites = empty_figure("No prescription site data")
            fig_sites.update_layout(height=380)
    else:
        fig_sites = empty_figure("No prescription site data")
        fig_sites.update_layout(height=380)

    row2_charts.append(
        dmc.GridCol(
            span={"base": 12, "md": 6},
            children=dmc.Paper(
                children=[
                    dmc.Text(
                        "Treatment Site Distribution",
                        size="sm", fw=500, c="#6B7280", mb="sm",
                    ),
                    dcc.Graph(figure=fig_sites, config={"displayModeBar": False}),
                ],
                p="sm", radius="md", shadow="xs", withBorder=True,
            ),
        )
    )

    # Chart 4: Treatment Duration Distribution (histogram, completed courses)
    if "TreatmentDurationDays" in completed_df.columns and not completed_df.empty:
        dur_data = completed_df["TreatmentDurationDays"].dropna()
        dur_data = dur_data[dur_data > 0]
        if not dur_data.empty:
            fig_duration = go.Figure(go.Histogram(
                x=dur_data,
                nbinsx=30,
                marker_color=STATUS_COLORS["COMPLETED"],
                hovertemplate=(
                    "Duration: %{x} days<br>Count: %{y}<extra></extra>"
                ),
            ))
            fig_duration.update_layout(height=380)
            apply_default_layout(fig_duration)
            fig_duration.update_layout(
                xaxis_title="Duration (days)",
                yaxis_title="Courses",
            )
            # Add median reference line
            med_val = dur_data.median()
            fig_duration.add_vline(
                x=med_val,
                line_dash="dash",
                line_color=NEUTRAL["text_secondary"],
                annotation_text=f"Median: {med_val:.0f}d",
                annotation_position="top right",
                annotation_font_size=11,
                annotation_font_color=NEUTRAL["text_secondary"],
            )
        else:
            fig_duration = empty_figure("No duration data available")
            fig_duration.update_layout(height=380)
    else:
        fig_duration = empty_figure("No duration data available")
        fig_duration.update_layout(height=380)

    row2_charts.append(
        dmc.GridCol(
            span={"base": 12, "md": 6},
            children=dmc.Paper(
                children=[
                    dmc.Text(
                        "Treatment Duration Distribution",
                        size="sm", fw=500, c="#6B7280", mb="sm",
                    ),
                    dcc.Graph(figure=fig_duration, config={"displayModeBar": False}),
                ],
                p="sm", radius="md", shadow="xs", withBorder=True,
            ),
        )
    )

    chart_children.append(dmc.Grid(gutter=16, children=row2_charts))

    # ------------------------------------------------------------------
    # Detail Table (AG Grid)
    # ------------------------------------------------------------------
    table_df = df_status.copy()

    table_cols = [
        "PatientFullName", "CourseId", "CourseStartDate", "ClinicalStatus",
        "TreatingPhysician", "TreatmentTechniques", "FractionsPrescribed",
        "FractionsDelivered", "TreatmentDurationDays", "Department",
        "Machines", "PrescriptionSites",
    ]
    available_cols = [c for c in table_cols if c in table_df.columns]
    table_df = table_df[available_cols].copy()

    # Format date column for display
    if "CourseStartDate" in table_df.columns:
        table_df["CourseStartDate"] = table_df["CourseStartDate"].dt.strftime(
            "%Y-%m-%d"
        )

    records = table_df.to_dict("records")

    column_defs = [
        {"field": "PatientFullName", "headerName": "Patient", "width": 180},
        {"field": "CourseId", "headerName": "Course ID", "width": 120},
        {
            "field": "CourseStartDate",
            "headerName": "Start Date",
            "width": 120,
            "sort": "desc",
        },
        {"field": "ClinicalStatus", "headerName": "Status", "width": 110},
        {"field": "TreatingPhysician", "headerName": "Physician", "width": 160},
        {"field": "TreatmentTechniques", "headerName": "Techniques", "width": 180},
        {
            "field": "FractionsPrescribed",
            "headerName": "Fx Prescribed",
            "width": 120,
            "type": "numericColumn",
        },
        {
            "field": "FractionsDelivered",
            "headerName": "Fx Delivered",
            "width": 110,
            "type": "numericColumn",
        },
        {
            "field": "TreatmentDurationDays",
            "headerName": "Duration (d)",
            "width": 110,
            "type": "numericColumn",
        },
        {"field": "Department", "headerName": "Department", "width": 110},
        {"field": "Machines", "headerName": "Machines", "width": 160},
        {"field": "PrescriptionSites", "headerName": "Rx Sites", "width": 180},
    ]

    table_children = [
        dmc.Paper(
            children=[
                dmc.Group(
                    justify="space-between",
                    mb="sm",
                    children=[
                        dmc.Text(
                            "Course Details", size="sm", fw=500, c="#6B7280",
                        ),
                        dmc.Button(
                            "Export CSV",
                            id="courses-table-export",
                            size="compact-xs",
                            variant="light",
                        ),
                    ],
                ),
                dag.AgGrid(
                    id="courses-detail-table",
                    rowData=records,
                    columnDefs=column_defs,
                    defaultColDef=DEFAULT_COLUMN_DEFS,
                    dashGridOptions={**DEFAULT_GRID_OPTIONS},
                    style={"height": "500px"},
                    className="ag-theme-quartz",
                ),
            ],
            p="md",
            radius="md",
            shadow="xs",
            withBorder=True,
        ),
    ]

    return kpi_children, chart_children, table_children


# ---------------------------------------------------------------------------
# Table CSV Export (clientside)
# ---------------------------------------------------------------------------

clientside_callback(
    """function(n) {
        if (!n) return window.dash_clientside.no_update;
        var gridApi = window.dash_ag_grid
            ? window.dash_ag_grid['courses-detail-table']
            : null;
        if (gridApi && gridApi.api) {
            gridApi.api.exportDataAsCsv({fileName: 'courses_detail.csv'});
        }
        return window.dash_clientside.no_update;
    }""",
    Output("courses-table-export", "n_clicks"),
    Input("courses-table-export", "n_clicks"),
    prevent_initial_call=True,
)
