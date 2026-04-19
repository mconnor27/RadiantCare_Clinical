"""Procedures page -- ancillary procedure tracking by category with tabbed detail views."""

import math
import dash
import dash_mantine_components as dmc
import dash_ag_grid as dag
from dash import callback, Input, Output, State, dcc, html, clientside_callback, ClientsideFunction
from dash_iconify import DashIconify
import plotly.graph_objects as go
import pandas as pd
import numpy as np

from config.settings import (
    DEPARTMENTS, DEPARTMENT_COLORS, CHART_COLORWAY, PRIMARY,
    DEFAULT_LAYOUT, FONT_FAMILY, SEMANTIC_COLORS, NEUTRAL,
    DEFAULT_COLUMN_DEFS, DEFAULT_GRID_OPTIONS, CHART_PAPER_HEIGHT, PRIOR_PERIOD_COLORS,
)
from components.filter_bar import department_chips
from components.kpi_card import kpi_card, kpi_placeholder
from components.chart_card import chart_card, register_chart_callbacks
from components.detail_table import detail_table
from components.phi import apply_phi_grid_rules
from utils.charts import apply_default_layout, empty_figure, dept_color
from utils.tables import sanitize_for_grid
from utils.date_slider import (
    month_idx, idx_to_date, MAX_IDX, DEFAULT_SLIDER, SLIDER_MARKS,
    preset_to_slider_val, preset_to_exact_dates,
)

dash.register_page(__name__, path="/procedures", name="Procedures", order=10)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
PAGE_ID = "proc"
_DEFAULT_DATE_PRESET = "12mo"

PROCEDURE_CATEGORIES = [
    "Pluvicto", "Rectal Spacer", "Lupron", "Prostate LDR", "Volume Study", "Gold Seeds",
]

_TAB_KEYS = {
    "Lupron": "lupron",
    "Prostate LDR": "ldr",
    "Rectal Spacer": "spacer",
    "Gold Seeds": "seeds",
    "Volume Study": "volstudy",
    "Pluvicto": "pluvicto",
}

_CAT_TAB_PAIRS = list(_TAB_KEYS.items())  # ordered list of (cat_name, key)

_CATEGORY_COLORS = {
    "Lupron": CHART_COLORWAY[0],       # purple
    "Prostate LDR": CHART_COLORWAY[1],  # blue
    "Rectal Spacer": CHART_COLORWAY[2], # red
    "Gold Seeds": CHART_COLORWAY[3],    # green
    "Volume Study": CHART_COLORWAY[4],  # orange
    "Pluvicto": CHART_COLORWAY[5],      # cyan
}


# ---------------------------------------------------------------------------
# Filter Bar
# ---------------------------------------------------------------------------

