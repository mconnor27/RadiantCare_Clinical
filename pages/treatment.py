"""Treatment page -- deep-dive treatment analytics: modality, fields, elapsed time,
isocenters, fractions, new starts, gating utilization."""

import dash
import dash_mantine_components as dmc
import dash_ag_grid as dag
from dash import callback, Input, Output, State, dcc, html, clientside_callback, ClientsideFunction
from dash_iconify import DashIconify
import plotly.graph_objects as go
import pandas as pd
import numpy as np

from config.settings import (
    PHYSICIANS, DEPARTMENTS, DEPARTMENT_COLORS, CHART_COLORWAY, PRIMARY,
    DEFAULT_LAYOUT, FONT_FAMILY, SEMANTIC_COLORS, NEUTRAL,
    DEFAULT_COLUMN_DEFS, DEFAULT_GRID_OPTIONS, CHART_PAPER_HEIGHT,
    MACHINE_DEPT,
)
from components.filter_bar import department_chips
from components.kpi_card import kpi_card
from components.chart_card import chart_card, register_chart_callbacks
from components.detail_table import detail_table
from utils.charts import apply_default_layout, empty_figure, dept_color
from utils.holidays import get_holidays
from utils.date_slider import (
    month_idx, idx_to_date, MAX_IDX, SLIDER_MARKS,
    preset_to_slider_val,
)

dash.register_page(__name__, path="/treatment", name="Treatment", order=8)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_SITE_DEPTS = set(DEPARTMENTS)  # {"Lacey", "Centralia", "Aberdeen"}
_DEFAULT_DATE_PRESET = "12mo"

# Technique bucketing
_TECHNIQUE_MAP = {
    "VMAT": "VMAT",
    "IMRT": "IMRT",
    "3D": "3D Conformal",
    "Electron": "Electron",
    "SBRT": "SRS/SBRT",
    "SRS": "SRS/SBRT",
}

_TECHNIQUE_COLORS = {
    "VMAT": CHART_COLORWAY[0],       # purple
    "IMRT": CHART_COLORWAY[1],       # blue
    "3D Conformal": CHART_COLORWAY[3],  # green
    "Electron": CHART_COLORWAY[4],   # orange
    "SRS/SBRT": CHART_COLORWAY[5],   # cyan
    "Other": CHART_COLORWAY[7],      # brown
}

_TECHNIQUE_ORDER = ["VMAT", "IMRT", "3D Conformal", "Electron", "SRS/SBRT", "Other"]

_FIELD_COLORS = {
    "Arc": CHART_COLORWAY[0],
    "Dynamic MLC": CHART_COLORWAY[1],
    "Static MLC": CHART_COLORWAY[3],
    "Electron": CHART_COLORWAY[4],
}


def _bucket_technique(raw):
    """Map a raw PlanTechniques value to a display bucket."""
    if pd.isna(raw) or not raw:
        return "Other"
    primary = str(raw).split(",")[0].strip()
    return _TECHNIQUE_MAP.get(primary, "Other")


# ---------------------------------------------------------------------------
# Filter Bar (robust two-row style)
# ---------------------------------------------------------------------------

