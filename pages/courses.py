"""Courses page -- treatment course tracking: status, technique mix, duration, fraction tracking."""

import math
import dash
import dash_mantine_components as dmc
import dash_ag_grid as dag
from dash import callback, Input, Output, State, dcc, html, clientside_callback, ClientsideFunction
from dash_iconify import DashIconify
import plotly.graph_objects as go
import pandas as pd
import numpy as np
from datetime import timedelta

from config.settings import (
    DEPARTMENTS, DEPARTMENT_COLORS, CHART_COLORWAY, PRIMARY,
    DEFAULT_LAYOUT, FONT_FAMILY, SEMANTIC_COLORS, NEUTRAL,
    DEFAULT_COLUMN_DEFS, DEFAULT_GRID_OPTIONS, DEFAULT_GRID_STYLE, DEFAULT_GRID_CLASS, CHART_PAPER_HEIGHT,
    PRIOR_PERIOD_COLORS,
)
from components.filter_bar import department_chips
from components.kpi_card import kpi_card, kpi_placeholder
from components.chart_card import chart_card, register_chart_callbacks
from components.chart_settings import chart_settings_popover
from components.detail_table import detail_table
from components.phi import apply_phi_grid_rules
from utils.charts import apply_default_layout, empty_figure, dept_color
from utils.date_slider import (
    month_idx, idx_to_date, MAX_IDX, DEFAULT_SLIDER, SLIDER_MARKS,
    preset_to_slider_val, preset_to_exact_dates,
)
from components.diagnosis_filter import diagnosis_accordion, register_diagnosis_callbacks
from utils.diagnosis_categories import (
    assign_diagnosis_column,
    build_code_to_category,
    get_categories_for_codes,
    primary_category,
)

dash.register_page(__name__, path="/courses", name="Courses", order=9)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_DEFAULT_DATE_PRESET = "ytd"

STATUS_COLORS = {
    "ACTIVE": SEMANTIC_COLORS["info"],       # #3B82F6
    "COMPLETED": SEMANTIC_COLORS["success"],  # #10B981
}

# Date mode options — which date column to use for filtering
DATE_MODES = [
    {"value": "started", "label": "Started"},
    {"value": "treated", "label": "Treated"},
    {"value": "completed", "label": "Completed"},
]


# ---------------------------------------------------------------------------
# Filter Bar
# ---------------------------------------------------------------------------

