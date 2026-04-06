"""Diagnosis page — ridgeline trend and current-vs-prior comparison by diagnosis group."""

import dash
import dash_mantine_components as dmc
from dash import callback, Input, Output, State, dcc, html, clientside_callback, ClientsideFunction
from dash_iconify import DashIconify
import plotly.graph_objects as go
import pandas as pd
import numpy as np

from config.settings import (
    DEPARTMENTS, DEPARTMENT_COLORS, CHART_COLORWAY,
    PRIMARY, DEFAULT_LAYOUT, FONT_FAMILY, NEUTRAL,
)
from components.filter_bar import department_chips
from components.chart_card import chart_card, register_chart_callbacks
from components.chart_settings import chart_settings_popover
from utils.charts import apply_default_layout, empty_figure
from utils.date_slider import (
    month_idx, idx_to_date, MAX_IDX, DEFAULT_SLIDER, SLIDER_MARKS,
    preset_to_slider_val,
)
from utils.diagnosis_categories import (
    CATEGORIES as BODY_SYSTEMS,
    build_code_to_category,
    get_categories_for_codes,
    primary_category,
)

dash.register_page(__name__, path="/diagnosis", name="Diagnosis", order=6)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_DEFAULT_DATE_PRESET = "ytd" if pd.Timestamp.now().month > 1 else "12mo"

# Consistent colors for each diagnosis group (13 categories)
_DIAG_COLORS = [
    "#7C2A83", "#2196F3", "#F44336", "#4CAF50", "#FF9800",
    "#00BCD4", "#9C27B0", "#795548", "#E91E63", "#3F51B5",
    "#8BC34A", "#FF5722", "#607D8B",
]

_RIDGE_HEIGHT = 840


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_date_range(slider_val):
    """Calculate start/end from slider, capped to today."""
    today = pd.Timestamp.now().normalize()
    if slider_val and len(slider_val) == 2:
        start = idx_to_date(slider_val[0])
        end = min(idx_to_date(slider_val[1], end_of_month=True), today)
        return start, end
    return pd.Timestamp("2020-01-01"), today


def _load_consults():
    """Load clinic visits and filter to new consults only."""
    from data.loader import load_clinic_visits
    from pages.home import _is_consult

    df = load_clinic_visits()
    if df.empty:
        return df

    if "ActivityName" in df.columns:
        mask = df.apply(_is_consult, axis=1)
        df = df[mask]
    return df


def _load_courses_data():
    """Load courses data."""
    from data.loader import load_courses
    return load_courses()


def _assign_diagnosis(df, c2b):
    """Add _diag_group column from DiagnosisCodes."""
    if "DiagnosisCodes" not in df.columns or not c2b:
        return df
    df = df.copy()
    df["_diag_group"] = df["DiagnosisCodes"].apply(lambda v: primary_category(v, c2b))
    df = df[df["_diag_group"] != "Unknown"]
    return df


def _color_map():
    """Return a stable {group_name: hex_color} dict for all BODY_SYSTEMS."""
    return {g: _DIAG_COLORS[i % len(_DIAG_COLORS)] for i, g in enumerate(BODY_SYSTEMS)}


def _hex_to_rgba(hex_color, alpha=0.35):
    """Convert hex like '#7C2A83' to 'rgba(124,42,131,0.35)'."""
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


# ---------------------------------------------------------------------------
# Trend store data builder (server → store, rendered clientside)
# ---------------------------------------------------------------------------

def _prepare_trend_store(df, date_col):
    """Build per-group time-series data for all agg levels (W/M/Y).

    Returns a JSON-serialisable dict consumed by the clientside renderer.
    """
    if df.empty or "_diag_group" not in df.columns or date_col not in df.columns:
        return None

    tmp = df[[date_col, "_diag_group"]].dropna(subset=[date_col]).copy()
    cmap = _color_map()

    group_counts = tmp["_diag_group"].value_counts()
    groups = list(reversed(group_counts.index.tolist()))  # ascending (bottom→top)
    if not groups:
        return None

    combos = {}
    for agg in ("W", "M", "Y"):
        period_code = "Y" if agg == "Y" else agg
        t = tmp.copy()
        t["period"] = t[date_col].dt.to_period(period_code).dt.to_timestamp()
        all_periods = sorted(t["period"].unique())
        dates = [d.isoformat() for d in all_periods]

        series = []
        for grp in groups:
            sub = t[t["_diag_group"] == grp]
            counts = sub.groupby("period").size().reindex(all_periods, fill_value=0)
            series.append({
                "name": grp,
                "values": counts.tolist(),
                "color": cmap.get(grp, CHART_COLORWAY[0]),
            })

        combos[agg] = {"dates": dates, "series": series}

    return {"combos": combos, "groups": groups, "height": _RIDGE_HEIGHT}