def _build_filter_bar():
    """Build the two-row filter bar for procedures page."""
    return dmc.Paper(
        children=[
            # Row 1: dimension filters
            dmc.Group(
                children=[
                    department_chips(PAGE_ID),
                    # Physician dropdown
                    html.Div(
                        children=[
                            html.Div(
                                children=[
                                    dmc.Button(
                                        "Physician",
                                        id=f"{PAGE_ID}-physician-trigger",
                                        variant="default",
                                        size="sm",
                                        rightSection=DashIconify(icon="mdi:chevron-down", width=14),
                                    ),
                                    dmc.ActionIcon(
                                        DashIconify(icon="mdi:close-circle", width=18),
                                        id=f"{PAGE_ID}-physician-clear",
                                        variant="subtle",
                                        color="gray",
                                        size="sm",
                                        className="wf-filter-clear-btn",
                                    ),
                                ],
                                style={"position": "relative", "display": "inline-block"},
                            ),
                            dmc.Paper(
                                id=f"{PAGE_ID}-physician-panel",
                                children=[
                                    dmc.ChipGroup(
                                        children=[],
                                        id=f"{PAGE_ID}-filter-physician",
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
                    # Status filter
                    dmc.SegmentedControl(
                        id=f"{PAGE_ID}-filter-status",
                        data=[
                            {"value": "all", "label": "All"},
                            {"value": "open", "label": "Open"},
                            {"value": "completed", "label": "Completed"},
                        ],
                        value="all",
                        size="xs",
                    ),
                    # Smoothing slider for KPI sparklines
                    dmc.Group(
                        children=[
                            dmc.Text("Smoothing", size="xs", c="#6B7280", fw=500),
                            dmc.Slider(
                                id=f"{PAGE_ID}-smooth-slider",
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
# Tab Panels — detail content only (charts live above tabs)
# ---------------------------------------------------------------------------

def _tab_panel(cat_key):
    """Build a tab panel with detail grid only (charts are shared above tabs)."""
    return [
        detail_table(
            f"{PAGE_ID}-tab-grid-{cat_key}",
            title="Detail Records",
            export_id=f"{PAGE_ID}-tab-export-{cat_key}",
            extra_controls=[
                dmc.Button(
                    "Clear Filters",
                    id=f"{PAGE_ID}-table-clear-filters-{cat_key}",
                    size="compact-xs",
                    variant="light",
                    color="red",
                    leftSection=DashIconify(icon="mdi:filter-remove", width=14),
                    style={"display": "none"},
                ),
            ],
        ),
    ]


def _pluvicto_panel():
    """Build the Pluvicto tab panel with patient queue + detail grid."""
    return [
        # Patient queue — slim inline table with status toggle
        dmc.Paper(
            children=[
                dmc.Group(
                    justify="space-between", align="center", mb=6,
                    children=[
                        dmc.Text("Pluvicto Patient Queue", size="sm", fw=500, c=NEUTRAL["text_secondary"]),
                        dmc.SegmentedControl(
                            id=f"{PAGE_ID}-pluvicto-queue-filter",
                            data=[
                                {"value": "all", "label": "All"},
                                {"value": "in_progress", "label": "In Progress"},
                                {"value": "completed", "label": "Completed"},
                            ],
                            value="all",
                            size="xs",
                        ),
                    ],
                ),
                html.Div(id=f"{PAGE_ID}-pluvicto-queue"),
            ],
            p="md",
            radius="md",
            shadow="xs",
            withBorder=True,
        ),
        detail_table(
            f"{PAGE_ID}-tab-grid-pluvicto",
            title="Detail Records",
            export_id=f"{PAGE_ID}-tab-export-pluvicto",
            extra_controls=[
                dmc.Button(
                    "Clear Filters",
                    id=f"{PAGE_ID}-table-clear-filters-pluvicto",
                    size="compact-xs",
                    variant="light",
                    color="red",
                    leftSection=DashIconify(icon="mdi:filter-remove", width=14),
                    style={"display": "none"},
                ),
            ],
        ),
    ]


def _spacer_panel():
    """Build the Rectal Spacer tab panel with upcoming patient queue + detail grid."""
    return [
        dmc.Paper(
            children=[
                dmc.Text("Rectal Spacer Patient Queue", size="sm", fw=500,
                         c=NEUTRAL["text_secondary"], mb=6),
                html.Div(id=f"{PAGE_ID}-spacer-queue"),
            ],
            p="md",
            radius="md",
            shadow="xs",
            withBorder=True,
        ),
        detail_table(
            f"{PAGE_ID}-tab-grid-spacer",
            title="Detail Records",
            export_id=f"{PAGE_ID}-tab-export-spacer",
            extra_controls=[
                dmc.Button(
                    "Clear Filters",
                    id=f"{PAGE_ID}-table-clear-filters-spacer",
                    size="compact-xs",
                    variant="light",
                    color="red",
                    leftSection=DashIconify(icon="mdi:filter-remove", width=14),
                    style={"display": "none"},
                ),
            ],
        ),
    ]


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
                dmc.Title("Procedures", order=2, className="page-title",
                          style={"margin": 0, "textAlign": "center"}),
                html.Div(
                    style={"position": "relative"},
                    children=[
                        _build_filter_bar(),
                        html.Div(
                            id=f"{PAGE_ID}-grid-filter-badge",
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

        # KPI row — 5 cards
        dmc.Grid(id=f"{PAGE_ID}-kpi-row", gutter="md", children=[
            dmc.GridCol(kpi_placeholder(), id=f"{PAGE_ID}-kpi-pluvicto", span={"base": 12, "sm": 6, "md": 2.4}),
            dmc.GridCol(kpi_placeholder(), id=f"{PAGE_ID}-kpi-upcoming-pluv", span={"base": 12, "sm": 6, "md": 2.4}),
            dmc.GridCol(kpi_placeholder(), id=f"{PAGE_ID}-kpi-spacer", span={"base": 12, "sm": 6, "md": 2.4}),
            dmc.GridCol(kpi_placeholder(), id=f"{PAGE_ID}-kpi-upcoming-spacer", span={"base": 12, "sm": 6, "md": 2.4}),
            dmc.GridCol(kpi_placeholder(), id=f"{PAGE_ID}-kpi-lead-time", span={"base": 12, "sm": 6, "md": 2.4}),
        ]),

        # Category tabs (tab list only — charts sit between tabs and content)
        dmc.Tabs(
            id=f"{PAGE_ID}-tabs",
            value="pluvicto",
            variant="outline",
            color="violet",
            children=[
                dmc.TabsList([
                    dmc.TabsTab("Pluvicto", value="pluvicto"),
                    dmc.TabsTab("Rectal Spacer", value="spacer"),
                    dmc.TabsTab("Lupron", value="lupron"),
                    dmc.TabsTab("Prostate LDR", value="ldr"),
                    dmc.TabsTab("Volume Study", value="volstudy"),
                    dmc.TabsTab("Gold Seeds", value="seeds"),
                ]),
            ],
        ),

        # Shared chart row — updates based on selected tab
        dmc.Grid(gutter="md", children=[
            dmc.GridCol(
                chart_card(
                    f"{PAGE_ID}-chart-trend",
                    "Volume Trend",
                    settings_id=f"{PAGE_ID}-trend",
                    chart_types=[
                        {"value": "bar", "label": "Bar"},
                        {"value": "line", "label": "Line"},
                        {"value": "area", "label": "Area"},
                    ],
                    chart_type_default="bar",
                    show_smooth=True,
                    smooth_max=12,
                    smooth_default=0,
                    paper_padding="md",
                    extra_controls_left=[
                        dmc.SegmentedControl(
                            id=f"{PAGE_ID}-trend-slice",
                            data=[
                                {"value": "", "label": "Total"},
                                {"value": "physician", "label": "MD"},
                                {"value": "dept", "label": "Dept"},
                            ],
                            value="",
                            size="xs",
                        ),
                    ],
                    extra_controls=[
                        dmc.SegmentedControl(
                            id=f"{PAGE_ID}-trend-agg",
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
                    f"{PAGE_ID}-chart-cumul",
                    "Cumulative Volume",
                    settings_id=f"{PAGE_ID}-cumul",
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
                            id=f"{PAGE_ID}-cumul-mode",
                            data=[
                                {"value": "prior", "label": "Prior Periods"},
                                {"value": "slice", "label": "Slice By"},
                            ],
                            value="prior",
                            size="xs",
                        ),
                        dmc.SegmentedControl(
                            id=f"{PAGE_ID}-cumul-period-type",
                            data=[
                                {"value": "calendar", "label": "Calendar"},
                                {"value": "rolling", "label": "Rolling"},
                            ],
                            value="calendar",
                            size="xs",
                        ),
                        dmc.SegmentedControl(
                            id=f"{PAGE_ID}-cumul-slice",
                            data=[
                                {"value": "physician", "label": "MD"},
                                {"value": "dept", "label": "Dept"},
                            ],
                            value="physician",
                            size="xs",
                            orientation="horizontal",
                            style={"display": "none"},
                        ),
                    ],
                ),
                span={"base": 12, "md": 6},
            ),
        ]),

        # Tab content panels (detail grids + Pluvicto queue)
        dmc.Box(children=[
            html.Div(id=f"{PAGE_ID}-tab-content-pluvicto",
                     children=dmc.Stack(gap=16, children=_pluvicto_panel()),
                     style={"display": "block"}),
            html.Div(id=f"{PAGE_ID}-tab-content-spacer",
                     children=dmc.Stack(gap=16, children=_spacer_panel()),
                     style={"display": "none"}),
            html.Div(id=f"{PAGE_ID}-tab-content-lupron",
                     children=dmc.Stack(gap=16, children=_tab_panel("lupron")),
                     style={"display": "none"}),
            html.Div(id=f"{PAGE_ID}-tab-content-ldr",
                     children=dmc.Stack(gap=16, children=_tab_panel("ldr")),
                     style={"display": "none"}),
            html.Div(id=f"{PAGE_ID}-tab-content-volstudy",
                     children=dmc.Stack(gap=16, children=_tab_panel("volstudy")),
                     style={"display": "none"}),
            html.Div(id=f"{PAGE_ID}-tab-content-seeds",
                     children=dmc.Stack(gap=16, children=_tab_panel("seeds")),
                     style={"display": "none"}),
        ]),

        # Stores for chart data
        dcc.Store(id=f"{PAGE_ID}-store-kpi-sparklines"),
        dcc.Store(id=f"{PAGE_ID}-store-trend"),
        dcc.Store(id=f"{PAGE_ID}-store-cumul"),
        dcc.Store(id=f"{PAGE_ID}-table-filter-rows"),  # filtered row indices from grid

        # Interval for periodic refresh
        dcc.Interval(id=f"{PAGE_ID}-interval", interval=300_000, n_intervals=0),
    ],
)


# ---------------------------------------------------------------------------
# Filter Callbacks
# ---------------------------------------------------------------------------

def _register_filter_callbacks():
    """Register all filter-sync callbacks."""

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
        ClientsideFunction(namespace="proceduresDateSlider", function_name="syncSlider"),
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

    # --- Trigger labels ---
    clientside_callback(
        """function(val) {
            if (!val) return "Physician";
            return val.split(", ")[0];
        }""",
        Output(f"{PAGE_ID}-physician-trigger", "children"),
        Input(f"{PAGE_ID}-filter-physician", "value"),
    )

    # --- Clear-button visibility ---
    clientside_callback(
        """function(val) { return val ? {"display": "inline-flex"} : {"display": "none"}; }""",
        Output(f"{PAGE_ID}-physician-clear", "style"),
        Input(f"{PAGE_ID}-filter-physician", "value"),
    )

    # --- Clear-button actions ---
    clientside_callback(
        """function(n) { return null; }""",
        Output(f"{PAGE_ID}-filter-physician", "value", allow_duplicate=True),
        Input(f"{PAGE_ID}-physician-clear", "n_clicks"),
        prevent_initial_call=True,
    )


_register_filter_callbacks()


# ---------------------------------------------------------------------------
# Tab content visibility (show active tab's detail panel, hide others)
# ---------------------------------------------------------------------------
_TAB_CONTENT_IDS = [f"{PAGE_ID}-tab-content-{key}" for _, key in _CAT_TAB_PAIRS]

clientside_callback(
    """function(tab) {
        var keys = %s;
        return keys.map(function(k) {
            return k === tab ? {"display": "block"} : {"display": "none"};
        });
    }""" % str([key for _, key in _CAT_TAB_PAIRS]),
    [Output(cid, "style") for cid in _TAB_CONTENT_IDS],
    Input(f"{PAGE_ID}-tabs", "value"),
)


# ---------------------------------------------------------------------------
# Cumulative mode toggle: show/hide slice selector + period-type toggle
# ---------------------------------------------------------------------------
clientside_callback(
    """function(mode) {
        var isSlice = mode === "slice";
        var sliceStyle = isSlice ? {"display": "inline-flex"} : {"display": "none"};
        var ptStyle = isSlice ? {"display": "none"} : {};
        return [sliceStyle, ptStyle];
    }""",
    Output(f"{PAGE_ID}-cumul-slice", "style"),
    Output(f"{PAGE_ID}-cumul-period-type", "style"),
    Input(f"{PAGE_ID}-cumul-mode", "value"),
)

# Hide "Total" slice option in line/area mode (only useful for bar)
_PROC_CUMUL_SLICE_ALL = [
    {"value": "total", "label": "Total"},
    {"value": "physician", "label": "MD"},
    {"value": "dept", "label": "Dept"},
]
_PROC_CUMUL_SLICE_NO_TOTAL = [o for o in _PROC_CUMUL_SLICE_ALL if o["value"] != "total"]

clientside_callback(
    """function(chartType, sliceVal) {
        var all = %s;
        var noTotal = %s;
        if (chartType === "bar") {
            return [all, window.dash_clientside.no_update];
        }
        var newVal = (sliceVal === "total") ? "physician" : window.dash_clientside.no_update;
        return [noTotal, newVal];
    }""" % (str(_PROC_CUMUL_SLICE_ALL).replace("'", '"'), str(_PROC_CUMUL_SLICE_NO_TOTAL).replace("'", '"')),
    Output(f"{PAGE_ID}-cumul-slice", "data"),
    Output(f"{PAGE_ID}-cumul-slice", "value", allow_duplicate=True),
    Input(f"{PAGE_ID}-cumul-settings-type", "value"),
    State(f"{PAGE_ID}-cumul-slice", "value"),
    prevent_initial_call=True,
)

_SLICE_CLASS_JS = """function(val) {
    return (val && val !== "total") ? "slice-group-active" : "slice-total-active";
}"""

clientside_callback(
    _SLICE_CLASS_JS,
    Output(f"{PAGE_ID}-cumul-slice", "className"),
    Input(f"{PAGE_ID}-cumul-slice", "value"),
)

_HIDE_STACK_JS = """function(sliceVal, chartType) {
    var single = !sliceVal || sliceVal === "total" || sliceVal === "";
    var noStack = chartType === "line";
    return (single || noStack) ? {"display": "none"} : {};
}"""

for _slice_id, _settings_id in [
    (f"{PAGE_ID}-trend-slice", f"{PAGE_ID}-trend"),
]:
    clientside_callback(
        _HIDE_STACK_JS,
        Output(f"{_settings_id}-settings-stack-wrap", "style", allow_duplicate=True),
        Input(_slice_id, "value"),
        Input(f"{_settings_id}-settings-type", "value"),
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
    Output(f"{PAGE_ID}-cumul-settings-stack-wrap", "style"),
    Input(f"{PAGE_ID}-cumul-mode", "value"),
    Input(f"{PAGE_ID}-cumul-slice", "value"),
    Input(f"{PAGE_ID}-cumul-settings-type", "value"),
)


# ---------------------------------------------------------------------------
# Dynamic physician chip population
# ---------------------------------------------------------------------------
@callback(
    Output(f"{PAGE_ID}-filter-physician", "children"),
    Input(f"{PAGE_ID}-interval", "n_intervals"),
    Input(f"{PAGE_ID}-filter-daterange", "start_date"),
    Input(f"{PAGE_ID}-filter-daterange", "end_date"),
    Input(f"{PAGE_ID}-filter-department", "value"),
    Input(f"{PAGE_ID}-filter-status", "value"),
    Input(f"{PAGE_ID}-date-slider", "value"),
    Input(f"{PAGE_ID}-tabs", "value"),
)
def _populate_physician_chips(_n, range_start, range_end, dept_filter, status_filter, slider_val, active_tab):
    from data.loader import load_procedures
    try:
        df = load_procedures()
    except Exception:
        return []
    if df.empty or "AppointmentPhysician" not in df.columns:
        return []
    start, end = _get_date_range(slider_val, [range_start, range_end])
    dff = _filter_data(df, start, end, dept_filter, None, status_filter)
    # Filter to active procedure category tab
    _key_to_cat = {key: cat for cat, key in _CAT_TAB_PAIRS}
    active_cat = _key_to_cat.get(active_tab)
    if active_cat and "ProcedureCategory" in dff.columns:
        dff = dff[dff["ProcedureCategory"] == active_cat]
    from components.filter_bar import physician_short_name
    mds = sorted(dff["AppointmentPhysician"].dropna().unique())
    return [
        dmc.Chip(physician_short_name(md), value=md, size="xs", variant="filled")
        for md in mds
    ]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_date_range(slider_val, daterange):
    """Calculate start/end dates from slider or explicit daterange."""
    if daterange and len(daterange) == 2 and daterange[0] and daterange[1]:
        return pd.Timestamp(daterange[0]), pd.Timestamp(daterange[1])
    if slider_val and len(slider_val) == 2:
        start = idx_to_date(slider_val[0])
        end = idx_to_date(slider_val[1], end_of_month=True)
        return start, end
    return pd.Timestamp("2000-01-01"), pd.Timestamp("2099-12-31")


def _apply_grid_row_filter(dff, grid_rows):
    """Filter dff to only rows matching the grid's visible row indices."""
    if grid_rows is None or dff is None or dff.empty:
        return dff
    idx_set = set(int(i) for i in grid_rows)
    return dff.loc[dff.index.isin(idx_set)].reset_index(drop=True)


def _filter_data(df, start, end, dept_filter, physician_filter, status_filter):
    """Apply common filters to procedures DataFrame."""
    dff = df.copy()
    if "ScheduledDateTime" in dff.columns:
        dff = dff[dff["ScheduledDateTime"].notna()]
        dff = dff[(dff["ScheduledDateTime"] >= start) & (dff["ScheduledDateTime"] <= end)]
    if dept_filter and "Department" in dff.columns:
        dff = dff[dff["Department"].isin(dept_filter)]
    if physician_filter and "AppointmentPhysician" in dff.columns:
        dff = dff[dff["AppointmentPhysician"] == physician_filter]
    if status_filter and status_filter != "all" and "ActivityStatus" in dff.columns:
        if status_filter == "open":
            dff = dff[dff["ActivityStatus"] == "Open"]
        elif status_filter == "completed":
            dff = dff[dff["ActivityStatus"] == "Manually Completed"]
    return dff


# ---------------------------------------------------------------------------
# KPI helpers
# ---------------------------------------------------------------------------

def _build_upcoming_card(df_all, cat_name, accent_color, n=3):
    """Build an 'upcoming' KPI card showing next N scheduled with date + MD."""
    if df_all.empty or "ProcedureCategory" not in df_all.columns:
        return _upcoming_paper(f"Upcoming {cat_name}", "0", [], accent_color)

    cat_df = df_all[df_all["ProcedureCategory"] == cat_name]
    if "ActivityStatus" in cat_df.columns:
        upcoming = cat_df[cat_df["ActivityStatus"] == "Open"].copy()
    else:
        upcoming = pd.DataFrame()

    count = len(upcoming)
    if upcoming.empty:
        return _upcoming_paper(f"Upcoming {cat_name}", "0", [], accent_color)

    # Sort by date, take next N
    if "ScheduledDateTime" in upcoming.columns:
        upcoming = upcoming.sort_values("ScheduledDateTime").head(n)

    # Build detail lines
    lines = []
    for _, row in upcoming.iterrows():
        dt = row.get("ScheduledDateTime")
        md = row.get("AppointmentPhysician", "")
        dt_str = dt.strftime("%m/%d") if pd.notna(dt) else ""
        md_short = md.split(", ")[0] if md and pd.notna(md) else ""
        line = f"{dt_str} — {md_short}" if md_short else dt_str
        if line:
            lines.append(line)

    return _upcoming_paper(f"Upcoming {cat_name}", f"{count:,}", lines, accent_color)


def _upcoming_paper(label, value, date_lines, accent_color):
    """Build a KPI-style Paper for upcoming procedures with dates on separate lines."""
    children = [
        dmc.Text(label, size="xs", c=NEUTRAL["text_secondary"], fw=500),
        dmc.Text(str(value), size="xl", fw=700, c=NEUTRAL["text_primary"], lh=1.2),
    ]
    if date_lines:
        for line in date_lines:
            children.append(
                dmc.Text(line, size="xs", c=NEUTRAL["text_muted"], lh=1.4)
            )
    return dmc.Paper(
        children=[dmc.Stack(children=children, gap=2)],
        pt="sm", px="md", pb=4, radius="md", shadow="xs", withBorder=True,
        style={"borderLeft": f"4px solid {accent_color}" if accent_color else "none"},
    )


def _build_sparkline_kpi(dff, cat_name, accent_color, df_all=None, start=None, end=None, spark_id=None):
    """Build a KPI card with sparkline and trend comparison for a category."""
    if "ProcedureCategory" not in dff.columns:
        return kpi_card(cat_name, "0", accent_color=accent_color, sparkline_id=spark_id), None

    sub = dff[dff["ProcedureCategory"] == cat_name]
    count = len(sub)

    # Trend comparison vs prior period of same length
    trend_text, trend_dir = None, None
    if df_all is not None and start is not None and end is not None:
        period_days = (end - start).days
        if period_days > 0:
            prior_end = start - pd.Timedelta(days=1)
            prior_start = prior_end - pd.Timedelta(days=period_days)
            prior_df = df_all[
                (df_all["ScheduledDateTime"] >= prior_start)
                & (df_all["ScheduledDateTime"] <= prior_end)
            ]
            prior_count = len(prior_df[prior_df["ProcedureCategory"] == cat_name])
            if prior_count > 0:
                pct = (count - prior_count) / prior_count * 100
                trend_text = f"{abs(pct):.0f}% vs prior"
                trend_dir = "up" if pct > 0 else ("down" if pct < 0 else None)
            elif count > 0:
                trend_text = "New"
                trend_dir = "up"

    spark_data = None
    if not sub.empty and "ScheduledDateTime" in sub.columns:
        weekly = sub.set_index("ScheduledDateTime").resample("W").size()
        if len(weekly) > 1:
            spark_data = {
                "values": weekly.tolist(),
                "labels": [d.isoformat() for d in weekly.index],
                "color": accent_color,
            }

    return kpi_card(
        cat_name, f"{count:,}",
        trend_text=trend_text,
        trend_direction=trend_dir,
        sparkline_id=spark_id,
        accent_color=accent_color,
    ), spark_data


def _build_lead_time_kpi(dff, categories, df_all=None, start=None, end=None, spark_id=None):
    """Build avg lead time KPI for specific categories with trend comparison."""
    if dff.empty or "ProcedureCategory" not in dff.columns or "DaysFromCreatedToAppt" not in dff.columns:
        return kpi_card("Avg Lead Time", "N/A", accent_color=PRIMARY, sparkline_id=spark_id), None

    sub = dff[dff["ProcedureCategory"].isin(categories)]
    vals = sub["DaysFromCreatedToAppt"].dropna()
    if vals.empty:
        return kpi_card("Avg Lead Time", "N/A", accent_color=PRIMARY, sparkline_id=spark_id), None

    avg = round(vals.mean(), 1)

    # Trend comparison vs prior period (lower lead time = better, so invert direction)
    trend_text, trend_dir = None, None
    if df_all is not None and start is not None and end is not None:
        period_days = (end - start).days
        if period_days > 0:
            prior_end = start - pd.Timedelta(days=1)
            prior_start = prior_end - pd.Timedelta(days=period_days)
            prior_df = df_all[
                (df_all["ScheduledDateTime"] >= prior_start)
                & (df_all["ScheduledDateTime"] <= prior_end)
            ]
            prior_sub = prior_df[prior_df["ProcedureCategory"].isin(categories)]
            prior_vals = prior_sub["DaysFromCreatedToAppt"].dropna()
            if not prior_vals.empty:
                prior_avg = prior_vals.mean()
                if prior_avg > 0:
                    pct = (avg - prior_avg) / prior_avg * 100
                    trend_text = f"{abs(pct):.0f}% vs prior"
                    # Lower lead time is better → increase = bad (down/red), decrease = good (up/green)
                    trend_dir = "down" if pct > 0 else ("up" if pct < 0 else None)

    # Sparkline of weekly avg lead time
    t = sub[sub["DaysFromCreatedToAppt"].notna()].copy()
    spark_vals, spark_labels = None, None
    if not t.empty and "ScheduledDateTime" in t.columns:
        weekly = t.set_index("ScheduledDateTime")["DaysFromCreatedToAppt"].resample("W").mean()
        fv, fl = [], []
        for v, d in zip(weekly, weekly.index):
            if pd.notna(v):
                fv.append(round(v, 1))
                fl.append(pd.Timestamp(d))
        if len(fv) > 1:
            spark_vals = fv
            spark_labels = fl

    spark_data = None
    if spark_vals and len(spark_vals) > 1:
        spark_data = {
            "values": spark_vals,
            "labels": [d.isoformat() for d in spark_labels],
            "color": PRIMARY,
            "hover_fmt": "%{x|%b %d}: %{customdata:.1f} days<extra></extra>",
        }

    return kpi_card(
        "Avg Lead Time", f"{avg} days",
        trend_text=trend_text,
        trend_direction=trend_dir,
        sparkline_id=spark_id,
        accent_color=PRIMARY,
    ), spark_data


# ---------------------------------------------------------------------------
# Chart data builders (census format for clientside rendering)
# ---------------------------------------------------------------------------

def _empty_trend(cat_name=""):
    msg = f"No {cat_name} during this period" if cat_name else "No data for this period"
    return {
        "dates": [], "series": [],
        "stacked": False, "yTitle": "Count", "height": 380,
        "emptyMessage": msg,
    }


def _prepare_trend_data(dff, cat_name, agg="M", slice_by=""):
    """Build census-format data for volume trend chart.

    Returns dict compatible with census.smoothChartWithType clientside function.
    """
    if dff.empty or "ScheduledDateTime" not in dff.columns:
        return _empty_trend(cat_name)

    t = dff.copy()
    period_code = {"W": "W", "Y": "Y"}.get(agg, "M")
    t["period"] = t["ScheduledDateTime"].dt.to_period(period_code).dt.to_timestamp()
    data_periods = sorted(t["period"].unique())

    if not data_periods:
        return _empty_trend(cat_name)

    # Build full period range (including empty periods) so gaps are visible
    freq_map = {"W": "W-MON", "Y": "YS", "M": "MS"}
    freq = freq_map.get(agg, "MS")
    # Pad single-point ranges so the x-axis renders properly
    rng_start = data_periods[0]
    rng_end = data_periods[-1]
    if rng_start == rng_end:
        rng_start = rng_start - pd.tseries.frequencies.to_offset(freq)
        rng_end = rng_end + pd.tseries.frequencies.to_offset(freq)
    all_periods = pd.date_range(rng_start, rng_end, freq=freq)
    all_periods = sorted(set(all_periods) | set(data_periods))

    cat_color = _CATEGORY_COLORS.get(cat_name, PRIMARY)

    if not slice_by:
        counts = t.groupby("period").size()
        series = [{
            "name": cat_name,
            "values": [int(counts.get(p, 0)) for p in all_periods],
            "color": cat_color,
        }]
        stacked = False
    elif slice_by == "physician" and "AppointmentPhysician" in t.columns:
        physicians = sorted(t["AppointmentPhysician"].dropna().unique())
        colors = list(CHART_COLORWAY) * (len(physicians) // len(CHART_COLORWAY) + 1)
        series = []
        for i, md in enumerate(physicians):
            sub = t[t["AppointmentPhysician"] == md]
            counts = sub.groupby("period").size()
            display = md.split(", ")[0] if "," in md else md
            series.append({
                "name": display,
                "values": [int(counts.get(p, 0)) for p in all_periods],
                "color": colors[i],
            })
        stacked = True
    elif slice_by == "dept" and "Department" in t.columns:
        depts = sorted(t["Department"].dropna().unique())
        series = []
        for dept in depts:
            sub = t[t["Department"] == dept]
            counts = sub.groupby("period").size()
            series.append({
                "name": dept,
                "values": [int(counts.get(p, 0)) for p in all_periods],
                "color": DEPARTMENT_COLORS.get(dept, CHART_COLORWAY[len(series) % len(CHART_COLORWAY)]),
            })
        stacked = True
    else:
        counts = t.groupby("period").size()
        series = [{
            "name": cat_name,
            "values": [int(counts.get(p, 0)) for p in all_periods],
            "color": cat_color,
        }]
        stacked = False

    # If every series is all zeros, show empty message instead of flat line
    if all(sum(s["values"]) == 0 for s in series):
        return _empty_trend(cat_name)

    return {
        "dates": [d.isoformat() for d in all_periods],
        "series": series,
        "stacked": stacked,
        "hideLegend": len(series) <= 1,
        "yTitle": "Count",
        "height": 380,
    }


def _build_day_index_ticks(start_norm, n_days, max_ticks=12):
    """Build tick positions/labels for a day-index x-axis."""
    candidates = []

    # Daily (only if few enough days)
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

    # Monthly (1st of each month)
    pos, lbl = [], []
    for i in range(n_days):
        d = start_norm + pd.Timedelta(days=i)
        if d.day == 1 or i == 0:
            pos.append(i)
            lbl.append(d.strftime("%b '%y") if d.month == 1 or i == 0 else d.strftime("%b"))
    candidates.append((pos, lbl))

    # Quarterly (Jan, Apr, Jul, Oct)
    pos, lbl = [], []
    for i in range(n_days):
        d = start_norm + pd.Timedelta(days=i)
        if (d.day == 1 and d.month in (1, 4, 7, 10)) or i == 0:
            pos.append(i)
            lbl.append(d.strftime("%b '%y"))
    candidates.append((pos, lbl))

    # Yearly (Jan 1st)
    pos, lbl = [], []
    for i in range(n_days):
        d = start_norm + pd.Timedelta(days=i)
        if (d.day == 1 and d.month == 1) or i == 0:
            pos.append(i)
            lbl.append(str(d.year))
    candidates.append((pos, lbl))

    # Pick the candidate with the most ticks that still fits
    best = candidates[-1]
    for c in candidates:
        if len(c[0]) <= max_ticks:
            best = c
            break
    return best


def _prepare_cumul_data(dff_all, cat_name, start, end, date_preset="12mo",
                        slice_by="", mode="prior", max_prior=5,
                        period_type="calendar"):
    """Build cumulative chart data for clientside rendering.

    mode="prior": Current period + prior periods overlay (day-index x-axis).
    mode="slice": Current period only, split by physician or department.
    """
    _EMPTY_CUMUL = {
        "mode": "prior", "startDate": start.normalize().isoformat(),
        "dayIndices": [0], "tickPositions": [], "tickLabels": [],
        "current": {"label": "", "values": [0], "color": PRIMARY, "endpoint": 0},
        "prior": [], "sliceBreakdown": {"periods": [], "slices": []},
        "height": 380, "yTitle": f"Cumulative {cat_name}",
    }

    if dff_all.empty or "ScheduledDateTime" not in dff_all.columns:
        return _EMPTY_CUMUL

    from utils.cumulative_current_year import setup_current_year_range, apply_current_year_projection
    today = pd.Timestamp.now().normalize()
    start, end, _cy_last_actual = setup_current_year_range(date_preset, mode, start, end)
    if _cy_last_actual is None and end.normalize() > today:
        end = today

    period_days = (end - start).days + 1
    # Force rolling when period exceeds 1 year (calendar shifts would overlap)
    if period_days > 365 and period_type == "calendar":
        period_type = "rolling"
    if period_days < 2:
        return _EMPTY_CUMUL

    cat_color = _CATEGORY_COLORS.get(cat_name, PRIMARY)

    def _cumulative_for_window(df, w_start, w_end):
        mask = (df["ScheduledDateTime"] >= w_start) & (df["ScheduledDateTime"] <= w_end)
        sub = df.loc[mask]
        if sub.empty:
            return []
        daily = sub.groupby(sub["ScheduledDateTime"].dt.normalize()).size()
        idx = pd.date_range(w_start.normalize(), w_end.normalize(), freq="D")
        daily = daily.reindex(idx, fill_value=0)
        return daily.cumsum().tolist()

    start_norm = start.normalize()
    n_days = period_days
    day_indices = list(range(n_days))
    tick_positions, tick_labels = _build_day_index_ticks(start_norm, n_days)

    if mode == "prior":
        # Current window cumulative
        current_vals = _cumulative_for_window(dff_all, start, end) or [0] * n_days
        if len(current_vals) < n_days:
            current_vals = current_vals + [None] * (n_days - len(current_vals))

        data_min = dff_all["ScheduledDateTime"].min()

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

        current_label = _period_label(start, end)

        # Build prior windows
        prior = []
        last_prior_start = None
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
                vals = _cumulative_for_window(dff_all, p_start, p_end)
                if vals and any(v > 0 for v in vals):
                    if len(vals) < n_days:
                        vals = vals + [vals[-1] if vals else 0] * (n_days - len(vals))
                    elif len(vals) > n_days:
                        vals = vals[:n_days]
                    prior.append({"label": _period_label(p_start, p_end), "values": vals, "color": PRIOR_PERIOD_COLORS[min(i - 1, len(PRIOR_PERIOD_COLORS) - 1)]})
                    last_prior_start = p_start

        # Metadata for client-side control updates
        has_partial = (last_prior_start is not None
                       and last_prior_start.normalize() < data_min.normalize())
        _prior_meta = {
            "periodDays": period_days,
            "maxAvailablePriors": len(prior),
            "hasPartialPrior": has_partial,
        }

        _result = {
            "mode": "prior",
            "startDate": start_norm.isoformat(),
            "dayIndices": day_indices,
            "tickPositions": tick_positions,
            "tickLabels": tick_labels,
            "current": {
                "label": current_label,
                "values": current_vals,
                "color": cat_color,
                "endpoint": next((v for v in reversed(current_vals) if v is not None), 0),
            },
            "prior": prior,
            "sliceBreakdown": {"periods": [], "slices": []},
            "height": 380,
            "yTitle": f"Cumulative {cat_name}",
            **_prior_meta,
        }
        if _cy_last_actual is not None:
            apply_current_year_projection(_result, _cy_last_actual, start)
        return _result

    # --- Slice mode ---
    mask = (dff_all["ScheduledDateTime"] >= start) & (dff_all["ScheduledDateTime"] <= end)
    dff_period = dff_all.loc[mask]
    dates_range = pd.date_range(start.normalize(), end.normalize(), freq="D")

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
    if slice_by == "dept" and "Department" in dff_period.columns:
        for dept in sorted(dff_period["Department"].dropna().unique()):
            sub = dff_period[dff_period["Department"] == dept]
            daily = sub.groupby(sub["ScheduledDateTime"].dt.normalize()).size()
            daily = daily.reindex(dates_range, fill_value=0)
            series.append({
                "name": dept,
                "values": _trimmed_cumsum(daily),
                "color": DEPARTMENT_COLORS.get(dept, CHART_COLORWAY[len(series) % len(CHART_COLORWAY)]),
            })
    elif slice_by == "physician" and "AppointmentPhysician" in dff_period.columns:
        for md in sorted(dff_period["AppointmentPhysician"].dropna().unique()):
            sub = dff_period[dff_period["AppointmentPhysician"] == md]
            daily = sub.groupby(sub["ScheduledDateTime"].dt.normalize()).size()
            daily = daily.reindex(dates_range, fill_value=0)
            display = md.split(", ")[0] if "," in md else md
            series.append({
                "name": display,
                "values": _trimmed_cumsum(daily),
                "color": CHART_COLORWAY[len(series) % len(CHART_COLORWAY)],
            })
    else:
        # Fallback: total cumulative
        daily = dff_period.groupby(dff_period["ScheduledDateTime"].dt.normalize()).size()
        daily = daily.reindex(dates_range, fill_value=0)
        series.append({
            "name": cat_name,
            "values": daily.cumsum().tolist(),
            "color": cat_color,
        })

    # Build dates as ISO strings for line/area x-axis
    dates_iso = [d.isoformat() for d in dates_range]

    return {
        "mode": "slice",
        "startDate": start_norm.isoformat(),
        "dayIndices": day_indices,
        "dates": dates_iso,
        "tickPositions": tick_positions,
        "tickLabels": tick_labels,
        "current": {"label": cat_name, "values": [], "color": cat_color, "endpoint": 0},
        "prior": [],
        "sliceBreakdown": {"periods": [], "slices": []},
        "series": series,
        "stacked": False,
        "height": 380,
        "yTitle": f"Cumulative {cat_name}",
        "periodDays": period_days,
        "maxAvailablePriors": 0,
        "hasPartialPrior": False,
    }


def _build_tab_grid_data(dff):
    """Build AG Grid column defs and row data for a category tab."""
    cols = apply_phi_grid_rules([
        {"field": "ScheduledDateTime", "headerName": "Date", "minWidth": 120,
         "sort": "desc"},
        {"field": "PatientFullName", "headerName": "Patient", "minWidth": 160},
        {"field": "AppointmentPhysician", "headerName": "Physician", "minWidth": 130},
        {"field": "DaysFromCreatedToAppt", "headerName": "Lead (days)", "minWidth": 90},
        {"field": "DurationMinutes", "headerName": "Duration (min)", "minWidth": 100},
        {"field": "ActivityStatus", "headerName": "Status", "minWidth": 110},
        {"field": "Department", "headerName": "Dept", "minWidth": 90},
        {"field": "ReferringPhysician", "headerName": "Referring MD", "minWidth": 130},
        {"field": "AppointmentNotes", "headerName": "Appt Notes", "minWidth": 200,
         "wrapText": True, "autoHeight": True},
    ])
    if dff.empty:
        return cols, []
    display_cols = [c["field"] for c in cols if c["field"] in dff.columns]
    rows = dff[display_cols].copy()
    if "ScheduledDateTime" in rows.columns:
        rows["ScheduledDateTime"] = rows["ScheduledDateTime"].dt.strftime("%m/%d/%Y")
    rows = sanitize_for_grid(rows)
    return cols, rows.to_dict("records")


# ---------------------------------------------------------------------------
# Pluvicto Queue
# ---------------------------------------------------------------------------

def _build_pluvicto_queue(status_filter="all"):
    """Build the Pluvicto patient queue as a slim DMC table.

    status_filter: "all", "in_progress", or "completed"
    """
    from data.loader import load_procedures, load_pluvicto_workflow

    try:
        procs = load_procedures()
        wf = load_pluvicto_workflow()
    except Exception:
        return dmc.Text("No data available", size="sm", c=NEUTRAL["text_muted"])

    plv_procs = procs[procs["ProcedureCategory"] == "Pluvicto"] if "ProcedureCategory" in procs.columns else pd.DataFrame()
    patients = {}

    # From workflow: consult date and stage
    if not wf.empty and "PatientId" in wf.columns:
        for pid in wf["PatientId"].unique():
            pw = wf[wf["PatientId"] == pid].sort_values("StageOrder" if "StageOrder" in wf.columns else "StageDateTime")
            exam_row = pw[pw["StageName"] == "Exam"] if "StageName" in pw.columns else pd.DataFrame()
            consult_date = exam_row["StageDateTime"].min() if not exam_row.empty and "StageDateTime" in exam_row.columns else None
            latest_stage = pw.iloc[-1]["StageName"] if "StageName" in pw.columns and len(pw) > 0 else "Unknown"
            patient_name = pw.iloc[0].get("PatientName", pw.iloc[0].get("PatientFullName", "Unknown"))
            # Consult MD from the Exam row
            consult_md = ""
            if not exam_row.empty and "AppointmentPhysician" in exam_row.columns:
                md_val = exam_row["AppointmentPhysician"].dropna()
                if not md_val.empty:
                    consult_md = md_val.iloc[0].split(", ")[0]
            patients[pid] = {
                "Patient": patient_name,
                "Consult": consult_date.strftime("%m/%d/%y") if pd.notna(consult_date) else "",
                "Stage": latest_stage,
                "Physician": consult_md,
                "tx_dates": [],
            }

    # From procedures: treatment dates
    if not plv_procs.empty and "PatientId" in plv_procs.columns:
        for pid in plv_procs["PatientId"].unique():
            pp = plv_procs[plv_procs["PatientId"] == pid].sort_values("ScheduledDateTime")
            if pid not in patients:
                patients[pid] = {
                    "Patient": pp.iloc[0].get("PatientFullName", "Unknown"),
                    "Consult": "",
                    "Stage": "On Treatment",
                    "Physician": "",
                    "tx_dates": [],
                }
            rec = patients[pid]
            for _, row in pp.head(6).iterrows():
                tx_date = row.get("ScheduledDateTime")
                md_name = row.get("AppointmentPhysician", "")
                # Build initials from "Last, First" -> "FL"
                md_init = ""
                if md_name and pd.notna(md_name):
                    parts = [p.strip() for p in str(md_name).split(",")]
                    if len(parts) >= 2:
                        md_init = parts[1][0] + parts[0][0]  # First initial + Last initial
                    elif parts:
                        md_init = parts[0][0]
                rec["tx_dates"].append((tx_date if pd.notna(tx_date) else None, md_init))

            # Determine patient status: completed (all 6 done) vs in_progress
            n_completed = len(pp[pp["ActivityStatus"] == "Manually Completed"]) if "ActivityStatus" in pp.columns else 0
            n_total = len(pp)
            if n_total >= 6 and n_completed >= 6:
                rec["_status"] = "completed"
            else:
                rec["_status"] = "in_progress"

    # Patients only in workflow (no procedures yet) are "in_progress"
    for rec in patients.values():
        if "_status" not in rec:
            rec["_status"] = "in_progress"

    # Apply status filter
    if status_filter and status_filter != "all":
        patients = {pid: rec for pid, rec in patients.items() if rec["_status"] == status_filter}

    if not patients:
        return dmc.Text("No Pluvicto patients in queue", size="sm", c=NEUTRAL["text_muted"])

    today = pd.Timestamp.now().normalize()
    col_w = "10%"  # even width across 10 columns

    # Build table header
    headers = ["Patient", "Consult", "Stage", "Treatment 1", "Treatment 2", "Treatment 3", "Treatment 4", "Treatment 5", "Treatment 6", "MD"]
    head = dmc.TableThead(dmc.TableTr([
        dmc.TableTh(h, style={"fontSize": "11px", "color": NEUTRAL["text_secondary"],
                              "fontWeight": 600, "textTransform": "uppercase",
                              "padding": "6px 8px", "whiteSpace": "nowrap",
                              "width": col_w})
        for h in headers
    ]))

    # Colors for past vs future
    _DONE_COLOR = SEMANTIC_COLORS["success"]   # green
    _FUTURE_COLOR = NEUTRAL["text_muted"]      # gray
    _EMPTY_COLOR = NEUTRAL["border_light"]

    def _tx_cell(tx_info):
        """Render a Tx cell with color-coded dot: green=past, gray=future, empty=not scheduled.

        tx_info: (datetime, md_initials) tuple or None
        """
        base = {"fontSize": "13px", "padding": "5px 8px", "whiteSpace": "nowrap", "width": col_w}
        if tx_info is None:
            return dmc.TableTd(
                dmc.Text("—", size="sm", c=_EMPTY_COLOR),
                style=base,
            )
        dt, md_init = tx_info
        if dt is None:
            return dmc.TableTd(
                dmc.Text("—", size="sm", c=_EMPTY_COLOR),
                style=base,
            )
        is_past = dt.normalize() <= today
        dot_color = _DONE_COLOR if is_past else _FUTURE_COLOR
        label = dt.strftime("%m/%d/%y")
        if md_init:
            label += f" ({md_init})"
        return dmc.TableTd(
            dmc.Group(
                gap=6, align="center", wrap="nowrap",
                children=[
                    html.Span(style={
                        "width": "7px", "height": "7px", "borderRadius": "50%",
                        "backgroundColor": dot_color, "display": "inline-block",
                        "flexShrink": 0,
                    }),
                    dmc.Text(label, size="sm",
                             c=NEUTRAL["text_primary"] if is_past else _FUTURE_COLOR),
                ],
            ),
            style=base,
        )

    cell_style = {"fontSize": "13px", "padding": "5px 8px", "whiteSpace": "nowrap", "width": col_w}

    body_rows = []
    for rec in patients.values():
        tx = rec["tx_dates"]
        cells = [
            dmc.TableTd(rec["Patient"], style={**cell_style, "fontWeight": 500}),
            dmc.TableTd(rec["Consult"], style=cell_style),
            dmc.TableTd(rec["Stage"], style=cell_style),
        ]
        for i in range(6):
            cells.append(_tx_cell(tx[i] if i < len(tx) else None))
        cells.append(dmc.TableTd(rec["Physician"], style=cell_style))
        body_rows.append(dmc.TableTr(cells))

    body = dmc.TableTbody(body_rows)

    return dmc.Table(
        [head, body],
        striped=True,
        highlightOnHover=True,
        withTableBorder=False,
        withColumnBorders=False,
        horizontalSpacing="xs",
        verticalSpacing=4,
        style={"tableLayout": "fixed", "width": "100%"},
    )


# ---------------------------------------------------------------------------
# Rectal Spacer Queue
# ---------------------------------------------------------------------------

def _build_spacer_queue():
    """Build the Rectal Spacer upcoming patient queue as a slim DMC table.

    Shows only future/open patients — single procedure per patient.
    """
    from data.loader import load_procedures

    try:
        procs = load_procedures()
    except Exception:
        return dmc.Text("No data available", size="sm", c=NEUTRAL["text_muted"])

    if procs.empty or "ProcedureCategory" not in procs.columns:
        return dmc.Text("No data available", size="sm", c=NEUTRAL["text_muted"])

    spacer = procs[procs["ProcedureCategory"] == "Rectal Spacer"].copy()
    if spacer.empty:
        return dmc.Text("No Rectal Spacer patients in queue", size="sm", c=NEUTRAL["text_muted"])

    # Only upcoming (open) appointments
    if "ActivityStatus" in spacer.columns:
        spacer = spacer[spacer["ActivityStatus"] == "Open"]
    if spacer.empty:
        return dmc.Text("No upcoming Rectal Spacer patients", size="sm", c=NEUTRAL["text_muted"])

    # Sort by date
    if "ScheduledDateTime" in spacer.columns:
        spacer = spacer.sort_values("ScheduledDateTime")

    today = pd.Timestamp.now().normalize()

    _FUTURE_COLOR = NEUTRAL["text_muted"]
    _DONE_COLOR = SEMANTIC_COLORS["success"]

    cell_style = {"fontSize": "13px", "padding": "5px 8px", "whiteSpace": "nowrap"}

    headers = ["Patient", "Scheduled Date", "Physician", "Dept", "Lead (days)", "Referring MD"]
    head = dmc.TableThead(dmc.TableTr([
        dmc.TableTh(h, style={"fontSize": "11px", "color": NEUTRAL["text_secondary"],
                              "fontWeight": 600, "textTransform": "uppercase",
                              "padding": "6px 8px", "whiteSpace": "nowrap"})
        for h in headers
    ]))

    body_rows = []
    for _, row in spacer.iterrows():
        dt = row.get("ScheduledDateTime")
        is_past = pd.notna(dt) and dt.normalize() <= today
        dot_color = _DONE_COLOR if is_past else _FUTURE_COLOR
        dt_str = dt.strftime("%m/%d/%y") if pd.notna(dt) else ""
        md = row.get("AppointmentPhysician", "")
        md_short = md.split(", ")[0] if md and pd.notna(md) else ""
        dept = row.get("Department", "")
        dept_str = dept if pd.notna(dept) else ""
        lead = row.get("DaysFromCreatedToAppt")
        lead_str = f"{int(lead)}" if pd.notna(lead) else ""
        ref_md = row.get("ReferringPhysician", "")
        ref_str = ref_md if pd.notna(ref_md) else ""
        patient = row.get("PatientFullName", "Unknown")

        # Date cell with colored dot
        date_cell = dmc.TableTd(
            dmc.Group(
                gap=6, align="center", wrap="nowrap",
                children=[
                    html.Span(style={
                        "width": "7px", "height": "7px", "borderRadius": "50%",
                        "backgroundColor": dot_color, "display": "inline-block",
                        "flexShrink": 0,
                    }),
                    dmc.Text(dt_str, size="sm",
                             c=NEUTRAL["text_primary"] if is_past else _FUTURE_COLOR),
                ],
            ),
            style=cell_style,
        )

        body_rows.append(dmc.TableTr([
            dmc.TableTd(patient, style={**cell_style, "fontWeight": 500}),
            date_cell,
            dmc.TableTd(md_short, style=cell_style),
            dmc.TableTd(dept_str, style=cell_style),
            dmc.TableTd(lead_str, style={**cell_style, "textAlign": "right"}),
            dmc.TableTd(ref_str, style=cell_style),
        ]))

    body = dmc.TableTbody(body_rows)

    return dmc.Table(
        [head, body],
        striped=True,
        highlightOnHover=True,
        withTableBorder=False,
        withColumnBorders=False,
        horizontalSpacing="xs",
        verticalSpacing=4,
    )


# ---------------------------------------------------------------------------
# Main Server Callback
# ---------------------------------------------------------------------------

# Build output list: KPIs + stores + per-tab grids + Pluvicto queue
_OUTPUTS = [
    # 5 KPIs
    Output(f"{PAGE_ID}-kpi-pluvicto", "children"),
    Output(f"{PAGE_ID}-kpi-upcoming-pluv", "children"),
    Output(f"{PAGE_ID}-kpi-spacer", "children"),
    Output(f"{PAGE_ID}-kpi-upcoming-spacer", "children"),
    Output(f"{PAGE_ID}-kpi-lead-time", "children"),
    # Stores (for clientside rendering)
    Output(f"{PAGE_ID}-store-kpi-sparklines", "data"),
    Output(f"{PAGE_ID}-store-trend", "data"),
    Output(f"{PAGE_ID}-store-cumul", "data"),
]
# Per-tab: grid columnDefs, grid rowData (no more per-tab chart figures)
for _cat_name, _cat_key in _CAT_TAB_PAIRS:
    _OUTPUTS.append(Output(f"{PAGE_ID}-tab-grid-{_cat_key}", "columnDefs"))
    _OUTPUTS.append(Output(f"{PAGE_ID}-tab-grid-{_cat_key}", "rowData"))
# Pluvicto queue + Spacer queue
_OUTPUTS.append(Output(f"{PAGE_ID}-pluvicto-queue", "children"))
_OUTPUTS.append(Output(f"{PAGE_ID}-spacer-queue", "children"))


@callback(
    *_OUTPUTS,
    Input(f"{PAGE_ID}-interval", "n_intervals"),
    Input(f"{PAGE_ID}-filter-daterange", "start_date"),
    Input(f"{PAGE_ID}-filter-daterange", "end_date"),
    Input(f"{PAGE_ID}-filter-department", "value"),
    Input(f"{PAGE_ID}-filter-physician", "value"),
    Input(f"{PAGE_ID}-filter-status", "value"),
    Input(f"{PAGE_ID}-date-slider", "value"),
    Input(f"{PAGE_ID}-pluvicto-queue-filter", "value"),
    Input(f"{PAGE_ID}-tabs", "value"),
    Input(f"{PAGE_ID}-trend-agg", "value"),
    Input(f"{PAGE_ID}-trend-slice", "value"),
    Input(f"{PAGE_ID}-cumul-mode", "value"),
    Input(f"{PAGE_ID}-cumul-period-type", "value"),
    Input(f"{PAGE_ID}-cumul-slice", "value"),
    Input(f"{PAGE_ID}-cumul-settings-prior-periods", "value"),
    Input(f"{PAGE_ID}-filter-date-preset", "value"),
    Input(f"{PAGE_ID}-table-filter-rows", "data"),
    running=[
        (Output(f"{PAGE_ID}-chart-trend-loading", "visible"), True, False),
        (Output(f"{PAGE_ID}-chart-cumul-loading", "visible"), True, False),
    ],
)
def _update_procedures(
    _n, range_start, range_end, dept_filter, physician_filter, status_filter, slider_val,
    queue_filter, active_tab, trend_agg, trend_slice,
    cumul_mode, cumul_period_type, cumul_slice, cumul_prior_periods, date_preset,
    grid_rows,
):
    from data.loader import load_procedures

    try:
        df = load_procedures()
    except Exception:
        n_grids = len(_CAT_TAB_PAIRS) * 2
        return tuple([None] * 5 + [None, None, None] + [[], []] * len(_CAT_TAB_PAIRS) + [None, None])

    start, end = _get_date_range(slider_val, [range_start, range_end])
    dff_full = _filter_data(df, start, end, dept_filter, physician_filter, status_filter)

    # Check if triggered by grid filter — skip table rebuild
    triggered_by_grid = (
        dash.callback_context.triggered
        and len(dash.callback_context.triggered) == 1
        and dash.callback_context.triggered[0]["prop_id"] == f"{PAGE_ID}-table-filter-rows.data"
    )

    # Apply grid column filter to narrow KPIs/charts to visible rows
    dff = _apply_grid_row_filter(dff_full, grid_rows) if grid_rows is not None else dff_full

    # --- KPIs (with prior-period comparison) ---
    df_base = df[df["ScheduledDateTime"].notna()].copy() if "ScheduledDateTime" in df.columns else df.copy()
    if dept_filter and "Department" in df_base.columns:
        df_base = df_base[df_base["Department"].isin(dept_filter)]
    if physician_filter and "AppointmentPhysician" in df_base.columns:
        df_base = df_base[df_base["AppointmentPhysician"] == physician_filter]
    if status_filter and status_filter != "all" and "ActivityStatus" in df_base.columns:
        if status_filter == "open":
            df_base = df_base[df_base["ActivityStatus"] == "Open"]
        elif status_filter == "completed":
            df_base = df_base[df_base["ActivityStatus"] == "Manually Completed"]

    kpi_pluv, spark_pluv = _build_sparkline_kpi(
        dff, "Pluvicto", _CATEGORY_COLORS["Pluvicto"],
        df_all=df_base, start=start, end=end, spark_id=f"{PAGE_ID}-spark-pluvicto")
    kpi_upcoming_pluv = _build_upcoming_card(df, "Pluvicto", _CATEGORY_COLORS["Pluvicto"])
    kpi_spacer, spark_spacer = _build_sparkline_kpi(
        dff, "Rectal Spacer", _CATEGORY_COLORS["Rectal Spacer"],
        df_all=df_base, start=start, end=end, spark_id=f"{PAGE_ID}-spark-spacer")
    kpi_upcoming_spacer = _build_upcoming_card(df, "Rectal Spacer", _CATEGORY_COLORS["Rectal Spacer"])
    kpi_lead, spark_lead = _build_lead_time_kpi(
        dff, ["Pluvicto", "Rectal Spacer"],
        df_all=df_base, start=start, end=end, spark_id=f"{PAGE_ID}-spark-lead")

    # Sparkline store for clientside smoothing
    sparkline_store = {}
    if spark_pluv:
        sparkline_store["pluvicto"] = spark_pluv
    if spark_spacer:
        sparkline_store["spacer"] = spark_spacer
    if spark_lead:
        sparkline_store["lead"] = spark_lead

    # --- Chart stores (for active tab's category) ---
    # Resolve tab key → category name
    _key_to_cat = {key: cat for cat, key in _CAT_TAB_PAIRS}
    active_cat = _key_to_cat.get(active_tab, "Pluvicto")
    cat_df = dff[dff["ProcedureCategory"] == active_cat] if "ProcedureCategory" in dff.columns else pd.DataFrame()

    # Trend store (census format)
    trend_data = _prepare_trend_data(cat_df, active_cat, agg=trend_agg or "M", slice_by=trend_slice or "")

    # Cumulative store
    # For cumulative, use dimension-filtered but full-date-range data (df_base) so prior periods work
    cat_base = df_base[df_base["ProcedureCategory"] == active_cat] if "ProcedureCategory" in df_base.columns else pd.DataFrame()
    cumul_data = _prepare_cumul_data(
        cat_base, active_cat, start, end,
        date_preset=date_preset or "12mo",
        slice_by=cumul_slice or "total" if cumul_mode == "slice" else "",
        mode=cumul_mode or "prior",
        max_prior=cumul_prior_periods or 5,
        period_type=cumul_period_type or "calendar",
    )

    # --- Tab grids (use dff_full so column filters work on all page-filtered data) ---
    tab_outputs = []
    for cat_name, cat_key in _CAT_TAB_PAIRS:
        if triggered_by_grid:
            # Skip table rebuild when only grid filter changed
            tab_outputs.append(dash.no_update)
            tab_outputs.append(dash.no_update)
        else:
            grid_df = dff_full[dff_full["ProcedureCategory"] == cat_name] if "ProcedureCategory" in dff_full.columns else pd.DataFrame()
            cols, rows = _build_tab_grid_data(grid_df)
            tab_outputs.append(cols)
            tab_outputs.append(rows)

    # --- Pluvicto queue ---
    queue_table = _build_pluvicto_queue(queue_filter or "all")
    spacer_queue = _build_spacer_queue()

    return (
        kpi_pluv, kpi_upcoming_pluv, kpi_spacer, kpi_upcoming_spacer, kpi_lead,
        sparkline_store,
        trend_data, cumul_data,
        *tab_outputs,
        queue_table,
        spacer_queue,
    )


# ---------------------------------------------------------------------------
# CSV Export callbacks
# ---------------------------------------------------------------------------

def _register_export_callbacks():
    for cat_name, cat_key in _CAT_TAB_PAIRS:
        clientside_callback(
            """function(n) {
                if (!n) return window.dash_clientside.no_update;
                gridExportCsv('""" + f"{PAGE_ID}-tab-grid-{cat_key}" + """', '""" + cat_name.replace(" ", "_") + """_procedures.csv');
                return window.dash_clientside.no_update;
            }""",
            Output(f"{PAGE_ID}-tab-export-{cat_key}", "n_clicks"),
            Input(f"{PAGE_ID}-tab-export-{cat_key}", "n_clicks"),
            prevent_initial_call=True,
        )


_register_export_callbacks()


# ---------------------------------------------------------------------------
# Clientside callbacks for chart rendering
# ---------------------------------------------------------------------------

# Trend chart: store + smoothing + chart type → figure
clientside_callback(
    ClientsideFunction(namespace="census", function_name="smoothChartWithType"),
    Output(f"{PAGE_ID}-chart-trend", "figure"),
    Input(f"{PAGE_ID}-store-trend", "data"),
    Input(f"{PAGE_ID}-trend-settings-smooth", "value"),
    Input(f"{PAGE_ID}-trend-settings-type", "value"),
    State(f"{PAGE_ID}-chart-trend", "figure"),
)

# Cumulative chart: store + smoothing + chart type + stack + prior periods → figure
clientside_callback(
    ClientsideFunction(namespace="cumulative", function_name="renderWithProjectToggle"),
    Output(f"{PAGE_ID}-chart-cumul", "figure"),
    Input(f"{PAGE_ID}-store-cumul", "data"),
    Input(f"{PAGE_ID}-cumul-settings-smooth", "value"),
    Input(f"{PAGE_ID}-cumul-settings-type", "value"),
    Input(f"{PAGE_ID}-cumul-settings-stack", "value"),
    Input(f"{PAGE_ID}-cumul-settings-prior-periods", "value"),

    Input(f"{PAGE_ID}-cumul-project", "checked"),
    State(f"{PAGE_ID}-chart-cumul", "figure"),
)

# Disable Calendar when period > 1 year; cap prior-periods slider to available data
clientside_callback(
    """function(storeData, currentPtValue) {
        return window.dash_clientside.cumulative.updatePriorControls(storeData, currentPtValue);
    }""",
    Output(f"{PAGE_ID}-cumul-period-type", "data"),
    Output(f"{PAGE_ID}-cumul-period-type", "value", allow_duplicate=True),
    Output(f"{PAGE_ID}-cumul-settings-prior-periods", "max"),
    Output(f"{PAGE_ID}-cumul-settings-prior-periods", "marks"),
    Input(f"{PAGE_ID}-store-cumul", "data"),
    State(f"{PAGE_ID}-cumul-period-type", "value"),
    prevent_initial_call=True,
)

# Register settings gear toggle + PNG export callbacks
register_chart_callbacks([
    (f"{PAGE_ID}-trend", f"{PAGE_ID}-chart-trend"),
    {"sid": f"{PAGE_ID}-cumul", "gid": f"{PAGE_ID}-chart-cumul", "show_grouping": False},
])

# KPI sparkline smoothing (clientside — instant on drag)
_PROC_SPARKLINE_IDS = [
    f"{PAGE_ID}-spark-pluvicto",
    f"{PAGE_ID}-spark-spacer",
    f"{PAGE_ID}-spark-lead",
]

for _spark_id in _PROC_SPARKLINE_IDS:
    clientside_callback(
        ClientsideFunction(namespace="sparklines", function_name="updateFromStore"),
        Output(_spark_id, "figure"),
        Input(f"{PAGE_ID}-store-kpi-sparklines", "data"),
        Input(_spark_id, "id"),
        Input(f"{PAGE_ID}-smooth-slider", "value"),
    )


# ---------------------------------------------------------------------------
# Table column-filter detection → badge + clear button + store
# ---------------------------------------------------------------------------
# One clientside callback per tab grid: detect if column filters are active,
# write visible row indices to the shared store, and show/hide badge + clear btn.

for _cat_name, _cat_key in _CAT_TAB_PAIRS:
    _GRID_FILTER_JS = (
        """function(vrd, activeTab, allRows, prev) {
    var nu = window.dash_clientside.no_update;
    var hidden = {"position": "absolute", "top": -12, "right": 8, "zIndex": 10, "display": "none", "cursor": "pointer"};
    var base = {"position": "absolute", "top": -12, "right": 8, "zIndex": 10, "display": "block", "cursor": "pointer"};
    var btnHide = {"display": "none"};
    if (activeTab !== '"""
        + _cat_key
        + """') return [nu, nu, nu];
    if (!vrd || !allRows) return [nu, nu, nu];
    if (vrd.length === allRows.length) {
        if (prev === null) return [nu, nu, nu];
        return [null, hidden, btnHide];
    }
    var idxs = [];
    for (var i = 0; i < vrd.length; i++) {
        for (var j = 0; j < allRows.length; j++) {
            if (JSON.stringify(vrd[i]) === JSON.stringify(allRows[j])) { idxs.push(j); break; }
        }
    }
    idxs.sort(function(a, b) { return a - b; });
    if (!idxs.length) {
        return prev == null ? [nu, nu, nu] : [null, hidden, btnHide];
    }
    if (prev && prev.length === idxs.length) {
        var same = true;
        for (var k = 0; k < idxs.length; k++) {
            if (prev[k] !== idxs[k]) { same = false; break; }
        }
        if (same) return [nu, nu, nu];
    }
    return [idxs, base, {}];
}"""
    )
    clientside_callback(
        _GRID_FILTER_JS,
        Output(f"{PAGE_ID}-table-filter-rows", "data", allow_duplicate=True),
        Output(f"{PAGE_ID}-grid-filter-badge", "style", allow_duplicate=True),
        Output(f"{PAGE_ID}-table-clear-filters-{_cat_key}", "style"),
        Input(f"{PAGE_ID}-tab-grid-{_cat_key}", "virtualRowData"),
        Input(f"{PAGE_ID}-tabs", "value"),
        State(f"{PAGE_ID}-tab-grid-{_cat_key}", "rowData"),
        State(f"{PAGE_ID}-table-filter-rows", "data"),
        prevent_initial_call=True,
    )


# Clear Filters button per tab — reset that grid's filterModel
for _cat_name, _cat_key in _CAT_TAB_PAIRS:
    clientside_callback(
        """function(n) {
            if (!n) return window.dash_clientside.no_update;
            return {};
        }""",
        Output(f"{PAGE_ID}-tab-grid-{_cat_key}", "filterModel"),
        Input(f"{PAGE_ID}-table-clear-filters-{_cat_key}", "n_clicks"),
        prevent_initial_call=True,
    )


# Badge click → scroll to the active tab's detail grid
clientside_callback(
    """function(n) {
        if (!n) return window.dash_clientside.no_update;
        var el = document.querySelector('[id^="proc-tab-grid-"]');
        if (el) el.scrollIntoView({behavior: 'smooth', block: 'start'});
        return window.dash_clientside.no_update;
    }""",
    Output(f"{PAGE_ID}-grid-filter-badge", "n_clicks"),
    Input(f"{PAGE_ID}-grid-filter-badge", "n_clicks"),
    prevent_initial_call=True,
)


# Reset table-filter-rows store + hide badge when tab changes
clientside_callback(
    """function(tab) {
        return [null, {"position": "absolute", "top": -12, "right": 8, "zIndex": 10, "display": "none", "cursor": "pointer"}];
    }""",
    Output(f"{PAGE_ID}-table-filter-rows", "data", allow_duplicate=True),
    Output(f"{PAGE_ID}-grid-filter-badge", "style", allow_duplicate=True),
    Input(f"{PAGE_ID}-tabs", "value"),
    prevent_initial_call=True,
)


# Project-to-year-end toggle visibility (shown only for current_year preset)
clientside_callback(
    """function(preset) {
        return preset === "current_year" ? {} : {"display": "none"};
    }""",
    Output(f"{PAGE_ID}-cumul" + "-project-wrap", "style"),
    Input(f"{PAGE_ID}-filter-date-preset", "value"),
)

