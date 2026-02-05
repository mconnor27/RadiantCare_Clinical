"""Operations page — treatment volume trends, operating hours ribbons, upcoming schedule."""

import dash
import dash_mantine_components as dmc
from dash import callback, Input, Output, dcc
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
from datetime import datetime, timedelta

from config.settings import (
    DEPARTMENTS, DEPARTMENT_COLORS, MACHINE_MAP, CHART_COLORWAY,
    PRIMARY, DEFAULT_LAYOUT, FONT_FAMILY,
)
from components.filter_bar import filter_bar, date_presets, department_chips, physician_select
from components.kpi_card import kpi_card
from utils.charts import apply_default_layout, empty_figure, dept_color

dash.register_page(__name__, path="/operations", name="Operations", order=1)

# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------
layout = dmc.Stack(
    gap="md",
    children=[
        dmc.Title("Operations", order=2, c="#7C2A83", ta="center", fw=700, py="sm"),
        filter_bar("operations"),

        # KPI row
        dmc.Grid(id="ops-kpi-row", gutter="md", children=[
            dmc.GridCol(id="ops-kpi-total", span={"base": 6, "md": 3}),
            dmc.GridCol(id="ops-kpi-daily-avg", span={"base": 6, "md": 3}),
            dmc.GridCol(id="ops-kpi-new-starts", span={"base": 6, "md": 3}),
            dmc.GridCol(id="ops-kpi-utilization", span={"base": 6, "md": 3}),
        ]),

        # Treatment Appointments (completed) chart — full width
        dmc.Paper(
            children=[
                dmc.Group(
                    justify="space-between", mb="sm",
                    children=[
                        dmc.Text("Treatment Appointments (completed)", size="sm", fw=500, c="#6B7280"),
                        dmc.SegmentedControl(
                            id="ops-volume-agg",
                            data=[{"value": "W", "label": "Weekly"}, {"value": "M", "label": "Monthly"}],
                            value="W", size="xs",
                        ),
                    ],
                ),
                dcc.Graph(id="ops-chart-volume", config={"displayModeBar": False}),
            ],
            p="md", radius="md", shadow="xs", withBorder=True,
        ),

        # Operating Hours Ribbon — full width, stacked subplots
        dmc.Paper(
            children=[
                dmc.Text("Daily Operating Hours by Site", size="sm", fw=500, c="#6B7280", mb="sm"),
                dcc.Graph(id="ops-chart-ribbon", config={"displayModeBar": False}),
            ],
            p="md", radius="md", shadow="xs", withBorder=True,
        ),

        # Upcoming 2 Weeks heatmap + Availability row
        dmc.Grid(gutter="md", children=[
            dmc.GridCol(
                dmc.Paper(
                    children=[
                        dmc.Text("Upcoming 2 Weeks — Appointment Density", size="sm", fw=500, c="#6B7280", mb="sm"),
                        dcc.Graph(id="ops-chart-upcoming", config={"displayModeBar": False}),
                    ],
                    p="md", radius="md", shadow="xs", withBorder=True,
                ),
                span={"base": 12, "md": 6},
            ),
            dmc.GridCol(
                dmc.Paper(
                    children=[
                        dmc.Text("Exam & Sim Availability (Next 2 Wks)", size="sm", fw=500, c="#6B7280", mb="sm"),
                        dcc.Graph(id="ops-chart-availability", config={"displayModeBar": False}),
                    ],
                    p="md", radius="md", shadow="xs", withBorder=True,
                ),
                span={"base": 12, "md": 6},
            ),
        ]),

        dcc.Interval(id="ops-interval", interval=300_000, n_intervals=0),
    ],
)


# ---------------------------------------------------------------------------
# Callbacks
# ---------------------------------------------------------------------------