# ---------------------------------------------------------------------------
# Current vs Prior comparison bar chart
# ---------------------------------------------------------------------------

def _period_label(start, end):
    """Smart period label for date ranges."""
    same_year = start.year == end.year
    same_month = same_year and start.month == end.month
    if same_month:
        return start.strftime("%b %Y")
    if same_year:
        if start.month == 1 and end.month == 12:
            return str(start.year)
        return f"{start.strftime('%b')} – {end.strftime('%b %Y')}"
    return f"{start.strftime('%b %y')} – {end.strftime('%b %y')}"


def _build_comparison_bars(dff_curr, dff_prior, start, end, prior_start, prior_end):
    """Horizontal grouped bar chart: current vs prior period per diagnosis group.

    Bars are colored by diagnosis group (current) with prior in muted gray.
    Count annotations on each bar and a delta % annotation to the right.
    """
    if dff_curr.empty or "_diag_group" not in dff_curr.columns:
        fig = empty_figure("No diagnosis data available")
        fig.update_layout(height=_RIDGE_HEIGHT)
        return fig

    cmap = _color_map()
    curr_label = _period_label(start, end)
    prior_label = _period_label(prior_start, prior_end)

    # Count by group — use all groups present in either period
    curr_counts = dff_curr["_diag_group"].value_counts()
    prior_counts = (
        dff_prior["_diag_group"].value_counts()
        if dff_prior is not None and not dff_prior.empty and "_diag_group" in dff_prior.columns
        else pd.Series(dtype=int)
    )

    all_groups = sorted(set(curr_counts.index) | set(prior_counts.index))
    # Order by current count descending, reversed for horizontal bar (largest at top)
    all_groups = sorted(all_groups, key=lambda g: curr_counts.get(g, 0))

    curr_vals = [int(curr_counts.get(g, 0)) for g in all_groups]
    prior_vals = [int(prior_counts.get(g, 0)) for g in all_groups]

    fig = go.Figure()

    # Prior bars (behind, muted)
    fig.add_trace(go.Bar(
        x=prior_vals,
        y=all_groups,
        orientation="h",
        marker_color="rgba(156, 163, 175, 0.45)",
        name=prior_label,
        text=[f"{v:,}" for v in prior_vals],
        textposition="inside",
        insidetextanchor="end",
        textangle=0,
        textfont=dict(size=13, color="#6B7280"),
        hovertemplate=[
            f"<b>{g}</b><br>{prior_label}: {v:,}<extra></extra>"
            for g, v in zip(all_groups, prior_vals)
        ],
    ))

    # Current bars (front, colored per group)
    bar_colors = [cmap.get(g, CHART_COLORWAY[0]) for g in all_groups]
    fig.add_trace(go.Bar(
        x=curr_vals,
        y=all_groups,
        orientation="h",
        marker_color=bar_colors,
        name=curr_label,
        text=[f"{v:,}" for v in curr_vals],
        textposition="inside",
        insidetextanchor="end",
        textangle=0,
        textfont=dict(size=13, color="white"),
        hovertemplate=[
            f"<b>{g}</b><br>{curr_label}: {v:,}<extra></extra>"
            for g, v in zip(all_groups, curr_vals)
        ],
    ))

    # Delta annotations to the right of each bar pair
    max_val = max(max(curr_vals, default=0), max(prior_vals, default=0))
    annot_x = max_val * 1.05 if max_val > 0 else 1

    annotations = []
    for i, g in enumerate(all_groups):
        c, p = curr_vals[i], prior_vals[i]
        if p > 0:
            pct = (c - p) / p * 100
            if pct > 0:
                txt = f"▲ {pct:.0f}%"
                color = "#10B981"
            elif pct < 0:
                txt = f"▼ {abs(pct):.0f}%"
                color = "#EF4444"
            else:
                txt = "—"
                color = "#9CA3AF"
        elif c > 0:
            txt = "● new"
            color = "#3B82F6"
        else:
            txt = ""
            color = "#9CA3AF"

        if txt:
            annotations.append(dict(
                x=annot_x,
                y=g,
                text=txt,
                showarrow=False,
                font=dict(size=13, color=color, family=FONT_FAMILY),
                xanchor="left",
                yanchor="middle",
            ))

    apply_default_layout(fig, barmode="group")
    fig.update_layout(
        height=_RIDGE_HEIGHT,
        xaxis_title="", yaxis_title="",
        xaxis=dict(visible=False, range=[0, annot_x * 1.15]),
        yaxis=dict(automargin="left+top+bottom", ticklabelstandoff=0,
                   categoryorder="array", categoryarray=all_groups,
                   tickfont=dict(size=12)),
        margin=dict(l=0, r=60, t=24, b=12),
        showlegend=True,
        legend=dict(
            orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0,
            font=dict(size=11),
        ),
        bargroupgap=0.15,
        annotations=annotations,
    )
    return fig


