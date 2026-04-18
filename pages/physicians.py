"""Physicians page — manpower, assignments, after-hours work, cross-coverage."""

import dash
import dash_mantine_components as dmc
from dash import callback, clientside_callback, ClientsideFunction, Input, Output, State, dcc, html
from dash_iconify import DashIconify
import dash_ag_grid as dag
import plotly.graph_objects as go
import pandas as pd
from datetime import timedelta

from config.settings import (
    DEPARTMENTS, DEPARTMENT_COLORS, PRIMARY, NEUTRAL,
    SEMANTIC_COLORS, CHART_COLORWAY, CHART_PAPER_HEIGHT,
    DEFAULT_COLUMN_DEFS, DEFAULT_GRID_OPTIONS, DEFAULT_GRID_STYLE, DEFAULT_GRID_CLASS,
)
from components.chart_settings import chart_settings_popover
from components.detail_table import detail_table
from components.kpi_card import kpi_card, kpi_placeholder
from utils.charts import apply_default_layout, empty_figure, color_for_index
from utils.tables import sanitize_for_grid
from utils.date_slider import (
    month_idx, idx_to_date, MAX_IDX, DEFAULT_SLIDER, SLIDER_MARKS,
    preset_to_slider_val, preset_to_exact_dates,
)

dash.register_page(__name__, path="/physicians", name="Physicians", order=10)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
PAGE_ID = "phys"
_DEFAULT_DATE_PRESET = "12mo"

# Statuses that indicate a physician is NOT working
_OFF_STATUSES = {"OFF", "VACATION", "SICK", "SICK LEAVE"}

# Statuses that indicate a physician is on duty (site assignments + on call)
_ON_DUTY = {"LACEY", "CENTRALIA", "ABERDEEN", "ON CALL", "ON", "WEEKEND CALL"}