def _build_tx_filter_bar():
    """Build the two-row filter bar for treatment page."""
    return dmc.Paper(
        children=[
            # Row 1: dimension filters + smoothing
            dmc.Group(
                children=[
                    department_chips("tx"),
                    # Physician dropdown
                    html.Div(
                        children=[
                            html.Div(
                                children=[
                                    dmc.Button(
                                        "Physician",
                                        id="tx-physician-trigger",
                                        variant="default",
                                        size="sm",
                                        rightSection=DashIconify(icon="mdi:chevron-down", width=14),
                                    ),
                                    dmc.ActionIcon(
                                        DashIconify(icon="mdi:close-circle", width=18),
                                        id="tx-physician-clear",
                                        variant="subtle",
                                        color="gray",
                                        size="sm",
                                        className="wf-filter-clear-btn",
                                    ),
                                ],
                                style={"position": "relative", "display": "inline-block"},
                            ),
                            dmc.Paper(
                                id="tx-physician-panel",
                                children=[
                                    dmc.ChipGroup(
                                        children=[
                                            dmc.Chip(
                                                p.split(", ")[0],
                                                value=p,
                                                size="xs",
                                                variant="filled",
                                            )
                                            for p in PHYSICIANS
                                        ],
                                        id="tx-filter-physician",
                                        multiple=False,
                                    ),
                                ],
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
                    # Smoothing slider
                    dmc.Group(
                        children=[
                            dmc.Text("Smoothing", size="xs", c="#6B7280", fw=500),
                            dmc.Slider(
                                id="tx-smooth-slider",
                                min=0,
                                max=1,
                                step=0.01,
                                value=0.3,
                                size="xs",
                                showLabelOnHover=False,
                                w=120,
                                updatemode="drag",
                            ),
                        ],
                        gap=6,
                        align="center",
                    ),
                ],
                gap="md",
                wrap="wrap",
                align="center",
            ),
            # Row 2: date controls
            dmc.Group(
                children=[
                    dmc.Select(
                        id="tx-filter-date-preset",
                        data=[
                            {"value": "12mo", "label": "Prior 12 mo"},
                            {"value": "6mo", "label": "Prior 6 mo"},
                            {"value": "3mo", "label": "Prior 3 mo"},
                            {"value": "30d", "label": "Prior 30 days"},
                            {"value": "ytd", "label": "Year to Date"},
                            {"value": "last_year", "label": "Last Year"},
                            {"value": "this_month", "label": "This Month"},
                            {"value": "last_month", "label": "Last Month"},
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
                            id="tx-filter-daterange",
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
                            html.Div(id="tx-date-range-label", style={"display": "none"}),
                            dmc.RangeSlider(
                                id="tx-date-slider",
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

layout = dmc.Stack(
    gap=16,
    className="page-content",
    children=[
        # Sticky header
        dmc.Box(
            className="page-sticky-header",
            children=[
                dmc.Title("Treatment", order=2, className="page-title",
                          style={"margin": 0, "textAlign": "center"}),
                _build_tx_filter_bar(),
            ],
        ),

        # KPI row — 6 cards with clientside sparklines
        dmc.Grid(id="tx-kpi-row", gutter="md", children=[
            dmc.GridCol(id="tx-kpi-volume", span={"base": 12, "sm": 6, "md": 2}),
            dmc.GridCol(id="tx-kpi-newstarts", span={"base": 12, "sm": 6, "md": 2}),
            dmc.GridCol(id="tx-kpi-patients", span={"base": 12, "sm": 6, "md": 2}),
            dmc.GridCol(id="tx-kpi-elapsed", span={"base": 12, "sm": 6, "md": 2}),
            dmc.GridCol(id="tx-kpi-fields", span={"base": 12, "sm": 6, "md": 2}),
            dmc.GridCol(id="tx-kpi-gating", span={"base": 12, "sm": 6, "md": 2}),
        ]),

        # Row 1: Treatment Volume + Technique Mix
        dmc.Grid(gutter="md", children=[
            dmc.GridCol(
                chart_card(
                    "tx-chart-volume",
                    "Treatment Volume by Department",
                    settings_id="tx-volume",
                    chart_types=[
                        {"value": "area", "label": "Area"},
                        {"value": "line", "label": "Line"},
                        {"value": "bar", "label": "Bar"},
                    ],
                    show_smooth=True,
                    smooth_max=40,
                    smooth_default=15,
                    store_data=True,
                    paper_padding="md",
                ),
                span={"base": 12, "md": 6},
            ),
            dmc.GridCol(
                chart_card(
                    "tx-chart-technique",
                    "Technique Mix",
                    settings_id="tx-technique",
                    chart_types=[
                        {"value": "area", "label": "Area"},
                        {"value": "bar", "label": "Bar"},
                        {"value": "line", "label": "Line"},
                    ],
                    show_smooth=True,
                    smooth_max=40,
                    smooth_default=15,
                    store_data=True,
                    paper_padding="md",
                ),
                span={"base": 12, "md": 6},
            ),
        ]),

        # Row 2: Session Duration + Field Type Breakdown
        dmc.Grid(gutter="md", children=[
            dmc.GridCol(
                chart_card(
                    "tx-chart-elapsed",
                    "Session Duration Distribution",
                    settings_id="tx-elapsed",
                    show_smooth=False,
                    show_settings=False,
                    paper_padding="md",
                    extra_controls=[
                        dmc.SegmentedControl(
                            id="tx-elapsed-groupby",
                            data=[
                                {"value": "department", "label": "Department"},
                                {"value": "machine", "label": "Machine"},
                            ],
                            value="department",
                            size="xs",
                        ),
                    ],
                ),
                span={"base": 12, "md": 6},
            ),
            dmc.GridCol(
                chart_card(
                    "tx-chart-fields",
                    "Field Type Breakdown",
                    settings_id="tx-fields",
                    chart_types=[
                        {"value": "area", "label": "Area"},
                        {"value": "bar", "label": "Bar"},
                        {"value": "line", "label": "Line"},
                    ],
                    show_smooth=True,
                    smooth_max=40,
                    smooth_default=15,
                    store_data=True,
                    paper_padding="md",
                ),
                span={"base": 12, "md": 6},
            ),
        ]),

        # Row 3: New Starts + Gating Utilization
        dmc.Grid(gutter="md", children=[
            dmc.GridCol(
                chart_card(
                    "tx-chart-newstarts",
                    "New Starts Trend",
                    settings_id="tx-newstarts",
                    chart_types=[
                        {"value": "area", "label": "Area"},
                        {"value": "line", "label": "Line"},
                        {"value": "bar", "label": "Bar"},
                    ],
                    show_smooth=True,
                    smooth_max=40,
                    smooth_default=15,
                    store_data=True,
                    paper_padding="md",
                    extra_controls=[
                        dmc.SegmentedControl(
                            id="tx-newstarts-metric",
                            data=[
                                {"value": "fraction", "label": "By Fraction"},
                                {"value": "course", "label": "By Course"},
                            ],
                            value="fraction",
                            size="xs",
                        ),
                    ],
                ),
                span={"base": 12, "md": 6},
            ),
            dmc.GridCol(
                chart_card(
                    "tx-chart-gating",
                    "Gating Utilization",
                    settings_id="tx-gating",
                    chart_types=[
                        {"value": "line", "label": "Line"},
                        {"value": "area", "label": "Area"},
                    ],
                    show_smooth=True,
                    smooth_max=40,
                    smooth_default=15,
                    store_data=True,
                    paper_padding="md",
                ),
                span={"base": 12, "md": 6},
            ),
        ]),

        # Row 4: Multi-Isocenter Rate + OSMS Adoption
        dmc.Grid(gutter="md", children=[
            dmc.GridCol(
                chart_card(
                    "tx-chart-multiiso",
                    "Multi-Isocenter Rate",
                    settings_id="tx-multiiso",
                    chart_types=[
                        {"value": "line", "label": "Line"},
                        {"value": "area", "label": "Area"},
                        {"value": "bar", "label": "Bar"},
                    ],
                    show_smooth=True,
                    smooth_max=40,
                    smooth_default=15,
                    store_data=True,
                    paper_padding="md",
                ),
                span={"base": 12, "md": 6},
            ),
            dmc.GridCol(
                chart_card(
                    "tx-chart-osms",
                    "OSMS Adoption",
                    settings_id="tx-osms",
                    chart_types=[
                        {"value": "line", "label": "Line"},
                        {"value": "area", "label": "Area"},
                        {"value": "bar", "label": "Bar"},
                    ],
                    show_smooth=True,
                    smooth_max=40,
                    smooth_default=15,
                    store_data=True,
                    paper_padding="md",
                ),
                span={"base": 12, "md": 6},
            ),
        ]),

        # Detail table
        detail_table(
            "tx-detail-grid",
            title="Session Detail",
            export_id="tx-detail-export",
        ),

        # Stores
        dcc.Store(id="tx-store-kpi-sparklines"),

        # Interval for periodic refresh
        dcc.Interval(id="tx-interval", interval=300_000, n_intervals=0),
    ],
)


# ---------------------------------------------------------------------------
# Register chart settings callbacks
# ---------------------------------------------------------------------------
register_chart_callbacks([
    ("tx-volume", "tx-chart-volume"),
    ("tx-technique", "tx-chart-technique"),
    ("tx-fields", "tx-chart-fields"),
    ("tx-newstarts", "tx-chart-newstarts"),
    ("tx-gating", "tx-chart-gating"),
    ("tx-multiiso", "tx-chart-multiiso"),
    ("tx-osms", "tx-chart-osms"),
])


# ---------------------------------------------------------------------------
# Filter sync callbacks
# ---------------------------------------------------------------------------

def _register_tx_filter_callbacks():
    """Register all filter-sync callbacks for the treatment page."""

    # A) Preset -> Slider + DatePicker
    @callback(
        Output("tx-date-slider", "value"),
        Output("tx-filter-daterange", "start_date", allow_duplicate=True),
        Output("tx-filter-daterange", "end_date", allow_duplicate=True),
        Input("tx-filter-date-preset", "value"),
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

    # B) Slider -> DatePicker + Label (clientside)
    clientside_callback(
        ClientsideFunction(namespace="txDateSlider", function_name="syncSlider"),
        Output("tx-filter-daterange", "start_date", allow_duplicate=True),
        Output("tx-filter-daterange", "end_date", allow_duplicate=True),
        Output("tx-date-range-label", "children"),
        Input("tx-date-slider", "value"),
        State("tx-filter-daterange", "start_date"),
        State("tx-filter-daterange", "end_date"),
        prevent_initial_call=True,
    )

    # C) DatePicker -> Slider
    @callback(
        Output("tx-date-slider", "value", allow_duplicate=True),
        Input("tx-filter-daterange", "start_date"),
        Input("tx-filter-daterange", "end_date"),
        State("tx-date-slider", "value"),
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

    # D) Slider -> auto-clear preset
    @callback(
        Output("tx-filter-date-preset", "value", allow_duplicate=True),
        Input("tx-date-slider", "value"),
        State("tx-filter-date-preset", "value"),
        prevent_initial_call=True,
    )
    def _maybe_clear_preset(slider_val, current_preset):
        if not current_preset or current_preset == "custom":
            return dash.no_update
        expected = preset_to_slider_val(current_preset, MAX_IDX)
        if slider_val == expected:
            return dash.no_update
        return "custom"

    # --- Physician trigger label ---
    clientside_callback(
        """function(val) {
            if (!val) return "Physician";
            return val.split(", ")[0];
        }""",
        Output("tx-physician-trigger", "children"),
        Input("tx-filter-physician", "value"),
    )

    # --- Physician clear-button visibility ---
    clientside_callback(
        """function(val) { return val ? {"display": "inline-flex"} : {"display": "none"}; }""",
        Output("tx-physician-clear", "style"),
        Input("tx-filter-physician", "value"),
    )

    # --- Physician clear-button action ---
    clientside_callback(
        """function(n) { return null; }""",
        Output("tx-filter-physician", "value", allow_duplicate=True),
        Input("tx-physician-clear", "n_clicks"),
        prevent_initial_call=True,
    )


_register_tx_filter_callbacks()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_date_range(slider_val, daterange):
    """Calculate start/end dates from slider or explicit daterange."""
    today = pd.Timestamp.now().normalize()
    if daterange and len(daterange) == 2 and daterange[0] and daterange[1]:
        return pd.Timestamp(daterange[0]), min(pd.Timestamp(daterange[1]), today)
    if slider_val and len(slider_val) == 2:
        start = idx_to_date(slider_val[0])
        end = min(idx_to_date(slider_val[1], end_of_month=True), today)
        return start, end
    return pd.Timestamp("2000-01-01"), today


def _prior_range(start, end, preset):
    """Compute the prior-period range for trend comparison."""
    if not start or not end:
        return None, None, None
    _PRIOR_MAP = {
        "12mo": ("vs prior 12 mo", lambda s, e: (s - (e - s) - pd.Timedelta(days=1), s - pd.Timedelta(days=1))),
        "6mo": ("vs prior 6 mo", lambda s, e: (s - (e - s) - pd.Timedelta(days=1), s - pd.Timedelta(days=1))),
        "3mo": ("vs prior 3 mo", lambda s, e: (s - (e - s) - pd.Timedelta(days=1), s - pd.Timedelta(days=1))),
        "30d": ("vs prior 30 days", lambda s, e: (s - (e - s) - pd.Timedelta(days=1), s - pd.Timedelta(days=1))),
        "ytd": ("vs prior YTD", lambda s, e: (
            pd.Timestamp(s.year - 1, 1, 1),
            min(pd.Timestamp(s.year - 1, e.month, min(e.day, 28)), pd.Timestamp(s.year - 1, 12, 31)),
        )),
        "last_year": ("vs year before", lambda s, e: (
            pd.Timestamp(s.year - 1, 1, 1), pd.Timestamp(s.year - 1, 12, 31),
        )),
        "this_month": ("vs last MTD", lambda s, e: (
            s - pd.DateOffset(months=1), e - pd.DateOffset(months=1),
        )),
        "last_month": ("vs month before", lambda s, e: (
            s - pd.DateOffset(months=1), s - pd.Timedelta(days=1),
        )),
    }
    if preset not in _PRIOR_MAP:
        return None, None, None
    label, fn = _PRIOR_MAP[preset]
    prior_start, prior_end = fn(start, end)
    return prior_start, prior_end, label


def _trend(curr, prior):
    """Compute trend text and direction."""
    if prior is None or prior == 0:
        return None, None
    pct = (curr - prior) / abs(prior) * 100
    direction = "up" if pct > 0 else "down"
    return f"{abs(pct):.0f}%", direction


# ---------------------------------------------------------------------------
# Main server callback — KPIs + all chart stores + detail table
# ---------------------------------------------------------------------------

@callback(
    # KPIs
    Output("tx-kpi-volume", "children"),
    Output("tx-kpi-newstarts", "children"),
    Output("tx-kpi-patients", "children"),
    Output("tx-kpi-elapsed", "children"),
    Output("tx-kpi-fields", "children"),
    Output("tx-kpi-gating", "children"),
    # Chart stores
    Output("tx-chart-volume-store", "data"),
    Output("tx-chart-technique-store", "data"),
    Output("tx-chart-fields-store", "data"),
    Output("tx-chart-newstarts-store", "data"),
    Output("tx-chart-gating-store", "data"),
    Output("tx-chart-multiiso-store", "data"),
    Output("tx-chart-osms-store", "data"),
    # Violin plot (server-side figure)
    Output("tx-chart-elapsed", "figure"),
    # Detail table
    Output("tx-detail-grid", "rowData"),
    Output("tx-detail-grid", "columnDefs"),
    # Sparkline store
    Output("tx-store-kpi-sparklines", "data"),
    # Inputs
    Input("tx-interval", "n_intervals"),
    Input("tx-date-slider", "value"),
    Input("tx-filter-date-preset", "value"),
    Input("tx-filter-department", "value"),
    Input("tx-filter-physician", "value"),
    Input("tx-elapsed-groupby", "value"),
    Input("tx-newstarts-metric", "value"),
    running=[
        (Output("tx-chart-volume-loading", "visible"), True, False),
        (Output("tx-chart-technique-loading", "visible"), True, False),
        (Output("tx-chart-elapsed-loading", "visible"), True, False),
        (Output("tx-chart-fields-loading", "visible"), True, False),
        (Output("tx-chart-newstarts-loading", "visible"), True, False),
        (Output("tx-chart-gating-loading", "visible"), True, False),
        (Output("tx-chart-multiiso-loading", "visible"), True, False),
        (Output("tx-chart-osms-loading", "visible"), True, False),
    ],
)
def update_treatment(_n, slider_val, date_preset, departments, physician,
                     elapsed_groupby, newstarts_metric):
    from data.loader import load_treatment, load_treatment_detail

    na_kpi = kpi_card("--", "N/A")
    empty = empty_figure()
    empty_result = (na_kpi,) * 6 + (None,) * 7 + (empty, [], [], {})

    try:
        df_agg = load_treatment()
        df_det = load_treatment_detail()
    except Exception:
        return empty_result

    if df_agg.empty and df_det.empty:
        return empty_result

    # ---- Holidays (exclude weekends + holidays from daily data) ----
    holidays = get_holidays()

    # ---- Date range from slider ----
    start, end = _get_date_range(slider_val, None)

    # ---- Filter Treatment.csv (aggregated) to site-level rows ----
    if not df_agg.empty:
        df_agg = df_agg[df_agg["Department"].isin(_SITE_DEPTS)].copy()
        if departments:
            df_agg = df_agg[df_agg["Department"].isin(departments)]
        # Exclude weekends and holidays
        df_agg = df_agg[df_agg["ScheduledDate"].dt.weekday < 5]
        if holidays:
            df_agg = df_agg[~df_agg["ScheduledDate"].dt.normalize().isin(holidays)]
        df_agg_filtered = df_agg[
            (df_agg["ScheduledDate"] >= start) & (df_agg["ScheduledDate"] <= end)
        ]
    else:
        df_agg_filtered = pd.DataFrame()

    # ---- Filter Treatment-Detail ----
    if not df_det.empty:
        if departments:
            df_det_f = df_det[df_det["Department"].isin(departments)]
        else:
            df_det_f = df_det
        if physician:
            df_det_f = df_det_f[df_det_f["TreatingPhysician"] == physician]
        # Exclude weekends and holidays
        df_det_f = df_det_f[df_det_f["ScheduledDateTime"].dt.weekday < 5]
        if holidays:
            df_det_f = df_det_f[~df_det_f["ScheduledDateTime"].dt.normalize().isin(holidays)]
        df_det_filtered = df_det_f[
            (df_det_f["ScheduledDateTime"] >= start) & (df_det_f["ScheduledDateTime"] <= end)
        ]
    else:
        df_det_filtered = pd.DataFrame()

    # ---- Prior period for trends ----
    prior_start, prior_end, trend_label = _prior_range(start, end, date_preset)
    df_agg_prior = pd.DataFrame()
    df_det_prior = pd.DataFrame()
    if prior_start is not None and not df_agg.empty:
        df_agg_prior = df_agg[
            (df_agg["ScheduledDate"] >= prior_start) & (df_agg["ScheduledDate"] <= prior_end)
        ]
    if prior_start is not None and not df_det.empty:
        det_src = df_det_f if not df_det.empty else df_det
        df_det_prior = det_src[
            (det_src["ScheduledDateTime"] >= prior_start) & (det_src["ScheduledDateTime"] <= prior_end)
        ]

    # ==================================================================
    # KPIs + sparkline data (raw values → store for clientside smoothing)
    # ==================================================================
    kpis = []
    sparkline_data = {}

    # Sparkline period: daily or weekly depending on range length
    range_days = (end - start).days
    _spark_period = "D" if range_days <= 90 else "W"

    def _build_spark(series, key, color, hover_fmt=None):
        """Add a sparkline entry to sparkline_data."""
        if series is None or len(series) < 3:
            return
        if _spark_period == "W" and hasattr(series, "resample"):
            series = series.resample("W").mean()
        if len(series) < 3:
            return
        sparkline_data[key] = {
            "labels": [d.isoformat() for d in series.index],
            "values": [round(float(v), 2) if pd.notna(v) else None for v in series.values],
            "color": color,
        }
        if hover_fmt:
            sparkline_data[key]["hover_fmt"] = hover_fmt

    # 1. Daily Treatments (avg per business day)
    if not df_agg_filtered.empty and "CompletedAppointments" in df_agg_filtered.columns:
        val = df_agg_filtered["CompletedAppointments"].mean()
        t_text, t_dir = None, None
        if not df_agg_prior.empty:
            t_text, t_dir = _trend(val, df_agg_prior["CompletedAppointments"].mean())
            if t_text:
                t_text = f"{t_text} {trend_label}"
        spark_s = df_agg_filtered.set_index("ScheduledDate")["CompletedAppointments"].sort_index()
        _build_spark(spark_s, "volume", DEPARTMENT_COLORS["Lacey"])
        kpis.append(kpi_card(
            "Daily Treatments (avg)", f"{val:,.1f}",
            accent_color=DEPARTMENT_COLORS["Lacey"],
            trend_text=t_text, trend_direction=t_dir,
            sparkline_id="tx-spark-volume",
        ))
    else:
        kpis.append(na_kpi)

    # 2. New Starts
    ns_col = "NewStarts_ByFraction"
    if not df_agg_filtered.empty and ns_col in df_agg_filtered.columns:
        ns_val = df_agg_filtered[ns_col].sum()
        t_text, t_dir = None, None
        if not df_agg_prior.empty and ns_col in df_agg_prior.columns:
            ns_prior = df_agg_prior[ns_col].sum()
            t_text, t_dir = _trend(ns_val, ns_prior)
            if t_text:
                t_text = f"{t_text} {trend_label}"
        spark_s = df_agg_filtered.set_index("ScheduledDate")[ns_col].sort_index()
        spark_w = spark_s.resample("W").sum()
        if len(spark_w) >= 3:
            sparkline_data["newstarts"] = {
                "labels": [d.isoformat() for d in spark_w.index],
                "values": spark_w.tolist(),
                "color": SEMANTIC_COLORS["info"],
            }
        kpis.append(kpi_card(
            "New Starts (period)", f"{int(ns_val):,}",
            accent_color=SEMANTIC_COLORS["info"],
            trend_text=t_text, trend_direction=t_dir,
            sparkline_id="tx-spark-newstarts",
        ))
    else:
        kpis.append(na_kpi)

    # 3. Unique Patients (avg per day)
    if not df_agg_filtered.empty and "UniquePatients" in df_agg_filtered.columns:
        val = df_agg_filtered["UniquePatients"].mean()
        t_text, t_dir = None, None
        if not df_agg_prior.empty:
            t_text, t_dir = _trend(val, df_agg_prior["UniquePatients"].mean())
            if t_text:
                t_text = f"{t_text} {trend_label}"
        spark_s = df_agg_filtered.set_index("ScheduledDate")["UniquePatients"].sort_index()
        _build_spark(spark_s, "patients", SEMANTIC_COLORS["success"])
        kpis.append(kpi_card(
            "Unique Patients (avg/day)", f"{val:,.1f}",
            accent_color=SEMANTIC_COLORS["success"],
            trend_text=t_text, trend_direction=t_dir,
            sparkline_id="tx-spark-patients",
        ))
    else:
        kpis.append(na_kpi)

    # 4. Avg Session Time (median from Detail)
    if not df_det_filtered.empty and "SessionElapsedMinutes" in df_det_filtered.columns:
        elapsed = df_det_filtered["SessionElapsedMinutes"].dropna()
        elapsed = elapsed[(elapsed > 0) & (elapsed <= 60)]
        val = elapsed.median()
        t_text, t_dir = None, None
        if not df_det_prior.empty and "SessionElapsedMinutes" in df_det_prior.columns:
            ep = df_det_prior["SessionElapsedMinutes"].dropna()
            ep = ep[(ep > 0) & (ep <= 60)]
            if not ep.empty:
                t_text, t_dir = _trend(val, ep.median())
                if t_text:
                    t_text = f"{t_text} {trend_label}"
        tmp = df_det_filtered[["ScheduledDateTime", "SessionElapsedMinutes"]].copy()
        tmp = tmp[(tmp["SessionElapsedMinutes"] > 0) & (tmp["SessionElapsedMinutes"] <= 60)]
        tmp["_d"] = tmp["ScheduledDateTime"].dt.normalize()
        spark_s = tmp.groupby("_d")["SessionElapsedMinutes"].median().sort_index()
        _build_spark(spark_s, "elapsed", CHART_COLORWAY[4],
                     hover_fmt="%{x|%b %d}: %{customdata:,.1f} min<extra></extra>")
        kpis.append(kpi_card(
            "Session Time (median)", f"{val:,.1f} min",
            accent_color=CHART_COLORWAY[4],
            trend_text=t_text, trend_direction=t_dir,
            sparkline_id="tx-spark-elapsed",
        ))
    else:
        kpis.append(na_kpi)

    # 5. Avg Fields/Session
    if not df_det_filtered.empty and "FieldCount" in df_det_filtered.columns:
        fc = df_det_filtered["FieldCount"].dropna()
        val = fc.mean()
        t_text, t_dir = None, None
        if not df_det_prior.empty and "FieldCount" in df_det_prior.columns:
            fp = df_det_prior["FieldCount"].dropna()
            if not fp.empty:
                t_text, t_dir = _trend(val, fp.mean())
                if t_text:
                    t_text = f"{t_text} {trend_label}"
        tmp = df_det_filtered[["ScheduledDateTime", "FieldCount"]].dropna().copy()
        tmp["_d"] = tmp["ScheduledDateTime"].dt.normalize()
        spark_s = tmp.groupby("_d")["FieldCount"].mean().sort_index()
        _build_spark(spark_s, "fields", CHART_COLORWAY[5])
        kpis.append(kpi_card(
            "Fields/Session (avg)", f"{val:,.1f}",
            accent_color=CHART_COLORWAY[5],
            trend_text=t_text, trend_direction=t_dir,
            sparkline_id="tx-spark-fields",
        ))
    else:
        kpis.append(na_kpi)

    # 6. Gating %
    if not df_det_filtered.empty and "FieldGating" in df_det_filtered.columns:
        gating = df_det_filtered["FieldGating"].dropna()
        val = gating.mean() * 100
        t_text, t_dir = None, None
        if not df_det_prior.empty and "FieldGating" in df_det_prior.columns:
            gp = df_det_prior["FieldGating"].dropna()
            if not gp.empty:
                t_text, t_dir = _trend(val, gp.mean() * 100)
                if t_text:
                    t_text = f"{t_text} {trend_label}"
        tmp = df_det_filtered[["ScheduledDateTime", "FieldGating"]].dropna().copy()
        tmp["_d"] = tmp["ScheduledDateTime"].dt.normalize()
        spark_s = (tmp.groupby("_d")["FieldGating"].mean() * 100).sort_index()
        _build_spark(spark_s, "gating", CHART_COLORWAY[6],
                     hover_fmt="%{x|%b %d}: %{customdata:,.1f}%<extra></extra>")
        kpis.append(kpi_card(
            "Gating Utilization", f"{val:,.1f}%",
            accent_color=CHART_COLORWAY[6],
            trend_text=t_text, trend_direction=t_dir,
            sparkline_id="tx-spark-gating",
        ))
    else:
        kpis.append(na_kpi)

    # ==================================================================
    # Chart 1: Treatment Volume by Department (store for clientside)
    # ==================================================================
    volume_data = None
    if not df_agg_filtered.empty and "CompletedAppointments" in df_agg_filtered.columns:
        vdf = df_agg_filtered[["ScheduledDate", "Department", "CompletedAppointments"]].copy()
        vdf = vdf.sort_values("ScheduledDate")
        dates_all = sorted(vdf["ScheduledDate"].dropna().unique())
        dates_str = [pd.Timestamp(d).isoformat() for d in dates_all]
        series = []
        for dept in DEPARTMENTS:
            sub = vdf[vdf["Department"] == dept]
            daily = sub.groupby("ScheduledDate")["CompletedAppointments"].sum()
            daily = daily.reindex(dates_all, fill_value=0)
            series.append({
                "name": dept,
                "values": daily.tolist(),
                "color": DEPARTMENT_COLORS.get(dept, CHART_COLORWAY[0]),
            })
        volume_data = {
            "dates": dates_str,
            "series": series,
            "yTitle": "Treatments",
            "height": 380,
        }

    # ==================================================================
    # Chart 2: Technique Mix (store for clientside)
    # ==================================================================
    technique_data = None
    if not df_det_filtered.empty and "PlanTechniques" in df_det_filtered.columns:
        tdf = df_det_filtered[["ScheduledDateTime", "PlanTechniques"]].copy()
        tdf["Technique"] = tdf["PlanTechniques"].apply(_bucket_technique)
        tdf["_d"] = tdf["ScheduledDateTime"].dt.normalize()
        dates_all = sorted(tdf["_d"].dropna().unique())
        dates_str = [pd.Timestamp(d).isoformat() for d in dates_all]
        series = []
        for tech in _TECHNIQUE_ORDER:
            sub = tdf[tdf["Technique"] == tech]
            if sub.empty:
                continue
            daily = sub.groupby("_d").size()
            daily = daily.reindex(dates_all, fill_value=0)
            series.append({
                "name": tech,
                "values": daily.tolist(),
                "color": _TECHNIQUE_COLORS.get(tech, CHART_COLORWAY[0]),
            })
        if series:
            technique_data = {
                "dates": dates_str,
                "series": series,
                "yTitle": "Sessions",
                "height": 380,
            }

    # ==================================================================
    # Chart 3: Session Duration Violin Plot (server-side figure)
    # ==================================================================
    elapsed_fig = empty
    if not df_det_filtered.empty and "SessionElapsedMinutes" in df_det_filtered.columns:
        edf = df_det_filtered[["SessionElapsedMinutes", "Department", "Machine"]].copy()
        edf = edf[(edf["SessionElapsedMinutes"] > 0) & (edf["SessionElapsedMinutes"] <= 60)]
        if not edf.empty:
            fig = go.Figure()
            group_col = "Department" if elapsed_groupby == "department" else "Machine"
            groups = sorted(edf[group_col].dropna().unique())
            for grp in groups:
                sub = edf[edf[group_col] == grp]["SessionElapsedMinutes"]
                if group_col == "Department":
                    color = DEPARTMENT_COLORS.get(grp, CHART_COLORWAY[0])
                else:
                    dept = MACHINE_DEPT.get(grp, "")
                    color = DEPARTMENT_COLORS.get(dept, CHART_COLORWAY[0])
                fig.add_trace(go.Violin(
                    y=sub,
                    name=grp,
                    line_color=color,
                    fillcolor=color,
                    opacity=0.6,
                    meanline_visible=True,
                    box_visible=True,
                    points=False,
                    scalemode="width",
                    width=0.6,
                ))
            apply_default_layout(fig, yaxis_title="Minutes", showlegend=False)
            fig.update_layout(
                yaxis=dict(range=[0, min(60, edf["SessionElapsedMinutes"].quantile(0.99) + 5)]),
                violinmode="group",
            )
            elapsed_fig = fig

    # ==================================================================
    # Chart 4: Field Type Breakdown (store for clientside)
    # ==================================================================
    fields_data = None
    if not df_agg_filtered.empty:
        field_cols = {
            "Fields_Arc": "Arc",
            "Fields_DynamicMLC": "Dynamic MLC",
            "Fields_StaticMLC": "Static MLC",
            "Fields_Electron": "Electron",
        }
        available = {k: v for k, v in field_cols.items() if k in df_agg_filtered.columns}
        if available:
            fdf = df_agg_filtered[["ScheduledDate"] + list(available.keys())].copy()
            fdf = fdf.fillna(0)
            dates_all = sorted(fdf["ScheduledDate"].dropna().unique())
            dates_str = [pd.Timestamp(d).isoformat() for d in dates_all]
            series = []
            for col, label in available.items():
                daily = fdf.groupby("ScheduledDate")[col].sum()
                daily = daily.reindex(dates_all, fill_value=0)
                series.append({
                    "name": label,
                    "values": daily.tolist(),
                    "color": _FIELD_COLORS.get(label, CHART_COLORWAY[0]),
                })
            fields_data = {
                "dates": dates_str,
                "series": series,
                "yTitle": "Fields",
                "height": 380,
            }

    # ==================================================================
    # Chart 5: New Starts Trend (store for clientside)
    # ==================================================================
    newstarts_data = None
    if not df_agg_filtered.empty:
        ns_metric = ("NewStarts_ByCourseFirstTreatmentDate"
                     if newstarts_metric == "course"
                     else "NewStarts_ByFraction")
        if ns_metric in df_agg_filtered.columns:
            nsdf = df_agg_filtered[["ScheduledDate", "Department", ns_metric]].copy()
            nsdf = nsdf.sort_values("ScheduledDate")
            dates_all = sorted(nsdf["ScheduledDate"].dropna().unique())
            dates_str = [pd.Timestamp(d).isoformat() for d in dates_all]
            series = []
            for dept in DEPARTMENTS:
                sub = nsdf[nsdf["Department"] == dept]
                daily = sub.groupby("ScheduledDate")[ns_metric].sum()
                daily = daily.reindex(dates_all, fill_value=0)
                series.append({
                    "name": dept,
                    "values": daily.tolist(),
                    "color": DEPARTMENT_COLORS.get(dept, CHART_COLORWAY[0]),
                })
            newstarts_data = {
                "dates": dates_str,
                "series": series,
                "yTitle": "New Starts",
                "height": 380,
            }

    # ==================================================================
    # Chart 6: Gating Utilization Trend (store for clientside)
    # ==================================================================
    gating_data = None
    if not df_det_filtered.empty and "FieldGating" in df_det_filtered.columns:
        gdf = df_det_filtered[["ScheduledDateTime", "FieldGating"]].dropna().copy()
        gdf["_d"] = gdf["ScheduledDateTime"].dt.normalize()
        daily_pct = gdf.groupby("_d")["FieldGating"].mean() * 100
        daily_pct = daily_pct.sort_index()
        dates_str = [d.isoformat() for d in daily_pct.index]
        gating_data = {
            "dates": dates_str,
            "series": [{
                "name": "Gating %",
                "values": [round(v, 1) for v in daily_pct.tolist()],
                "color": CHART_COLORWAY[6],
            }],
            "stacked": False,
            "yTitle": "% of Sessions",
            "height": 380,
        }

    # ==================================================================
    # Chart 7: Multi-Isocenter Rate (store for clientside)
    # ==================================================================
    multiiso_data = None
    if not df_det_filtered.empty and "UniqueIsocenters" in df_det_filtered.columns:
        midf = df_det_filtered[["ScheduledDateTime", "UniqueIsocenters", "Department"]].dropna().copy()
        midf["_multi"] = (midf["UniqueIsocenters"] > 1).astype(int)
        midf["_d"] = midf["ScheduledDateTime"].dt.normalize()
        dates_all = sorted(midf["_d"].unique())
        dates_str = [pd.Timestamp(d).isoformat() for d in dates_all]
        series = []
        for dept in DEPARTMENTS:
            sub = midf[midf["Department"] == dept]
            if sub.empty:
                continue
            daily_rate = sub.groupby("_d")["_multi"].mean() * 100
            daily_rate = daily_rate.reindex(dates_all, fill_value=0)
            series.append({
                "name": dept,
                "values": [round(v, 1) for v in daily_rate.tolist()],
                "color": DEPARTMENT_COLORS.get(dept, CHART_COLORWAY[0]),
            })
        if series:
            multiiso_data = {
                "dates": dates_str,
                "series": series,
                "yTitle": "% Multi-Iso Sessions",
                "height": 380,
            }

    # ==================================================================
    # Chart 8: OSMS Adoption (store for clientside)
    # ==================================================================
    osms_data = None
    if not df_det_filtered.empty and "HasOSMS" in df_det_filtered.columns:
        odf = df_det_filtered[["ScheduledDateTime", "HasOSMS", "Machine"]].dropna().copy()
        odf["_d"] = odf["ScheduledDateTime"].dt.normalize()
        dates_all = sorted(odf["_d"].unique())
        dates_str = [pd.Timestamp(d).isoformat() for d in dates_all]
        # By machine — OSMS adoption varies heavily by machine
        series = []
        machines = sorted(odf["Machine"].unique())
        for i, machine in enumerate(machines):
            sub = odf[odf["Machine"] == machine]
            daily_rate = sub.groupby("_d")["HasOSMS"].mean() * 100
            daily_rate = daily_rate.reindex(dates_all, fill_value=0)
            dept = MACHINE_DEPT.get(machine, "")
            color = DEPARTMENT_COLORS.get(dept, CHART_COLORWAY[i % len(CHART_COLORWAY)])
            series.append({
                "name": machine,
                "values": [round(v, 1) for v in daily_rate.tolist()],
                "color": color,
            })
        if series:
            osms_data = {
                "dates": dates_str,
                "series": series,
                "stacked": False,
                "yTitle": "% OSMS Sessions",
                "height": 380,
            }

    # ==================================================================
    # Detail Table
    # ==================================================================
    row_data = []
    col_defs = []
    if not df_det_filtered.empty:
        table_cols = {
            "ScheduledDateTime": ("Date", 140),
            "PatientId": ("MRN", 90),
            "PatientFullName": ("Patient", 150),
            "Machine": ("Machine", 120),
            "Department": ("Dept", 90),
            "TreatingPhysician": ("Physician", 140),
            "CourseName": ("Course", 110),
            "PlanTechniques": ("Technique", 110),
            "FractionNumber": ("Fx #", 65),
            "TotalFractions": ("Total Fx", 75),
            "SessionElapsedMinutes": ("Session (min)", 100),
            "BeamElapsedMinutes": ("Beam (min)", 90),
            "FieldCount": ("Fields", 65),
            "UniqueIsocenters": ("Isocenters", 90),
            "FieldGating": ("Gating", 70),
            "IsNewStart_ByFraction": ("New Start", 85),
            "BillingPhysician": ("Billing MD", 140),
        }
        available_cols = {k: v for k, v in table_cols.items() if k in df_det_filtered.columns}

        col_defs = []
        for col_name, (header, width) in available_cols.items():
            cd = {"field": col_name, "headerName": header, "width": width}
            if col_name == "ScheduledDateTime":
                cd["valueFormatter"] = {"function": "d3.timeFormat('%m/%d/%Y %I:%M %p')(new Date(params.value))"}
                cd["sort"] = "desc"
            elif col_name in ("SessionElapsedMinutes", "BeamElapsedMinutes"):
                cd["valueFormatter"] = {"function": "params.value != null ? params.value.toFixed(1) : ''"}
            col_defs.append(cd)

        # Limit to most recent 5000 rows to keep browser responsive
        tbl = df_det_filtered.sort_values("ScheduledDateTime", ascending=False).head(5000)
        for col in ["ScheduledDateTime"]:
            if col in tbl.columns:
                tbl[col] = tbl[col].dt.strftime("%Y-%m-%dT%H:%M:%S")
        row_data = tbl[list(available_cols.keys())].to_dict("records")

    return (*kpis, volume_data, technique_data, fields_data, newstarts_data,
            gating_data, multiiso_data, osms_data,
            elapsed_fig, row_data, col_defs, sparkline_data)


# ---------------------------------------------------------------------------
# Clientside callbacks — KPI sparklines via store + smooth slider
# ---------------------------------------------------------------------------

clientside_callback(
    ClientsideFunction(namespace="sparklines", function_name="smoothTxVolume"),
    Output("tx-spark-volume", "figure"),
    Input("tx-store-kpi-sparklines", "data"),
    Input("tx-smooth-slider", "value"),
)

clientside_callback(
    ClientsideFunction(namespace="sparklines", function_name="smoothTxNewstarts"),
    Output("tx-spark-newstarts", "figure"),
    Input("tx-store-kpi-sparklines", "data"),
    Input("tx-smooth-slider", "value"),
)

clientside_callback(
    ClientsideFunction(namespace="sparklines", function_name="smoothTxPatients"),
    Output("tx-spark-patients", "figure"),
    Input("tx-store-kpi-sparklines", "data"),
    Input("tx-smooth-slider", "value"),
)

clientside_callback(
    ClientsideFunction(namespace="sparklines", function_name="smoothTxElapsed"),
    Output("tx-spark-elapsed", "figure"),
    Input("tx-store-kpi-sparklines", "data"),
    Input("tx-smooth-slider", "value"),
)

clientside_callback(
    ClientsideFunction(namespace="sparklines", function_name="smoothTxFields"),
    Output("tx-spark-fields", "figure"),
    Input("tx-store-kpi-sparklines", "data"),
    Input("tx-smooth-slider", "value"),
)

clientside_callback(
    ClientsideFunction(namespace="sparklines", function_name="smoothTxGating"),
    Output("tx-spark-gating", "figure"),
    Input("tx-store-kpi-sparklines", "data"),
    Input("tx-smooth-slider", "value"),
)


# ---------------------------------------------------------------------------
# Clientside callbacks — chart rendering via census.smoothChartWithType
# ---------------------------------------------------------------------------

clientside_callback(
    ClientsideFunction("census", "smoothChartWithType"),
    Output("tx-chart-volume", "figure"),
    Input("tx-chart-volume-store", "data"),
    Input("tx-volume-settings-smooth", "value"),
    Input("tx-volume-settings-type", "value"),
    State("tx-chart-volume", "figure"),
)

clientside_callback(
    ClientsideFunction("census", "smoothChartWithType"),
    Output("tx-chart-technique", "figure"),
    Input("tx-chart-technique-store", "data"),
    Input("tx-technique-settings-smooth", "value"),
    Input("tx-technique-settings-type", "value"),
    State("tx-chart-technique", "figure"),
)

clientside_callback(
    ClientsideFunction("census", "smoothChartWithType"),
    Output("tx-chart-fields", "figure"),
    Input("tx-chart-fields-store", "data"),
    Input("tx-fields-settings-smooth", "value"),
    Input("tx-fields-settings-type", "value"),
    State("tx-chart-fields", "figure"),
)

clientside_callback(
    ClientsideFunction("census", "smoothChartWithType"),
    Output("tx-chart-newstarts", "figure"),
    Input("tx-chart-newstarts-store", "data"),
    Input("tx-newstarts-settings-smooth", "value"),
    Input("tx-newstarts-settings-type", "value"),
    State("tx-chart-newstarts", "figure"),
)

clientside_callback(
    ClientsideFunction("census", "smoothChartWithType"),
    Output("tx-chart-gating", "figure"),
    Input("tx-chart-gating-store", "data"),
    Input("tx-gating-settings-smooth", "value"),
    Input("tx-gating-settings-type", "value"),
    State("tx-chart-gating", "figure"),
)

# Multi-iso chart
clientside_callback(
    ClientsideFunction("census", "smoothChartWithType"),
    Output("tx-chart-multiiso", "figure"),
    Input("tx-chart-multiiso-store", "data"),
    Input("tx-multiiso-settings-smooth", "value"),
    Input("tx-multiiso-settings-type", "value"),
    State("tx-chart-multiiso", "figure"),
)

# OSMS chart
clientside_callback(
    ClientsideFunction("census", "smoothChartWithType"),
    Output("tx-chart-osms", "figure"),
    Input("tx-chart-osms-store", "data"),
    Input("tx-osms-settings-smooth", "value"),
    Input("tx-osms-settings-type", "value"),
    State("tx-chart-osms", "figure"),
)


# ---------------------------------------------------------------------------
# Detail table CSV export
# ---------------------------------------------------------------------------
clientside_callback(
    """function(n) {
        if (!n) return window.dash_clientside.no_update;
        var gridApi = window.dash_ag_grid
            ? window.dash_ag_grid['tx-detail-grid']
            : null;
        if (gridApi && gridApi.api) {
            gridApi.api.exportDataAsCsv({fileName: 'treatment_sessions.csv'});
        }
        return window.dash_clientside.no_update;
    }""",
    Output("tx-detail-export", "n_clicks"),
    Input("tx-detail-export", "n_clicks"),
    prevent_initial_call=True,
)