# ---------------------------------------------------------------------------
# Filter Bar
# ---------------------------------------------------------------------------

def _build_filter_bar():
    """Two-row filter: data filters + date slider."""
    return dmc.Paper(
        children=[
            dmc.Group(
                children=[
                    department_chips("diag"),
                    dmc.Select(
                        id="diag-filter-physician",
                        data=[],
                        placeholder="All Physicians",
                        clearable=True,
                        size="sm",
                        w=200,
                    ),
                    # Diagnosis group dropdown
                    html.Div(
                        children=[
                            html.Div(
                                children=[
                                    dmc.Button(
                                        "Diagnosis",
                                        id="diag-diagnosis-trigger",
                                        variant="default",
                                        size="sm",
                                        rightSection=DashIconify(icon="mdi:chevron-down", width=14),
                                    ),
                                    dmc.ActionIcon(
                                        DashIconify(icon="mdi:close-circle", width=18),
                                        id="diag-diagnosis-clear",
                                        variant="subtle",
                                        color="gray",
                                        size="sm",
                                        className="wf-filter-clear-btn",
                                    ),
                                ],
                                style={"position": "relative", "display": "inline-block"},
                            ),
                            dmc.Paper(
                                dmc.ChipGroup(
                                    children=[
                                        dmc.Chip(bs, value=bs, size="xs", variant="filled")
                                        for bs in BODY_SYSTEMS
                                    ],
                                    id="diag-filter-diagnosis",
                                    multiple=True,
                                    value=[],
                                ),
                                id="diag-diagnosis-panel",
                                p="xs",
                                shadow="md",
                                withBorder=True,
                                radius="md",
                                className="wf-chip-dropdown",
                                style={"display": "none"},
                            ),
                        ],
                        style={"position": "relative", "display": "inline-block"},
                    ),
                    dmc.SegmentedControl(
                        id="diag-mode-toggle",
                        data=[
                            {"value": "consults", "label": "New Consults"},
                            {"value": "courses", "label": "Courses"},
                        ],
                        value="consults",
                        size="sm",
                        color="violet",
                    ),
                ],
                gap="md",
                align="center",
                wrap="wrap",
            ),
            dmc.Group(
                children=[
                    dmc.Select(
                        id="diag-filter-date-preset",
                        data=[
                            {"value": "12mo", "label": "Prior 12 mo"},
                            {"value": "6mo", "label": "Prior 6 mo"},
                            {"value": "3mo", "label": "Prior 3 mo"},
                            {"value": "ytd", "label": "Year to Date"},
                            {"value": "last_year", "label": "Last Year"},
                            {"value": "all", "label": "All Time"},
                            {"value": "custom", "label": "Custom Range"},
                        ],
                        value=_DEFAULT_DATE_PRESET,
                        size="xs",
                        w=150,
                        allowDeselect=False,
                        leftSection=DashIconify(icon="mdi:clock-outline", width=14),
                        comboboxProps={"zIndex": 500, "offset": 2},
                        maxDropdownHeight=400,
                    ),
                    dmc.Paper(
                        dcc.DatePickerRange(
                            id="diag-filter-daterange",
                            display_format="MMM D, YYYY",
                            start_date_placeholder_text="Start",
                            end_date_placeholder_text="End",
                            clearable=True,
                            number_of_months_shown=2,
                            minimum_nights=0,
                            start_date=idx_to_date(preset_to_slider_val(_DEFAULT_DATE_PRESET, MAX_IDX)[0]).strftime("%Y-%m-%d"),
                            end_date=idx_to_date(preset_to_slider_val(_DEFAULT_DATE_PRESET, MAX_IDX)[1], end_of_month=True).strftime("%Y-%m-%d"),
                            className="wf-date-picker-range",
                        ),
                        px="xs",
                        py=4,
                        radius="sm",
                        withBorder=True,
                        className="wf-datepicker-wrapper",
                    ),
                    dmc.Box(
                        children=[
                            html.Div(id="diag-date-range-label", style={"display": "none"}),
                            dmc.RangeSlider(
                                id="diag-date-slider",
                                min=0,
                                max=MAX_IDX,
                                step=1,
                                value=preset_to_slider_val(_DEFAULT_DATE_PRESET, MAX_IDX),
                                marks=SLIDER_MARKS,
                                color="violet",
                                size="sm",
                                minRange=0,
                            ),
                        ],
                        style={"flex": "1", "minWidth": "280px"},
                    ),
                ],
                gap="md",
                align="center",
                mt="xs",
            ),
        ],
        p="sm",
        px="md",
        radius="md",
        shadow="xs",
        withBorder=True,
    )


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------

