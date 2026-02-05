"""Simulations page — volume trends, timing intervals, schedule ribbons, detail grid."""

import dash
import dash_mantine_components as dmc
from dash import callback, Input, Output, dcc
import dash_ag_grid as dag
import plotly.graph_objects as go
import pandas as pd
import numpy as np
from datetime import timedelta

from config.settings import (
    DEPARTMENTS, DEPARTMENT_COLORS, CHART_COLORWAY,
    PRIMARY, FONT_FAMILY,
)
from components.filter_bar import (
    filter_bar, date_presets, date_range_picker, department_chips, physician_select,
)
from components.kpi_card import kpi_card
from utils.charts import apply_default_layout, empty_figure

dash.register_page(__name__, path="/simulations", name="Simulations", order=4)

PAGE_ID = "sim"

# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------
layout = dmc.Stack(
    gap="md",
    children=[
        dmc.Title("Simulations", order=2, c="#7C2A83", ta="center", fw=700, py="sm"),

        # Filter bar
        filter_bar("sim", children=[
            date_presets("sim"),
            date_range_picker("sim"),
            department_chips("sim"),
            physician_select("sim"),
            dmc.MultiSelect(
                id="sim-filter-simtype",
                placeholder="Sim Type",
                data=[],
                clearable=True,
                size="sm",
                w=220,
            ),
            dmc.ChipGroup(
                children=[
                    dmc.Chip("Completed", value="completed", size="sm", variant="filled"),
                    dmc.Chip("All", value="all", size="sm", variant="filled"),
                ],
                id="sim-filter-status",
                value="all",
                multiple=False,
            ),
        ]),

        # KPI row — 5 cards
        dmc.Grid(id="sim-kpi-row", gutter="md", children=[
            dmc.GridCol(id="sim-kpi-total", span={"base": 6, "md": 2.4}),
            dmc.GridCol(id="sim-kpi-consult-sim", span={"base": 6, "md": 2.4}),
            dmc.GridCol(id="sim-kpi-sim-tx", span={"base": 6, "md": 2.4}),
            dmc.GridCol(id="sim-kpi-consult-tx", span={"base": 6, "md": 2.4}),
            dmc.GridCol(id="sim-kpi-resim", span={"base": 6, "md": 2.4}),
        ]),

        # Row 1: Volume Trend + Timing Intervals (half-width each)
        dmc.Grid(gutter="md", children=[
            dmc.GridCol(
                dmc.Paper(
                    children=[
                        dmc.Group(
                            justify="space-between", mb="sm",
                            children=[
                                dmc.Text("Simulation Volume Trend", size="sm", fw=500, c="#6B7280"),
                                dmc.SegmentedControl(
                                    id="sim-volume-agg",
                                    data=[
                                        {"value": "W", "label": "Weekly"},
                                        {"value": "M", "label": "Monthly"},
                                    ],
                                    value="W", size="xs",
                                ),
                            ],
                        ),
                        dcc.Graph(id="sim-chart-volume", config={"displayModeBar": False}),
                    ],
                    p="md", radius="md", shadow="xs", withBorder=True,
                ),
                span={"base": 12, "md": 6},
            ),
            dmc.GridCol(
                dmc.Paper(
                    children=[
                        dmc.Text("Timing Intervals (monthly median)", size="sm", fw=500, c="#6B7280", mb="sm"),
                        dcc.Graph(id="sim-chart-timing", config={"displayModeBar": False}),
                    ],
                    p="md", radius="md", shadow="xs", withBorder=True,
                ),
                span={"base": 12, "md": 6},
            ),
        ]),

        # Row 2: Sim Type Distribution + Schedule Ribbon (half-width each)
        dmc.Grid(gutter="md", children=[
            dmc.GridCol(
                dmc.Paper(
                    children=[
                        dmc.Text("Sim Type Distribution", size="sm", fw=500, c="#6B7280", mb="sm"),
                        dcc.Graph(id="sim-chart-distribution", config={"displayModeBar": False}),
                    ],
                    p="md", radius="md", shadow="xs", withBorder=True,
                ),
                span={"base": 12, "md": 6},
            ),
            dmc.GridCol(
                dmc.Paper(
                    children=[
                        dmc.Text("Simulation Schedule Ribbon", size="sm", fw=500, c="#6B7280", mb="sm"),
                        dcc.Graph(id="sim-chart-ribbon", config={"displayModeBar": False}),
                    ],
                    p="md", radius="md", shadow="xs", withBorder=True,
                ),
                span={"base": 12, "md": 6},
            ),
        ]),

        # Detail table — full width
        dmc.Paper(
            children=[
                dmc.Text("Simulation Detail", size="sm", fw=500, c="#6B7280", mb="sm"),
                dmc.Box(id="sim-table-container"),
            ],
            p="md", radius="md", shadow="xs", withBorder=True,
        ),

        dcc.Interval(id="sim-interval", interval=300_000, n_intervals=0),
    ],
)