# ---------------------------------------------------------------------------
# Filter Bar (two-row: dimension filters + date controls)
# ---------------------------------------------------------------------------
def _build_filter_bar():
    return dmc.Paper(
        children=[
            dmc.Group(
                children=[
                    dmc.Select(
                        id=f"{PAGE_ID}-filter-date-preset",
                        data=[
                            {"value": "12mo", "label": "Prior 12 mo"},
                            {"value": "6mo", "label": "Prior 6 mo"},
                            {"value": "3mo", "label": "Prior 3 mo"},
                            {"value": "30d", "label": "Prior 30 days"},
                            {"value": "ytd", "label": "Year to Date"},
                            {"value": "current_year", "label": "Current Year"},
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
                            id=f"{PAGE_ID}-filter-daterange",
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
                            html.Div(id=f"{PAGE_ID}-date-range-label", style={"display": "none"}),
                            dmc.RangeSlider(
                                id=f"{PAGE_ID}-date-slider",
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
                    dmc.Group(gap=8, align="center", children=[
                        dmc.Text("Smoothing", size="sm", c="#9CA3AF", fw=500),
                        dmc.Slider(
                            id=f"{PAGE_ID}-filter-smoothing",
                            min=0, max=1, step=0.01, value=0.4,
                            size="xs", w=120,
                            showLabelOnHover=False,
                            updatemode="drag",
                        ),
                    ]),
                ],
                gap="md",
                align="center",
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
        # Sticky header with title and filter bar
        dmc.Box(
            className="page-sticky-header",
            children=[
                dmc.Title("Physicians", order=2, className="page-title",
                          style={"margin": 0, "textAlign": "center"}),
                _build_filter_bar(),
            ],
        ),

        # KPI row
        dmc.Grid(id=f"{PAGE_ID}-kpi-row", gutter="md", children=[
            dmc.GridCol(kpi_placeholder(), id=f"{PAGE_ID}-kpi-coverage", span={"base": 6, "md": 2.4}),
            dmc.GridCol(kpi_placeholder(), id=f"{PAGE_ID}-kpi-afterhours", span={"base": 6, "md": 2.4}),
            dmc.GridCol(kpi_placeholder(), id=f"{PAGE_ID}-kpi-crosscoverage", span={"base": 6, "md": 2.4}),
            dmc.GridCol(kpi_placeholder(), id=f"{PAGE_ID}-kpi-vacation", span={"base": 6, "md": 2.4}),
            dmc.GridCol(kpi_placeholder(), id=f"{PAGE_ID}-kpi-weekend", span={"base": 6, "md": 2.4}),
        ]),

        # Charts row 1: Manpower over time + Site assignments
        dmc.Grid(gutter="md", align="stretch", children=[
            dmc.GridCol(
                dmc.Paper(
                    children=[
                        dmc.Group(
                            justify="space-between", mb="sm",
                            children=[
                                dmc.Text("Manpower Over Time", size="sm", fw=500, c=NEUTRAL["text_secondary"]),
                                dmc.Group(
                                    gap="sm", align="center",
                                    children=[
                                        dmc.SegmentedControl(
                                            id=f"{PAGE_ID}-manpower-agg",
                                            data=[
                                                {"value": "D", "label": "Daily"},
                                                {"value": "W", "label": "Weekly"},
                                                {"value": "M", "label": "Monthly"},
                                                {"value": "Y", "label": "Yearly"},
                                            ],
                                            value="M",
                                            size="xs",
                                        ),
                                        chart_settings_popover(
                                            f"{PAGE_ID}-manpower",
                                            chart_types=[
                                                {"value": "line", "label": "Line"},
                                                {"value": "area", "label": "Area"},
                                                {"value": "bar", "label": "Bar"},
                                            ],
                                            chart_type_default="bar",
                                            show_smooth=True,
                                            smooth_max=50,
                                            smooth_default=15,
                                            show_grouping=False,
                                        ),
                                    ],
                                ),
                            ],
                        ),
                        dmc.Box(
                            pos="relative",
                            style={"flex": "1", "minHeight": 0},
                            children=[
                                dmc.Box(
                                    style={"position": "absolute", "inset": 0},
                                    children=[
                                        dmc.LoadingOverlay(id=f"{PAGE_ID}-manpower-loading", visible=False, loaderProps={"type": "dots", "color": PRIMARY}),
                                        dcc.Graph(id=f"{PAGE_ID}-chart-manpower", config={"displayModeBar": False}, style={"height": "100%"}),
                                    ],
                                ),
                            ],
                        ),
                    ],
                    h=CHART_PAPER_HEIGHT,
                    style={"display": "flex", "flexDirection": "column", "width": "100%"},
                    p="md", radius="md", shadow="xs", withBorder=True,
                ),
                span={"base": 12, "md": 6},
            ),
            dmc.GridCol(
                dmc.Paper(
                    children=[
                        dmc.Group(
                            justify="space-between", mb="sm",
                            children=[
                                dmc.Text("Site Assignments", size="sm", fw=500, c=NEUTRAL["text_secondary"]),
                                dmc.Group(
                                    gap="sm", align="center",
                                    children=[
                                        dmc.SegmentedControl(
                                            id=f"{PAGE_ID}-sites-mode",
                                            data=[
                                                {"value": "count", "label": "Count"},
                                                {"value": "pct", "label": "%"},
                                            ],
                                            value="count",
                                            size="xs",
                                        ),
                                        chart_settings_popover(
                                            f"{PAGE_ID}-sites",
                                            show_smooth=False,
                                            show_grouping=True,
                                            grouping_default="grouped",
                                        ),
                                    ],
                                ),
                            ],
                        ),
                        dmc.Box(
                            pos="relative",
                            style={"flex": "1", "minHeight": 0},
                            children=[
                                dmc.Box(
                                    style={"position": "absolute", "inset": 0},
                                    children=[
                                        dmc.LoadingOverlay(id=f"{PAGE_ID}-sites-loading", visible=False, loaderProps={"type": "dots", "color": PRIMARY}),
                                        dcc.Graph(id=f"{PAGE_ID}-chart-sites", config={"displayModeBar": False}, style={"height": "100%"}),
                                    ],
                                ),
                            ],
                        ),
                    ],
                    h=CHART_PAPER_HEIGHT,
                    style={"display": "flex", "flexDirection": "column", "width": "100%"},
                    p="md", radius="md", shadow="xs", withBorder=True,
                ),
                span={"base": 12, "md": 6},
            ),
        ]),

        # Charts row 2: After-hours work + Cross-coverage
        dmc.Grid(gutter="md", children=[
            dmc.GridCol(
                dmc.Paper(
                    children=[
                        dmc.Group(
                            justify="space-between", align="center", wrap="nowrap", mb="sm",
                            children=[
                                dmc.Group(
                                    gap="sm", align="center",
                                    children=[
                                        dmc.Text("After-Hours Tasks", size="sm", fw=500, c=NEUTRAL["text_secondary"], style={"whiteSpace": "nowrap"}),
                                        # Filter dropdown panel
                                        html.Div(
                                            [
                                                dmc.ActionIcon(
                                                    DashIconify(icon="mdi:filter-variant", width=16),
                                                    id=f"{PAGE_ID}-ah-filter-btn",
                                                    variant="subtle",
                                                    color="gray",
                                                    size="sm",
                                                ),
                                                html.Div(
                                                    dmc.Paper(
                                                        dmc.Stack(
                                                            gap="sm",
                                                            children=[
                                                                dmc.Stack(
                                                                    gap=4,
                                                                    children=[
                                                                        dmc.Text("Include", size="xs", fw=500, c="#6B7280"),
                                                                        dmc.ChipGroup(
                                                                            id=f"{PAGE_ID}-ah-toggles",
                                                                            children=[
                                                                                dmc.Chip("Weekends", value="weekends", size="xs", variant="filled", color="violet"),
                                                                                dmc.Chip("Holidays", value="holidays", size="xs", variant="filled", color="violet"),
                                                                                dmc.Chip("Off Days", value="off", size="xs", variant="filled", color="violet"),
                                                                                dmc.Chip("Vacation", value="vacation", size="xs", variant="filled", color="violet"),
                                                                            ],
                                                                            value=["weekends"],
                                                                            multiple=True,
                                                                        ),
                                                                    ],
                                                                ),
                                                                dmc.Stack(
                                                                    gap=4,
                                                                    children=[
                                                                        dmc.Group(
                                                                            gap=4,
                                                                            children=[
                                                                                dmc.Switch(
                                                                                    id=f"{PAGE_ID}-ah-hours-active",
                                                                                    size="xs",
                                                                                    checked=True,
                                                                                    color="orange",
                                                                                ),
                                                                                dmc.Text("Business hours", size="xs", fw=500, c="#6B7280"),
                                                                            ],
                                                                        ),
                                                                        dmc.Box(
                                                                            id=f"{PAGE_ID}-ah-hours-wrapper",
                                                                            children=dmc.RangeSlider(
                                                                                id=f"{PAGE_ID}-ah-hours",
                                                                                min=0, max=48, step=1,
                                                                                value=[14, 36],
                                                                                marks=[
                                                                                    {"value": 0, "label": "12a"},
                                                                                    {"value": 12, "label": "6a"},
                                                                                    {"value": 24, "label": "12p"},
                                                                                    {"value": 36, "label": "6p"},
                                                                                    {"value": 48, "label": "12a"},
                                                                                ],
                                                                                color="orange",
                                                                                size="xs",
                                                                                minRange=1,
                                                                                disabled=False,
                                                                            ),
                                                                        ),
                                                                    ],
                                                                ),
                                                            ],
                                                        ),
                                                        p="sm",
                                                        radius="md",
                                                        shadow="md",
                                                        withBorder=True,
                                                        style={"backgroundColor": "white", "minWidth": "260px"},
                                                    ),
                                                    id=f"{PAGE_ID}-ah-filter-panel",
                                                    className="chart-settings-panel chart-settings-panel--left",
                                                    style={"display": "none"},
                                                ),
                                            ],
                                            className="chart-settings-container",
                                            style={"position": "relative", "display": "inline-block"},
                                        ),
                                    ],
                                ),
                                dmc.Group(
                                    gap="sm", align="center",
                                    children=[
                                        dmc.SegmentedControl(
                                            id=f"{PAGE_ID}-ah-mode",
                                            data=[
                                                {"value": "count", "label": "Count"},
                                                {"value": "pct", "label": "%"},
                                            ],
                                            value="count",
                                            size="xs",
                                        ),
                                        chart_settings_popover(
                                            f"{PAGE_ID}-afterhours",
                                            show_smooth=False,
                                            show_grouping=False,
                                        ),
                                    ],
                                ),
                            ],
                        ),
                        dmc.Box(
                            pos="relative",
                            style={"flex": "1", "minHeight": 0},
                            children=[
                                dmc.Box(
                                    style={"position": "absolute", "inset": 0},
                                    children=[
                                        dmc.LoadingOverlay(id=f"{PAGE_ID}-afterhours-loading", visible=False, loaderProps={"type": "dots", "color": PRIMARY}),
                                        dcc.Graph(id=f"{PAGE_ID}-chart-afterhours", config={"displayModeBar": False}, style={"height": "100%"}),
                                    ],
                                ),
                            ],
                        ),
                    ],
                    h=CHART_PAPER_HEIGHT,
                    style={"display": "flex", "flexDirection": "column", "width": "100%"},
                    p="md", radius="md", shadow="xs", withBorder=True,
                ),
                span={"base": 12, "md": 6},
            ),
            dmc.GridCol(
                dmc.Paper(
                    children=[
                        dmc.Group(
                            justify="space-between", mb="sm",
                            children=[
                                dmc.Text("Cross-Coverage (Tasks for Other MDs' Patients)", size="sm", fw=500, c=NEUTRAL["text_secondary"]),
                                dmc.Group(
                                    gap="sm", align="center",
                                    children=[
                                        dmc.SegmentedControl(
                                            id=f"{PAGE_ID}-cc-mode",
                                            data=[
                                                {"value": "count", "label": "Count"},
                                                {"value": "pct", "label": "%"},
                                            ],
                                            value="count",
                                            size="xs",
                                        ),
                                        chart_settings_popover(
                                            f"{PAGE_ID}-crosscov",
                                            show_smooth=False,
                                            show_grouping=False,
                                        ),
                                    ],
                                ),
                            ],
                        ),
                        dmc.Box(
                            pos="relative",
                            style={"flex": "1", "minHeight": 0},
                            children=[
                                dmc.Box(
                                    style={"position": "absolute", "inset": 0},
                                    children=[
                                        dmc.LoadingOverlay(id=f"{PAGE_ID}-crosscov-loading", visible=False, loaderProps={"type": "dots", "color": PRIMARY}),
                                        dcc.Graph(id=f"{PAGE_ID}-chart-crosscoverage", config={"displayModeBar": False}, style={"height": "100%"}),
                                    ],
                                ),
                            ],
                        ),
                    ],
                    h=CHART_PAPER_HEIGHT,
                    style={"display": "flex", "flexDirection": "column", "width": "100%"},
                    p="md", radius="md", shadow="xs", withBorder=True,
                ),
                span={"base": 12, "md": 6},
            ),
        ]),

        # Schedule calendar heatmap (full width)
        dmc.Paper(
            children=[
                dmc.Text("Physician Schedule Calendar", size="sm", fw=500, c=NEUTRAL["text_secondary"], mb="sm"),
                dmc.Box(
                    pos="relative",
                    children=[
                        dmc.LoadingOverlay(id=f"{PAGE_ID}-calendar-loading", visible=False, loaderProps={"type": "dots", "color": PRIMARY}),
                        dcc.Graph(id=f"{PAGE_ID}-chart-calendar", config={"displayModeBar": False}),
                    ],
                ),
            ],
            p="md", radius="md", shadow="xs", withBorder=True,
        ),

        # Schedule detail table
        detail_table(
            f"{PAGE_ID}-detail-grid",
            title="Schedule Detail",
            export_id=f"{PAGE_ID}-table-export",
            column_size="autoSize",
        ),

        dcc.Store(id=f"{PAGE_ID}-store-manpower"),
        dcc.Store(id=f"{PAGE_ID}-store-kpi-sparklines"),
        dcc.Interval(id=f"{PAGE_ID}-interval", interval=300_000, n_intervals=0),
    ],
)


# ---------------------------------------------------------------------------
# Filter Sync Callbacks
# ---------------------------------------------------------------------------
def _register_filter_callbacks():

    # A) Preset -> Slider + DatePicker
    @callback(
        Output(f"{PAGE_ID}-date-slider", "value"),
        Output(f"{PAGE_ID}-filter-daterange", "start_date", allow_duplicate=True),
        Output(f"{PAGE_ID}-filter-daterange", "end_date", allow_duplicate=True),
        Input(f"{PAGE_ID}-filter-date-preset", "value"),
        prevent_initial_call=True,
    )
    def _sync_preset(preset):
        if not preset or preset == "custom":
            return (dash.no_update,) * 3
        sv = preset_to_slider_val(preset, MAX_IDX)
        s, e = preset_to_exact_dates(preset)
        return sv, s, e

    # B) Slider -> DatePicker + Label (clientside)
    clientside_callback(
        ClientsideFunction(namespace="physDateSlider", function_name="syncSlider"),
        Output(f"{PAGE_ID}-filter-daterange", "start_date", allow_duplicate=True),
        Output(f"{PAGE_ID}-filter-daterange", "end_date", allow_duplicate=True),
        Output(f"{PAGE_ID}-date-range-label", "children"),
        Input(f"{PAGE_ID}-date-slider", "value"),
        State(f"{PAGE_ID}-filter-daterange", "start_date"),
        State(f"{PAGE_ID}-filter-daterange", "end_date"),
        prevent_initial_call=True,
    )

    # C) DatePicker -> Slider
    @callback(
        Output(f"{PAGE_ID}-date-slider", "value", allow_duplicate=True),
        Input(f"{PAGE_ID}-filter-daterange", "start_date"),
        Input(f"{PAGE_ID}-filter-daterange", "end_date"),
        State(f"{PAGE_ID}-date-slider", "value"),
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
        Output(f"{PAGE_ID}-filter-date-preset", "value", allow_duplicate=True),
        Input(f"{PAGE_ID}-date-slider", "value"),
        State(f"{PAGE_ID}-filter-date-preset", "value"),
        prevent_initial_call=True,
    )
    def _maybe_clear_preset(slider_val, current_preset):
        if not current_preset or current_preset == "custom":
            return dash.no_update
        expected = preset_to_slider_val(current_preset, MAX_IDX)
        if slider_val == expected:
            return dash.no_update
        return "custom"


_register_filter_callbacks()

# Toggle business-hours slider disabled state
clientside_callback(
    """function(checked) {
        return [!checked, {opacity: checked ? 1 : 0.35, pointerEvents: checked ? 'auto' : 'none'}];
    }""",
    Output(f"{PAGE_ID}-ah-hours", "disabled"),
    Output(f"{PAGE_ID}-ah-hours-wrapper", "style"),
    Input(f"{PAGE_ID}-ah-hours-active", "checked"),
)


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


def _trend(curr, prior, invert=False):
    """Return (pct_text, direction, prior_value) for trend display."""
    if prior is None or prior == 0:
        return None, None, None
    pct = (curr - prior) / prior * 100
    direction = ("down" if pct > 0 else "up") if invert else ("up" if pct > 0 else "down")
    return f"{abs(pct):.0f}%", direction, prior


# ---------------------------------------------------------------------------
# Callbacks
# ---------------------------------------------------------------------------
@callback(
    Output(f"{PAGE_ID}-kpi-coverage", "children"),
    Output(f"{PAGE_ID}-kpi-afterhours", "children"),
    Output(f"{PAGE_ID}-kpi-crosscoverage", "children"),
    Output(f"{PAGE_ID}-kpi-vacation", "children"),
    Output(f"{PAGE_ID}-kpi-weekend", "children"),
    Output(f"{PAGE_ID}-store-manpower", "data"),
    Output(f"{PAGE_ID}-store-kpi-sparklines", "data"),
    Output(f"{PAGE_ID}-chart-sites", "figure"),
    Output(f"{PAGE_ID}-chart-afterhours", "figure"),
    Output(f"{PAGE_ID}-chart-crosscoverage", "figure"),
    Output(f"{PAGE_ID}-chart-calendar", "figure"),
    Output(f"{PAGE_ID}-detail-grid", "rowData"),
    Output(f"{PAGE_ID}-detail-grid", "columnDefs"),
    Output(f"{PAGE_ID}-manpower-loading", "visible"),
    Output(f"{PAGE_ID}-sites-loading", "visible"),
    Output(f"{PAGE_ID}-afterhours-loading", "visible"),
    Output(f"{PAGE_ID}-crosscov-loading", "visible"),
    Output(f"{PAGE_ID}-calendar-loading", "visible"),
    Input(f"{PAGE_ID}-interval", "n_intervals"),
    Input(f"{PAGE_ID}-filter-daterange", "start_date"),
    Input(f"{PAGE_ID}-filter-daterange", "end_date"),
    Input(f"{PAGE_ID}-date-slider", "value"),
    Input(f"{PAGE_ID}-manpower-agg", "value"),
    Input(f"{PAGE_ID}-sites-mode", "value"),
    Input(f"{PAGE_ID}-ah-toggles", "value"),
    Input(f"{PAGE_ID}-ah-hours", "value"),
    Input(f"{PAGE_ID}-ah-hours-active", "checked"),
    Input(f"{PAGE_ID}-sites-settings-stack", "value"),
    Input(f"{PAGE_ID}-ah-mode", "value"),
    Input(f"{PAGE_ID}-cc-mode", "value"),
)
def update_physicians(_n, range_start, range_end, slider_val, manpower_agg, sites_mode,
                      ah_toggles, ah_hours, ah_hours_active, sites_stack, ah_mode, cc_mode):
    from data.loader import load_physician_schedule, load_tasks

    # Initialize empty outputs
    empty = empty_figure("Data unavailable")
    na_kpi = kpi_card("—", "N/A")
    loading_off = False

    try:
        schedule = load_physician_schedule()
    except Exception:
        return (na_kpi,) * 5 + (None, None) + (empty,) * 4 + ([], []) + (loading_off,) * 5

    try:
        tasks = load_tasks()
    except Exception:
        tasks = pd.DataFrame()

    # Date range from slider/datepicker
    start, end = _get_date_range(slider_val, [range_start, range_end])

    # Compute prior period of equal length for trend comparison
    period_days = (end - start).days
    if period_days > 0:
        prior_end = start - pd.Timedelta(days=1)
        prior_start = prior_end - pd.Timedelta(days=period_days)
    else:
        prior_end = prior_start = None

    # Ensure Date column is datetime
    if "Date" in schedule.columns:
        schedule["Date"] = pd.to_datetime(schedule["Date"], errors="coerce")

    # Filter schedule — current period
    df = schedule.copy()
    if "Date" in df.columns:
        df = df[df["Date"].between(start, end)]

    # Filter schedule — prior period
    df_prior = schedule.copy()
    if prior_start is not None and "Date" in df_prior.columns:
        df_prior = df_prior[df_prior["Date"].between(prior_start, prior_end)]
    else:
        df_prior = pd.DataFrame()

    # Filter tasks — current period
    task_df = tasks.copy()
    if not task_df.empty and "CompletedDateTime" in task_df.columns:
        task_df["CompletedDateTime"] = pd.to_datetime(task_df["CompletedDateTime"], errors="coerce")
        task_df = task_df[task_df["CompletedDateTime"].between(start, end)]

    # Filter tasks — prior period
    task_prior = tasks.copy()
    if prior_start is not None and not task_prior.empty and "CompletedDateTime" in task_prior.columns:
        task_prior["CompletedDateTime"] = pd.to_datetime(task_prior["CompletedDateTime"], errors="coerce")
        task_prior = task_prior[task_prior["CompletedDateTime"].between(prior_start, prior_end)]
    else:
        task_prior = pd.DataFrame()

    # --- KPIs (with trends) ---
    kpi_cov, spark_cov = _kpi_coverage(df, df_prior)
    # Slider is 0-48 (each tick = 30 min); convert to fractional hours
    ah_start_tick = ah_hours[0] if ah_hours else 14
    ah_end_tick = ah_hours[1] if ah_hours else 36
    ah_opts = {
        "toggles": ah_toggles or [],
        "biz_start": ah_start_tick * 0.5,
        "biz_end": ah_end_tick * 0.5,
        "hours_active": ah_hours_active if ah_hours_active is not None else True,
    }
    kpi_ah, spark_ah = _kpi_afterhours(task_df, task_prior, df, ah_opts)
    kpi_cc, spark_cc = _kpi_crosscoverage(task_df, task_prior)
    kpi_vac, spark_vac = _kpi_vacation_days(df, df_prior)
    kpi_wknd, spark_wknd = _kpi_weekend_calls(df, df_prior)

    sparkline_data = {}
    if spark_cov:
        sparkline_data["coverage"] = spark_cov
    if spark_ah:
        sparkline_data["afterhours"] = spark_ah
    if spark_cc:
        sparkline_data["crosscov"] = spark_cc
    if spark_vac:
        sparkline_data["vacation"] = spark_vac
    if spark_wknd:
        sparkline_data["weekend"] = spark_wknd

    # --- Charts ---
    manpower_data = _build_manpower_data(df, manpower_agg or "D")
    barmode = "stack" if sites_stack == "stacked" else "group"
    fig_sites = _build_site_assignments(df, sites_mode or "count", barmode=barmode)
    fig_afterhours = _build_afterhours_chart(task_df, df, ah_opts, mode=ah_mode or "count")
    fig_crosscov = _build_crosscoverage_chart(task_df, mode=cc_mode or "count")
    fig_calendar = _build_calendar_heatmap(df)

    # --- Table ---
    table_rows, table_cols = _build_schedule_table(df)

    return (
        kpi_cov, kpi_ah, kpi_cc, kpi_vac, kpi_wknd,
        manpower_data, sparkline_data or None,
        fig_sites, fig_afterhours, fig_crosscov, fig_calendar,
        table_rows, table_cols,
        False, False, False, False, False,
    )


# ---------------------------------------------------------------------------
# KPI helpers (with trend comparison)
# ---------------------------------------------------------------------------
def _kpi_coverage(df, df_prior):
    """Average MDs on duty per day."""
    if df.empty or "Date" not in df.columns or "Status" not in df.columns:
        return kpi_card("Avg Daily Coverage", "N/A")
    on_duty = df[df["Status"].str.upper().isin(_ON_DUTY)]
    if on_duty.empty or "Physician" not in on_duty.columns:
        return kpi_card("Avg Daily Coverage", "0")
    # Count unique physicians per day, excluding holidays
    from utils.holidays import get_holidays
    holidays = get_holidays()
    on_duty_wkday = on_duty[
        (on_duty["Date"].dt.dayofweek < 5) & (~on_duty["Date"].dt.normalize().isin(holidays))
    ]
    if on_duty_wkday.empty:
        return kpi_card("Avg Daily Coverage", "0")
    daily_counts = on_duty_wkday.groupby("Date")["Physician"].nunique()
    avg = daily_counts.mean()

    # Prior period trend
    trend_text, trend_dir = None, None
    if not df_prior.empty and "Status" in df_prior.columns and "Physician" in df_prior.columns:
        prior_on = df_prior[df_prior["Status"].str.upper().isin(_ON_DUTY)]
        prior_on = prior_on[
            (prior_on["Date"].dt.dayofweek < 5) & (~prior_on["Date"].dt.normalize().isin(holidays))
        ]
        if not prior_on.empty:
            prior_avg = prior_on.groupby("Date")["Physician"].nunique().mean()
            trend_text, trend_dir, _ = _trend(avg, prior_avg)
            if trend_text:
                trend_text = f"{trend_text} vs prior ({prior_avg:.1f})"

    # Sparkline — weekly avg on-duty count
    spark_data = None
    daily = daily_counts
    if len(daily) > 7:
        weekly = daily.resample("W").mean().dropna()
        if len(weekly) > 1:
            spark_data = {
                "labels": [d.isoformat() for d in weekly.index],
                "values": [round(v, 1) for v in weekly.tolist()],
                "color": PRIMARY,
            }

    return kpi_card(
        "Avg Daily Coverage", f"{avg:.1f} MDs",
        trend_text=trend_text, trend_direction=trend_dir,
        accent_color=PRIMARY,
        sparkline_id=f"{PAGE_ID}-spark-coverage",
    ), spark_data


def _filter_afterhours(task_df, schedule_df, opts):
    """Return subset of completed tasks that qualify as 'after-hours'.

    opts keys:
        toggles: list of "weekends", "holidays", "off", "vacation"
        biz_start: int hour (e.g. 7)  — business hours start
        biz_end: int hour (e.g. 18)   — business hours end
    Tasks outside biz_start..biz_end are always after-hours.
    Toggle flags add additional criteria.
    """
    if task_df.empty or "CompletedDateTime" not in task_df.columns:
        return pd.DataFrame()
    completed = task_df[task_df["CompletedDateTime"].notna()].copy()
    if completed.empty:
        return completed

    toggles = opts.get("toggles", [])
    biz_start = opts.get("biz_start", 7)
    biz_end = opts.get("biz_end", 18)

    completed["_time_frac"] = completed["CompletedDateTime"].dt.hour + completed["CompletedDateTime"].dt.minute / 60
    completed["_date"] = completed["CompletedDateTime"].dt.normalize()
    completed["_dow"] = completed["CompletedDateTime"].dt.dayofweek

    # Build a "non-working day" mask first — any task on these days
    # counts regardless of time-of-day
    non_working = pd.Series(False, index=completed.index)

    # Weekend toggle
    if "weekends" in toggles:
        non_working = non_working | (completed["_dow"] >= 5)

    # Holiday toggle
    if "holidays" in toggles:
        from utils.holidays import get_holidays
        holidays = get_holidays()
        non_working = non_working | (completed["_date"].isin(holidays))

    # Schedule-based toggles (off / vacation)
    # A physician has multiple rows per day (one per dept). They're only truly
    # off/vacation if their BEST status for the day is off/vacation — i.e., they
    # don't also have a working status like LACEY/CENTRALIA/ABERDEEN/ON CALL.
    if ("off" in toggles or "vacation" in toggles) and not schedule_df.empty:
        sched = schedule_df.copy()
        sched["_sup"] = sched["Status"].str.upper()
        # Find each physician's best status per day
        _SCHED_PRIORITY = {
            "LACEY": 6, "CENTRALIA": 5, "ABERDEEN": 5,
            "ON CALL": 4, "ON": 4, "WEEKEND CALL": 3,
            "VACATION": 2, "SICK": 2, "SICK LEAVE": 2,
            "OFF": 1,
        }
        sched["_pri"] = sched["_sup"].map(_SCHED_PRIORITY).fillna(0)
        best_status = sched.sort_values("_pri", ascending=False).drop_duplicates(
            subset=["Date", "Physician"], keep="first"
        )
        # Only flag days where the best status is off/vacation
        target_statuses = set()
        if "off" in toggles:
            target_statuses.add("OFF")
        if "vacation" in toggles:
            target_statuses |= {"VACATION", "SICK", "SICK LEAVE"}
        truly_off = best_status[best_status["_sup"].isin(target_statuses)]
        if not truly_off.empty and "CompletingMD" in completed.columns:
            off_df = truly_off[["Date", "Physician"]].copy()
            off_df["Date"] = off_df["Date"].dt.normalize()
            off_df["_is_off"] = True
            merged = completed.merge(
                off_df, left_on=["_date", "CompletingMD"],
                right_on=["Date", "Physician"], how="left",
            )
            non_working = non_working | merged["_is_off"].fillna(False).values

    # Time-based: outside business hours, but only on normal working days
    hours_active = opts.get("hours_active", True)
    if hours_active:
        outside_hours = (completed["_time_frac"] < biz_start) | (completed["_time_frac"] >= biz_end)
        # Final: non-working day (all tasks count) OR working day outside business hours
        mask = non_working | (~non_working & outside_hours)
    else:
        # Hours filter disabled — only day-type toggles matter
        mask = non_working

    return completed[mask]


def _kpi_afterhours(task_df, task_prior, schedule_df, opts):
    """Tasks completed after hours with configurable criteria."""
    if task_df.empty or "CompletedDateTime" not in task_df.columns:
        return kpi_card("After-Hours Tasks", "N/A"), None

    ah = _filter_afterhours(task_df, schedule_df, opts)
    curr = len(ah)

    trend_text, trend_dir = None, None
    prior_ah = _filter_afterhours(task_prior, schedule_df, opts)
    prior = len(prior_ah)
    if prior > 0:
        trend_text, trend_dir, _ = _trend(curr, prior, invert=True)
        if trend_text:
            trend_text = f"{trend_text} vs prior ({prior:,})"

    spark_data = None
    if not ah.empty and len(ah) > 7:
        weekly = ah.set_index("CompletedDateTime").resample("W").size()
        if len(weekly) > 1:
            spark_data = {
                "labels": [d.isoformat() for d in weekly.index],
                "values": weekly.tolist(),
                "color": SEMANTIC_COLORS["warning"],
            }

    return kpi_card(
        "After-Hours Tasks", f"{curr:,}",
        trend_text=trend_text, trend_direction=trend_dir,
        accent_color=SEMANTIC_COLORS["warning"],
        sparkline_id=f"{PAGE_ID}-spark-afterhours",
    ), spark_data


def _count_crosscoverage(task_df):
    """Count cross-coverage tasks."""
    if task_df.empty or "CompletingMD" not in task_df.columns or "TreatingPhysician" not in task_df.columns:
        return 0, 0
    completed = task_df[task_df["CompletedDateTime"].notna()].copy()
    cross = completed[completed["CompletingMD"] != completed["TreatingPhysician"]]
    return len(cross), len(completed)


def _kpi_crosscoverage(task_df, task_prior):
    """Tasks where CompletingMD != TreatingPhysician."""
    if task_df.empty or "CompletingMD" not in task_df.columns or "TreatingPhysician" not in task_df.columns:
        return kpi_card("Cross-Coverage Tasks", "N/A"), None
    cross_count, total_count = _count_crosscoverage(task_df)
    pct = (cross_count / total_count * 100) if total_count > 0 else 0

    trend_text, trend_dir = None, None
    prior_cross, _ = _count_crosscoverage(task_prior)
    if prior_cross > 0:
        trend_text, trend_dir, _ = _trend(cross_count, prior_cross, invert=True)
        if trend_text:
            trend_text = f"{trend_text} vs prior ({prior_cross:,})"

    spark_data = None
    if not task_df.empty and "CompletedDateTime" in task_df.columns:
        completed = task_df[task_df["CompletedDateTime"].notna()].copy()
        cross = completed[completed["CompletingMD"] != completed["TreatingPhysician"]]
        if not cross.empty and len(cross) > 7:
            weekly = cross.set_index("CompletedDateTime").resample("W").size()
            if len(weekly) > 1:
                spark_data = {
                    "labels": [d.isoformat() for d in weekly.index],
                    "values": weekly.tolist(),
                    "color": CHART_COLORWAY[1],
                }

    return kpi_card(
        "Cross-Coverage", f"{cross_count:,}",
        value_detail=f"({pct:.1f}%)",
        trend_text=trend_text, trend_direction=trend_dir,
        accent_color=CHART_COLORWAY[1],
        sparkline_id=f"{PAGE_ID}-spark-crosscov",
    ), spark_data


def _kpi_vacation_days(df, df_prior):
    """Total vacation/sick physician-days in period."""
    if df.empty or "Status" not in df.columns or "Physician" not in df.columns:
        return kpi_card("Off/Vacation Days", "N/A"), None
    vac = df[df["Status"].str.upper().isin(_OFF_STATUSES)]
    vac_days = vac.drop_duplicates(subset=["Date", "Physician"])
    curr = len(vac_days)

    trend_text, trend_dir = None, None
    if not df_prior.empty and "Status" in df_prior.columns and "Physician" in df_prior.columns:
        prior_vac = df_prior[df_prior["Status"].str.upper().isin(_OFF_STATUSES)]
        prior_count = len(prior_vac.drop_duplicates(subset=["Date", "Physician"]))
        if prior_count > 0:
            trend_text, trend_dir, _ = _trend(curr, prior_count)
            if trend_text:
                trend_text = f"{trend_text} vs prior ({prior_count:,})"

    spark_data = None
    if not vac_days.empty and "Date" in vac_days.columns and len(vac_days) > 7:
        weekly = vac_days.groupby("Date").size().resample("W").sum()
        if len(weekly) > 1:
            spark_data = {
                "labels": [d.isoformat() for d in weekly.index],
                "values": weekly.tolist(),
                "color": NEUTRAL["text_muted"],
            }

    return kpi_card(
        "Off/Vacation Days", f"{curr:,}",
        trend_text=trend_text, trend_direction=trend_dir,
        accent_color=NEUTRAL["text_muted"],
        sparkline_id=f"{PAGE_ID}-spark-vacation",
    ), spark_data


def _kpi_weekend_calls(df, df_prior):
    """Weekend call shifts (unique physician-days)."""
    if df.empty or "Status" not in df.columns or "Physician" not in df.columns:
        return kpi_card("Weekend Calls", "N/A"), None
    wknd = df[df["Status"].str.upper() == "WEEKEND CALL"]
    wknd_days = wknd.drop_duplicates(subset=["Date", "Physician"])
    curr = len(wknd_days)

    trend_text, trend_dir = None, None
    if not df_prior.empty and "Status" in df_prior.columns and "Physician" in df_prior.columns:
        prior_wknd = df_prior[df_prior["Status"].str.upper() == "WEEKEND CALL"]
        prior_count = len(prior_wknd.drop_duplicates(subset=["Date", "Physician"]))
        if prior_count > 0:
            trend_text, trend_dir, _ = _trend(curr, prior_count)
            if trend_text:
                trend_text = f"{trend_text} vs prior ({prior_count:,})"

    spark_data = None
    if not wknd_days.empty and "Date" in wknd_days.columns and len(wknd_days) > 4:
        weekly = wknd_days.groupby("Date").size().resample("W").sum()
        if len(weekly) > 1:
            spark_data = {
                "labels": [d.isoformat() for d in weekly.index],
                "values": weekly.tolist(),
                "color": CHART_COLORWAY[3],
            }

    return kpi_card(
        "Weekend Calls", f"{curr:,}",
        trend_text=trend_text, trend_direction=trend_dir,
        accent_color=CHART_COLORWAY[3],
        sparkline_id=f"{PAGE_ID}-spark-weekend",
    ), spark_data


# ---------------------------------------------------------------------------
# Chart builders
# ---------------------------------------------------------------------------
def _build_manpower_data(df, agg="D"):
    """Build raw manpower data dict for clientside smoothing.

    agg: "D" = daily (avg MDs/day), "W"/"M"/"Y" = total man-days per period.
    """
    if df.empty or "Date" not in df.columns or "Status" not in df.columns:
        return None

    on_duty = df[df["Status"].str.upper().isin(_ON_DUTY)].copy()
    if on_duty.empty or "Physician" not in on_duty.columns:
        return None

    # Count unique physicians per day (each MD has multiple rows per day)
    daily = on_duty.groupby("Date")["Physician"].nunique().reset_index(name="count")
    # Keep only non-holiday weekdays
    from utils.holidays import get_holidays
    holidays = get_holidays()
    daily = daily[
        (daily["Date"].dt.dayofweek < 5) & (~daily["Date"].dt.normalize().isin(holidays))
    ]
    if daily.empty:
        return None

    daily = daily.set_index("Date").sort_index()

    if agg == "D":
        dates = [d.isoformat() for d in daily.index]
        values = daily["count"].tolist()
        y_title = "MDs On Duty"
    else:
        # W/M/Y: sum man-days per period
        # Use period-start codes so JS detectAggLevel sees day=1 for M/Y
        resample_code = {"W": "W", "M": "MS", "Y": "YS"}.get(agg, agg)
        grouped = daily["count"].resample(resample_code).sum()
        grouped = grouped[grouped > 0]
        if grouped.empty:
            return None
        dates = [d.isoformat() for d in grouped.index]
        values = grouped.tolist()
        y_title = "Man-Days"

    return {
        "dates": dates,
        "series": [{
            "name": y_title,
            "values": values,
            "color": PRIMARY,
        }],
        "yTitle": y_title,
        "hideLegend": True,
    }


def _build_site_assignments(df, mode="count", barmode="group"):
    """Bar chart of site assignment days per physician.

    Site is derived from Status (LACEY/CENTRALIA/ABERDEEN/ON CALL).
    ON CALL historically = Lacey assignment.
    mode: "count" = raw days, "pct" = percentage of each physician's total.
    barmode: "group" or "stack".
    """
    if df.empty or "Status" not in df.columns or "Physician" not in df.columns:
        return empty_figure("No assignment data")

    df = df[~df["Physician"].str.endswith(" MD, ", na=False)]
    if df.empty:
        return empty_figure("No assignment data")

    _SITE_MAP = {"LACEY": "Lacey", "ON CALL": "Lacey", "CENTRALIA": "Centralia", "ABERDEEN": "Aberdeen"}
    assigned = df[df["Status"].str.upper().isin(_SITE_MAP)].copy()
    if assigned.empty:
        return empty_figure("No site assignment data")

    assigned["Site"] = assigned["Status"].str.upper().map(_SITE_MAP)
    # Count unique physician-days per site
    site_days = assigned.drop_duplicates(subset=["Date", "Physician", "Site"])
    counts = site_days.groupby(["Physician", "Site"]).size().reset_index(name="count")
    counts["short_name"] = counts["Physician"].str.split(",").str[0]

    if mode == "pct":
        totals = counts.groupby("Physician")["count"].transform("sum")
        counts["value"] = (counts["count"] / totals * 100).round(1)
        y_title = "% of Assignment Days"
        hover_fmt = ".1f"
    else:
        counts["value"] = counts["count"]
        y_title = "Assignment Days"
        hover_fmt = "d"

    fig = go.Figure()
    for site in ["Lacey", "Centralia", "Aberdeen"]:
        site_data = counts[counts["Site"] == site]
        if site_data.empty:
            continue
        fig.add_trace(go.Bar(
            x=site_data["short_name"],
            y=site_data["value"],
            name=site,
            marker_color=DEPARTMENT_COLORS.get(site, PRIMARY),
            hovertemplate=f"%{{x}}: %{{y:{hover_fmt}}}{'%' if mode == 'pct' else ' days'}<extra>{site}</extra>",
        ))

    apply_default_layout(fig, autosize=True)
    fig.update_layout(
        yaxis_title=y_title,
        barmode=barmode,
        margin=dict(l=48, r=16, t=4, b=20),
    )
    return fig


def _build_afterhours_chart(task_df, schedule_df, opts, mode="count"):
    """Bar chart of after-hours tasks by physician."""
    if task_df.empty or "CompletedDateTime" not in task_df.columns or "CompletingMD" not in task_df.columns:
        return empty_figure("No task data")

    ah = _filter_afterhours(task_df, schedule_df, opts)
    if ah.empty:
        return empty_figure("No after-hours tasks")

    ah_by_md = ah.groupby("CompletingMD").size().reset_index(name="count")

    if mode == "pct":
        # Percentage of each MD's total completed tasks that are after-hours
        completed = task_df[task_df["CompletedDateTime"].notna()]
        total_by_md = completed.groupby("CompletingMD").size()
        ah_by_md["value"] = ah_by_md.apply(
            lambda r: round(r["count"] / total_by_md.get(r["CompletingMD"], 1) * 100, 1), axis=1
        )
        x_title = "% of MD's Tasks After-Hours"
        hover_suffix = "%"
    else:
        ah_by_md["value"] = ah_by_md["count"]
        x_title = "After-Hours Tasks"
        hover_suffix = ""

    ah_by_md = ah_by_md.sort_values("value", ascending=True)
    ah_by_md["short_name"] = ah_by_md["CompletingMD"].str.split(",").str[0]

    fig = go.Figure(go.Bar(
        x=ah_by_md["value"],
        y=ah_by_md["short_name"],
        orientation="h",
        marker_color=SEMANTIC_COLORS["warning"],
        hovertemplate="%{y}: %{x}" + hover_suffix + "<extra></extra>",
    ))

    apply_default_layout(fig, autosize=True)
    fig.update_layout(xaxis_title=x_title, margin=dict(l=100, r=16, t=4, b=28))
    return fig


def _build_crosscoverage_chart(task_df, mode="count"):
    """Bar chart showing cross-coverage by physician."""
    if task_df.empty or "CompletingMD" not in task_df.columns or "TreatingPhysician" not in task_df.columns:
        return empty_figure("No task data")

    completed = task_df[task_df["CompletedDateTime"].notna()].copy()
    cross = completed[completed["CompletingMD"] != completed["TreatingPhysician"]]

    if cross.empty:
        return empty_figure("No cross-coverage tasks")

    cc_by_md = cross.groupby("CompletingMD").size().reset_index(name="count")

    if mode == "pct":
        # Percentage of each MD's total completed tasks that are cross-coverage
        total_by_md = completed.groupby("CompletingMD").size()
        cc_by_md["value"] = cc_by_md.apply(
            lambda r: round(r["count"] / total_by_md.get(r["CompletingMD"], 1) * 100, 1), axis=1
        )
        x_title = "% of MD's Tasks Cross-Coverage"
        hover_suffix = "%"
    else:
        cc_by_md["value"] = cc_by_md["count"]
        x_title = "Cross-Coverage Tasks"
        hover_suffix = ""

    cc_by_md = cc_by_md.sort_values("value", ascending=True)
    cc_by_md["short_name"] = cc_by_md["CompletingMD"].str.split(",").str[0]

    fig = go.Figure(go.Bar(
        x=cc_by_md["value"],
        y=cc_by_md["short_name"],
        orientation="h",
        marker_color=CHART_COLORWAY[1],
        hovertemplate="%{y}: %{x}" + hover_suffix + "<extra></extra>",
    ))

    apply_default_layout(fig, autosize=True)
    fig.update_layout(xaxis_title=x_title, margin=dict(l=100, r=16, t=4, b=28))
    return fig


def _build_calendar_heatmap(df):
    """Calendar heatmap showing physician schedules."""
    if df.empty or "Date" not in df.columns or "Physician" not in df.columns:
        return empty_figure("No schedule data")

    # Each physician has multiple rows per day — pick the most informative status.
    # Priority: site assignment > weekend call > off > vacation/sick
    _STATUS_PRIORITY = {
        "LACEY": 6, "CENTRALIA": 5, "ABERDEEN": 5,
        "ON CALL": 4, "ON": 4,
        "WEEKEND CALL": 3,
        "VACATION": 2, "SICK": 2, "SICK LEAVE": 2,
        "OFF": 1,
    }
    temp = df.copy()
    # Exclude weekend call rows and placeholder site-MD entries
    temp = temp[temp["Status"].str.upper() != "WEEKEND CALL"]
    temp = temp[~temp["Physician"].str.endswith(" MD, ", na=False)]
    if temp.empty:
        return empty_figure("No schedule data")
    temp["_priority"] = temp["Status"].str.upper().map(_STATUS_PRIORITY).fillna(2)
    # Keep one row per physician-day: the highest-priority status
    best = temp.sort_values("_priority", ascending=False).drop_duplicates(
        subset=["Date", "Physician"], keep="first"
    )

    # Exclude physicians who only have OFF (or no working status at all)
    _WORKING = {"LACEY", "CENTRALIA", "ABERDEEN", "ON CALL", "ON", "VACATION", "SICK", "SICK LEAVE"}
    active_mds = best[best["Status"].str.upper().isin(_WORKING)]["Physician"].unique()
    best = best[best["Physician"].isin(active_mds)]
    if best.empty:
        return empty_figure("No active physician data")

    pivot = best.pivot_table(
        index="Physician",
        columns="Date",
        values="Status",
        aggfunc="first",
    )

    if pivot.empty:
        return empty_figure("No schedule data")

    # Map status to numeric for heatmap
    # Off days = yellow (0.5), vacation/sick = red (0), on duty = green (1)
    status_map = {
        "ON": 3, "ON CALL": 3, "LACEY": 3, "CENTRALIA": 3, "ABERDEEN": 3,
        "OFF": 1,
        "VACATION": -1, "SICK": -1, "SICK LEAVE": -1,
    }

    # Determine each physician's active range (first/last day with non-OFF status)
    working_rows = best[best["Status"].str.upper().isin(
        {"LACEY", "CENTRALIA", "ABERDEEN", "ON CALL", "ON", "VACATION", "SICK", "SICK LEAVE"}
    )]
    active_ranges = working_rows.groupby("Physician")["Date"].agg(["min", "max"])

    # Build masks for active range and status mapping (vectorized)
    dates = pivot.columns

    # Vectorized: map all statuses to z values and hover text
    upper_pivot = pivot.map(lambda x: str(x).upper() if pd.notna(x) else None)
    z_data = upper_pivot.map(lambda x: status_map.get(x, 1) if x is not None else None)
    hover_data = pivot.map(lambda x: str(x) if pd.notna(x) else "Off")

    # Mask out dates outside each physician's active range
    for physician in pivot.index:
        if physician in active_ranges.index:
            first_day = active_ranges.loc[physician, "min"]
            last_day = active_ranges.loc[physician, "max"]
            outside = (dates < first_day) | (dates > last_day)
        else:
            outside = pd.Series(True, index=dates)
        z_data.loc[physician, outside] = None
        hover_data.loc[physician, outside] = ""
        # Fill gaps within range as Off
        in_range_nan = ~outside & z_data.loc[physician].isna()
        z_data.loc[physician, in_range_nan] = 1.0
        hover_data.loc[physician, in_range_nan] = "Off"

    # Build pre-formatted hovertext so Plotly doesn't need customdata alignment
    y_labels = [p.split(",")[0] for p in z_data.index]
    hovertext = []
    for i, physician in enumerate(z_data.index):
        row = []
        for j, col in enumerate(dates):
            status = hover_data.iloc[i, j]
            if status == "":
                row.append("")
            else:
                row.append(f"Date: {col.strftime('%b %d, %Y')}<br>Physician: {y_labels[i]}<br>Status: {status}")
        hovertext.append(row)

    fig = go.Figure(go.Heatmap(
        z=z_data.values.astype(float),
        x=z_data.columns,
        y=y_labels,
        hovertext=hovertext,
        hoverinfo="text",
        colorscale=[
            [0, "#EF4444"],      # Vacation/Sick (-1)
            [0.5, "#FCD34D"],    # Off (1)
            [1, "#10B981"],      # On duty (3)
        ],
        showscale=False,
        zmin=-1, zmax=3,
    ))

    # Scale height to number of physicians
    n_physicians = len(pivot.index)
    chart_h = max(180, n_physicians * 50)
    apply_default_layout(fig, height=chart_h)
    fig.update_layout(
        margin=dict(l=100, r=16, t=4, b=20),
        xaxis=dict(tickformat="%b %d"),
    )
    return fig


def _build_schedule_table(df):
    """Build rowData and columnDefs for the schedule detail grid."""
    if df.empty:
        return [], []

    # Deduplicate: pick highest-priority status per physician-day
    _STATUS_PRIORITY = {
        "LACEY": 6, "CENTRALIA": 5, "ABERDEEN": 5,
        "ON CALL": 4, "ON": 4, "WEEKEND CALL": 3,
        "OFF": 1, "VACATION": 0, "SICK": 0, "SICK LEAVE": 0,
    }
    from utils.holidays import get_holidays
    holidays = get_holidays()

    working = df.copy()

    # Build a date-level holiday name lookup from OFF rows BEFORE dedup.
    # Uses date-level (not physician-level) so every physician on a holiday
    # gets the name even if their winning row is WEEKEND CALL, not OFF.
    is_hol_date = working["Date"].dt.normalize().isin(holidays)
    is_off = working["Status"].str.upper() == "OFF"
    has_note = working["ActivityNote"].notna() & (working["ActivityNote"] != "")
    cleaned_note = working["ActivityNote"].str.replace(r"^CLOSED\s*-?\s*", "", regex=True).str.strip()
    working["_hol_note"] = cleaned_note.where(is_hol_date & is_off & has_note, "")
    # Most common cleaned note per date
    hol_notes = working.loc[working["_hol_note"] != "", ["Date", "_hol_note"]]
    if not hol_notes.empty:
        holiday_lookup = (
            hol_notes.groupby(hol_notes["Date"].dt.normalize())["_hol_note"]
            .agg(lambda s: s.value_counts().index[0])
            .rename("_holiday_name")
        )
    else:
        holiday_lookup = pd.Series(dtype=str, name="_holiday_name")

    # Deduplicate: pick highest-priority status per physician-day
    working["_priority"] = working["Status"].str.upper().map(_STATUS_PRIORITY).fillna(2)
    working = working.sort_values(["Date", "Physician", "_priority"], ascending=[False, True, False])
    deduped = working.drop_duplicates(subset=["Date", "Physician"], keep="first")
    deduped = deduped.drop(columns=["_priority", "_hol_note"])

    # Map holiday name by date, normalize to title case
    deduped["Holiday"] = (
        deduped["Date"].dt.normalize().map(holiday_lookup).fillna("").str.title()
    )

    # Derive day-of-week and weekend flag
    deduped["DayOfWeek"] = deduped["Date"].dt.strftime("%a")
    deduped["Weekend"] = deduped["Date"].dt.dayofweek.ge(5).map({True: "Yes", False: ""})

    column_defs = [
        {"field": "Date", "headerName": "Date", "width": 120, "suppressSizeToFit": True, "sort": "desc"},
        {"field": "DayOfWeek", "headerName": "Day", "width": 75, "suppressSizeToFit": True},
        {"field": "Physician", "headerName": "Physician", "width": 160},
        {"field": "Status", "headerName": "Status", "width": 140},
        {"field": "Department", "headerName": "Department", "width": 120},
        {"field": "Weekend", "headerName": "Weekend", "width": 100},
        {"field": "Holiday", "headerName": "Holiday", "width": 220},
        {"field": "ActivityNote", "headerName": "Comment", "width": 200},
    ]
    # Only include columns that exist
    available = set(deduped.columns)
    column_defs = [cd for cd in column_defs if cd["field"] in available]

    if "Date" in deduped.columns:
        deduped["Date"] = deduped["Date"].dt.strftime("%Y-%m-%d")

    table_df = sanitize_for_grid(deduped)
    return table_df.to_dict("records"), column_defs


# ---------------------------------------------------------------------------
# Clientside callback — manpower chart smoothing / chart type
# ---------------------------------------------------------------------------
clientside_callback(
    ClientsideFunction(namespace="census", function_name="smoothChartWithType"),
    Output(f"{PAGE_ID}-chart-manpower", "figure"),
    Input(f"{PAGE_ID}-store-manpower", "data"),
    Input(f"{PAGE_ID}-manpower-settings-smooth", "value"),
    Input(f"{PAGE_ID}-manpower-settings-type", "value"),
    State(f"{PAGE_ID}-chart-manpower", "figure"),
)


# ---------------------------------------------------------------------------
# Settings panel toggle
# ---------------------------------------------------------------------------
@callback(
    Output(f"{PAGE_ID}-manpower-settings-panel", "style"),
    Input(f"{PAGE_ID}-manpower-settings-btn", "n_clicks"),
    State(f"{PAGE_ID}-manpower-settings-panel", "style"),
    prevent_initial_call=True,
)
def toggle_manpower_settings(n, style):
    if not n:
        return style
    current = style or {}
    is_hidden = current.get("display") == "none"
    return {"display": "block"} if is_hidden else {"display": "none"}


# Sites / After-Hours / Cross-Coverage settings panel toggle + export
for _sid, _gid in [
    (f"{PAGE_ID}-sites", f"{PAGE_ID}-chart-sites"),
    (f"{PAGE_ID}-afterhours", f"{PAGE_ID}-chart-afterhours"),
    (f"{PAGE_ID}-crosscov", f"{PAGE_ID}-chart-crosscoverage"),
]:
    clientside_callback(
        ClientsideFunction("chartSettings", "toggle"),
        Output(f"{_sid}-settings-panel", "style"),
        Input(f"{_sid}-settings-btn", "n_clicks"),
        State(f"{_sid}-settings-panel", "style"),
        prevent_initial_call=True,
    )
    clientside_callback(
        ClientsideFunction("chartExport", "exportPng"),
        Output(f"{_sid}-settings-export", "n_clicks"),
        Input(f"{_sid}-settings-export", "n_clicks"),
        State(_gid, "id"),
        prevent_initial_call=True,
    )

# After-hours filter panel toggle
clientside_callback(
    ClientsideFunction("chartSettings", "toggle"),
    Output(f"{PAGE_ID}-ah-filter-panel", "style"),
    Input(f"{PAGE_ID}-ah-filter-btn", "n_clicks"),
    State(f"{PAGE_ID}-ah-filter-panel", "style"),
    prevent_initial_call=True,
)


# ---------------------------------------------------------------------------
# KPI Sparkline clientside callbacks
# ---------------------------------------------------------------------------
_SPARK_KEYS = ["coverage", "afterhours", "crosscov", "vacation", "weekend"]

for _key in _SPARK_KEYS:
    clientside_callback(
        """function(data, smoothPct, componentId) {
            return window.dash_clientside.sparklines.updateFromStore(data, componentId, smoothPct);
        }""",
        Output(f"{PAGE_ID}-spark-{_key}", "figure"),
        Input(f"{PAGE_ID}-store-kpi-sparklines", "data"),
        Input(f"{PAGE_ID}-filter-smoothing", "value"),
        State(f"{PAGE_ID}-spark-{_key}", "id"),
    )

# Table export CSV
clientside_callback(
    f"""function(n) {{
        if (!n) return window.dash_clientside.no_update;
        gridExportCsv('{PAGE_ID}-detail-grid', 'physician_schedule.csv');
        return window.dash_clientside.no_update;
    }}""",
    Output(f"{PAGE_ID}-table-export", "n_clicks"),
    Input(f"{PAGE_ID}-table-export", "n_clicks"),
    prevent_initial_call=True,
)