_TREND_CHART_TYPES = [
    {"value": "area", "label": "Area"},
    {"value": "line", "label": "Line"},
    {"value": "bar", "label": "Bar"},
]

layout = dmc.Stack(
    gap=16,
    className="page-content",
    children=[
        dmc.Box(
            className="page-sticky-header",
            children=[
                dmc.Title("Diagnosis", order=2, className="page-title",
                          style={"margin": 0, "textAlign": "center"}),
                _build_filter_bar(),
            ],
        ),
        # Charts row: trend ridgeline + comparison bars
        dmc.Grid(
            gutter="md",
            children=[
                dmc.GridCol(
                    chart_card(
                        "diag-chart-trend",
                        "Trend",
                        chart_types=_TREND_CHART_TYPES,
                        show_smooth=True,
                        smooth_max=30,
                        smooth_default=0,
                        graph_height="100%",
                        paper_height=f"{_RIDGE_HEIGHT + 60}px",
                        store_data=True,
                        extra_controls=[
                            dmc.SegmentedControl(
                                id="diag-trend-agg",
                                data=[
                                    {"value": "W", "label": "Weekly"},
                                    {"value": "M", "label": "Monthly"},
                                    {"value": "Y", "label": "Yearly"},
                                ],
                                value="M",
                                size="xs",
                            ),
                        ],
                    ),
                    span=6,
                ),
                dmc.GridCol(
                    dmc.Paper(
                        children=[
                            dmc.Group(
                                justify="space-between",
                                mb=8,
                                children=[
                                    dmc.Text("Current vs Prior Period", size="sm", fw=500,
                                             c=NEUTRAL["text_secondary"]),
                                    dmc.SegmentedControl(
                                        id="diag-compare-period-type",
                                        data=[
                                            {"value": "calendar", "label": "Calendar"},
                                            {"value": "rolling", "label": "Rolling"},
                                        ],
                                        value="calendar",
                                        size="xs",
                                    ),
                                ],
                            ),
                            dmc.Box(
                                pos="relative",
                                style={"flex": "1", "minHeight": 0},
                                children=[
                                    dmc.Box(
                                        style={"position": "absolute", "top": 0, "left": 0,
                                               "right": 0, "bottom": 0},
                                        children=[
                                            dcc.Graph(
                                                id="diag-chart-comparison",
                                                config={"displayModeBar": False},
                                                responsive=True,
                                                style={"height": "100%", "width": "100%"},
                                            ),
                                        ],
                                    ),
                                ],
                            ),
                        ],
                        p="sm", pb=8, radius="md", shadow="xs", withBorder=True,
                        h=f"{_RIDGE_HEIGHT + 60}px",
                        style={"display": "flex", "flexDirection": "column"},
                    ),
                    span=6,
                ),
            ],
        ),
        dcc.Interval(id="diag-interval", interval=5 * 60 * 1000, n_intervals=0),
    ],
)

