"""Plans page -- treatment plan tracking: status, technique mix, duration, session tracking."""

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
)
from components.filter_bar import department_chips
from components.kpi_card import kpi_card
from components.chart_card import chart_card, register_chart_callbacks
from components.chart_settings import chart_settings_popover
from components.detail_table import detail_table
from utils.charts import apply_default_layout, empty_figure, dept_color
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

dash.register_page(__name__, path="/plans", name="Plans", order=10)


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
    {"value": "created", "label": "Created"},
    {"value": "treated", "label": "Treated"},
    {"value": "completed", "label": "Completed"},
]


# ---------------------------------------------------------------------------
# Filter Bar
# ---------------------------------------------------------------------------

def _build_plans_filter_bar():
    """Build the two-row filter bar for plans page."""
    return dmc.Paper(
        children=[
            # Row 1: dimension filters
            dmc.Group(
                children=[
                    department_chips("plans"),
                    # Physician dropdown
                    html.Div(
                        children=[
                            html.Div(
                                children=[
                                    dmc.Button(
                                        "Physician",
                                        id="plans-physician-trigger",
                                        variant="default",
                                        size="sm",
                                        rightSection=DashIconify(icon="mdi:chevron-down", width=14),
                                    ),
                                    dmc.ActionIcon(
                                        DashIconify(icon="mdi:close-circle", width=18),
                                        id="plans-physician-clear",
                                        variant="subtle",
                                        color="gray",
                                        size="sm",
                                        className="wf-filter-clear-btn",
                                    ),
                                ],
                                style={"position": "relative", "display": "inline-block"},
                            ),
                            dmc.Paper(
                                id="plans-physician-panel",
                                children=[
                                    dmc.ChipGroup(
                                        children=[],
                                        id="plans-filter-physician",
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
                    # Diagnosis dropdown
                    html.Div(
                        children=[
                            html.Div(
                                children=[
                                    dmc.Button(
                                        "Diagnosis",
                                        id="plans-diagnosis-trigger",
                                        variant="default",
                                        size="sm",
                                        rightSection=DashIconify(icon="mdi:chevron-down", width=14),
                                    ),
                                    dmc.ActionIcon(
                                        DashIconify(icon="mdi:close-circle", width=18),
                                        id="plans-diagnosis-clear",
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
                                    id="plans-filter-diagnosis",
                                    multiple=True,
                                    value=[],
                                ),
                                id="plans-diagnosis-panel",
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
                    # Technique dropdown
                    html.Div(
                        children=[
                            html.Div(
                                children=[
                                    dmc.Button(
                                        "Technique",
                                        id="plans-technique-trigger",
                                        variant="default",
                                        size="sm",
                                        rightSection=DashIconify(icon="mdi:chevron-down", width=14),
                                    ),
                                    dmc.ActionIcon(
                                        DashIconify(icon="mdi:close-circle", width=18),
                                        id="plans-technique-clear",
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
                                    id="plans-filter-technique",
                                    multiple=True,
                                    value=[],
                                ),
                                id="plans-technique-panel",
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
                        id="plans-filter-status",
                        data=[
                            {"value": "all", "label": "All"},
                            {"value": "ACTIVE", "label": "Active"},
                            {"value": "COMPLETED", "label": "Completed"},
                        ],
                        value="all",
                        size="xs",
                    ),
                    # Session range slider
                    dmc.Group(
                        children=[
                            dmc.Text("Sessions", size="xs", c="#6B7280", fw=500,
                                     id="plans-session-label"),
                            dmc.RangeSlider(
                                id="plans-session-slider",
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
                                id="plans-session-clear",
                                variant="subtle",
                                color="gray",
                                size="xs",
                                style={"display": "none"},
                            ),
                        ],
                        gap=6,
                        align="center",
                    ),
                    dcc.Store(id="plans-session-engaged", data=False),
                    # Smoothing slider for KPI sparklines (rightmost)
                    dmc.Group(
                        children=[
                            dmc.Text("Smoothing", size="xs", c="#6B7280", fw=500),
                            dmc.Slider(
                                id="plans-smooth-slider",
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
                        id="plans-filter-date-preset",
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
                            id="plans-filter-daterange",
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
                        id="plans-date-mode",
                        data=DATE_MODES,
                        value="created",
                        size="xs",
                    ),
                    dmc.Box(
                        children=[
                            html.Div(id="plans-date-range-label", style={"display": "none"}),
                            dmc.RangeSlider(
                                id="plans-date-slider",
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
                dmc.Title("Plans", order=2, className="page-title",
                          style={"margin": 0, "textAlign": "center"}),
                _build_plans_filter_bar(),
            ],
        ),

        # KPI row — 6 cards
        dmc.Grid(id="plans-kpi-row", gutter="md", children=[
            dmc.GridCol(id="plans-kpi-active", span={"base": 12, "sm": 6, "md": 2}),
            dmc.GridCol(id="plans-kpi-created", span={"base": 12, "sm": 6, "md": 2}),
            dmc.GridCol(id="plans-kpi-completed", span={"base": 12, "sm": 6, "md": 2}),
            dmc.GridCol(id="plans-kpi-median-sessions", span={"base": 12, "sm": 6, "md": 2}),
            dmc.GridCol(id="plans-kpi-median-duration", span={"base": 12, "sm": 6, "md": 2}),
            dmc.GridCol(id="plans-kpi-multimachine", span={"base": 12, "sm": 6, "md": 2}),
        ]),

        # Row 1: Course Volume Trend + Cumulative (half-width each)
        dmc.Grid(gutter="md", children=[
            dmc.GridCol(
                chart_card(
                    "plans-chart-volume",
                    "Plan Volume Trend",
                    settings_id="plans-volume",
                    chart_types=[
                        {"value": "line", "label": "Line"},
                        {"value": "area", "label": "Area"},
                        {"value": "bar", "label": "Bar"},
                    ],
                    show_smooth=True,
                    smooth_max=12,
                    smooth_default=0,
                    paper_padding="md",
                    extra_controls_left=[
                        dmc.SegmentedControl(
                            id="plans-volume-slice",
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
                    extra_controls=[
                        dmc.SegmentedControl(
                            id="plans-volume-agg",
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
                span={"base": 12, "md": 6},
            ),
            dmc.GridCol(
                chart_card(
                    "plans-chart-cumulative",
                    "Cumulative Plan Volume",
                    settings_id="plans-cumulative",
                    chart_types=[
                        {"value": "line", "label": "Line"},
                        {"value": "area", "label": "Area"},
                        {"value": "bar", "label": "Bar"},
                    ],
                    show_smooth=True,
                    smooth_max=50,
                    smooth_default=0,
                    paper_padding="md",
                    extra_controls=[
                        dmc.SegmentedControl(
                            id="plans-cumulative-mode",
                            data=[
                                {"value": "prior", "label": "Prior Periods"},
                                {"value": "slice", "label": "Slice By"},
                            ],
                            value="prior",
                            size="xs",
                        ),
                        dmc.SegmentedControl(
                            id="plans-cumulative-period-type",
                            data=[
                                {"value": "calendar", "label": "Calendar"},
                                {"value": "rolling", "label": "Rolling"},
                            ],
                            value="calendar",
                            size="xs",
                        ),
                        dmc.SegmentedControl(
                            id="plans-cumulative-slice",
                            data=[
                                {"value": "physician", "label": "MD"},
                                {"value": "site", "label": "Site"},
                                {"value": "diagnosis", "label": "Dx"},
                            ],
                            value="site",
                            size="xs",
                            style={"display": "none"},
                        ),
                    ],
                ),
                span={"base": 12, "md": 6},
            ),
        ]),

        # Charts container (remaining charts)
        dmc.Stack(id="plans-charts", gap=16),

        # Detail table container
        dmc.Stack(id="plans-table-container", gap=0),

        # Stores for clientside rendering
        dcc.Store(id="plans-store-volume"),
        dcc.Store(id="plans-store-cumulative"),
        dcc.Store(id="plans-store-kpi-sparklines"),
        dcc.Store(id="plans-store-ridgeline"),
        dcc.Store(id="plans-store-session-trend"),
        dcc.Store(id="plans-store-session-dist"),
        dcc.Store(id="plans-store-complexity-trends"),
        dcc.Store(id="plans-store-technique-dist"),
        dcc.Store(id="plans-store-quit-trend"),

        # Interval for periodic refresh
        dcc.Interval(id="plans-interval", interval=300_000, n_intervals=0),
    ],
)


# ---------------------------------------------------------------------------
# Register chart settings callbacks
# ---------------------------------------------------------------------------
register_chart_callbacks([
    ("plans-volume", "plans-chart-volume"),
    ("plans-cumulative", "plans-chart-cumulative"),
    ("plans-session-trend", "plans-chart-session-trend"),
    ("plans-complexity", "plans-chart-complexity"),
    ("plans-technique-dist", "plans-chart-technique-dist"),
    ("plans-quit-trend", "plans-chart-quit-trend"),
])


# ---------------------------------------------------------------------------
# Slice-by dim styling
# ---------------------------------------------------------------------------
_SLICE_CLASS_JS = """function(val) {
    return val ? "slice-group-active" : "slice-total-active";
}"""

for _sid in ["plans-volume-slice"]:
    clientside_callback(
        _SLICE_CLASS_JS,
        Output(_sid, "className"),
        Input(_sid, "value"),
    )


# ---------------------------------------------------------------------------
# Cumulative mode toggle — show/hide slice selector
# ---------------------------------------------------------------------------
clientside_callback(
    """function(mode) {
        if (mode === "slice") return {};
        return {display: "none"};
    }""",
    Output("plans-cumulative-slice", "style"),
    Input("plans-cumulative-mode", "value"),
)


# ---------------------------------------------------------------------------
# Filter Callbacks
# ---------------------------------------------------------------------------

def _register_plans_filter_callbacks():
    """Register all filter-sync callbacks."""

    # A) Preset → Slider + DatePicker
    @callback(
        Output("plans-date-slider", "value"),
        Output("plans-filter-daterange", "start_date", allow_duplicate=True),
        Output("plans-filter-daterange", "end_date", allow_duplicate=True),
        Input("plans-filter-date-preset", "value"),
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

    # B) Slider → DatePicker + Label (clientside)
    clientside_callback(
        ClientsideFunction(namespace="plansDateSlider", function_name="syncSlider"),
        Output("plans-filter-daterange", "start_date", allow_duplicate=True),
        Output("plans-filter-daterange", "end_date", allow_duplicate=True),
        Output("plans-date-range-label", "children"),
        Input("plans-date-slider", "value"),
        State("plans-filter-daterange", "start_date"),
        State("plans-filter-daterange", "end_date"),
        prevent_initial_call=True,
    )

    # C) DatePicker → Slider
    @callback(
        Output("plans-date-slider", "value", allow_duplicate=True),
        Input("plans-filter-daterange", "start_date"),
        Input("plans-filter-daterange", "end_date"),
        State("plans-date-slider", "value"),
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
        Output("plans-filter-date-preset", "value", allow_duplicate=True),
        Input("plans-date-slider", "value"),
        State("plans-filter-date-preset", "value"),
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
        Output("plans-physician-trigger", "children"),
        Input("plans-filter-physician", "value"),
    )
    clientside_callback(
        """function(vals) {
            if (!vals || vals.length === 0) return "Diagnosis";
            if (vals.length === 1) return vals[0];
            return vals.length + " selected";
        }""",
        Output("plans-diagnosis-trigger", "children"),
        Input("plans-filter-diagnosis", "value"),
    )

    # --- Clear-button visibility ---
    clientside_callback(
        """function(val) { return val ? {"display": "inline-flex"} : {"display": "none"}; }""",
        Output("plans-physician-clear", "style"),
        Input("plans-filter-physician", "value"),
    )
    clientside_callback(
        """function(vals) { return vals && vals.length > 0 ? {"display": "inline-flex"} : {"display": "none"}; }""",
        Output("plans-diagnosis-clear", "style"),
        Input("plans-filter-diagnosis", "value"),
    )

    # --- Clear-button actions ---
    clientside_callback(
        """function(n) { return null; }""",
        Output("plans-filter-physician", "value", allow_duplicate=True),
        Input("plans-physician-clear", "n_clicks"),
        prevent_initial_call=True,
    )
    clientside_callback(
        """function(n) { return []; }""",
        Output("plans-filter-diagnosis", "value", allow_duplicate=True),
        Input("plans-diagnosis-clear", "n_clicks"),
        prevent_initial_call=True,
    )

    # --- Technique trigger/clear/visibility ---
    clientside_callback(
        """function(vals) {
            if (!vals || vals.length === 0) return "Technique";
            if (vals.length === 1) return vals[0];
            return vals.length + " selected";
        }""",
        Output("plans-technique-trigger", "children"),
        Input("plans-filter-technique", "value"),
    )
    clientside_callback(
        """function(vals) { return vals && vals.length > 0 ? {"display": "inline-flex"} : {"display": "none"}; }""",
        Output("plans-technique-clear", "style"),
        Input("plans-filter-technique", "value"),
    )
    clientside_callback(
        """function(n) { return []; }""",
        Output("plans-filter-technique", "value", allow_duplicate=True),
        Input("plans-technique-clear", "n_clicks"),
        prevent_initial_call=True,
    )


_register_plans_filter_callbacks()


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
    Output("plans-session-engaged", "data", allow_duplicate=True),
    Input("plans-session-slider", "value"),
    State("plans-session-engaged", "data"),
    State("plans-session-slider", "min"),
    State("plans-session-slider", "max"),
    prevent_initial_call=True,
)

# Clear button → disengage
clientside_callback(
    """function(n) {
        if (!n) return window.dash_clientside.no_update;
        return false;
    }""",
    Output("plans-session-engaged", "data", allow_duplicate=True),
    Input("plans-session-clear", "n_clicks"),
    prevent_initial_call=True,
)

# Show/hide clear button based on engaged state
clientside_callback(
    """function(engaged) {
        return engaged ? {"display": "inline-flex"} : {"display": "none"};
    }""",
    Output("plans-session-clear", "style"),
    Input("plans-session-engaged", "data"),
)

# Dim the slider label when not engaged, highlight when active
clientside_callback(
    """function(engaged) {
        if (engaged) return {"color": "#7C2A83", "fontWeight": 600, "fontSize": "var(--mantine-font-size-xs)"};
        return {"color": "#9CA3AF", "fontWeight": 500, "fontSize": "var(--mantine-font-size-xs)"};
    }""",
    Output("plans-session-label", "style"),
    Input("plans-session-engaged", "data"),
)

# Dim the slider color when not engaged
clientside_callback(
    """function(engaged) {
        return engaged ? "violet" : "gray";
    }""",
    Output("plans-session-slider", "color"),
    Input("plans-session-engaged", "data"),
)

# Auto-sync slider value to [min, max] when not engaged
# Fires when min/max change (from server) or when engaged flips to false
clientside_callback(
    """function(engaged, sliderMin, sliderMax) {
        if (engaged) return window.dash_clientside.no_update;
        return [sliderMin, sliderMax];
    }""",
    Output("plans-session-slider", "value", allow_duplicate=True),
    Input("plans-session-engaged", "data"),
    Input("plans-session-slider", "min"),
    Input("plans-session-slider", "max"),
    prevent_initial_call=True,
)


# ---------------------------------------------------------------------------
# Dynamic physician chip population
# ---------------------------------------------------------------------------
@callback(
    Output("plans-filter-physician", "children"),
    Input("plans-interval", "n_intervals"),
)
def _populate_physician_chips(_n):
    """Populate physician filter with MDs from the plans dataset."""
    from data.loader import load_plans
    from components.filter_bar import physician_short_name

    try:
        df = load_plans()
    except Exception:
        return []

    if df.empty or "TreatingPhysician" not in df.columns:
        return []

    mds = sorted(df["TreatingPhysician"].dropna().unique())

    return [
        dmc.Chip(
            physician_short_name(md),
            value=md,
            size="xs",
            variant="filled",
        )
        for md in mds
    ]


# ---------------------------------------------------------------------------
# Dynamic technique chip population
# ---------------------------------------------------------------------------
@callback(
    Output("plans-filter-technique", "children"),
    Input("plans-interval", "n_intervals"),
)
def _populate_technique_chips(_n):
    """Populate technique filter from the plans dataset."""
    from data.loader import load_plans

    try:
        df = load_plans()
    except Exception:
        return []

    if df.empty or "TreatmentTechnique" not in df.columns:
        return []

    all_techs = sorted(df["TreatmentTechnique"].dropna().unique())

    return [
        dmc.Chip(t, value=t, size="xs", variant="filled")
        for t in all_techs
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

    "created" uses PlanCreationDate — when the plan was created in ARIA.
    "treated" uses FirstTreatmentDate for census-style filtering.
    "completed" uses LastTreatmentDate.
    """
    if mode == "treated":
        return "FirstTreatmentDate"
    elif mode == "completed":
        return "LastTreatmentDate"
    return "PlanCreationDate"  # "created" (default)


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
# Ridgeline: Sessions per Plan by Year
# ---------------------------------------------------------------------------

def _prepare_ridgeline_data(df, date_col):
    """Extract per-year session values for the ridgeline store.

    Returns a JSON-serialisable dict or None.
    """
    col = "NoSessionPlanned"
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
# Sessions Trend: median sessions over time (all agg × slice combos)
# ---------------------------------------------------------------------------

def _prepare_session_trend_data(dff, date_col, c2b, start=None, end=None):
    """Prepare median-sessions-over-time data for all agg × slice combos."""
    frac_col = "NoSessionPlanned"
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
                t2 = t.copy()
                t2["_bs"] = t2["DiagnosisCodes"].apply(lambda v: primary_category(v, c2b))
                t2_bs = t2[t2["_bs"] != "Unknown"]
                top_bs = t2_bs["_bs"].value_counts().head(8).index.tolist()
                for i, bs in enumerate(top_bs):
                    sub = t2_bs[t2_bs["_bs"] == bs]
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
# Quit Rate Trend: % of completed plans where delivered < planned
# ---------------------------------------------------------------------------

def _prepare_quit_trend_data(completed_df, date_col, c2b, start=None, end=None):
    """Prepare quit-rate-over-time data for all agg × slice combos."""
    needed = {"NoSessionPlanned", "SessionBasedFractionCount", date_col}
    if not needed.issubset(completed_df.columns) or completed_df.empty:
        return None

    tmp = completed_df[
        (completed_df["NoSessionPlanned"] > 0)
        & (completed_df["SessionBasedFractionCount"] > 0)
        & completed_df[date_col].notna()
    ].copy()
    tmp["_quit"] = (
        tmp["SessionBasedFractionCount"] < tmp["NoSessionPlanned"]
    ).astype(int)

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

    combos = {}
    for agg in ["W", "M", "Y"]:
        period_code = "Y" if agg == "Y" else agg
        t = tmp.copy()
        t["period"] = t["_plot_date"].dt.to_period(period_code).dt.to_timestamp()
        all_periods = sorted(t["period"].unique())
        dates = [d.isoformat() for d in all_periods]

        for slice_key in ["", "physician", "site", "diagnosis"]:
            series = []

            def _rate_series(sub, name, color):
                grp = sub.groupby("period")["_quit"].agg(["sum", "count"]).reindex(all_periods)
                # Require ≥5 plans for a meaningful rate
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
                t2 = t.copy()
                t2["_bs"] = t2["DiagnosisCodes"].apply(lambda v: primary_category(v, c2b))
                t2_bs = t2[t2["_bs"] != "Unknown"]
                top_bs = t2_bs["_bs"].value_counts().head(8).index.tolist()
                for i, bs in enumerate(top_bs):
                    _rate_series(
                        t2_bs[t2_bs["_bs"] == bs], bs,
                        CHART_COLORWAY[i % len(CHART_COLORWAY)],
                    )

            combos[f"{agg}|{slice_key}"] = {"dates": dates, "series": series}

    return combos


# ---------------------------------------------------------------------------
# Fractions Distribution: histogram/density data
# ---------------------------------------------------------------------------

def _prepare_session_dist_data(dff):
    """Prepare sessions distribution data for the store."""
    frac_col = "NoSessionPlanned"
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


def _prepare_complexity_trend_data(dff, date_col, start=None, end=None):
    """Prepare multi-machine/dept trend data for store.

    Returns a dict with keys for each agg period (W/M/Y), each containing
    dates + series for pct and avg modes for each dimension.
    Plans only have 2 dimensions (machines and departments).
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

    # Count machines, departments per plan
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

    dims = [
        ("machines", "_n_machines", "Machines"),
        ("depts", "_n_depts", "Departments"),
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


def _prepare_technique_dist_data(dff, date_col, start=None, end=None):
    """Prepare technique distribution over time from plans data.

    TreatmentTechnique is singular per plan (not comma-separated like courses),
    so no any/primary counting modes needed.

    Returns JSON-serialisable dict keyed by "{agg}" for the store.
    """
    tech_col = "TreatmentTechnique"
    if dff.empty or date_col not in dff.columns or tech_col not in dff.columns:
        return None

    base = dff[[date_col, tech_col]].dropna(subset=[date_col, tech_col]).copy()
    if base.empty:
        return None

    if start is not None:
        base["_plot_date"] = base[date_col].clip(lower=start)
        if end is not None:
            base["_plot_date"] = base["_plot_date"].clip(upper=end)
    else:
        base["_plot_date"] = base[date_col]

    all_techs = set(base[tech_col].unique())
    ordered = [t for t in _TECHNIQUE_ORDER if t in all_techs]
    remaining = sorted(all_techs - set(ordered))
    ordered.extend(remaining)

    combos = {}
    for agg in ["W", "M", "Y"]:
        period_code = "Y" if agg == "Y" else agg
        t = base.copy()
        t["period"] = t["_plot_date"].dt.to_period(period_code).dt.to_timestamp()
        all_periods = sorted(t["period"].unique())
        dates = [d.isoformat() for d in all_periods]

        pivot = t.groupby(["period", tech_col]).size().unstack(fill_value=0)
        pivot = pivot.reindex(all_periods, fill_value=0)

        series = []
        for tech in ordered:
            vals = pivot[tech].tolist() if tech in pivot.columns else [0] * len(all_periods)
            series.append({
                "name": tech,
                "values": vals,
                "color": _TECHNIQUE_COLORS.get(tech, CHART_COLORWAY[len(series) % len(CHART_COLORWAY)]),
            })

        combos[agg] = {
            "dates": dates,
            "series": series,
        }

    return combos


_RIDGE_HEIGHT = 720


def _build_ridgeline_figure(data, bw_factor=0.5, mode="density"):
    """Build the ridgeline Plotly figure from store data + bandwidth factor."""
    from scipy.stats import gaussian_kde

    if not data:
        fig = empty_figure("No sessions data available")
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

        for i, yr in enumerate(years):
            row = i + 1
            vals = np.array(per_year[yr])
            counts, _ = np.histogram(vals, bins=bins)
            n_plans = len(vals)
            median_fx = float(np.median(vals)) if len(vals) else 0

            fig.add_trace(go.Bar(
                x=bin_centers.tolist(),
                y=counts.tolist(),
                marker_color="rgb(158, 113, 178)",
                marker_line_width=0,
                width=1.0,
                customdata=np.full(len(bin_centers), median_fx).tolist(),
                hovertemplate=(
                    f"<b>{yr}</b> (n={n_plans:,})"
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

        fig.update_xaxes(title_text="Sessions Planned", row=n_years, col=1)
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
        for i, yr in enumerate(years):
            axis_name = f"yaxis{i + 1}" if i > 0 else "yaxis"
            yref = f"y{i + 1} domain" if i > 0 else "y domain"
            fig.update_layout(**{axis_name: dict(
                showticklabels=False, showgrid=False, zeroline=False,
            )})
            fig.add_annotation(
                text=str(yr), x=0, y=0.5,
                xref="paper", yref=yref,
                xanchor="right", yanchor="middle",
                xshift=-8,
                showarrow=False,
                font=dict(size=11, color="#6B7280"),
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
            n_plans = len(vals)
            median_fx = float(np.median(vals)) if vals else 0

            ridges.append({
                "year": yr,
                "baseline": baseline,
                "x_pts": x_pts,
                "y_scaled": y_scaled,
                "n_plans": n_plans,
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
                line=dict(color="rgba(255,255,255,0.98)", width=2.4),
                name=str(yr),
                showlegend=False,
                customdata=np.full(len(x_list), r["median_fx"]).tolist(),
                hovertemplate=(
                    f"<b>{yr}</b> (n={r['n_plans']:,})"
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
            title="Sessions Planned",
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

def _prepare_volume_data(dff, agg, slice_by="", date_col="PlanCreationDate", c2b=None,
                         start=None, end=None, date_mode="created"):
    """Prepare course volume trend data for clientside rendering.

    In "treated" mode, counts how many plans were under active treatment
    during each period (census-style), rather than when they started.
    Other modes count plans by their date_col value per period.
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
        # Build period boundaries
        period_range = pd.date_range(start, end, freq=period_code)
        if len(period_range) < 2:
            period_range = pd.date_range(start, end, periods=2, freq=None)
        all_periods = sorted(period_range)
        dates = [d.isoformat() for d in all_periods]

        ft = dff["FirstTreatmentDate"].values
        lt = dff["LastTreatmentDate"].fillna(dff["FirstTreatmentDate"]).values

        def _census_counts(sub_ft, sub_lt):
            """Count plans active at each period start."""
            counts = []
            for p in all_periods:
                p_np = p.to_numpy()
                counts.append(int(((sub_ft <= p_np) & (sub_lt >= p_np)).sum()))
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
            dff["_bs"] = dff["DiagnosisCodes"].apply(lambda v: primary_category(v, c2b))
            dff_bs = dff[dff["_bs"] != "Unknown"]
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
            "yTitle": "Active Plans",
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
        dff["_bs"] = dff["DiagnosisCodes"].apply(lambda v: primary_category(v, c2b))
        dff_bs = dff[dff["_bs"] != "Unknown"]
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
        "yTitle": "Plans",
        "hideLegend": len(series) <= 1,
    }


# ---------------------------------------------------------------------------
# Data Preparation: Cumulative
# ---------------------------------------------------------------------------

def _prepare_cumulative_data(df_all, start, end, date_preset,
                              date_col, departments, physician, diagnosis_cats,
                              status, session_range, c2b,
                              techniques=None, date_mode="created",
                              mode="prior", period_type="calendar",
                              slice_by="site"):
    """Prepare cumulative plan volume data for overlay chart."""
    if df_all.empty or date_col not in df_all.columns:
        return None

    today = pd.Timestamp.now().normalize()
    if end.normalize() > today:
        end = today

    period_days = (end - start).days + 1
    if period_days < 2:
        return None

    def _window_mask(df, w_start, w_end):
        """Return boolean mask for plans in the window, respecting date_mode."""
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
        # Clamp plot dates to window so overlap-matched plans whose
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
        if sb == "site" and "Department" in sub.columns:
            return sub.groupby("Department").size().to_dict()
        elif sb == "physician" and "TreatingPhysician" in sub.columns:
            counts = sub.groupby("TreatingPhysician").size()
            return {(k.split(",")[0] if "," in k else k): v for k, v in counts.items()}
        elif sb == "diagnosis" and c2b and "DiagnosisCodes" in sub.columns:
            sub = sub.copy()
            sub["_bs"] = sub["DiagnosisCodes"].apply(lambda v: primary_category(v, c2b))
            sub = sub[sub["_bs"] != "Unknown"]
            return sub.groupby("_bs").size().to_dict()
        return {}

    # Apply filters to full dataset
    dff_all = _apply_filters(df_all, departments, physician, diagnosis_cats, status, session_range, c2b,
                             techniques=techniques)

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
        for i in range(1, 6):
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
    for label, p_start, p_end in windows:
        vals = _cumulative_for_window(dff_all, p_start, p_end)
        if vals and any(v > 0 for v in vals):
            if len(vals) < n_days:
                vals = vals + [vals[-1] if vals else 0] * (n_days - len(vals))
            elif len(vals) > n_days:
                vals = vals[:n_days]
            prior.append({"label": label, "values": vals, "color": "#D1D5DB"})

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
        return {
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
            "yTitle": "Cumulative Plans",
        }

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
            last_idx = next((i for i in range(len(raw) - 1, -1, -1) if raw[i] > 0), None)
            if first_idx is None:
                return [None] * len(cumvals)
            for i in range(first_idx):
                cumvals[i] = None
            for i in range(last_idx + 1, len(cumvals)):
                cumvals[i] = None
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
            dff_p = dff_period.copy()
            dff_p["_bs"] = dff_p["DiagnosisCodes"].apply(lambda v: primary_category(v, c2b))
            dff_p = dff_p[dff_p["_bs"] != "Unknown"]
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
            "yTitle": "Cumulative Plans",
        }


# ---------------------------------------------------------------------------
# Effective completion logic
# ---------------------------------------------------------------------------

_INACTIVITY_THRESHOLD_DAYS = 90


def _is_effectively_completed(df):
    """Return a boolean Series: True if a plan is effectively completed.

    A plan is considered completed if ANY of:
      1. ClinicalStatus == "COMPLETED"
      2. NoFractionsRemaining == 0
      3. No treatment activity in the last 90 days (inactivity timeout)
    """
    mask = pd.Series(False, index=df.index)

    if "ClinicalStatus" in df.columns:
        mask = mask | (df["ClinicalStatus"] == "COMPLETED")

    if "NoFractionsRemaining" in df.columns:
        remaining = pd.to_numeric(df["NoFractionsRemaining"], errors="coerce")
        mask = mask | (remaining == 0)

    # Inactivity timeout — no treatment in 90 days
    if "LastTreatmentDate" in df.columns:
        today = pd.Timestamp.now().normalize()
        days_since = (today - df["LastTreatmentDate"]).dt.days
        mask = mask | (days_since > _INACTIVITY_THRESHOLD_DAYS)

    return mask


# ---------------------------------------------------------------------------
# Filter application
# ---------------------------------------------------------------------------

def _apply_filters(df, departments, physician, diagnosis_cats, status, session_range, c2b,
                   techniques=None):
    """Apply dimension filters (not date) to a dataframe."""
    if df.empty:
        return df

    if departments and "Department" in df.columns:
        df = df[df["Department"].isin(departments)]

    if physician and "TreatingPhysician" in df.columns:
        df = df[df["TreatingPhysician"] == physician]

    if diagnosis_cats and c2b and "DiagnosisCodes" in df.columns:
        mask = df["DiagnosisCodes"].apply(
            lambda v: bool(get_categories_for_codes(v, c2b) & set(diagnosis_cats))
        )
        df = df[mask]

    if techniques and "TreatmentTechnique" in df.columns:
        tech_set = set(techniques)
        df = df[df["TreatmentTechnique"].isin(tech_set)]

    if status and status != "all":
        if status == "COMPLETED":
            df = df[_is_effectively_completed(df)]
        elif status == "ACTIVE":
            df = df[~_is_effectively_completed(df)]

    if session_range and "NoSessionPlanned" in df.columns:
        smin, smax = session_range
        vals = df["NoSessionPlanned"]
        df = df[(vals >= smin) | vals.isna()]
        vals2 = df["NoSessionPlanned"]
        df = df[(vals2 <= smax) | vals2.isna()]

    return df


# ---------------------------------------------------------------------------
# Main Callback
# ---------------------------------------------------------------------------

@callback(
    Output("plans-kpi-active", "children"),
    Output("plans-kpi-created", "children"),
    Output("plans-kpi-completed", "children"),
    Output("plans-kpi-median-sessions", "children"),
    Output("plans-kpi-median-duration", "children"),
    Output("plans-kpi-multimachine", "children"),
    Output("plans-store-volume", "data"),
    Output("plans-store-cumulative", "data"),
    Output("plans-store-kpi-sparklines", "data"),
    Output("plans-store-ridgeline", "data"),
    Output("plans-store-session-trend", "data"),
    Output("plans-store-session-dist", "data"),
    Output("plans-store-complexity-trends", "data"),
    Output("plans-store-technique-dist", "data"),
    Output("plans-store-quit-trend", "data"),
    Output("plans-charts", "children"),
    Output("plans-table-container", "children"),
    Output("plans-session-slider", "min"),
    Output("plans-session-slider", "max"),
    Input("plans-interval", "n_intervals"),
    Input("plans-volume-agg", "value"),
    Input("plans-volume-slice", "value"),
    Input("plans-cumulative-mode", "value"),
    Input("plans-cumulative-period-type", "value"),
    Input("plans-cumulative-slice", "value"),
    Input("plans-date-slider", "value"),
    Input("plans-filter-department", "value"),
    Input("plans-filter-physician", "value"),
    Input("plans-filter-diagnosis", "value"),
    Input("plans-filter-technique", "value"),
    Input("plans-filter-status", "value"),
    Input("plans-session-slider", "value"),
    Input("plans-date-mode", "value"),
    Input("plans-filter-date-preset", "value"),
    State("plans-session-engaged", "data"),
    running=[
        (Output("plans-chart-volume-loading", "visible"), True, False),
        (Output("plans-chart-cumulative-loading", "visible"), True, False),
    ],
)
def update_plans(_n, agg, volume_slice,
                    cumul_mode, cumul_period_type, cumul_slice,
                    slider_val,
                    departments, physician, diagnosis_cats, techniques,
                    status, session_range, date_mode, date_preset,
                    session_engaged):
    from data.loader import load_plans

    na_kpi = kpi_card("--", "N/A")
    empty = empty_figure()
    empty_result = (na_kpi,) * 6 + (None, None, {}, None, None, None, None, None, None, [], [], 0, 50)

    try:
        df = load_plans()
    except Exception:
        return empty_result

    if df.empty:
        return empty_result

    # Build diagnosis lookup
    c2b = _build_diag_lookup()

    # Determine date column based on mode
    date_col = _date_col_for_mode(date_mode)

    # Ensure date column exists; fall back to PlanCreationDate
    if date_col not in df.columns or df[date_col].notna().sum() == 0:
        date_col = "PlanCreationDate"

    # "Completed In" mode: restrict to effectively-completed plans BEFORE
    # date filtering, so we only plot plans that actually finished — not
    # every course that happened to have a LastTreatmentDate in the window.
    if date_mode == "completed":
        df = df[_is_effectively_completed(df)]

    # Update session slider range from data (before date filter so range stays stable)
    session_min_data = 0
    session_max_data = 50
    if "NoSessionPlanned" in df.columns:
        svals = df["NoSessionPlanned"].dropna()
        if not svals.empty:
            session_min_data = int(svals.min())
            session_max_data = int(svals.max())

    # Date range from slider
    start, end = _get_date_range(slider_val, None)

    # Keep full df for cumulative prior-period comparison
    df_all = df.copy()

    # Date filter
    if date_mode == "treated":
        # "Treated In" — include any course whose treatment span overlaps the window.
        # Overlap condition: FirstTreatmentDate <= end AND LastTreatmentDate >= start
        ft = "FirstTreatmentDate"
        lt = "LastTreatmentDate"
        if ft in df.columns and lt in df.columns:
            df = df[df[ft].notna()]
            # Fall back LastTreatmentDate to FirstTreatmentDate for active plans
            last = df[lt].fillna(df[ft])
            df = df[(df[ft] <= end) & (last >= start)]
    elif date_col in df.columns:
        df = df[df[date_col].notna()]
        df = df[(df[date_col] >= start) & (df[date_col] <= end)]

    if df.empty:
        return (na_kpi,) * 6 + (None, None, {}, None, None, None, None, None, [], [], session_min_data, session_max_data)

    # Only apply session filter when the user has engaged the slider
    active_session_range = session_range if session_engaged else None

    # Apply dimension filters
    dff = _apply_filters(df, departments, physician, diagnosis_cats, status, active_session_range, c2b,
                         techniques=techniques)

    if dff.empty:
        return (na_kpi,) * 6 + (None, None, {}, None, None, None, None, None, [], [], session_min_data, session_max_data)

    # ------------------------------------------------------------------
    # Prior-period comparison
    # ------------------------------------------------------------------
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

    trend_label = None
    dff_prior = pd.DataFrame()
    if date_preset and date_preset in _PRIOR_MAP and date_col in df_all.columns:
        trend_label, prior_fn = _PRIOR_MAP[date_preset]
        prior_start, prior_end = prior_fn(start, end)
        # Apply same date mode logic to prior period
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
        dff_prior = _apply_filters(df_prior, departments, physician, diagnosis_cats, status, active_session_range, c2b,
                                   techniques=techniques)

    # All data with dimension filters but no date or status filter (for active census)
    dff_all_no_date = _apply_filters(df_all, departments, physician, diagnosis_cats, "all", active_session_range, c2b,
                                     techniques=techniques)

    # ------------------------------------------------------------------
    # Sparkline data
    # ------------------------------------------------------------------
    sparkline_data = {}
    range_months = (end.year - start.year) * 12 + (end.month - start.month) + 1
    _spark_period = "D" if range_months <= 3 else "W"

    def _build_count_sparkline(sub_df, key, color, use_col=None):
        """Build a count-based sparkline grouped by period."""
        col = use_col or date_col
        if col not in sub_df.columns or sub_df.empty:
            return
        temp = sub_df[sub_df[col].notna()].copy()
        if temp.empty:
            return
        # Clamp dates to window for overlap-matched plans
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
        """Build a median-value sparkline grouped by period."""
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

    # Active census sparkline — running count of plans under active treatment
    # at each time point. A course is active at date d if FirstTreatmentDate <= d <= LastTreatmentDate.
    if "FirstTreatmentDate" in dff_all_no_date.columns and "LastTreatmentDate" in dff_all_no_date.columns:
        _adf = dff_all_no_date[dff_all_no_date["FirstTreatmentDate"].notna()].copy()
        _adf["_lt"] = _adf["LastTreatmentDate"].fillna(_adf["FirstTreatmentDate"])
        # Cap at last actual data date (data exports lag by ~1 day)
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

    # Created sparkline (plans with PlanCreationDate in period)
    if "PlanCreationDate" in dff.columns:
        created_df = dff[(dff["PlanCreationDate"] >= start) & (dff["PlanCreationDate"] <= end)]
        _build_count_sparkline(created_df, "created", CHART_COLORWAY[0], use_col="PlanCreationDate")

    # Completed sparkline
    eff_completed = _is_effectively_completed(dff)
    completed_df = dff[eff_completed]
    _build_count_sparkline(completed_df, "completed", STATUS_COLORS["COMPLETED"])

    # Median sessions sparkline
    _build_median_sparkline(dff, "NoSessionPlanned", "sessions", CHART_COLORWAY[5])

    # Median duration sparkline (completed only)
    _build_median_sparkline(completed_df, "TreatmentDurationDays", "duration", CHART_COLORWAY[4],
                            hover_fmt="%{x|%b %d}: %{customdata:,.0f} days<extra></extra>")

    # Multi-machine sparkline (% per period)
    if "Machines" in dff.columns and date_col in dff.columns:
        temp = dff[dff[date_col].notna()].copy()
        temp["_multi"] = temp["Machines"].fillna("").str.contains(",").astype(int)
        plot_dates = temp[date_col].clip(lower=start, upper=end)
        if _spark_period == "D":
            temp["_sp"] = plot_dates.dt.normalize()
        else:
            temp["_sp"] = plot_dates.dt.to_period("W").dt.to_timestamp()
        grp = temp.groupby("_sp")["_multi"]
        pct = (grp.sum() / grp.count() * 100)
        if len(pct) > 2:
            sparkline_data["multimachine"] = {
                "labels": [d.isoformat() for d in pct.index],
                "values": [round(v, 1) for v in pct.tolist()],
                "color": CHART_COLORWAY[6],
                "hover_fmt": "%{x|%b %d}: %{customdata:.0f}%<extra></extra>",
            }

    # ------------------------------------------------------------------
    # KPIs with trends
    # ------------------------------------------------------------------

    # 1. Active Plans — across ALL data (not date-filtered)
    eff_completed_all = _is_effectively_completed(dff_all_no_date)
    active_count = int((~eff_completed_all).sum())

    # Prior-period active count: plans where prior_end falls between
    # FirstTreatmentDate and LastTreatmentDate (i.e. under treatment at that date).
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
        sparkline_id="plans-spark-active",
        trend_text=f"{_t_active[0]} {trend_label}" if _t_active[0] else None,
        trend_direction=_t_active[1],
    )

    # 2. Created (in period)
    if "PlanCreationDate" in dff.columns:
        created_count = int(
            ((dff["PlanCreationDate"] >= start) & (dff["PlanCreationDate"] <= end)).sum()
        )
    else:
        created_count = len(dff)
    _t_created = (None, None)
    if trend_label and not dff_prior.empty and "PlanCreationDate" in dff_prior.columns:
        prior_created = int(
            ((dff_prior["PlanCreationDate"] >= prior_start) & (dff_prior["PlanCreationDate"] <= prior_end)).sum()
        )
        _t_created = _trend(created_count, prior_created)
    kpi_created = kpi_card(
        "Created", f"{created_count:,}",
        accent_color=CHART_COLORWAY[0],
        sparkline_id="plans-spark-created",
        trend_text=f"{_t_created[0]} {trend_label}" if _t_created[0] else None,
        trend_direction=_t_created[1],
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
        sparkline_id="plans-spark-completed",
        trend_text=f"{_t_completed[0]} {trend_label}" if _t_completed[0] else None,
        trend_direction=_t_completed[1],
    )

    # 4. Median Sessions Planned
    median_sessions_val = None
    if not dff.empty and "NoSessionPlanned" in dff.columns:
        session_vals = pd.to_numeric(dff["NoSessionPlanned"], errors="coerce").dropna()
        median_sessions_val = session_vals.median() if not session_vals.empty else None
    _t_sessions = (None, None)
    if trend_label and not dff_prior.empty and median_sessions_val is not None:
        if "NoSessionPlanned" in dff_prior.columns:
            prior_sv = pd.to_numeric(dff_prior["NoSessionPlanned"], errors="coerce").dropna()
            if not prior_sv.empty:
                _t_sessions = _trend(median_sessions_val, prior_sv.median())
    kpi_median_sessions = kpi_card(
        "Median Sessions", f"{median_sessions_val:.0f}" if median_sessions_val is not None else "N/A",
        accent_color=CHART_COLORWAY[5],
        sparkline_id="plans-spark-sessions",
        trend_text=f"{_t_sessions[0]} {trend_label}" if _t_sessions[0] else None,
        trend_direction=_t_sessions[1],
    )

    # 5. Median Duration (completed plans only)
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
        label="Completed plans only. Calendar days from first to last treatment.",
        position="top", withArrow=True, multiline=True, w=240,
    )
    kpi_median_dur = kpi_card(
        "Median Duration", f"{median_dur_val:.0f}" if median_dur_val is not None else "N/A",
        value_detail="days",
        accent_color=CHART_COLORWAY[4],
        sparkline_id="plans-spark-duration",
        trend_text=f"{_t_dur[0]} {trend_label}" if _t_dur[0] else None,
        trend_direction=_t_dur[1],
        header_control=_dur_info,
    )

    # 6. Multi-Machine Plans (%)
    multimach_pct = None
    multimach_count = 0
    if "Machines" in dff.columns and not dff.empty:
        multimach_count = int(dff["Machines"].fillna("").str.contains(",").sum())
        multimach_pct = multimach_count / len(dff) * 100 if len(dff) > 0 else 0
    _t_mm = (None, None)
    if trend_label and not dff_prior.empty and "Machines" in dff_prior.columns and multimach_pct is not None:
        prior_mm = int(dff_prior["Machines"].fillna("").str.contains(",").sum())
        prior_mm_pct = prior_mm / len(dff_prior) * 100 if len(dff_prior) > 0 else 0
        _t_mm = _trend(multimach_pct, prior_mm_pct)
    kpi_multimachine = kpi_card(
        "Multi-Machine", f"{multimach_pct:.0f}%" if multimach_pct is not None else "N/A",
        value_detail=f"({multimach_count:,})",
        accent_color=CHART_COLORWAY[6],
        sparkline_id="plans-spark-multimachine",
        trend_text=f"{_t_mm[0]} {trend_label}" if _t_mm[0] else None,
        trend_direction=_t_mm[1],
    )

    # ------------------------------------------------------------------
    # Volume trend data (clientside)
    # ------------------------------------------------------------------
    volume_data = _prepare_volume_data(dff, agg, volume_slice, date_col=date_col, c2b=c2b,
                                       start=start, end=end, date_mode=date_mode)

    # ------------------------------------------------------------------
    # Cumulative data (clientside)
    # ------------------------------------------------------------------
    cumulative_data = _prepare_cumulative_data(
        df_all, start, end, date_preset,
        date_col, departments, physician, diagnosis_cats,
        status, active_session_range, c2b,
        techniques=techniques, date_mode=date_mode,
        mode=cumul_mode or "prior",
        period_type=cumul_period_type or "calendar",
        slice_by=cumul_slice or "site",
    )

    # ------------------------------------------------------------------
    # Remaining Charts (server-side)
    # ------------------------------------------------------------------
    chart_children = []

    # --- Row 2: Ridgeline + Technique Mix -------
    row2_charts = []

    # Ridgeline: Sessions per Plan by Year (all-time, but respects dimension filters)
    ridgeline_data = _prepare_ridgeline_data(dff_all_no_date, date_col)
    row2_charts.append(
        dmc.GridCol(
            span={"base": 12, "md": 6},
            children=dmc.Paper(
                children=[
                    dmc.Group(
                        justify="space-between",
                        align="center",
                        children=[
                            dmc.Text("Sessions per Plan by Year", size="sm", fw=500, c="#6B7280"),
                            dmc.Group(
                                gap="md", align="center",
                                children=[
                                    dmc.SegmentedControl(
                                        id="plans-ridge-mode",
                                        data=[
                                            {"value": "density", "label": "Density"},
                                            {"value": "histogram", "label": "Histogram"},
                                        ],
                                        value="density",
                                        size="xs",
                                    ),
                                    dmc.Group(
                                        id="plans-ridge-bw-group",
                                        gap=6, align="center",
                                        children=[
                                            dmc.Text("Bandwidth", size="xs", c="#9CA3AF", fw=500),
                                            dmc.Slider(
                                                id="plans-ridge-bw",
                                                min=0.05,
                                                max=1.0,
                                                step=0.05,
                                                value=0.1,
                                                size="xs",
                                                w=100,
                                                color="violet",
                                                showLabelOnHover=True,
                                                updatemode="mouseup",
                                            ),
                                        ],
                                    ),
                                ],
                            ),
                        ],
                        mb="sm",
                    ),
                    dcc.Graph(id="plans-chart-ridgeline", config={"displayModeBar": False},
                              style={"height": "720px"}),
                ],
                p="sm", radius="md", shadow="xs", withBorder=True,
            ),
        ),
    )

    # Sessions Trend + Distribution data (for stores, rendered by separate callbacks)
    session_trend_data = _prepare_session_trend_data(dff, date_col, c2b, start=start, end=end)
    session_dist_data = _prepare_session_dist_data(dff)
    quit_trend_data = _prepare_quit_trend_data(completed_df, "LastTreatmentDate", c2b, start=start, end=end)
    complexity_trend_data = _prepare_complexity_trend_data(
        dff, date_col, start=start, end=end,
    )
    technique_dist_data = _prepare_technique_dist_data(dff, date_col, start=start, end=end)

    # Right column: Median Sessions Trend (top) + Sessions Distribution (bottom)
    row2_charts.append(
        dmc.GridCol(
            span={"base": 12, "md": 6},
            children=dmc.Stack(
                gap=16,
                style={"height": "100%"},
                children=[
                    # Top: Median Sessions Trend
                    dmc.Paper(
                        children=[
                            dmc.Group(
                                justify="space-between", align="center", mb="sm",
                                children=[
                                    dmc.Group(
                                        gap="sm", align="center",
                                        children=[
                                            dmc.Text("Median Sessions Trend", size="sm", fw=500, c="#6B7280"),
                                            dmc.SegmentedControl(
                                                id="plans-session-trend-slice",
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
                                                id="plans-session-trend-agg",
                                                data=[
                                                    {"value": "W", "label": "Weekly"},
                                                    {"value": "M", "label": "Monthly"},
                                                    {"value": "Y", "label": "Yearly"},
                                                ],
                                                value="M",
                                                size="xs",
                                            ),
                                            chart_settings_popover(
                                                "plans-session-trend",
                                                chart_types=[
                                                    {"value": "line", "label": "Line"},
                                                    {"value": "area", "label": "Area"},
                                                    {"value": "bar", "label": "Bar"},
                                                ],
                                                show_smooth=True,
                                                smooth_max=12,
                                                smooth_default=0,
                                            ),
                                        ],
                                    ),
                                ],
                            ),
                            dcc.Graph(
                                id="plans-chart-session-trend",
                                config={"displayModeBar": False},
                                style={"flex": "1", "minHeight": 0},
                            ),
                        ],
                        p="sm", radius="md", shadow="xs", withBorder=True,
                        style={"flex": "1 1 0", "display": "flex", "flexDirection": "column"},
                    ),
                    # Bottom: Sessions Distribution (histogram/density)
                    dmc.Paper(
                        children=[
                            dmc.Group(
                                justify="space-between", align="center", mb="sm",
                                children=[
                                    dmc.Text("Sessions Distribution", size="sm", fw=500, c="#6B7280"),
                                    dmc.SegmentedControl(
                                        id="plans-session-dist-mode",
                                        data=[
                                            {"value": "histogram", "label": "Histogram"},
                                            {"value": "density", "label": "Density"},
                                        ],
                                        value="histogram",
                                        size="xs",
                                    ),
                                ],
                            ),
                            dcc.Graph(
                                id="plans-chart-session-dist",
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
            "plans-chart-technique-dist",
            "Technique Distribution",
            settings_id="plans-technique-dist",
            chart_types=[
                {"value": "line", "label": "Line"},
                {"value": "area", "label": "Area"},
                {"value": "bar", "label": "Bar"},
            ],
            show_smooth=True,
            smooth_max=24,
            smooth_default=3,
            paper_padding="md",
            paper_height="500px",
            graph_height="420px",
            extra_controls_left=[
                dmc.SegmentedControl(
                    id="plans-technique-dist-mode",
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
                    id="plans-technique-dist-agg",
                    data=[
                        {"value": "W", "label": "Weekly"},
                        {"value": "M", "label": "Monthly"},
                        {"value": "Y", "label": "Yearly"},
                    ],
                    value="M",
                    size="xs",
                ),
            ],
        )
    )

    # --- Course Complexity Trends (2x2 facets) ---
    chart_children.append(
        chart_card(
            "plans-chart-complexity",
            "Plan Complexity Trends",
            settings_id="plans-complexity",
            chart_types=[
                {"value": "line", "label": "Line"},
                {"value": "area", "label": "Area"},
                {"value": "bar", "label": "Bar"},
            ],
            show_smooth=True,
            smooth_max=12,
            smooth_default=4,
            paper_padding="md",
            paper_height="440px",
            graph_height="380px",
            extra_controls_left=[
                dmc.SegmentedControl(
                    id="plans-complexity-mode",
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
                    id="plans-complexity-agg",
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
    if "PrescriptionSite" in dff.columns and not dff.empty:
        sites_series = dff["PrescriptionSite"].dropna()
        if not sites_series.empty:
            _site_display = {
                "Prostate and Seminal Vessicles.": "Prostate/SV",
            }
            site_counts = sites_series.value_counts().head(15).sort_values(ascending=True)
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
                margin=dict(l=120, r=8, t=0, b=0),
            )
            fig_sites.update_xaxes(automargin=True)
            fig_sites.update_yaxes(automargin=True)
        else:
            fig_sites = empty_figure("No prescription site data")
            fig_sites.update_layout(height=None)
    else:
        fig_sites = empty_figure("No prescription site data")
        fig_sites.update_layout(height=None)

    row3a_charts.append(
        dmc.GridCol(
            span={"base": 12, "md": 6},
            children=dmc.Paper(
                children=[
                    dmc.Text("Treatment Site Distribution", size="sm", fw=500, c="#6B7280", mb=0),
                    dmc.Box(
                        pos="relative",
                        style={"flex": "1", "minHeight": 0},
                        children=[
                            dmc.Box(
                                style={"position": "absolute", "top": 0, "left": 0, "right": 0, "bottom": 0},
                                children=[
                                    dcc.Graph(
                                        figure=fig_sites,
                                        config={"displayModeBar": False},
                                        style={"height": "100%"},
                                    )
                                ],
                            )
                        ],
                    ),
                ],
                p="sm", pt="md", pb=6, radius="md", shadow="xs", withBorder=True,
                h=CHART_PAPER_HEIGHT,
                style={"display": "flex", "flexDirection": "column"},
            ),
        )
    )

    # Quitting Rate Trend (clientside-rendered from store)
    row3a_charts.append(
        dmc.GridCol(
            span={"base": 12, "md": 6},
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
                                        id="plans-quit-trend-slice",
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
                                        id="plans-quit-trend-agg",
                                        data=[
                                            {"value": "W", "label": "Weekly"},
                                            {"value": "M", "label": "Monthly"},
                                            {"value": "Y", "label": "Yearly"},
                                        ],
                                        value="M",
                                        size="xs",
                                    ),
                                    chart_settings_popover(
                                        "plans-quit-trend",
                                        chart_types=[
                                            {"value": "line", "label": "Line"},
                                            {"value": "area", "label": "Area"},
                                            {"value": "bar", "label": "Bar"},
                                        ],
                                        show_smooth=True,
                                        smooth_max=12,
                                        smooth_default=0,
                                    ),
                                ],
                            ),
                        ],
                    ),
                    dcc.Graph(
                        id="plans-chart-quit-trend",
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

    chart_children.append(dmc.Grid(gutter=16, align="stretch", children=row3a_charts))

    # ------------------------------------------------------------------
    # Detail Table (AG Grid)
    # ------------------------------------------------------------------
    table_df = dff.copy()

    table_cols = [
        "PatientFullName", "CourseId", "PlanSetupId", "PlanCreationDate",
        "ClinicalStatus", "PlanStatus", "TreatmentTechnique",
        "NoSessionPlanned", "SessionBasedFractionCount", "NoFractionsRemaining",
        "TreatmentDurationDays", "Department", "Machines", "PrescriptionSite",
    ]
    available_cols = [c for c in table_cols if c in table_df.columns]
    table_df = table_df[available_cols].copy()

    if "PlanCreationDate" in table_df.columns:
        table_df["PlanCreationDate"] = table_df["PlanCreationDate"].dt.strftime("%Y-%m-%d")

    records = table_df.to_dict("records")

    column_defs = [
        {"field": "PatientFullName", "headerName": "Patient", "width": 180},
        {"field": "CourseId", "headerName": "Course", "width": 110},
        {"field": "PlanSetupId", "headerName": "Plan Name", "width": 140},
        {"field": "PlanCreationDate", "headerName": "Created", "width": 110, "sort": "desc"},
        {"field": "ClinicalStatus", "headerName": "Status", "width": 100},
        {"field": "PlanStatus", "headerName": "Plan Status", "width": 130},
        {"field": "TreatmentTechnique", "headerName": "Technique", "width": 100},
        {"field": "NoSessionPlanned", "headerName": "Sessions", "width": 100, "type": "numericColumn"},
        {"field": "SessionBasedFractionCount", "headerName": "Delivered", "width": 100, "type": "numericColumn"},
        {"field": "NoFractionsRemaining", "headerName": "Remaining", "width": 100, "type": "numericColumn"},
        {"field": "TreatmentDurationDays", "headerName": "Duration (d)", "width": 100, "type": "numericColumn"},
        {"field": "Department", "headerName": "Department", "width": 100},
        {"field": "Machines", "headerName": "Machines", "width": 140},
        {"field": "PrescriptionSite", "headerName": "Rx Site", "width": 160},
    ]

    table_children = [
        dmc.Paper(
            children=[
                dmc.Group(
                    justify="space-between",
                    mb="sm",
                    children=[
                        dmc.Text("Plan Details", size="sm", fw=500, c="#6B7280"),
                        dmc.Button("Export CSV", id="plans-table-export", size="compact-xs", variant="light"),
                    ],
                ),
                dag.AgGrid(
                    id="plans-detail-table",
                    rowData=records,
                    columnDefs=column_defs,
                    defaultColDef=DEFAULT_COLUMN_DEFS,
                    columnSize="autoSize",
                    dashGridOptions={**DEFAULT_GRID_OPTIONS},
                    style=DEFAULT_GRID_STYLE,
                    className=DEFAULT_GRID_CLASS,
                ),
            ],
            p="md", radius="md", shadow="xs", withBorder=True,
        ),
    ]

    return (
        kpi_active, kpi_created, kpi_completed, kpi_median_sessions, kpi_median_dur, kpi_multimachine,
        volume_data, cumulative_data, sparkline_data,
        ridgeline_data, session_trend_data, session_dist_data, complexity_trend_data, technique_dist_data, quit_trend_data,
        chart_children, table_children,
        session_min_data, session_max_data,
    )


# ---------------------------------------------------------------------------
# Clientside callbacks for charts
# ---------------------------------------------------------------------------

clientside_callback(
    ClientsideFunction(namespace="census", function_name="smoothChartWithType"),
    Output("plans-chart-volume", "figure"),
    Input("plans-store-volume", "data"),
    Input("plans-volume-settings-smooth", "value"),
    Input("plans-volume-settings-type", "value"),
    State("plans-chart-volume", "figure"),
)

clientside_callback(
    ClientsideFunction(namespace="cumulative", function_name="renderCumulative"),
    Output("plans-chart-cumulative", "figure"),
    Input("plans-store-cumulative", "data"),
    Input("plans-cumulative-settings-smooth", "value"),
    Input("plans-cumulative-settings-type", "value"),
    State("plans-chart-cumulative", "figure"),
)


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# KPI Sparkline clientside callbacks
# ---------------------------------------------------------------------------

_PLANS_SPARKLINE_IDS = [
    "plans-spark-active",
    "plans-spark-created",
    "plans-spark-completed",
    "plans-spark-sessions",
    "plans-spark-duration",
    "plans-spark-multimachine",
]

for _spark_id in _PLANS_SPARKLINE_IDS:
    clientside_callback(
        ClientsideFunction(namespace="sparklines", function_name="updateFromStore"),
        Output(_spark_id, "figure"),
        Input("plans-store-kpi-sparklines", "data"),
        Input(_spark_id, "id"),
        Input("plans-smooth-slider", "value"),
    )


# ---------------------------------------------------------------------------
# Ridgeline callback (mode + bandwidth)
# ---------------------------------------------------------------------------

@callback(
    Output("plans-chart-ridgeline", "figure"),
    Input("plans-store-ridgeline", "data"),
    Input("plans-ridge-bw", "value"),
    Input("plans-ridge-mode", "value"),
)
def _update_ridgeline(data, bw, mode):
    return _build_ridgeline_figure(data, bw_factor=bw or 0.5, mode=mode or "density")


# Hide bandwidth slider in histogram mode
clientside_callback(
    """function(mode) {
        return mode === "histogram" ? {display: "none"} : {};
    }""",
    Output("plans-ridge-bw-group", "style"),
    Input("plans-ridge-mode", "value"),
)


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
                    plot_bgcolor: "#FFFFFF", paper_bgcolor: "#FFFFFF",
                    xaxis: {visible: false}, yaxis: {visible: false},
                    annotations: [{text: "No sessions data", showarrow: false,
                        xref: "paper", yref: "paper", x: 0.5, y: 0.5,
                        font: {size: 14, color: "#9CA3AF"}}]
                }
            };
        }
        var data = {
            dates: combo.dates,
            series: combo.series,
            yTitle: "Median Sessions",
            hideLegend: combo.series.length <= 1,
            stacked: false
        };
        return window.dash_clientside.census.smoothChartWithType(data, smoothVal, chartType || "line", currentFig);
    }""",
    Output("plans-chart-session-trend", "figure"),
    Input("plans-store-session-trend", "data"),
    Input("plans-session-trend-settings-smooth", "value"),
    Input("plans-session-trend-settings-type", "value"),
    Input("plans-session-trend-agg", "value"),
    Input("plans-session-trend-slice", "value"),
    State("plans-chart-session-trend", "figure"),
)


# ---------------------------------------------------------------------------
# Quit Rate Trend callback (clientside: agg + slice-by + smooth + chart type)
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
                    plot_bgcolor: "#FFFFFF", paper_bgcolor: "#FFFFFF",
                    xaxis: {visible: false}, yaxis: {visible: false},
                    annotations: [{text: "No quit rate data", showarrow: false,
                        xref: "paper", yref: "paper", x: 0.5, y: 0.5,
                        font: {size: 14, color: "#9CA3AF"}}]
                }
            };
        }
        var data = {
            dates: combo.dates,
            series: combo.series,
            yTitle: "Quit Rate (%)",
            hideLegend: combo.series.length <= 1,
            stacked: false
        };
        return window.dash_clientside.census.smoothChartWithType(data, smoothVal, chartType || "line", currentFig);
    }""",
    Output("plans-chart-quit-trend", "figure"),
    Input("plans-store-quit-trend", "data"),
    Input("plans-quit-trend-settings-smooth", "value"),
    Input("plans-quit-trend-settings-type", "value"),
    Input("plans-quit-trend-agg", "value"),
    Input("plans-quit-trend-slice", "value"),
    State("plans-chart-quit-trend", "figure"),
)


# ---------------------------------------------------------------------------
# Fractions Distribution callback (histogram/density toggle)
# ---------------------------------------------------------------------------

@callback(
    Output("plans-chart-session-dist", "figure"),
    Input("plans-store-session-dist", "data"),
    Input("plans-session-dist-mode", "value"),
)
def _update_session_dist(data, mode):
    if not data:
        fig = empty_figure("No sessions data")
        fig.update_layout(height=310)
        return fig

    mode = mode or "histogram"
    fig = go.Figure()

    if mode == "density" and data.get("kde_x"):
        fig.add_trace(go.Scatter(
            x=data["kde_x"],
            y=data["kde_y"],
            mode="lines",
            fill="tozeroy",
            line=dict(color=PRIMARY, width=2),
            fillcolor="rgba(124, 42, 131, 0.2)",
            hovertemplate="Sessions: %{x:.0f}<br>Density: %{y:.4f}<extra></extra>",
        ))
        y_title = "Density"
    else:
        fig.add_trace(go.Histogram(
            x=data["values"],
            nbinsx=30,
            marker_color=PRIMARY,
            hovertemplate="Sessions: %{x}<br>Count: %{y}<extra></extra>",
        ))
        y_title = "Plans"

    # Median vertical line
    med = data["median"]
    fig.add_vline(x=med, line_dash="dash", line_color=NEUTRAL["text_secondary"])
    fig.add_annotation(
        x=med, y=1.0, yref="paper", yshift=2,
        text=f"Median: {med:.0f}", showarrow=False,
        font=dict(size=11, color=NEUTRAL["text_secondary"]),
        yanchor="bottom", xanchor="center",
    )

    apply_default_layout(fig)
    fig.update_layout(
        height=310,
        xaxis_title=f"Sessions Planned  (n={data['n']}  Mean: {data['mean']:.0f}  IQR: {data['p25']:.0f}\u2013{data['p75']:.0f})",
        yaxis_title=y_title,
        margin=dict(l=48, r=16, t=16, b=24),
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
]


@callback(
    Output("plans-chart-complexity", "figure"),
    Input("plans-store-complexity-trends", "data"),
    Input("plans-complexity-agg", "value"),
    Input("plans-complexity-mode", "value"),
    Input("plans-complexity-settings-smooth", "value"),
    Input("plans-complexity-settings-type", "value"),
    prevent_initial_call=False,
)
def _update_complexity_facets(data, agg, mode, smooth, chart_type):
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
        rows=1, cols=2,
        subplot_titles=[title for _, title in _COMPLEXITY_FACETS],
        horizontal_spacing=0.08,
    )

    for i, (dim_key, _title) in enumerate(_COMPLEXITY_FACETS):
        row = 1
        col = i + 1
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
            fig.add_trace(go.Scatter(
                x=dates, y=values,
                mode="lines+markers",
                line=dict(color=cfg["color"], width=2),
                marker=dict(size=3),
                fill=fill_mode,
                fillcolor=_hex_to_rgba(cfg["color"]),
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
    # Re-apply subplot title styling after default layout
    for ann in fig.layout.annotations:
        ann.update(font=dict(size=12, color="#6B7280"))
    fig.update_layout(
        height=380,
        showlegend=False,
        margin=dict(l=48, r=16, t=32, b=40),
    )
    return fig


# ---------------------------------------------------------------------------
# Technique Distribution callback
# ---------------------------------------------------------------------------

@callback(
    Output("plans-chart-technique-dist", "figure"),
    Input("plans-store-technique-dist", "data"),
    Input("plans-technique-dist-mode", "value"),
    Input("plans-technique-dist-agg", "value"),
    Input("plans-technique-dist-settings-smooth", "value"),
    Input("plans-technique-dist-settings-type", "value"),
    prevent_initial_call=False,
)
def _update_technique_dist(data, mode, agg, smooth, chart_type):
    if not data:
        return empty_figure("No technique data")

    agg = agg or "M"
    combo = data.get(agg)
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
                hovertemplate=(
                    "<b>%{x|%b %Y}</b><br>"
                    + s["name"] + ": %{y:.0f}" + ("%" if mode == "pct" else "")
                    + "<extra></extra>"
                ),
            ))
        fig.update_layout(barmode="stack")
    else:
        stackgroup = "tech" if chart_type == "area" else None
        for s in proc_series:
            fig.add_trace(go.Scatter(
                x=dates,
                y=s["values"],
                name=s["name"],
                mode="lines",
                line=dict(color=s["color"], width=0.5 if chart_type == "area" else 2),
                stackgroup=stackgroup,
                fillcolor=s["color"] if chart_type == "area" else None,
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
        yaxis_title="Proportion (%)" if mode == "pct" else "Plan Count",
        showlegend=True,
        legend=dict(
            orientation="h", y=1.02, x=0.5, xanchor="center", yanchor="bottom",
            traceorder="normal",
        ),
        margin=dict(l=48, r=16, t=56, b=40),
        hovermode="x unified",
    )
    if mode == "pct":
        fig.update_yaxes(range=[0, 100])

    return fig


# Table CSV Export (clientside)
# ---------------------------------------------------------------------------

clientside_callback(
    """function(n) {
        if (!n) return window.dash_clientside.no_update;
        var gridApi = window.dash_ag_grid
            ? window.dash_ag_grid['plans-detail-table']
            : null;
        if (gridApi && gridApi.api) {
            gridApi.api.exportDataAsCsv({fileName: 'plans_detail.csv'});
        }
        return window.dash_clientside.no_update;
    }""",
    Output("plans-table-export", "n_clicks"),
    Input("plans-table-export", "n_clicks"),
    prevent_initial_call=True,
)
