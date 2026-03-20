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
    PHYSICIANS, DEPARTMENTS, DEPARTMENT_COLORS, CHART_COLORWAY, PRIMARY,
    DEFAULT_LAYOUT, FONT_FAMILY, SEMANTIC_COLORS, NEUTRAL,
    DEFAULT_COLUMN_DEFS, DEFAULT_GRID_OPTIONS, CHART_PAPER_HEIGHT,
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
                                id="courses-physician-panel",
                                children=[
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
                    # Diagnosis dropdown
                    html.Div(
                        children=[
                            html.Div(
                                children=[
                                    dmc.Button(
                                        "Diagnosis",
                                        id="courses-diagnosis-trigger",
                                        variant="default",
                                        size="sm",
                                        rightSection=DashIconify(icon="mdi:chevron-down", width=14),
                                    ),
                                    dmc.ActionIcon(
                                        DashIconify(icon="mdi:close-circle", width=18),
                                        id="courses-diagnosis-clear",
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
                                    id="courses-filter-diagnosis",
                                    multiple=True,
                                    value=[],
                                ),
                                id="courses-diagnosis-panel",
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
                                id="courses-technique-panel",
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
                        value="started",
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
                _build_courses_filter_bar(),
            ],
        ),

        # KPI row — 6 cards
        dmc.Grid(id="courses-kpi-row", gutter="md", children=[
            dmc.GridCol(id="courses-kpi-active", span={"base": 12, "sm": 6, "md": 2}),
            dmc.GridCol(id="courses-kpi-started", span={"base": 12, "sm": 6, "md": 2}),
            dmc.GridCol(id="courses-kpi-completed", span={"base": 12, "sm": 6, "md": 2}),
            dmc.GridCol(id="courses-kpi-median-fractions", span={"base": 12, "sm": 6, "md": 2}),
            dmc.GridCol(id="courses-kpi-median-duration", span={"base": 12, "sm": 6, "md": 2}),
            dmc.GridCol(id="courses-kpi-multiplan", span={"base": 12, "sm": 6, "md": 2}),
        ]),

        # Row 1: Course Volume Trend + Cumulative (half-width each)
        dmc.Grid(gutter="md", children=[
            dmc.GridCol(
                chart_card(
                    "courses-chart-volume",
                    "Course Volume Trend",
                    settings_id="courses-volume",
                    chart_types=[
                        {"value": "bar", "label": "Bar"},
                        {"value": "area", "label": "Area"},
                        {"value": "line", "label": "Line"},
                    ],
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
                            value="",
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
                            value="M",
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
                    smooth_max=50,
                    smooth_default=0,
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
        dmc.Stack(id="courses-charts", gap=16),

        # Detail table container
        dmc.Stack(id="courses-table-container", gap=0),

        # Stores for clientside rendering
        dcc.Store(id="courses-store-volume"),
        dcc.Store(id="courses-store-cumulative"),
        dcc.Store(id="courses-store-kpi-sparklines"),

        # Interval for periodic refresh
        dcc.Interval(id="courses-interval", interval=300_000, n_intervals=0),
    ],
)


# ---------------------------------------------------------------------------
# Register chart settings callbacks
# ---------------------------------------------------------------------------
register_chart_callbacks([
    ("courses-volume", "courses-chart-volume"),
    ("courses-cumulative", "courses-chart-cumulative"),
])


# ---------------------------------------------------------------------------
# Slice-by dim styling
# ---------------------------------------------------------------------------
_SLICE_CLASS_JS = """function(val) {
    return val ? "slice-group-active" : "slice-total-active";
}"""

for _sid in ["courses-volume-slice"]:
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
    Output("courses-cumulative-slice", "style"),
    Input("courses-cumulative-mode", "value"),
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
        s = idx_to_date(sv[0]).strftime("%Y-%m-%d")
        e_ts = idx_to_date(sv[1], end_of_month=True)
        today = pd.Timestamp.now().normalize()
        if e_ts > today:
            e_ts = today
        e = e_ts.strftime("%Y-%m-%d")
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
    clientside_callback(
        """function(vals) {
            if (!vals || vals.length === 0) return "Diagnosis";
            if (vals.length === 1) return vals[0];
            return vals.length + " selected";
        }""",
        Output("courses-diagnosis-trigger", "children"),
        Input("courses-filter-diagnosis", "value"),
    )

    # --- Clear-button visibility ---
    clientside_callback(
        """function(val) { return val ? {"display": "inline-flex"} : {"display": "none"}; }""",
        Output("courses-physician-clear", "style"),
        Input("courses-filter-physician", "value"),
    )
    clientside_callback(
        """function(vals) { return vals && vals.length > 0 ? {"display": "inline-flex"} : {"display": "none"}; }""",
        Output("courses-diagnosis-clear", "style"),
        Input("courses-filter-diagnosis", "value"),
    )

    # --- Clear-button actions ---
    clientside_callback(
        """function(n) { return null; }""",
        Output("courses-filter-physician", "value", allow_duplicate=True),
        Input("courses-physician-clear", "n_clicks"),
        prevent_initial_call=True,
    )
    clientside_callback(
        """function(n) { return []; }""",
        Output("courses-filter-diagnosis", "value", allow_duplicate=True),
        Input("courses-diagnosis-clear", "n_clicks"),
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
    """function(engaged, sliderMin, sliderMax) {
        if (engaged) return window.dash_clientside.no_update;
        return [sliderMin, sliderMax];
    }""",
    Output("courses-fraction-slider", "value", allow_duplicate=True),
    Input("courses-fraction-engaged", "data"),
    Input("courses-fraction-slider", "min"),
    Input("courses-fraction-slider", "max"),
    prevent_initial_call=True,
)


# ---------------------------------------------------------------------------
# Dynamic physician chip population
# ---------------------------------------------------------------------------
@callback(
    Output("courses-filter-physician", "children"),
    Input("courses-interval", "n_intervals"),
)
def _populate_physician_chips(_n):
    """Populate physician filter with MDs from the courses dataset."""
    from data.loader import load_courses

    try:
        df = load_courses()
    except Exception:
        return []

    if df.empty or "TreatingPhysician" not in df.columns:
        return []

    mds = sorted(df["TreatingPhysician"].dropna().unique())

    return [
        dmc.Chip(
            md.split(", ")[0],
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
# Data Preparation: Volume Trend
# ---------------------------------------------------------------------------

def _prepare_volume_data(dff, agg, slice_by="", date_col="CourseStartDate", c2b=None,
                         start=None, end=None):
    """Prepare course volume trend data for clientside rendering.

    When start/end are provided (e.g. "treated in" mode where overlap-matched
    courses may have date_col values outside the window), periods are clamped
    to the filter range so the chart doesn't show bars outside the window.
    """
    if dff.empty or date_col not in dff.columns:
        return None

    dff = dff.copy()
    period_code = "Y" if agg == "Y" else agg

    # For overlap-matched courses whose date_col falls before the window,
    # clamp to the window start so they appear in the first visible period.
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
                              slice_by="site"):
    """Prepare cumulative course volume data for overlay chart."""
    if df_all.empty or date_col not in df_all.columns:
        return None

    today = pd.Timestamp.now().normalize()
    if end.normalize() > today:
        end = today

    period_days = (end - start).days + 1
    if period_days < 2:
        return None

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
    dff_all = _apply_filters(df_all, departments, physician, diagnosis_cats, status, frac_range, c2b,
                             inpatient=inpatient, techniques=techniques)

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
            "yTitle": "Cumulative Courses",
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
            "yTitle": "Cumulative Courses",
        }


# ---------------------------------------------------------------------------
# Effective completion logic
# ---------------------------------------------------------------------------

_INACTIVITY_THRESHOLD_DAYS = 90


def _is_effectively_completed(df):
    """Return a boolean Series: True if a course is effectively completed.

    A course is considered completed if ANY of:
      1. ClinicalStatus == "COMPLETED"
      2. FractionsDelivered >= FractionsPrescribed (both non-null, prescribed > 0)
      3. LastDayActivityFlag is truthy (Yes/1/True)
      4. DCActivityFlag is truthy (Yes/1/True)
      5. No treatment activity in the last 90 days (inactivity timeout)
    """
    mask = pd.Series(False, index=df.index)

    if "ClinicalStatus" in df.columns:
        mask = mask | (df["ClinicalStatus"] == "COMPLETED")

    # Fractions delivered >= prescribed
    if "FractionsDelivered" in df.columns and "FractionsPrescribed" in df.columns:
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
                   inpatient=False, techniques=None):
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
# Main Callback
# ---------------------------------------------------------------------------

@callback(
    Output("courses-kpi-active", "children"),
    Output("courses-kpi-started", "children"),
    Output("courses-kpi-completed", "children"),
    Output("courses-kpi-median-fractions", "children"),
    Output("courses-kpi-median-duration", "children"),
    Output("courses-kpi-multiplan", "children"),
    Output("courses-store-volume", "data"),
    Output("courses-store-cumulative", "data"),
    Output("courses-store-kpi-sparklines", "data"),
    Output("courses-charts", "children"),
    Output("courses-table-container", "children"),
    Output("courses-fraction-slider", "min"),
    Output("courses-fraction-slider", "max"),
    Input("courses-interval", "n_intervals"),
    Input("courses-volume-agg", "value"),
    Input("courses-volume-slice", "value"),
    Input("courses-cumulative-mode", "value"),
    Input("courses-cumulative-period-type", "value"),
    Input("courses-cumulative-slice", "value"),
    Input("courses-date-slider", "value"),
    Input("courses-filter-department", "value"),
    Input("courses-filter-physician", "value"),
    Input("courses-filter-diagnosis", "value"),
    Input("courses-filter-technique", "value"),
    Input("courses-filter-status", "value"),
    Input("courses-fraction-slider", "value"),
    Input("courses-date-mode", "value"),
    Input("courses-filter-date-preset", "value"),
    Input("courses-inpatient-switch", "checked"),
    State("courses-fraction-engaged", "data"),
    running=[
        (Output("courses-chart-volume-loading", "visible"), True, False),
        (Output("courses-chart-cumulative-loading", "visible"), True, False),
    ],
)
def update_courses(_n, agg, volume_slice,
                    cumul_mode, cumul_period_type, cumul_slice,
                    slider_val,
                    departments, physician, diagnosis_cats, techniques,
                    status, frac_range, date_mode, date_preset, inpatient,
                    frac_engaged):
    from data.loader import load_courses

    na_kpi = kpi_card("--", "N/A")
    empty = empty_figure()
    empty_result = (na_kpi,) * 6 + (None, None, {}, [], [], 0, 50)

    try:
        df = load_courses()
    except Exception:
        return empty_result

    if df.empty:
        return empty_result

    # Build diagnosis lookup
    c2b = _build_diag_lookup()

    # Determine date column based on mode
    date_col = _date_col_for_mode(date_mode)

    # Ensure date column exists; fall back to CourseStartDate
    if date_col not in df.columns or df[date_col].notna().sum() == 0:
        date_col = "CourseStartDate"

    # "Completed In" mode: restrict to effectively-completed courses BEFORE
    # date filtering, so we only plot courses that actually finished — not
    # every course that happened to have a LastTreatmentDate in the window.
    if date_mode == "completed":
        df = df[_is_effectively_completed(df)]

    # Update fraction slider range from data (before date filter so range stays stable)
    frac_min_data = 0
    frac_max_data = 50
    if "FractionsPrescribed" in df.columns:
        fvals = df["FractionsPrescribed"].dropna()
        if not fvals.empty:
            frac_min_data = int(fvals.min())
            frac_max_data = int(fvals.max())

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
            # Fall back LastTreatmentDate to FirstTreatmentDate for active courses
            last = df[lt].fillna(df[ft])
            df = df[(df[ft] <= end) & (last >= start)]
    elif date_col in df.columns:
        df = df[df[date_col].notna()]
        df = df[(df[date_col] >= start) & (df[date_col] <= end)]

    if df.empty:
        return (na_kpi,) * 6 + (None, None, {}, [], [], frac_min_data, frac_max_data)

    # Only apply fraction filter when the user has engaged the slider
    active_frac_range = frac_range if frac_engaged else None

    # Apply dimension filters
    dff = _apply_filters(df, departments, physician, diagnosis_cats, status, active_frac_range, c2b,
                         inpatient=inpatient, techniques=techniques)

    if dff.empty:
        return (na_kpi,) * 6 + (None, None, {}, [], [], frac_min_data, frac_max_data)

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
        dff_prior = _apply_filters(df_prior, departments, physician, diagnosis_cats, status, active_frac_range, c2b,
                                   inpatient=inpatient, techniques=techniques)

    # All data with dimension filters but no date or status filter (for active census)
    dff_all_no_date = _apply_filters(df_all, departments, physician, diagnosis_cats, "all", active_frac_range, c2b,
                                     inpatient=inpatient, techniques=techniques)

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
        # Clamp dates to window for overlap-matched courses
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

    # Active census sparkline — running count of courses under active treatment
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

    # Started sparkline (courses with FirstTreatmentDate in period)
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

    # 1. Active Courses — across ALL data (not date-filtered)
    eff_completed_all = _is_effectively_completed(dff_all_no_date)
    active_count = int((~eff_completed_all).sum())

    # Prior-period active count: courses where prior_end falls between
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

    # 4. Median Fractions — use FractionsPrescribed for active, FractionsDelivered for completed
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
    # Volume trend data (clientside)
    # ------------------------------------------------------------------
    volume_data = _prepare_volume_data(dff, agg, volume_slice, date_col=date_col, c2b=c2b,
                                       start=start, end=end)

    # ------------------------------------------------------------------
    # Cumulative data (clientside)
    # ------------------------------------------------------------------
    cumulative_data = _prepare_cumulative_data(
        df_all, start, end, date_preset,
        date_col, departments, physician, diagnosis_cats,
        status, active_frac_range, c2b, inpatient=inpatient,
        techniques=techniques, date_mode=date_mode,
        mode=cumul_mode or "prior",
        period_type=cumul_period_type or "calendar",
        slice_by=cumul_slice or "site",
    )

    # ------------------------------------------------------------------
    # Remaining Charts (server-side)
    # ------------------------------------------------------------------
    chart_children = []

    # --- Row 2: Technique Mix + Treatment Site Distribution -------
    row2_charts = []

    # Technique Mix (donut)
    if "TreatmentTechniques" in dff.columns and not dff.empty:
        techniques = dff["TreatmentTechniques"].dropna().str.split(",")
        tech_list = []
        for t_list in techniques:
            for t in t_list:
                stripped = t.strip()
                if stripped:
                    tech_list.append(stripped)

        if tech_list:
            tech_counts = pd.Series(tech_list).value_counts().head(10)
            fig_technique = go.Figure(go.Pie(
                labels=tech_counts.index.tolist(),
                values=tech_counts.values.tolist(),
                hole=0.45,
                marker=dict(colors=CHART_COLORWAY[: len(tech_counts)]),
                textinfo="label+percent",
                textposition="outside",
                hovertemplate=(
                    "<b>%{label}</b><br>Count: %{value}<br>"
                    "%{percent}<extra></extra>"
                ),
            ))
            fig_technique.update_layout(height=380, showlegend=False)
            apply_default_layout(fig_technique)
            fig_technique.update_layout(
                margin=dict(l=20, r=20, t=20, b=20),
                showlegend=False,
            )
        else:
            fig_technique = empty_figure("No technique data available")
            fig_technique.update_layout(height=380)
    else:
        fig_technique = empty_figure("No technique data available")
        fig_technique.update_layout(height=380)

    row2_charts.append(
        dmc.GridCol(
            span={"base": 12, "md": 6},
            children=dmc.Paper(
                children=[
                    dmc.Text("Technique Mix", size="sm", fw=500, c="#6B7280", mb="sm"),
                    dcc.Graph(figure=fig_technique, config={"displayModeBar": False},
                              style={"height": "380px"}),
                ],
                p="sm", radius="md", shadow="xs", withBorder=True,
            ),
        )
    )

    # Treatment Site Distribution (horizontal bar)
    if "PrescriptionSites" in dff.columns and not dff.empty:
        sites_series = dff["PrescriptionSites"].dropna()
        if not sites_series.empty:
            site_counts = sites_series.value_counts().head(15).sort_values(ascending=True)
            fig_sites = go.Figure(go.Bar(
                y=site_counts.index.tolist(),
                x=site_counts.values.tolist(),
                orientation="h",
                marker_color=PRIMARY,
                hovertemplate="<b>%{y}</b><br>Count: %{x}<extra></extra>",
            ))
            fig_sites.update_layout(height=380)
            apply_default_layout(fig_sites)
            fig_sites.update_layout(
                yaxis_title="",
                xaxis_title="Courses",
                margin=dict(l=160, r=8, t=8, b=32),
            )
        else:
            fig_sites = empty_figure("No prescription site data")
            fig_sites.update_layout(height=380)
    else:
        fig_sites = empty_figure("No prescription site data")
        fig_sites.update_layout(height=380)

    row2_charts.append(
        dmc.GridCol(
            span={"base": 12, "md": 6},
            children=dmc.Paper(
                children=[
                    dmc.Text("Treatment Site Distribution", size="sm", fw=500, c="#6B7280", mb="sm"),
                    dcc.Graph(figure=fig_sites, config={"displayModeBar": False},
                              style={"height": "380px"}),
                ],
                p="sm", radius="md", shadow="xs", withBorder=True,
            ),
        )
    )

    chart_children.append(dmc.Grid(gutter=16, children=row2_charts))

    # --- Row 3: Duration Distribution + (placeholder) -------
    row3_charts = []

    if "TreatmentDurationDays" in completed_df.columns and not completed_df.empty:
        dur_data = completed_df["TreatmentDurationDays"].dropna()
        dur_data = dur_data[dur_data > 0]
        if not dur_data.empty:
            fig_duration = go.Figure(go.Histogram(
                x=dur_data,
                nbinsx=30,
                marker_color=STATUS_COLORS["COMPLETED"],
                hovertemplate="Duration: %{x} days<br>Count: %{y}<extra></extra>",
            ))
            fig_duration.update_layout(height=380)
            apply_default_layout(fig_duration)
            fig_duration.update_layout(
                xaxis_title="Duration (days)",
                yaxis_title="Courses",
            )
            med_val = dur_data.median()
            fig_duration.add_vline(
                x=med_val,
                line_dash="dash",
                line_color=NEUTRAL["text_secondary"],
                annotation_text=f"Median: {med_val:.0f}d",
                annotation_position="top right",
                annotation_font_size=11,
                annotation_font_color=NEUTRAL["text_secondary"],
            )
        else:
            fig_duration = empty_figure("No duration data available")
            fig_duration.update_layout(height=380)
    else:
        fig_duration = empty_figure("No duration data available")
        fig_duration.update_layout(height=380)

    row3_charts.append(
        dmc.GridCol(
            span={"base": 12, "md": 6},
            children=dmc.Paper(
                children=[
                    dmc.Text("Treatment Duration Distribution", size="sm", fw=500, c="#6B7280", mb="sm"),
                    dcc.Graph(figure=fig_duration, config={"displayModeBar": False},
                              style={"height": "380px"}),
                ],
                p="sm", radius="md", shadow="xs", withBorder=True,
            ),
        )
    )

    chart_children.append(dmc.Grid(gutter=16, children=row3_charts))

    # ------------------------------------------------------------------
    # Detail Table (AG Grid)
    # ------------------------------------------------------------------
    table_df = dff.copy()

    table_cols = [
        "PatientFullName", "CourseId", "CourseStartDate", "ClinicalStatus",
        "TreatingPhysician", "TreatmentTechniques", "FractionsPrescribed",
        "FractionsDelivered", "TreatmentDurationDays", "Department",
        "Machines", "PrescriptionSites",
    ]
    available_cols = [c for c in table_cols if c in table_df.columns]
    table_df = table_df[available_cols].copy()

    if "CourseStartDate" in table_df.columns:
        table_df["CourseStartDate"] = table_df["CourseStartDate"].dt.strftime("%Y-%m-%d")

    records = table_df.to_dict("records")

    column_defs = [
        {"field": "PatientFullName", "headerName": "Patient", "width": 180},
        {"field": "CourseId", "headerName": "Course ID", "width": 120},
        {"field": "CourseStartDate", "headerName": "Start Date", "width": 120, "sort": "desc"},
        {"field": "ClinicalStatus", "headerName": "Status", "width": 110},
        {"field": "TreatingPhysician", "headerName": "Physician", "width": 160},
        {"field": "TreatmentTechniques", "headerName": "Techniques", "width": 180},
        {"field": "FractionsPrescribed", "headerName": "Fx Prescribed", "width": 120, "type": "numericColumn"},
        {"field": "FractionsDelivered", "headerName": "Fx Delivered", "width": 110, "type": "numericColumn"},
        {"field": "TreatmentDurationDays", "headerName": "Duration (d)", "width": 110, "type": "numericColumn"},
        {"field": "Department", "headerName": "Department", "width": 110},
        {"field": "Machines", "headerName": "Machines", "width": 160},
        {"field": "PrescriptionSites", "headerName": "Rx Sites", "width": 180},
    ]

    table_children = [
        dmc.Paper(
            children=[
                dmc.Group(
                    justify="space-between",
                    mb="sm",
                    children=[
                        dmc.Text("Course Details", size="sm", fw=500, c="#6B7280"),
                        dmc.Button("Export CSV", id="courses-table-export", size="compact-xs", variant="light"),
                    ],
                ),
                dag.AgGrid(
                    id="courses-detail-table",
                    rowData=records,
                    columnDefs=column_defs,
                    defaultColDef=DEFAULT_COLUMN_DEFS,
                    dashGridOptions={**DEFAULT_GRID_OPTIONS},
                    style={"height": "500px"},
                    className="ag-theme-quartz",
                ),
            ],
            p="md", radius="md", shadow="xs", withBorder=True,
        ),
    ]

    return (
        kpi_active, kpi_started, kpi_completed, kpi_median_frac, kpi_median_dur, kpi_multiplan,
        volume_data, cumulative_data, sparkline_data,
        chart_children, table_children,
        frac_min_data, frac_max_data,
    )


# ---------------------------------------------------------------------------
# Clientside callbacks for charts
# ---------------------------------------------------------------------------

clientside_callback(
    ClientsideFunction(namespace="census", function_name="smoothChartWithType"),
    Output("courses-chart-volume", "figure"),
    Input("courses-store-volume", "data"),
    Input("courses-volume-settings-smooth", "value"),
    Input("courses-volume-settings-type", "value"),
    State("courses-chart-volume", "figure"),
)

clientside_callback(
    ClientsideFunction(namespace="cumulative", function_name="renderCumulative"),
    Output("courses-chart-cumulative", "figure"),
    Input("courses-store-cumulative", "data"),
    Input("courses-cumulative-settings-smooth", "value"),
    Input("courses-cumulative-settings-type", "value"),
    State("courses-chart-cumulative", "figure"),
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
    clientside_callback(
        ClientsideFunction(namespace="sparklines", function_name="updateFromStore"),
        Output(_spark_id, "figure"),
        Input("courses-store-kpi-sparklines", "data"),
        Input(_spark_id, "id"),
        Input("courses-smooth-slider", "value"),
    )


# Table CSV Export (clientside)
# ---------------------------------------------------------------------------

clientside_callback(
    """function(n) {
        if (!n) return window.dash_clientside.no_update;
        var gridApi = window.dash_ag_grid
            ? window.dash_ag_grid['courses-detail-table']
            : null;
        if (gridApi && gridApi.api) {
            gridApi.api.exportDataAsCsv({fileName: 'courses_detail.csv'});
        }
        return window.dash_clientside.no_update;
    }""",
    Output("courses-table-export", "n_clicks"),
    Input("courses-table-export", "n_clicks"),
    prevent_initial_call=True,
)