# Register gear-icon toggle + export callbacks for trend chart
register_chart_callbacks(["diag-chart-trend"])

# ---------------------------------------------------------------------------
# Diagnosis dropdown: trigger label, clear visibility, clear action
# ---------------------------------------------------------------------------
clientside_callback(
    """function(vals) {
        if (!vals || vals.length === 0) return "Diagnosis";
        if (vals.length === 1) return vals[0];
        return vals.length + " selected";
    }""",
    Output("diag-diagnosis-trigger", "children"),
    Input("diag-filter-diagnosis", "value"),
)
clientside_callback(
    """function(vals) { return vals && vals.length > 0 ? {"display": "inline-flex"} : {"display": "none"}; }""",
    Output("diag-diagnosis-clear", "style"),
    Input("diag-filter-diagnosis", "value"),
)
clientside_callback(
    """function(n) { return []; }""",
    Output("diag-filter-diagnosis", "value", allow_duplicate=True),
    Input("diag-diagnosis-clear", "n_clicks"),
    prevent_initial_call=True,
)


# ---------------------------------------------------------------------------
# Date filter sync: Preset ↔ Slider ↔ DatePicker
# ---------------------------------------------------------------------------

# A) Preset → Slider + DatePicker
@callback(
    Output("diag-date-slider", "value"),
    Output("diag-filter-daterange", "start_date", allow_duplicate=True),
    Output("diag-filter-daterange", "end_date", allow_duplicate=True),
    Input("diag-filter-date-preset", "value"),
    prevent_initial_call=True,
)
def _sync_preset(preset):
    if not preset or preset == "custom":
        return (dash.no_update,) * 3
    sv = preset_to_slider_val(preset, MAX_IDX)
    s = idx_to_date(sv[0]).strftime("%Y-%m-%d")
    e_ts = idx_to_date(sv[1], end_of_month=True)
    today = pd.Timestamp.now().normalize()
    if e_ts > today:
        e_ts = today
    e = e_ts.strftime("%Y-%m-%d")
    return sv, s, e

# B) Slider → DatePicker + Label (clientside for speed)
clientside_callback(
    ClientsideFunction(namespace="diagDateSlider", function_name="syncSlider"),
    Output("diag-filter-daterange", "start_date", allow_duplicate=True),
    Output("diag-filter-daterange", "end_date", allow_duplicate=True),
    Output("diag-date-range-label", "children"),
    Input("diag-date-slider", "value"),
    State("diag-filter-daterange", "start_date"),
    State("diag-filter-daterange", "end_date"),
    prevent_initial_call=True,
)

# C) DatePicker → Slider
@callback(
    Output("diag-date-slider", "value", allow_duplicate=True),
    Input("diag-filter-daterange", "start_date"),
    Input("diag-filter-daterange", "end_date"),
    State("diag-date-slider", "value"),
    prevent_initial_call=True,
)
def _sync_picker_to_slider(start, end, current_slider):
    if not start or not end:
        return dash.no_update
    s = pd.Timestamp(start)
    e = pd.Timestamp(end)
    new_val = [month_idx(s.year, s.month), month_idx(e.year, e.month)]
    if new_val == current_slider:
        return dash.no_update
    return new_val

# D) Slider → auto-set preset to "Custom" when it doesn't match
@callback(
    Output("diag-filter-date-preset", "value", allow_duplicate=True),
    Input("diag-date-slider", "value"),
    prevent_initial_call=True,
)
def _slider_to_preset(slider_val):
    for preset_key in ("12mo", "6mo", "3mo", "ytd", "last_year", "all"):
        if slider_val == preset_to_slider_val(preset_key, MAX_IDX):
            return preset_key
    return "custom"