def _build_courses_filter_bar():
    """Build the two-row filter bar for courses page."""
    return dmc.Paper(
        children=[
            # Row 1: dimension filters
            dmc.Group(
                children=[
                    department_chips("courses"),
                    # Physician dropdown
                    html.Div(
                        children=[
                            html.Div(
                                children=[
                                    dmc.Button(
                                        "Physician",
                                        id="courses-physician-trigger",
                                        variant="default",
                                        size="sm",
                                        rightSection=DashIconify(icon="mdi:chevron-down", width=14),
                                    ),
                                    dmc.ActionIcon(
                                        DashIconify(icon="mdi:close-circle", width=18),
                                        id="courses-physician-clear",
                                        variant="subtle",
                                        color="gray",
                                        size="sm",
                                        className="wf-filter-clear-btn",
                                    ),
                                ],
                                style={"position": "relative", "display": "inline-block"},
                            ),
                            dmc.Paper(
                                children=[
                                    dmc.SegmentedControl(
                                        id="courses-physician-role",
                                        data=[
                                            {"value": "treating", "label": "Treating"},
                                            {"value": "consult", "label": "Consult"},
                                        ],
                                        value="treating",
                                        size="xs",
                                        fullWidth=True,
                                        mb="xs",
                                    ),
                                    dmc.ChipGroup(
                                        children=[],
                                        id="courses-filter-physician",
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
                    diagnosis_accordion("courses"),
                    # Technique dropdown
                    html.Div(
                        children=[
                            html.Div(
                                children=[
                                    dmc.Button(
                                        "Technique",
                                        id="courses-technique-trigger",
                                        variant="default",
                                        size="sm",
                                        rightSection=DashIconify(icon="mdi:chevron-down", width=14),
                                    ),
                                    dmc.ActionIcon(
                                        DashIconify(icon="mdi:close-circle", width=18),
                                        id="courses-technique-clear",
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
                                    children=[],
                                    id="courses-filter-technique",
                                    multiple=True,
                                    value=[],
                                ),
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
                    # Status filter
                    dmc.SegmentedControl(
                        id="courses-filter-status",
                        data=[
                            {"value": "all", "label": "All"},
                            {"value": "ACTIVE", "label": "Active"},
                            {"value": "COMPLETED", "label": "Completed"},
                        ],
                        value="all",
                        size="xs",
                    ),
                    # Inpatient toggle
                    dmc.Switch(
                        id="courses-inpatient-switch",
                        label="Inpatient",
                        size="xs",
                        checked=False,
                    ),
                    # Fraction range slider
                    dmc.Group(
                        children=[
                            dmc.Text("Fractions", size="xs", c="#6B7280", fw=500,
                                     id="courses-fraction-label"),
                            dmc.RangeSlider(
                                id="courses-fraction-slider",
                                min=0,
                                max=50,
                                step=1,
                                value=[0, 50],
                                size="xs",
                                w=160,
                                color="violet",
                                minRange=0,
                                marks=[],
                            ),
                            dmc.ActionIcon(
                                DashIconify(icon="mdi:close-circle", width=16),
                                id="courses-fraction-clear",
                                variant="subtle",
                                color="gray",
                                size="xs",
                                style={"display": "none"},
                            ),
                        ],
                        gap=6,
                        align="center",
                    ),
                    dcc.Store(id="courses-fraction-engaged", data=False),
                    # Smoothing slider for KPI sparklines (rightmost)
                    dmc.Group(
                        children=[
                            dmc.Text("Smoothing", size="xs", c="#6B7280", fw=500),
                            dmc.Slider(
                                id="courses-smooth-slider",
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
                        id="courses-filter-date-preset",
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
                            id="courses-filter-daterange",
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
                    dmc.SegmentedControl(
                        id="courses-date-mode",
                        data=DATE_MODES,
                        value="treated",
                        size="xs",
                    ),
                    dmc.Box(
                        children=[
                            html.Div(id="courses-date-range-label", style={"display": "none"}),
                            dmc.RangeSlider(
                                id="courses-date-slider",
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
                dmc.Title("Courses", order=2, className="page-title",
                          style={"margin": 0, "textAlign": "center"}),
                html.Div(
                    style={"position": "relative"},
                    children=[
                        _build_courses_filter_bar(),
                        html.Div(
                            id="courses-grid-filter-badge",
                            children=dmc.Tooltip(
                                label="Table column filters are active — charts reflect the filtered subset",
                                position="left", withArrow=True, multiline=True, w=220,
                                children=dmc.Badge(
                                    "Table Filtered",
                                    color="red", variant="filled", size="md",
                                    leftSection=DashIconify(icon="mdi:filter", width=14),
                                ),
                            ),
                            style={
                                "position": "absolute", "top": -12, "right": 8,
                                "zIndex": 10, "display": "none", "cursor": "pointer",
                            },
                        ),
                    ],
                ),
            ],
        ),

        # KPI row — 6 cards
        dmc.Grid(gutter="md", children=[
            dmc.GridCol(kpi_placeholder(), id="courses-kpi-active", span={"base": 12, "sm": 6, "md": 2}),
            dmc.GridCol(kpi_placeholder(), id="courses-kpi-started", span={"base": 12, "sm": 6, "md": 2}),
            dmc.GridCol(kpi_placeholder(), id="courses-kpi-completed", span={"base": 12, "sm": 6, "md": 2}),
            dmc.GridCol(kpi_placeholder(), id="courses-kpi-median-fractions", span={"base": 12, "sm": 6, "md": 2}),
            dmc.GridCol(kpi_placeholder(), id="courses-kpi-median-duration", span={"base": 12, "sm": 6, "md": 2}),
            dmc.GridCol(kpi_placeholder(), id="courses-kpi-multiplan", span={"base": 12, "sm": 6, "md": 2}),
        ]),

        # Row 1: Course Volume Trend + Cumulative (half-width each)
        dmc.Grid(gutter="md", children=[
            dmc.GridCol(
                chart_card(
                    "courses-chart-volume",
                    "Course Volume Trend",
                    settings_id="courses-volume",
                    chart_types=[
                        {"value": "line", "label": "Line"},
                        {"value": "area", "label": "Area"},
                        {"value": "bar", "label": "Bar"},
                    ],
                    chart_type_default="bar",
                    show_smooth=True,
                    smooth_max=12,
                    smooth_default=0,
                    paper_padding="md",
                    extra_controls_left=[
                        dmc.SegmentedControl(
                            id="courses-volume-slice",
                            data=[
                                {"value": "", "label": "Total"},
                                {"value": "physician", "label": "MD"},
                                {"value": "site", "label": "Site"},
                                {"value": "diagnosis", "label": "Dx"},
                            ],
                            value="site",
                            size="xs",
                        ),
                    ],
                    extra_controls=[
                        dmc.SegmentedControl(
                            id="courses-volume-agg",
                            data=[
                                {"value": "W", "label": "Weekly"},
                                {"value": "M", "label": "Monthly"},
                                {"value": "Y", "label": "Yearly"},
                            ],
                            value="W",
                            size="xs",
                        ),
                    ],
                ),
                span={"base": 12, "md": 6},
            ),
            dmc.GridCol(
                chart_card(
                    "courses-chart-cumulative",
                    "Cumulative Course Volume",
                    settings_id="courses-cumulative",
                    chart_types=[
                        {"value": "line", "label": "Line"},
                        {"value": "area", "label": "Area"},
                        {"value": "bar", "label": "Bar"},
                    ],
                    show_smooth=True,
                    show_prior_periods=True,
                    show_project_toggle=True,
                    smooth_min=0,
                    smooth_max=1,
                    smooth_step=0.05,
                    smooth_default=0.1,
                    prior_periods_default=3,
                    paper_padding="md",
                    extra_controls=[
                        dmc.SegmentedControl(
                            id="courses-cumulative-mode",
                            data=[
                                {"value": "prior", "label": "Prior Periods"},
                                {"value": "slice", "label": "Slice By"},
                            ],
                            value="prior",
                            size="xs",
                        ),
                        dmc.SegmentedControl(
                            id="courses-cumulative-period-type",
                            data=[
                                {"value": "calendar", "label": "Calendar"},
                                {"value": "rolling", "label": "Rolling"},
                            ],
                            value="calendar",
                            size="xs",
                        ),
                        dmc.SegmentedControl(
                            id="courses-cumulative-slice",
                            data=[
                                {"value": "physician", "label": "MD"},
                                {"value": "site", "label": "Site"},
                                {"value": "diagnosis", "label": "Dx"},
                            ],
                            value="physician",
                            size="xs",
                            style={"display": "none"},
                        ),
                    ],
                ),
                span={"base": 12, "md": 6},
            ),
        ]),

        # Charts container (remaining charts)
        dmc.Stack(id="courses-charts", gap=16),

        # Detail table container
        detail_table(
            "courses-detail-grid",
            title="Course Details",
            export_id="courses-table-export",
            column_size="autoSize",
            extra_controls=[
                dmc.Button(
                    "Clear Filters",
                    id="courses-table-clear-filters",
                    size="compact-xs",
                    variant="light",
                    color="red",
                    leftSection=DashIconify(icon="mdi:filter-remove", width=14),
                    style={"display": "none"},
                ),
            ],
        ),

        # Stores for clientside rendering
        dcc.Store(id="courses-store-volume"),
        dcc.Store(id="courses-store-cumulative"),
        dcc.Store(id="courses-store-kpi-sparklines"),
        dcc.Store(id="courses-store-ridgeline"),
        dcc.Store(id="courses-store-frac-trend"),
        dcc.Store(id="courses-store-frac-dist"),
        dcc.Store(id="courses-store-complexity-trends"),
        dcc.Store(id="courses-store-technique-dist"),
        dcc.Store(id="courses-store-quit-trend"),
        dcc.Store(id="courses-store-interruption"),
        dcc.Store(id="courses-table-filter-rows"),  # filtered row indices from grid

        # Interval for periodic refresh
        dcc.Interval(id="courses-interval", interval=300_000, n_intervals=0, max_intervals=0),  # fires once on mount; no background refresh (daily data + global refresh button)
    ],
)


# ---------------------------------------------------------------------------
# Register chart settings callbacks
# ---------------------------------------------------------------------------
register_chart_callbacks([
    ("courses-volume", "courses-chart-volume"),
    {"sid": "courses-cumulative", "gid": "courses-chart-cumulative", "store_id": "courses-store-cumulative", "show_grouping": False},
    ("courses-frac-trend", "courses-chart-frac-trend"),
    ("courses-complexity", "courses-chart-complexity"),
    ("courses-technique-dist", "courses-chart-technique-dist"),
    ("courses-quit-trend", "courses-chart-quit-trend"),
    ("courses-ridgeline", "courses-chart-ridgeline"),
    ("courses-frac-dist", "courses-chart-frac-dist"),
    ("courses-sites", "courses-chart-sites"),
    ("courses-interruption", "courses-chart-interruption"),
])


# ---------------------------------------------------------------------------
# Slice-by dim styling
# ---------------------------------------------------------------------------
_SLICE_CLASS_JS = """function(val) {
    return (val && val !== "total") ? "slice-group-active" : "slice-total-active";
}"""

for _sid in ["courses-volume-slice", "courses-cumulative-slice",
              "courses-frac-trend-slice", "courses-quit-trend-slice",
              "courses-interruption-slice"]:
    clientside_callback(
        _SLICE_CLASS_JS,
        Output(_sid, "className"),
        Input(_sid, "value"),
    )

_HIDE_STACK_JS = """function(sliceVal, chartType) {
    var single = !sliceVal || sliceVal === "total" || sliceVal === "";
    var noStack = chartType === "line";
    return (single || noStack) ? {"display": "none"} : {};
}"""

for _slice_id, _settings_id in [
    ("courses-volume-slice", "courses-volume"),
    ("courses-frac-trend-slice", "courses-frac-trend"),
    ("courses-quit-trend-slice", "courses-quit-trend"),
]:
    clientside_callback(
        _HIDE_STACK_JS,
        Output(f"{_settings_id}-settings-stack-wrap", "style", allow_duplicate=True),
        Input(_slice_id, "value"),
        Input(f"{_settings_id}-settings-type", "value"),
        prevent_initial_call="initial_duplicate",
    )

# Course Interruptions: bar-only, so the chart-type selector was removed.
# Hide the grouping toggle when no slice is selected (single-series view).
clientside_callback(
    """function(sliceVal) {
        var single = !sliceVal || sliceVal === "total" || sliceVal === "";
        return single ? {"display": "none"} : {};
    }""",
    Output("courses-interruption-settings-stack-wrap", "style", allow_duplicate=True),
    Input("courses-interruption-slice", "value"),
    prevent_initial_call="initial_duplicate",
)

# Technique dist: hide grouping in line mode (always multi-series)
clientside_callback(
    """function(chartType) {
        return chartType === "line" ? {"display": "none"} : {};
    }""",
    Output("courses-technique-dist-settings-stack-wrap", "style", allow_duplicate=True),
    Input("courses-technique-dist-settings-type", "value"),
    prevent_initial_call="initial_duplicate",
)

# Cumulative chart: also hide grouping in Prior Periods mode (single dimension)
clientside_callback(
    """function(mode, sliceVal, chartType) {
        var single = !sliceVal || sliceVal === "total" || sliceVal === "";
        if (single) return {"display": "none"};
        if (chartType === "bar") return {};
        var isPrior = mode === "prior";
        var noStack = chartType === "line";
        return (isPrior || noStack) ? {"display": "none"} : {};
    }""",
    Output("courses-cumulative-settings-stack-wrap", "style"),
    Input("courses-cumulative-mode", "value"),
    Input("courses-cumulative-slice", "value"),
    Input("courses-cumulative-settings-type", "value"),
)


# ---------------------------------------------------------------------------
# Cumulative sub-controls based on mode + chart-type:
#   bar           → hide mode toggle, show period-type + slice together
#   prior + non-bar → show mode + period-type, hide slice
#   slice + non-bar → show mode + slice, hide period-type
# ---------------------------------------------------------------------------
clientside_callback(
    """function(mode, chartType) {
        if (chartType === "bar") {
            return [{"display": "none"}, {}, {}];
        }
        if (mode === "prior") {
            return [{}, {}, {"display": "none"}];
        }
        return [{}, {"display": "none"}, {}];
    }""",
    Output("courses-cumulative-mode", "style"),
    Output("courses-cumulative-period-type", "style"),
    Output("courses-cumulative-slice", "style"),
    Input("courses-cumulative-mode", "value"),
    Input("courses-cumulative-settings-type", "value"),
)

# Disable Calendar when period > 1 year; cap prior-periods slider to available data
clientside_callback(
    """function(storeData, currentPtValue) {
        return window.dash_clientside.cumulative.updatePriorControls(storeData, currentPtValue);
    }""",
    Output("courses-cumulative-period-type", "data"),
    Output("courses-cumulative-period-type", "value", allow_duplicate=True),
    Output("courses-cumulative-settings-prior-periods", "max"),
    Output("courses-cumulative-settings-prior-periods", "marks"),
    Input("courses-store-cumulative", "data"),
    State("courses-cumulative-period-type", "value"),
    prevent_initial_call=True,
)

# Hide "Total" slice option in line/area mode (only useful for bar)
_COURSES_CUMUL_SLICE_ALL = [
    {"value": "total", "label": "Total"},
    {"value": "physician", "label": "MD"},
    {"value": "site", "label": "Site"},
    {"value": "diagnosis", "label": "Dx"},
]
_COURSES_CUMUL_SLICE_NO_TOTAL = [o for o in _COURSES_CUMUL_SLICE_ALL if o["value"] != "total"]

clientside_callback(
    """function(chartType, sliceVal) {
        var all = %s;
        var noTotal = %s;
        if (chartType === "bar") {
            return [all, window.dash_clientside.no_update];
        }
        var newVal = (sliceVal === "total") ? "physician" : window.dash_clientside.no_update;
        return [noTotal, newVal];
    }""" % (str(_COURSES_CUMUL_SLICE_ALL).replace("'", '"'), str(_COURSES_CUMUL_SLICE_NO_TOTAL).replace("'", '"')),
    Output("courses-cumulative-slice", "data"),
    Output("courses-cumulative-slice", "value", allow_duplicate=True),
    Input("courses-cumulative-settings-type", "value"),
    State("courses-cumulative-slice", "value"),
    prevent_initial_call=True,
)


# ---------------------------------------------------------------------------
# Filter Callbacks
# ---------------------------------------------------------------------------

def _register_courses_filter_callbacks():
    """Register all filter-sync callbacks."""

    # A) Preset → Slider + DatePicker
    @callback(
        Output("courses-date-slider", "value"),
        Output("courses-filter-daterange", "start_date", allow_duplicate=True),
        Output("courses-filter-daterange", "end_date", allow_duplicate=True),
        Input("courses-filter-date-preset", "value"),
        prevent_initial_call=True,
    )
    def _sync_preset(preset):
        if not preset or preset == "custom":
            return (dash.no_update,) * 3
        sv = preset_to_slider_val(preset, MAX_IDX)
        s, e = preset_to_exact_dates(preset)
        return sv, s, e

    # B) Slider → DatePicker + Label (clientside)
    clientside_callback(
        ClientsideFunction(namespace="coursesDateSlider", function_name="syncSlider"),
        Output("courses-filter-daterange", "start_date", allow_duplicate=True),
        Output("courses-filter-daterange", "end_date", allow_duplicate=True),
        Output("courses-date-range-label", "children"),
        Input("courses-date-slider", "value"),
        State("courses-filter-daterange", "start_date"),
        State("courses-filter-daterange", "end_date"),
        prevent_initial_call=True,
    )

    # C) DatePicker → Slider
    @callback(
        Output("courses-date-slider", "value", allow_duplicate=True),
        Input("courses-filter-daterange", "start_date"),
        Input("courses-filter-daterange", "end_date"),
        State("courses-date-slider", "value"),
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

    # D) Slider → auto-clear preset
    @callback(
        Output("courses-filter-date-preset", "value", allow_duplicate=True),
        Input("courses-date-slider", "value"),
        State("courses-filter-date-preset", "value"),
        prevent_initial_call=True,
    )
    def _maybe_clear_preset(slider_val, current_preset):
        if not current_preset or current_preset == "custom":
            return dash.no_update
        expected = preset_to_slider_val(current_preset, MAX_IDX)
        if slider_val == expected:
            return dash.no_update
        return "custom"

    # --- Trigger labels ---
    clientside_callback(
        """function(val) {
            if (!val) return "Physician";
            return val.split(", ")[0];
        }""",
        Output("courses-physician-trigger", "children"),
        Input("courses-filter-physician", "value"),
    )
    # --- Clear-button visibility ---
    clientside_callback(
        """function(val) { return val ? {"display": "inline-flex"} : {"display": "none"}; }""",
        Output("courses-physician-clear", "style"),
        Input("courses-filter-physician", "value"),
    )

    # --- Clear-button actions ---
    clientside_callback(
        """function(n) { return null; }""",
        Output("courses-filter-physician", "value", allow_duplicate=True),
        Input("courses-physician-clear", "n_clicks"),
        prevent_initial_call=True,
    )

    # --- Technique trigger/clear/visibility ---
    clientside_callback(
        """function(vals) {
            if (!vals || vals.length === 0) return "Technique";
            if (vals.length === 1) return vals[0];
            return vals.length + " selected";
        }""",
        Output("courses-technique-trigger", "children"),
        Input("courses-filter-technique", "value"),
    )
    clientside_callback(
        """function(vals) { return vals && vals.length > 0 ? {"display": "inline-flex"} : {"display": "none"}; }""",
        Output("courses-technique-clear", "style"),
        Input("courses-filter-technique", "value"),
    )
    clientside_callback(
        """function(n) { return []; }""",
        Output("courses-filter-technique", "value", allow_duplicate=True),
        Input("courses-technique-clear", "n_clicks"),
        prevent_initial_call=True,
    )


_register_courses_filter_callbacks()
register_diagnosis_callbacks("courses")


# ---------------------------------------------------------------------------
# Fraction slider engagement logic
# ---------------------------------------------------------------------------

# User drags slider → mark as engaged
clientside_callback(
    """function(val, currentEngaged, sliderMin, sliderMax) {
        // If value matches the full data range, don't engage
        if (val && val[0] === sliderMin && val[1] === sliderMax) {
            return window.dash_clientside.no_update;
        }
        return true;
    }""",
    Output("courses-fraction-engaged", "data", allow_duplicate=True),
    Input("courses-fraction-slider", "value"),
    State("courses-fraction-engaged", "data"),
    State("courses-fraction-slider", "min"),
    State("courses-fraction-slider", "max"),
    prevent_initial_call=True,
)

# Clear button → disengage
clientside_callback(
    """function(n) {
        if (!n) return window.dash_clientside.no_update;
        return false;
    }""",
    Output("courses-fraction-engaged", "data", allow_duplicate=True),
    Input("courses-fraction-clear", "n_clicks"),
    prevent_initial_call=True,
)

# Show/hide clear button based on engaged state
clientside_callback(
    """function(engaged) {
        return engaged ? {"display": "inline-flex"} : {"display": "none"};
    }""",
    Output("courses-fraction-clear", "style"),
    Input("courses-fraction-engaged", "data"),
)

# Dim the slider label when not engaged, highlight when active
clientside_callback(
    """function(engaged) {
        if (engaged) return {"color": "#7C2A83", "fontWeight": 600, "fontSize": "var(--mantine-font-size-xs)"};
        return {"color": "#9CA3AF", "fontWeight": 500, "fontSize": "var(--mantine-font-size-xs)"};
    }""",
    Output("courses-fraction-label", "style"),
    Input("courses-fraction-engaged", "data"),
)

# Dim the slider color when not engaged
clientside_callback(
    """function(engaged) {
        return engaged ? "violet" : "gray";
    }""",
    Output("courses-fraction-slider", "color"),
    Input("courses-fraction-engaged", "data"),
)

# Auto-sync slider value to [min, max] when not engaged
# Fires when min/max change (from server) or when engaged flips to false
clientside_callback(
    """function(engaged, sliderMin, sliderMax, currentVal) {
        if (engaged) return window.dash_clientside.no_update;
        var target = [sliderMin, sliderMax];
        if (currentVal && currentVal.length === 2
            && currentVal[0] === target[0] && currentVal[1] === target[1]) {
            return window.dash_clientside.no_update;
        }
        return target;
    }""",
    Output("courses-fraction-slider", "value", allow_duplicate=True),
    Input("courses-fraction-engaged", "data"),
    State("courses-fraction-slider", "min"),
    State("courses-fraction-slider", "max"),
    State("courses-fraction-slider", "value"),
    prevent_initial_call=True,
)


# ---------------------------------------------------------------------------
# Dynamic physician chip population
# ---------------------------------------------------------------------------
@callback(
    Output("courses-filter-physician", "children"),
    Output("courses-filter-physician", "value", allow_duplicate=True),
    Input("courses-interval", "n_intervals"),
    Input("courses-date-slider", "value"),
    Input("courses-filter-department", "value"),
    Input("courses-diag-store", "data"),
    Input("courses-diag-mode", "data"),
    Input("courses-filter-technique", "value"),
    Input("courses-filter-status", "value"),
    Input("courses-date-mode", "value"),
    Input("courses-inpatient-switch", "checked"),
    Input("courses-physician-role", "value"),
    prevent_initial_call="initial_duplicate",
)
def _populate_physician_chips(_n, slider_val, departments, diagnosis_cats,
                              diag_mode, techniques, status, date_mode,
                              inpatient, physician_role):
    """Populate physician filter from courses dataset, applying all active filters."""
    from data.loader import load_courses
    from components.filter_bar import physician_short_name

    try:
        df = load_courses()
    except Exception:
        return [], None

    phys_col = "ConsultPhysician" if physician_role == "consult" else "TreatingPhysician"

    if df.empty or phys_col not in df.columns:
        return [], None

    c2b = _build_diag_lookup()

    # Date column based on mode
    date_col = _date_col_for_mode(date_mode)
    if date_col not in df.columns or df[date_col].notna().sum() == 0:
        date_col = "CourseStartDate"

    # Completed mode
    if date_mode == "completed":
        df = df[_is_effectively_completed(df)]

    # Date filter
    start, end = _get_date_range(slider_val, None)
    if date_col in df.columns:
        df = df[df[date_col].notna()]
        df = df[(df[date_col] >= start) & (df[date_col] <= end)]

    # Apply dimension filters (skip physician)
    df = _apply_filters(df, departments, None, diagnosis_cats, status, None, c2b,
                        inpatient=inpatient, techniques=techniques,
                        diag_mode=diag_mode or "primary")

    mds = sorted(df[phys_col].dropna().unique())

    chips = [
        dmc.Chip(
            physician_short_name(md),
            value=md,
            size="xs",
            variant="filled",
        )
        for md in mds
    ]
    # Clear selection only when role toggle is the trigger
    from dash import ctx
    clear_val = None if ctx.triggered_id == "courses-physician-role" else dash.no_update
    return chips, clear_val


# ---------------------------------------------------------------------------
# Dynamic technique chip population
# ---------------------------------------------------------------------------
@callback(
    Output("courses-filter-technique", "children"),
    Input("courses-interval", "n_intervals"),
)
def _populate_technique_chips(_n):
    """Populate technique filter from the courses dataset."""
    from data.loader import load_courses

    try:
        df = load_courses()
    except Exception:
        return []

    if df.empty or "TreatmentTechniques" not in df.columns:
        return []

    # Explode comma-separated techniques
    all_techs = set()
    for val in df["TreatmentTechniques"].dropna():
        for t in str(val).split(","):
            t = t.strip()
            if t:
                all_techs.add(t)

    return [
        dmc.Chip(t, value=t, size="xs", variant="filled")
        for t in sorted(all_techs)
    ]


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


def _date_col_for_mode(mode):
    """Return the column name to use for date filtering based on mode.

    "started" uses FirstTreatmentDate — CourseStartDate is when the course
    record is created in ARIA, which can predate the actual first treatment
    by days/weeks.  FirstTreatmentDate reflects when treatment actually began.
    """
    if mode == "treated":
        return "FirstTreatmentDate"
    elif mode == "completed":
        return "LastTreatmentDate"
    return "FirstTreatmentDate"  # "started" (default)


def _build_diag_lookup():
    """Build diagnosis code → category map."""
    from data.loader import load_diagnosis
    try:
        diag_df = load_diagnosis()
    except Exception:
        diag_df = None
    return build_code_to_category(diag_df)


def _trim_edges(series_or_list):
    """Replace leading/trailing zeros/NaN with None so Plotly gaps the line."""
    raw = list(series_or_list)
    n = len(raw)
    for i in range(n):
        v = raw[i]
        if v is None:
            continue
        try:
            if math.isnan(v):
                raw[i] = None
        except (TypeError, ValueError):
            pass

    def _has_data(v):
        return v is not None and v != 0
    first = next((i for i in range(n) if _has_data(raw[i])), None)
    if first is None:
        return [None] * n
    last = next((i for i in range(n - 1, -1, -1) if _has_data(raw[i])), None)
    for i in range(first):
        raw[i] = None
    for i in range(last + 1, n):
        raw[i] = None
    return raw


def _build_day_index_ticks(start_norm, n_days, max_ticks=12):
    """Build tick positions/labels for a day-index x-axis."""
    candidates = []

    if n_days <= max_ticks:
        pos, lbl = [], []
        for i in range(n_days):
            d = start_norm + pd.Timedelta(days=i)
            pos.append(i)
            lbl.append(d.strftime("%m/%d"))
        candidates.append((pos, lbl))

    # Weekly
    pos, lbl = [], []
    for i in range(0, n_days, 7):
        d = start_norm + pd.Timedelta(days=i)
        pos.append(i)
        lbl.append(d.strftime("%m/%d"))
    candidates.append((pos, lbl))

    # Monthly
    pos, lbl = [], []
    prev_month = None
    for i in range(n_days):
        d = start_norm + pd.Timedelta(days=i)
        if d.month != prev_month:
            pos.append(i)
            lbl.append(d.strftime("%b") if n_days > 180 else d.strftime("%b %d"))
            prev_month = d.month
    candidates.append((pos, lbl))

    # Quarterly
    pos, lbl = [], []
    prev_q = None
    for i in range(n_days):
        d = start_norm + pd.Timedelta(days=i)
        q = (d.year, (d.month - 1) // 3)
        if q != prev_q:
            pos.append(i)
            lbl.append(d.strftime("%b '%y"))
            prev_q = q
    candidates.append((pos, lbl))

    # Yearly
    pos, lbl = [], []
    prev_year = None
    for i in range(n_days):
        d = start_norm + pd.Timedelta(days=i)
        if d.year != prev_year:
            pos.append(i)
            lbl.append(str(d.year))
            prev_year = d.year
    candidates.append((pos, lbl))

    # Every 2 years
    pos, lbl = [], []
    prev_year = None
    for i in range(n_days):
        d = start_norm + pd.Timedelta(days=i)
        if d.year != prev_year and d.year % 2 == 0:
            pos.append(i)
            lbl.append(str(d.year))
            prev_year = d.year
    candidates.append((pos, lbl))

    # Every 5 years
    pos, lbl = [], []
    prev_year = None
    for i in range(n_days):
        d = start_norm + pd.Timedelta(days=i)
        if d.year != prev_year and d.year % 5 == 0:
            pos.append(i)
            lbl.append(str(d.year))
            prev_year = d.year
    candidates.append((pos, lbl))

    for p, l in candidates:
        if len(p) <= max_ticks:
            return p, l
    return candidates[-1]


# ---------------------------------------------------------------------------
# Ridgeline: Fractions per Course by Year
# ---------------------------------------------------------------------------

def _prepare_ridgeline_data(df, date_col):
    """Extract per-year fraction values for the ridgeline store.

    Returns a JSON-serialisable dict or None.
    """
    col = "FractionsPrescribed"
    if col not in df.columns or df.empty or date_col not in df.columns:
        return None

    tmp = df[[date_col, col]].copy()
    tmp["_frac"] = pd.to_numeric(tmp[col], errors="coerce")
    tmp = tmp.dropna(subset=["_frac", date_col])
    tmp = tmp[tmp["_frac"] > 0]
    if tmp.empty:
        return None

    # Exclude outliers: fractions above Q3 + 1.5×IQR
    q1, q3 = tmp["_frac"].quantile(0.25), tmp["_frac"].quantile(0.75)
    upper_fence = q3 + 1.5 * (q3 - q1)
    tmp = tmp[tmp["_frac"] <= upper_fence]

    tmp["_year"] = tmp[date_col].dt.year
    years = sorted(tmp["_year"].unique(), reverse=True)
    if not years:
        return None

    per_year = {}
    for yr in years:
        per_year[str(yr)] = tmp.loc[tmp["_year"] == yr, "_frac"].tolist()

    return {
        "years": [str(y) for y in years],
        "per_year": per_year,
        "x_min": max(0, float(tmp["_frac"].min()) - 2),
        "x_max": float(tmp["_frac"].max()) + 2,
    }


# ---------------------------------------------------------------------------
# Fractions Trend: median fractions over time (all agg × slice combos)
# ---------------------------------------------------------------------------

def _prepare_frac_trend_data(dff, date_col, c2b, start=None, end=None, diag_mode="primary"):
    """Prepare median-fractions-over-time data for all agg × slice combos."""
    frac_col = "FractionsPrescribed"
    if frac_col not in dff.columns or date_col not in dff.columns or dff.empty:
        return None

    tmp = dff[[date_col, frac_col]].copy()
    for col in ["TreatingPhysician", "Department", "DiagnosisCodes"]:
        if col in dff.columns:
            tmp[col] = dff[col].values

    tmp["_frac"] = pd.to_numeric(tmp[frac_col], errors="coerce")
    tmp = tmp.dropna(subset=["_frac", date_col])
    tmp = tmp[tmp["_frac"] > 0]
    if tmp.empty:
        return None

    if start is not None:
        tmp["_plot_date"] = tmp[date_col].clip(lower=start)
        if end is not None:
            tmp["_plot_date"] = tmp["_plot_date"].clip(upper=end)
    else:
        tmp["_plot_date"] = tmp[date_col]

    combos = {}
    for agg in ["W", "M", "Y"]:
        period_code = "Y" if agg == "Y" else agg
        t = tmp.copy()
        t["period"] = t["_plot_date"].dt.to_period(period_code).dt.to_timestamp()
        all_periods = sorted(t["period"].unique())
        dates = [d.isoformat() for d in all_periods]

        for slice_key in ["", "physician", "site", "diagnosis"]:
            series = []
            if not slice_key:
                medians = t.groupby("period")["_frac"].median().reindex(all_periods)
                series.append({
                    "name": "Median",
                    "values": [round(float(v), 1) if pd.notna(v) else None for v in medians],
                    "color": PRIMARY,
                })
            elif slice_key == "physician":
                col = "TreatingPhysician"
                if col in t.columns:
                    for i, phys in enumerate(sorted(t[col].dropna().unique())):
                        sub = t[t[col] == phys]
                        medians = sub.groupby("period")["_frac"].median().reindex(all_periods)
                        series.append({
                            "name": phys.split(",")[0] if "," in phys else phys,
                            "values": [round(float(v), 1) if pd.notna(v) else None for v in medians],
                            "color": CHART_COLORWAY[i % len(CHART_COLORWAY)],
                        })
            elif slice_key == "site":
                if "Department" in t.columns:
                    for dept in sorted(t["Department"].dropna().unique()):
                        sub = t[t["Department"] == dept]
                        medians = sub.groupby("period")["_frac"].median().reindex(all_periods)
                        series.append({
                            "name": dept,
                            "values": [round(float(v), 1) if pd.notna(v) else None for v in medians],
                            "color": DEPARTMENT_COLORS.get(dept, CHART_COLORWAY[0]),
                        })
            elif slice_key == "diagnosis" and c2b and "DiagnosisCodes" in t.columns:
                t2 = assign_diagnosis_column(t, c2b, mode=diag_mode)
                top_bs = t2["_bs"].value_counts().head(8).index.tolist()
                for i, bs in enumerate(top_bs):
                    sub = t2[t2["_bs"] == bs]
                    medians = sub.groupby("period")["_frac"].median().reindex(all_periods)
                    series.append({
                        "name": bs,
                        "values": [round(float(v), 1) if pd.notna(v) else None for v in medians],
                        "color": CHART_COLORWAY[i % len(CHART_COLORWAY)],
                    })

            combos[f"{agg}|{slice_key}"] = {
                "dates": dates,
                "series": series,
            }

    return combos


# ---------------------------------------------------------------------------
# Quit Rate Trend: % of completed courses where delivered < planned
# ---------------------------------------------------------------------------

def _prepare_quit_trend_data(completed_df, date_col, c2b, start=None, end=None, diag_mode="primary"):
    """Prepare quit-rate-over-time data for all agg × slice × metric combos.

    Computes quit flags for both session-based and fraction-based metrics.
    """
    has_sessions = (
        "CourseSessionsPlanned" in completed_df.columns
        and "CourseSessionsDelivered" in completed_df.columns
    )
    has_fractions = (
        "FractionsPrescribed" in completed_df.columns
        and "FractionsDelivered" in completed_df.columns
    )
    if (not has_sessions and not has_fractions) or completed_df.empty:
        return None
    if date_col not in completed_df.columns:
        return None

    # Build base df — need at least one metric with planned > 0 & delivered > 0
    base_mask = completed_df[date_col].notna()
    if has_sessions:
        sess_mask = (completed_df["CourseSessionsPlanned"] > 0) & (completed_df["CourseSessionsDelivered"] > 0)
    if has_fractions:
        frac_mask = (completed_df["FractionsPrescribed"] > 0) & (completed_df["FractionsDelivered"] > 0)

    if has_sessions and has_fractions:
        base_mask = base_mask & (sess_mask | frac_mask)
    elif has_sessions:
        base_mask = base_mask & sess_mask
    else:
        base_mask = base_mask & frac_mask

    tmp = completed_df[base_mask].copy()
    if has_sessions:
        tmp["_quit_session"] = (
            tmp["CourseSessionsDelivered"] < tmp["CourseSessionsPlanned"]
        ).astype(int)
    if has_fractions:
        tmp["_quit_fraction"] = (
            tmp["FractionsDelivered"] < tmp["FractionsPrescribed"]
        ).astype(int)
    # Default _quit for backwards compat
    tmp["_quit"] = tmp.get("_quit_fraction", tmp.get("_quit_session"))

    for col in ["TreatingPhysician", "Department", "DiagnosisCodes"]:
        if col in completed_df.columns and col not in tmp.columns:
            tmp[col] = completed_df.loc[tmp.index, col].values

    if tmp.empty:
        return None

    if start is not None:
        tmp["_plot_date"] = tmp[date_col].clip(lower=start)
        if end is not None:
            tmp["_plot_date"] = tmp["_plot_date"].clip(upper=end)
    else:
        tmp["_plot_date"] = tmp[date_col]

    # Build combos for each metric × agg × slice
    metrics = []
    if has_fractions:
        metrics.append(("fraction", "_quit_fraction"))
    if has_sessions:
        metrics.append(("session", "_quit_session"))

    combos = {}
    for metric_name, quit_col in metrics:
        for agg in ["W", "M", "Y"]:
            period_code = "Y" if agg == "Y" else agg
            t = tmp.copy()
            t["period"] = t["_plot_date"].dt.to_period(period_code).dt.to_timestamp()
            all_periods = sorted(t["period"].unique())
            dates = [d.isoformat() for d in all_periods]

            for slice_key in ["", "physician", "site", "diagnosis"]:
                series = []

                def _rate_series(sub, name, color, _qc=quit_col, _ap=all_periods):
                    grp = sub.groupby("period")[_qc].agg(["sum", "count"]).reindex(_ap)
                    rates = []
                    for _, row in grp.iterrows():
                        if pd.notna(row["count"]) and row["count"] >= 5:
                            rates.append(round(float(row["sum"]) / float(row["count"]) * 100, 1))
                        else:
                            rates.append(None)
                    series.append({"name": name, "values": rates, "color": color})

                if not slice_key:
                    _rate_series(t, "Overall", PRIMARY)
                elif slice_key == "physician":
                    col = "TreatingPhysician"
                    if col in t.columns:
                        for i, phys in enumerate(sorted(t[col].dropna().unique())):
                            label = phys.split(",")[0] if "," in phys else phys
                            _rate_series(
                                t[t[col] == phys], label,
                                CHART_COLORWAY[i % len(CHART_COLORWAY)],
                            )
                elif slice_key == "site":
                    if "Department" in t.columns:
                        for dept in sorted(t["Department"].dropna().unique()):
                            _rate_series(
                                t[t["Department"] == dept], dept,
                                DEPARTMENT_COLORS.get(dept, CHART_COLORWAY[0]),
                            )
                elif slice_key == "diagnosis" and c2b and "DiagnosisCodes" in t.columns:
                    t2 = assign_diagnosis_column(t, c2b, mode=diag_mode)
                    top_bs = t2["_bs"].value_counts().head(8).index.tolist()
                    for i, bs in enumerate(top_bs):
                        _rate_series(
                            t2[t2["_bs"] == bs], bs,
                            CHART_COLORWAY[i % len(CHART_COLORWAY)],
                        )

                combos[f"{agg}|{slice_key}|{metric_name}"] = {"dates": dates, "series": series}

    return combos


# ---------------------------------------------------------------------------
# Course Interruption: actual duration vs expected duration
# ---------------------------------------------------------------------------

def _prepare_interruption_data(completed_df):
    """Compute course interruption metrics.

    A course is "interrupted" if its actual treatment duration exceeds the
    expected duration based on fractions delivered at daily frequency,
    excluding weekends and holidays.

    Returns a dict with histogram data and summary stats, or None.
    """
    from utils.holidays import get_holidays

    needed = {"FirstTreatmentDate", "LastTreatmentDate", "FractionsDelivered"}
    if not needed.issubset(completed_df.columns) or completed_df.empty:
        return None

    df = completed_df[
        completed_df["FirstTreatmentDate"].notna()
        & completed_df["LastTreatmentDate"].notna()
        & (completed_df["FractionsDelivered"] > 1)
    ].copy()

    if df.empty:
        return None

    holidays = get_holidays()
    hol_arr = np.array(sorted(holidays), dtype="datetime64[D]") if holidays else np.array([], dtype="datetime64[D]")

    ft = df["FirstTreatmentDate"].values.astype("datetime64[D]")
    lt = df["LastTreatmentDate"].values.astype("datetime64[D]")
    fx = df["FractionsDelivered"].values.astype(int)

    # Actual business days of treatment span
    actual_bdays = np.busday_count(ft, lt, holidays=hol_arr).astype(float) + 1  # inclusive

    # Expected business days based on frequency
    # Default: daily (1 fx per business day)
    expected_bdays = fx.astype(float)
    if "RxFrequency" in df.columns:
        freq = df["RxFrequency"].fillna("")
        # Every Other Day: 1 fx per 2 business days
        mask_eod = freq.str.lower().str.contains("every other", na=False)
        expected_bdays = np.where(mask_eod, fx * 2.0, expected_bdays)
        # 2X Daily: 2 fx per business day
        mask_2x = freq.str.lower().str.contains("2x daily", na=False)
        expected_bdays = np.where(mask_2x, np.ceil(fx / 2.0), expected_bdays)
        # Twice Weekly: 2 fx per 5 business days
        mask_tw = freq.str.lower().str.contains("twice weekly", na=False)
        expected_bdays = np.where(mask_tw, np.ceil(fx * 2.5), expected_bdays)

    # Delay in business days
    delay = actual_bdays - expected_bdays
    df["_delay_bdays"] = delay

    # Interruption = delay > 0
    df["_interrupted"] = delay > 0

    # Bucket definitions
    _BUCKETS = [
        ("1 day", 1, 1),
        ("2-3 days", 2, 3),
        ("4-7 days", 4, 7),
        ("1-2 wk", 8, 14),
        ("2-4 wk", 15, 28),
        ("> 4 wk", 29, 9999),
    ]

    def _summarize(sub):
        n = len(sub)
        n_int = int(sub["_interrupted"].sum())
        dels = sub.loc[sub["_interrupted"], "_delay_bdays"]
        bkts = []
        for label, lo, hi in _BUCKETS:
            count = int(((dels >= lo) & (dels <= hi)).sum()) if not dels.empty else 0
            bkts.append({"label": label, "count": count})
        return {
            "n_total": n,
            "n_interrupted": n_int,
            "rate": round(n_int / n * 100, 1) if n else 0,
            "median_delay": round(float(dels.median()), 1) if not dels.empty else 0,
            "buckets": bkts,
        }

    result = {"": _summarize(df)}

    # Per-physician
    if "TreatingPhysician" in df.columns:
        phys_data = {}
        for phys in sorted(df["TreatingPhysician"].dropna().unique()):
            label = phys.split(",")[0] if "," in phys else phys
            phys_data[label] = _summarize(df[df["TreatingPhysician"] == phys])
        result["physician"] = phys_data

    # Per-site
    if "Department" in df.columns:
        site_data = {}
        for dept in sorted(df["Department"].dropna().unique()):
            site_data[dept] = _summarize(df[df["Department"] == dept])
        result["site"] = site_data

    # Per-diagnosis
    if "DiagnosisCodes" in df.columns:
        try:
            from pages.courses import _build_diag_lookup, assign_diagnosis_column
            c2b = _build_diag_lookup()
            if c2b:
                df2 = assign_diagnosis_column(df, c2b, mode="primary")
                dx_data = {}
                for bs in df2["_bs"].value_counts().head(8).index:
                    dx_data[bs] = _summarize(df2[df2["_bs"] == bs])
                result["diagnosis"] = dx_data
        except Exception:
            pass

    return result


# ---------------------------------------------------------------------------
# Fractions Distribution: histogram/density data
# ---------------------------------------------------------------------------

def _prepare_frac_dist_data(dff):
    """Prepare fractions distribution data for the store."""
    frac_col = "FractionsPrescribed"
    if frac_col not in dff.columns or dff.empty:
        return None

    vals = pd.to_numeric(dff[frac_col], errors="coerce").dropna()
    vals = vals[vals > 0]
    if vals.empty:
        return None

    arr = vals.values
    try:
        from scipy.stats import gaussian_kde
        kde = gaussian_kde(arr, bw_method="silverman")
        x_min = max(0, float(arr.min()) - 2)
        x_max = float(arr.max()) + 2
        x_grid = np.linspace(x_min, x_max, 200)
        kde_y_raw = kde(x_grid)
        kde_x = [round(float(v), 2) for v in x_grid]
        kde_y = [round(float(v), 6) for v in kde_y_raw]
    except Exception:
        kde_x, kde_y = [], []

    return {
        "values": [round(float(v), 1) for v in arr],
        "median": round(float(np.median(arr)), 1),
        "mean": round(float(np.mean(arr)), 1),
        "p25": round(float(np.percentile(arr, 25)), 1),
        "p75": round(float(np.percentile(arr, 75)), 1),
        "n": int(len(arr)),
        "kde_x": kde_x,
        "kde_y": kde_y,
    }


# ---------------------------------------------------------------------------
# Complexity Trends: multi-machine, multi-dept, multi-plan over time
# ---------------------------------------------------------------------------

def _count_comma_items(series):
    """Count items in a comma-separated string column, returning numeric Series."""
    return series.fillna("").apply(
        lambda v: len([x for x in str(v).split(",") if x.strip()]) if pd.notna(v) and str(v).strip() else 0
    )


def _prepare_complexity_trend_data(dff, date_col, start=None, end=None, iso_map=None):
    """Prepare multi-machine/dept/plan/iso trend data for store.

    Returns a dict with keys for each agg period (W/M/Y), each containing
    dates + series for pct and avg modes for each dimension.

    iso_map: optional Series indexed by (PatientId, CourseId) → max UniqueIsocenters
    """
    if dff.empty or date_col not in dff.columns:
        return None

    tmp = dff.copy()
    if start is not None:
        tmp["_plot_date"] = tmp[date_col].clip(lower=start)
        if end is not None:
            tmp["_plot_date"] = tmp["_plot_date"].clip(upper=end)
    else:
        tmp["_plot_date"] = tmp[date_col]

    # Count machines, departments, plans per course
    if "Machines" in tmp.columns:
        tmp["_n_machines"] = _count_comma_items(tmp["Machines"])
    else:
        tmp["_n_machines"] = 0

    # Use original Departments column (comma-separated) if available, else Department (single)
    if "Departments" in tmp.columns:
        tmp["_n_depts"] = _count_comma_items(tmp["Departments"])
    elif "Department" in tmp.columns:
        tmp["_n_depts"] = 1
    else:
        tmp["_n_depts"] = 0

    if "PlanCount" in tmp.columns:
        tmp["_n_plans"] = pd.to_numeric(tmp["PlanCount"], errors="coerce").fillna(0).astype(int)
    else:
        tmp["_n_plans"] = 0

    # Max isocenters per course from Treatment Detail
    if iso_map is not None and "PatientId" in tmp.columns and "CourseId" in tmp.columns:
        tmp["_n_isos"] = (
            tmp.set_index(["PatientId", "CourseId"]).index
            .map(iso_map)
        )
        tmp["_n_isos"] = pd.to_numeric(tmp["_n_isos"], errors="coerce").fillna(1).astype(int)
    else:
        tmp["_n_isos"] = 1

    dims = [
        ("machines", "_n_machines", "Machines"),
        ("depts", "_n_depts", "Departments"),
        ("plans", "_n_plans", "Plans"),
        ("isos", "_n_isos", "Isocenters"),
    ]

    combos = {}
    for agg in ["W", "M", "Y"]:
        period_code = "Y" if agg == "Y" else agg
        t = tmp.copy()
        t["period"] = t["_plot_date"].dt.to_period(period_code).dt.to_timestamp()
        all_periods = sorted(t["period"].unique())
        dates = [d.isoformat() for d in all_periods]

        for dim, col, label in dims:
            grp = t.groupby("period")
            count_total = grp[col].count().reindex(all_periods, fill_value=0)
            count_multi = grp[col].apply(lambda s: (s > 1).sum()).reindex(all_periods, fill_value=0)
            avg_val = grp[col].mean().reindex(all_periods)

            pct_vals = []
            for p in all_periods:
                total = count_total.get(p, 0)
                multi = count_multi.get(p, 0)
                if total > 0:
                    pct_vals.append(round(multi / total * 100, 1))
                else:
                    pct_vals.append(None)

            avg_vals = [round(float(v), 2) if pd.notna(v) else None for v in avg_val]

            combos[f"{agg}|{dim}"] = {
                "dates": dates,
                "pct": pct_vals,
                "avg": avg_vals,
                "label": label,
            }

    return combos


# ---------------------------------------------------------------------------
# Technique Distribution: stacked area by advancement order
# ---------------------------------------------------------------------------

# Ordered from most to least advanced
_TECHNIQUE_ORDER = ["SRS", "SBRT", "VMAT", "IMRT", "3D", "Electron"]
_TECHNIQUE_COLORS = {
    "SRS": "#e74c3c",
    "SBRT": "#e67e22",
    "VMAT": "#9b59b6",
    "IMRT": "#3498db",
    "3D": "#2ecc71",
    "Electron": "#f1c40f",
}


def _prepare_technique_dist_data(dff, date_col, start=None, end=None, date_mode="started"):
    """Prepare technique distribution over time from courses data.

    Builds two counting modes:
    - "any": explode comma-separated techniques (course counted once per technique)
    - "primary": take only the first listed technique per course

    In "treated" mode, uses census-style counting: each course is counted in
    every period it was actively under treatment, matching the volume trend.

    Returns JSON-serialisable dict keyed by "{agg}|{counting}" for the store.
    """
    tech_col = "TreatmentTechniques"
    if dff.empty or date_col not in dff.columns or tech_col not in dff.columns:
        return None

    use_census = (
        date_mode == "treated"
        and "FirstTreatmentDate" in dff.columns
        and "LastTreatmentDate" in dff.columns
        and start is not None and end is not None
    )

    needed_cols = list(dict.fromkeys(
        [date_col, tech_col]
        + (["FirstTreatmentDate", "LastTreatmentDate"] if use_census else [])
    ))
    base = dff[[c for c in needed_cols if c in dff.columns]].dropna(subset=[date_col, tech_col]).copy()
    if base.empty:
        return None

    # Explode techniques for both counting modes
    # "any" — all techniques per course
    any_base = base.copy()
    any_base["_techs"] = any_base[tech_col].str.split(",")
    any_base = any_base.explode("_techs")
    any_base["_techs"] = any_base["_techs"].str.strip()
    any_base = any_base[any_base["_techs"] != ""]

    # "primary" — first technique only
    primary_base = base.copy()
    primary_base["_techs"] = primary_base[tech_col].str.split(",").str[0].str.strip()
    primary_base = primary_base[primary_base["_techs"] != ""]

    if any_base.empty:
        return None

    # Collect all techniques for consistent ordering
    all_techs = set(any_base["_techs"].unique()) | set(primary_base["_techs"].unique())
    ordered = [t for t in _TECHNIQUE_ORDER if t in all_techs]
    remaining = sorted(all_techs - set(ordered))
    ordered.extend(remaining)

    combos = {}
    for agg in ["W", "M", "Y"]:
        period_code = "Y" if agg == "Y" else agg

        for counting, src_df in [("any", any_base), ("primary", primary_base)]:
            if use_census:
                # Census: count each course in every period it's active
                period_range = pd.date_range(start, end, freq="D")
                periods_pd = sorted(period_range.to_period(period_code).unique())
                all_periods = [p.to_timestamp() for p in periods_pd]
                period_bounds = [
                    (p.to_timestamp().to_numpy(), p.to_timestamp(how="end").to_numpy())
                    for p in periods_pd
                ]

                ft = src_df["FirstTreatmentDate"].values
                lt = src_df["LastTreatmentDate"].fillna(src_df["FirstTreatmentDate"]).values
                techs = src_df["_techs"].values

                # For each period, count courses overlapping its full interval
                rows = []
                for p, (p_start, p_end) in zip(all_periods, period_bounds):
                    active = (ft <= p_end) & (lt >= p_start)
                    for tech in ordered:
                        count = int((active & (techs == tech)).sum())
                        rows.append((p, tech, count))

                pivot = pd.DataFrame(rows, columns=["period", "_techs", "count"])
                pivot = pivot.pivot(index="period", columns="_techs", values="count").fillna(0)
                pivot = pivot.reindex(all_periods, fill_value=0)
            else:
                # Standard: count by date_col per period, clipped to window
                t = src_df.copy()
                if start is not None:
                    t["_plot_date"] = t[date_col].clip(lower=start)
                    if end is not None:
                        t["_plot_date"] = t["_plot_date"].clip(upper=end)
                else:
                    t["_plot_date"] = t[date_col]
                t["period"] = t["_plot_date"].dt.to_period(period_code).dt.to_timestamp()
                all_periods = sorted(t["period"].unique())
                pivot = t.groupby(["period", "_techs"]).size().unstack(fill_value=0)
                pivot = pivot.reindex(all_periods, fill_value=0)

            dates = [d.isoformat() for d in all_periods]
            series = []
            for tech in ordered:
                vals = pivot[tech].tolist() if tech in pivot.columns else [0] * len(all_periods)
                series.append({
                    "name": tech,
                    "values": vals,
                    "color": _TECHNIQUE_COLORS.get(tech, CHART_COLORWAY[len(series) % len(CHART_COLORWAY)]),
                })

            combos[f"{agg}|{counting}"] = {
                "dates": dates,
                "series": series,
            }

    return combos


_RIDGE_HEIGHT = 720


def _build_ridgeline_figure(data, bw_factor=0.5, mode="density", theme="light"):
    """Build the ridgeline Plotly figure from store data + bandwidth factor."""
    from scipy.stats import gaussian_kde
    _is_dark = (theme or "light") == "dark"
    _ridge_border = "rgba(230,234,245,0.75)" if _is_dark else "rgba(255,255,255,0.45)"

    if not data:
        fig = empty_figure("No fractions data available")
        fig.update_layout(height=_RIDGE_HEIGHT)
        return fig

    years = data["years"]
    per_year = data["per_year"]

    spacing = 0.32
    peak_factor = 5.35

    if mode == "histogram":
        from plotly.subplots import make_subplots

        n_years = len(years)
        bin_min = int(data["x_min"])
        bin_max = int(data["x_max"]) + 1
        bins = np.arange(bin_min, bin_max + 1)
        bin_centers = (bins[:-1] + bins[1:]) / 2.0

        fig = make_subplots(
            rows=n_years, cols=1,
            shared_xaxes=True,
            vertical_spacing=0.01,
        )

        # `years` is sorted newest-first to match density mode's bottom-to-top
        # baseline ordering. Subplot rows count top-down, so flip the row
        # assignment to keep the newest year in the bottom row.
        for i, yr in enumerate(years):
            row = n_years - i
            vals = np.array(per_year[yr])
            counts, _ = np.histogram(vals, bins=bins)
            n_courses = len(vals)
            median_fx = float(np.median(vals)) if len(vals) else 0

            fig.add_trace(go.Bar(
                x=bin_centers.tolist(),
                y=counts.tolist(),
                marker_color="rgb(158, 113, 178)",
                marker_line_width=0,
                width=1.0,
                customdata=np.full(len(bin_centers), median_fx).tolist(),
                hovertemplate=(
                    f"<b>{yr}</b> (n={n_courses:,})"
                    "<br>Fractions: %{x:.0f}"
                    "<br>Count: %{y}"
                    "<br>Median: %{customdata:.0f}"
                    "<extra></extra>"
                ),
                showlegend=False,
            ), row=row, col=1)

            # Suppress y-axis labels; year label added as annotation below
            yaxis_key = f"yaxis{row}" if row > 1 else "yaxis"
            fig.update_layout(**{yaxis_key: dict(
                showticklabels=False, showgrid=False, zeroline=False,
            )})

        fig.update_xaxes(title_text="Fractions Prescribed", row=n_years, col=1)
        fig.update_layout(
            height=_RIDGE_HEIGHT, bargap=0,
            margin=dict(l=60, r=16, t=16, b=40),
        )
        apply_default_layout(fig)
        fig.update_layout(
            height=_RIDGE_HEIGHT, bargap=0,
            margin=dict(l=60, r=16, t=16, b=40),
        )
        # Re-suppress y tick labels after apply_default_layout
        # and add horizontal year annotations
        _year_label_color = "#E6E7EC" if _is_dark else "#6B7280"
        for i, yr in enumerate(years):
            row = n_years - i
            axis_name = f"yaxis{row}" if row > 1 else "yaxis"
            yref = f"y{row} domain" if row > 1 else "y domain"
            fig.update_layout(**{axis_name: dict(
                showticklabels=False, showgrid=False, zeroline=False,
            )})
            fig.add_annotation(
                text=str(yr), x=0, y=0.5,
                xref="paper", yref=yref,
                xanchor="right", yanchor="middle",
                xshift=-8,
                showarrow=False,
                font=dict(family=FONT_FAMILY, size=11, color=_year_label_color),
            )
        return fig

    else:  # density mode
        x_pts = np.linspace(data["x_min"], data["x_max"], 200)
        kde_curves = {}
        global_max = 0.0
        for yr in years:
            vals = np.array(per_year[yr])
            if len(vals) < 3:
                kde_curves[yr] = np.zeros_like(x_pts)
                continue
            try:
                if bw_factor <= 0.5:
                    mult = 0.15 + (bw_factor / 0.5) * 0.85
                else:
                    mult = 1.0 + ((bw_factor - 0.5) / 0.5) * 2.0
                silverman_bw = gaussian_kde(vals, bw_method="silverman").factor
                kde = gaussian_kde(vals, bw_method=silverman_bw * mult)
                y_pts = kde(x_pts)
            except Exception:
                y_pts = np.zeros_like(x_pts)
            kde_curves[yr] = y_pts
            peak = y_pts.max()
            if peak > global_max:
                global_max = peak

        scale = (peak_factor * spacing / global_max) if global_max > 0 else 1.0

        fig = go.Figure()
        ridge_tops = []
        ridges = []

        for i, yr in enumerate(years):
            baseline = i * spacing
            y_scaled = kde_curves[yr] * scale + baseline
            ridge_tops.append(float(np.max(y_scaled)) if len(y_scaled) else baseline)
            vals = per_year[yr]
            n_courses = len(vals)
            median_fx = float(np.median(vals)) if vals else 0

            ridges.append({
                "year": yr,
                "baseline": baseline,
                "x_pts": x_pts,
                "y_scaled": y_scaled,
                "n_courses": n_courses,
                "median_fx": median_fx,
            })

        for r in reversed(ridges):
            y_s = r["y_scaled"]
            b = r["baseline"]
            fig.add_trace(go.Scatter(
                x=np.concatenate([r["x_pts"], r["x_pts"][::-1]]).tolist(),
                y=np.concatenate([y_s, np.full(len(r["x_pts"]), b)]).tolist(),
                fill="toself",
                fillcolor="rgb(158, 113, 178)",
                line=dict(width=0, color="rgba(0,0,0,0)"),
                hoverinfo="skip",
                showlegend=False,
            ))
            x_list = r["x_pts"].tolist()
            y_list = r["y_scaled"].tolist()
            yr = r["year"]
            fig.add_trace(go.Scatter(
                x=x_list,
                y=y_list,
                mode="lines",
                line=dict(color=_ridge_border, width=1.5),
                name=str(yr),
                showlegend=False,
                customdata=np.full(len(x_list), r["median_fx"]).tolist(),
                hovertemplate=(
                    f"<b>{yr}</b> (n={r['n_courses']:,})"
                    "<br>Fractions: %{x:.0f}"
                    "<br>Median: %{customdata:.0f}"
                    "<extra></extra>"
                ),
            ))

    tick_vals = [i * spacing for i in range(len(years))]
    tick_text = [str(yr) for yr in years]
    ridge_axes = dict(
        yaxis=dict(
            tickvals=tick_vals, ticktext=tick_text,
            showgrid=True, gridcolor="rgba(200,200,200,0.45)",
            zeroline=False, title="",
            range=[-0.25 * spacing, (max(ridge_tops) if ridge_tops else spacing) + 0.2 * spacing],
        ),
        xaxis=dict(
            title="Fractions Prescribed",
            showgrid=True, gridcolor="rgba(200,200,200,0.3)",
            zeroline=False,
        ),
    )
    fig.update_layout(height=_RIDGE_HEIGHT, **ridge_axes,
                      margin=dict(l=60, r=16, t=16, b=40))
    apply_default_layout(fig)
    fig.update_layout(**ridge_axes, margin=dict(l=60, r=16, t=16, b=40))
    return fig


# ---------------------------------------------------------------------------
# Data Preparation: Volume Trend
# ---------------------------------------------------------------------------

def _prepare_volume_data(dff, agg, slice_by="", date_col="CourseStartDate", c2b=None,
                         start=None, end=None, date_mode="started", diag_mode="primary"):
    """Prepare course volume trend data for clientside rendering.

    In "treated" mode, counts how many courses were under active treatment
    during each period (census-style), rather than when they started.
    Other modes count courses by their date_col value per period.
    """
    if dff.empty or date_col not in dff.columns:
        return None

    dff = dff.copy()
    period_code = "Y" if agg == "Y" else agg

    # --- Census mode for "treated" ---
    use_census = (
        date_mode == "treated"
        and "FirstTreatmentDate" in dff.columns
        and "LastTreatmentDate" in dff.columns
        and start is not None and end is not None
    )

    if use_census:
        # Build period boundaries using to_period for consistent week alignment
        # with other charts (Monday-start weeks)
        period_range = pd.date_range(start, end, freq="D")
        periods_pd = sorted(period_range.to_period(period_code).unique())
        all_periods = [p.to_timestamp() for p in periods_pd]
        dates = [d.isoformat() for d in all_periods]
        # Count courses overlapping each period's full interval, not just those
        # active at the period's start instant — otherwise a yearly bar reflects
        # only courses on-beam on Jan 1 rather than all courses treated that year.
        starts_np = [p.to_timestamp().to_numpy() for p in periods_pd]
        ends_np = [p.to_timestamp(how="end").to_numpy() for p in periods_pd]

        ft = dff["FirstTreatmentDate"].values
        lt = dff["LastTreatmentDate"].fillna(dff["FirstTreatmentDate"]).values

        def _census_counts(sub_ft, sub_lt):
            """Count courses whose treatment overlapped each period interval."""
            counts = []
            for p_start, p_end in zip(starts_np, ends_np):
                counts.append(int(((sub_ft <= p_end) & (sub_lt >= p_start)).sum()))
            return counts

        series = []
        if not slice_by:
            series.append({
                "name": "Total",
                "values": _trim_edges(_census_counts(ft, lt)),
                "color": PRIMARY,
            })
        elif slice_by == "physician" and "TreatingPhysician" in dff.columns:
            for i, phys in enumerate(sorted(dff["TreatingPhysician"].dropna().unique())):
                mask = (dff["TreatingPhysician"] == phys).values
                series.append({
                    "name": phys.split(",")[0] if "," in phys else phys,
                    "values": _trim_edges(_census_counts(ft[mask], lt[mask])),
                    "color": CHART_COLORWAY[i % len(CHART_COLORWAY)],
                })
        elif slice_by == "site" and "Department" in dff.columns:
            for dept in sorted(dff["Department"].dropna().unique()):
                mask = (dff["Department"] == dept).values
                series.append({
                    "name": dept,
                    "values": _trim_edges(_census_counts(ft[mask], lt[mask])),
                    "color": DEPARTMENT_COLORS.get(dept, CHART_COLORWAY[0]),
                })
        elif slice_by == "diagnosis" and c2b and "DiagnosisCodes" in dff.columns:
            dff_bs = assign_diagnosis_column(dff, c2b, mode=diag_mode)
            top_bs = dff_bs["_bs"].value_counts().head(8).index.tolist()
            for i, bs in enumerate(top_bs):
                mask = (dff_bs["_bs"] == bs).values
                ft_bs = dff_bs["FirstTreatmentDate"].values[mask]
                lt_bs = dff_bs["LastTreatmentDate"].fillna(dff_bs["FirstTreatmentDate"]).values[mask]
                series.append({
                    "name": bs,
                    "values": _trim_edges(_census_counts(ft_bs, lt_bs)),
                    "color": CHART_COLORWAY[i % len(CHART_COLORWAY)],
                })

        return {
            "dates": dates,
            "series": series,
            "height": 350,
            "yTitle": "Active Courses",
            "hideLegend": len(series) <= 1,
        }

    # --- Standard mode: count by date_col per period ---
    if start is not None:
        dff["_plot_date"] = dff[date_col].clip(lower=start)
        if end is not None:
            dff["_plot_date"] = dff["_plot_date"].clip(upper=end)
    else:
        dff["_plot_date"] = dff[date_col]

    dff["period"] = dff["_plot_date"].dt.to_period(period_code).dt.to_timestamp()

    all_periods = sorted(dff["period"].unique())
    dates = [d.isoformat() for d in all_periods]

    series = []

    if not slice_by:
        counts = dff.groupby("period").size().reindex(all_periods, fill_value=0)
        series.append({
            "name": "Total",
            "values": _trim_edges(counts.tolist()),
            "color": PRIMARY,
        })

    elif slice_by == "physician":
        col = "TreatingPhysician"
        if col in dff.columns:
            physicians = sorted(dff[col].dropna().unique())
            for i, phys in enumerate(physicians):
                subset = dff[dff[col] == phys]
                counts = subset.groupby("period").size().reindex(all_periods, fill_value=0)
                series.append({
                    "name": phys.split(",")[0] if "," in phys else phys,
                    "values": _trim_edges(counts.tolist()),
                    "color": CHART_COLORWAY[i % len(CHART_COLORWAY)],
                })

    elif slice_by == "site":
        if "Department" in dff.columns:
            for dept in sorted(dff["Department"].dropna().unique()):
                subset = dff[dff["Department"] == dept]
                counts = subset.groupby("period").size().reindex(all_periods, fill_value=0)
                series.append({
                    "name": dept,
                    "values": _trim_edges(counts.tolist()),
                    "color": DEPARTMENT_COLORS.get(dept, CHART_COLORWAY[0]),
                })

    elif slice_by == "diagnosis" and c2b and "DiagnosisCodes" in dff.columns:
        dff_bs = assign_diagnosis_column(dff, c2b, mode=diag_mode)
        top_bs = dff_bs["_bs"].value_counts().head(8).index.tolist()
        for i, bs in enumerate(top_bs):
            subset = dff_bs[dff_bs["_bs"] == bs]
            counts = subset.groupby("period").size().reindex(all_periods, fill_value=0)
            series.append({
                "name": bs,
                "values": _trim_edges(counts.tolist()),
                "color": CHART_COLORWAY[i % len(CHART_COLORWAY)],
            })

    return {
        "dates": dates,
        "series": series,
        "height": 350,
        "yTitle": "Courses",
        "hideLegend": len(series) <= 1,
    }


# ---------------------------------------------------------------------------
# Data Preparation: Cumulative
# ---------------------------------------------------------------------------

def _prepare_cumulative_data(df_all, start, end, date_preset,
                              date_col, departments, physician, diagnosis_cats,
                              status, frac_range, c2b, inpatient=False,
                              techniques=None, date_mode="started",
                              mode="prior", period_type="calendar",
                              slice_by="site", max_prior=10,
                              diag_mode="primary", physician_role="treating"):
    """Prepare cumulative course volume data for overlay chart."""
    if df_all.empty or date_col not in df_all.columns:
        return None

    from utils.cumulative_current_year import setup_current_year_range, apply_current_year_projection
    today = pd.Timestamp.now().normalize()
    start, end, _cy_last_actual = setup_current_year_range(date_preset, mode, start, end)
    if _cy_last_actual is None and end.normalize() > today:
        end = today

    period_days = (end - start).days + 1
    if period_days < 2:
        return None

    # Force rolling when period exceeds 1 year (calendar shifts would overlap)
    if period_days > 365 and period_type == "calendar":
        period_type = "rolling"

    def _window_mask(df, w_start, w_end):
        """Return boolean mask for courses in the window, respecting date_mode."""
        if date_mode == "treated":
            # Overlap: FirstTreatmentDate <= w_end AND LastTreatmentDate >= w_start
            ft = df["FirstTreatmentDate"] if "FirstTreatmentDate" in df.columns else df[date_col]
            lt = df["LastTreatmentDate"].fillna(ft) if "LastTreatmentDate" in df.columns else ft
            return (ft <= w_end) & (lt >= w_start) & ft.notna()
        return (df[date_col] >= w_start) & (df[date_col] <= w_end)

    def _cumulative_for_window(df, w_start, w_end):
        sub = df.loc[_window_mask(df, w_start, w_end)]
        if sub.empty:
            return []
        # Clamp plot dates to window so overlap-matched courses whose
        # date_col falls before the window appear on day 1, not outside.
        plot_dates = sub[date_col].dt.normalize().clip(lower=w_start.normalize(),
                                                        upper=w_end.normalize())
        daily = plot_dates.groupby(plot_dates).size()
        idx = pd.date_range(w_start.normalize(), w_end.normalize(), freq="D")
        daily = daily.reindex(idx, fill_value=0)
        return daily.cumsum().tolist()

    def _slice_totals_for_window(df, w_start, w_end, sb):
        sub = df.loc[_window_mask(df, w_start, w_end)]
        if sub.empty:
            return {}
        if sb == "total":
            return {"Total": len(sub)}
        if sb == "site" and "Department" in sub.columns:
            return sub.groupby("Department", observed=True).size().to_dict()
        elif sb == "physician" and "TreatingPhysician" in sub.columns:
            counts = sub.groupby("TreatingPhysician", observed=True).size()
            return {(k.split(",")[0] if "," in k else k): v for k, v in counts.items()}
        elif sb == "diagnosis" and c2b and "DiagnosisCodes" in sub.columns:
            sub = sub.copy()
            if diag_mode == "all":
                sub["_bs_list"] = sub["DiagnosisCodes"].apply(
                    lambda v: list(get_categories_for_codes(v, c2b)) if pd.notna(v) else []
                )
                sub = sub.explode("_bs_list").rename(columns={"_bs_list": "_bs"})
            else:
                sub["_bs"] = sub["DiagnosisCodes"].apply(lambda v: primary_category(v, c2b))
            sub = sub[sub["_bs"] != "Unknown"]
            return sub.groupby("_bs").size().to_dict()
        return {}

    # Apply filters to full dataset
    dff_all = _apply_filters(df_all, departments, physician, diagnosis_cats, status, frac_range, c2b,
                             inpatient=inpatient, techniques=techniques, diag_mode=diag_mode,
                             physician_role=physician_role)

    n_days = period_days
    start_norm = start.normalize()
    day_indices = list(range(n_days))
    tick_positions, tick_labels = _build_day_index_ticks(start_norm, n_days)

    if dff_all.empty:
        current_vals = [0] * n_days
    else:
        current_vals = _cumulative_for_window(dff_all, start, end)

    data_min = dff_all[date_col].min() if not dff_all.empty else start

    def _period_label(p_start, p_end):
        same_year = p_start.year == p_end.year
        same_month = same_year and p_start.month == p_end.month
        if same_month:
            return p_start.strftime("%b %Y")
        if same_year:
            if date_preset in ("ytd", "last_year") or (p_start.month == 1 and p_end.month == 12):
                return str(p_start.year)
            return f"{p_start.strftime('%b')} – {p_end.strftime('%b %Y')}"
        fmt = "%b '%y"
        return f"{p_start.strftime(fmt)} – {p_end.strftime(fmt)}"

    windows = []
    if date_preset != "all":
        for i in range(1, max_prior + 1):
            if period_type == "calendar":
                try:
                    p_start = start - pd.DateOffset(years=i)
                    p_end = end - pd.DateOffset(years=i)
                except Exception:
                    continue
            else:
                shift = pd.Timedelta(days=period_days * i)
                p_start = start - shift
                p_end = end - shift
            if p_end < data_min:
                break
            windows.append((_period_label(p_start, p_end), p_start, p_end))

    prior = []
    last_prior_start = None
    for pi, (label, p_start, p_end) in enumerate(windows):
        vals = _cumulative_for_window(dff_all, p_start, p_end)
        if vals and any(v > 0 for v in vals):
            if len(vals) < n_days:
                vals = vals + [vals[-1] if vals else 0] * (n_days - len(vals))
            elif len(vals) > n_days:
                vals = vals[:n_days]
            prior.append({"label": label, "values": vals, "color": PRIOR_PERIOD_COLORS[min(pi, len(PRIOR_PERIOD_COLORS) - 1)]})
            last_prior_start = p_start

    # Metadata for client-side control updates
    has_partial = (last_prior_start is not None
                   and last_prior_start.normalize() < data_min.normalize())
    _prior_meta = {
        "periodDays": period_days,
        "maxAvailablePriors": len(prior),
        "hasPartialPrior": has_partial,
    }

    current_label = _period_label(start, end)
    if len(current_vals) < n_days:
        current_vals = current_vals + [None] * (n_days - len(current_vals))

    # Slice breakdown for bar mode
    all_windows = [(current_label, start, end)]
    for label, p_start, p_end in windows:
        all_windows.append((label, p_start, p_end))

    all_slice_totals = []
    all_slice_keys = set()
    for wlabel, ws, we in all_windows:
        totals = _slice_totals_for_window(dff_all, ws, we, slice_by)
        all_slice_totals.append((wlabel, totals))
        all_slice_keys.update(totals.keys())

    slice_keys_sorted = sorted(all_slice_keys)
    if slice_by == "site":
        slice_colors = {k: DEPARTMENT_COLORS.get(k, CHART_COLORWAY[i % len(CHART_COLORWAY)])
                       for i, k in enumerate(slice_keys_sorted)}
    else:
        slice_colors = {k: CHART_COLORWAY[i % len(CHART_COLORWAY)]
                       for i, k in enumerate(slice_keys_sorted)}

    breakdown_periods = [t[0] for t in reversed(all_slice_totals)]
    breakdown_slices = []
    for sk in slice_keys_sorted:
        vals = [t[1].get(sk, 0) for t in reversed(all_slice_totals)]
        breakdown_slices.append({"name": sk, "values": vals, "color": slice_colors[sk]})
    slice_breakdown = {"periods": breakdown_periods, "slices": breakdown_slices}

    if mode == "prior":
        _result = {
            "mode": "prior",
            "startDate": start_norm.isoformat(),
            "dayIndices": day_indices,
            "tickPositions": tick_positions,
            "tickLabels": tick_labels,
            "current": {
                "label": current_label,
                "values": current_vals,
                "color": PRIMARY,
                "endpoint": current_vals[-1] if current_vals and current_vals[-1] is not None else (
                    next((v for v in reversed(current_vals) if v is not None), 0)
                ),
            },
            "prior": prior,
            "sliceBreakdown": slice_breakdown,
            "height": 350,
            "yTitle": "Cumulative Courses",
            **_prior_meta,
        }
        if _cy_last_actual is not None:
            apply_current_year_projection(_result, _cy_last_actual, start)
        return _result

    else:  # mode == "slice"
        dff_period = dff_all.loc[_window_mask(dff_all, start, end)]
        dates_range = pd.date_range(start.normalize(), end.normalize(), freq="D")

        def _clamped_daily(sub):
            """Group by date_col clamped to the window."""
            plot_dates = sub[date_col].dt.normalize().clip(
                lower=start.normalize(), upper=end.normalize())
            return plot_dates.groupby(plot_dates).size()

        def _trimmed_cumsum(daily_counts):
            cumvals = daily_counts.cumsum().tolist()
            raw = daily_counts.tolist()
            first_idx = next((i for i, v in enumerate(raw) if v > 0), None)
            if first_idx is None:
                return [None] * len(cumvals)
            for i in range(first_idx):
                cumvals[i] = None
            last_idx = next((i for i in range(len(raw) - 1, -1, -1) if raw[i] > 0), first_idx)
            for i in range(last_idx + 1, len(cumvals)):
                cumvals[i] = cumvals[last_idx]
            return cumvals

        series = []

        if slice_by == "site" and "Department" in dff_period.columns:
            for dept in sorted(dff_period["Department"].dropna().unique()):
                sub = dff_period[dff_period["Department"] == dept]
                daily = _clamped_daily(sub).reindex(dates_range, fill_value=0)
                series.append({
                    "name": dept,
                    "values": _trimmed_cumsum(daily),
                    "color": DEPARTMENT_COLORS.get(dept, CHART_COLORWAY[0]),
                })

        elif slice_by == "physician" and "TreatingPhysician" in dff_period.columns:
            for i, phys in enumerate(sorted(dff_period["TreatingPhysician"].dropna().unique())):
                sub = dff_period[dff_period["TreatingPhysician"] == phys]
                daily = _clamped_daily(sub).reindex(dates_range, fill_value=0)
                series.append({
                    "name": phys.split(",")[0] if "," in phys else phys,
                    "values": _trimmed_cumsum(daily),
                    "color": CHART_COLORWAY[i % len(CHART_COLORWAY)],
                })

        elif slice_by == "diagnosis" and c2b and "DiagnosisCodes" in dff_period.columns:
            dff_p = assign_diagnosis_column(dff_period, c2b, mode=diag_mode)
            top = dff_p["_bs"].value_counts().head(8).index.tolist()
            for i, bs in enumerate(top):
                sub = dff_p[dff_p["_bs"] == bs]
                daily = _clamped_daily(sub).reindex(dates_range, fill_value=0)
                series.append({
                    "name": bs,
                    "values": _trimmed_cumsum(daily),
                    "color": CHART_COLORWAY[i % len(CHART_COLORWAY)],
                })

        dates_iso = [d.isoformat() for d in dates_range]
        return {
            "mode": "slice",
            "dates": dates_iso,
            "series": series,
            "sliceBreakdown": slice_breakdown,
            "height": 350,
            "yTitle": "Cumulative Courses",
            **_prior_meta,
        }


# ---------------------------------------------------------------------------
# Effective completion logic
# ---------------------------------------------------------------------------

_INACTIVITY_THRESHOLD_DAYS = 90


def _apply_grid_row_filter(dff, grid_rows):
    """Filter dff to only rows matching the grid's visible row indices."""
    if grid_rows is None or dff is None or dff.empty:
        return dff
    idx_set = set(int(i) for i in grid_rows)
    return dff.loc[dff.index.isin(idx_set)].reset_index(drop=True)


def _is_effectively_completed(df):
    """Return a boolean Series: True if a course is effectively completed.

    A course is considered completed if ANY of:
      1. ClinicalStatus == "COMPLETED"
      2. CourseSessionsDelivered >= CourseSessionsPlanned (raw DB session counts)
         Falls back to FractionsDelivered >= FractionsPrescribed if session cols missing
      3. LastDayActivityFlag is truthy (Yes/1/True)
      4. DCActivityFlag is truthy (Yes/1/True)
      5. No treatment activity in the last 90 days (inactivity timeout)
    """
    mask = pd.Series(False, index=df.index)

    if "ClinicalStatus" in df.columns:
        mask = mask | (df["ClinicalStatus"] == "COMPLETED")

    # Sessions delivered >= planned (preferred — raw DB counts)
    if "CourseSessionsDelivered" in df.columns and "CourseSessionsPlanned" in df.columns:
        sd = pd.to_numeric(df["CourseSessionsDelivered"], errors="coerce")
        sp = pd.to_numeric(df["CourseSessionsPlanned"], errors="coerce")
        mask = mask | ((sd >= sp) & sp.notna() & (sp > 0) & sd.notna())
    elif "FractionsDelivered" in df.columns and "FractionsPrescribed" in df.columns:
        # Fallback for older data without session columns
        fd = pd.to_numeric(df["FractionsDelivered"], errors="coerce")
        fp = pd.to_numeric(df["FractionsPrescribed"], errors="coerce")
        mask = mask | ((fd >= fp) & fp.notna() & (fp > 0) & fd.notna())

    # LastDayActivityFlag
    if "LastDayActivityFlag" in df.columns:
        ld = df["LastDayActivityFlag"].astype(str).str.strip().str.lower()
        mask = mask | ld.isin({"yes", "1", "true"})

    # DCActivityFlag
    if "DCActivityFlag" in df.columns:
        dc = df["DCActivityFlag"].astype(str).str.strip().str.lower()
        mask = mask | dc.isin({"yes", "1", "true"})

    # Inactivity timeout — no treatment in 90 days
    if "LastTreatmentDate" in df.columns:
        today = pd.Timestamp.now().normalize()
        days_since = (today - df["LastTreatmentDate"]).dt.days
        mask = mask | (days_since > _INACTIVITY_THRESHOLD_DAYS)

    return mask


# ---------------------------------------------------------------------------
# Filter application
# ---------------------------------------------------------------------------

def _apply_filters(df, departments, physician, diagnosis_cats, status, frac_range, c2b,
                   inpatient=False, techniques=None, diag_mode="primary",
                   physician_role="treating"):
    """Apply dimension filters (not date) to a dataframe."""
    from utils.diagnosis_categories import filter_by_diagnosis

    if df.empty:
        return df

    if departments and "Department" in df.columns:
        df = df[df["Department"].isin(departments)]

    if physician:
        phys_col = "ConsultPhysician" if physician_role == "consult" else "TreatingPhysician"
        if phys_col in df.columns:
            df = df[df[phys_col] == physician]

    if diagnosis_cats:
        df = filter_by_diagnosis(df, diagnosis_cats, c2b, mode=diag_mode)

    if techniques and "TreatmentTechniques" in df.columns:
        tech_set = set(techniques)
        df = df[df["TreatmentTechniques"].apply(
            lambda v: bool({t.strip() for t in str(v).split(",")} & tech_set) if pd.notna(v) else False
        )]

    if status and status != "all":
        if status == "COMPLETED":
            df = df[_is_effectively_completed(df)]
        elif status == "ACTIVE":
            df = df[~_is_effectively_completed(df)]

    if inpatient and "InPatientFlag" in df.columns:
        ip = df["InPatientFlag"].astype(str).str.strip().str.lower()
        df = df[ip.isin({"yes", "1", "true"})]

    if frac_range and "FractionsPrescribed" in df.columns:
        fmin, fmax = frac_range
        vals = df["FractionsPrescribed"]
        df = df[(vals >= fmin) | vals.isna()]
        vals2 = df["FractionsPrescribed"]
        df = df[(vals2 <= fmax) | vals2.isna()]

    return df


# ---------------------------------------------------------------------------
# Module-level helpers (extracted from monolithic callback)
# ---------------------------------------------------------------------------

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


def _trend(curr, prior, invert=False):
    if prior is None or prior == 0:
        return None, None
    pct = (curr - prior) / abs(prior) * 100
    direction = ("down" if pct > 0 else "up") if invert else ("up" if pct > 0 else "down")
    return f"{abs(pct):.0f}%", direction


# ---------------------------------------------------------------------------
# Shared filter loading
# ---------------------------------------------------------------------------

def _load_and_filter_courses(slider_val, departments, physician, diagnosis_cats,
                              diag_mode, techniques, status, frac_range, date_mode,
                              date_preset, inpatient, frac_engaged,
                              physician_role="treating"):
    """Load courses data, apply filters. Returns dict with shared frames or None."""
    from data.loader import load_courses

    try:
        df = load_courses().copy()
    except Exception:
        return None

    if df.empty:
        return None

    c2b = _build_diag_lookup()

    date_col = _date_col_for_mode(date_mode)
    if date_col not in df.columns or df[date_col].notna().sum() == 0:
        date_col = "CourseStartDate"

    if date_mode == "completed":
        df = df[_is_effectively_completed(df)]

    # Fraction slider range (before date filter so range stays stable)
    frac_min_data = 0
    frac_max_data = 50
    if "FractionsPrescribed" in df.columns:
        fvals = df["FractionsPrescribed"].dropna()
        if not fvals.empty:
            frac_min_data = int(fvals.min())
            frac_max_data = int(fvals.max())

    start, end = _get_date_range(slider_val, None)
    df_all = df.copy()

    # Date filter
    if date_mode == "treated":
        ft = "FirstTreatmentDate"
        lt = "LastTreatmentDate"
        if ft in df.columns and lt in df.columns:
            df = df[df[ft].notna()]
            last = df[lt].fillna(df[ft])
            df = df[(df[ft] <= end) & (last >= start)]
    elif date_col in df.columns:
        df = df[df[date_col].notna()]
        df = df[(df[date_col] >= start) & (df[date_col] <= end)]

    if df.empty:
        return None

    active_frac_range = frac_range if frac_engaged else None

    diag_mode = diag_mode or "primary"
    dff = _apply_filters(df, departments, physician, diagnosis_cats, status, active_frac_range, c2b,
                         inpatient=inpatient, techniques=techniques, diag_mode=diag_mode,
                         physician_role=physician_role)

    if dff.empty:
        return None

    # Prior period
    trend_label = None
    prior_start = prior_end = None
    dff_prior = pd.DataFrame()
    if date_preset and date_preset in _PRIOR_MAP and date_col in df_all.columns:
        trend_label, prior_fn = _PRIOR_MAP[date_preset]
        prior_start, prior_end = prior_fn(start, end)
        if date_mode == "treated":
            ft_col = "FirstTreatmentDate"
            lt_col = "LastTreatmentDate"
            if ft_col in df_all.columns and lt_col in df_all.columns:
                df_prior = df_all[df_all[ft_col].notna()]
                lt_prior = df_prior[lt_col].fillna(df_prior[ft_col])
                df_prior = df_prior[(df_prior[ft_col] <= prior_end) & (lt_prior >= prior_start)]
            else:
                df_prior = pd.DataFrame()
        elif date_mode == "completed":
            df_prior = df_all[df_all[date_col].notna()]
            df_prior = df_prior[(df_prior[date_col] >= prior_start) & (df_prior[date_col] <= prior_end)]
        else:
            df_prior = df_all[df_all[date_col].notna()]
            df_prior = df_prior[(df_prior[date_col] >= prior_start) & (df_prior[date_col] <= prior_end)]
        dff_prior = _apply_filters(df_prior, departments, physician, diagnosis_cats, status, active_frac_range, c2b,
                                   inpatient=inpatient, techniques=techniques, diag_mode=diag_mode,
                                   physician_role=physician_role)

    dff_all_no_date = _apply_filters(df_all, departments, physician, diagnosis_cats, "all", active_frac_range, c2b,
                                     inpatient=inpatient, techniques=techniques, diag_mode=diag_mode,
                                     physician_role=physician_role)

    return {
        "df": df, "df_all": df_all, "dff": dff,
        "dff_prior": dff_prior, "dff_all_no_date": dff_all_no_date,
        "c2b": c2b, "date_col": date_col, "date_mode": date_mode,
        "start": start, "end": end, "date_preset": date_preset,
        "departments": departments, "physician": physician,
        "diagnosis_cats": diagnosis_cats, "techniques": techniques,
        "status": status, "active_frac_range": active_frac_range,
        "inpatient": inpatient, "diag_mode": diag_mode, "physician_role": physician_role,
        "trend_label": trend_label, "prior_start": prior_start, "prior_end": prior_end,
        "frac_min_data": frac_min_data, "frac_max_data": frac_max_data,
    }


# Common filter inputs shared by all split callbacks
_COURSES_FILTER_INPUTS = [
    Input("courses-interval", "n_intervals"),
    Input("courses-date-slider", "value"),
    Input("courses-filter-department", "value"),
    Input("courses-filter-physician", "value"),
    Input("courses-diag-store", "data"),
    Input("courses-diag-mode", "data"),
    Input("courses-filter-technique", "value"),
    Input("courses-filter-status", "value"),
    Input("courses-fraction-slider", "value"),
    Input("courses-date-mode", "value"),
    Input("courses-inpatient-switch", "checked"),
    Input("courses-physician-role", "value"),
]

# States listed separately so they always land at the END of args,
# regardless of how many extra Inputs a callback appends after
# *_COURSES_FILTER_INPUTS.  Preset is State (slider is the true
# trigger; preset cascades through it).
_COURSES_FILTER_STATES = [
    State("courses-filter-date-preset", "value"),
    State("courses-fraction-engaged", "data"),
]


def _unpack_courses_filter_args(args, n_extra_inputs=0):
    """Unpack common filter args into kwargs for _load_and_filter_courses.

    Dash delivers all Inputs first, then all States.  The 12 Inputs from
    _COURSES_FILTER_INPUTS come first, then any extra per-callback Inputs
    (n_extra_inputs), then the 2 States from _COURSES_FILTER_STATES.
    """
    n_inputs = 12 + n_extra_inputs
    (_n, slider_val, departments, physician, diagnosis_cats, diag_mode, techniques,
     status, frac_range, date_mode, inpatient, physician_role) = args[:12]
    date_preset = args[n_inputs]
    frac_engaged = args[n_inputs + 1]
    return dict(
        slider_val=slider_val, departments=departments, physician=physician,
        diagnosis_cats=diagnosis_cats, diag_mode=diag_mode, techniques=techniques,
        status=status, frac_range=frac_range, date_mode=date_mode,
        date_preset=date_preset, inpatient=inpatient, frac_engaged=frac_engaged,
        physician_role=physician_role or "treating",
    )


# ---------------------------------------------------------------------------
# Callback 1: KPIs + Sparklines + Detail Table + Charts container + Fraction slider
# ---------------------------------------------------------------------------

@callback(
    Output("courses-kpi-active", "children"),
    Output("courses-kpi-started", "children"),
    Output("courses-kpi-completed", "children"),
    Output("courses-kpi-median-fractions", "children"),
    Output("courses-kpi-median-duration", "children"),
    Output("courses-kpi-multiplan", "children"),
    Output("courses-store-kpi-sparklines", "data"),
    Output("courses-store-ridgeline", "data"),
    Output("courses-store-frac-trend", "data"),
    Output("courses-store-frac-dist", "data"),
    Output("courses-store-complexity-trends", "data"),
    Output("courses-store-technique-dist", "data"),
    Output("courses-store-quit-trend", "data"),
    Output("courses-store-interruption", "data"),
    Output("courses-charts", "children"),
    Output("courses-detail-grid", "rowData"),
    Output("courses-detail-grid", "columnDefs"),
    Output("courses-fraction-slider", "min"),
    Output("courses-fraction-slider", "max"),
    *_COURSES_FILTER_INPUTS,
    Input("courses-table-filter-rows", "data"),
    *_COURSES_FILTER_STATES,
)
def _update_courses_kpis(*args):
    ctx = _unpack_courses_filter_args(args, n_extra_inputs=1)
    grid_rows = args[12]  # right after 12 filter Inputs
    data = _load_and_filter_courses(**ctx)

    na_kpi = kpi_card("--", "N/A")
    empty_kpis = (na_kpi,) * 6 + ({}, None, None, None, None, None, None, [], [], 0, 50)

    if data is None:
        return empty_kpis

    # Check if triggered by grid filter — skip table/chart-children rebuild
    triggered_by_grid = (
        dash.callback_context.triggered
        and len(dash.callback_context.triggered) == 1
        and dash.callback_context.triggered[0]["prop_id"] == "courses-table-filter-rows.data"
    )

    dff_full = data["dff"]
    dff = _apply_grid_row_filter(dff_full, grid_rows)
    dff_prior = data["dff_prior"]
    dff_all_no_date = data["dff_all_no_date"]
    date_col = data["date_col"]
    date_mode = data["date_mode"]
    start, end = data["start"], data["end"]
    date_preset = data["date_preset"]
    trend_label = data["trend_label"]
    prior_start = data["prior_start"]
    prior_end = data["prior_end"]
    c2b = data["c2b"]
    frac_min_data = data["frac_min_data"]
    frac_max_data = data["frac_max_data"]

    # ------------------------------------------------------------------
    # Sparkline data
    # ------------------------------------------------------------------
    sparkline_data = {}
    range_months = (end.year - start.year) * 12 + (end.month - start.month) + 1
    _spark_period = "D" if range_months <= 3 else "W"

    def _build_count_sparkline(sub_df, key, color, use_col=None):
        col = use_col or date_col
        if col not in sub_df.columns or sub_df.empty:
            return
        temp = sub_df[sub_df[col].notna()].copy()
        if temp.empty:
            return
        plot_dates = temp[col].clip(lower=start, upper=end)
        if _spark_period == "D":
            temp["_sp"] = plot_dates.dt.normalize()
        else:
            temp["_sp"] = plot_dates.dt.to_period("W").dt.to_timestamp()
        grp = temp.groupby("_sp").size()
        if len(grp) > 2:
            sparkline_data[key] = {
                "labels": [d.isoformat() for d in grp.index],
                "values": grp.tolist(),
                "color": color,
            }

    def _build_median_sparkline(sub_df, val_col, key, color, hover_fmt=None):
        if val_col not in sub_df.columns or date_col not in sub_df.columns or sub_df.empty:
            return
        temp = sub_df[[date_col, val_col]].copy()
        temp["val"] = pd.to_numeric(temp[val_col], errors="coerce")
        temp = temp.dropna(subset=["val"])
        if temp.empty:
            return
        plot_dates = temp[date_col].clip(lower=start, upper=end)
        if _spark_period == "D":
            temp["_sp"] = plot_dates.dt.normalize()
        else:
            temp["_sp"] = plot_dates.dt.to_period("W").dt.to_timestamp()
        grp = temp.groupby("_sp")["val"].median()
        if len(grp) > 2:
            sparkline_data[key] = {
                "labels": [d.isoformat() for d in grp.index],
                "values": grp.tolist(),
                "color": color,
                "hover_fmt": hover_fmt or "%{x|%b %d}: %{customdata:,.1f}<extra></extra>",
            }

    # Active census sparkline
    if "FirstTreatmentDate" in dff_all_no_date.columns and "LastTreatmentDate" in dff_all_no_date.columns:
        _adf = dff_all_no_date[dff_all_no_date["FirstTreatmentDate"].notna()].copy()
        _adf["_lt"] = _adf["LastTreatmentDate"].fillna(_adf["FirstTreatmentDate"])
        _last_data_date = _adf["_lt"].dt.normalize().max()
        _spark_end = min(end, _last_data_date) if pd.notna(_last_data_date) else end
        if _spark_period == "D":
            sp_dates = pd.date_range(start, _spark_end, freq="D")
        else:
            sp_dates = pd.date_range(start, _spark_end, freq="W-MON")
        if len(sp_dates) > 2:
            ft_vals = _adf["FirstTreatmentDate"].values
            lt_vals = _adf["_lt"].values
            active_counts = []
            for d in sp_dates:
                d_np = d.to_numpy()
                active_counts.append(int(((ft_vals <= d_np) & (lt_vals >= d_np)).sum()))
            sparkline_data["active"] = {
                "labels": [d.isoformat() for d in sp_dates],
                "values": active_counts,
                "color": STATUS_COLORS["ACTIVE"],
            }

    # Started sparkline
    if "FirstTreatmentDate" in dff.columns:
        started_df = dff[(dff["FirstTreatmentDate"] >= start) & (dff["FirstTreatmentDate"] <= end)]
        _build_count_sparkline(started_df, "started", CHART_COLORWAY[0], use_col="FirstTreatmentDate")

    # Completed sparkline
    eff_completed = _is_effectively_completed(dff)
    completed_df = dff[eff_completed]
    _build_count_sparkline(completed_df, "completed", STATUS_COLORS["COMPLETED"])

    # Median fractions sparkline
    _build_median_sparkline(dff, "FractionsPrescribed", "fractions", CHART_COLORWAY[5])

    # Median duration sparkline (completed only)
    _build_median_sparkline(completed_df, "TreatmentDurationDays", "duration", CHART_COLORWAY[4],
                            hover_fmt="%{x|%b %d}: %{customdata:,.0f} days<extra></extra>")

    # Multi-plan sparkline (% per period)
    if "PlanCount" in dff.columns and date_col in dff.columns:
        temp = dff[dff[date_col].notna()].copy()
        temp["_pc"] = pd.to_numeric(temp["PlanCount"], errors="coerce")
        temp["_multi"] = (temp["_pc"] > 1).astype(int)
        plot_dates = temp[date_col].clip(lower=start, upper=end)
        if _spark_period == "D":
            temp["_sp"] = plot_dates.dt.normalize()
        else:
            temp["_sp"] = plot_dates.dt.to_period("W").dt.to_timestamp()
        grp = temp.groupby("_sp")["_multi"]
        pct = (grp.sum() / grp.count() * 100)
        if len(pct) > 2:
            sparkline_data["multiplan"] = {
                "labels": [d.isoformat() for d in pct.index],
                "values": [round(v, 1) for v in pct.tolist()],
                "color": CHART_COLORWAY[6],
                "hover_fmt": "%{x|%b %d}: %{customdata:.0f}%<extra></extra>",
            }

    # ------------------------------------------------------------------
    # KPIs with trends
    # ------------------------------------------------------------------

    # 1. Active Courses
    eff_completed_all = _is_effectively_completed(dff_all_no_date)
    active_count = int((~eff_completed_all).sum())

    _t_active = (None, None)
    if trend_label and "FirstTreatmentDate" in dff_all_no_date.columns:
        _ft = dff_all_no_date["FirstTreatmentDate"]
        _lt = dff_all_no_date["LastTreatmentDate"].fillna(_ft)
        prior_active = int(((_ft <= prior_end) & (_lt >= prior_end)).sum())
        if prior_active > 0:
            _t_active = _trend(active_count, prior_active)

    kpi_active = kpi_card(
        "Currently Active", f"{active_count:,}",
        accent_color=STATUS_COLORS["ACTIVE"],
        sparkline_id="courses-spark-active",
        trend_text=f"{_t_active[0]} {trend_label}" if _t_active[0] else None,
        trend_direction=_t_active[1],
    )

    # 2. Started (in period)
    if "FirstTreatmentDate" in dff.columns:
        started_count = int(
            ((dff["FirstTreatmentDate"] >= start) & (dff["FirstTreatmentDate"] <= end)).sum()
        )
    else:
        started_count = len(dff)
    _t_started = (None, None)
    if trend_label and not dff_prior.empty and "FirstTreatmentDate" in dff_prior.columns:
        prior_started = int(
            ((dff_prior["FirstTreatmentDate"] >= prior_start) & (dff_prior["FirstTreatmentDate"] <= prior_end)).sum()
        )
        _t_started = _trend(started_count, prior_started)
    kpi_started = kpi_card(
        "Started", f"{started_count:,}",
        accent_color=CHART_COLORWAY[0],
        sparkline_id="courses-spark-started",
        trend_text=f"{_t_started[0]} {trend_label}" if _t_started[0] else None,
        trend_direction=_t_started[1],
    )

    # 3. Completed (in period)
    completed_count = int(eff_completed.sum())
    _t_completed = (None, None)
    if trend_label and not dff_prior.empty:
        prior_completed = int(_is_effectively_completed(dff_prior).sum())
        _t_completed = _trend(completed_count, prior_completed)
    kpi_completed = kpi_card(
        "Completed", f"{completed_count:,}",
        accent_color=STATUS_COLORS["COMPLETED"],
        sparkline_id="courses-spark-completed",
        trend_text=f"{_t_completed[0]} {trend_label}" if _t_completed[0] else None,
        trend_direction=_t_completed[1],
    )

    # 4. Median Fractions
    median_frac_val = None
    if not dff.empty:
        frac_series = []
        if "FractionsDelivered" in completed_df.columns and not completed_df.empty:
            frac_series.append(pd.to_numeric(completed_df["FractionsDelivered"], errors="coerce"))
        active_df = dff[~eff_completed]
        if "FractionsPrescribed" in active_df.columns and not active_df.empty:
            frac_series.append(pd.to_numeric(active_df["FractionsPrescribed"], errors="coerce"))
        if frac_series:
            all_frac = pd.concat(frac_series).dropna()
            median_frac_val = all_frac.median() if not all_frac.empty else None
    _t_frac = (None, None)
    if trend_label and not dff_prior.empty and median_frac_val is not None:
        prior_eff = _is_effectively_completed(dff_prior)
        prior_frac_parts = []
        prior_comp_df = dff_prior[prior_eff]
        prior_act_df = dff_prior[~prior_eff]
        if "FractionsDelivered" in prior_comp_df.columns and not prior_comp_df.empty:
            prior_frac_parts.append(pd.to_numeric(prior_comp_df["FractionsDelivered"], errors="coerce"))
        if "FractionsPrescribed" in prior_act_df.columns and not prior_act_df.empty:
            prior_frac_parts.append(pd.to_numeric(prior_act_df["FractionsPrescribed"], errors="coerce"))
        if prior_frac_parts:
            prior_all_frac = pd.concat(prior_frac_parts).dropna()
            if not prior_all_frac.empty:
                _t_frac = _trend(median_frac_val, prior_all_frac.median())
    kpi_median_frac = kpi_card(
        "Median Fractions", f"{median_frac_val:.0f}" if median_frac_val is not None else "N/A",
        accent_color=CHART_COLORWAY[5],
        sparkline_id="courses-spark-fractions",
        trend_text=f"{_t_frac[0]} {trend_label}" if _t_frac[0] else None,
        trend_direction=_t_frac[1],
    )

    # 5. Median Duration (completed courses only)
    median_dur_val = None
    if "TreatmentDurationDays" in completed_df.columns and not completed_df.empty:
        dur_vals = completed_df["TreatmentDurationDays"].dropna()
        median_dur_val = dur_vals.median() if not dur_vals.empty else None
    _t_dur = (None, None)
    if trend_label and not dff_prior.empty and median_dur_val is not None:
        prior_comp = dff_prior[_is_effectively_completed(dff_prior)]
        if "TreatmentDurationDays" in prior_comp.columns and not prior_comp.empty:
            prior_dur = prior_comp["TreatmentDurationDays"].dropna()
            if not prior_dur.empty:
                _t_dur = _trend(median_dur_val, prior_dur.median(), invert=True)
    _dur_info = dmc.Tooltip(
        DashIconify(icon="mdi:information-outline", width=16, color="#9CA3AF", style={"cursor": "help"}),
        label="Completed courses only. Calendar days from first to last treatment.",
        position="top", withArrow=True, multiline=True, w=240,
    )
    kpi_median_dur = kpi_card(
        "Median Duration", f"{median_dur_val:.0f}" if median_dur_val is not None else "N/A",
        value_detail="days",
        accent_color=CHART_COLORWAY[4],
        sparkline_id="courses-spark-duration",
        trend_text=f"{_t_dur[0]} {trend_label}" if _t_dur[0] else None,
        trend_direction=_t_dur[1],
        header_control=_dur_info,
    )

    # 6. Multi-Plan Courses (%)
    multiplan_pct = None
    multiplan_count = 0
    if "PlanCount" in dff.columns and not dff.empty:
        plan_counts = pd.to_numeric(dff["PlanCount"], errors="coerce")
        multiplan_count = int((plan_counts > 1).sum())
        multiplan_pct = multiplan_count / len(dff) * 100 if len(dff) > 0 else 0
    _t_mp = (None, None)
    if trend_label and not dff_prior.empty and "PlanCount" in dff_prior.columns and multiplan_pct is not None:
        prior_pc = pd.to_numeric(dff_prior["PlanCount"], errors="coerce")
        prior_mp_pct = (prior_pc > 1).sum() / len(dff_prior) * 100 if len(dff_prior) > 0 else 0
        _t_mp = _trend(multiplan_pct, prior_mp_pct)
    kpi_multiplan = kpi_card(
        "Multi-Plan Courses", f"{multiplan_pct:.0f}%" if multiplan_pct is not None else "N/A",
        value_detail=f"({multiplan_count:,})",
        accent_color=CHART_COLORWAY[6],
        sparkline_id="courses-spark-multiplan",
        trend_text=f"{_t_mp[0]} {trend_label}" if _t_mp[0] else None,
        trend_direction=_t_mp[1],
    )

    # ------------------------------------------------------------------
    # Store data for charts rendered by other callbacks
    # ------------------------------------------------------------------
    ridgeline_data = _prepare_ridgeline_data(dff_all_no_date, date_col)
    _dm = data.get("diag_mode", "primary")
    frac_trend_data = _prepare_frac_trend_data(dff, date_col, c2b, start=start, end=end, diag_mode=_dm)
    frac_dist_data = _prepare_frac_dist_data(dff)
    quit_trend_data = _prepare_quit_trend_data(completed_df, "LastTreatmentDate", c2b, start=start, end=end, diag_mode=_dm)
    interruption_data = _prepare_interruption_data(completed_df)

    # Build iso_map: max UniqueIsocenters per (PatientId, CourseId) from Treatment Detail
    iso_map = None
    try:
        from data.loader import load_treatment_detail
        td = load_treatment_detail()
        if not td.empty and "UniqueIsocenters" in td.columns and "CourseName" in td.columns:
            # Don't write _isos onto the cached frame — compute the iso column
            # locally so the shared TTL-cached DataFrame stays clean.
            isos = pd.to_numeric(td["UniqueIsocenters"], errors="coerce")
            iso_map = isos.groupby([td["PatientId"], td["CourseName"]]).max()
            iso_map.index.names = ["PatientId", "CourseId"]
    except Exception:
        pass
    complexity_trend_data = _prepare_complexity_trend_data(
        dff, date_col, start=start, end=end, iso_map=iso_map,
    )
    technique_dist_data = _prepare_technique_dist_data(dff, date_col, start=start, end=end, date_mode=date_mode)

    # ------------------------------------------------------------------
    # Remaining Charts (server-side layout)
    # ------------------------------------------------------------------
    chart_children = []

    # --- Row 2: Ridgeline + Technique Mix -------
    row2_charts = []

    row2_charts.append(
        dmc.GridCol(
            span={"base": 12, "md": 6},
            children=dmc.Paper(
                children=[
                    dmc.Group(
                        justify="space-between",
                        align="center",
                        children=[
                            dmc.Text("Fractions per Course by Year", size="sm", fw=500, c="#6B7280"),
                            dmc.Group(
                                gap="sm", align="center",
                                children=[
                                    dmc.SegmentedControl(
                                        id="courses-ridge-mode",
                                        data=[
                                            {"value": "density", "label": "Density"},
                                            {"value": "histogram", "label": "Histogram"},
                                        ],
                                        value="density",
                                        size="xs",
                                    ),
                                    chart_settings_popover(
                                        "courses-ridgeline",
                                        chart_types=None,
                                        show_smooth=False,
                                        extra_settings=[
                                            html.Div(
                                                id="courses-ridge-bw-group",
                                                children=dmc.Stack(
                                                    gap=4,
                                                    children=[
                                                        dmc.Text("Density Smoothing", size="xs", fw=500, c="#6B7280"),
                                                        dmc.Slider(
                                                            id="courses-ridge-bw",
                                                            min=0.05,
                                                            max=1.0,
                                                            step=0.05,
                                                            value=0.1,
                                                            size="xs",
                                                            color="violet",
                                                            showLabelOnHover=True,
                                                            updatemode="drag",
                                                        ),
                                                    ],
                                                ),
                                            ),
                                        ],
                                    ),
                                ],
                            ),
                        ],
                        mb="sm",
                    ),
                    dcc.Graph(id="courses-chart-ridgeline", config={"displayModeBar": False},
                              style={"height": "720px"}),
                ],
                p="sm", radius="md", shadow="xs", withBorder=True,
            ),
        ),
    )

    # Right column: Median Fractions Trend (top) + Fractions Distribution (bottom)
    row2_charts.append(
        dmc.GridCol(
            span={"base": 12, "md": 6},
            children=dmc.Stack(
                gap=16,
                style={"height": "100%"},
                children=[
                    # Top: Median Fractions Trend
                    dmc.Paper(
                        children=[
                            dmc.Group(
                                justify="space-between", align="center", mb="sm",
                                children=[
                                    dmc.Group(
                                        gap="sm", align="center",
                                        children=[
                                            dmc.Text("Median Fractions Trend", size="sm", fw=500, c="#6B7280"),
                                            dmc.SegmentedControl(
                                                id="courses-frac-trend-slice",
                                                data=[
                                                    {"value": "", "label": "Total"},
                                                    {"value": "physician", "label": "MD"},
                                                    {"value": "site", "label": "Site"},
                                                    {"value": "diagnosis", "label": "Dx"},
                                                ],
                                                value="",
                                                size="xs",
                                            ),
                                        ],
                                    ),
                                    dmc.Group(
                                        gap="sm", align="center",
                                        children=[
                                            dmc.SegmentedControl(
                                                id="courses-frac-trend-agg",
                                                data=[
                                                    {"value": "W", "label": "Weekly"},
                                                    {"value": "M", "label": "Monthly"},
                                                    {"value": "Y", "label": "Yearly"},
                                                ],
                                                value="W",
                                                size="xs",
                                            ),
                                            chart_settings_popover(
                                                "courses-frac-trend",
                                                chart_types=[
                                                    {"value": "line", "label": "Line"},
                                                    {"value": "area", "label": "Area"},
                                                    {"value": "bar", "label": "Bar"},
                                                ],
                                                chart_type_default="area",
                                                show_smooth=True,
                                                smooth_max=12,
                                                smooth_default=1,
                                            ),
                                        ],
                                    ),
                                ],
                            ),
                            dcc.Graph(
                                id="courses-chart-frac-trend",
                                config={"displayModeBar": False},
                                style={"flex": "1", "minHeight": 0},
                            ),
                        ],
                        p="sm", radius="md", shadow="xs", withBorder=True,
                        style={"flex": "1 1 0", "display": "flex", "flexDirection": "column"},
                    ),
                    # Bottom: Fractions Distribution (histogram/density)
                    dmc.Paper(
                        children=[
                            dmc.Group(
                                justify="space-between", align="center", mb="sm",
                                children=[
                                    dmc.Text("Fractions Distribution", size="sm", fw=500, c="#6B7280"),
                                    dmc.Group(
                                        gap="sm", align="center",
                                        children=[
                                            dmc.SegmentedControl(
                                                id="courses-frac-dist-mode",
                                                data=[
                                                    {"value": "histogram", "label": "Histogram"},
                                                    {"value": "density", "label": "Density"},
                                                ],
                                                value="histogram",
                                                size="xs",
                                            ),
                                            chart_settings_popover(
                                                "courses-frac-dist",
                                                chart_types=None,
                                                show_smooth=False,
                                                extra_settings=[
                                                    html.Div(
                                                        id="courses-frac-dist-bw-group",
                                                        children=dmc.Stack(
                                                            gap=4,
                                                            children=[
                                                                dmc.Text("Density Smoothing", size="xs", fw=500, c="#6B7280"),
                                                                dmc.Slider(
                                                                    id="courses-frac-dist-bw",
                                                                    min=0.05,
                                                                    max=1.0,
                                                                    step=0.05,
                                                                    value=0.15,
                                                                    size="xs",
                                                                    color="violet",
                                                                    showLabelOnHover=True,
                                                                    updatemode="drag",
                                                                ),
                                                            ],
                                                        ),
                                                    ),
                                                ],
                                            ),
                                        ],
                                    ),
                                ],
                            ),
                            dcc.Graph(
                                id="courses-chart-frac-dist",
                                config={"displayModeBar": False},
                                style={"flex": "1", "minHeight": 0},
                            ),
                        ],
                        p="sm", radius="md", shadow="xs", withBorder=True,
                        style={"flex": "1 1 0", "display": "flex", "flexDirection": "column"},
                    ),
                ],
            ),
        ),
    )

    chart_children.append(dmc.Grid(gutter=16, align="stretch", children=row2_charts))

    # --- Technique Distribution (full-width stacked area) ---
    chart_children.append(
        chart_card(
            "courses-chart-technique-dist",
            "Technique Distribution",
            settings_id="courses-technique-dist",
            chart_types=[
                {"value": "line", "label": "Line"},
                {"value": "area", "label": "Area"},
                {"value": "bar", "label": "Bar"},
            ],
            chart_type_default="area",
            show_smooth=True,
            smooth_max=24,
            smooth_default=3,
            paper_padding="md",
            paper_height="500px",
            graph_height="420px",
            extra_controls_left=[
                dmc.SegmentedControl(
                    id="courses-technique-dist-counting",
                    data=[
                        {"value": "primary", "label": "Primary"},
                        {"value": "any", "label": "Any"},
                    ],
                    value="primary",
                    size="xs",
                ),
                dmc.SegmentedControl(
                    id="courses-technique-dist-mode",
                    data=[
                        {"value": "count", "label": "Count"},
                        {"value": "pct", "label": "%"},
                    ],
                    value="count",
                    size="xs",
                ),
            ],
            extra_controls=[
                dmc.SegmentedControl(
                    id="courses-technique-dist-agg",
                    data=[
                        {"value": "W", "label": "Weekly"},
                        {"value": "M", "label": "Monthly"},
                        {"value": "Y", "label": "Yearly"},
                    ],
                    value="W",
                    size="xs",
                ),
            ],
        )
    )

    # --- Course Complexity Trends (2x2 facets) ---
    chart_children.append(
        chart_card(
            "courses-chart-complexity",
            "Course Complexity Trends",
            settings_id="courses-complexity",
            chart_types=[
                {"value": "line", "label": "Line"},
                {"value": "area", "label": "Area"},
                {"value": "bar", "label": "Bar"},
            ],
            chart_type_default="area",
            show_grouping=False,
            show_smooth=True,
            smooth_max=12,
            smooth_default=4,
            paper_padding="md",
            paper_height="620px",
            graph_height="560px",
            extra_controls_left=[
                dmc.SegmentedControl(
                    id="courses-complexity-mode",
                    data=[
                        {"value": "pct", "label": "%"},
                        {"value": "avg", "label": "Avg #"},
                    ],
                    value="pct",
                    size="xs",
                ),
            ],
            extra_controls=[
                dmc.SegmentedControl(
                    id="courses-complexity-agg",
                    data=[
                        {"value": "W", "label": "Weekly"},
                        {"value": "M", "label": "Monthly"},
                        {"value": "Y", "label": "Yearly"},
                    ],
                    value="W",
                    size="xs",
                ),
            ],
        )
    )

    # --- Row 3: Treatment Site Distribution + Quitting Rate Trend -------
    row3a_charts = []

    # Treatment Site Distribution (horizontal bar)
    if "PrescriptionSites" in dff.columns and not dff.empty:
        sites_series = dff["PrescriptionSites"].dropna()
        if not sites_series.empty:
            site_list = []
            for val in sites_series:
                unique_sites = set()
                for s in str(val).split(";"):
                    stripped = s.strip()
                    if stripped:
                        unique_sites.add(stripped)
                site_list.extend(unique_sites)
            _site_display = {
                "Prostate and Seminal Vessicles.": "Prostate/SV",
            }
            site_counts = pd.Series(site_list).value_counts().head(15).sort_values(ascending=True)
            display_labels = [_site_display.get(s, s) for s in site_counts.index]
            fig_sites = go.Figure(go.Bar(
                y=display_labels,
                x=site_counts.values.tolist(),
                orientation="h",
                marker_color=PRIMARY,
                customdata=site_counts.index.tolist(),
                hovertemplate="<b>%{customdata}</b><br>Count: %{x}<extra></extra>",
            ))
            apply_default_layout(fig_sites)
            fig_sites.update_layout(
                height=None,
                yaxis_title="",
                xaxis_title="",
                margin=dict(l=120, r=8, t=16, b=36),
            )
            fig_sites.update_xaxes(automargin=False)
            fig_sites.update_yaxes(automargin=True)
        else:
            fig_sites = empty_figure("No prescription site data")
            fig_sites.update_layout(height=None)
    else:
        fig_sites = empty_figure("No prescription site data")
        fig_sites.update_layout(height=None)

    row3a_charts.append(
        dmc.GridCol(
            span={"base": 12, "md": 4},
            children=dmc.Paper(
                children=[
                    dmc.Group(
                        justify="space-between", align="center", mb=0,
                        children=[
                            dmc.Text("Treatment Site Distribution", size="sm", fw=500, c="#6B7280"),
                            chart_settings_popover(
                                "courses-sites",
                                chart_types=None,
                                show_smooth=False,
                                show_grouping=False,
                            ),
                        ],
                    ),
                    dmc.Box(
                        pos="relative",
                        style={"flex": "1", "minHeight": 0},
                        children=[
                            dmc.Box(
                                style={"position": "absolute", "top": 0, "left": 0, "right": 0, "bottom": 0},
                                children=[
                                    dcc.Graph(
                                        id="courses-chart-sites",
                                        figure=fig_sites,
                                        config={"displayModeBar": False},
                                        style={"height": "100%"},
                                    )
                                ],
                            )
                        ],
                    ),
                ],
                p="sm", pt="xs", pb=0, radius="md", shadow="xs", withBorder=True,
                h=CHART_PAPER_HEIGHT,
                style={"display": "flex", "flexDirection": "column"},
            ),
        )
    )

    # Quitting Rate Trend (clientside-rendered from store)
    row3a_charts.append(
        dmc.GridCol(
            span={"base": 12, "md": 4},
            children=dmc.Paper(
                children=[
                    dmc.Group(
                        justify="space-between", align="center", mb="sm",
                        children=[
                            dmc.Group(
                                gap="sm", align="center",
                                children=[
                                    dmc.Text("Quitting Rate Trend", size="sm", fw=500, c="#6B7280"),
                                    dmc.SegmentedControl(
                                        id="courses-quit-trend-slice",
                                        data=[
                                            {"value": "", "label": "Total"},
                                            {"value": "physician", "label": "MD"},
                                            {"value": "site", "label": "Site"},
                                            {"value": "diagnosis", "label": "Dx"},
                                        ],
                                        value="",
                                        size="xs",
                                    ),
                                ],
                            ),
                            dmc.Group(
                                gap="sm", align="center",
                                children=[
                                    dmc.SegmentedControl(
                                        id="courses-quit-trend-agg",
                                        data=[
                                            {"value": "W", "label": "Weekly"},
                                            {"value": "M", "label": "Monthly"},
                                            {"value": "Y", "label": "Yearly"},
                                        ],
                                        value="M",
                                        size="xs",
                                    ),
                                    chart_settings_popover(
                                        "courses-quit-trend",
                                        chart_types=[
                                            {"value": "line", "label": "Line"},
                                            {"value": "area", "label": "Area"},
                                            {"value": "bar", "label": "Bar"},
                                        ],
                                        show_smooth=True,
                                        smooth_max=12,
                                        smooth_default=0,
                                        extra_settings=[
                                            html.Div(
                                                dmc.Stack(gap=4, children=[
                                                    dmc.Text("Metric", size="xs", fw=500, c="#6B7280"),
                                                    dmc.SegmentedControl(
                                                        id="courses-quit-metric",
                                                        data=[
                                                            {"value": "fraction", "label": "Fraction"},
                                                            {"value": "session", "label": "Session"},
                                                        ],
                                                        value="fraction",
                                                        size="xs",
                                                        fullWidth=True,
                                                    ),
                                                ]),
                                            ),
                                        ],
                                    ),
                                ],
                            ),
                        ],
                    ),
                    dcc.Graph(
                        id="courses-chart-quit-trend",
                        config={"displayModeBar": False},
                        style={"flex": "1", "minHeight": 0},
                    ),
                ],
                p="sm", radius="md", shadow="xs", withBorder=True,
                h=CHART_PAPER_HEIGHT,
                style={"display": "flex", "flexDirection": "column"},
            ),
        )
    )

    # Course Interruption chart (clientside-rendered from store)
    row3a_charts.append(
        dmc.GridCol(
            span={"base": 12, "md": 4},
            children=chart_card(
                "courses-chart-interruption",
                "Course Interruptions",
                settings_id="courses-interruption",
                chart_types=None,
                show_smooth=False,
                paper_padding="md",
                extra_controls_left=[
                    dmc.SegmentedControl(
                        id="courses-interruption-mode",
                        data=[
                            {"value": "count", "label": "Count"},
                            {"value": "pct", "label": "%"},
                        ],
                        value="pct",
                        size="xs",
                    ),
                ],
                extra_controls=[
                    dmc.SegmentedControl(
                        id="courses-interruption-slice",
                        data=[
                            {"value": "", "label": "Total"},
                            {"value": "physician", "label": "MD"},
                            {"value": "site", "label": "Site"},
                            {"value": "diagnosis", "label": "Dx"},
                        ],
                        value="",
                        size="xs",
                    ),
                ],
            ),
        )
    )

    chart_children.append(dmc.Grid(gutter=16, align="stretch", children=row3a_charts))

    # ------------------------------------------------------------------
    # Detail Table (AG Grid) — skip rebuild when only grid filter changed
    # ------------------------------------------------------------------
    if triggered_by_grid:
        records = dash.no_update
        column_defs = dash.no_update
        chart_children = dash.no_update
        frac_min_data = dash.no_update
        frac_max_data = dash.no_update
    else:
        table_df = dff_full.copy()

        # Computed status
        table_df["_Status"] = "Active"
        eff_comp_mask = _is_effectively_completed(table_df)
        table_df.loc[eff_comp_mask, "_Status"] = "Completed"

        # Format dates
        for dc in ["LastTreatmentDate", "FirstTreatmentDate", "CourseStartDate"]:
            if dc in table_df.columns:
                table_df[dc] = table_df[dc].dt.strftime("%Y-%m-%d")

        # Deduplicate techniques
        if "TreatmentTechniques" in table_df.columns:
            table_df["TreatmentTechniques"] = table_df["TreatmentTechniques"].apply(
                lambda v: ", ".join(dict.fromkeys(s.strip() for s in str(v).split(",") if s.strip()))
                if pd.notna(v) else v
            )

        # Deduplicate prescription sites
        if "PrescriptionSites" in table_df.columns:
            table_df["PrescriptionSites"] = table_df["PrescriptionSites"].apply(
                lambda v: "; ".join(dict.fromkeys(s.strip() for s in str(v).split(";") if s.strip()))
                if pd.notna(v) else v
            )

        table_cols = [
            "LastTreatmentDate", "FirstTreatmentDate", "CourseStartDate",
            "PatientFullName", "Department", "Machines",
            "CourseId", "PlanNames", "_Status",
            "TreatingPhysician", "ConsultPhysician",
            "TreatmentTechniques",
            "FractionsPrescribed", "FractionsDelivered", "TreatmentDurationDays",
            "PrescriptionSites",
        ]
        available_cols = [c for c in table_cols if c in table_df.columns]
        table_df = table_df[available_cols]
        table_df["_row_idx"] = dff_full.index

        records = table_df.to_dict("records")

        column_defs = [
            {"field": "LastTreatmentDate", "headerName": "Last Tx", "maxWidth": 110, "sort": "desc"},
            {"field": "FirstTreatmentDate", "headerName": "First Tx", "maxWidth": 110},
            {"field": "CourseStartDate", "headerName": "Start Date", "maxWidth": 110},
            {"field": "PatientFullName", "headerName": "Patient", "width": 170},
            {"field": "Department", "headerName": "Department", "width": 110},
            {"field": "Machines", "headerName": "Machines", "width": 140},
            {"field": "CourseId", "headerName": "Course ID", "width": 110},
            {"field": "PlanNames", "headerName": "Plans", "width": 160},
            {"field": "_Status", "headerName": "Status", "width": 100},
            {"field": "TreatingPhysician", "headerName": "Treating MD", "width": 140},
            {"field": "ConsultPhysician", "headerName": "Consult MD", "width": 140},
            {"field": "TreatmentTechniques", "headerName": "Techniques", "width": 150},
            {"field": "FractionsPrescribed", "headerName": "Fx Rx", "width": 80, "type": "numericColumn"},
            {"field": "FractionsDelivered", "headerName": "Fx Del", "width": 80, "type": "numericColumn"},
            {"field": "TreatmentDurationDays", "headerName": "Duration (d)", "width": 100, "type": "numericColumn"},
            {"field": "PrescriptionSites", "headerName": "Rx Sites", "width": 160},
        ]
        column_defs = [cd for cd in column_defs if cd["field"] in available_cols]
        column_defs.append({"field": "_row_idx", "hide": True})
        column_defs = apply_phi_grid_rules(column_defs)

    return (
        kpi_active, kpi_started, kpi_completed, kpi_median_frac, kpi_median_dur, kpi_multiplan,
        sparkline_data,
        ridgeline_data, frac_trend_data, frac_dist_data, complexity_trend_data, technique_dist_data, quit_trend_data, interruption_data,
        chart_children, records, column_defs,
        frac_min_data, frac_max_data,
    )


# ---------------------------------------------------------------------------
# Callback 2: Volume Store
# ---------------------------------------------------------------------------

@callback(
    Output("courses-store-volume", "data"),
    *_COURSES_FILTER_INPUTS,
    Input("courses-volume-agg", "value"),
    Input("courses-volume-slice", "value"),
    Input("courses-table-filter-rows", "data"),
    *_COURSES_FILTER_STATES,
    running=[(Output("courses-chart-volume-loading", "visible"), True, False)],
)
def _update_courses_volume(*args):
    ctx = _unpack_courses_filter_args(args, n_extra_inputs=3)
    agg = args[12]
    volume_slice = args[13]
    grid_rows = args[14]
    data = _load_and_filter_courses(**ctx)
    if data is None:
        return None
    dff = _apply_grid_row_filter(data["dff"], grid_rows)
    if dff is None or dff.empty:
        return None
    return _prepare_volume_data(
        dff, agg, volume_slice or "", date_col=data["date_col"],
        c2b=data["c2b"], start=data["start"], end=data["end"],
        date_mode=data["date_mode"], diag_mode=data.get("diag_mode", "primary"),
    )


# ---------------------------------------------------------------------------
# Callback 3: Cumulative Store
# ---------------------------------------------------------------------------

@callback(
    Output("courses-store-cumulative", "data"),
    *_COURSES_FILTER_INPUTS,
    Input("courses-cumulative-mode", "value"),
    Input("courses-cumulative-period-type", "value"),
    Input("courses-cumulative-slice", "value"),
    Input("courses-table-filter-rows", "data"),
    *_COURSES_FILTER_STATES,
    running=[(Output("courses-chart-cumulative-loading", "visible"), True, False)],
)
def _update_courses_cumulative(*args):
    ctx = _unpack_courses_filter_args(args, n_extra_inputs=4)
    cumul_mode = args[12]
    cumul_period_type = args[13]
    cumul_slice = args[14]
    grid_rows = args[15]
    data = _load_and_filter_courses(**ctx)
    if data is None:
        return None
    df_all = _apply_grid_row_filter(data["df_all"], grid_rows)
    if df_all is None or df_all.empty:
        return None
    return _prepare_cumulative_data(
        df_all, data["start"], data["end"], data["date_preset"],
        data["date_col"], data["departments"], data["physician"],
        data["diagnosis_cats"], data["status"], data["active_frac_range"],
        data["c2b"], inpatient=data["inpatient"],
        techniques=data["techniques"], date_mode=data["date_mode"],
        mode=cumul_mode or "prior",
        period_type=cumul_period_type or "calendar",
        slice_by=cumul_slice or "site",
        max_prior=10, diag_mode=data.get("diag_mode", "primary"),
        physician_role=data.get("physician_role", "treating"),
    )


# ---------------------------------------------------------------------------
# Clientside callbacks for charts
# ---------------------------------------------------------------------------

clientside_callback(
    """function(rawData, smoothPct, chartType, stackVal, currentFig) {
        return window.dash_clientside.census.smoothChartWithType(rawData, smoothPct, chartType, currentFig, stackVal);
    }""",
    Output("courses-chart-volume", "figure"),
    Input("courses-store-volume", "data"),
    Input("courses-volume-settings-smooth", "value"),
    Input("courses-volume-settings-type", "value"),
    Input("courses-volume-settings-stack", "value"),
    State("courses-chart-volume", "figure"),
    prevent_initial_call=True,
)

clientside_callback("""function() {
        var fig = window.dash_clientside.cumulative.renderWithProjectToggle.apply(null, arguments);
        return window.dash_clientside.chartDeferred.wrap("courses-chart-cumulative", fig, true);
    }""",
    Output("courses-chart-cumulative", "figure"),
    Input("courses-store-cumulative", "data"),
    Input("courses-cumulative-settings-smooth", "value"),
    Input("courses-cumulative-settings-type", "value"),
    Input("courses-cumulative-settings-stack", "value"),
    Input("courses-cumulative-settings-prior-periods", "value"),

    Input("courses-cumulative-project", "checked"),
    State("courses-chart-cumulative", "figure"),
    prevent_initial_call=True,
)


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# KPI Sparkline clientside callbacks
# ---------------------------------------------------------------------------

_COURSES_SPARKLINE_IDS = [
    "courses-spark-active",
    "courses-spark-started",
    "courses-spark-completed",
    "courses-spark-fractions",
    "courses-spark-duration",
    "courses-spark-multiplan",
]

for _spark_id in _COURSES_SPARKLINE_IDS:
    clientside_callback(f"""function() {{
        var fig = window.dash_clientside.sparklines.updateFromStore.apply(null, arguments);
        return window.dash_clientside.chartDeferred.wrap("{_spark_id}", fig);
    }}""",
        Output(_spark_id, "figure"),
        Input("courses-store-kpi-sparklines", "data"),
        Input(_spark_id, "id"),
        Input("courses-smooth-slider", "value"),
        prevent_initial_call=True,
    )


# ---------------------------------------------------------------------------
# Ridgeline callback (mode + bandwidth)
# ---------------------------------------------------------------------------

@callback(
    Output("courses-chart-ridgeline", "figure"),
    Input("courses-store-ridgeline", "data"),
    Input("courses-ridge-bw", "value"),
    Input("courses-ridge-mode", "value"),
    Input("global-theme-store", "data"),
)
def _update_ridgeline(data, bw, mode, theme):
    return _build_ridgeline_figure(data, bw_factor=bw or 0.5, mode=mode or "density", theme=theme)


# Hide bandwidth slider in histogram mode
clientside_callback(
    """function(mode) {
        return mode === "histogram" ? {display: "none"} : {};
    }""",
    Output("courses-ridge-bw-group", "style"),
    Input("courses-ridge-mode", "value"),
)

# Hide frac-dist bandwidth slider in histogram mode
clientside_callback(
    """function(mode) {
        return mode === "histogram" ? {display: "none"} : {};
    }""",
    Output("courses-frac-dist-bw-group", "style"),
    Input("courses-frac-dist-mode", "value"),
)


# ---------------------------------------------------------------------------
# Course Interruption callback
# ---------------------------------------------------------------------------

@callback(
    Output("courses-chart-interruption", "figure"),
    Input("courses-store-interruption", "data"),
    Input("courses-interruption-mode", "value"),
    Input("courses-interruption-slice", "value"),
    Input("courses-interruption-settings-stack", "value"),
)
def _update_interruption(data, mode, slice_by, stack_mode):
    if not data:
        fig = empty_figure("No interruption data")
        fig.update_layout(height=None)
        return fig

    mode = mode or "count"
    slice_by = slice_by or ""

    if not slice_by:
        # Total view
        summary = data.get("", data)
        if not summary or summary.get("n_interrupted", 0) == 0:
            fig = empty_figure("No interruption data")
            fig.update_layout(height=None)
            return fig

        buckets = summary["buckets"]
        n_total = summary["n_total"]
        labels = [b["label"] for b in buckets]

        if mode == "pct":
            values = [round(b["count"] / n_total * 100, 1) if n_total else 0 for b in buckets]
            y_title = "% of Courses"
        else:
            values = [b["count"] for b in buckets]
            y_title = "Courses"

        fig = go.Figure(go.Bar(
            x=labels, y=values, marker_color=PRIMARY,
            hovertemplate="<b>%{x}</b><br>" + y_title + ": %{y}<extra></extra>",
        ))
        sub_text = f"{summary['rate']:.0f}% interrupted  ·  Median {summary['median_delay']:.0f} business days"
    else:
        # Sliced view — grouped bar by slice category
        slice_data = data.get(slice_by, {})
        if not slice_data:
            fig = empty_figure("No data for slice")
            fig.update_layout(height=None)
            return fig

        bucket_labels = [b["label"] for b in list(slice_data.values())[0]["buckets"]]
        fig = go.Figure()

        colors = CHART_COLORWAY
        if slice_by == "site":
            colors = None  # use dept colors

        for i, (name, summary) in enumerate(slice_data.items()):
            buckets = summary["buckets"]
            n_total = summary["n_total"]
            if mode == "pct":
                values = [round(b["count"] / n_total * 100, 1) if n_total else 0 for b in buckets]
            else:
                values = [b["count"] for b in buckets]

            color = DEPARTMENT_COLORS.get(name, CHART_COLORWAY[i % len(CHART_COLORWAY)]) if slice_by == "site" else CHART_COLORWAY[i % len(CHART_COLORWAY)]
            fig.add_trace(go.Bar(
                x=bucket_labels, y=values, name=name, marker_color=color,
                hovertemplate=f"<b>{name}</b><br>" + "%{x}: %{y}<extra></extra>",
            ))

        fig.update_layout(barmode="stack" if stack_mode == "stacked" else "group")
        y_title = "% of Courses" if mode == "pct" else "Courses"

        total_summary = data.get("", {})
        sub_text = f"{total_summary.get('rate', 0):.0f}% interrupted overall" if total_summary else ""

    apply_default_layout(fig)
    fig.add_annotation(
        text=sub_text,
        xref="paper", yref="paper",
        x=0.5, y=-0.07, yanchor="top",
        showarrow=False,
        font=dict(size=12, color="#9CA3AF"),
    )
    fig.update_layout(
        height=None,
        yaxis_title=y_title,
        xaxis_title="",
        margin=dict(l=40, r=8, t=8, b=0),
        showlegend=bool(slice_by),
        legend=dict(orientation="h", y=1.02, x=0.5, xanchor="center", yanchor="bottom"),
    )
    return fig


# ---------------------------------------------------------------------------
# Fractions Trend callback (clientside: agg + slice-by + smooth + chart type)
# ---------------------------------------------------------------------------

clientside_callback(
    """function(storeData, smoothVal, chartType, agg, sliceBy, currentFig) {
        if (!storeData) return window.dash_clientside.no_update;
        var key = (agg || "M") + "|" + (sliceBy || "");
        var combo = storeData[key];
        if (!combo || !combo.series || combo.series.length === 0) {
            return {
                data: [],
                layout: {
                    font: {family: "system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif", size: 12},
                    margin: {l: 48, r: 16, t: 24, b: 40},
                    plot_bgcolor: "rgba(0,0,0,0)", paper_bgcolor: "rgba(0,0,0,0)",
                    xaxis: {visible: false}, yaxis: {visible: false},
                    annotations: [{text: "No fractions data", showarrow: false,
                        xref: "paper", yref: "paper", x: 0.5, y: 0.5,
                        font: {size: 14, color: "#9CA3AF"}}]
                }
            };
        }
        var ct = chartType || "line";
        var isDark = document.documentElement.getAttribute("data-theme") === "dark";
        // PRIMARY violet (#7C2A83) is too dark to read as a line/area on the
        // dark paper background — swap to violet[3] (#C186C9) for any non-bar
        // chart type in dark mode. Bars stay PRIMARY (large filled area).
        var series = combo.series;
        if (isDark && ct !== "bar") {
            series = series.map(function(s) {
                if (s.color && s.color.toUpperCase() === "#7C2A83") {
                    return Object.assign({}, s, {color: "#C186C9"});
                }
                return s;
            });
        }
        var data = {
            dates: combo.dates,
            series: series,
            yTitle: "Median Fractions",
            hideLegend: series.length <= 1,
            stacked: false
        };
        var __fig = (window.dash_clientside.census.smoothChartWithType(data, smoothVal, ct, currentFig));
        return window.dash_clientside.chartDeferred.wrap("courses-chart-frac-trend", __fig);
    }""",
    Output("courses-chart-frac-trend", "figure"),
    Input("courses-store-frac-trend", "data"),
    Input("courses-frac-trend-settings-smooth", "value"),
    Input("courses-frac-trend-settings-type", "value"),
    Input("courses-frac-trend-agg", "value"),
    Input("courses-frac-trend-slice", "value"),
    State("courses-chart-frac-trend", "figure"),
    prevent_initial_call=True,
)


# ---------------------------------------------------------------------------
# Quit Rate Trend callback (clientside: agg + slice-by + smooth + chart type)
# ---------------------------------------------------------------------------

clientside_callback(
    """function(storeData, smoothVal, chartType, agg, sliceBy, metric, currentFig) {
        if (!storeData) return window.dash_clientside.no_update;
        var key = (agg || "M") + "|" + (sliceBy || "") + "|" + (metric || "fraction");
        var combo = storeData[key];
        if (!combo || !combo.series || combo.series.length === 0) {
            return {
                data: [],
                layout: {
                    font: {family: "system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif", size: 12},
                    margin: {l: 48, r: 16, t: 24, b: 40},
                    plot_bgcolor: "rgba(0,0,0,0)", paper_bgcolor: "rgba(0,0,0,0)",
                    xaxis: {visible: false}, yaxis: {visible: false},
                    annotations: [{text: "No quit rate data", showarrow: false,
                        xref: "paper", yref: "paper", x: 0.5, y: 0.5,
                        font: {size: 14, color: "#9CA3AF"}}]
                }
            };
        }
        var ct = chartType || "line";
        var isDark = document.documentElement.getAttribute("data-theme") === "dark";
        // Same swap as the Median Fractions Trend: PRIMARY violet (#7C2A83)
        // is too dark for line/area on the dark paper background. Bars stay
        // PRIMARY because the filled area gives plenty of contrast.
        var series = combo.series;
        if (isDark && ct !== "bar") {
            series = series.map(function(s) {
                if (s.color && s.color.toUpperCase() === "#7C2A83") {
                    return Object.assign({}, s, {color: "#C186C9"});
                }
                return s;
            });
        }
        var data = {
            dates: combo.dates,
            series: series,
            yTitle: "Quit Rate (%)",
            hideLegend: series.length <= 1,
            stacked: false
        };
        var __fig = (window.dash_clientside.census.smoothChartWithType(data, smoothVal, ct, currentFig));
        return window.dash_clientside.chartDeferred.wrap("courses-chart-quit-trend", __fig);
    }""",
    Output("courses-chart-quit-trend", "figure"),
    Input("courses-store-quit-trend", "data"),
    Input("courses-quit-trend-settings-smooth", "value"),
    Input("courses-quit-trend-settings-type", "value"),
    Input("courses-quit-trend-agg", "value"),
    Input("courses-quit-trend-slice", "value"),
    Input("courses-quit-metric", "value"),
    State("courses-chart-quit-trend", "figure"),
    prevent_initial_call=True,
)


# ---------------------------------------------------------------------------
# Fractions Distribution callback (histogram/density toggle)
# ---------------------------------------------------------------------------

@callback(
    Output("courses-chart-frac-dist", "figure"),
    Input("courses-store-frac-dist", "data"),
    Input("courses-frac-dist-mode", "value"),
    Input("courses-frac-dist-bw", "value"),
    Input("global-theme-store", "data"),
)
def _update_frac_dist(data, mode, bw, theme):
    if not data:
        fig = empty_figure("No fractions data")
        fig.update_layout(height=310)
        return fig

    _is_dark = (theme or "light") == "dark"
    # Brighter violet in dark mode for adequate contrast against the dark
    # paper background; PRIMARY is fine on light backgrounds.
    _accent = "#C186C9" if _is_dark else PRIMARY

    mode = mode or "histogram"
    bw = bw or 0.15
    fig = go.Figure()

    if mode == "density" and data.get("values"):
        from scipy.stats import gaussian_kde
        arr = np.array(data["values"])
        try:
            kde = gaussian_kde(arr, bw_method=bw)
            x_min = max(0, float(arr.min()) - 2)
            x_max = float(arr.max()) + 2
            x_grid = np.linspace(x_min, x_max, 200)
            kde_y = kde(x_grid)
            fig.add_trace(go.Scatter(
                x=x_grid.tolist(),
                y=kde_y.tolist(),
                mode="lines",
                fill="tozeroy",
                line=dict(color=PRIMARY, width=2),
                fillcolor="rgba(124, 42, 131, 0.15)",
                hovertemplate="Fractions: %{x:.0f}<br>Density: %{y:.4f}<extra></extra>",
            ))
        except Exception:
            pass
        y_title = "Density"
    else:
        fig.add_trace(go.Histogram(
            x=data["values"],
            xbins=dict(start=0, size=1),
            autobinx=False,
            marker_color=PRIMARY,
            hovertemplate="Fractions: %{x}<br>Count: %{y}<extra></extra>",
        ))
        y_title = "Courses"

    # Median vertical line
    med = data["median"]
    fig.add_vline(x=med, line_dash="dash", line_color=_accent)
    fig.add_annotation(
        x=med, y=1.0, yref="paper", yshift=2,
        text=f"Median: {med:.0f}", showarrow=False,
        font=dict(family=FONT_FAMILY, size=11, color=_accent),
        yanchor="bottom", xanchor="center",
    )

    apply_default_layout(fig)
    fig.update_layout(
        height=310,
        xaxis_title=f"Fractions Prescribed  (n={data['n']}  Mean: {data['mean']:.0f}  IQR: {data['p25']:.0f}\u2013{data['p75']:.0f})",
        yaxis_title=y_title,
        margin=dict(l=48, r=16, t=16, b=4),
    )
    return fig


# ---------------------------------------------------------------------------
# Complexity Trend callbacks (multi-machine / multi-dept / multi-plan)
# ---------------------------------------------------------------------------

def _hex_to_rgba(hex_color, alpha=0.1):
    """Convert hex color to rgba string."""
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


_COMPLEXITY_DIM_CFG = {
    "machines": {"color": CHART_COLORWAY[0], "pct_label": "% Multi-Machine", "avg_label": "Avg Machines"},
    "depts": {"color": CHART_COLORWAY[1], "pct_label": "% Multi-Department", "avg_label": "Avg Departments"},
    "plans": {"color": CHART_COLORWAY[2], "pct_label": "% Multi-Plan", "avg_label": "Avg Plans"},
    "isos": {"color": CHART_COLORWAY[3], "pct_label": "% Multi-Isocenter", "avg_label": "Avg Isocenters"},
}

def _apply_moving_avg(values, window):
    """Apply simple moving average to a list of values (None-safe)."""
    if window <= 1:
        return values
    result = []
    for i in range(len(values)):
        start = max(0, i - window + 1)
        chunk = [v for v in values[start:i + 1] if v is not None]
        result.append(round(sum(chunk) / len(chunk), 2) if chunk else None)
    return result


_COMPLEXITY_FACETS = [
    ("machines", "Multi-Machine"),
    ("depts", "Multi-Department"),
    ("plans", "Multi-Plan"),
    ("isos", "Multi-Isocenter"),
]


@callback(
    Output("courses-chart-complexity", "figure"),
    Input("courses-store-complexity-trends", "data"),
    Input("courses-complexity-agg", "value"),
    Input("courses-complexity-mode", "value"),
    Input("courses-complexity-settings-smooth", "value"),
    Input("courses-complexity-settings-type", "value"),
    Input("global-theme-store", "data"),
    prevent_initial_call=False,
)
def _update_complexity_facets(data, agg, mode, smooth, chart_type, theme):
    from plotly.subplots import make_subplots

    if not data:
        fig = empty_figure("No data")
        fig.update_layout(height=560)
        return fig

    agg = agg or "W"
    mode = mode or "pct"
    chart_type = chart_type or "line"
    smooth = smooth or 0

    fig = make_subplots(
        rows=2, cols=2,
        subplot_titles=[title for _, title in _COMPLEXITY_FACETS],
        vertical_spacing=0.12,
        horizontal_spacing=0.06,
    )

    for i, (dim_key, _title) in enumerate(_COMPLEXITY_FACETS):
        row = i // 2 + 1
        col = i % 2 + 1
        cfg = _COMPLEXITY_DIM_CFG[dim_key]

        key = f"{agg}|{dim_key}"
        combo = data.get(key)
        if not combo:
            continue

        dates = combo["dates"]
        raw_values = combo[mode]
        values = _apply_moving_avg(raw_values, smooth)

        if mode == "pct":
            hover_tmpl = "<b>%{x|%b %Y}</b><br>%{y:.1f}%<extra></extra>"
        else:
            hover_tmpl = "<b>%{x|%b %Y}</b><br>%{y:.2f}<extra></extra>"

        if chart_type == "bar":
            fig.add_trace(go.Bar(
                x=dates, y=values,
                marker_color=cfg["color"],
                hovertemplate=hover_tmpl,
                showlegend=False,
            ), row=row, col=col)
        else:
            fill_mode = "tozeroy" if chart_type == "area" else "none"
            _alpha = 0.25 if theme == "dark" else 0.1
            fig.add_trace(go.Scatter(
                x=dates, y=values,
                mode="lines+markers",
                line=dict(color=cfg["color"], width=2),
                marker=dict(size=3),
                fill=fill_mode,
                fillcolor=_hex_to_rgba(cfg["color"], _alpha),
                connectgaps=True,
                hovertemplate=hover_tmpl,
                showlegend=False,
            ), row=row, col=col)

        # Y-axis range for pct mode
        if mode == "pct":
            max_val = max((v for v in values if v is not None), default=0)
            ceiling = min(100, max(max_val * 1.25, 5))
            yaxis_key = f"yaxis{i + 1}" if i > 0 else "yaxis"
            fig.update_layout(**{yaxis_key: dict(range=[0, ceiling])})

    apply_default_layout(fig)
    # Re-apply subplot title styling after default layout. Plotly's
    # subplot_titles annotations don't inherit the figure's font.family,
    # so set it explicitly — otherwise the SVG falls back to a thinner
    # default sans-serif (most visible against the dark paper background).
    _is_dark = (theme or "light") == "dark"
    _title_color = "#9CA3AF" if _is_dark else "#6B7280"
    for ann in fig.layout.annotations:
        ann.update(font=dict(family=FONT_FAMILY, size=12, color=_title_color))
    fig.update_layout(
        height=560,
        showlegend=False,
        margin=dict(l=48, r=16, t=32, b=40),
        hovermode="x unified",
    )
    return fig


# ---------------------------------------------------------------------------
# Technique Distribution callback
# ---------------------------------------------------------------------------

@callback(
    Output("courses-chart-technique-dist", "figure"),
    Input("courses-store-technique-dist", "data"),
    Input("courses-technique-dist-counting", "value"),
    Input("courses-technique-dist-mode", "value"),
    Input("courses-technique-dist-agg", "value"),
    Input("courses-technique-dist-settings-smooth", "value"),
    Input("courses-technique-dist-settings-type", "value"),
    Input("courses-technique-dist-settings-stack", "value"),
    prevent_initial_call=False,
)
def _update_technique_dist(data, counting, mode, agg, smooth, chart_type, stack_mode):
    if not data:
        return empty_figure("No technique data")

    agg = agg or "M"
    counting = counting or "any"
    key = f"{agg}|{counting}"
    combo = data.get(key)
    if not combo or not combo.get("series"):
        return empty_figure("No technique data for selection")

    dates = combo["dates"]
    mode = mode or "count"
    chart_type = chart_type or "area"
    smooth = smooth or 0

    # Build raw values per technique; stack order: least advanced at bottom
    # (reversed from _TECHNIQUE_ORDER so most advanced ends up on top)
    raw_series = list(reversed(combo["series"]))

    # Convert to proportions if needed
    n_periods = len(dates)
    if mode == "pct":
        totals = [0.0] * n_periods
        for s in raw_series:
            for i in range(n_periods):
                totals[i] += s["values"][i]
        proc_series = []
        for s in raw_series:
            pct_vals = []
            for i in range(n_periods):
                if totals[i] > 0:
                    pct_vals.append(round(s["values"][i] / totals[i] * 100, 1))
                else:
                    pct_vals.append(0)
            proc_series.append({**s, "values": pct_vals})
    else:
        proc_series = raw_series

    # Apply smoothing
    if smooth > 1:
        proc_series = [
            {**s, "values": _apply_moving_avg(s["values"], smooth)}
            for s in proc_series
        ]

    fig = go.Figure()

    if chart_type == "bar":
        for s in proc_series:
            fig.add_trace(go.Bar(
                x=dates,
                y=s["values"],
                name=s["name"],
                marker_color=s["color"],
                marker_opacity=0.7,
                hovertemplate=(
                    "<b>%{x|%b %Y}</b><br>"
                    + s["name"] + ": %{y:.0f}" + ("%" if mode == "pct" else "")
                    + "<extra></extra>"
                ),
            ))
        fig.update_layout(barmode="stack" if stack_mode != "grouped" else "group")
    else:
        stackgroup = "tech" if (chart_type == "area" and stack_mode != "grouped") else None
        for s in proc_series:
            fig.add_trace(go.Scatter(
                x=dates,
                y=s["values"],
                name=s["name"],
                mode="lines",
                line=dict(color=s["color"], width=0.5 if chart_type == "area" else 2),
                stackgroup=stackgroup,
                fillcolor=_hex_to_rgba(s["color"], 0.75) if chart_type == "area" else None,
                opacity=0.85,
                hovertemplate=(
                    "<b>%{x|%b %Y}</b><br>"
                    + s["name"] + ": %{y:.0f}" + ("%" if mode == "pct" else "")
                    + "<extra></extra>"
                ),
            ))

    apply_default_layout(fig)
    n_series = len(proc_series)
    fig.update_layout(
        height=420,
        yaxis_title="Proportion (%)" if mode == "pct" else "Course Count",
        showlegend=True,
        legend=dict(
            orientation="h", y=1.02, x=0.5, xanchor="center", yanchor="bottom",
            traceorder="normal",
        ),
        margin=dict(l=48, r=16, t=56, b=40),
        hovermode="x unified",
        hoverdistance=-1,
    )
    if mode == "pct" and chart_type != "line":
        fig.update_yaxes(range=[0, 100])

    return fig


# Table CSV Export (clientside)
# ---------------------------------------------------------------------------

clientside_callback(
    """function(n) {
        if (!n) return window.dash_clientside.no_update;
        gridExportCsv('courses-detail-grid', 'courses_detail.csv');
        return window.dash_clientside.no_update;
    }""",
    Output("courses-table-export", "n_clicks"),
    Input("courses-table-export", "n_clicks"),
    prevent_initial_call=True,
)


# Grid-filter → chart sync: extract _row_idx from virtualRowData, toggle badge.
clientside_callback(
    """function(virtual, rowData, prev) {
        var nu = window.dash_clientside.no_update;
        var base = {"position": "absolute", "top": -12, "right": 8, "zIndex": 10, "cursor": "pointer"};
        var hidden = Object.assign({}, base, {"display": "none"});
        var btnHide = {"display": "none"};
        if (!rowData || !rowData.length || !virtual) {
            return prev == null ? [nu, nu, nu] : [null, hidden, btnHide];
        }
        if (virtual.length >= rowData.length) {
            return prev == null ? [nu, nu, nu] : [null, hidden, btnHide];
        }
        var idxs = [];
        for (var i = 0; i < virtual.length; i++) {
            if (virtual[i]._row_idx != null) idxs.push(virtual[i]._row_idx);
        }
        idxs.sort(function(a, b) { return a - b; });
        if (!idxs.length) {
            return prev == null ? [nu, nu, nu] : [null, hidden, btnHide];
        }
        if (prev && prev.length === idxs.length) {
            var same = true;
            for (var j = 0; j < idxs.length; j++) {
                if (prev[j] !== idxs[j]) { same = false; break; }
            }
            if (same) return [nu, nu, nu];
        }
        return [idxs, base, {}];
    }""",
    Output("courses-table-filter-rows", "data"),
    Output("courses-grid-filter-badge", "style"),
    Output("courses-table-clear-filters", "style"),
    Input("courses-detail-grid", "virtualRowData"),
    State("courses-detail-grid", "rowData"),
    State("courses-table-filter-rows", "data"),
    prevent_initial_call=True,
)


# Clear Filters button — reset grid filterModel
clientside_callback(
    """function(n) {
        if (!n) return window.dash_clientside.no_update;
        return {};
    }""",
    Output("courses-detail-grid", "filterModel"),
    Input("courses-table-clear-filters", "n_clicks"),
    prevent_initial_call=True,
)


# Badge click → scroll to the detail table
clientside_callback(
    """function(n) {
        if (!n) return window.dash_clientside.no_update;
        var el = document.getElementById('courses-detail-grid');
        if (el) el.scrollIntoView({behavior: 'smooth', block: 'start'});
        return window.dash_clientside.no_update;
    }""",
    Output("courses-grid-filter-badge", "n_clicks"),
    Input("courses-grid-filter-badge", "n_clicks"),
    prevent_initial_call=True,
)


# Project-to-year-end toggle visibility (shown only for current_year preset)
clientside_callback(
    """function(preset) {
        return preset === "current_year" ? {} : {"display": "none"};
    }""",
    Output("courses-cumulative" + "-project-wrap", "style"),
    Input("courses-filter-date-preset", "value"),
)