# ---------------------------------------------------------------------------
# Helper: apply date filters
# ---------------------------------------------------------------------------
def _apply_date_filter(df, date_col, date_preset, date_range):
    """Filter dataframe by date preset or explicit date range."""
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

    if date_col in df.columns:
        df = df[(df[date_col] >= start) & (df[date_col] <= end)]
    return df


# ---------------------------------------------------------------------------
# Callback: populate sim type multi-select options
# ---------------------------------------------------------------------------
@callback(
    Output("sim-filter-simtype", "data"),
    Input("sim-interval", "n_intervals"),
)
def populate_simtype_options(_n):
    """Populate sim type filter with unique ActivityName values."""
    try:
        from data.loader import load_simulations
        df = load_simulations()
        if "ActivityName" in df.columns:
            types = sorted(df["ActivityName"].dropna().unique().tolist())
            return [{"value": t, "label": t} for t in types]
    except Exception:
        pass
    return []


# ---------------------------------------------------------------------------
# Main callback
# ---------------------------------------------------------------------------
@callback(
    Output("sim-kpi-total", "children"),
    Output("sim-kpi-consult-sim", "children"),
    Output("sim-kpi-sim-tx", "children"),
    Output("sim-kpi-consult-tx", "children"),
    Output("sim-kpi-resim", "children"),
    Output("sim-chart-volume", "figure"),
    Output("sim-chart-timing", "figure"),
    Output("sim-chart-distribution", "figure"),
    Output("sim-chart-ribbon", "figure"),
    Output("sim-table-container", "children"),
    Input("sim-interval", "n_intervals"),
    Input("sim-volume-agg", "value"),
    Input("sim-filter-department", "value"),
    Input("sim-filter-physician", "value"),
    Input("sim-filter-date-preset", "value"),
    Input("sim-filter-daterange", "value"),
    Input("sim-filter-simtype", "value"),
    Input("sim-filter-status", "value"),
)
def update_simulations(_n, agg, departments, physicians, date_preset, date_range, sim_types, status):
    from data.loader import load_simulations

    na_card = kpi_card("--", "N/A")
    empty = empty_figure()

    try:
        df = load_simulations()
    except Exception:
        return (na_card,) * 5 + (empty,) * 4 + ([],)

    if df.empty:
        return (na_card,) * 5 + (empty,) * 4 + ([],)

    # --- Apply filters ---
    if departments and "Department" in df.columns:
        df = df[df["Department"].isin(departments)]

    if physicians and "SupervisingPhysician" in df.columns:
        df = df[df["SupervisingPhysician"].isin(physicians)]

    if sim_types and "ActivityName" in df.columns:
        df = df[df["ActivityName"].isin(sim_types)]

    if status == "completed" and "Status" in df.columns:
        df = df[df["Status"].str.lower() == "completed"]

    # Keep unfiltered-by-date copy for the ribbon (spans all historical data)
    df_all_dates = df.copy()

    # Apply date filter
    df = _apply_date_filter(df, "ScheduledDateTime", date_preset, date_range)

    if df.empty:
        return (na_card,) * 5 + (empty,) * 4 + ([],)

    # --- KPIs ---
    kpi_total_card = kpi_card("Total Simulations", f"{len(df):,}", accent_color=PRIMARY)

    def _median_days(col):
        if col in df.columns:
            vals = pd.to_numeric(df[col], errors="coerce").dropna()
            if len(vals) > 0:
                return f"{vals.median():.1f}"
        return "N/A"

    kpi_cs = kpi_card(
        "Median Consult-to-Sim",
        f"{_median_days('DaysFromClinicExamToSimulation')} days",
        accent_color=CHART_COLORWAY[1],
    )
    kpi_st = kpi_card(
        "Median Sim-to-Treatment",
        f"{_median_days('DaysFromSimToTreatment')} days",
        accent_color=CHART_COLORWAY[2],
    )
    kpi_ct = kpi_card(
        "Median Consult-to-Treatment",
        f"{_median_days('DaysFromClinicExamToTreatment')} days",
        accent_color=CHART_COLORWAY[3],
    )

    # Re-Sim Rate
    if "ActivityName" in df.columns:
        resim_count = df["ActivityName"].str.contains("Re-Simulation", case=False, na=False).sum()
        total_count = len(df)
        resim_pct = f"{(resim_count / total_count * 100):.1f}%" if total_count > 0 else "N/A"
    else:
        resim_pct = "N/A"
    kpi_resim_card = kpi_card("Re-Sim Rate", resim_pct, accent_color=CHART_COLORWAY[4])

    # --- Charts ---
    fig_volume = _build_volume_trend(df, agg, departments)
    fig_timing = _build_timing_intervals(df)
    fig_distribution = _build_type_distribution(df)
    fig_ribbon = _build_schedule_ribbon(df_all_dates)

    # --- Detail table ---
    table = _build_detail_table(df)

    return (
        kpi_total_card, kpi_cs, kpi_st, kpi_ct, kpi_resim_card,
        fig_volume, fig_timing, fig_distribution, fig_ribbon,
        table,
    )


