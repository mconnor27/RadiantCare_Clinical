"""Clinic Visits page — visit volumes, lead times, conversion rates, and detail grid."""

import dash
import dash_mantine_components as dmc
import dash_ag_grid as dag
from dash import callback, Input, Output, dcc
import plotly.graph_objects as go
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

from config.settings import (
    DEPARTMENTS, DEPARTMENT_COLORS, PHYSICIANS, CHART_COLORWAY,
    PRIMARY, DEFAULT_LAYOUT, FONT_FAMILY, DEFAULT_COLUMN_DEFS, DEFAULT_GRID_OPTIONS,
)
from components.filter_bar import (
    filter_bar, date_presets, department_chips, physician_select, date_range_picker,
)
from components.kpi_card import kpi_card
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
    gap="md",
    children=[
        dmc.Title("Clinic Visits", order=2, c="#7C2A83", ta="center", fw=700, py="sm"),

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

        # KPI row — 6 cards
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
                                dmc.SegmentedControl(
                                    id="cv-volume-agg",
                                    data=[
                                        {"value": "W", "label": "Weekly"},
                                        {"value": "M", "label": "Monthly"},
                                    ],
                                    value="W",
                                    size="xs",
                                ),
                            ],
                        ),
                        dcc.Graph(id="cv-chart-volume", config={"displayModeBar": False}),
                    ],
                    p="md", radius="md", shadow="xs", withBorder=True,
                ),
                span={"base": 12, "md": 6},
            ),
            dmc.GridCol(
                dmc.Paper(
                    children=[
                        dmc.Text("Lead Time Trend (median days)", size="sm", fw=500, c="#6B7280", mb="sm"),
                        dcc.Graph(id="cv-chart-lead-time", config={"displayModeBar": False}),
                    ],
                    p="md", radius="md", shadow="xs", withBorder=True,
                ),
                span={"base": 12, "md": 6},
            ),
        ]),

        # Row 2: Consult -> Sim Conversion (full width)
        dmc.Paper(
            children=[
                dmc.Text("Consult to Simulation Conversion Rate", size="sm", fw=500, c="#6B7280", mb="sm"),
                dcc.Graph(id="cv-chart-conversion", config={"displayModeBar": False}),
            ],
            p="md", radius="md", shadow="xs", withBorder=True,
        ),

        # Row 3: Cancel Rate (1/3) + Diagnosis Mix (1/3) + Physician Load (1/3)
        dmc.Grid(gutter="md", children=[
            dmc.GridCol(
                dmc.Paper(
                    children=[
                        dmc.Text("Cancel / No-Show Rate", size="sm", fw=500, c="#6B7280", mb="sm"),
                        dcc.Graph(id="cv-chart-cancel-rate", config={"displayModeBar": False}),
                    ],
                    p="md", radius="md", shadow="xs", withBorder=True,
                ),
                span={"base": 12, "md": 4},
            ),
            dmc.GridCol(
                dmc.Paper(
                    children=[
                        dmc.Text("Diagnosis Mix (Consults)", size="sm", fw=500, c="#6B7280", mb="sm"),
                        dcc.Graph(id="cv-chart-diagnosis", config={"displayModeBar": False}),
                    ],
                    p="md", radius="md", shadow="xs", withBorder=True,
                ),
                span={"base": 12, "md": 4},
            ),
            dmc.GridCol(
                dmc.Paper(
                    children=[
                        dmc.Text("Physician Visit Load", size="sm", fw=500, c="#6B7280", mb="sm"),
                        dcc.Graph(id="cv-chart-physician-load", config={"displayModeBar": False}),
                    ],
                    p="md", radius="md", shadow="xs", withBorder=True,
                ),
                span={"base": 12, "md": 4},
            ),
        ]),

        # Detail table — full width
        dmc.Paper(
            children=[
                dmc.Text("Visit Details", size="sm", fw=500, c="#6B7280", mb="sm"),
                dmc.Skeleton(
                    id="cv-table-container",
                    height=300,
                    visible=False,
                    children=[],
                ),
            ],
            p="md", radius="md", shadow="xs", withBorder=True,
        ),

        dcc.Interval(id="cv-interval", interval=300_000, n_intervals=0),
    ],
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _classify_visit_type(activity_name):
    """Classify a visit based on ActivityName into Consult, Follow-Up, or Virtual."""
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


