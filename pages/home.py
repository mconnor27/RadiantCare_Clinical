"""Home page — executive summary with KPIs and physician/site census charts."""

import dash
import dash_mantine_components as dmc
from dash import callback, Input, Output, dcc
import plotly.graph_objects as go
import pandas as pd
from datetime import datetime, timedelta

from config.settings import (
    PHYSICIANS, DEPARTMENTS, DEPARTMENT_COLORS, CHART_COLORWAY, PRIMARY,
    DEFAULT_LAYOUT, FONT_FAMILY,
)
from components.kpi_card import kpi_card
from utils.charts import apply_default_layout, empty_figure

dash.register_page(__name__, path="/", name="Home", order=0)

# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------
layout = dmc.Stack(
    gap="md",
    children=[
        dmc.Title("Home", order=2, c="#7C2A83", ta="center", fw=700, py="sm"),

        # KPI row
        dmc.Grid(
            id="home-kpi-row",
            gutter="md",
            children=[
                dmc.GridCol(id="home-kpi-tx-today", span={"base": 12, "sm": 6, "md": 2}),
                dmc.GridCol(id="home-kpi-sims-week", span={"base": 12, "sm": 6, "md": 2}),
                dmc.GridCol(id="home-kpi-consults-week", span={"base": 12, "sm": 6, "md": 2}),
                dmc.GridCol(id="home-kpi-otv-pass", span={"base": 12, "sm": 6, "md": 2}),
                dmc.GridCol(id="home-kpi-new-starts", span={"base": 12, "sm": 6, "md": 2}),
                dmc.GridCol(id="home-kpi-pipeline", span={"base": 12, "sm": 6, "md": 2}),
            ],
        ),

        # Main charts — physician census and site census
        dmc.Grid(
            gutter="md",
            children=[
                dmc.GridCol(
                    dmc.Paper(
                        children=[
                            dmc.Text(
                                "Active Patients by Physician (90-day rolling)",
                                size="sm", fw=500, c="#6B7280", mb="sm",
                            ),
                            dcc.Graph(id="home-chart-physician", config={"displayModeBar": False}),
                        ],
                        p="md", radius="md", shadow="xs", withBorder=True,
                    ),
                    span={"base": 12, "md": 6},
                ),
                dmc.GridCol(
                    dmc.Paper(
                        children=[
                            dmc.Text(
                                "Active Patients by Site (90-day rolling)",
                                size="sm", fw=500, c="#6B7280", mb="sm",
                            ),
                            dcc.Graph(id="home-chart-site", config={"displayModeBar": False}),
                        ],
                        p="md", radius="md", shadow="xs", withBorder=True,
                    ),
                    span={"base": 12, "md": 6},
                ),
            ],
        ),

        # Interval for periodic refresh
        dcc.Interval(id="home-interval", interval=300_000, n_intervals=0),
    ],
)


# ---------------------------------------------------------------------------
# Callbacks
# ---------------------------------------------------------------------------