@callback(
    Output("ops-kpi-total", "children"),
    Output("ops-kpi-daily-avg", "children"),
    Output("ops-kpi-new-starts", "children"),
    Output("ops-kpi-utilization", "children"),
    Output("ops-chart-volume", "figure"),
    Output("ops-chart-ribbon", "figure"),
    Output("ops-chart-upcoming", "figure"),
    Output("ops-chart-availability", "figure"),
    Input("ops-interval", "n_intervals"),
    Input("ops-volume-agg", "value"),
    Input("operations-filter-department", "value"),
    Input("operations-filter-date-preset", "value"),
    Input("operations-filter-daterange", "value"),
    Input("operations-filter-physician", "value"),
)
def update_operations(_n, agg, departments, date_preset, daterange, _physicians):
    from data.loader import (
        load_treatment, load_daily_volume, load_daily_volume_future,
        load_availability, load_courses,
    )

    today = pd.Timestamp.now().normalize()

    # Date range — explicit range overrides preset
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

    # --- Load aggregated treatment data ---
    try:
        tx = load_treatment()
        # Filter to site-level departments only (exclude machine-level like "Lacey - 21EX")
        site_depts = [d for d in tx["Department"].unique() if d in DEPARTMENTS]
        tx_sites = tx[tx["Department"].isin(site_depts)]

        if departments:
            tx_sites = tx_sites[tx_sites["Department"].isin(departments)]
        tx_period = tx_sites[
            (tx_sites["ScheduledDate"] >= start) &
            (tx_sites["ScheduledDate"] <= end)
        ]
    except Exception:
        tx_sites = pd.DataFrame()
        tx_period = pd.DataFrame()

    # --- KPIs ---
    if not tx_period.empty and "CompletedAppointments" in tx_period.columns:
        total = int(tx_period["CompletedAppointments"].sum())
        days_in_range = max((end - start).days, 1)
        daily_avg = round(total / days_in_range, 1)
    else:
        total = 0
        daily_avg = 0.0

    try:
        courses = load_courses()
        if departments:
            courses = courses[courses["Department"].isin(departments)]
        new_starts = len(courses[courses["CourseStartDate"] >= start])
    except Exception:
        new_starts = 0

    kpi_total = kpi_card("Total Treatments", f"{total:,}", accent_color=PRIMARY)
    kpi_avg = kpi_card("Daily Average", str(daily_avg))
    kpi_starts = kpi_card("New Starts (courses)", str(new_starts))
    kpi_util = kpi_card("Utilization", "N/A")

    # --- Volume trend chart (uses aggregated Treatment data) ---
    fig_volume = _build_volume_trend(tx_period, agg, departments)

    # --- Operating hours ribbon (uses Daily Volume for start/end times) ---
    fig_ribbon = _build_ribbon(departments, start)

    # --- Upcoming 2 weeks heatmap ---
    fig_upcoming = _build_upcoming_heatmap(departments)

    # --- Availability chart ---
    fig_avail = _build_availability()

    return kpi_total, kpi_avg, kpi_starts, kpi_util, fig_volume, fig_ribbon, fig_upcoming, fig_avail


def _build_volume_trend(tx, agg, departments):
    """Stacked bar of treatment volume by department using aggregated data."""
    if tx.empty or "ScheduledDate" not in tx.columns or "CompletedAppointments" not in tx.columns:
        return empty_figure("No treatment data")

    tx = tx.copy()
    tx["period"] = tx["ScheduledDate"].dt.to_period(agg).dt.to_timestamp()

    fig = go.Figure()
    for dept in (departments or DEPARTMENTS):
        dept_data = tx[tx["Department"] == dept]
        if dept_data.empty:
            continue
        counts = dept_data.groupby("period")["CompletedAppointments"].sum().reset_index()
        fig.add_trace(go.Bar(
            x=counts["period"], y=counts["CompletedAppointments"],
            name=dept, marker_color=dept_color(dept),
        ))

    apply_default_layout(fig, barmode="stack", height=350)
    fig.update_layout(
        xaxis_title="Period", yaxis_title="Appointments",
        margin=dict(l=48, r=16, t=16, b=48),
    )
    return fig