def _apply_filters(df, departments, physicians, visit_type, status, start, end):
    """Apply all filter selections to the clinic visits dataframe."""
    if df.empty:
        return df

    dff = df.copy()

    # Date range
    if "ScheduledDateTime" in dff.columns:
        if start is not None:
            dff = dff[dff["ScheduledDateTime"] >= pd.Timestamp(start)]
        if end is not None:
            dff = dff[dff["ScheduledDateTime"] <= pd.Timestamp(end)]

    # Departments
    if departments and "Department" in dff.columns:
        dff = dff[dff["Department"].isin(departments)]

    # Physicians
    if physicians and "AppointmentPhysician" in dff.columns:
        dff = dff[dff["AppointmentPhysician"].isin(physicians)]

    # Visit type
    if visit_type and visit_type != "All" and "VisitType" in dff.columns:
        dff = dff[dff["VisitType"] == visit_type]

    # Status
    if status and status != "All" and "Status" in dff.columns:
        dff = dff[dff["Status"].str.lower() == status.lower()]

    return dff


# ---------------------------------------------------------------------------
# Callback
# ---------------------------------------------------------------------------

@callback(
    Output("cv-kpi-total", "children"),
    Output("cv-kpi-consults", "children"),
    Output("cv-kpi-followups", "children"),
    Output("cv-kpi-lead-time", "children"),
    Output("cv-kpi-sim-conversion", "children"),
    Output("cv-kpi-days-to-sim", "children"),
    Output("cv-chart-volume", "figure"),
    Output("cv-chart-lead-time", "figure"),
    Output("cv-chart-conversion", "figure"),
    Output("cv-chart-cancel-rate", "figure"),
    Output("cv-chart-diagnosis", "figure"),
    Output("cv-chart-physician-load", "figure"),
    Output("cv-table-container", "children"),
    Input("cv-interval", "n_intervals"),
    Input("cv-volume-agg", "value"),
    Input("clinic-visits-filter-date-preset", "value"),
    Input("clinic-visits-filter-daterange", "value"),
    Input("clinic-visits-filter-department", "value"),
    Input("clinic-visits-filter-physician", "value"),
    Input("clinic-visits-filter-visit-type", "value"),
    Input("clinic-visits-filter-status", "value"),
)
def update_clinic_visits(
    _n, agg, date_preset, date_range, departments, physicians, visit_type, status
):
    from data.loader import load_clinic_visits, load_diagnosis

    # Fallback outputs
    na_kpi = kpi_card("--", "N/A")
    empty = empty_figure()

    try:
        df = load_clinic_visits()
    except Exception:
        return (na_kpi,) * 6 + (empty,) * 6 + ([],)

    if df.empty:
        return (na_kpi,) * 6 + (empty,) * 6 + ([],)

    # Classify visit types
    if "ActivityName" in df.columns:
        df["VisitType"] = df["ActivityName"].apply(_classify_visit_type)
    else:
        df["VisitType"] = "Other"

    # Resolve date range
    today = pd.Timestamp.now().normalize()

    if date_range and len(date_range) == 2 and date_range[0] and date_range[1]:
        start = pd.Timestamp(date_range[0])
        end = pd.Timestamp(date_range[1])
    elif date_preset == "ytd":
        start = pd.Timestamp(today.year, 1, 1)
        end = today
    elif date_preset == "12mo":
        start = today - timedelta(days=365)
        end = today
    else:
        start = pd.Timestamp("2020-01-01")
        end = today

    # Apply filters (status filter for most views is "Completed" unless "All")
    dff = _apply_filters(df, departments, physicians, visit_type, status, start, end)

    # For cancel-rate chart, we need unfiltered-by-status data within date/dept/physician
    dff_all_status = _apply_filters(df, departments, physicians, visit_type, "All", start, end)

    # ------------------------------------------------------------------
    # KPIs
    # ------------------------------------------------------------------
    total_visits = len(dff)
    consult_count = len(dff[dff["VisitType"] == "Consult"]) if "VisitType" in dff.columns else 0
    followup_count = len(dff[dff["VisitType"] == "Follow-Up"]) if "VisitType" in dff.columns else 0

    # Lead time — median DaysFromCreatedToAppt
    if "DaysFromCreatedToAppt" in dff.columns:
        lead_vals = pd.to_numeric(dff["DaysFromCreatedToAppt"], errors="coerce").dropna()
        lead_time_str = f"{lead_vals.median():.0f}" if len(lead_vals) > 0 else "N/A"
    else:
        lead_time_str = "N/A"

    # Sim conversion rate — % of consults where HasSimulationWithin180Days == 1
    consults_df = dff[dff["VisitType"] == "Consult"] if "VisitType" in dff.columns else pd.DataFrame()
    if "HasSimulationWithin180Days" in consults_df.columns and len(consults_df) > 0:
        sim_flag = pd.to_numeric(consults_df["HasSimulationWithin180Days"], errors="coerce").fillna(0)
        sim_rate = sim_flag.mean() * 100
        sim_rate_str = f"{sim_rate:.1f}%"
    else:
        sim_rate_str = "N/A"

    # Median days to sim
    if "DaysToSimulation" in consults_df.columns and len(consults_df) > 0:
        days_sim = pd.to_numeric(consults_df["DaysToSimulation"], errors="coerce").dropna()
        days_sim_str = f"{days_sim.median():.0f}" if len(days_sim) > 0 else "N/A"
    else:
        days_sim_str = "N/A"

    kpi_total = kpi_card("Total Visits", f"{total_visits:,}", accent_color=PRIMARY)
    kpi_consults = kpi_card("Consults", f"{consult_count:,}")
    kpi_followups = kpi_card("Follow-Ups", f"{followup_count:,}")
    kpi_lead = kpi_card("Lead Time (median days)", lead_time_str)
    kpi_sim_conv = kpi_card("Sim Conversion Rate", sim_rate_str)
    kpi_days_sim = kpi_card("Median Days to Sim", days_sim_str)

    # ------------------------------------------------------------------
    # Charts
    # ------------------------------------------------------------------
    fig_volume = _build_volume_trend(dff, agg)
    fig_lead = _build_lead_time_trend(dff, departments)
    fig_conversion = _build_conversion_chart(dff, departments)
    fig_cancel = _build_cancel_rate(dff_all_status)
    fig_diagnosis = _build_diagnosis_mix(dff)
    fig_physician = _build_physician_load(dff)

    # ------------------------------------------------------------------
    # Detail table
    # ------------------------------------------------------------------
    table = _build_detail_table(dff)

    return (
        kpi_total, kpi_consults, kpi_followups, kpi_lead, kpi_sim_conv, kpi_days_sim,
        fig_volume, fig_lead, fig_conversion, fig_cancel, fig_diagnosis, fig_physician,
        table,
    )


