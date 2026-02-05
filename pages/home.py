"""Home page — executive summary with sparkline KPI cards and rolling census charts."""

import dash
import dash_mantine_components as dmc
from dash import callback, Input, Output, dcc
import plotly.graph_objects as go
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

from config.settings import (
    PHYSICIANS, DEPARTMENTS, DEPARTMENT_COLORS, CHART_COLORWAY, PRIMARY,
    DEFAULT_LAYOUT, FONT_FAMILY, SEMANTIC_COLORS,
)
from components.filter_bar import department_chips
from components.kpi_card import kpi_card
from utils.charts import apply_default_layout, empty_figure, dept_color
from statsmodels.nonparametric.smoothers_lowess import lowess as _lowess


def _apply_loess(series, frac):
    """Apply LOESS smoothing to a pandas Series."""
    if frac <= 0 or len(series) < 4:
        return series
    x_num = np.arange(len(series))
    smoothed = _lowess(series.values.astype(float), x_num, frac=frac, return_sorted=False)
    return pd.Series(smoothed, index=series.index)


def _clean_spark(series, biz_days_only=True, frac=0.2):
    """Clean sparkline series: filter non-business days, apply LOESS smoothing."""
    if biz_days_only and hasattr(series.index, 'weekday'):
        series = series[series.index.weekday < 5]
        series = series[series > 0]
    return _apply_loess(series, frac)


dash.register_page(__name__, path="/", name="Home", order=0)

# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------
layout = dmc.Stack(
    gap="md",
    children=[
        dmc.Title("Home", order=2, c="#7C2A83", ta="center", fw=700, py="sm"),

        # Filter bar — date presets + smoothing slider
        dmc.Paper(
            children=[
                dmc.Group(
                    children=[
                        dmc.SegmentedControl(
                            id="home-filter-date-preset",
                            data=[
                                {"value": "today", "label": "Today"},
                                {"value": "week", "label": "This Week"},
                                {"value": "month", "label": "This Month"},
                                {"value": "ytd", "label": "YTD"},
                                {"value": "12mo", "label": "12 Mo"},
                            ],
                            value="ytd", size="sm",
                        ),
                        department_chips("home"),
                        dmc.Group(gap=8, align="center", children=[
                            dmc.Text("Smoothing", size="sm", c="#9CA3AF", fw=500),
                            dmc.Slider(
                                id="home-filter-smoothing",
                                min=0, max=1, step=0.01, value=0.4,
                                size="xs", w=120,
                                showLabelOnHover=False,
                            ),
                        ]),
                    ],
                    gap="lg", wrap="wrap",
                ),
            ],
            p="sm", px="md", radius="md", shadow="xs", withBorder=True, mb="md",
        ),

        # KPI row — 5 cards with sparklines
        dmc.Grid(
            id="home-kpi-row",
            gutter="md",
            children=[
                dmc.GridCol(id="home-kpi-consults-week", span={"base": 12, "sm": 6, "md": 2.4}),
                dmc.GridCol(id="home-kpi-sims-week", span={"base": 12, "sm": 6, "md": 2.4}),
                dmc.GridCol(id="home-kpi-tx-today", span={"base": 12, "sm": 6, "md": 2.4}),
                dmc.GridCol(id="home-kpi-consult-lead", span={"base": 12, "sm": 6, "md": 2.4}),
                dmc.GridCol(id="home-kpi-sim-lead", span={"base": 12, "sm": 6, "md": 2.4}),
            ],
        ),

        # Census charts — side by side
        dmc.Grid(
            gutter="md",
            children=[
                dmc.GridCol(
                    span={"base": 12, "md": 6},
                    children=dmc.Paper(
                        children=[
                            dmc.Group(
                                justify="space-between", mb="sm",
                                children=[
                                    dmc.Text("Active Patients by Physician", size="sm", fw=500, c="#6B7280"),
                                    dmc.Group(gap="xs", align="center", children=[
                                        dmc.SegmentedControl(
                                            id="home-md-range",
                                            data=[
                                                {"value": "30", "label": "30d"},
                                                {"value": "60", "label": "60d"},
                                                {"value": "90", "label": "90d"},
                                                {"value": "180", "label": "6mo"},
                                                {"value": "365", "label": "1y"},
                                                {"value": "0", "label": "All"},
                                            ],
                                            value="90", size="xs",
                                        ),
                                        dmc.Text("Smooth", size="xs", c="#9CA3AF", fw=500),
                                        dmc.Slider(
                                            id="home-md-smooth",
                                            min=0, max=50, step=1, value=15,
                                            size="xs", w=80,
                                            showLabelOnHover=False,
                                        ),
                                    ]),
                                ],
                            ),
                            dcc.Graph(id="home-chart-physician", config={"displayModeBar": False}),
                        ],
                        p="md", radius="md", shadow="xs", withBorder=True,
                    ),
                ),
                dmc.GridCol(
                    span={"base": 12, "md": 6},
                    children=dmc.Paper(
                        children=[
                            dmc.Group(
                                justify="space-between", mb="sm",
                                children=[
                                    dmc.Text("Active Patients by Site", size="sm", fw=500, c="#6B7280"),
                                    dmc.Group(gap="xs", align="center", children=[
                                        dmc.SegmentedControl(
                                            id="home-site-range",
                                            data=[
                                                {"value": "30", "label": "30d"},
                                                {"value": "60", "label": "60d"},
                                                {"value": "90", "label": "90d"},
                                                {"value": "180", "label": "6mo"},
                                                {"value": "365", "label": "1y"},
                                                {"value": "0", "label": "All"},
                                            ],
                                            value="90", size="xs",
                                        ),
                                        dmc.Text("Smooth", size="xs", c="#9CA3AF", fw=500),
                                        dmc.Slider(
                                            id="home-site-smooth",
                                            min=0, max=50, step=1, value=15,
                                            size="xs", w=80,
                                            showLabelOnHover=False,
                                        ),
                                    ]),
                                ],
                            ),
                            dcc.Graph(id="home-chart-site", config={"displayModeBar": False}),
                        ],
                        p="md", radius="md", shadow="xs", withBorder=True,
                    ),
                ),
            ],
        ),

        # Interval for periodic refresh
        dcc.Interval(id="home-interval", interval=300_000, n_intervals=0),
    ],
)