# ---------------------------------------------------------------------------
# Chart builders
# ---------------------------------------------------------------------------

def _build_volume_trend(df, agg, departments):
    """Stacked bar chart of simulation volume by sim type with weekly/monthly toggle."""
    if df.empty or "ScheduledDateTime" not in df.columns:
        return empty_figure()

    try:
        df = df.copy()
        df["period"] = df["ScheduledDateTime"].dt.to_period(agg).dt.to_timestamp()

        fig = go.Figure()

        if "ActivityName" in df.columns:
            sim_types = sorted(df["ActivityName"].dropna().unique().tolist())
            for i, stype in enumerate(sim_types):
                type_data = df[df["ActivityName"] == stype]
                counts = type_data.groupby("period").size().reset_index(name="count")
                fig.add_trace(go.Bar(
                    x=counts["period"],
                    y=counts["count"],
                    name=stype,
                    marker_color=CHART_COLORWAY[i % len(CHART_COLORWAY)],
                ))
        else:
            counts = df.groupby("period").size().reset_index(name="count")
            fig.add_trace(go.Bar(
                x=counts["period"],
                y=counts["count"],
                name="Simulations",
                marker_color=PRIMARY,
            ))

        apply_default_layout(fig, barmode="stack", height=350)
        fig.update_layout(
            xaxis_title="Period",
            yaxis_title="Simulations",
            margin=dict(l=48, r=16, t=16, b=48),
        )
        return fig

    except Exception:
        return empty_figure("Error building volume trend")


def _build_timing_intervals(df):
    """Three trend lines of monthly median for Consult->Sim, Sim->Treatment, Consult->Treatment."""
    if df.empty or "ScheduledDateTime" not in df.columns:
        return empty_figure()

    try:
        df = df.copy()
        df["month"] = df["ScheduledDateTime"].dt.to_period("M").dt.to_timestamp()

        fig = go.Figure()

        interval_cols = [
            ("DaysFromClinicExamToSimulation", "Consult \u2192 Sim", CHART_COLORWAY[0]),
            ("DaysFromSimToTreatment", "Sim \u2192 Treatment", CHART_COLORWAY[1]),
            ("DaysFromClinicExamToTreatment", "Consult \u2192 Treatment", CHART_COLORWAY[2]),
        ]

        has_data = False
        for col, label, color in interval_cols:
            if col in df.columns:
                temp = df[["month", col]].copy()
                temp[col] = pd.to_numeric(temp[col], errors="coerce")
                temp = temp.dropna(subset=[col])
                if temp.empty:
                    continue
                monthly = temp.groupby("month")[col].median().reset_index()
                fig.add_trace(go.Scatter(
                    x=monthly["month"],
                    y=monthly[col],
                    mode="lines+markers",
                    name=label,
                    line=dict(color=color, width=2),
                    marker=dict(size=5),
                ))
                has_data = True

        if not has_data:
            return empty_figure("No timing interval data available")

        apply_default_layout(fig, height=350)
        fig.update_layout(
            yaxis_title="Median Days",
            margin=dict(l=48, r=16, t=16, b=48),
        )
        return fig

    except Exception:
        return empty_figure("Error building timing intervals")


def _build_type_distribution(df):
    """Horizontal bar chart of counts by ActivityName."""
    if df.empty or "ActivityName" not in df.columns:
        return empty_figure("No sim type data available")

    try:
        counts = df["ActivityName"].value_counts().sort_values(ascending=True)

        colors = [
            CHART_COLORWAY[i % len(CHART_COLORWAY)]
            for i in range(len(counts))
        ]

        fig = go.Figure(go.Bar(
            x=counts.values,
            y=counts.index,
            orientation="h",
            marker_color=colors,
            text=counts.values,
            textposition="auto",
        ))

        apply_default_layout(fig, height=max(350, len(counts) * 30 + 80))
        fig.update_layout(
            xaxis_title="Count",
            yaxis_title="",
            margin=dict(l=180, r=16, t=16, b=48),
        )
        return fig

    except Exception:
        return empty_figure("Error building type distribution")