# ---------------------------------------------------------------------------
# Chart builders
# ---------------------------------------------------------------------------

def _build_volume_trend(dff, agg):
    """Stacked bar of visit volume by visit type, weekly or monthly."""
    try:
        if dff.empty or "ScheduledDateTime" not in dff.columns:
            return empty_figure()

        dff = dff.copy()
        dff["period"] = dff["ScheduledDateTime"].dt.to_period(agg).dt.to_timestamp()

        fig = go.Figure()
        type_colors = {
            "Consult": CHART_COLORWAY[0],
            "Follow-Up": CHART_COLORWAY[1],
            "Virtual": CHART_COLORWAY[3],
            "Other": CHART_COLORWAY[4],
        }

        for vtype in ["Consult", "Follow-Up", "Virtual", "Other"]:
            subset = dff[dff["VisitType"] == vtype]
            if subset.empty:
                continue
            counts = subset.groupby("period").size().reset_index(name="count")
            fig.add_trace(go.Bar(
                x=counts["period"], y=counts["count"],
                name=vtype, marker_color=type_colors.get(vtype, CHART_COLORWAY[5]),
            ))

        apply_default_layout(fig, barmode="stack", height=350)
        fig.update_layout(
            xaxis_title="Period", yaxis_title="Visits",
            margin=dict(l=48, r=16, t=16, b=48),
        )
        return fig
    except Exception:
        return empty_figure()


def _build_lead_time_trend(dff, departments):
    """Line chart of median DaysFromCreatedToAppt by department over time."""
    try:
        if dff.empty or "ScheduledDateTime" not in dff.columns or "DaysFromCreatedToAppt" not in dff.columns:
            return empty_figure("Lead time data unavailable")

        dff = dff.copy()
        dff["DaysFromCreatedToAppt"] = pd.to_numeric(dff["DaysFromCreatedToAppt"], errors="coerce")
        dff = dff.dropna(subset=["DaysFromCreatedToAppt"])
        dff["month"] = dff["ScheduledDateTime"].dt.to_period("M").dt.to_timestamp()

        if dff.empty:
            return empty_figure("No lead time data")

        fig = go.Figure()
        active_depts = dff["Department"].unique() if "Department" in dff.columns else []

        for dept in (departments or DEPARTMENTS):
            if dept not in active_depts:
                continue
            dept_data = dff[dff["Department"] == dept]
            monthly = dept_data.groupby("month")["DaysFromCreatedToAppt"].median().reset_index()
            fig.add_trace(go.Scatter(
                x=monthly["month"], y=monthly["DaysFromCreatedToAppt"],
                mode="lines+markers", name=dept,
                line=dict(color=dept_color(dept), width=2),
                marker=dict(size=4),
            ))

        apply_default_layout(fig, height=350)
        fig.update_layout(
            xaxis_title="Month", yaxis_title="Median Lead Time (days)",
            margin=dict(l=48, r=16, t=16, b=48),
        )
        return fig
    except Exception:
        return empty_figure()