# ---------------------------------------------------------------------------
# KPI Callback
# ---------------------------------------------------------------------------

@callback(
    Output("home-kpi-consults-week", "children"),
    Output("home-kpi-sims-week", "children"),
    Output("home-kpi-tx-today", "children"),
    Output("home-kpi-consult-lead", "children"),
    Output("home-kpi-sim-lead", "children"),
    Input("home-interval", "n_intervals"),
    Input("home-filter-date-preset", "value"),
    Input("home-filter-smoothing", "value"),
    Input("home-filter-department", "value"),
)
def update_kpis(_n, date_preset, smoothing, departments):
    """Compute all 5 KPI cards with sparklines."""
    from data.loader import load_treatment_detail, load_simulations, load_clinic_visits

    PERIOD_LABELS = {
        "today": "Today", "week": "This Week",
        "month": "This Month", "ytd": "YTD", "12mo": "12 Mo",
    }
    TREND_LABELS = {
        "today": "vs yesterday", "week": "vs last week",
        "month": "vs last month", "ytd": "vs prior year",
        "12mo": "vs prior 12 mo",
    }
    SPARK_FREQ = {
        "today": "D", "week": "D", "month": "D", "ytd": "W", "12mo": "W",
    }
    period_label = PERIOD_LABELS.get(date_preset, "YTD")
    trend_label = TREND_LABELS.get(date_preset, "vs prior")
    spark_freq = SPARK_FREQ.get(date_preset, "W")
    smooth_frac = (smoothing or 0) * 0.5  # slider 0–1 maps to LOESS frac 0–0.5

    def _spark_start(last_date, preset):
        """Compute sparkline start date (different from KPI range start)."""
        if preset == "ytd":
            return pd.Timestamp(last_date.year, 1, 1)
        lookbacks = {"today": 14, "week": 28, "month": 60, "12mo": 365}
        return last_date - timedelta(days=lookbacks.get(preset, 365))

    def _preset_start(last_date, preset):
        if preset == "today":
            return last_date
        elif preset == "week":
            return last_date - timedelta(days=last_date.weekday())
        elif preset == "month":
            return pd.Timestamp(last_date.year, last_date.month, 1)
        elif preset == "12mo":
            return last_date - timedelta(days=365)
        else:  # ytd
            return pd.Timestamp(last_date.year, 1, 1)

    def _prior_range(last_date, preset):
        if preset == "today":
            d = last_date - timedelta(days=1)
            return d, d
        elif preset == "week":
            cs = last_date - timedelta(days=last_date.weekday())
            return cs - timedelta(weeks=1), cs - timedelta(days=1)
        elif preset == "month":
            cs = pd.Timestamp(last_date.year, last_date.month, 1)
            pe = cs - timedelta(days=1)
            return pd.Timestamp(pe.year, pe.month, 1), pe
        elif preset == "12mo":
            return last_date - timedelta(days=730), last_date - timedelta(days=366)
        else:  # ytd
            try:
                pe = pd.Timestamp(last_date.year - 1, last_date.month, last_date.day)
            except ValueError:
                pe = pd.Timestamp(last_date.year - 1, last_date.month, 28)
            return pd.Timestamp(last_date.year - 1, 1, 1), pe

    def _trend(curr, prior, invert=False):
        if prior is None or prior == 0:
            return None, None
        pct = (curr - prior) / prior * 100
        if abs(pct) < 0.5:
            return None, None
        direction = ("down" if pct > 0 else "up") if invert else ("up" if pct > 0 else "down")
        return f"{abs(pct):.0f}%", direction

    def _count_spark(df, date_col, last_date):
        s_start = _spark_start(last_date, date_preset)
        s_data = df[(df[date_col] >= s_start) & (df[date_col] <= last_date)]
        if spark_freq == "W":
            series = s_data.groupby(s_data[date_col].dt.to_period("W").dt.start_time).size()
            return _apply_loess(series, smooth_frac)
        series = s_data.groupby(s_data[date_col].dt.normalize()).size()
        series = series.reindex(pd.date_range(s_start, last_date), fill_value=0)
        return _clean_spark(series, frac=smooth_frac)

    def _lead_spark(df, date_col, lead_col, last_date):
        s_start = _spark_start(last_date, date_preset)
        s_data = df[(df[date_col] >= s_start) & (df[date_col] <= last_date)]
        if spark_freq == "W":
            series = s_data.groupby(s_data[date_col].dt.to_period("W").dt.start_time)[lead_col].mean()
        else:
            series = s_data.groupby(s_data[date_col].dt.normalize())[lead_col].mean()
            if hasattr(series.index, 'weekday'):
                series = series[series.index.weekday < 5]
        return _apply_loess(series, smooth_frac)

    # Load data once
    try:
        td = load_treatment_detail()
        if departments and "Department" in td.columns:
            td = td[td["Department"].isin(departments)]
    except Exception:
        td = pd.DataFrame()
    try:
        sims = load_simulations()
        if departments and "Department" in sims.columns:
            sims = sims[sims["Department"].isin(departments)]
        # Filter to initial and stereotactic simulations only
        if not sims.empty and "ActivityName" in sims.columns:
            sims = sims[
                sims["ActivityName"].str.contains("Initial", case=False, na=False) |
                sims["ActivityName"].str.contains("Stereotactic Simulation", case=False, na=False)
            ]
    except Exception:
        sims = pd.DataFrame()
    try:
        cv = load_clinic_visits()
        if departments and "Department" in cv.columns:
            cv = cv[cv["Department"].isin(departments)]
        consults = cv[cv["ActivityName"].str.contains("Consult", case=False, na=False)] if "ActivityName" in cv.columns else pd.DataFrame()
        # Filter to completed or billed consults
        if not consults.empty:
            completed = consults["Status"].str.contains("Completed", case=False, na=False) if "Status" in consults.columns else pd.Series(False, index=consults.index)
            billed = consults["ProcedureCodes"].notna() & (consults["ProcedureCodes"].astype(str).str.strip() != "") if "ProcedureCodes" in consults.columns else pd.Series(False, index=consults.index)
            consults = consults[completed | billed]
    except Exception:
        consults = pd.DataFrame()

    # --- 1. Consults ---
    if not consults.empty and "ScheduledDateTime" in consults.columns:
        last_cv = consults["ScheduledDateTime"].dt.normalize().max()
        start = _preset_start(last_cv, date_preset)
        curr = len(consults[consults["ScheduledDateTime"] >= start])
        ps, pe = _prior_range(last_cv, date_preset)
        prior = len(consults[(consults["ScheduledDateTime"] >= ps) & (consults["ScheduledDateTime"] <= pe)])
        pt, t_dir = _trend(curr, prior)
        ss = _count_spark(consults, "ScheduledDateTime", last_cv)
        kpi_consults = kpi_card(
            f"Consults ({period_label})", f"{curr:,}",
            trend_text=f"{pt} {trend_label}" if pt else None,
            trend_direction=t_dir,
            sparkline_past=ss.tolist(),
            sparkline_past_labels=ss.index.tolist(),
            accent_color=CHART_COLORWAY[2],
        )
    else:
        kpi_consults = kpi_card("Consults", "N/A")

    # --- 2. Simulations ---
    if not sims.empty and "ScheduledDateTime" in sims.columns:
        last_sim = sims["ScheduledDateTime"].dt.normalize().max()
        start = _preset_start(last_sim, date_preset)
        curr = len(sims[sims["ScheduledDateTime"] >= start])
        ps, pe = _prior_range(last_sim, date_preset)
        prior = len(sims[(sims["ScheduledDateTime"] >= ps) & (sims["ScheduledDateTime"] <= pe)])
        pt, t_dir = _trend(curr, prior)
        ss = _count_spark(sims, "ScheduledDateTime", last_sim)
        kpi_sims = kpi_card(
            f"Simulations ({period_label})", f"{curr:,}",
            trend_text=f"{pt} {trend_label}" if pt else None,
            trend_direction=t_dir,
            sparkline_past=ss.tolist(),
            sparkline_past_labels=ss.index.tolist(),
            accent_color=CHART_COLORWAY[1],
        )
    else:
        kpi_sims = kpi_card("Simulations", "N/A")

    # --- 3. Treatments ---
    if not td.empty and "ScheduledDateTime" in td.columns:
        last_date = td["ScheduledDateTime"].dt.normalize().max()
        start = _preset_start(last_date, date_preset)
        curr = len(td[td["ScheduledDateTime"] >= start])
        ps, pe = _prior_range(last_date, date_preset)
        prior = len(td[(td["ScheduledDateTime"] >= ps) & (td["ScheduledDateTime"] <= pe)])
        pt, t_dir = _trend(curr, prior)
        ss = _count_spark(td, "ScheduledDateTime", last_date)
        kpi_tx = kpi_card(
            f"Treatments ({period_label})", f"{curr:,}",
            trend_text=f"{pt} {trend_label}" if pt else None,
            trend_direction=t_dir,
            sparkline_past=ss.tolist(),
            sparkline_past_labels=ss.index.tolist(),
            accent_color=PRIMARY,
        )
    else:
        kpi_tx = kpi_card("Treatments", "N/A", accent_color=PRIMARY)

    # --- 4. Consult Lead Time (days from booking to appointment) ---
    if not consults.empty and "AppointmentCreatedDate" in consults.columns:
        cl = consults[consults["AppointmentCreatedDate"].notna()].copy()
        cl["lead_days"] = (cl["ScheduledDateTime"] - cl["AppointmentCreatedDate"]).dt.days
        cl = cl[cl["lead_days"] >= 0]
        if not cl.empty:
            last_cv = cl["ScheduledDateTime"].dt.normalize().max()
            start = _preset_start(last_cv, date_preset)
            curr_data = cl[cl["ScheduledDateTime"] >= start]
            curr_avg = curr_data["lead_days"].mean() if len(curr_data) > 0 else 0
            ps, pe = _prior_range(last_cv, date_preset)
            prior_data = cl[(cl["ScheduledDateTime"] >= ps) & (cl["ScheduledDateTime"] <= pe)]
            prior_avg = prior_data["lead_days"].mean() if len(prior_data) > 0 else None
            pt, t_dir = _trend(curr_avg, prior_avg, invert=True)
            ss = _lead_spark(cl, "ScheduledDateTime", "lead_days", last_cv)
            kpi_consult_lead = kpi_card(
                f"Consult Lead Time ({period_label})", f"{curr_avg:.0f}",
                value_detail="days",
                trend_text=f"{pt} {trend_label}" if pt else None,
                trend_direction=t_dir,
                sparkline_past=ss.tolist(),
                sparkline_past_labels=ss.index.tolist(),
                sparkline_hover_fmt="%{x|%b %d}: %{y:.0f} days<extra></extra>",
                accent_color=CHART_COLORWAY[4],
            )
        else:
            kpi_consult_lead = kpi_card("Consult Lead Time", "N/A")
    else:
        kpi_consult_lead = kpi_card("Consult Lead Time", "N/A")

    # --- 5. Sim Lead Time (days from booking to appointment) ---
    if not sims.empty and "AppointmentCreatedDate" in sims.columns:
        sl = sims[sims["AppointmentCreatedDate"].notna()].copy()
        sl["lead_days"] = (sl["ScheduledDateTime"] - sl["AppointmentCreatedDate"]).dt.days
        sl = sl[sl["lead_days"] >= 0]
        if not sl.empty:
            last_sim = sl["ScheduledDateTime"].dt.normalize().max()
            start = _preset_start(last_sim, date_preset)
            curr_data = sl[sl["ScheduledDateTime"] >= start]
            curr_avg = curr_data["lead_days"].mean() if len(curr_data) > 0 else 0
            ps, pe = _prior_range(last_sim, date_preset)
            prior_data = sl[(sl["ScheduledDateTime"] >= ps) & (sl["ScheduledDateTime"] <= pe)]
            prior_avg = prior_data["lead_days"].mean() if len(prior_data) > 0 else None
            pt, t_dir = _trend(curr_avg, prior_avg, invert=True)
            ss = _lead_spark(sl, "ScheduledDateTime", "lead_days", last_sim)
            kpi_sim_lead = kpi_card(
                f"Sim Lead Time ({period_label})", f"{curr_avg:.0f}",
                value_detail="days",
                trend_text=f"{pt} {trend_label}" if pt else None,
                trend_direction=t_dir,
                sparkline_past=ss.tolist(),
                sparkline_past_labels=ss.index.tolist(),
                sparkline_hover_fmt="%{x|%b %d}: %{y:.0f} days<extra></extra>",
                accent_color=CHART_COLORWAY[3],
            )
        else:
            kpi_sim_lead = kpi_card("Sim Lead Time", "N/A")
    else:
        kpi_sim_lead = kpi_card("Sim Lead Time", "N/A")

    return kpi_consults, kpi_sims, kpi_tx, kpi_consult_lead, kpi_sim_lead


