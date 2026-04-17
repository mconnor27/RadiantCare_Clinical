"""OTV Audit page — on-treatment visit compliance and billing audit."""

import dash
import dash_mantine_components as dmc
from dash import callback, Input, Output, State, dcc, html, clientside_callback, ClientsideFunction
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
from components.filter_bar import department_chips, physician_short_name
from components.kpi_card import kpi_card, kpi_placeholder
from components.chart_card import chart_card, register_chart_callbacks
from components.detail_table import detail_table
from components.diagnosis_filter import diagnosis_accordion, register_diagnosis_callbacks
from utils.charts import apply_default_layout, empty_figure
from utils.tables import sanitize_for_grid
from utils.date_slider import (
    month_idx, idx_to_date, MAX_IDX, SLIDER_MARKS,
    preset_to_slider_val,
)
from utils.diagnosis_categories import build_code_to_category, primary_category, filter_by_diagnosis

dash.register_page(__name__, path="/otv-audit", name="OTV Audit", order=11)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_DEFAULT_DATE_PRESET = "12mo"


# ---------------------------------------------------------------------------
# Filter Bar
# ---------------------------------------------------------------------------

def _build_otv_filter_bar():
    """Two-row filter bar matching courses page pattern."""
    return dmc.Paper(
        children=[
            # Row 1: dimension filters
            dmc.Group(
                children=[
                    department_chips("otv"),
                    # Physician filter with role toggle
                    html.Div(
                        children=[
                            html.Div(
                                children=[
                                    dmc.Button(
                                        "Physician",
                                        id="otv-physician-trigger",
                                        variant="default",
                                        size="sm",
                                        rightSection=DashIconify(icon="mdi:chevron-down", width=14),
                                    ),
                                    dmc.ActionIcon(
                                        DashIconify(icon="mdi:close-circle", width=18),
                                        id="otv-physician-clear",
                                        variant="subtle",
                                        color="gray",
                                        size="sm",
                                        className="wf-filter-clear-btn",
                                    ),
                                ],
                                style={"position": "relative", "display": "inline-block"},
                            ),
                            dmc.Paper(
                                id="otv-physician-panel",
                                children=[
                                    dmc.SegmentedControl(
                                        id="otv-physician-role",
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
                                        id="otv-filter-physician",
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
                    # Diagnosis accordion filter
                    diagnosis_accordion("otv"),
                    # Fraction range slider
                    dmc.Group(
                        children=[
                            dmc.Text("Fractions", size="xs", c="#6B7280", fw=500,
                                     id="otv-fraction-label"),
                            dmc.RangeSlider(
                                id="otv-fraction-slider",
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
                                id="otv-fraction-clear",
                                variant="subtle",
                                color="gray",
                                size="xs",
                                style={"display": "none"},
                            ),
                        ],
                        gap=6,
                        align="center",
                    ),
                    dcc.Store(id="otv-fraction-engaged", data=False),
                    dmc.Switch(
                        id="otv-exclude-incomplete",
                        label="Completed courses only",
                        size="xs",
                        checked=True,
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
                        id="otv-filter-date-preset",
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
                            id="otv-filter-daterange",
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
                            html.Div(id="otv-date-range-label", style={"display": "none"}),
                            dmc.RangeSlider(
                                id="otvs-date-slider",
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
        # Sticky header with title and filter bar
        dmc.Box(
            className="page-sticky-header",
            children=[
                dmc.Title("OTV Audit", order=2, className="page-title",
                          style={"margin": 0, "textAlign": "center"}),
                html.Div(
                    style={"position": "relative"},
                    children=[
                        _build_otv_filter_bar(),
                        html.Div(
                            id="otv-grid-filter-badge",
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

        # KPI row
        dmc.Grid(id="otv-kpi-row", gutter="md", children=[
            dmc.GridCol(kpi_placeholder(), id="otv-kpi-total", span={"base": 6, "md": 2}),
            dmc.GridCol(kpi_placeholder(), id="otv-kpi-compliance", span={"base": 6, "md": 2}),
            dmc.GridCol(kpi_placeholder(), id="otv-kpi-extra", span={"base": 6, "md": 2}),
            dmc.GridCol(kpi_placeholder(), id="otv-kpi-toofew", span={"base": 6, "md": 2}),
            dmc.GridCol(kpi_placeholder(), id="otv-kpi-discrepancy", span={"base": 6, "md": 2}),
            dmc.GridCol(kpi_placeholder(), id="otv-kpi-missed-rvu", span={"base": 6, "md": 2}),
        ]),

        # Charts row 1: By department + Trend
        dmc.Grid(gutter="md", children=[
            dmc.GridCol(
                chart_card(
                    "otv-chart-department",
                    "Compliance by Department",
                    chart_types=None,
                    show_smooth=False,
                    settings_id="otv-dept",
                    extra_controls=[
                        dmc.SegmentedControl(
                            id="otv-dept-mode",
                            data=[
                                {"value": "count", "label": "Count"},
                                {"value": "pct", "label": "%"},
                            ],
                            value="count",
                            size="xs",
                        ),
                    ],
                ),
                span={"base": 12, "md": 6},
            ),
            dmc.GridCol(
                chart_card(
                    "otv-chart-trend",
                    "Compliance Trend",
                    chart_types=[
                        {"value": "line", "label": "Line"},
                        {"value": "area", "label": "Area"},
                        {"value": "bar", "label": "Bar"},
                    ],
                    show_smooth=True,
                    smooth_max=30,
                    smooth_default=0,
                    settings_id="otv-trend",
                    extra_controls=[
                        dmc.SegmentedControl(
                            id="otv-trend-agg",
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
        ]),

        # Charts row 2: Distribution + Discrepancy histogram
        dmc.Grid(gutter="md", children=[
            dmc.GridCol(
                dmc.Paper(
                    children=[
                        dmc.Text("Audit Result Distribution", size="sm", fw=500, c=NEUTRAL["text_secondary"], mb="sm"),
                        dmc.Box(
                            pos="relative",
                            style={"flex": "1", "minHeight": 0},
                            children=[
                                dmc.Box(
                                    style={"position": "absolute", "inset": 0},
                                    children=[
                                        dmc.LoadingOverlay(id="otv-dist-loading", visible=False, loaderProps={"type": "dots", "color": PRIMARY}),
                                        dcc.Graph(id="otv-chart-distribution", config={"displayModeBar": False}, style={"height": "100%"}),
                                    ],
                                ),
                            ],
                        ),
                    ],
                    h=CHART_PAPER_HEIGHT,
                    style={"display": "flex", "flexDirection": "column", "width": "100%"},
                    pt="md", px="md", pb="xs", radius="md", shadow="xs", withBorder=True,
                ),
                span={"base": 12, "md": 6},
            ),
            dmc.GridCol(
                dmc.Paper(
                    children=[
                        dmc.Group([
                            dmc.Group([
                                dmc.Text("Failed Cases Breakdown", size="sm", fw=500, c=NEUTRAL["text_secondary"]),
                                dmc.SegmentedControl(
                                    id="otv-breakdown-mode",
                                    data=[
                                        {"value": "count", "label": "Count"},
                                        {"value": "pct", "label": "%"},
                                    ],
                                    value="count",
                                    size="xs",
                                ),
                            ], gap="sm", align="center"),
                            dmc.SegmentedControl(
                                id="otv-breakdown-slice",
                                data=[
                                    {"value": "physician", "label": "MD"},
                                    {"value": "diagnosis", "label": "Diagnosis"},
                                    {"value": "fractions", "label": "Fractions"},
                                    {"value": "fx_mod", "label": "Modulo 5"},
                                ],
                                value="physician",
                                size="xs",
                            ),
                        ], justify="space-between", mb="sm"),
                        dmc.Box(
                            pos="relative",
                            style={"flex": "1", "minHeight": 0},
                            children=[
                                dmc.Box(
                                    style={"position": "absolute", "inset": 0},
                                    children=[
                                        dmc.LoadingOverlay(id="otv-hist-loading", visible=False, loaderProps={"type": "dots", "color": PRIMARY}),
                                        dcc.Graph(id="otv-chart-histogram", config={"displayModeBar": False}, style={"height": "100%"}),
                                    ],
                                ),
                            ],
                        ),
                    ],
                    h=CHART_PAPER_HEIGHT,
                    style={"display": "flex", "flexDirection": "column", "width": "100%"},
                    pt="md", px="md", pb="xs", radius="md", shadow="xs", withBorder=True,
                ),
                span={"base": 12, "md": 6},
            ),
        ]),

        # Detail table
        detail_table(
            "otv-detail-grid",
            title="OTV Audit Detail",
            export_id="otv-table-export",
            extra_controls=[
                dmc.SegmentedControl(
                    id="otv-table-result-filter",
                    data=[
                        {"value": "all", "label": "All"},
                        {"value": "Too Few", "label": "Too Few"},
                        {"value": "Extra Visit(s)", "label": "Extra"},
                    ],
                    value="all",
                    size="xs",
                ),
                dmc.SegmentedControl(
                    id="otv-table-course-status",
                    data=[
                        {"value": "all", "label": "All"},
                        {"value": "completed", "label": "Completed"},
                        {"value": "active", "label": "Active"},
                    ],
                    value="all",
                    size="xs",
                ),
                dmc.Button(
                    "Clear Filters",
                    id="otv-table-clear-filters",
                    size="compact-xs",
                    variant="light",
                    color="red",
                    leftSection=DashIconify(icon="mdi:filter-remove", width=14),
                    style={"display": "none"},
                ),
            ],
        ),

        # Stores
        dcc.Store(id="otv-store-kpi-sparklines"),
        dcc.Store(id="otv-table-filter-rows"),
        dcc.Interval(id="otv-interval", interval=300_000, n_intervals=0),
    ],
)

# Register gear-icon toggle + PNG export for chart cards
register_chart_callbacks([
    ("otv-dept", "otv-chart-department"),
    ("otv-trend", "otv-chart-trend"),
])

# Register diagnosis accordion callbacks
register_diagnosis_callbacks("otv")


# ---------------------------------------------------------------------------
# Filter Sync Callbacks
# ---------------------------------------------------------------------------

# Sync: top-bar "Completed courses only" switch -> table course status toggle
@callback(
    Output("otv-table-course-status", "value"),
    Input("otv-exclude-incomplete", "checked"),
    prevent_initial_call=True,
)
def _sync_exclude_to_table(checked):
    return "completed" if checked else "all"


# A) Preset -> Slider + DatePicker
@callback(
    Output("otvs-date-slider", "value", allow_duplicate=True),
    Output("otv-filter-daterange", "start_date", allow_duplicate=True),
    Output("otv-filter-daterange", "end_date", allow_duplicate=True),
    Input("otv-filter-date-preset", "value"),
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
    ClientsideFunction(namespace="otvsDateSlider", function_name="syncSlider"),
    Output("otv-filter-daterange", "start_date", allow_duplicate=True),
    Output("otv-filter-daterange", "end_date", allow_duplicate=True),
    Output("otv-date-range-label", "children"),
    Input("otvs-date-slider", "value"),
    State("otv-filter-daterange", "start_date"),
    State("otv-filter-daterange", "end_date"),
    prevent_initial_call=True,
)


# C) DatePicker -> Slider
@callback(
    Output("otvs-date-slider", "value", allow_duplicate=True),
    Input("otv-filter-daterange", "start_date"),
    Input("otv-filter-daterange", "end_date"),
    State("otvs-date-slider", "value"),
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
    Output("otv-filter-date-preset", "value", allow_duplicate=True),
    Input("otvs-date-slider", "value"),
    State("otv-filter-date-preset", "value"),
    prevent_initial_call=True,
)
def _maybe_clear_preset(slider_val, current_preset):
    if not current_preset or current_preset == "custom":
        return dash.no_update
    expected = preset_to_slider_val(current_preset, MAX_IDX)
    if slider_val == expected:
        return dash.no_update
    return "custom"


# ---------------------------------------------------------------------------
# Fraction Slider — engagement logic (matches courses page pattern)
# ---------------------------------------------------------------------------

# User drags slider -> mark as engaged
clientside_callback(
    """function(val, currentEngaged, sliderMin, sliderMax) {
        if (val && val[0] === sliderMin && val[1] === sliderMax) {
            return window.dash_clientside.no_update;
        }
        return true;
    }""",
    Output("otv-fraction-engaged", "data", allow_duplicate=True),
    Input("otv-fraction-slider", "value"),
    State("otv-fraction-engaged", "data"),
    State("otv-fraction-slider", "min"),
    State("otv-fraction-slider", "max"),
    prevent_initial_call=True,
)

# Clear button -> disengage
clientside_callback(
    """function(n) {
        if (!n) return window.dash_clientside.no_update;
        return false;
    }""",
    Output("otv-fraction-engaged", "data", allow_duplicate=True),
    Input("otv-fraction-clear", "n_clicks"),
    prevent_initial_call=True,
)

# Show/hide clear button based on engaged state
clientside_callback(
    """function(engaged) {
        return engaged ? {"display": "inline-flex"} : {"display": "none"};
    }""",
    Output("otv-fraction-clear", "style"),
    Input("otv-fraction-engaged", "data"),
)

# Dim the slider label when not engaged
clientside_callback(
    """function(engaged) {
        if (engaged) return {"color": "#7C2A83", "fontWeight": 600, "fontSize": "var(--mantine-font-size-xs)"};
        return {"color": "#9CA3AF", "fontWeight": 500, "fontSize": "var(--mantine-font-size-xs)"};
    }""",
    Output("otv-fraction-label", "style"),
    Input("otv-fraction-engaged", "data"),
)

# Dim the slider color when not engaged
clientside_callback(
    """function(engaged) {
        return engaged ? "violet" : "gray";
    }""",
    Output("otv-fraction-slider", "color"),
    Input("otv-fraction-engaged", "data"),
)

# Auto-sync slider value to [min, max] when not engaged
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
    Output("otv-fraction-slider", "value", allow_duplicate=True),
    Input("otv-fraction-engaged", "data"),
    State("otv-fraction-slider", "min"),
    State("otv-fraction-slider", "max"),
    State("otv-fraction-slider", "value"),
    prevent_initial_call=True,
)


# ---------------------------------------------------------------------------
# Physician Filter — UI callbacks
# ---------------------------------------------------------------------------

# Trigger label: show selected MD last name or default "Physician"
clientside_callback(
    """function(val) {
        if (!val) return "Physician";
        return val.split(", ")[0];
    }""",
    Output("otv-physician-trigger", "children"),
    Input("otv-filter-physician", "value"),
)

# Clear-button visibility
clientside_callback(
    """function(val) { return val ? {"display": "inline-flex"} : {"display": "none"}; }""",
    Output("otv-physician-clear", "style"),
    Input("otv-filter-physician", "value"),
)

# Clear-button action
clientside_callback(
    """function(n) { return null; }""",
    Output("otv-filter-physician", "value", allow_duplicate=True),
    Input("otv-physician-clear", "n_clicks"),
    prevent_initial_call=True,
)


# Populate physician chips from Courses data, filtered by current selections
@callback(
    Output("otv-filter-physician", "children"),
    Output("otv-filter-physician", "value"),
    Input("otv-physician-role", "value"),
    Input("otv-interval", "n_intervals"),
    Input("otvs-date-slider", "value"),
    Input("otv-filter-department", "value"),
    Input("otv-exclude-incomplete", "checked"),
    Input("otv-diag-store", "data"),
    Input("otv-diag-mode", "data"),
    State("otv-filter-physician", "value"),
)
def _populate_physician_chips(physician_role, _n, slider_val, departments, exclude_incomplete,
                              diag_cats, diag_mode, current_val):
    from data.loader import load_otvs, load_courses, load_diagnosis

    try:
        otv = load_otvs()
        courses = load_courses()
    except Exception:
        return [], None

    # Determine which column to use
    phys_col = "ConsultPhysician" if physician_role == "consult" else "TreatingPhysician"
    if phys_col not in courses.columns:
        return [], None

    # Join physician from courses onto OTV keys
    if not {"PatientId", "CourseId"}.issubset(otv.columns) or not {"PatientId", "CourseId"}.issubset(courses.columns):
        return [], None

    phy_map = courses[["PatientId", "CourseId", phys_col]].drop_duplicates(
        subset=["PatientId", "CourseId"], keep="last"
    )
    phy_map["PatientId"] = phy_map["PatientId"].astype(str)
    phy_map["CourseId"] = phy_map["CourseId"].astype(str)
    otv = otv.copy()
    otv["PatientId"] = otv["PatientId"].astype(str)
    otv["CourseId"] = otv["CourseId"].astype(str)
    merged = otv.merge(phy_map, on=["PatientId", "CourseId"], how="left")

    # Apply active filters so MD list reflects filtered data
    if exclude_incomplete:
        try:
            completed_keys = _completed_course_keys()
            if completed_keys:
                keys = merged["PatientId"] + "|" + merged["CourseId"]
                merged = merged[keys.isin(completed_keys)]
        except Exception:
            pass

    date_col = "LastTreatmentDate" if "LastTreatmentDate" in merged.columns else "FirstTreatmentDate"
    if date_col in merged.columns:
        merged[date_col] = pd.to_datetime(merged[date_col], errors="coerce")
        start, end = _get_date_range(slider_val, None)
        merged = merged[merged[date_col].notna() & (merged[date_col] >= start) & (merged[date_col] <= end)]

    all_depts = set(DEPARTMENTS)
    if departments and "Department" in merged.columns and set(departments) != all_depts:
        merged = merged[merged["Department"].isin(departments)]

    if diag_cats and "DiagnosisCodes" in merged.columns:
        try:
            diag_df = load_diagnosis()
            c2c = build_code_to_category(diag_df)
            merged = filter_by_diagnosis(merged, diag_cats, c2c, mode=diag_mode or "primary")
        except Exception:
            pass

    mds = sorted(merged[phys_col].dropna().unique())
    chips = [
        dmc.Chip(physician_short_name(md), value=md, size="xs", variant="filled")
        for md in mds
    ]

    # Clear selection when role toggle changes (so stale value doesn't persist)
    clear_val = None if dash.ctx.triggered_id == "otv-physician-role" else dash.no_update
    # If current value is no longer in the available list, clear it
    if current_val and current_val not in mds:
        clear_val = None

    return chips, clear_val


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


def _apply_grid_row_filter(dff, grid_rows):
    """Filter dff to only rows matching the grid's visible row indices."""
    if grid_rows is None or dff is None or dff.empty:
        return dff
    idx_set = set(int(i) for i in grid_rows)
    return dff.loc[dff.index.isin(idx_set)].reset_index(drop=True)


_INACTIVITY_THRESHOLD_DAYS = 90


def _completed_course_keys():
    """Return set of 'PatientId|CourseId' keys for effectively completed courses.

    Uses courses page completion logic: ClinicalStatus, session counts,
    LastDayActivityFlag, DCActivityFlag, and 90-day inactivity timeout.
    Join key is PatientId+CourseId because CourseId alone is not unique
    across patients (e.g., multiple patients can have 'C1_Prostate').
    """
    from data.loader import load_courses

    courses = load_courses()
    if courses.empty or "PatientId" not in courses.columns or "CourseId" not in courses.columns:
        return set()

    mask = pd.Series(False, index=courses.index)

    if "ClinicalStatus" in courses.columns:
        mask = mask | (courses["ClinicalStatus"] == "COMPLETED")

    if "CourseSessionsDelivered" in courses.columns and "CourseSessionsPlanned" in courses.columns:
        sd = pd.to_numeric(courses["CourseSessionsDelivered"], errors="coerce")
        sp = pd.to_numeric(courses["CourseSessionsPlanned"], errors="coerce")
        mask = mask | ((sd >= sp) & sp.notna() & (sp > 0) & sd.notna())

    if "LastDayActivityFlag" in courses.columns:
        ld = courses["LastDayActivityFlag"].astype(str).str.strip().str.lower()
        mask = mask | ld.isin({"yes", "1", "true"})

    if "DCActivityFlag" in courses.columns:
        dc = courses["DCActivityFlag"].astype(str).str.strip().str.lower()
        mask = mask | dc.isin({"yes", "1", "true"})

    if "LastTreatmentDate" in courses.columns:
        today = pd.Timestamp.now().normalize()
        days_since = (today - courses["LastTreatmentDate"]).dt.days
        mask = mask | (days_since > _INACTIVITY_THRESHOLD_DAYS)

    completed = courses[mask]
    return set(
        completed["PatientId"].astype(str) + "|" + completed["CourseId"].astype(str)
    )


def _trend(curr, prior, invert=False):
    """Compute trend % and direction."""
    if prior is None or prior == 0:
        return None, None
    pct = (curr - prior) / abs(prior) * 100
    direction = ("down" if pct > 0 else "up") if invert else ("up" if pct > 0 else "down")
    return f"{abs(pct):.0f}%", direction


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


# ---------------------------------------------------------------------------
# Main Callback
# ---------------------------------------------------------------------------
@callback(
    Output("otv-kpi-total", "children"),
    Output("otv-kpi-compliance", "children"),
    Output("otv-kpi-extra", "children"),
    Output("otv-kpi-toofew", "children"),
    Output("otv-kpi-discrepancy", "children"),
    Output("otv-kpi-missed-rvu", "children"),
    Output("otv-chart-department", "figure"),
    Output("otv-chart-trend", "figure"),
    Output("otv-chart-distribution", "figure"),
    Output("otv-chart-histogram", "figure"),
    Output("otv-detail-grid", "rowData"),
    Output("otv-detail-grid", "columnDefs"),
    Output("otv-store-kpi-sparklines", "data"),
    Output("otv-chart-department-loading", "visible"),
    Output("otv-chart-trend-loading", "visible"),
    Output("otv-dist-loading", "visible"),
    Output("otv-hist-loading", "visible"),
    Output("otv-fraction-slider", "min"),
    Output("otv-fraction-slider", "max"),
    Input("otv-interval", "n_intervals"),
    Input("otvs-date-slider", "value"),
    Input("otv-filter-date-preset", "value"),
    Input("otv-filter-department", "value"),
    Input("otv-exclude-incomplete", "checked"),
    Input("otv-breakdown-slice", "value"),
    Input("otv-breakdown-mode", "value"),
    Input("otv-dept-mode", "value"),
    Input("otv-trend-settings-type", "value"),
    Input("otv-trend-agg", "value"),
    Input("otv-trend-settings-smooth", "value"),
    Input("otv-table-result-filter", "value"),
    Input("otv-table-course-status", "value"),
    Input("otv-filter-physician", "value"),
    Input("otv-physician-role", "value"),
    Input("otv-diag-store", "data"),
    Input("otv-diag-mode", "data"),
    Input("otv-fraction-slider", "value"),
    Input("otv-table-filter-rows", "data"),
    State("otv-fraction-engaged", "data"),
)
def update_otv_audit(_n, slider_val, date_preset, departments, exclude_incomplete,
                     breakdown_slice, breakdown_mode, dept_mode, trend_chart_type, trend_agg, trend_smooth,
                     table_result_filter, table_course_status, physician, physician_role,
                     diag_cats, diag_mode, frac_range, grid_rows, frac_engaged):
    from data.loader import load_otvs, load_courses, load_diagnosis

    empty = empty_figure("OTV Audit data unavailable")
    na_kpi = kpi_card("--", "N/A")
    loading_off = False

    _empty_return = (na_kpi,) * 6 + (empty,) * 4 + ([], []) + (None,) + (loading_off,) * 4 + (0, 50)

    try:
        otv = load_otvs()
    except Exception:
        return _empty_return

    # Exclude incomplete courses using courses-page completion logic
    # Joined on PatientId+CourseId (CourseId alone is not patient-unique)
    if exclude_incomplete and "PatientId" in otv.columns and "CourseId" in otv.columns:
        try:
            completed_keys = _completed_course_keys()
            if completed_keys:
                otv_keys = otv["PatientId"].astype(str) + "|" + otv["CourseId"].astype(str)
                otv = otv[otv_keys.isin(completed_keys)]
        except Exception:
            pass

    # Join physician from Courses (OTV Audit has no physician columns)
    phys_col = "ConsultPhysician" if physician_role == "consult" else "TreatingPhysician"
    if {"PatientId", "CourseId"}.issubset(otv.columns):
        try:
            courses = load_courses()
            if {phys_col, "PatientId", "CourseId"}.issubset(courses.columns):
                phy_map = courses[["PatientId", "CourseId", phys_col]].drop_duplicates(
                    subset=["PatientId", "CourseId"], keep="last"
                )
                phy_map["PatientId"] = phy_map["PatientId"].astype(str)
                phy_map["CourseId"] = phy_map["CourseId"].astype(str)
                otv["PatientId"] = otv["PatientId"].astype(str)
                otv["CourseId"] = otv["CourseId"].astype(str)
                otv = otv.merge(phy_map, on=["PatientId", "CourseId"], how="left")
        except Exception:
            pass

    # Apply physician filter
    if physician and phys_col in otv.columns:
        otv = otv[otv[phys_col] == physician]

    # Apply diagnosis filter
    if diag_cats and "DiagnosisCodes" in otv.columns:
        try:
            diag_df = load_diagnosis()
            c2c = build_code_to_category(diag_df)
            otv = filter_by_diagnosis(otv, diag_cats, c2c, mode=diag_mode or "primary")
        except Exception:
            pass

    # Date column
    date_col = "LastTreatmentDate" if "LastTreatmentDate" in otv.columns else "FirstTreatmentDate"
    if date_col in otv.columns:
        otv[date_col] = pd.to_datetime(otv[date_col], errors="coerce")

    # Optionally recalculate AuditResult to fix courses that straddled the
    # Aug-2021 billing switchover from "Weekly Chart Check" (77336) to
    # "Weekly check oncochart" (77427).
    #
    # SQL logic (OTV_Audit.sql:697-724):
    #   Too Few:  CPTs_ExclNC < Allowed  (if billing exists, else WeeklyExams < Allowed)
    #   Extra:    WeeklyExams > Allowed  (always uses exams, catches NC'd extras)
    #   OK:       everything else
    #
    # Our fix: for "Too Few", use max(CPTs_ExclNC, WeeklyExams) so transition
    # courses aren't penalised when CPTs are partial but exams are complete.
    if {"WeeklyExamActivities", "ManagementCPTs_ExcludingNC", "AllowedOTVs"} <= set(otv.columns):
        exams = otv["WeeklyExamActivities"]
        cpts = otv["ManagementCPTs_ExcludingNC"]
        allowed = otv["AllowedOTVs"]
        effective_for_toofew = pd.concat([exams, cpts], axis=1).max(axis=1)
        otv["AuditResult"] = "OK"
        otv.loc[exams > allowed, "AuditResult"] = "Extra Visit(s)"
        otv.loc[effective_for_toofew < allowed, "AuditResult"] = "Too Few"

    # Fraction slider range (before date filter so range stays stable)
    frac_col = "PrescribedFractions"
    frac_min_data, frac_max_data = 0, 50
    if frac_col in otv.columns:
        fvals = pd.to_numeric(otv[frac_col], errors="coerce").dropna()
        if not fvals.empty:
            frac_min_data = int(fvals.min())
            frac_max_data = int(fvals.max())

    # Date range from slider
    start, end = _get_date_range(slider_val, None)

    # Filter by date
    df = otv.copy()
    if date_col in df.columns:
        df = df[df[date_col].notna()]
        df = df[(df[date_col] >= start) & (df[date_col] <= end)]

    # Department filter: when all departments selected (or none), show everything
    # including records with no department. Only filter when a subset is chosen.
    all_depts = set(DEPARTMENTS)
    if departments and "Department" in df.columns and set(departments) != all_depts:
        df = df[df["Department"].isin(departments)]

    # Fraction range filter (only when engaged)
    active_frac_range = frac_range if frac_engaged else None
    if active_frac_range and frac_col in df.columns:
        fmin, fmax = active_frac_range
        vals = pd.to_numeric(df[frac_col], errors="coerce")
        df = df[((vals >= fmin) & (vals <= fmax)) | vals.isna()]

    if df.empty:
        return _empty_return

    # --- Table (built from df before grid row filter) ---
    triggered_by_grid = (
        dash.callback_context.triggered
        and len(dash.callback_context.triggered) == 1
        and dash.callback_context.triggered[0]["prop_id"] == "otv-table-filter-rows.data"
    )
    if triggered_by_grid:
        table_rows = dash.no_update
        table_cols = dash.no_update
    else:
        table_rows, table_cols = _build_table(df, table_result_filter, table_course_status)

    # Apply grid row filter — KPIs, sparklines, and charts use the subset
    dff = _apply_grid_row_filter(df, grid_rows)

    # --- Prior-period comparison ---
    trend_label = None
    df_prior = pd.DataFrame()
    if date_preset and date_preset in _PRIOR_MAP and date_col in otv.columns:
        trend_label, prior_fn = _PRIOR_MAP[date_preset]
        prior_start, prior_end = prior_fn(start, end)
        df_prior = otv[otv[date_col].notna()]
        df_prior = df_prior[(df_prior[date_col] >= prior_start) & (df_prior[date_col] <= prior_end)]
        if departments and "Department" in df_prior.columns and set(departments) != all_depts:
            df_prior = df_prior[df_prior["Department"].isin(departments)]
        if active_frac_range and frac_col in df_prior.columns:
            fmin, fmax = active_frac_range
            pvals = pd.to_numeric(df_prior[frac_col], errors="coerce")
            df_prior = df_prior[((pvals >= fmin) & (pvals <= fmax)) | pvals.isna()]

    # --- KPIs (from grid-filtered dff) ---
    total = len(dff)
    has_result = "AuditResult" in dff.columns
    ok_count = (dff["AuditResult"] != "Too Few").sum() if has_result else 0
    extra_count = (dff["AuditResult"] == "Extra Visit(s)").sum() if has_result else 0
    toofew_count = (dff["AuditResult"] == "Too Few").sum() if has_result else 0
    compliance_rate = (ok_count / total * 100) if total > 0 else 0

    # Discrepancy calculation
    if "ManagementCPTs_Total" in dff.columns and "AllowedOTVs" in dff.columns:
        dff["Discrepancy"] = dff["ManagementCPTs_Total"] - dff["AllowedOTVs"]
        non_ok = dff[dff["AuditResult"] != "OK"] if has_result else dff
        avg_discrepancy = non_ok["Discrepancy"].mean() if len(non_ok) > 0 else 0
    else:
        avg_discrepancy = 0

    # Prior-period KPI values for trends
    _t_total = (None, None)
    _t_compliance = (None, None)
    _t_extra = (None, None)
    _t_toofew = (None, None)
    _t_discrepancy = (None, None)

    if trend_label and not df_prior.empty:
        prior_total = len(df_prior)
        prior_has_result = "AuditResult" in df_prior.columns
        prior_ok = (df_prior["AuditResult"] != "Too Few").sum() if prior_has_result else 0
        prior_extra = (df_prior["AuditResult"] == "Extra Visit(s)").sum() if prior_has_result else 0
        prior_toofew = (df_prior["AuditResult"] == "Too Few").sum() if prior_has_result else 0
        prior_compliance = (prior_ok / prior_total * 100) if prior_total > 0 else 0

        _t_total = _trend(total, prior_total)
        _t_compliance = _trend(compliance_rate, prior_compliance)
        _t_extra = _trend(extra_count, prior_extra, invert=True)  # More extras is bad
        _t_toofew = _trend(toofew_count, prior_toofew, invert=True)  # More too-few is bad

        if "ManagementCPTs_Total" in df_prior.columns and "AllowedOTVs" in df_prior.columns:
            df_prior_disc = df_prior.copy()
            df_prior_disc["Discrepancy"] = df_prior_disc["ManagementCPTs_Total"] - df_prior_disc["AllowedOTVs"]
            prior_non_ok = df_prior_disc[df_prior_disc["AuditResult"] != "OK"] if prior_has_result else df_prior_disc
            prior_avg_disc = prior_non_ok["Discrepancy"].mean() if len(prior_non_ok) > 0 else 0
            _t_discrepancy = _trend(avg_discrepancy, prior_avg_disc, invert=True)

    kpi_total = kpi_card(
        "Total Courses", f"{total:,}",
        accent_color=PRIMARY,
        sparkline_id="otv-spark-total",
        trend_text=f"{_t_total[0]} {trend_label}" if _t_total[0] else None,
        trend_direction=_t_total[1],
    )
    kpi_compliance = kpi_card(
        "Compliance Rate", f"{compliance_rate:.1f}%",
        accent_color=SEMANTIC_COLORS["success"] if compliance_rate >= 90 else SEMANTIC_COLORS["warning"],
        sparkline_id="otv-spark-compliance",
        trend_text=f"{_t_compliance[0]} {trend_label}" if _t_compliance[0] else None,
        trend_direction=_t_compliance[1],
    )
    kpi_extra = kpi_card(
        "Extra Visits", f"{extra_count:,}",
        accent_color=SEMANTIC_COLORS["warning"],
        sparkline_id="otv-spark-extra",
        trend_text=f"{_t_extra[0]} {trend_label}" if _t_extra[0] else None,
        trend_direction=_t_extra[1],
    )
    kpi_toofew = kpi_card(
        "Too Few Visits", f"{toofew_count:,}",
        accent_color=SEMANTIC_COLORS["error"],
        sparkline_id="otv-spark-toofew",
        trend_text=f"{_t_toofew[0]} {trend_label}" if _t_toofew[0] else None,
        trend_direction=_t_toofew[1],
    )
    kpi_discrepancy = kpi_card(
        "Avg Discrepancy", f"{avg_discrepancy:+.1f}",
        sparkline_id="otv-spark-discrepancy",
        trend_text=f"{_t_discrepancy[0]} {trend_label}" if _t_discrepancy[0] else None,
        trend_direction=_t_discrepancy[1],
    )

    # --- Missed wRVU ---
    # Determine correct management CPT per course based on fractions and technique:
    #   77431 — 1-2 fx course (once per course)
    #   77432 — SRS single-fraction cranial (per session)
    #   77435 — SBRT 3-5 fx (per fraction)
    #   77427 — Conventional 6+ fx (per 5 fractions)
    missed_wrvu = 0.0
    missed_dollars = 0.0
    _MEDICARE_CF = 32.35  # 2026 Medicare conversion factor ($/RVU)

    # RVU lookup by code and year
    _rvu_by_code = {}  # code -> {year: wRVU}
    _mp_by_code = {}   # code -> {year: MP_RVU}
    _fac_total_by_code = {}  # code -> {year: Fac_Total_RVU}
    try:
        from data.loader import load_rvu_lookup
        _rvu_tbl = load_rvu_lookup()
        for _code in ["77427", "77431", "77432", "77435"]:
            _sub = _rvu_tbl[_rvu_tbl["HCPCS"] == _code].set_index("Year")
            _rvu_by_code[_code] = _sub["wRVU"]
            _mp_by_code[_code] = _sub["MP_RVU"] if "MP_RVU" in _sub.columns else pd.Series(dtype=float)
            _fac_total_by_code[_code] = _sub["Fac_Total_RVU"] if "Fac_Total_RVU" in _sub.columns else pd.Series(dtype=float)
    except Exception:
        pass

    # Fallback values (2026)
    _FALLBACK_WRVU = {"77427": 3.37, "77431": 1.76, "77432": 7.72, "77435": 11.57}
    _FALLBACK_MP = {"77427": 0.26, "77431": 0.14, "77432": 0.61, "77435": 0.92}
    _FALLBACK_FAC_TOTAL = {"77427": 5.85, "77431": 3.19, "77432": 12.70, "77435": 19.20}
    # All sites: physician group earns pro fees only (wRVU + MP_RVU)

    def _classify_mgmt_cpt(row):
        """Determine the management CPT code for a course."""
        fx = row.get("SessionCount_Delivery", 0) or 0
        course_id = str(row.get("CourseId", "")).upper()
        is_srs_sbrt = any(k in course_id for k in ["SRS", "SBRT", "SRT", "STEREO"])
        if fx <= 2:
            if is_srs_sbrt and fx == 1 and any(k in course_id for k in ["SRS", "BRAIN", "CRANIAL"]):
                return "77432"  # SRS management
            return "77431"  # Short-course management
        if is_srs_sbrt and fx <= 5:
            return "77435"  # SBRT management
        return "77427"  # Conventional management

    def _calc_missed(frame):
        """Return (missed_wrvu, missed_dollars) for Too Few courses."""
        if frame.empty or "AuditResult" not in frame.columns:
            return 0.0, 0.0
        tf = frame[frame["AuditResult"] == "Too Few"]
        if tf.empty or not {"AllowedOTVs", "WeeklyExamActivities", "ManagementCPTs_ExcludingNC"} <= set(tf.columns):
            return 0.0, 0.0
        actual = tf[["WeeklyExamActivities", "ManagementCPTs_ExcludingNC"]].max(axis=1)
        missed = (tf["AllowedOTVs"] - actual).clip(lower=0)
        cpt_codes = tf.apply(_classify_mgmt_cpt, axis=1)
        years = tf[date_col].dt.year if date_col in tf.columns else pd.Series(2026, index=tf.index)
        wrvu_total = 0.0
        dollar_total = 0.0
        for code in ["77427", "77431", "77432", "77435"]:
            mask = cpt_codes == code
            if not mask.any():
                continue
            # wRVU (always the work component)
            if code in _rvu_by_code and not _rvu_by_code[code].empty:
                row_wrvu = years[mask].map(_rvu_by_code[code]).fillna(_FALLBACK_WRVU[code])
            else:
                row_wrvu = pd.Series(_FALLBACK_WRVU[code], index=tf.index[mask])
            wrvu_total += (missed[mask] * row_wrvu).sum()

            # Dollars: pro fees only at all sites — (wRVU + MP) × CF
            if code in _rvu_by_code and not _rvu_by_code[code].empty:
                row_mp = years[mask].map(_mp_by_code.get(code, pd.Series(dtype=float))).fillna(_FALLBACK_MP[code])
            else:
                row_mp = pd.Series(_FALLBACK_MP[code], index=tf.index[mask])
            dollar_total += (missed[mask] * (row_wrvu + row_mp) * _MEDICARE_CF).sum()

        return wrvu_total, dollar_total

    missed_wrvu, missed_dollars = _calc_missed(dff)

    # Prior-period missed wRVU trend
    _t_missed = (None, None)
    if trend_label and not df_prior.empty:
        prior_missed_wrvu, _ = _calc_missed(df_prior)
        _t_missed = _trend(missed_wrvu, prior_missed_wrvu, invert=True)

    kpi_missed_rvu = kpi_card(
        "Missed wRVU", f"{missed_wrvu:,.1f}",
        accent_color=SEMANTIC_COLORS["error"],
        value_detail=f"(${missed_dollars:,.0f})",
        sparkline_id="otv-spark-missedrvu",
        trend_text=f"{_t_missed[0]} {trend_label}" if _t_missed[0] else None,
        trend_direction=_t_missed[1],
    )

    # --- Sparkline data ---
    sparkline_data = {}
    range_months = (end.year - start.year) * 12 + (end.month - start.month) + 1
    _spark_period = "D" if range_months <= 3 else "W"

    if date_col in dff.columns and has_result:
        temp = dff[dff[date_col].notna()].copy()
        if not temp.empty:
            if _spark_period == "D":
                temp["_sp"] = temp[date_col].dt.normalize()
            else:
                temp["_sp"] = temp[date_col].dt.to_period("W").dt.to_timestamp()

            # Total courses sparkline
            grp_total = temp.groupby("_sp").size()
            if len(grp_total) > 2:
                sparkline_data["total"] = {
                    "labels": [d.isoformat() for d in grp_total.index],
                    "values": grp_total.tolist(),
                    "color": PRIMARY,
                }

            # Compliance rate sparkline
            grp_comp = temp.groupby("_sp").apply(
                lambda x: (x["AuditResult"] != "Too Few").sum() / len(x) * 100 if len(x) > 0 else 0
            )
            if len(grp_comp) > 2:
                sparkline_data["compliance"] = {
                    "labels": [d.isoformat() for d in grp_comp.index],
                    "values": [round(v, 1) for v in grp_comp.tolist()],
                    "color": SEMANTIC_COLORS["success"],
                    "hover_fmt": "%{x|%b %d}: %{customdata:.1f}%<extra></extra>",
                }

            # Extra visits sparkline
            extra_temp = temp[temp["AuditResult"] == "Extra Visit(s)"]
            if not extra_temp.empty:
                grp_extra = extra_temp.groupby("_sp").size()
                # Reindex to full period range to fill gaps with 0
                grp_extra = grp_extra.reindex(grp_total.index, fill_value=0)
                if len(grp_extra) > 2:
                    sparkline_data["extra"] = {
                        "labels": [d.isoformat() for d in grp_extra.index],
                        "values": grp_extra.tolist(),
                        "color": SEMANTIC_COLORS["warning"],
                    }

            # Too few sparkline
            toofew_temp = temp[temp["AuditResult"] == "Too Few"]
            if not toofew_temp.empty:
                grp_toofew = toofew_temp.groupby("_sp").size()
                grp_toofew = grp_toofew.reindex(grp_total.index, fill_value=0)
                if len(grp_toofew) > 2:
                    sparkline_data["toofew"] = {
                        "labels": [d.isoformat() for d in grp_toofew.index],
                        "values": grp_toofew.tolist(),
                        "color": SEMANTIC_COLORS["error"],
                    }

            # Discrepancy sparkline (mean per period)
            if "Discrepancy" in temp.columns:
                non_ok_temp = temp[temp["AuditResult"] != "OK"]
                if not non_ok_temp.empty:
                    grp_disc = non_ok_temp.groupby("_sp")["Discrepancy"].mean()
                    if len(grp_disc) > 2:
                        sparkline_data["discrepancy"] = {
                            "labels": [d.isoformat() for d in grp_disc.index],
                            "values": [round(v, 2) for v in grp_disc.tolist()],
                            "color": CHART_COLORWAY[4],
                            "hover_fmt": "%{x|%b %d}: %{customdata:+.1f}<extra></extra>",
                        }

            # Missed wRVU sparkline (sum per period)
            if not toofew_temp.empty and {"AllowedOTVs", "WeeklyExamActivities", "ManagementCPTs_ExcludingNC"} <= set(temp.columns):
                tf_sp = toofew_temp.copy()
                tf_actual = tf_sp[["WeeklyExamActivities", "ManagementCPTs_ExcludingNC"]].max(axis=1)
                tf_sp["_missed_count"] = (tf_sp["AllowedOTVs"] - tf_actual).clip(lower=0)
                tf_sp["_cpt"] = tf_sp.apply(_classify_mgmt_cpt, axis=1)
                tf_sp["_wrvu_each"] = tf_sp["_cpt"].map(_FALLBACK_WRVU)
                tf_sp["_missed"] = tf_sp["_missed_count"] * tf_sp["_wrvu_each"]
                grp_missed = tf_sp.groupby("_sp")["_missed"].sum()
                grp_missed = grp_missed.reindex(grp_total.index, fill_value=0)
                if len(grp_missed) > 2:
                    sparkline_data["missedrvu"] = {
                        "labels": [d.isoformat() for d in grp_missed.index],
                        "values": [round(v, 1) for v in grp_missed.tolist()],
                        "color": SEMANTIC_COLORS["error"],
                        "hover_fmt": "%{x|%b %d}: %{customdata:.1f} wRVU<extra></extra>",
                    }

    # --- Charts (from grid-filtered dff) ---
    fig_dept = _build_department_chart(dff, dept_mode or "count")
    fig_trend = _build_trend_chart(dff, date_col, trend_chart_type or "line", trend_agg or "M", trend_smooth or 0)
    fig_dist = _build_distribution_chart(dff)
    fig_hist = _build_failed_breakdown(dff, breakdown_slice or "physician", breakdown_mode or "count")

    return (
        kpi_total, kpi_compliance, kpi_extra, kpi_toofew, kpi_discrepancy, kpi_missed_rvu,
        fig_dept, fig_trend, fig_dist, fig_hist, table_rows, table_cols,
        sparkline_data,
        False, False, False, False,
        frac_min_data, frac_max_data,
    )


# ---------------------------------------------------------------------------
# KPI Sparkline clientside callbacks
# ---------------------------------------------------------------------------

_OTV_SPARKLINE_IDS = [
    "otv-spark-total",
    "otv-spark-compliance",
    "otv-spark-extra",
    "otv-spark-toofew",
    "otv-spark-discrepancy",
    "otv-spark-missedrvu",
]

for _spark_id in _OTV_SPARKLINE_IDS:
    clientside_callback(
        ClientsideFunction(namespace="sparklines", function_name="updateFromStore"),
        Output(_spark_id, "figure"),
        Input("otv-store-kpi-sparklines", "data"),
        Input(_spark_id, "id"),
    )


# ---------------------------------------------------------------------------
# Grid filter → chart sync
# ---------------------------------------------------------------------------

# Extract _row_idx from virtualRowData, toggle badge + clear button
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
    Output("otv-table-filter-rows", "data"),
    Output("otv-grid-filter-badge", "style"),
    Output("otv-table-clear-filters", "style"),
    Input("otv-detail-grid", "virtualRowData"),
    State("otv-detail-grid", "rowData"),
    State("otv-table-filter-rows", "data"),
    prevent_initial_call=True,
)

# Clear filters button → reset grid filter model
clientside_callback(
    """function(n) {
        if (!n) return window.dash_clientside.no_update;
        return {};
    }""",
    Output("otv-detail-grid", "filterModel"),
    Input("otv-table-clear-filters", "n_clicks"),
    prevent_initial_call=True,
)

# Badge click → scroll to grid
clientside_callback(
    """function(n) {
        if (!n) return window.dash_clientside.no_update;
        var el = document.getElementById('otv-detail-grid');
        if (el) el.scrollIntoView({behavior: 'smooth', block: 'start'});
        return window.dash_clientside.no_update;
    }""",
    Output("otv-grid-filter-badge", "n_clicks"),
    Input("otv-grid-filter-badge", "n_clicks"),
    prevent_initial_call=True,
)


# ---------------------------------------------------------------------------
# Chart Builders
# ---------------------------------------------------------------------------

def _build_department_chart(df, mode="count"):
    """Stacked bar chart of audit results by department (count or %)."""
    if "Department" not in df.columns or "AuditResult" not in df.columns:
        return empty_figure("No department data")

    pivot = df.groupby(["Department", "AuditResult"]).size().unstack(fill_value=0)

    if mode == "pct":
        row_totals = pivot.sum(axis=1)
        pivot = pivot.div(row_totals, axis=0) * 100

    fig = go.Figure()

    result_colors = {
        "OK": SEMANTIC_COLORS["success"],
        "Extra Visit(s)": SEMANTIC_COLORS["warning"],
        "Too Few": SEMANTIC_COLORS["error"],
    }

    for result in ["OK", "Extra Visit(s)", "Too Few"]:
        if result in pivot.columns:
            fig.add_trace(go.Bar(
                x=pivot.index,
                y=pivot[result],
                name=result,
                marker_color=result_colors.get(result, PRIMARY),
                hovertemplate="%{x}: %{y:.1f}%<extra>" + result + "</extra>" if mode == "pct"
                    else "%{x}: %{y}<extra>" + result + "</extra>",
            ))

    apply_default_layout(fig, barmode="stack")
    y_title = "%" if mode == "pct" else "Courses"
    extra = dict(yaxis_range=[0, 105]) if mode == "pct" else {}
    fig.update_layout(yaxis_title=y_title, margin=dict(l=48, r=16, t=12, b=20), **extra)
    return fig


def _build_trend_chart(df, date_col, chart_type="line", agg="M", smooth=0):
    """Compliance rate over time as line, area, or bar, aggregated by W/M/Y."""
    if date_col not in df.columns or "AuditResult" not in df.columns:
        return empty_figure("No trend data")

    df = df.copy()
    df["_period"] = df[date_col].dt.to_period(agg).dt.to_timestamp()

    grouped = df.groupby("_period").apply(
        lambda x: (x["AuditResult"] != "Too Few").sum() / len(x) * 100 if len(x) > 0 else 0,
        include_groups=False,
    ).reset_index(name="compliance")

    y = grouped["compliance"].tolist()
    if smooth and smooth > 0 and len(y) > 3:
        window = min(int(smooth), len(y) - 1)
        if window >= 2:
            s = pd.Series(y)
            y = s.rolling(window, min_periods=1, center=True).mean().tolist()

    x_vals = grouped["_period"].tolist()

    fig = go.Figure()
    if chart_type == "bar":
        fig.add_trace(go.Bar(
            x=x_vals,
            y=y,
            marker_color=PRIMARY,
            hovertemplate="%{x|%b %Y}: %{y:.1f}%<extra></extra>",
        ))
    elif chart_type == "area":
        fig.add_trace(go.Scatter(
            x=x_vals,
            y=y,
            mode="lines",
            fill="tozeroy",
            line=dict(color=PRIMARY, width=2),
            fillcolor="rgba(124, 42, 131, 0.15)",
            hovertemplate="%{x|%b %Y}: %{y:.1f}%<extra></extra>",
        ))
    else:
        fig.add_trace(go.Scatter(
            x=x_vals,
            y=y,
            mode="lines+markers",
            line=dict(color=PRIMARY, width=2),
            marker=dict(size=5),
            hovertemplate="%{x|%b %Y}: %{y:.1f}%<extra></extra>",
        ))

    apply_default_layout(fig)
    fig.update_layout(
        yaxis_title="Compliance %",
        yaxis_range=[0, 105],
        margin=dict(l=48, r=16, t=12, b=20),
    )
    return fig


def _build_distribution_chart(df):
    """Pie chart of audit result distribution."""
    if "AuditResult" not in df.columns:
        return empty_figure("No audit data")

    counts = df["AuditResult"].value_counts()

    result_colors = {
        "OK": SEMANTIC_COLORS["success"],
        "Extra Visit(s)": SEMANTIC_COLORS["warning"],
        "Too Few": SEMANTIC_COLORS["error"],
    }
    colors = [result_colors.get(r, PRIMARY) for r in counts.index]

    fig = go.Figure(go.Pie(
        labels=counts.index,
        values=counts.values,
        marker_colors=colors,
        hole=0.4,
        textinfo="label+percent",
        textposition="outside",
    ))

    apply_default_layout(fig)
    fig.update_layout(
        showlegend=False,
        margin=dict(l=16, r=16, t=12, b=12),
    )
    return fig


def _build_failed_breakdown(df, slice_by="department", mode="count"):
    """Horizontal bar chart of failed cases (Extra Visit(s) / Too Few) by dimension."""
    if "AuditResult" not in df.columns:
        return empty_figure("No audit data")

    failed = df[df["AuditResult"].isin(["Extra Visit(s)", "Too Few"])].copy()
    if failed.empty:
        return empty_figure("No failed cases")

    result_colors = {
        "Extra Visit(s)": SEMANTIC_COLORS["warning"],
        "Too Few": SEMANTIC_COLORS["error"],
    }

    # Determine sort order: numeric slices use custom category ordering
    _custom_order = None

    def _assign_dim(frame):
        """Assign _dim column to a frame based on slice_by. Returns filtered frame."""
        nonlocal _custom_order
        if slice_by == "physician":
            if "TreatingPhysician" not in frame.columns:
                try:
                    from data.loader import load_courses
                    courses = load_courses()
                    if {"PatientId", "CourseId", "TreatingPhysician"}.issubset(courses.columns):
                        phy_map = courses[["PatientId", "CourseId", "TreatingPhysician"]].drop_duplicates(
                            subset=["PatientId", "CourseId"], keep="last"
                        )
                        phy_map["PatientId"] = phy_map["PatientId"].astype(str)
                        phy_map["CourseId"] = phy_map["CourseId"].astype(str)
                        frame["PatientId"] = frame["PatientId"].astype(str)
                        frame["CourseId"] = frame["CourseId"].astype(str)
                        frame = frame.merge(phy_map, on=["PatientId", "CourseId"], how="left")
                except Exception:
                    pass
            col = "TreatingPhysician"
            if col not in frame.columns:
                return frame.iloc[:0]
            frame = frame[frame[col].notna()]
            frame["_dim"] = frame[col].str.split(",").str[0]
        elif slice_by == "diagnosis":
            if "DiagnosisCodes" not in frame.columns:
                return frame.iloc[:0]
            try:
                from data.loader import load_diagnosis
                diag_df = load_diagnosis()
                c2b = build_code_to_category(diag_df)
            except Exception:
                c2b = {}
            if not c2b:
                return frame.iloc[:0]
            frame["_dim"] = frame["DiagnosisCodes"].apply(lambda v: primary_category(v, c2b))
            frame = frame[frame["_dim"] != "Unknown"]
        elif slice_by == "fractions":
            frac_col = "PrescribedFractions"
            if frac_col not in frame.columns:
                return frame.iloc[:0]
            fx = pd.to_numeric(frame[frac_col], errors="coerce")
            frame = frame[fx.notna()].copy()
            fx = fx[fx.notna()].astype(int)

            def _fx_bucket(v):
                if v <= 1:
                    return "1"
                if v <= 5:
                    return "2-5"
                if v <= 10:
                    return "6-10"
                if v <= 20:
                    return "11-20"
                if v <= 30:
                    return "21-30"
                if v <= 40:
                    return "31-40"
                return "41+"
            frame["_dim"] = fx.map(_fx_bucket)
            _custom_order = ["1", "2-5", "6-10", "11-20", "21-30", "31-40", "41+"]
        elif slice_by == "fx_mod":
            frac_col = "PrescribedFractions"
            if frac_col not in frame.columns:
                return frame.iloc[:0]
            fx = pd.to_numeric(frame[frac_col], errors="coerce")
            frame = frame[fx.notna()].copy()
            fx = fx[fx.notna()].astype(int)
            frame["_dim"] = (fx % 5).map(lambda v: f"{v} left over")
            _custom_order = [f"{i} left over" for i in range(5)]
        else:
            if "Department" not in frame.columns:
                return frame.iloc[:0]
            frame["_dim"] = frame["Department"]
        return frame

    failed = _assign_dim(failed)
    if failed.empty:
        return empty_figure("No failed cases")

    pivot = failed.groupby(["_dim", "AuditResult"]).size().unstack(fill_value=0)

    # In pct mode, divide by total courses per dimension (including OK)
    dim_totals = None
    if mode == "pct":
        df_all = _assign_dim(df.copy())
        if not df_all.empty and "_dim" in df_all.columns:
            dim_totals = df_all.groupby("_dim").size()

    if _custom_order:
        present = [c for c in _custom_order if c in pivot.index]
        pivot = pivot.reindex(present[::-1], fill_value=0)
    else:
        pivot["_total"] = pivot.sum(axis=1)
        pivot = pivot.sort_values("_total", ascending=True)
        pivot = pivot.drop(columns=["_total"])

    if mode == "pct" and dim_totals is not None:
        for col in pivot.columns:
            pivot[col] = pivot[col] / dim_totals.reindex(pivot.index, fill_value=1) * 100

    fig = go.Figure()
    for result in ["Too Few", "Extra Visit(s)"]:
        if result not in pivot.columns:
            continue
        hover = (
            "%{y}: %{x:.1f}%<extra>" + result + "</extra>" if mode == "pct"
            else "%{y}: %{x}<extra>" + result + "</extra>"
        )
        fig.add_trace(go.Bar(
            y=pivot.index,
            x=pivot[result],
            name=result,
            marker_color=result_colors.get(result, PRIMARY),
            orientation="h",
            hovertemplate=hover,
        ))

    # Dynamic left margin: short labels need less space
    left_margin = 72 if slice_by in ("physician", "fractions", "fx_mod") else 120
    x_title = "% of Courses" if mode == "pct" else "Courses"
    extra = {}
    apply_default_layout(fig, barmode="stack")
    fig.update_layout(
        xaxis_title=x_title,
        margin=dict(l=left_margin, r=16, t=12, b=20),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5),
        **extra,
    )
    return fig


def _build_table(df, result_filter="all", course_status="all"):
    """Return (rowData, columnDefs) for the OTV audit detail grid."""
    if result_filter and result_filter != "all" and "AuditResult" in df.columns:
        df = df[df["AuditResult"] == result_filter]
    if course_status and course_status != "all" and "PatientId" in df.columns and "CourseId" in df.columns:
        completed_keys = _completed_course_keys()
        otv_keys = df["PatientId"].astype(str) + "|" + df["CourseId"].astype(str)
        if course_status == "completed":
            df = df[otv_keys.isin(completed_keys)]
        elif course_status == "active":
            df = df[~otv_keys.isin(completed_keys)]
    if df.empty:
        return [], []

    display_cols = [
        {"field": "LastTreatmentDate", "headerName": "Last Tx"},
        {"field": "FirstTreatmentDate", "headerName": "First Tx"},
        {"field": "PatientName", "headerName": "Patient"},
        {"field": "PatientId", "headerName": "MRN"},
        {"field": "CourseId", "headerName": "Course"},
        {"field": "Department", "headerName": "Dept"},
        {"field": "TreatingPhysician", "headerName": "Treating MD"},
        {"field": "ConsultPhysician", "headerName": "Consult MD"},
        {"field": "SessionCount_Delivery", "headerName": "Fx Done"},
        {"field": "PrescribedFractions", "headerName": "Rx Fx"},
        {"field": "AllowedOTVs", "headerName": "Allowed"},
        {"field": "WeeklyExamActivities", "headerName": "Exams"},
        {"field": "ManagementCPTs_ExcludingNC", "headerName": "CPTs"},
        {"field": "AuditResult", "headerName": "Result", "cellStyle": {
            "styleConditions": [
                {"condition": "params.value === 'OK'", "style": {"color": SEMANTIC_COLORS["success"], "fontWeight": "600"}},
                {"condition": "params.value === 'Extra Visit(s)'", "style": {"color": SEMANTIC_COLORS["warning"], "fontWeight": "600"}},
                {"condition": "params.value === 'Too Few'", "style": {"color": SEMANTIC_COLORS["error"], "fontWeight": "600"}},
            ],
        }},
    ]

    # Filter to only existing columns
    existing_cols = [c for c in display_cols if c["field"] in df.columns]

    table_df = df.head(500).copy()
    table_df["_row_idx"] = range(len(table_df))
    for c in ["FirstTreatmentDate", "LastTreatmentDate"]:
        if c in table_df.columns and pd.api.types.is_datetime64_any_dtype(table_df[c]):
            table_df[c] = table_df[c].dt.strftime("%m/%d/%Y")
    table_df = sanitize_for_grid(table_df)

    return table_df.to_dict("records"), existing_cols