# ---------------------------------------------------------------------------
# Main callback — outputs store data (trend) + figure (comparison bars)
# ---------------------------------------------------------------------------
@callback(
    Output("diag-chart-trend-store", "data"),
    Output("diag-chart-comparison", "figure"),
    Output("diag-filter-physician", "data"),
    Input("diag-interval", "n_intervals"),
    Input("diag-date-slider", "value"),
    Input("diag-filter-department", "value"),
    Input("diag-filter-physician", "value"),
    Input("diag-filter-diagnosis", "value"),
    Input("diag-mode-toggle", "value"),
    Input("diag-compare-period-type", "value"),
)
def update_diagnosis(_n, slider_val, departments, physician, diag_filter, mode, period_type):
    from data.loader import load_diagnosis

    empty_bar = empty_figure("No data for selected filters")
    empty_bar.update_layout(height=_RIDGE_HEIGHT)
    no_phys = []

    try:
        diag_df = load_diagnosis()
    except Exception:
        diag_df = None
    c2b = build_code_to_category(diag_df)

    start, end = _get_date_range(slider_val)

    if mode == "courses":
        try:
            df_all = _load_courses_data()
        except Exception:
            return None, empty_bar, no_phys
        date_col = "CourseStartDate"
        phys_col = "TreatingPhysician"
    else:
        try:
            df_all = _load_consults()
        except Exception:
            return None, empty_bar, no_phys
        date_col = "ScheduledDateTime"
        phys_col = "AppointmentPhysician"

    if df_all.empty:
        return None, empty_bar, no_phys

    # Department filter (before extracting physician options)
    if departments and "Department" in df_all.columns:
        df_all = df_all[df_all["Department"].isin(departments)]

    # Build physician options from data (after department filter, before physician filter)
    phys_options = []
    if phys_col in df_all.columns:
        phys_options = sorted(df_all[phys_col].dropna().unique().tolist())

    # Physician filter
    if physician and phys_col in df_all.columns:
        df_all = df_all[df_all[phys_col] == physician]

    # Diagnosis group filter (applied before _assign_diagnosis so the
    # comparison chart and trend both respect it)
    if diag_filter and "DiagnosisCodes" in df_all.columns:
        diag_set = set(diag_filter)
        # Need c2b for filtering — already computed above
        mask = df_all["DiagnosisCodes"].apply(
            lambda v: bool(get_categories_for_codes(v, c2b) & diag_set) if pd.notna(v) else False
        )
        df_all = df_all[mask]

    if df_all.empty:
        return None, empty_bar, phys_options

    # Assign diagnosis groups on full dataset
    df_all = _assign_diagnosis(df_all, c2b)
    if df_all.empty or "_diag_group" not in df_all.columns:
        return None, empty_bar, phys_options

    # Current period
    if date_col in df_all.columns:
        dff = df_all[(df_all[date_col] >= start) & (df_all[date_col] <= end)]
    else:
        dff = df_all

    if dff.empty:
        return None, empty_bar, phys_options

    # Prior period: calendar (same dates last year) or rolling (shift by range length)
    period_type = period_type or "calendar"
    if period_type == "calendar":
        try:
            prior_start = start - pd.DateOffset(years=1)
            prior_end = end - pd.DateOffset(years=1)
        except Exception:
            span = end - start
            prior_end = start - pd.Timedelta(days=1)
            prior_start = prior_end - span
    else:
        span = end - start
        prior_end = start - pd.Timedelta(days=1)
        prior_start = prior_end - span

    if date_col in df_all.columns:
        dff_prior = df_all[
            (df_all[date_col] >= prior_start) & (df_all[date_col] <= prior_end)
        ]
    else:
        dff_prior = pd.DataFrame()

    # Build outputs
    trend_store = _prepare_trend_store(dff, date_col)
    fig_bars = _build_comparison_bars(
        dff, dff_prior, start, end, prior_start, prior_end,
    )

    return trend_store, fig_bars, phys_options


# ---------------------------------------------------------------------------
# Clientside callback — renders trend ridgeline from store + settings
# ---------------------------------------------------------------------------
clientside_callback(
    ClientsideFunction(namespace="diagRidge", function_name="renderTrend"),
    Output("diag-chart-trend", "figure"),
    Input("diag-chart-trend-store", "data"),
    Input("diag-chart-trend-settings-smooth", "value"),
    Input("diag-chart-trend-settings-type", "value"),
    Input("diag-trend-agg", "value"),
)