def _build_schedule_ribbon(df):
    """Ribbon chart showing earliest sim start to latest sim end per day.

    X-axis = dates spanning all historical data.
    Y-axis = time of day (6am-8pm).
    Single ribbon using go.Scatter fill='tonexty'.
    """
    if df.empty or "ScheduledDateTime" not in df.columns:
        return empty_figure("No schedule data for ribbon chart")

    try:
        df = df.copy()
        df["Date"] = df["ScheduledDateTime"].dt.normalize()
        df["TimeHour"] = (
            df["ScheduledDateTime"].dt.hour
            + df["ScheduledDateTime"].dt.minute / 60
        )

        # Compute end time from Duration (minutes) if available
        if "Duration" in df.columns:
            dur_minutes = pd.to_numeric(df["Duration"], errors="coerce").fillna(0)
            df["EndHour"] = df["TimeHour"] + dur_minutes / 60
        else:
            df["EndHour"] = df["TimeHour"]

        daily = df.groupby("Date").agg(
            earliest_start=("TimeHour", "min"),
            latest_end=("EndHour", "max"),
        ).reset_index().sort_values("Date")

        # Clamp values to the display range
        daily["earliest_start"] = daily["earliest_start"].clip(lower=6, upper=20)
        daily["latest_end"] = daily["latest_end"].clip(lower=6, upper=20)

        fig = go.Figure()

        # Upper bound (latest end) — invisible line for fill reference
        fig.add_trace(go.Scatter(
            x=daily["Date"],
            y=daily["latest_end"],
            mode="lines",
            line=dict(width=0),
            showlegend=False,
            hoverinfo="skip",
        ))

        # Lower bound (earliest start) with fill to upper bound
        hex_color = PRIMARY.lstrip("#")
        r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
        ribbon_fill = f"rgba({r},{g},{b},0.3)"

        fig.add_trace(go.Scatter(
            x=daily["Date"],
            y=daily["earliest_start"],
            mode="lines",
            line=dict(width=0),
            fill="tonexty",
            fillcolor=ribbon_fill,
            name="Sim Window",
            hovertemplate=(
                "Date: %{x|%b %d, %Y}<br>"
                "Earliest: %{y:.1f}h<br>"
                "<extra></extra>"
            ),
        ))

        apply_default_layout(fig, height=350)
        fig.update_layout(
            yaxis=dict(
                title="Time of Day",
                range=[6, 20],
                tickvals=[6, 8, 10, 12, 14, 16, 18, 20],
                ticktext=["6am", "8am", "10am", "12pm", "2pm", "4pm", "6pm", "8pm"],
                gridcolor="#F0F0F0",
                linecolor="#E0E0E0",
                showgrid=True,
            ),
            xaxis=dict(
                gridcolor="#F0F0F0",
                linecolor="#E0E0E0",
                showgrid=False,
            ),
            margin=dict(l=60, r=16, t=16, b=48),
        )
        return fig

    except Exception:
        return empty_figure("Error building schedule ribbon")


def _build_detail_table(df):
    """AG Grid table with simulation details."""
    display_cols = [
        "ScheduledDateTime", "Department", "SupervisingPhysician",
        "ActivityName", "Duration", "PatientFullName",
        "DaysFromClinicExamToSimulation", "DaysFromSimToTreatment",
        "DaysFromClinicExamToTreatment",
    ]

    available_cols = [c for c in display_cols if c in df.columns]

    if not available_cols:
        return dmc.Text("No simulation data available", c="#9CA3AF", ta="center", py="xl")

    try:
        table_df = df[available_cols].head(200).copy()

        # Format datetime columns
        for c in table_df.select_dtypes(include=["datetime64"]).columns:
            table_df[c] = table_df[c].dt.strftime("%m/%d/%Y %I:%M %p")

        table_df = table_df.fillna("\u2014")

        # Build friendly header names
        header_map = {
            "ScheduledDateTime": "Scheduled",
            "Department": "Department",
            "SupervisingPhysician": "Physician",
            "ActivityName": "Sim Type",
            "Duration": "Duration (min)",
            "PatientFullName": "Patient",
            "DaysFromClinicExamToSimulation": "Consult\u2192Sim (days)",
            "DaysFromSimToTreatment": "Sim\u2192Tx (days)",
            "DaysFromClinicExamToTreatment": "Consult\u2192Tx (days)",
        }

        column_defs = [
            {"field": c, "headerName": header_map.get(c, c)}
            for c in available_cols
        ]

        return dag.AgGrid(
            id="sim-detail-grid",
            rowData=table_df.to_dict("records"),
            columnDefs=column_defs,
            defaultColDef={"sortable": True, "filter": True, "resizable": True},
            dashGridOptions={
                "pagination": True,
                "paginationPageSize": 50,
                "domLayout": "autoHeight",
            },
            className="ag-theme-alpine",
        )

    except Exception:
        return dmc.Text("Error loading simulation detail", c="#9CA3AF", ta="center", py="xl")