# ---------------------------------------------------------------------------
# Physician Census Callback
# ---------------------------------------------------------------------------

@callback(
    Output("home-chart-physician", "figure"),
    Input("home-interval", "n_intervals"),
    Input("home-md-range", "value"),
    Input("home-md-smooth", "value"),
    Input("home-filter-department", "value"),
)
def update_physician_chart(_n, range_days, smooth_pct, departments):
    from data.loader import load_treatment_detail

    try:
        td = load_treatment_detail()
        if departments and "Department" in td.columns:
            td = td[td["Department"].isin(departments)]
        if td.empty or "ScheduledDateTime" not in td.columns:
            return empty_figure("Treatment-Detail data unavailable")

        last_date = td["ScheduledDateTime"].dt.normalize().max()
        days = int(range_days) if int(range_days) > 0 else None
        if days:
            td = td[td["ScheduledDateTime"] >= last_date - timedelta(days=days)]

        frac = (smooth_pct or 0) / 100  # slider 0–50 → frac 0.0–0.5
        return _build_census_chart(
            td, "TreatingPhysician", PHYSICIANS, CHART_COLORWAY,
            frac, height=380,
        )
    except Exception:
        return empty_figure("Treatment-Detail data unavailable")


# ---------------------------------------------------------------------------
# Site Census Callback
# ---------------------------------------------------------------------------