@callback(
    Output("home-kpi-tx-today", "children"),
    Output("home-kpi-sims-week", "children"),
    Output("home-kpi-consults-week", "children"),
    Output("home-kpi-otv-pass", "children"),
    Output("home-kpi-new-starts", "children"),
    Output("home-kpi-pipeline", "children"),
    Output("home-chart-physician", "figure"),
    Output("home-chart-site", "figure"),
    Input("home-interval", "n_intervals"),
)
def update_home(_n):
    """Load data and update all home page components.

    KPIs use data-relative dates (last available date) so they show
    meaningful values even when data hasn't been refreshed recently.
    """
    from data.loader import (
        load_treatment, load_treatment_detail, load_simulations,
        load_clinic_visits, load_otvs, load_availability, load_workflow,
        load_courses,
    )

    today = pd.Timestamp.now().normalize()

    # --- Treatment Daily Average (last 30 days of available data) ---
    try:
        tx = load_treatment()
        if not tx.empty and "ScheduledDate" in tx.columns and "CompletedAppointments" in tx.columns:
            last_date = tx["ScheduledDate"].max()
            thirty_ago = last_date - timedelta(days=30)
            tx_recent = tx[tx["ScheduledDate"] >= thirty_ago]
            daily_avg = tx_recent["CompletedAppointments"].sum() / max(tx_recent["ScheduledDate"].nunique(), 1)
            kpi_tx = kpi_card(
                "Treatments / Day (30d avg)",
                f"{daily_avg:.0f}",
                accent_color=PRIMARY,
            )
        else:
            kpi_tx = kpi_card("Treatments / Day", "N/A", accent_color=PRIMARY)
    except Exception:
        kpi_tx = kpi_card("Treatments / Day", "N/A", accent_color=PRIMARY)

    # --- Simulations per Week (last 30 days of data → weekly avg) ---
    try:
        sims = load_simulations()
        if not sims.empty and "ScheduledDateTime" in sims.columns:
            last_sim_date = sims["ScheduledDateTime"].max()
            thirty_ago = last_sim_date - timedelta(days=30)
            sims_recent = sims[sims["ScheduledDateTime"] >= thirty_ago]
            weeks_in_range = max((last_sim_date - thirty_ago).days / 7, 1)
            sims_per_week = len(sims_recent) / weeks_in_range
            kpi_sims = kpi_card("Sims / Week (30d avg)", f"{sims_per_week:.0f}")
        else:
            kpi_sims = kpi_card("Sims / Week", "N/A")
    except Exception:
        kpi_sims = kpi_card("Sims / Week", "N/A")

    # --- Consults per Week (last 30 days of data → weekly avg) ---
    try:
        cv = load_clinic_visits()
        if not cv.empty and "ActivityName" in cv.columns and "ScheduledDateTime" in cv.columns:
            consults = cv[cv["ActivityName"].str.contains("Consult", case=False, na=False)]
            if not consults.empty:
                last_cv_date = consults["ScheduledDateTime"].max()
                thirty_ago = last_cv_date - timedelta(days=30)
                consults_recent = consults[consults["ScheduledDateTime"] >= thirty_ago]
                weeks_in_range = max((last_cv_date - thirty_ago).days / 7, 1)
                consults_per_week = len(consults_recent) / weeks_in_range
                kpi_consults = kpi_card("Consults / Week (30d avg)", f"{consults_per_week:.0f}")
            else:
                kpi_consults = kpi_card("Consults / Week", "0")
        else:
            kpi_consults = kpi_card("Consults / Week", "N/A")
    except Exception:
        kpi_consults = kpi_card("Consults / Week", "N/A")

    # --- OTV Audit Pass Rate ---
    try:
        otvs = load_otvs()
        if "AuditResult" in otvs.columns and len(otvs) > 0:
            pass_rate = (otvs["AuditResult"].str.upper() == "OK").mean() * 100
            kpi_otv = kpi_card("OTV Audit Pass Rate", f"{pass_rate:.1f}%")
        else:
            kpi_otv = kpi_card("OTV Audit Pass Rate", "N/A")
    except Exception:
        kpi_otv = kpi_card("OTV Audit Pass Rate", "N/A")

    # --- New Starts (last 30 days from Courses) ---
    try:
        courses = load_courses()
        if not courses.empty and "CourseStartDate" in courses.columns:
            last_course_date = courses["CourseStartDate"].max()
            thirty_ago = last_course_date - timedelta(days=30)
            new_starts = len(courses[courses["CourseStartDate"] >= thirty_ago])
            kpi_starts = kpi_card("New Starts (30d)", str(new_starts))
        else:
            kpi_starts = kpi_card("New Starts (30d)", "N/A")
    except Exception:
        kpi_starts = kpi_card("New Starts (30d)", "N/A")

    # --- Patients in Pipeline (consults in last 90 days without treatment) ---
    try:
        wf = load_workflow()
        if not wf.empty and "ScheduledDateTime" in wf.columns and "FirstTreatmentDate" in wf.columns:
            last_wf_date = wf["ScheduledDateTime"].max()
            ninety_ago = last_wf_date - timedelta(days=90)
            recent_wf = wf[wf["ScheduledDateTime"] >= ninety_ago]
            in_pipeline = len(recent_wf[recent_wf["FirstTreatmentDate"].isna()])
            kpi_pipe = kpi_card("In Pipeline (90d)", str(in_pipeline))
        else:
            kpi_pipe = kpi_card("In Pipeline", "N/A")
    except Exception:
        kpi_pipe = kpi_card("In Pipeline", "N/A")

    # --- Active Patients Charts (from Treatment-Detail, last 90 days of data) ---
    try:
        td = load_treatment_detail()
        if not td.empty and "ScheduledDateTime" in td.columns:
            last_td_date = td["ScheduledDateTime"].max()
            ninety_ago = last_td_date - timedelta(days=90)
            td_recent = td[td["ScheduledDateTime"] >= ninety_ago].copy()
            td_recent["Date"] = td_recent["ScheduledDateTime"].dt.normalize()

            # By Physician
            fig_md = _build_census_chart(td_recent, "TreatingPhysician", PHYSICIANS, CHART_COLORWAY)
            # By Site
            fig_site = _build_census_chart(td_recent, "Department", DEPARTMENTS,
                                           [DEPARTMENT_COLORS.get(d, "#999") for d in DEPARTMENTS])
        else:
            fig_md = empty_figure("Treatment-Detail data unavailable")
            fig_site = empty_figure("Treatment-Detail data unavailable")
    except Exception:
        fig_md = empty_figure("Treatment-Detail data unavailable")
        fig_site = empty_figure("Treatment-Detail data unavailable")

    return kpi_tx, kpi_sims, kpi_consults, kpi_otv, kpi_starts, kpi_pipe, fig_md, fig_site


def _build_census_chart(df, group_col, groups, colors):
    """Build a daily patient census line chart grouped by a column, with a total line."""
    if group_col not in df.columns or "Date" not in df.columns:
        return empty_figure(f"Column '{group_col}' not found")

    # Use PatientId or PatientMRN for unique patient count
    patient_col = next((c for c in ["PatientId", "PatientMRN"] if c in df.columns), None)
    if patient_col is None:
        return empty_figure("No patient identifier column")

    fig = go.Figure()

    # Per-group lines
    daily = df.groupby(["Date", group_col])[patient_col].nunique().reset_index(name="count")

    for i, grp in enumerate(groups):
        grp_data = daily[daily[group_col] == grp].sort_values("Date")
        if grp_data.empty:
            continue
        fig.add_trace(go.Scatter(
            x=grp_data["Date"],
            y=grp_data["count"],
            name=grp.split(",")[0] if "," in grp else grp,
            mode="lines",
            line=dict(color=colors[i % len(colors)], width=2),
        ))

    # Total line
    total = df.groupby("Date")[patient_col].nunique().reset_index(name="count").sort_values("Date")
    if not total.empty:
        fig.add_trace(go.Scatter(
            x=total["Date"],
            y=total["count"],
            name="Total",
            mode="lines",
            line=dict(color="#1A1A2E", width=2, dash="dot"),
        ))

    apply_default_layout(fig, height=350)
    fig.update_layout(
        xaxis_title="Date",
        yaxis_title="Unique Patients",
        margin=dict(l=48, r=16, t=16, b=48),
    )
    return fig