def _build_conversion_chart(dff, departments):
    """Monthly consult-to-sim conversion rate line, overall + by department."""
    try:
        consults = dff[dff["VisitType"] == "Consult"].copy() if "VisitType" in dff.columns else pd.DataFrame()

        if consults.empty or "HasSimulationWithin180Days" not in consults.columns:
            return empty_figure("Conversion data unavailable")

        consults["HasSimulationWithin180Days"] = pd.to_numeric(
            consults["HasSimulationWithin180Days"], errors="coerce"
        ).fillna(0)
        consults["month"] = consults["ScheduledDateTime"].dt.to_period("M").dt.to_timestamp()

        fig = go.Figure()

        # Overall line
        monthly_all = consults.groupby("month")["HasSimulationWithin180Days"].mean().reset_index()
        monthly_all["rate"] = monthly_all["HasSimulationWithin180Days"] * 100
        fig.add_trace(go.Scatter(
            x=monthly_all["month"], y=monthly_all["rate"],
            mode="lines+markers", name="Overall",
            line=dict(color="#1A1A2E", width=2.5),
            marker=dict(size=5),
        ))

        # Per-department lines
        active_depts = consults["Department"].unique() if "Department" in consults.columns else []
        for dept in (departments or DEPARTMENTS):
            if dept not in active_depts:
                continue
            dept_data = consults[consults["Department"] == dept]
            monthly_dept = dept_data.groupby("month")["HasSimulationWithin180Days"].mean().reset_index()
            monthly_dept["rate"] = monthly_dept["HasSimulationWithin180Days"] * 100
            fig.add_trace(go.Scatter(
                x=monthly_dept["month"], y=monthly_dept["rate"],
                mode="lines", name=dept,
                line=dict(color=dept_color(dept), width=1.5, dash="dash"),
            ))

        apply_default_layout(fig, height=350)
        fig.update_layout(
            xaxis_title="Month", yaxis_title="Conversion Rate (%)",
            margin=dict(l=48, r=16, t=16, b=48),
        )
        return fig
    except Exception:
        return empty_figure()


def _build_cancel_rate(dff_all):
    """Monthly percentage of cancelled visits."""
    try:
        if dff_all.empty or "Status" not in dff_all.columns or "ScheduledDateTime" not in dff_all.columns:
            return empty_figure("Cancel rate data unavailable")

        dff = dff_all.copy()
        dff["month"] = dff["ScheduledDateTime"].dt.to_period("M").dt.to_timestamp()

        monthly_total = dff.groupby("month").size().reset_index(name="total")
        cancelled = dff[dff["Status"].str.lower().isin(["cancelled", "canceled", "no-show", "no show"])]
        monthly_cancel = cancelled.groupby("month").size().reset_index(name="cancelled")

        merged = monthly_total.merge(monthly_cancel, on="month", how="left").fillna(0)
        merged["rate"] = (merged["cancelled"] / merged["total"]) * 100

        fig = go.Figure(go.Bar(
            x=merged["month"], y=merged["rate"],
            marker_color=CHART_COLORWAY[2],
            hovertemplate="Month: %{x}<br>Cancel Rate: %{y:.1f}%<extra></extra>",
        ))

        apply_default_layout(fig, height=300)
        fig.update_layout(
            xaxis_title="Month", yaxis_title="Cancel / No-Show %",
            margin=dict(l=48, r=16, t=16, b=48),
        )
        return fig
    except Exception:
        return empty_figure()