@callback(
    Output("home-chart-site", "figure"),
    Input("home-interval", "n_intervals"),
    Input("home-site-range", "value"),
    Input("home-site-smooth", "value"),
    Input("home-filter-department", "value"),
)
def update_site_chart(_n, range_days, smooth_pct, departments):
    from data.loader import load_treatment_detail

    try:
        td = load_treatment_detail()
        if departments and "Department" in td.columns:
            td = td[td["Department"].isin(departments)]
        if td.empty or "ScheduledDateTime" not in td.columns:
            return empty_figure("Treatment-Detail data unavailable")

        last_date = td["ScheduledDateTime"].dt.normalize().max()
        days = int(range_days) if int(range_days) > 0 else None
        if days:
            td = td[td["ScheduledDateTime"] >= last_date - timedelta(days=days)]

        sites = departments if departments else DEPARTMENTS
        colors = [DEPARTMENT_COLORS.get(d, "#999") for d in sites]
        frac = (smooth_pct or 0) / 100  # slider 0–50 → frac 0.0–0.5
        return _build_census_chart(
            td, "Department", sites, colors,
            frac, height=380,
        )
    except Exception:
        return empty_figure("Treatment-Detail data unavailable")


# ---------------------------------------------------------------------------
# Chart builder
# ---------------------------------------------------------------------------