def _build_ribbon(departments, start):
    """Operating hours ribbon chart using Daily Volume data (has actual start/end times)."""
    from data.loader import load_daily_volume

    try:
        dv = load_daily_volume()
        dv = dv[dv["ScheduledDate"] >= start]

        sites = departments if departments else DEPARTMENTS
        # Filter to site-level departments only
        dv_sites = dv[dv["Department"].isin(sites)]

        if dv_sites.empty:
            return empty_figure("No daily volume data for ribbon chart")

        fig = make_subplots(
            rows=len(sites), cols=1,
            shared_xaxes=True,
            vertical_spacing=0.06,
            subplot_titles=sites,
        )

        for i, site in enumerate(sites, 1):
            site_data = dv_sites[dv_sites["Department"] == site].copy()
            if site_data.empty:
                continue

            # Parse time columns
            for col in ["FirstActualStart", "LastActualEnd", "FirstScheduledStart", "LastScheduledEnd"]:
                if col in site_data.columns:
                    site_data[col] = pd.to_datetime(site_data[col], errors="coerce")

            # Prefer actual times, fall back to scheduled
            start_col = "FirstActualStart" if "FirstActualStart" in site_data.columns else "FirstScheduledStart"
            end_col = "LastActualEnd" if "LastActualEnd" in site_data.columns else "LastScheduledEnd"

            site_data = site_data.dropna(subset=[start_col, end_col])
            if site_data.empty:
                continue

            site_data["start_hour"] = site_data[start_col].dt.hour + site_data[start_col].dt.minute / 60
            site_data["end_hour"] = site_data[end_col].dt.hour + site_data[end_col].dt.minute / 60
            site_data = site_data.sort_values("ScheduledDate")

            color = dept_color(site)
            hex_c = color.lstrip("#")
            r, g, b = int(hex_c[0:2], 16), int(hex_c[2:4], 16), int(hex_c[4:6], 16)
            fill = f"rgba({r},{g},{b},0.3)"

            # Upper bound (latest end)
            fig.add_trace(go.Scatter(
                x=site_data["ScheduledDate"], y=site_data["end_hour"],
                mode="lines", line=dict(width=0),
                showlegend=False, hoverinfo="skip",
            ), row=i, col=1)

            # Lower bound (earliest start) with fill
            fig.add_trace(go.Scatter(
                x=site_data["ScheduledDate"], y=site_data["start_hour"],
                mode="lines", line=dict(width=0),
                fill="tonexty", fillcolor=fill,
                name=site, showlegend=False,
                hovertemplate="Date: %{x}<br>Start: %{y:.1f}h<extra></extra>",
            ), row=i, col=1)

            fig.update_yaxes(
                title_text="Time of Day", range=[6, 20],
                tickvals=[8, 10, 12, 14, 16, 18],
                ticktext=["8am", "10am", "12pm", "2pm", "4pm", "6pm"],
                row=i, col=1,
            )

        fig.update_layout(
            height=200 * len(sites) + 60,
            font=dict(family=FONT_FAMILY, size=12),
            plot_bgcolor="#FFFFFF",
            paper_bgcolor="#FFFFFF",
            margin=dict(l=60, r=16, t=40, b=40),
            showlegend=False,
        )
        return fig

    except Exception:
        return empty_figure("No treatment data for ribbon chart")


def _build_upcoming_heatmap(departments):
    """Heatmap of appointment density for the next 2 weeks."""
    from data.loader import load_daily_volume_future

    try:
        df = load_daily_volume_future()
        today = pd.Timestamp.now().normalize()
        two_weeks = today + timedelta(days=14)
        df = df[(df["ScheduledDate"] >= today) & (df["ScheduledDate"] <= two_weeks)]

        if departments:
            df = df[df["Department"].isin(departments)]

        # Filter to site-level departments
        df = df[df["Department"].isin(DEPARTMENTS)]

        if df.empty:
            return empty_figure("No upcoming schedule data")

        count_col = "AppointmentCount" if "AppointmentCount" in df.columns else df.columns[0]
        pivot = df.pivot_table(
            index="Department", columns="ScheduledDate",
            values=count_col,
            aggfunc="sum", fill_value=0,
        )

        fig = go.Figure(go.Heatmap(
            z=pivot.values,
            x=[d.strftime("%m/%d %a") for d in pivot.columns],
            y=pivot.index.tolist(),
            colorscale=[[0, "#F3E8F5"], [1, "#7C2A83"]],
            hovertemplate="Site: %{y}<br>Date: %{x}<br>Appointments: %{z}<extra></extra>",
        ))

        apply_default_layout(fig, height=220)
        fig.update_layout(margin=dict(l=80, r=16, t=16, b=48))
        return fig

    except Exception:
        return empty_figure("Future volume data unavailable")


def _build_availability():
    """Exam & Sim availability chart for next 2 weeks."""
    from data.loader import load_availability

    try:
        avail = load_availability()
        today = pd.Timestamp.now().normalize()
        two_weeks = today + timedelta(days=14)
        avail = avail[(avail["SlotDate"] >= today) & (avail["SlotDate"] <= two_weeks)]

        if avail.empty:
            return empty_figure("No availability data")

        # Group by date and category (Exam vs Sim)
        group_col = "Category" if "Category" in avail.columns else None
        if group_col:
            grouped = avail.groupby(["SlotDate", group_col]).size().reset_index(name="slots")
            fig = go.Figure()
            for stype in grouped[group_col].unique():
                sdata = grouped[grouped[group_col] == stype]
                fig.add_trace(go.Bar(
                    x=sdata["SlotDate"].dt.strftime("%m/%d"),
                    y=sdata["slots"],
                    name=stype,
                ))
            apply_default_layout(fig, barmode="group", height=220)
        else:
            grouped = avail.groupby("SlotDate").size().reset_index(name="slots")
            fig = go.Figure(go.Bar(
                x=grouped["SlotDate"].dt.strftime("%m/%d"),
                y=grouped["slots"],
                marker_color=PRIMARY,
            ))
            apply_default_layout(fig, height=220)

        fig.update_layout(margin=dict(l=48, r=16, t=16, b=48))
        return fig

    except Exception:
        return empty_figure("Availability data unavailable")