def _build_diagnosis_mix(dff):
    """Horizontal bar chart of consults by diagnosis group."""
    try:
        consults = dff[dff["VisitType"] == "Consult"] if "VisitType" in dff.columns else dff

        # Try to load diagnosis lookup for grouping
        try:
            from data.loader import load_diagnosis
            diag_lookup = load_diagnosis()
        except Exception:
            diag_lookup = pd.DataFrame()

        # Determine diagnosis column
        diag_col = None
        for candidate in ["DiagnosisGroup", "Diagnosis", "DiagnosisCode", "PrimaryDiagnosis"]:
            if candidate in consults.columns:
                diag_col = candidate
                break

        if diag_col is None and not diag_lookup.empty:
            # Try to merge diagnosis info
            merge_key = None
            for key in ["PatientId", "PatientFullName"]:
                if key in consults.columns and key in diag_lookup.columns:
                    merge_key = key
                    break
            if merge_key:
                diag_col_lookup = None
                for candidate in ["DiagnosisGroup", "Diagnosis", "DiagnosisCode"]:
                    if candidate in diag_lookup.columns:
                        diag_col_lookup = candidate
                        break
                if diag_col_lookup:
                    consults = consults.merge(
                        diag_lookup[[merge_key, diag_col_lookup]].drop_duplicates(),
                        on=merge_key, how="left",
                    )
                    diag_col = diag_col_lookup

        if diag_col is None or consults.empty:
            return empty_figure("Diagnosis data unavailable")

        counts = consults[diag_col].value_counts().head(15)
        if counts.empty:
            return empty_figure("No diagnosis data")

        # Sort ascending for horizontal bar (top values at top)
        counts = counts.sort_values(ascending=True)

        fig = go.Figure(go.Bar(
            x=counts.values,
            y=counts.index.astype(str),
            orientation="h",
            marker_color=CHART_COLORWAY[0],
        ))

        apply_default_layout(fig, height=300)
        fig.update_layout(
            xaxis_title="Consult Count",
            yaxis_title="",
            margin=dict(l=140, r=16, t=16, b=48),
        )
        return fig
    except Exception:
        return empty_figure()


def _build_physician_load(dff):
    """Grouped bar chart per physician showing consult vs follow-up counts."""
    try:
        if dff.empty or "AppointmentPhysician" not in dff.columns or "VisitType" not in dff.columns:
            return empty_figure("Physician load data unavailable")

        # Count by physician and visit type
        consults = dff[dff["VisitType"] == "Consult"]
        followups = dff[dff["VisitType"] == "Follow-Up"]

        consult_counts = consults.groupby("AppointmentPhysician").size()
        followup_counts = followups.groupby("AppointmentPhysician").size()

        # Get all physicians with any visits
        all_physicians = sorted(set(consult_counts.index) | set(followup_counts.index))
        if not all_physicians:
            return empty_figure("No physician visit data")

        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=all_physicians,
            y=[consult_counts.get(p, 0) for p in all_physicians],
            name="Consult",
            marker_color=CHART_COLORWAY[0],
        ))
        fig.add_trace(go.Bar(
            x=all_physicians,
            y=[followup_counts.get(p, 0) for p in all_physicians],
            name="Follow-Up",
            marker_color=CHART_COLORWAY[1],
        ))

        apply_default_layout(fig, barmode="group", height=300)
        fig.update_layout(
            xaxis_title="", yaxis_title="Visits",
            margin=dict(l=48, r=16, t=16, b=80),
            xaxis_tickangle=-30,
        )
        return fig
    except Exception:
        return empty_figure()


def _build_detail_table(dff):
    """Build the AG Grid detail table for visit data."""
    try:
        if dff.empty:
            return dmc.Text("No visit data available", c="#9CA3AF", ta="center", py="xl")

        display_cols = []
        col_header_map = {
            "PatientFullName": "Patient",
            "ScheduledDateTime": "Scheduled",
            "Department": "Department",
            "AppointmentPhysician": "Physician",
            "ActivityName": "Activity",
            "VisitType": "Visit Type",
            "Duration": "Duration",
            "Status": "Status",
            "DaysFromCreatedToAppt": "Lead Time (days)",
            "HasSimulationWithin180Days": "Has Sim",
            "DaysToSimulation": "Days to Sim",
        }

        for col in col_header_map:
            if col in dff.columns:
                display_cols.append(col)

        if not display_cols:
            return dmc.Text("No columns available for display", c="#9CA3AF", ta="center", py="xl")

        table_df = dff[display_cols].head(500).copy()

        # Format datetime columns
        for c in table_df.select_dtypes(include=["datetime64"]).columns:
            table_df[c] = table_df[c].dt.strftime("%m/%d/%Y %I:%M %p")

        table_df = table_df.fillna("--")

        column_defs = [
            {"field": c, "headerName": col_header_map.get(c, c)}
            for c in display_cols
        ]

        return dag.AgGrid(
            id="cv-detail-grid",
            rowData=table_df.to_dict("records"),
            columnDefs=column_defs,
            defaultColDef=DEFAULT_COLUMN_DEFS,
            dashGridOptions=DEFAULT_GRID_OPTIONS,
            className="ag-theme-alpine",
        )
    except Exception:
        return dmc.Text("Error loading visit details", c="#9CA3AF", ta="center", py="xl")