def _hex_to_rgba(hex_color, alpha=0.5):
    """Convert hex color to rgba string."""
    h = hex_color.lstrip("#")
    return f"rgba({int(h[0:2],16)},{int(h[2:4],16)},{int(h[4:6],16)},{alpha})"


def _build_census_chart(df, group_col, groups, colors, smooth_frac=0.15, height=380):
    """Build a stacked area chart of daily patient census."""
    df = df.copy()
    df["Date"] = df["ScheduledDateTime"].dt.normalize()

    if group_col not in df.columns:
        return empty_figure(f"Column '{group_col}' not found")

    patient_col = next((c for c in ["PatientId", "PatientMRN"] if c in df.columns), None)
    if patient_col is None:
        return empty_figure("No patient identifier column")

    fig = go.Figure()

    # Business days only (no weekends), excluding days with zero total patients
    date_range = pd.bdate_range(df["Date"].min(), df["Date"].max())
    total_per_day = df.groupby("Date")[patient_col].nunique()
    active_days = total_per_day[total_per_day > 0].index
    date_range = date_range[date_range.isin(active_days)]

    # Per-group stacked areas
    daily = df.groupby(["Date", group_col])[patient_col].nunique().reset_index(name="count")

    for i, grp in enumerate(groups):
        grp_data = daily[daily[group_col] == grp].set_index("Date")["count"]
        grp_data = grp_data.reindex(date_range, fill_value=0)

        y_vals = _apply_loess(grp_data, frac=smooth_frac) if smooth_frac > 0 else grp_data
        display_name = grp.split(",")[0] if "," in grp else grp
        c = colors[i % len(colors)]

        fig.add_trace(go.Scatter(
            x=date_range, y=y_vals,
            name=display_name,
            mode="lines",
            line=dict(color=c, width=1.5),
            fillcolor=_hex_to_rgba(c, 0.5),
            stackgroup="one",
            hovertemplate=f"{display_name}<br>Date: %{{x|%b %d}}<br>Patients: %{{y:.0f}}<extra></extra>",
        ))

    smoothed = smooth_frac > 0
    apply_default_layout(fig, height=height)
    fig.update_layout(
        xaxis_title="Date",
        yaxis_title="Unique Patients" + (" (smoothed)" if smoothed else ""),
        margin=dict(l=48, r=16, t=16, b=48),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
    )
    return fig
