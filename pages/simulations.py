"""Simulations page — volume trends, timing intervals, schedule ribbons, detail grid."""

import dash
import dash_mantine_components as dmc
from dash import callback, Input, Output, State, dcc, html, clientside_callback, ClientsideFunction
import dash_ag_grid as dag
from dash_iconify import DashIconify
import plotly.graph_objects as go
import pandas as pd
import numpy as np
from datetime import timedelta

from config.settings import (
    DEPARTMENTS, DEPARTMENT_COLORS, CHART_COLORWAY,
    CHART_PAPER_HEIGHT, CHART_PAPER_HEIGHT_SM, PRIMARY, FONT_FAMILY, PRIOR_PERIOD_COLORS,
)
from components.filter_bar import department_chips
from components.outlier_panel import outlier_panel, register_outlier_callbacks
from components.kpi_card import kpi_card, kpi_placeholder
from components.chart_card import chart_card, register_chart_callbacks
from components.diagnosis_filter import diagnosis_accordion, register_diagnosis_callbacks
from components.detail_table import detail_table
from components.chart_settings import chart_settings_popover
from utils.charts import apply_default_layout, empty_figure
from utils.tables import sanitize_for_grid
from utils.date_slider import (
    month_idx, idx_to_date, MAX_IDX, SLIDER_MARKS,
    preset_to_slider_val,
)
from utils.holidays import get_holidays
from utils.diagnosis_categories import (
    assign_diagnosis_column,
    build_code_to_category,
    get_categories_for_codes,
)

dash.register_page(__name__, path="/simulations", name="Simulations", order=4)

PAGE_ID = "sim"

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_DEFAULT_DATE_PRESET = "ytd" if pd.Timestamp.now().month > 1 else "3mo"
_CAP_LEAD = 21          # outlier cap: consult → sim (days)
_CAP_TIME_TO_TX = 21    # outlier cap: sim → treatment (days)
_CAP_LEAD_TIME = 21     # outlier cap: lead time / booked → sim (days)

# Sim types to exclude from filter and charts
_SIM_TYPE_EXCLUDE = frozenset({"HOLD SIM TIME", "MD Needed in Sim"})

# Sim machine display names and colors (keyed by SimulationResource)
_SIM_MACHINE_DISPLAY = {
    "CT_Sim": "CT Sim (Lacey)",
    "CT_Cen": "CT Sim (Centralia)",
    "TrueBeamNorth": "TrueBeam",
    "21EX": "21EX",
    "21iX_CEN": "21iX CEN",
    "21iX_AB": "21iX AB",
}
_SIM_MACHINE_COLORS = {
    "CT_Sim": DEPARTMENT_COLORS.get("Lacey", "#2196F3"),
    "CT_Cen": DEPARTMENT_COLORS.get("Centralia", "#F44336"),
    "TrueBeamNorth": "#1976D2",
    "21EX": "#64B5F6",
    "21iX_CEN": "#E57373",
    "21iX_AB": DEPARTMENT_COLORS.get("Aberdeen", "#4CAF50"),
}

# Display-name mapping: raw ARIA ActivityName → clean label
_SIM_TYPE_DISPLAY = {
    "Bite Block Fabrication-Stereotactic": "Bite Block Fabrication – SRS",
    "Decub Breast CT- Aberdeen":          "Decub Breast – Aberdeen",
    "Decub breast electron CT sim":       "Decub Breast",
    "Initial Aberdeen Simulation":        "Initial Simulation – Aberdeen",
    "Initial Centralia-in Lacey":         "Initial Simulation – Centralia",
    "Initial Simulation":                 "Initial Simulation",
    "RE-Simulation-Aberdeen":             "Re-Simulation – Aberdeen",
    "Re-Simulation":                      "Re-Simulation",
    "Re-seat  Bite Block Test":           "Bite Block Re-seat Test",
    "Stereotactic Simulation":            "Stereotactic Simulation (SRS)",
    "Treatment Device Fabrication":       "Treatment Device Fabrication",
    "electron- CSU on machine":           "Electron CSU On-Machine",
    "initial simulation on PET/CT table": "Initial Simulation – PET/CT",
}

def _sim_display_name(raw):
    """Return the clean display name for a sim type."""
    return _SIM_TYPE_DISPLAY.get(raw, raw)

# Pre-load sim types at import time so chips are stable (no callback race)
def _load_sim_types():
    try:
        from data.loader import load_simulations
        df = load_simulations()
        if "ActivityName" in df.columns:
            raw = sorted(df["ActivityName"].dropna().unique().tolist())
            return [t for t in raw if t not in _SIM_TYPE_EXCLUDE]
    except Exception:
        pass
    return []

_SIM_TYPES = _load_sim_types()

def _load_sim_machines():
    try:
        from data.loader import load_simulations
        df = load_simulations()
        if "SimulationResource" in df.columns:
            return sorted(df["SimulationResource"].dropna().unique().tolist())
    except Exception:
        pass
    return []

_SIM_MACHINES = _load_sim_machines()

# CPT code labels and descriptions for sim billing chart
_SIM_CPT_LABELS = {
    "77290": "77290", "77280": "77280", "77285": "77285",
    "77332": "77332", "77333": "77333", "77334": "77334",
    "77014": "77014", "76370": "76370", "77305": "77305",
}
_SIM_CPT_DESCRIPTIONS = {
    "77290": "Simulation, Complex",
    "77280": "Simulation, Simple",
    "77285": "Simulation, Intermediate",
    "77332": "Treatment Planning, Simple",
    "77333": "Treatment Planning, Intermediate",
    "77334": "Treatment Devices",
    "77014": "CT Guidance for RT",
    "76370": "CT Guidance for Therapy",
    "77305": "Teletherapy Isodose Plan",
}
# All known sim CPT base codes
_SIM_CPT_ALL = set(_SIM_CPT_LABELS.keys())

# Ribbon machine selector options (CT simulators only — not treatment linacs)
_RIBBON_MACHINE_OPTS = [
    {"value": "all", "label": "All"},
    {"value": "CT_Sim", "label": "Lacey"},
    {"value": "CT_Cen", "label": "Centralia"},
]


def _resim_scope_toggle(current="resim"):
    """Tiny Re-Sim / +Decub toggle for the Re-Sim Rate KPI card header."""
    return dmc.SegmentedControl(
        id="sim-resim-scope",
        data=[
            {"value": "resim", "label": "Re-Sim"},
            {"value": "resim_decub", "label": "+Decub"},
        ],
        value=current, size="xs",
    )


# ---------------------------------------------------------------------------
# Filter Bar
# ---------------------------------------------------------------------------

def _build_sim_filter_bar():
    """Build the CV-style two-row filter bar for simulations."""
    return dmc.Paper(
        children=[
            # Row 1: data filters
            dmc.Group(
                children=[
                    department_chips("sim"),
                    # Physician dropdown
                    html.Div(
                        children=[
                            html.Div(
                                children=[
                                    dmc.Button(
                                        "Physician",
                                        id="sim-physician-trigger",
                                        variant="default",
                                        size="sm",
                                        rightSection=DashIconify(icon="mdi:chevron-down", width=14),
                                    ),
                                    dmc.ActionIcon(
                                        DashIconify(icon="mdi:close-circle", width=18),
                                        id="sim-physician-clear",
                                        variant="subtle",
                                        color="gray",
                                        size="sm",
                                        className="wf-filter-clear-btn",
                                    ),
                                ],
                                style={"position": "relative", "display": "inline-block"},
                            ),
                            dmc.Paper(
                                id="sim-physician-panel",
                                children=[
                                    dmc.ChipGroup(
                                        children=[],
                                        id="sim-filter-physician",
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
                    # Sim Type dropdown
                    html.Div(
                        children=[
                            html.Div(
                                children=[
                                    dmc.Button(
                                        "Sim Type",
                                        id="sim-simtype-trigger",
                                        variant="default",
                                        size="sm",
                                        rightSection=DashIconify(icon="mdi:chevron-down", width=14),
                                    ),
                                    dmc.ActionIcon(
                                        DashIconify(icon="mdi:close-circle", width=18),
                                        id="sim-simtype-clear",
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
                                        dmc.Chip(_sim_display_name(t), value=t, size="xs", variant="filled")
                                        for t in _SIM_TYPES
                                    ],
                                    id="sim-filter-simtype",
                                    multiple=True,
                                    value=[],
                                ),
                                id="sim-simtype-panel",
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
                    # Machine dropdown
                    html.Div(
                        children=[
                            html.Div(
                                children=[
                                    dmc.Button(
                                        "Machine",
                                        id="sim-machine-trigger",
                                        variant="default",
                                        size="sm",
                                        rightSection=DashIconify(icon="mdi:chevron-down", width=14),
                                    ),
                                    dmc.ActionIcon(
                                        DashIconify(icon="mdi:close-circle", width=18),
                                        id="sim-machine-clear",
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
                                        dmc.Chip(
                                            _SIM_MACHINE_DISPLAY.get(m, m),
                                            value=m,
                                            size="xs",
                                            variant="filled",
                                        )
                                        for m in _SIM_MACHINES
                                    ],
                                    id="sim-filter-machine",
                                    multiple=True,
                                    value=[],
                                ),
                                id="sim-machine-panel",
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
                    diagnosis_accordion("sim"),
                    # Scope: All / Initial
                    dmc.SegmentedControl(
                        id="sim-volume-scope",
                        data=[
                            {"value": "all", "label": "All"},
                            {"value": "initial", "label": "Initial"},
                        ],
                        value="all",
                        size="xs",
                    ),
                    # Inpatient
                    dmc.Switch(
                        id="sim-inpatient-switch",
                        label="Inpatient",
                        size="xs",
                        checked=False,
                    ),
                    # Weekend / Holiday
                    dmc.Switch(
                        id="sim-weekend-switch",
                        label="Weekend",
                        size="xs",
                        checked=False,
                    ),
                    outlier_panel(PAGE_ID, transitions=[
                        ("Consult \u2192 Sim", _CAP_LEAD),
                        ("Sim \u2192 Treatment", _CAP_TIME_TO_TX),
                        ("Lead Time", _CAP_LEAD_TIME),
                    ]),
                    # Smoothing
                    dmc.Group(
                        children=[
                            dmc.Text("Smoothing", size="xs", c="#6B7280", fw=500),
                            dmc.Slider(
                                id="sim-smooth-slider",
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
                        id="sim-filter-date-preset",
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
                            id="sim-filter-daterange",
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
                            html.Div(id="sim-date-range-label", style={"display": "none"}),
                            dmc.RangeSlider(
                                id="sim-date-slider",
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
                dmc.Title("Simulations", order=2, className="page-title", style={"margin": 0, "textAlign": "center"}),
                html.Div(
                    style={"position": "relative"},
                    children=[
                        _build_sim_filter_bar(),
                        html.Div(
                            id="sim-grid-filter-badge",
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

        # KPI row — 6 cards with sparklines
        dmc.Grid(id="sim-kpi-row", gutter="md", children=[
            dmc.GridCol(kpi_placeholder(), id="sim-kpi-total", span={"base": 6, "md": 2}),
            dmc.GridCol(kpi_placeholder(), id="sim-kpi-initial", span={"base": 6, "md": 2}),
            dmc.GridCol(kpi_placeholder(), id="sim-kpi-lead", span={"base": 6, "md": 2}),
            dmc.GridCol(kpi_placeholder(), id="sim-kpi-consult-sim", span={"base": 6, "md": 2}),
            dmc.GridCol(kpi_placeholder(), id="sim-kpi-time-to-tx", span={"base": 6, "md": 2}),
            dmc.GridCol(kpi_placeholder(), id="sim-kpi-resim", span={"base": 6, "md": 2}),
        ]),

        # Row 1: Volume Trend + Cumulative Volume (CV-style)
        dmc.Grid(gutter="md", children=[
            dmc.GridCol(
                chart_card(
                    "sim-chart-volume",
                    "Simulation Volume Trend",
                    settings_id="sim-volume",
                    chart_types=[
                        {"value": "bar", "label": "Bar"},
                        {"value": "line", "label": "Line"},
                        {"value": "area", "label": "Area"},
                    ],
                    show_smooth=True,
                    smooth_max=12,
                    smooth_default=0,
                    paper_padding="md",
                    extra_controls_left=[
                        dmc.SegmentedControl(
                            id="sim-volume-slice",
                            data=[
                                {"value": "", "label": "Total"},
                                {"value": "scope", "label": "Scope"},
                                {"value": "type", "label": "Type"},
                                {"value": "physician", "label": "MD"},
                                {"value": "dept", "label": "Dept"},
                                {"value": "machine", "label": "Machine"},
                                {"value": "bodysite", "label": "Dx"},
                            ],
                            value="scope",
                            size="xs",
                        ),
                    ],
                    extra_controls=[
                        dmc.SegmentedControl(
                            id="sim-volume-agg",
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
                    "sim-chart-cumulative",
                    "Cumulative Simulation Volume",
                    settings_id="sim-cumulative",
                    chart_types=[
                        {"value": "line", "label": "Line"},
                        {"value": "area", "label": "Area"},
                        {"value": "bar", "label": "Bar"},
                    ],
                    show_smooth=True,
                    show_prior_periods=True,
                    smooth_min=0,
                    smooth_max=1,
                    smooth_step=0.05,
                    smooth_default=0.1,
                    prior_periods_default=3,
                    paper_padding="md",
                    extra_controls=[
                        dmc.SegmentedControl(
                            id="sim-cumulative-mode",
                            data=[
                                {"value": "prior", "label": "Prior Periods"},
                                {"value": "slice", "label": "Slice By"},
                            ],
                            value="prior",
                            size="xs",
                        ),
                        dmc.SegmentedControl(
                            id="sim-cumulative-period-type",
                            data=[
                                {"value": "calendar", "label": "Calendar"},
                                {"value": "rolling", "label": "Rolling"},
                            ],
                            value="calendar",
                            size="xs",
                        ),
                        dmc.SegmentedControl(
                            id="sim-cumulative-slice",
                            data=[
                                {"value": "total", "label": "Total"},
                                {"value": "scope", "label": "Scope"},
                                {"value": "type", "label": "Type"},
                                {"value": "physician", "label": "MD"},
                                {"value": "dept", "label": "Dept"},
                                {"value": "machine", "label": "Machine"},
                                {"value": "bodysite", "label": "Dx"},
                            ],
                            value="total",
                            size="xs",
                            style={"display": "none"},
                        ),
                    ],
                ),
                span={"base": 12, "md": 6},
            ),
        ]),

        # Row 2: Timing Intervals + Schedule Ribbon (half-width each)
        dmc.Grid(gutter="md", children=[
            dmc.GridCol(
                chart_card(
                    "sim-chart-timing",
                    "Timing Intervals",
                    settings_id="sim-timing",
                    chart_types=[
                        {"value": "line", "label": "Line"},
                        {"value": "area", "label": "Area"},
                        {"value": "bar", "label": "Bar"},
                    ],
                    show_smooth=True,
                    smooth_max=12,
                    smooth_default=2,
                    paper_padding="md",
                    extra_controls_left=[
                        dmc.SegmentedControl(
                            id="sim-timing-metric",
                            data=[
                                {"value": "consult_sim", "label": "Consult \u2192 Sim"},
                                {"value": "lead_time", "label": "Lead Time"},
                            ],
                            value="lead_time",
                            size="xs",
                        ),
                        dmc.SegmentedControl(
                            id="sim-timing-slice",
                            data=[
                                {"value": "", "label": "Total"},
                                {"value": "scope", "label": "Scope"},
                                {"value": "type", "label": "Type"},
                                {"value": "physician", "label": "MD"},
                                {"value": "dept", "label": "Dept"},
                                {"value": "machine", "label": "Machine"},
                                {"value": "bodysite", "label": "Dx"},
                            ],
                            value="",
                            size="xs",
                        ),
                    ],
                    extra_controls=[
                        dmc.SegmentedControl(
                            id="sim-timing-agg",
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
                dmc.Paper(
                    children=[
                        dmc.Group(
                            justify="space-between", mb="sm",
                            children=[
                                dmc.Group(gap="xs", align="center", children=[
                                    dmc.Text("Schedule Ribbon", size="sm", fw=500, c="#6B7280"),
                                    dmc.SegmentedControl(
                                        id="sim-ribbon-machine",
                                        data=_RIBBON_MACHINE_OPTS,
                                        value="all",
                                        size="xs",
                                    ),
                                ]),
                                chart_settings_popover(
                                    "sim-ribbon",
                                    chart_types=[
                                        {"value": "bar", "label": "Bar"},
                                        {"value": "ribbon", "label": "Ribbon"},
                                        {"value": "line", "label": "Line"},
                                    ],
                                    show_smooth=True,
                                    smooth_max=14,
                                    smooth_default=3,
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
                                        dmc.LoadingOverlay(id="sim-ribbon-loading", visible=False, loaderProps={"type": "dots", "color": "#7C2A83"}),
                                        dcc.Graph(id="sim-chart-ribbon", config={"displayModeBar": False}, responsive=True, style={"height": "100%", "width": "100%"}),
                                    ],
                                ),
                            ],
                        ),
                    ],
                    p="md", pb=8, radius="md", shadow="xs", withBorder=True,
                    h=CHART_PAPER_HEIGHT,
                    style={"display": "flex", "flexDirection": "column"},
                ),
                span={"base": 12, "md": 6},
            ),
        ]),

        # Row 3: Cancellation Rate + Diagnosis Mix + Billing (1/3 each)
        dmc.Grid(gutter="md", children=[
            dmc.GridCol(
                chart_card(
                    "sim-chart-cancel-rate",
                    "Cancellation Rate",
                    settings_id="sim-cancel",
                    paper_height=CHART_PAPER_HEIGHT_SM,
                    chart_types=[
                        {"value": "line", "label": "Line"},
                        {"value": "area", "label": "Area"},
                        {"value": "bar", "label": "Bar"},
                    ],
                    show_smooth=True,
                    smooth_max=12,
                    smooth_default=1,
                    extra_controls_left=[
                        dmc.SegmentedControl(
                            id="sim-cancel-slice",
                            data=[
                                {"value": "", "label": "Total"},
                                {"value": "scope", "label": "Scope"},
                                {"value": "dept", "label": "Dept"},
                            ],
                            value="",
                            size="xs",
                        ),
                    ],
                    extra_controls=[
                        dmc.SegmentedControl(
                            id="sim-cancel-agg",
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
                span={"base": 12, "md": 4},
            ),
            dmc.GridCol(
                dmc.Paper(
                    children=[
                        dmc.Group(
                            justify="space-between", mb=8,
                            children=[
                                dmc.Group(gap="xs", align="center", wrap="nowrap", style={"flex": "1"}, children=[
                                    dmc.Text("Diagnosis", size="sm", fw=500, c="#6B7280"),
                                    dmc.SegmentedControl(
                                        id="sim-diagnosis-compare",
                                        data=[
                                            {"value": "off", "label": "Current"},
                                            {"value": "prior", "label": "vs Prior"},
                                        ],
                                        value="off",
                                        size="xs",
                                    ),
                                    dmc.SegmentedControl(
                                        id="sim-diagnosis-slice",
                                        data=[
                                            {"value": "", "label": "Total"},
                                            {"value": "scope", "label": "Scope"},
                                            {"value": "physician", "label": "MD"},
                                            {"value": "dept", "label": "Dept"},
                                            {"value": "machine", "label": "Machine"},
                                        ],
                                        value="",
                                        size="xs",
                                    ),
                                    dmc.SegmentedControl(
                                        id="sim-diagnosis-mode",
                                        style={"marginLeft": "auto"},
                                        data=[
                                            {"value": "count", "label": "#"},
                                            {"value": "pct", "label": "%"},
                                        ],
                                        value="count",
                                        size="xs",
                                    ),
                                ]),
                                chart_settings_popover(
                                    "sim-diagnosis",
                                    chart_types=None,
                                    show_smooth=False,
                                ),
                            ],
                        ),
                        dmc.Box(
                            pos="relative",
                            ml="-12px", mr="-12px",
                            style={"flex": "1", "minHeight": 0},
                            children=[
                                dmc.Box(
                                    style={"position": "absolute", "top": 0, "left": 0, "right": 0, "bottom": 0},
                                    children=[
                                        dmc.LoadingOverlay(id="sim-diagnosis-loading", visible=False, loaderProps={"type": "dots", "color": "#7C2A83"}),
                                        dcc.Graph(id="sim-chart-diagnosis", config={"displayModeBar": False}, style={"height": "100%"}),
                                    ],
                                ),
                            ],
                        ),
                    ],
                    p="sm", pb=8, radius="md", shadow="xs", withBorder=True,
                    h="380px", style={"display": "flex", "flexDirection": "column"},
                ),
                span={"base": 12, "md": 4},
            ),
            dmc.GridCol(
                dmc.Paper(
                    children=[
                        dmc.Group(
                            justify="space-between", mb=8, gap="xs", wrap="nowrap",
                            children=[
                                dmc.Group(gap="xs", wrap="nowrap", align="center", style={"flex": "1"}, children=[
                                    dmc.Text("Billing", size="sm", fw=500, c="#6B7280"),
                                    dmc.SegmentedControl(
                                        id="sim-billing-slice",
                                        data=[
                                            {"value": "", "label": "Total"},
                                            {"value": "scope", "label": "Scope"},
                                            {"value": "physician", "label": "MD"},
                                            {"value": "dept", "label": "Dept"},
                                        ],
                                        value="",
                                        size="xs",
                                    ),
                                    dmc.SegmentedControl(
                                        id="sim-billing-mode",
                                        style={"marginLeft": "auto"},
                                        data=[
                                            {"value": "count", "label": "#"},
                                            {"value": "pct", "label": "%"},
                                        ],
                                        value="count",
                                        size="xs",
                                    ),
                                ]),
                                chart_settings_popover(
                                    "sim-billing",
                                    chart_types=None,
                                    show_smooth=False,
                                ),
                            ],
                        ),
                        dmc.Box(
                            pos="relative",
                            ml="-12px", mr="-12px",
                            style={"flex": "1", "minHeight": 0},
                            children=[
                                dmc.Box(
                                    style={"position": "absolute", "top": 0, "left": 0, "right": 0, "bottom": 0},
                                    children=[
                                        dmc.LoadingOverlay(id="sim-billing-loading", visible=False, loaderProps={"type": "dots", "color": "#7C2A83"}),
                                        dcc.Graph(id="sim-chart-billing", config={"displayModeBar": False}, style={"height": "100%"}),
                                    ],
                                ),
                            ],
                        ),
                    ],
                    p="sm", pb=8, radius="md", shadow="xs", withBorder=True,
                    h="380px", style={"display": "flex", "flexDirection": "column"},
                ),
                span={"base": 12, "md": 4},
            ),
        ]),

        # Detail table — full width, collapsible
        detail_table(
            "sim-detail-grid",
            title="Simulation Detail",
            export_id="sim-table-export",
            extra_controls=[
                dmc.Button(
                    "Clear Filters",
                    id="sim-table-clear-filters",
                    size="compact-xs",
                    variant="light",
                    color="red",
                    leftSection=DashIconify(icon="mdi:filter-remove", width=14),
                    style={"display": "none"},
                ),
            ],
        ),

        dcc.Interval(id="sim-interval", interval=300_000, n_intervals=0),

        # Stores for clientside rendering
        dcc.Store(id="sim-store-volume"),
        dcc.Store(id="sim-store-timing"),
        dcc.Store(id="sim-store-ribbon"),
        dcc.Store(id="sim-store-cumulative"),
        dcc.Store(id="sim-store-kpi-sparklines"),
        dcc.Store(id="sim-store-resim-scope", data="resim"),
        dcc.Store(id="sim-store-cancel"),
        dcc.Store(id="sim-table-filter-rows"),  # filtered row indices from grid
    ],
)

# Sync dynamically-created resim toggle → Store so the KPI callback can read it
clientside_callback(
    """function(v) { return v; }""",
    Output("sim-store-resim-scope", "data"),
    Input("sim-resim-scope", "value"),
    prevent_initial_call=True,
)


# ---------------------------------------------------------------------------
# Helper: Date Filter
# ---------------------------------------------------------------------------

def _get_date_range(slider_val, daterange=None):
    """Calculate start/end based on slider or explicit daterange override.
    End date is capped to today so charts never extend into the future."""
    today = pd.Timestamp.now().normalize()
    if daterange and len(daterange) == 2 and daterange[0] and daterange[1]:
        return pd.Timestamp(daterange[0]), min(pd.Timestamp(daterange[1]), today)
    if slider_val and len(slider_val) == 2:
        start = idx_to_date(slider_val[0])
        end = min(idx_to_date(slider_val[1], end_of_month=True), today)
        return start, end
    return pd.Timestamp("2020-01-01"), today



# ---------------------------------------------------------------------------
# Filter Callbacks
# ---------------------------------------------------------------------------

def _register_sim_filter_callbacks():
    """Register all filter-sync callbacks for the simulations page."""

    # A) Preset → Slider + DatePicker
    @callback(
        Output("sim-date-slider", "value"),
        Output("sim-filter-daterange", "start_date", allow_duplicate=True),
        Output("sim-filter-daterange", "end_date", allow_duplicate=True),
        Input("sim-filter-date-preset", "value"),
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
        ClientsideFunction(namespace="simDateSlider", function_name="syncSlider"),
        Output("sim-filter-daterange", "start_date", allow_duplicate=True),
        Output("sim-filter-daterange", "end_date", allow_duplicate=True),
        Output("sim-date-range-label", "children"),
        Input("sim-date-slider", "value"),
        State("sim-filter-daterange", "start_date"),
        State("sim-filter-daterange", "end_date"),
        prevent_initial_call=True,
    )

    # C) DatePicker → Slider
    @callback(
        Output("sim-date-slider", "value", allow_duplicate=True),
        Input("sim-filter-daterange", "start_date"),
        Input("sim-filter-daterange", "end_date"),
        State("sim-date-slider", "value"),
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
        Output("sim-filter-date-preset", "value", allow_duplicate=True),
        Input("sim-date-slider", "value"),
        State("sim-filter-date-preset", "value"),
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
        Output("sim-physician-trigger", "children"),
        Input("sim-filter-physician", "value"),
    )
    import json as _json
    _display_map_json = _json.dumps(_SIM_TYPE_DISPLAY)
    clientside_callback(
        "function(vals) {"
        "  if (!vals || vals.length === 0) return 'Sim Type';"
        "  var dm = " + _display_map_json + ";"
        "  if (vals.length === 1) return dm[vals[0]] || vals[0];"
        "  return vals.length + ' selected';"
        "}",
        Output("sim-simtype-trigger", "children"),
        Input("sim-filter-simtype", "value"),
    )
    _machine_map_json = _json.dumps(_SIM_MACHINE_DISPLAY)
    clientside_callback(
        "function(vals) {"
        "  if (!vals || vals.length === 0) return 'Machine';"
        "  var dm = " + _machine_map_json + ";"
        "  if (vals.length === 1) return dm[vals[0]] || vals[0];"
        "  return vals.length + ' selected';"
        "}",
        Output("sim-machine-trigger", "children"),
        Input("sim-filter-machine", "value"),
    )

    # --- Clear-button visibility ---
    clientside_callback(
        """function(val) { return val ? {"display": "inline-flex"} : {"display": "none"}; }""",
        Output("sim-physician-clear", "style"),
        Input("sim-filter-physician", "value"),
    )
    clientside_callback(
        """function(vals) { return vals && vals.length > 0 ? {"display": "inline-flex"} : {"display": "none"}; }""",
        Output("sim-simtype-clear", "style"),
        Input("sim-filter-simtype", "value"),
    )
    clientside_callback(
        """function(vals) { return vals && vals.length > 0 ? {"display": "inline-flex"} : {"display": "none"}; }""",
        Output("sim-machine-clear", "style"),
        Input("sim-filter-machine", "value"),
    )

    # --- Clear-button actions ---
    clientside_callback(
        """function(n) { return null; }""",
        Output("sim-filter-physician", "value", allow_duplicate=True),
        Input("sim-physician-clear", "n_clicks"),
        prevent_initial_call=True,
    )
    clientside_callback(
        """function(n) { return []; }""",
        Output("sim-filter-simtype", "value", allow_duplicate=True),
        Input("sim-simtype-clear", "n_clicks"),
        prevent_initial_call=True,
    )
    clientside_callback(
        """function(n) { return []; }""",
        Output("sim-filter-machine", "value", allow_duplicate=True),
        Input("sim-machine-clear", "n_clicks"),
        prevent_initial_call=True,
    )



# Register filter callbacks
_register_sim_filter_callbacks()

# Register diagnosis accordion callbacks
register_diagnosis_callbacks("sim")

# Register outlier panel callbacks
register_outlier_callbacks(PAGE_ID, n_transitions=3, defaults=[_CAP_LEAD, _CAP_TIME_TO_TX, _CAP_LEAD_TIME])


# ---------------------------------------------------------------------------
# Physician filter — dynamic from data
# ---------------------------------------------------------------------------
@callback(
    Output("sim-filter-physician", "children"),
    Input("sim-interval", "n_intervals"),
)
def _populate_sim_physician_chips(_n):
    from data.loader import load_simulations
    try:
        df = load_simulations()
    except Exception:
        return []
    if df.empty or "SupervisingPhysician" not in df.columns:
        return []
    from components.filter_bar import physician_options, physician_short_name
    return [
        dmc.Chip(physician_short_name(opt["label"]), value=opt["value"], size="xs", variant="filled")
        for opt in physician_options(df["SupervisingPhysician"])
    ]


# ---------------------------------------------------------------------------
# Main callback
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Shared data loading/filtering helper
# ---------------------------------------------------------------------------

_SIM_PERIOD_LABELS = {
    "30d": "30 Days", "3mo": "3 Mo", "6mo": "6 Mo", "12mo": "12 Mo",
    "ytd": "YTD", "last_year": "Last Year", "this_month": "This Mo",
    "last_month": "Last Mo", "all": "All Time", "custom": "Custom",
}
_SIM_TREND_LABELS = {
    "30d": "vs prior 30d", "3mo": "vs prior 3 mo", "6mo": "vs prior 6 mo",
    "12mo": "vs prior 12 mo", "ytd": "vs prior year",
    "last_year": "vs prior year", "this_month": "vs prior month",
    "last_month": "vs 2 months ago", "all": "", "custom": "",
}


def _sim_prior_range(date_preset, last_date):
    """Return (prior_start, prior_end) matching the current date_preset."""
    if date_preset == "30d":
        return last_date - timedelta(days=59), last_date - timedelta(days=30)
    elif date_preset == "3mo":
        return last_date - timedelta(days=179), last_date - timedelta(days=90)
    elif date_preset == "6mo":
        return last_date - timedelta(days=364), last_date - timedelta(days=183)
    elif date_preset == "12mo":
        return last_date - timedelta(days=730), last_date - timedelta(days=366)
    elif date_preset == "ytd":
        try:
            pe = pd.Timestamp(last_date.year - 1, last_date.month, last_date.day)
        except ValueError:
            pe = pd.Timestamp(last_date.year - 1, last_date.month, 28)
        return pd.Timestamp(last_date.year - 1, 1, 1), pe
    elif date_preset == "last_year":
        return pd.Timestamp(last_date.year - 2, 1, 1), pd.Timestamp(last_date.year - 2, 12, 31)
    elif date_preset == "this_month":
        pm_end = pd.Timestamp(last_date.year, last_date.month, 1) - timedelta(days=1)
        pm_start = pd.Timestamp(pm_end.year, pm_end.month, 1)
        return pm_start, pm_end
    elif date_preset == "last_month":
        lm_start = pd.Timestamp(last_date.year, last_date.month, 1) - timedelta(days=1)
        two_ago_start = pd.Timestamp(lm_start.year, lm_start.month, 1) - timedelta(days=1)
        return pd.Timestamp(two_ago_start.year, two_ago_start.month, 1), pd.Timestamp(lm_start.year, lm_start.month, 1) - timedelta(days=1)
    return None, None


def _sim_trend(curr, prior, invert=False):
    if prior is None or prior == 0:
        return None, None, None
    pct = (curr - prior) / prior * 100
    direction = ("down" if pct > 0 else "up") if invert else ("up" if pct > 0 else "down")
    return f"{abs(pct):.0f}%", direction, prior


def _dedup_patient_day(src):
    """Deduplicate simulations to one per patient per day."""
    if "PatientId" not in src.columns or "ScheduledDateTime" not in src.columns:
        return src
    sort_col = "DurationMinutes" if "DurationMinutes" in src.columns else None
    if sort_col:
        return (src.sort_values(sort_col, ascending=False)
                  .drop_duplicates(subset=["PatientId", "_SimDate"], keep="first"))
    return src.drop_duplicates(subset=["PatientId", "_SimDate"], keep="first")


def _load_and_filter_sim(slider_val, departments, physician, sim_types,
                          machines, body_sites, diag_mode, volume_scope,
                          inpatient, weekend_only, date_preset):
    """Load simulations data, apply filters. Returns dict or None."""
    from data.loader import load_simulations, load_diagnosis

    try:
        df = load_simulations().copy()
    except Exception:
        return None
    if df.empty:
        return None

    # Dimension filters
    if "ActivityName" in df.columns:
        df = df[~df["ActivityName"].isin(_SIM_TYPE_EXCLUDE)]
    if departments and "Department" in df.columns:
        df = df[df["Department"].isin(departments) | df["Department"].isna()]
    if physician and "SupervisingPhysician" in df.columns:
        df = df[df["SupervisingPhysician"] == physician]
    if sim_types and "ActivityName" in df.columns:
        df = df[df["ActivityName"].isin(sim_types)]
    if machines and "SimulationResource" in df.columns:
        df = df[df["SimulationResource"].isin(machines)]

    # Diagnosis lookup
    try:
        diag_df = load_diagnosis()
    except Exception:
        diag_df = None
    c2b = build_code_to_category(diag_df)

    if body_sites:
        from utils.diagnosis_categories import filter_by_diagnosis
        df = filter_by_diagnosis(df, body_sites, c2b, mode=diag_mode or "primary")

    if volume_scope == "initial" and "ActivityName" in df.columns:
        df = df[df["ActivityName"].apply(_is_initial_sim)]
    if inpatient and "InPatientFlag" in df.columns:
        df = df[df["InPatientFlag"].str.upper() == "YES"]

    df_all_status = df.copy()

    # Status filter (completed or billed)
    if "Status" in df.columns:
        completed = df["Status"].str.contains("Completed", case=False, na=False)
        billed = df["ProcedureCodes"].notna() & (df["ProcedureCodes"].astype(str).str.strip() != "") if "ProcedureCodes" in df.columns else pd.Series(False, index=df.index)
        df = df[completed | billed]

    if weekend_only and "ScheduledDateTime" in df.columns:
        df = df[df["ScheduledDateTime"].dt.dayofweek >= 5]
    if df.empty:
        return None

    start, end = _get_date_range(slider_val)

    if "PatientId" in df.columns and "ScheduledDateTime" in df.columns:
        df["_SimDate"] = df["ScheduledDateTime"].dt.normalize()
    df_all = df

    if "ScheduledDateTime" in df.columns:
        df = df[(df["ScheduledDateTime"] >= start) & (df["ScheduledDateTime"] <= end)]
    if df.empty:
        return None

    dfu = _dedup_patient_day(df)
    dfu_all = _dedup_patient_day(df_all)

    ps, pe = _sim_prior_range(date_preset, end)

    return {
        "df": df, "df_all": df_all, "df_all_status": df_all_status,
        "dfu": dfu, "dfu_all": dfu_all, "c2b": c2b,
        "start": start, "end": end, "date_preset": date_preset,
        "departments": departments, "physician": physician,
        "sim_types": sim_types, "ps": ps, "pe": pe,
        "diag_mode": diag_mode or "primary",
    }


# Common filter inputs shared by all split callbacks
_SIM_FILTER_INPUTS = [
    Input("sim-interval", "n_intervals"),
    Input("sim-date-slider", "value"),
    Input("sim-filter-department", "value"),
    Input("sim-filter-physician", "value"),
    Input("sim-filter-simtype", "value"),
    Input("sim-filter-machine", "value"),
    Input("sim-diag-store", "data"),
    Input("sim-diag-mode", "data"),
    Input("sim-volume-scope", "value"),
    Input("sim-inpatient-switch", "checked"),
    Input("sim-weekend-switch", "checked"),
    Input("sim-filter-date-preset", "value"),
]


def _unpack_sim_filter_args(args):
    """Unpack the 12 common filter args into kwargs for _load_and_filter_sim."""
    (_n, slider_val, departments, physician, sim_types,
     machines, body_sites, diag_mode, volume_scope, inpatient,
     weekend_only, date_preset) = args[:12]
    return dict(
        slider_val=slider_val, departments=departments, physician=physician,
        sim_types=sim_types, machines=machines, body_sites=body_sites,
        diag_mode=diag_mode, volume_scope=volume_scope, inpatient=inpatient,
        weekend_only=weekend_only, date_preset=date_preset,
    )


def _apply_grid_row_filter(df, grid_rows):
    """Filter df to only rows matching the grid's visible row indices.

    grid_rows: list of _row_idx values from virtualRowData, or None if no filter.
    Returns the (possibly filtered) DataFrame.
    """
    if grid_rows is None or df is None or df.empty:
        return df
    idx_set = set(int(i) for i in grid_rows)
    return df.loc[df.index.isin(idx_set)].reset_index(drop=True)


_GRID_DIM_COLS = ["Department", "SupervisingPhysician", "ActivityName", "PatientFullName"]


def _apply_grid_row_filter_all_status(df, df_all_status, grid_rows):
    """Apply grid row filter to df_all_status via dimension column matching.

    The grid shows completed sims; df_all_status includes all statuses.
    Match on dimension columns so cancelled sims for the same cohort are kept.
    """
    if grid_rows is None or df is None or df.empty:
        return df_all_status
    if df_all_status is None or df_all_status.empty:
        return df_all_status
    filtered = _apply_grid_row_filter(df, grid_rows)
    if filtered.empty:
        return df_all_status.iloc[:0]
    mask = pd.Series(True, index=df_all_status.index)
    for col in _GRID_DIM_COLS:
        if col in filtered.columns and col in df_all_status.columns:
            vals = set(filtered[col].dropna().unique())
            if vals:
                mask &= df_all_status[col].isin(vals) | df_all_status[col].isna()
    return df_all_status[mask]


# ---------------------------------------------------------------------------
# Callback 1A: Detail Table
# ---------------------------------------------------------------------------

@callback(
    Output("sim-detail-grid", "rowData"),
    Output("sim-detail-grid", "columnDefs"),
    *_SIM_FILTER_INPUTS,
)
def _update_sim_table(*args):
    ctx = _unpack_sim_filter_args(args)
    data = _load_and_filter_sim(**ctx)
    if data is None:
        return [], []
    df = data["df"]
    if df.empty:
        return [], []
    return _build_detail_table(df)


# ---------------------------------------------------------------------------
# Callback 1B: KPIs + Sparklines (responds to grid filter)
# ---------------------------------------------------------------------------

@callback(
    Output("sim-kpi-total", "children"),
    Output("sim-kpi-initial", "children"),
    Output("sim-kpi-lead", "children"),
    Output("sim-kpi-consult-sim", "children"),
    Output("sim-kpi-time-to-tx", "children"),
    Output("sim-kpi-resim", "children"),
    Output("sim-store-kpi-sparklines", "data"),
    *_SIM_FILTER_INPUTS,
    Input("sim-store-resim-scope", "data"),
    Input("sim-outlier-enabled", "data"),
    Input("sim-outlier-cap-0", "value"),
    Input("sim-outlier-cap-1", "value"),
    Input("sim-outlier-cap-2", "value"),
    Input("sim-table-filter-rows", "data"),
)
def _update_sim_kpis(*args):
    ctx = _unpack_sim_filter_args(args)
    resim_scope = args[12] or "resim"
    outlier_enabled = args[13]
    cap_lead_raw, cap_tx_raw, cap_lt_raw = args[14], args[15], args[16]
    grid_rows = args[17]
    if not outlier_enabled:
        cap_lead, cap_time_to_tx, cap_lead_time = 365, 365, 365
    else:
        cap_lead = cap_lead_raw or _CAP_LEAD
        cap_time_to_tx = cap_tx_raw or _CAP_TIME_TO_TX
        cap_lead_time = cap_lt_raw or _CAP_LEAD_TIME
    data = _load_and_filter_sim(**ctx)

    na_card = kpi_card("--", "N/A")
    empty_kpis = (na_card,) * 6 + ({},)
    if data is None:
        return empty_kpis

    df = _apply_grid_row_filter(data["df"], grid_rows)
    if df.empty:
        return empty_kpis
    dfu = _dedup_patient_day(df)
    dfu_all = data["dfu_all"]
    df_all = data["df_all"]
    start, end = data["start"], data["end"]
    date_preset = data["date_preset"]
    ps, pe = data["ps"], data["pe"]

    period_label = _SIM_PERIOD_LABELS.get(date_preset, "YTD")
    trend_label = _SIM_TREND_LABELS.get(date_preset, "")

    sparkline_data = {}

    range_months = (end.year - start.year) * 12 + (end.month - start.month) + 1
    _spark_period = "D" if range_months <= 3 else "W"

    def _spark_bucket(series):
        if _spark_period == "D":
            return series.dt.normalize()
        return series.dt.to_period("W").dt.to_timestamp()

    def _count_spark_raw(sub_df, date_col="ScheduledDateTime"):
        if sub_df.empty or date_col not in sub_df.columns:
            return None
        temp = sub_df.copy()
        temp["_sp"] = _spark_bucket(temp[date_col])
        grp = temp.groupby("_sp").size()
        if len(grp) < 3:
            return None
        return {"labels": [d.isoformat() for d in grp.index], "values": grp.tolist()}

    def _median_spark_raw(sub_df, col, date_col="ScheduledDateTime", cap=None):
        if sub_df.empty or col not in sub_df.columns or date_col not in sub_df.columns:
            return None
        temp = sub_df[[date_col, col]].copy()
        temp[col] = pd.to_numeric(temp[col], errors="coerce")
        temp = temp.dropna()
        if cap is not None:
            temp = temp[(temp[col] >= 0) & (temp[col] <= cap)]
        if temp.empty:
            return None
        temp["_sp"] = _spark_bucket(temp[date_col])
        grp = temp.groupby("_sp")[col].median()
        if len(grp) < 3:
            return None
        return {"labels": [d.isoformat() for d in grp.index], "values": grp.tolist()}

    def _median_days(col, cap=None):
        if col in dfu.columns:
            vals = pd.to_numeric(dfu[col], errors="coerce").dropna()
            if cap is not None:
                vals = vals[(vals >= 0) & (vals <= cap)]
            if len(vals) > 0:
                return vals.median()
        return None

    # Initial sims subset
    is_initial = (
        dfu["ActivityName"].str.contains("Initial", case=False, na=False) |
        dfu["ActivityName"].str.contains("Stereotactic Simulation", case=False, na=False)
    ) if "ActivityName" in dfu.columns else pd.Series(True, index=dfu.index)
    dfu_initial = dfu[is_initial]

    # 1. Total Simulations
    total_count = len(dfu)
    total_spark = _count_spark_raw(dfu)
    if total_spark:
        sparkline_data["total"] = {**total_spark, "color": PRIMARY, "hover_fmt": "%{x|%b %d}: %{customdata:,.0f}<extra></extra>"}

    if ps is not None:
        prior_total = len(dfu_all[(dfu_all["ScheduledDateTime"] >= ps) & (dfu_all["ScheduledDateTime"] <= pe)])
    else:
        prior_total = None
    tt_pct, tt_dir, tt_pv = _sim_trend(total_count, prior_total)
    kpi_total_card = kpi_card(
        f"Total Simulations ({period_label})", f"{total_count:,}",
        trend_text=f"{tt_pct} {trend_label} ({tt_pv:,})" if tt_pct else None,
        trend_direction=tt_dir, accent_color=PRIMARY, sparkline_id="sim-spark-total",
    )

    # 2. Initial Simulations
    initial_count = len(dfu_initial)
    init_spark = _count_spark_raw(dfu_initial)
    if init_spark:
        sparkline_data["initial"] = {**init_spark, "color": CHART_COLORWAY[1], "hover_fmt": "%{x|%b %d}: %{customdata:,.0f}<extra></extra>"}

    if ps is not None:
        is_initial_all = (
            dfu_all["ActivityName"].str.contains("Initial", case=False, na=False) |
            dfu_all["ActivityName"].str.contains("Stereotactic Simulation", case=False, na=False)
        ) if "ActivityName" in dfu_all.columns else pd.Series(True, index=dfu_all.index)
        dfu_all_initial = dfu_all[is_initial_all]
        prior_init = len(dfu_all_initial[(dfu_all_initial["ScheduledDateTime"] >= ps) & (dfu_all_initial["ScheduledDateTime"] <= pe)])
    else:
        prior_init = None
    it_pct, it_dir, it_pv = _sim_trend(initial_count, prior_init)
    kpi_initial_card = kpi_card(
        f"Initial Simulations ({period_label})", f"{initial_count:,}",
        trend_text=f"{it_pct} {trend_label} ({it_pv:,})" if it_pct else None,
        trend_direction=it_dir, accent_color=CHART_COLORWAY[1], sparkline_id="sim-spark-initial",
    )

    # 3. Lead Time (Booked-to-Sim)
    lt_median = _median_days("DaysFromCreatedToAppt", cap=cap_lead_time)
    lt_spark = _median_spark_raw(dfu, "DaysFromCreatedToAppt", cap=cap_lead_time)
    if lt_spark:
        sparkline_data["lead"] = {**lt_spark, "color": CHART_COLORWAY[2], "hover_fmt": "%{x|%b %d}: %{customdata:.0f} days<extra></extra>"}

    if ps is not None and "DaysFromCreatedToAppt" in dfu_all.columns:
        prior_lt_data = dfu_all[(dfu_all["ScheduledDateTime"] >= ps) & (dfu_all["ScheduledDateTime"] <= pe)]
        prior_lt_vals = pd.to_numeric(prior_lt_data["DaysFromCreatedToAppt"], errors="coerce").dropna()
        prior_lt_vals = prior_lt_vals[(prior_lt_vals >= 0) & (prior_lt_vals <= cap_lead_time)]
        prior_lt = prior_lt_vals.median() if len(prior_lt_vals) > 0 else None
    else:
        prior_lt = None
    lt_pct, lt_dir, lt_pv = _sim_trend(lt_median, prior_lt, invert=True) if lt_median else (None, None, None)
    _lead_info = dmc.Tooltip(
        DashIconify(icon="mdi:information-outline", width=16, color="#9CA3AF", style={"cursor": "help"}),
        label=f"Median days from booking creation to simulation. Outlier cap ({cap_lead_time}d). Lower = shorter scheduling horizon.",
        position="top", withArrow=True, multiline=True, w=240,
    )
    kpi_lead_card = kpi_card(
        f"Lead Time ({period_label})", f"{lt_median:.0f}" if lt_median else "N/A",
        value_detail="days" if lt_median else None,
        trend_text=f"{lt_pct} {trend_label} ({lt_pv:.0f}d)" if lt_pct else None,
        trend_direction=lt_dir, accent_color=CHART_COLORWAY[2], sparkline_id="sim-spark-lead",
        header_control=_lead_info,
    )

    # 3b. Consult → Sim
    cs_median = _median_days("DaysFromClinicExamToSimulation", cap=cap_lead)
    cs_spark = _median_spark_raw(dfu, "DaysFromClinicExamToSimulation", cap=cap_lead)
    if cs_spark:
        sparkline_data["consult_sim"] = {**cs_spark, "color": CHART_COLORWAY[5] if len(CHART_COLORWAY) > 5 else "#FF9800", "hover_fmt": "%{x|%b %d}: %{customdata:.0f} days<extra></extra>"}

    if ps is not None and "DaysFromClinicExamToSimulation" in dfu_all.columns:
        prior_cs_data = dfu_all[(dfu_all["ScheduledDateTime"] >= ps) & (dfu_all["ScheduledDateTime"] <= pe)]
        prior_cs_vals = pd.to_numeric(prior_cs_data["DaysFromClinicExamToSimulation"], errors="coerce").dropna()
        prior_cs_vals = prior_cs_vals[(prior_cs_vals >= 0) & (prior_cs_vals <= cap_lead)]
        prior_cs = prior_cs_vals.median() if len(prior_cs_vals) > 0 else None
    else:
        prior_cs = None
    cs_pct, cs_dir, cs_pv = _sim_trend(cs_median, prior_cs, invert=True) if cs_median else (None, None, None)
    _cs_info = dmc.Tooltip(
        DashIconify(icon="mdi:information-outline", width=16, color="#9CA3AF", style={"cursor": "help"}),
        label=f"Median days from consult to simulation. Outlier cap ({cap_lead}d) applies. Lower = faster throughput.",
        position="top", withArrow=True, multiline=True, w=240,
    )
    kpi_consult_sim_card = kpi_card(
        f"Consult \u2192 Sim ({period_label})", f"{cs_median:.0f}" if cs_median else "N/A",
        value_detail="days" if cs_median else None,
        trend_text=f"{cs_pct} {trend_label} ({cs_pv:.0f}d)" if cs_pct else None,
        trend_direction=cs_dir, accent_color=CHART_COLORWAY[5] if len(CHART_COLORWAY) > 5 else "#FF9800",
        sparkline_id="sim-spark-consult-sim",
        header_control=_cs_info,
    )

    # 4. Time to Treatment (Sim-to-Treatment)
    st_median = _median_days("DaysFromSimToTreatment", cap=cap_time_to_tx)
    st_spark = _median_spark_raw(dfu, "DaysFromSimToTreatment", cap=cap_time_to_tx)
    if st_spark:
        sparkline_data["time_to_tx"] = {**st_spark, "color": CHART_COLORWAY[3], "hover_fmt": "%{x|%b %d}: %{customdata:.0f} days<extra></extra>"}

    if ps is not None and "DaysFromSimToTreatment" in dfu_all.columns:
        prior_tx_data = dfu_all[(dfu_all["ScheduledDateTime"] >= ps) & (dfu_all["ScheduledDateTime"] <= pe)]
        prior_tx_vals = pd.to_numeric(prior_tx_data["DaysFromSimToTreatment"], errors="coerce").dropna()
        prior_tx_vals = prior_tx_vals[(prior_tx_vals >= 0) & (prior_tx_vals <= cap_time_to_tx)]
        prior_tx = prior_tx_vals.median() if len(prior_tx_vals) > 0 else None
    else:
        prior_tx = None
    st_pct, st_dir, st_pv = _sim_trend(st_median, prior_tx, invert=True) if st_median else (None, None, None)
    _tx_info = dmc.Tooltip(
        DashIconify(icon="mdi:information-outline", width=16, color="#9CA3AF", style={"cursor": "help"}),
        label=f"Median days from simulation to first treatment. Outlier cap ({cap_time_to_tx}d) applies to this metric. Lower = faster throughput.",
        position="top", withArrow=True, multiline=True, w=240,
    )
    kpi_time_to_tx_card = kpi_card(
        f"Time to Treatment ({period_label})", f"{st_median:.0f}" if st_median else "N/A",
        value_detail="days" if st_median else None,
        trend_text=f"{st_pct} {trend_label} ({st_pv:.0f}d)" if st_pct else None,
        trend_direction=st_dir, accent_color=CHART_COLORWAY[3], sparkline_id="sim-spark-time-to-tx",
        header_control=_tx_info,
    )

    # 5. Re-Sim Rate
    if "ActivityName" in df.columns and "PatientId" in df.columns:
        resim_mask = df["ActivityName"].str.contains("Re-Simulation", case=False, na=False)
        if resim_scope == "resim_decub":
            resim_mask = resim_mask | df["ActivityName"].str.contains("Decub", case=False, na=False)
        resim_patient_days = df[resim_mask][["PatientId", "_SimDate"]].drop_duplicates()
        resim_count = len(resim_patient_days)
        resim_pct_val = (resim_count / total_count * 100) if total_count > 0 else 0
        resim_pct = f"{resim_pct_val:.1f}%"

        if ps is not None:
            prior_dfu = dfu_all[(dfu_all["ScheduledDateTime"] >= ps) & (dfu_all["ScheduledDateTime"] <= pe)]
            prior_df = df_all[(df_all["ScheduledDateTime"] >= ps) & (df_all["ScheduledDateTime"] <= pe)]
            prior_resim_mask = prior_df["ActivityName"].str.contains("Re-Simulation", case=False, na=False)
            if resim_scope == "resim_decub":
                prior_resim_mask = prior_resim_mask | prior_df["ActivityName"].str.contains("Decub", case=False, na=False)
            prior_resim_days = prior_df[prior_resim_mask][["PatientId", "_SimDate"]].drop_duplicates()
            prior_resim_pct = (len(prior_resim_days) / len(prior_dfu) * 100) if len(prior_dfu) > 0 else None
        else:
            prior_resim_pct = None
        rs_pct, rs_dir, rs_pv = _sim_trend(resim_pct_val, prior_resim_pct, invert=True)

        if "ScheduledDateTime" in df.columns:
            temp_all = dfu[["ScheduledDateTime"]].copy()
            temp_all["_sp"] = _spark_bucket(temp_all["ScheduledDateTime"])
            period_total = temp_all.groupby("_sp").size()
            temp_resim = df[resim_mask][["ScheduledDateTime", "PatientId", "_SimDate"]].drop_duplicates(subset=["PatientId", "_SimDate"])
            temp_resim["_sp"] = _spark_bucket(temp_resim["ScheduledDateTime"])
            period_resim = temp_resim.groupby("_sp").size()
            period_rate = (period_resim / period_total * 100).dropna()
            if len(period_rate) >= 3:
                sparkline_data["resim"] = {
                    "labels": [d.isoformat() for d in period_rate.index],
                    "values": period_rate.tolist(),
                    "color": CHART_COLORWAY[4],
                    "hover_fmt": "%{x|%b %d}: %{customdata:.1f}%<extra></extra>",
                }
    else:
        resim_pct = "N/A"
        rs_pct, rs_dir, rs_pv = None, None, None

    kpi_resim_card = kpi_card(
        f"Re-Sim Rate ({period_label})", resim_pct,
        trend_text=f"{rs_pct} {trend_label} ({rs_pv:.1f}%)" if rs_pct else None,
        trend_direction=rs_dir, accent_color=CHART_COLORWAY[4],
        sparkline_id="sim-spark-resim", header_control=_resim_scope_toggle(resim_scope),
    )

    return (
        kpi_total_card, kpi_initial_card, kpi_lead_card, kpi_consult_sim_card,
        kpi_time_to_tx_card, kpi_resim_card, sparkline_data,
    )


# ---------------------------------------------------------------------------
# Callback 2: Volume Store
# ---------------------------------------------------------------------------

@callback(
    Output("sim-store-volume", "data"),
    *_SIM_FILTER_INPUTS,
    Input("sim-volume-agg", "value"),
    Input("sim-volume-slice", "value"),
    Input("sim-table-filter-rows", "data"),
    running=[(Output("sim-chart-volume-loading", "visible"), True, False)],
)
def _update_sim_volume(*args):
    ctx = _unpack_sim_filter_args(args)
    agg, volume_slice, grid_rows = args[12], args[13], args[14]
    data = _load_and_filter_sim(**ctx)
    if data is None:
        return None
    dfu = _dedup_patient_day(_apply_grid_row_filter(data["df"], grid_rows))
    if dfu.empty:
        return None
    return _prepare_volume_data(dfu, agg, slice_by=volume_slice or "", c2b=data["c2b"], diag_mode=data.get("diag_mode", "primary"))


# ---------------------------------------------------------------------------
# Callback 3: Timing Store
# ---------------------------------------------------------------------------

@callback(
    Output("sim-store-timing", "data"),
    *_SIM_FILTER_INPUTS,
    Input("sim-timing-metric", "value"),
    Input("sim-timing-agg", "value"),
    Input("sim-timing-slice", "value"),
    Input("sim-outlier-enabled", "data"),
    Input("sim-outlier-cap-0", "value"),
    Input("sim-outlier-cap-1", "value"),
    Input("sim-outlier-cap-2", "value"),
    Input("sim-table-filter-rows", "data"),
    running=[(Output("sim-chart-timing-loading", "visible"), True, False)],
)
def _update_sim_timing(*args):
    ctx = _unpack_sim_filter_args(args)
    timing_metric, timing_agg, timing_slice = args[12], args[13], args[14]
    outlier_enabled = args[15]
    cap_lead_raw, cap_tx_raw, cap_lt_raw = args[16], args[17], args[18]
    grid_rows = args[19]
    if not outlier_enabled:
        cap_lead, cap_tx, cap_lt = 365, 365, 365
    else:
        cap_lead = cap_lead_raw or _CAP_LEAD
        cap_tx = cap_tx_raw or _CAP_TIME_TO_TX
        cap_lt = cap_lt_raw or _CAP_LEAD_TIME
    # Pick the appropriate cap based on which metric is selected
    metric = timing_metric or "consult_sim"
    cap = cap_lead if metric == "consult_sim" else (cap_lt if metric == "lead_time" else cap_tx)
    data = _load_and_filter_sim(**ctx)
    if data is None:
        return None
    dfu = _dedup_patient_day(_apply_grid_row_filter(data["df"], grid_rows))
    if dfu.empty:
        return None
    return _prepare_timing_data(
        dfu, metric=metric,
        agg=timing_agg or "M", slice_by=timing_slice or "", c2b=data["c2b"],
        cap=cap, diag_mode=data.get("diag_mode", "primary"),
    )


# ---------------------------------------------------------------------------
# Callback 4: Cumulative Store
# ---------------------------------------------------------------------------

@callback(
    Output("sim-store-cumulative", "data"),
    *_SIM_FILTER_INPUTS,
    Input("sim-cumulative-mode", "value"),
    Input("sim-cumulative-period-type", "value"),
    Input("sim-cumulative-slice", "value"),
    Input("sim-table-filter-rows", "data"),
    running=[(Output("sim-chart-cumulative-loading", "visible"), True, False)],
)
def _update_sim_cumulative(*args):
    ctx = _unpack_sim_filter_args(args)
    cumul_mode, cumul_period_type, cumul_slice = args[12], args[13], args[14]
    grid_rows = args[15]
    data = _load_and_filter_sim(**ctx)
    if data is None:
        return None
    dfu_all = _dedup_patient_day(_apply_grid_row_filter(data["df_all"], grid_rows))
    if dfu_all.empty:
        return None
    return _prepare_cumulative_data(
        dfu_all, data["start"], data["end"], data["date_preset"],
        data["departments"], data["physician"], data["sim_types"],
        mode=cumul_mode or "prior",
        period_type=cumul_period_type or "calendar",
        slice_by=cumul_slice or "dept",
        c2b=data["c2b"], max_prior=5,
        diag_mode=data.get("diag_mode", "primary"),
    )


# ---------------------------------------------------------------------------
# Callback 5: Cancel Rate Store
# ---------------------------------------------------------------------------

@callback(
    Output("sim-store-cancel", "data"),
    *_SIM_FILTER_INPUTS,
    Input("sim-cancel-agg", "value"),
    Input("sim-cancel-slice", "value"),
    Input("sim-table-filter-rows", "data"),
    running=[(Output("sim-chart-cancel-rate-loading", "visible"), True, False)],
)
def _update_sim_cancel(*args):
    ctx = _unpack_sim_filter_args(args)
    cancel_agg, cancel_slice, grid_rows = args[12], args[13], args[14]
    data = _load_and_filter_sim(**ctx)
    if data is None:
        return None
    df_all = _apply_grid_row_filter_all_status(data["df"], data["df_all_status"], grid_rows)
    if df_all.empty:
        return None
    return _prepare_cancel_data(df_all, data["start"], data["end"], cancel_agg, cancel_slice)


# ---------------------------------------------------------------------------
# Callback 6: Diagnosis + Billing Figures
# ---------------------------------------------------------------------------

@callback(
    Output("sim-chart-diagnosis", "figure"),
    Output("sim-chart-billing", "figure"),
    *_SIM_FILTER_INPUTS,
    Input("sim-diagnosis-compare", "value"),
    Input("sim-diagnosis-slice", "value"),
    Input("sim-diagnosis-mode", "value"),
    Input("sim-billing-slice", "value"),
    Input("sim-billing-mode", "value"),
    Input("sim-table-filter-rows", "data"),
    running=[
        (Output("sim-diagnosis-loading", "visible"), True, False),
        (Output("sim-billing-loading", "visible"), True, False),
    ],
)
def _update_sim_diag_billing(*args):
    ctx = _unpack_sim_filter_args(args)
    diagnosis_compare, diagnosis_slice, diagnosis_mode = args[12], args[13], args[14]
    billing_slice, billing_mode = args[15], args[16]
    grid_rows = args[17]
    data = _load_and_filter_sim(**ctx)

    empty = empty_figure()
    if data is None:
        return empty, empty

    dfu = _dedup_patient_day(_apply_grid_row_filter(data["df"], grid_rows))
    if dfu.empty:
        return empty, empty
    dfu_all = data["dfu_all"]
    c2b = data["c2b"]
    date_preset = data["date_preset"]
    ps, pe = data["ps"], data["pe"]
    period_label = _SIM_PERIOD_LABELS.get(date_preset, "YTD")

    _diag_prior_df = None
    _diag_period_labels = None
    if diagnosis_compare == "prior" and ps is not None:
        prior_dfu = dfu_all[(dfu_all["ScheduledDateTime"] >= ps) & (dfu_all["ScheduledDateTime"] <= pe)]
        if not prior_dfu.empty:
            _diag_prior_df = prior_dfu
            _diag_period_labels = (period_label, f"Prior {period_label}")
    fig_diagnosis = _build_diagnosis_mix(
        dfu, c2b=c2b, slice_by=diagnosis_slice or "",
        mode=diagnosis_mode or "count",
        prior_df=_diag_prior_df, period_labels=_diag_period_labels,
        diag_mode=data.get("diag_mode", "primary"),
    )
    fig_billing = _build_sim_billing_mix(
        dfu, slice_by=billing_slice or "", mode=billing_mode or "count",
    )

    return fig_diagnosis, fig_billing


# ---------------------------------------------------------------------------
# Clientside callbacks for charts
# ---------------------------------------------------------------------------

clientside_callback(
    ClientsideFunction(namespace="census", function_name="smoothChartWithType"),
    Output("sim-chart-volume", "figure"),
    Input("sim-store-volume", "data"),
    Input("sim-volume-settings-smooth", "value"),
    Input("sim-volume-settings-type", "value"),
    State("sim-chart-volume", "figure"),
)

clientside_callback(
    ClientsideFunction(namespace="census", function_name="smoothChartWithType"),
    Output("sim-chart-timing", "figure"),
    Input("sim-store-timing", "data"),
    Input("sim-timing-settings-smooth", "value"),
    Input("sim-timing-settings-type", "value"),
    State("sim-chart-timing", "figure"),
)

clientside_callback(
    ClientsideFunction(namespace="hoursRibbon", function_name="smoothChartWithType"),
    Output("sim-chart-ribbon", "figure"),
    Input("sim-store-ribbon", "data"),
    Input("sim-ribbon-settings-smooth", "value"),
    Input("sim-ribbon-settings-type", "value"),
)

clientside_callback(
    """function(rawData, smoothPct, chartType, maxPrior, currentFig) {
        return window.dash_clientside.cumulative.renderCumulative(rawData, smoothPct, chartType, currentFig, null, maxPrior);
    }""",
    Output("sim-chart-cumulative", "figure"),
    Input("sim-store-cumulative", "data"),
    Input("sim-cumulative-settings-smooth", "value"),
    Input("sim-cumulative-settings-type", "value"),
    Input("sim-cumulative-settings-prior-periods", "value"),
    State("sim-chart-cumulative", "figure"),
)

# Show/hide cumulative sub-controls based on mode:
# Slice By → show slice selector, hide period-type
# Prior Periods → hide slice selector, show period-type
clientside_callback(
    """function(mode) {
        var isSlice = mode === "slice";
        return [
            isSlice ? {"display": "flex"} : {"display": "none"},
            isSlice ? {"display": "none"} : {"display": "flex"}
        ];
    }""",
    Output("sim-cumulative-slice", "style"),
    Output("sim-cumulative-period-type", "style"),
    Input("sim-cumulative-mode", "value"),
)

clientside_callback(
    ClientsideFunction(namespace="census", function_name="smoothChartWithType"),
    Output("sim-chart-cancel-rate", "figure"),
    Input("sim-store-cancel", "data"),
    Input("sim-cancel-settings-smooth", "value"),
    Input("sim-cancel-settings-type", "value"),
    State("sim-chart-cancel-rate", "figure"),
)

# Register chart_card settings callbacks
register_chart_callbacks([
    ("sim-volume", "sim-chart-volume"),
    ("sim-cumulative", "sim-chart-cumulative"),
    ("sim-timing", "sim-chart-timing"),
    ("sim-cancel", "sim-chart-cancel-rate"),
])

# ---------------------------------------------------------------------------
# Slice-by dim styling (matches clinic_visits pattern)
# ---------------------------------------------------------------------------

_SLICE_CLASS_JS = """function(val) {
    return (val && val !== "total") ? "slice-group-active" : "slice-total-active";
}"""

for _sid in ["sim-volume-slice", "sim-timing-slice", "sim-cancel-slice", "sim-cumulative-slice"]:
    clientside_callback(
        _SLICE_CLASS_JS,
        Output(_sid, "className"),
        Input(_sid, "value"),
    )

# Hide stacked/grouped toggle when slice is Total (single series)
_HIDE_STACK_JS = """function(sliceVal, chartType) {
    var single = !sliceVal || sliceVal === "total" || sliceVal === "";
    var noStack = chartType === "line";
    return (single || noStack) ? {"display": "none"} : {};
}"""

for _slice_id, _settings_id in [
    ("sim-volume-slice", "sim-volume"),
    ("sim-timing-slice", "sim-timing"),
    ("sim-cancel-slice", "sim-cancel"),
    ("sim-cumulative-slice", "sim-cumulative"),
]:
    clientside_callback(
        _HIDE_STACK_JS,
        Output(f"{_settings_id}-settings-stack-wrap", "style", allow_duplicate=True),
        Input(_slice_id, "value"),
        Input(f"{_settings_id}-settings-type", "value"),
        prevent_initial_call=True,
    )


# ---------------------------------------------------------------------------
# Clientside callbacks for KPI sparklines
# ---------------------------------------------------------------------------

for _func, _out_id in [
    ("smoothSpTotal", "sim-spark-total"),
    ("smoothSpInitial", "sim-spark-initial"),
    ("smoothSpLead", "sim-spark-lead"),
    ("smoothSpConsultSim", "sim-spark-consult-sim"),
    ("smoothSpTimeTx", "sim-spark-time-to-tx"),
    ("smoothSpResim", "sim-spark-resim"),
]:
    clientside_callback(
        ClientsideFunction(namespace="sparklines", function_name=_func),
        Output(_out_id, "figure"),
        Input("sim-store-kpi-sparklines", "data"),
        Input("sim-smooth-slider", "value"),
    )


# ---------------------------------------------------------------------------
# Ribbon callback — isolated from all filters except machine + date range
# ---------------------------------------------------------------------------

@callback(
    Output("sim-store-ribbon", "data"),
    Input("sim-interval", "n_intervals"),
    Input("sim-ribbon-machine", "value"),
    Input("sim-date-slider", "value"),
    running=[
        (Output("sim-ribbon-loading", "visible"), True, False),
    ],
)
def update_ribbon(_n, ribbon_machine, slider_val):
    from data.loader import load_simulations

    try:
        df = load_simulations()
    except Exception:
        return None

    if df.empty:
        return None

    # Only completed sims
    if "Status" in df.columns:
        df = df[df["Status"].str.lower().str.contains("completed", na=False)]

    # Exclude non-sim types
    if "ActivityName" in df.columns:
        df = df[~df["ActivityName"].isin(_SIM_TYPE_EXCLUDE)]

    # Machine filter (ribbon-specific)
    if ribbon_machine and ribbon_machine != "all" and "SimulationResource" in df.columns:
        df = df[df["SimulationResource"] == ribbon_machine]

    # Date range from slider
    start, end = _get_date_range(slider_val)
    if "ScheduledDateTime" in df.columns:
        df = df[(df["ScheduledDateTime"] >= start) & (df["ScheduledDateTime"] <= end)]

    if df.empty:
        return None

    return _prepare_ribbon_data(df)


# ---------------------------------------------------------------------------
# Settings panel toggles (ribbon still uses manual Paper layout)
# ---------------------------------------------------------------------------

@callback(Output("sim-ribbon-settings-panel", "style"), Input("sim-ribbon-settings-btn", "n_clicks"), State("sim-ribbon-settings-panel", "style"), prevent_initial_call=True)
def toggle_ribbon_settings(n, style):
    if not n: return style
    return {"display": "block"} if (style or {}).get("display") == "none" else {"display": "none"}

# Hide smoothing slider when ribbon chart is in bar mode
clientside_callback(
    """function(chartType) {
        return chartType === "bar"
            ? {"display": "none"}
            : {"display": ""};
    }""",
    Output("sim-ribbon-settings-smooth-wrap", "style"),
    Input("sim-ribbon-settings-type", "value"),
)


# ---------------------------------------------------------------------------
# Data preparation for clientside charts
# ---------------------------------------------------------------------------

def _trim_edges(series_or_list):
    """Replace leading/trailing zeros/NaN with None so Plotly gaps the line."""
    import math
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

    # Daily
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

    for p, l in candidates:
        if len(p) <= max_ticks:
            return p, l
    return candidates[-1]


def _is_initial_sim(activity_name):
    """Check if an ActivityName is an initial simulation."""
    if pd.isna(activity_name):
        return False
    low = str(activity_name).lower()
    return "initial" in low or "stereotactic simulation" in low


def _prepare_volume_data(df, agg, slice_by="", c2b=None, diag_mode="primary"):
    """Prepare volume trend data for clientside rendering.

    slice_by: "" (total), "scope", "type", "physician", "dept", "machine", "bodysite"
    Data is already filtered by scope in the main callback.
    """
    if df.empty or "ScheduledDateTime" not in df.columns:
        return None

    df = df.copy()

    period_code = "Y" if agg == "Y" else agg
    df["period"] = df["ScheduledDateTime"].dt.to_period(period_code).dt.to_timestamp()

    all_periods = sorted(df["period"].unique())
    dates = [d.isoformat() for d in all_periods]

    series = []

    if not slice_by:
        # No grouping — single total line
        counts = df.groupby("period").size().reindex(all_periods, fill_value=0)
        series.append({
            "name": "Total",
            "values": _trim_edges(counts.tolist()),
            "color": PRIMARY,
        })

    elif slice_by == "scope":
        # Split by Initial vs Re-Sim/Other
        if "ActivityName" in df.columns:
            init_mask = df["ActivityName"].apply(_is_initial_sim)
            for label, mask, color in [
                ("Initial", init_mask, CHART_COLORWAY[0]),
                ("Other", ~init_mask, CHART_COLORWAY[2]),
            ]:
                subset = df[mask]
                if subset.empty:
                    continue
                counts = subset.groupby("period").size().reindex(all_periods, fill_value=0)
                series.append({
                    "name": label,
                    "values": _trim_edges(counts.tolist()),
                    "color": color,
                })

    elif slice_by == "type":
        if "ActivityName" in df.columns:
            sim_types = sorted(df["ActivityName"].dropna().unique().tolist())
            for i, stype in enumerate(sim_types):
                subset = df[df["ActivityName"] == stype]
                counts = subset.groupby("period").size().reindex(all_periods, fill_value=0)
                series.append({
                    "name": _sim_display_name(stype),
                    "values": _trim_edges(counts.tolist()),
                    "color": CHART_COLORWAY[i % len(CHART_COLORWAY)],
                })

    elif slice_by == "physician":
        col = "SupervisingPhysician"
        if col in df.columns:
            physicians = sorted(df[col].dropna().unique())
            for i, phys in enumerate(physicians):
                subset = df[df[col] == phys]
                counts = subset.groupby("period").size().reindex(all_periods, fill_value=0)
                series.append({
                    "name": phys.split(",")[0] if "," in phys else phys,
                    "values": _trim_edges(counts.tolist()),
                    "color": CHART_COLORWAY[i % len(CHART_COLORWAY)],
                })

    elif slice_by == "dept":
        if "Department" in df.columns:
            for dept in sorted(df["Department"].dropna().unique()):
                subset = df[df["Department"] == dept]
                counts = subset.groupby("period").size().reindex(all_periods, fill_value=0)
                series.append({
                    "name": dept,
                    "values": _trim_edges(counts.tolist()),
                    "color": DEPARTMENT_COLORS.get(dept, CHART_COLORWAY[0]),
                })

    elif slice_by == "machine":
        if "SimulationResource" in df.columns:
            for m in sorted(df["SimulationResource"].dropna().unique()):
                subset = df[df["SimulationResource"] == m]
                counts = subset.groupby("period").size().reindex(all_periods, fill_value=0)
                series.append({
                    "name": _SIM_MACHINE_DISPLAY.get(m, m),
                    "values": _trim_edges(counts.tolist()),
                    "color": _SIM_MACHINE_COLORS.get(m, CHART_COLORWAY[len(series) % len(CHART_COLORWAY)]),
                })

    elif slice_by == "bodysite":
        if "DiagnosisCodes" in df.columns and c2b:
            df = assign_diagnosis_column(df, c2b, mode=diag_mode)
            for i, bs in enumerate(sorted(df["_bs"].dropna().unique())):
                subset = df[df["_bs"] == bs]
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
        "yTitle": "Simulations",
        "hideLegend": len(series) <= 1,
    }


def _prepare_cumulative_data(df_all, start, end, date_preset,
                              departments, physician, sim_types,
                              mode="prior",
                              period_type="calendar", slice_by="dept",
                              c2b=None, max_prior=5, diag_mode="primary"):
    """Prepare cumulative simulation volume data for overlay chart.

    mode="prior": Current period cumulative + up to 5 prior equivalent periods.
    mode="slice": Current period only, split by dimension.
    """
    if df_all.empty or "ScheduledDateTime" not in df_all.columns:
        return None

    # Cap end at today
    today = pd.Timestamp.now().normalize()
    if end.normalize() > today:
        end = today

    period_days = (end - start).days + 1
    if period_days < 2:
        return None

    dff_all = df_all.copy()

    if dff_all.empty:
        return None

    def _cumulative_for_window(df, w_start, w_end):
        mask = (df["ScheduledDateTime"] >= w_start) & (df["ScheduledDateTime"] <= w_end)
        sub = df.loc[mask]
        if sub.empty:
            return []
        daily = sub.groupby(sub["ScheduledDateTime"].dt.normalize()).size()
        idx = pd.date_range(w_start.normalize(), w_end.normalize(), freq="D")
        daily = daily.reindex(idx, fill_value=0)
        return daily.cumsum().tolist()

    def _slice_totals_for_window(df, w_start, w_end, sb):
        mask = (df["ScheduledDateTime"] >= w_start) & (df["ScheduledDateTime"] <= w_end)
        sub = df.loc[mask]
        if sub.empty:
            return {}
        if sb == "total":
            return {"Total": len(sub)}
        if sb == "dept" and "Department" in sub.columns:
            return sub.groupby("Department").size().to_dict()
        elif sb == "type" and "ActivityName" in sub.columns:
            counts = sub.groupby("ActivityName").size()
            return {_sim_display_name(k): v for k, v in counts.items()}
        elif sb == "physician" and "SupervisingPhysician" in sub.columns:
            counts = sub.groupby("SupervisingPhysician").size()
            return {(k.split(",")[0] if "," in k else k): v for k, v in counts.items()}
        elif sb == "machine" and "SimulationResource" in sub.columns:
            counts = sub.groupby("SimulationResource").size()
            return {_SIM_MACHINE_DISPLAY.get(k, k): v for k, v in counts.items()}
        elif sb == "scope" and "ActivityName" in sub.columns:
            init_mask = sub["ActivityName"].apply(_is_initial_sim)
            result = {}
            init_count = init_mask.sum()
            other_count = len(sub) - init_count
            if init_count > 0:
                result["Initial"] = int(init_count)
            if other_count > 0:
                result["Other"] = int(other_count)
            return result
        elif sb == "bodysite" and "DiagnosisCodes" in sub.columns and c2b:
            sub_bs = assign_diagnosis_column(sub, c2b, mode=diag_mode)
            return sub_bs.groupby("_bs").size().to_dict() if not sub_bs.empty else {}
        return {}

    n_days = period_days
    start_norm = start.normalize()
    day_indices = list(range(n_days))

    tick_positions, tick_labels = _build_day_index_ticks(start_norm, n_days)

    # Current window cumulative
    current_vals = _cumulative_for_window(dff_all, start, end) if not dff_all.empty else [0] * n_days

    # Earliest data date
    data_min = dff_all["ScheduledDateTime"].min() if not dff_all.empty else start

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

    # Build prior windows
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
    for pi, (label, p_start, p_end) in enumerate(windows):
        vals = _cumulative_for_window(dff_all, p_start, p_end)
        if vals and any(v > 0 for v in vals):
            if len(vals) < n_days:
                vals = vals + [vals[-1] if vals else 0] * (n_days - len(vals))
            elif len(vals) > n_days:
                vals = vals[:n_days]
            prior.append({"label": label, "values": vals, "color": PRIOR_PERIOD_COLORS[min(pi, len(PRIOR_PERIOD_COLORS) - 1)]})

    current_label = _period_label(start, end)

    if len(current_vals) < n_days:
        current_vals = current_vals + [None] * (n_days - len(current_vals))

    # Per-slice-per-period breakdown for bar mode
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
    if slice_by == "dept":
        slice_colors = {k: DEPARTMENT_COLORS.get(k, CHART_COLORWAY[i % len(CHART_COLORWAY)])
                       for i, k in enumerate(slice_keys_sorted)}
    elif slice_by == "machine":
        slice_colors = {k: _SIM_MACHINE_COLORS.get(k, CHART_COLORWAY[i % len(CHART_COLORWAY)])
                       for i, k in enumerate(slice_keys_sorted)}
    elif slice_by == "scope":
        _scope_colors = {"Initial": CHART_COLORWAY[0], "Other": CHART_COLORWAY[2]}
        slice_colors = {k: _scope_colors.get(k, CHART_COLORWAY[i % len(CHART_COLORWAY)])
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
            "yTitle": "Cumulative Simulations",
        }

    # Slice mode
    mask = (dff_all["ScheduledDateTime"] >= start) & (dff_all["ScheduledDateTime"] <= end)
    dff_period = dff_all.loc[mask]

    dates_range = pd.date_range(start.normalize(), end.normalize(), freq="D")

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

    if slice_by == "dept" and "Department" in dff_period.columns:
        for dept in sorted(dff_period["Department"].dropna().unique()):
            sub = dff_period[dff_period["Department"] == dept]
            daily = sub.groupby(sub["ScheduledDateTime"].dt.normalize()).size()
            daily = daily.reindex(dates_range, fill_value=0)
            series.append({
                "name": dept,
                "values": _trimmed_cumsum(daily),
                "color": DEPARTMENT_COLORS.get(dept, CHART_COLORWAY[0]),
            })

    elif slice_by == "type" and "ActivityName" in dff_period.columns:
        for i, stype in enumerate(sorted(dff_period["ActivityName"].dropna().unique())):
            sub = dff_period[dff_period["ActivityName"] == stype]
            daily = sub.groupby(sub["ScheduledDateTime"].dt.normalize()).size()
            daily = daily.reindex(dates_range, fill_value=0)
            series.append({
                "name": _sim_display_name(stype),
                "values": _trimmed_cumsum(daily),
                "color": CHART_COLORWAY[i % len(CHART_COLORWAY)],
            })

    elif slice_by == "physician" and "SupervisingPhysician" in dff_period.columns:
        physicians = sorted(dff_period["SupervisingPhysician"].dropna().unique())
        for i, phys in enumerate(physicians):
            sub = dff_period[dff_period["SupervisingPhysician"] == phys]
            daily = sub.groupby(sub["ScheduledDateTime"].dt.normalize()).size()
            daily = daily.reindex(dates_range, fill_value=0)
            series.append({
                "name": phys.split(",")[0] if "," in phys else phys,
                "values": _trimmed_cumsum(daily),
                "color": CHART_COLORWAY[i % len(CHART_COLORWAY)],
            })

    elif slice_by == "machine" and "SimulationResource" in dff_period.columns:
        for m in sorted(dff_period["SimulationResource"].dropna().unique()):
            sub = dff_period[dff_period["SimulationResource"] == m]
            daily = sub.groupby(sub["ScheduledDateTime"].dt.normalize()).size()
            daily = daily.reindex(dates_range, fill_value=0)
            series.append({
                "name": _SIM_MACHINE_DISPLAY.get(m, m),
                "values": _trimmed_cumsum(daily),
                "color": _SIM_MACHINE_COLORS.get(m, CHART_COLORWAY[len(series) % len(CHART_COLORWAY)]),
            })

    elif slice_by == "scope" and "ActivityName" in dff_period.columns:
        init_mask = dff_period["ActivityName"].apply(_is_initial_sim)
        for label, mask_val, color in [("Initial", init_mask, CHART_COLORWAY[0]), ("Other", ~init_mask, CHART_COLORWAY[2])]:
            sub = dff_period[mask_val]
            if sub.empty:
                continue
            daily = sub.groupby(sub["ScheduledDateTime"].dt.normalize()).size()
            daily = daily.reindex(dates_range, fill_value=0)
            series.append({
                "name": label,
                "values": _trimmed_cumsum(daily),
                "color": color,
            })

    elif slice_by == "bodysite" and "DiagnosisCodes" in dff_period.columns and c2b:
        dff_period_bs = assign_diagnosis_column(dff_period, c2b, mode=diag_mode)
        for i, bs in enumerate(sorted(dff_period_bs["_bs"].dropna().unique())):
            sub = dff_period_bs[dff_period_bs["_bs"] == bs]
            daily = sub.groupby(sub["ScheduledDateTime"].dt.normalize()).size()
            daily = daily.reindex(dates_range, fill_value=0)
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
        "yTitle": "Cumulative Simulations",
    }


def _prepare_timing_data(df, metric="consult_sim", agg="M", slice_by="", c2b=None, cap=None, diag_mode="primary"):
    """Prepare timing interval data for clientside rendering.

    metric: "consult_sim" (DaysFromClinicExamToSimulation) or
            "lead_time" (DaysFromCreatedToAppt — booked-to-happened).
    agg: "W", "M", or "Y".
    slice_by: "" (total), "scope", "type", "dept", "physician", "machine", "bodysite".
    cap: optional outlier cap in days.
    """
    col_map = {
        "consult_sim": "DaysFromClinicExamToSimulation",
        "lead_time": "DaysFromCreatedToAppt",
    }
    title_map = {
        "consult_sim": "Consult \u2192 Sim",
        "lead_time": "Lead Time (Booked \u2192 Sim)",
    }
    value_col = col_map.get(metric, col_map["consult_sim"])

    if df.empty or "ScheduledDateTime" not in df.columns or value_col not in df.columns:
        return None

    df = df.copy()
    df["_val"] = pd.to_numeric(df[value_col], errors="coerce")
    df = df.dropna(subset=["_val"])
    if cap is not None:
        df = df[(df["_val"] >= 0) & (df["_val"] <= cap)]
    if df.empty:
        return None

    period_code = "Y" if agg == "Y" else agg
    df["period"] = df["ScheduledDateTime"].dt.to_period(period_code).dt.to_timestamp()
    all_periods = sorted(df["period"].unique())
    dates = [d.isoformat() for d in all_periods]

    series = []

    if not slice_by:
        medians = df.groupby("period")["_val"].median().reindex(all_periods)
        values = [v if pd.notna(v) else None for v in medians.tolist()]
        series.append({
            "name": title_map.get(metric, metric),
            "values": values,
            "color": PRIMARY,
        })

    elif slice_by == "scope" and "ActivityName" in df.columns:
        init_mask = df["ActivityName"].apply(_is_initial_sim)
        for label, mask_val, color in [("Initial", init_mask, CHART_COLORWAY[0]), ("Other", ~init_mask, CHART_COLORWAY[2])]:
            sub = df[mask_val]
            if sub.empty:
                continue
            medians = sub.groupby("period")["_val"].median().reindex(all_periods)
            values = [v if pd.notna(v) else None for v in medians.tolist()]
            series.append({
                "name": label,
                "values": values,
                "color": color,
            })

    elif slice_by == "type" and "ActivityName" in df.columns:
        for i, stype in enumerate(sorted(df["ActivityName"].dropna().unique())):
            sub = df[df["ActivityName"] == stype]
            medians = sub.groupby("period")["_val"].median().reindex(all_periods)
            values = [v if pd.notna(v) else None for v in medians.tolist()]
            series.append({
                "name": _sim_display_name(stype),
                "values": values,
                "color": CHART_COLORWAY[i % len(CHART_COLORWAY)],
            })

    elif slice_by == "dept" and "Department" in df.columns:
        for dept in sorted(df["Department"].dropna().unique()):
            sub = df[df["Department"] == dept]
            medians = sub.groupby("period")["_val"].median().reindex(all_periods)
            values = [v if pd.notna(v) else None for v in medians.tolist()]
            series.append({
                "name": dept,
                "values": values,
                "color": DEPARTMENT_COLORS.get(dept, CHART_COLORWAY[len(series) % len(CHART_COLORWAY)]),
            })

    elif slice_by == "physician" and "SupervisingPhysician" in df.columns:
        for i, phys in enumerate(sorted(df["SupervisingPhysician"].dropna().unique())):
            sub = df[df["SupervisingPhysician"] == phys]
            medians = sub.groupby("period")["_val"].median().reindex(all_periods)
            values = [v if pd.notna(v) else None for v in medians.tolist()]
            series.append({
                "name": phys.split(",")[0] if "," in phys else phys,
                "values": values,
                "color": CHART_COLORWAY[i % len(CHART_COLORWAY)],
            })

    elif slice_by == "machine" and "SimulationResource" in df.columns:
        for m in sorted(df["SimulationResource"].dropna().unique()):
            sub = df[df["SimulationResource"] == m]
            medians = sub.groupby("period")["_val"].median().reindex(all_periods)
            values = [v if pd.notna(v) else None for v in medians.tolist()]
            series.append({
                "name": _SIM_MACHINE_DISPLAY.get(m, m),
                "values": values,
                "color": _SIM_MACHINE_COLORS.get(m, CHART_COLORWAY[len(series) % len(CHART_COLORWAY)]),
            })

    elif slice_by == "bodysite" and "DiagnosisCodes" in df.columns and c2b:
        df = assign_diagnosis_column(df, c2b, mode=diag_mode)
        for i, bs in enumerate(sorted(df["_bs"].dropna().unique())):
            sub = df[df["_bs"] == bs]
            medians = sub.groupby("period")["_val"].median().reindex(all_periods)
            values = [v if pd.notna(v) else None for v in medians.tolist()]
            series.append({
                "name": bs,
                "values": values,
                "color": CHART_COLORWAY[i % len(CHART_COLORWAY)],
            })

    if not series:
        return None

    return {
        "dates": dates,
        "series": series,
        "height": 350,
        "yTitle": "Median Days",
        "hideLegend": len(series) <= 1,
    }


def _prepare_ribbon_data(df):
    """Prepare schedule ribbon data for clientside rendering.

    This spans ALL historical data (not just filtered date range).
    """
    if df.empty or "ScheduledDateTime" not in df.columns:
        return None

    df = df.copy()
    df["Date"] = df["ScheduledDateTime"].dt.normalize()
    df["TimeHour"] = df["ScheduledDateTime"].dt.hour + df["ScheduledDateTime"].dt.minute / 60

    # Compute end time from DurationMinutes if available
    dur_col = "DurationMinutes" if "DurationMinutes" in df.columns else "Duration" if "Duration" in df.columns else None
    if dur_col:
        dur_minutes = pd.to_numeric(df[dur_col], errors="coerce").fillna(0)
        df["EndHour"] = df["TimeHour"] + dur_minutes / 60
    else:
        df["EndHour"] = df["TimeHour"]

    # Filter to weekdays and exclude holidays
    holidays = get_holidays()
    df = df[(df["Date"].dt.weekday < 5) & (~df["Date"].dt.normalize().isin(holidays))]

    daily = df.groupby("Date").agg(
        earliest_start=("TimeHour", "min"),
        latest_end=("EndHour", "max"),
    ).reset_index().sort_values("Date")

    # Clamp values to the display range
    daily["earliest_start"] = daily["earliest_start"].clip(lower=6, upper=20)
    daily["latest_end"] = daily["latest_end"].clip(lower=6, upper=20)

    # Build series for hoursRibbon clientside callback
    series = [{
        "name": "Simulations",
        "dates": [d.isoformat() for d in daily["Date"]],
        "startHours": daily["earliest_start"].tolist(),
        "endHours": daily["latest_end"].tolist(),
        "color": PRIMARY,
        "isFuture": False,
    }]

    # Calculate y-axis range
    min_hour = daily["earliest_start"].min()
    max_hour = daily["latest_end"].max()
    y_min = max(0, np.floor(min_hour) - 0.5)
    y_max = min(24, np.ceil(max_hour) + 0.5)

    tickvals = list(range(int(y_min) + 1, int(y_max), 2))
    ticktext = []
    for h in tickvals:
        if h < 12:
            ticktext.append(f"{h}am")
        elif h == 12:
            ticktext.append("12pm")
        else:
            ticktext.append(f"{h - 12}pm")

    # Pass holiday dates for rangebreaks
    holiday_strs = sorted([h.isoformat() for h in holidays
                           if daily["Date"].min() <= h <= daily["Date"].max()])

    return {
        "pastSeries": series,
        "futureSeries": [],
        "yAxis": {
            "min": y_min,
            "max": y_max,
            "tickvals": tickvals,
            "ticktext": ticktext,
        },
        "today": pd.Timestamp.now().normalize().isoformat(),
        "holidays": holiday_strs,
    }


def _build_type_distribution(df):
    """Horizontal bar chart of counts by ActivityName."""
    if df.empty or "ActivityName" not in df.columns:
        return empty_figure("No sim type data available")

    counts = df["ActivityName"].value_counts().sort_values(ascending=True)
    display_labels = [_sim_display_name(n) for n in counts.index]

    colors = [CHART_COLORWAY[i % len(CHART_COLORWAY)] for i in range(len(counts))]

    fig = go.Figure(go.Bar(
        x=counts.values,
        y=display_labels,
        orientation="h",
        marker_color=colors,
        text=counts.values,
        textposition="auto",
    ))

    apply_default_layout(fig, height=max(280, len(counts) * 30 + 60))
    fig.update_layout(xaxis_title="Count", yaxis_title="", margin=dict(l=180, r=16, t=16, b=48))
    return fig


def _prepare_cancel_data(dff_all, start, end, agg="M", slice_by=""):
    """Prepare cancellation rate data for clientside rendering.

    Computes cancel/no-show percentage per period, optionally sliced by type or dept.
    Uses all-status data (not filtered to completed-only).
    """
    if dff_all.empty or "Status" not in dff_all.columns or "ScheduledDateTime" not in dff_all.columns:
        return None

    dff = dff_all.copy()
    # Apply date range
    dff = dff[(dff["ScheduledDateTime"] >= start) & (dff["ScheduledDateTime"] <= end)]
    if dff.empty:
        return None

    period_code = "Y" if agg == "Y" else agg
    dff["period"] = dff["ScheduledDateTime"].dt.to_period(period_code).dt.to_timestamp()
    dff["_cancelled"] = dff["Status"].str.lower().str.contains("cancel|no-show|no show", na=False)

    all_periods = sorted(dff["period"].unique())
    dates = [d.isoformat() for d in all_periods]

    series = []

    if not slice_by:
        totals = dff.groupby("period").size().reindex(all_periods, fill_value=0)
        cancels = dff[dff["_cancelled"]].groupby("period").size().reindex(all_periods, fill_value=0)
        rates = ((cancels / totals) * 100).fillna(0)
        series.append({
            "name": "Cancel Rate",
            "values": _trim_edges(rates.tolist()),
            "color": PRIMARY,
        })

    elif slice_by == "scope":
        if "ActivityName" in dff.columns:
            init_mask = dff["ActivityName"].apply(_is_initial_sim)
            for i, (label, subset) in enumerate([("Initial", dff[init_mask]), ("Other", dff[~init_mask])]):
                if subset.empty:
                    continue
                totals = subset.groupby("period").size().reindex(all_periods, fill_value=0)
                cancels = subset[subset["_cancelled"]].groupby("period").size().reindex(all_periods, fill_value=0)
                rates = ((cancels / totals) * 100).fillna(0)
                series.append({
                    "name": label,
                    "values": _trim_edges(rates.tolist()),
                    "color": CHART_COLORWAY[i % len(CHART_COLORWAY)],
                })

    elif slice_by == "dept":
        if "Department" in dff.columns:
            for dept in sorted(dff["Department"].dropna().unique()):
                subset = dff[dff["Department"] == dept]
                if subset.empty:
                    continue
                totals = subset.groupby("period").size().reindex(all_periods, fill_value=0)
                cancels = subset[subset["_cancelled"]].groupby("period").size().reindex(all_periods, fill_value=0)
                rates = ((cancels / totals) * 100).fillna(0)
                series.append({
                    "name": dept,
                    "values": _trim_edges(rates.tolist()),
                    "color": DEPARTMENT_COLORS.get(dept, CHART_COLORWAY[0]),
                })

    return {"dates": dates, "series": series, "height": 320, "yTitle": "Cancellation Rate (%)", "stacked": False, "hideLegend": len(series) <= 1}


def _build_diagnosis_mix(dff, c2b=None, slice_by="", mode="count",
                          prior_df=None, period_labels=None, diag_mode="primary"):
    """Horizontal bar chart of simulations by body system (via diagnosis lookup).

    slice_by: "" for total, "scope"/"physician"/"dept"/"machine" for stacked bars.
    mode: "count" (absolute) or "pct" (% of total).
    prior_df: if provided, show paired current/prior bars (ignores slice_by).
    period_labels: tuple (current_label, prior_label).
    """
    if dff.empty:
        return empty_figure("Diagnosis data unavailable")

    if not (c2b and "DiagnosisCodes" in dff.columns):
        return empty_figure("Diagnosis data unavailable")

    work = assign_diagnosis_column(dff, c2b, mode=diag_mode)

    if work.empty:
        return empty_figure("No diagnosis data")

    # Top 12 body systems
    top_bs = work["_bs"].value_counts().head(12)
    top_bs_names = top_bs.index.tolist()
    work = work[work["_bs"].isin(top_bs_names)]
    bs_order = list(reversed(top_bs_names))

    total_current = len(work)
    fig = go.Figure()

    # --- Prior-period comparison mode ---
    if prior_df is not None and not prior_df.empty and "DiagnosisCodes" in prior_df.columns:
        prior_work = assign_diagnosis_column(prior_df, c2b, mode=diag_mode)
        prior_work = prior_work[prior_work["_bs"].isin(top_bs_names)]
        total_prior = len(prior_work)

        curr_counts = work["_bs"].value_counts().reindex(bs_order, fill_value=0)
        prior_counts = prior_work["_bs"].value_counts().reindex(bs_order, fill_value=0)

        curr_label = period_labels[0] if period_labels else "Current"
        prior_label = period_labels[1] if period_labels and len(period_labels) > 1 else "Prior"

        if mode == "pct":
            curr_vals = (curr_counts / total_current * 100).round(1) if total_current else curr_counts * 0
            prior_vals = (prior_counts / total_prior * 100).round(1) if total_prior else prior_counts * 0
            curr_hover = [f"<b>{bs}</b><br>{curr_label}: {v:.1f}%<extra></extra>" for bs, v in zip(bs_order, curr_vals)]
            prior_hover = [f"<b>{bs}</b><br>{prior_label}: {v:.1f}%<extra></extra>" for bs, v in zip(bs_order, prior_vals)]
        else:
            curr_vals = curr_counts
            prior_vals = prior_counts
            curr_hover = [f"<b>{bs}</b><br>{curr_label}: {v:,}<extra></extra>" for bs, v in zip(bs_order, curr_vals)]
            prior_hover = [f"<b>{bs}</b><br>{prior_label}: {v:,}<extra></extra>" for bs, v in zip(bs_order, prior_vals)]

        fig.add_trace(go.Bar(
            x=list(prior_vals), y=[str(b) for b in bs_order], orientation="h",
            marker_color="rgba(156, 163, 175, 0.5)", name=prior_label,
            hovertemplate=prior_hover,
        ))
        fig.add_trace(go.Bar(
            x=list(curr_vals), y=[str(b) for b in bs_order], orientation="h",
            marker_color=CHART_COLORWAY[0], name=curr_label,
            hovertemplate=curr_hover,
        ))

        apply_default_layout(fig, barmode="group")
        fig.update_layout(
            xaxis_title="", yaxis_title="",
            xaxis_visible=False,
            yaxis=dict(automargin="left+top+bottom", ticklabelstandoff=0),
            margin=dict(l=0, r=8, t=24, b=12),
            showlegend=True, bargroupgap=0.15,
        )
        if mode == "pct":
            fig.update_layout(xaxis=dict(ticksuffix="%"))
        return fig

    # --- Standard mode ---
    if not slice_by:
        counts = work["_bs"].value_counts().reindex(bs_order, fill_value=0)
        if mode == "pct":
            vals = (counts / total_current * 100).round(1) if total_current else counts * 0
            text = [f"{v:.1f}%" for v in vals]
            hover = [f"<b>{bs}</b><br>{v:.1f}%<extra></extra>" for bs, v in zip(bs_order, vals)]
        else:
            vals = counts
            text = [f"{v:,}" for v in vals]
            hover = [f"<b>{bs}</b><br>{v:,}<extra></extra>" for bs, v in zip(bs_order, vals)]
        fig.add_trace(go.Bar(
            x=list(vals), y=[str(b) for b in bs_order], orientation="h",
            marker_color=CHART_COLORWAY[0], showlegend=False,
            text=text, textposition="auto", textangle=0, hovertemplate=hover,
        ))
    else:
        if slice_by == "scope" and "ActivityName" in work.columns:
            init_mask = work["ActivityName"].apply(_is_initial_sim)
            col = None
            groups_data = [("Initial", work[init_mask]), ("Other", work[~init_mask])]
            colors = {"Initial": CHART_COLORWAY[0], "Other": CHART_COLORWAY[2]}
        elif slice_by == "physician" and "SupervisingPhysician" in work.columns:
            col = "SupervisingPhysician"
            groups = sorted(work[col].dropna().unique())
            colors = {g: CHART_COLORWAY[i % len(CHART_COLORWAY)] for i, g in enumerate(groups)}
            groups_data = [(g.split(",")[0] if "," in g else g, work[work[col] == g]) for g in groups]
        elif slice_by == "dept" and "Department" in work.columns:
            col = "Department"
            groups = sorted(work[col].dropna().unique())
            colors = {g: DEPARTMENT_COLORS.get(g, CHART_COLORWAY[i % len(CHART_COLORWAY)]) for i, g in enumerate(groups)}
            groups_data = [(g, work[work[col] == g]) for g in groups]
        elif slice_by == "machine" and "SimulationResource" in work.columns:
            col = "SimulationResource"
            groups = sorted(work[col].dropna().unique())
            colors = {_SIM_MACHINE_DISPLAY.get(g, g): _SIM_MACHINE_COLORS.get(g, CHART_COLORWAY[i % len(CHART_COLORWAY)]) for i, g in enumerate(groups)}
            groups_data = [(_SIM_MACHINE_DISPLAY.get(g, g), work[work[col] == g]) for g in groups]
        else:
            groups_data = []
            colors = {}

        for idx, (name, subset) in enumerate(groups_data):
            if subset.empty:
                continue
            counts = subset["_bs"].value_counts().reindex(bs_order, fill_value=0)
            if mode == "pct":
                grp_total = len(subset)
                vals = (counts / grp_total * 100).round(1) if grp_total else counts * 0
            else:
                vals = counts
            # Try name first (scope uses display names as keys), then fall back to colorway
            color = colors.get(name, CHART_COLORWAY[idx % len(CHART_COLORWAY)])
            fig.add_trace(go.Bar(
                x=list(vals), y=[str(b) for b in bs_order], orientation="h",
                marker_color=color,
                name=name,
            ))

    apply_default_layout(fig, barmode="stack")
    fig.update_layout(
        xaxis_title="", yaxis_title="",
        xaxis_visible=False,
        yaxis=dict(automargin="left+top+bottom", ticklabelstandoff=0),
        margin=dict(l=0, r=8, t=24, b=12),
        showlegend=bool(slice_by),
    )
    if mode == "pct":
        fig.update_layout(xaxis=dict(ticksuffix="%"))
    return fig


def _build_sim_billing_mix(dff, slice_by="", mode="count"):
    """Horizontal bar chart of sim CPT billing codes.

    slice_by: "" (total), "physician", or "dept"
    mode: "count" (absolute) or "pct" (% of sims with any code)
    """
    if dff.empty or "ProcedureCodes" not in dff.columns:
        return empty_figure("Billing data unavailable")

    # Build working df
    cols = ["ProcedureCodes"]
    if slice_by == "scope" and "ActivityName" in dff.columns:
        cols.append("ActivityName")
    elif slice_by == "physician" and "SupervisingPhysician" in dff.columns:
        cols.append("SupervisingPhysician")
    elif slice_by == "dept" and "Department" in dff.columns:
        cols.append("Department")

    work = dff[cols].copy()
    work = work.dropna(subset=["ProcedureCodes"])
    work = work[work["ProcedureCodes"].str.strip() != ""]

    if work.empty:
        return empty_figure("No billed simulations found")

    # Explode comma-separated codes
    work["_code"] = work["ProcedureCodes"].str.split(",")
    work = work.explode("_code")
    work["_code"] = work["_code"].str.strip()

    # Separate NC-modifier codes
    nc_mask = work["_code"].str.endswith(" NC", na=False)
    nc_rows = work[nc_mask].copy()
    work = work[~nc_mask]

    # Strip modifiers ("77290 Q6" → "77290", "77014-TC" → "77014")
    work["_base"] = work["_code"].str.split(" ").str[0]
    work["_base"] = work["_base"].str.split("-").str[0]

    # Filter to known sim CPT codes
    work = work[work["_base"].isin(_SIM_CPT_ALL)]
    work["_code"] = work["_base"]

    n_nc = len(nc_rows)
    if work.empty and n_nc == 0:
        return empty_figure("No sim billing codes found")

    # Code ordering by frequency, descending
    code_totals = work["_code"].value_counts() if not work.empty else pd.Series(dtype=int)
    code_order = list(reversed(code_totals.index.tolist()))
    if n_nc > 0:
        code_order = ["No Charge"] + code_order

    # Determine slice column
    slice_col = None
    if slice_by == "scope" and "ActivityName" in work.columns:
        slice_col = "_scope"
        init_mask = work["ActivityName"].apply(_is_initial_sim)
        work["_scope"] = init_mask.map({True: "Initial", False: "Other"})
        if n_nc > 0 and "ActivityName" in nc_rows.columns:
            nc_init = nc_rows["ActivityName"].apply(_is_initial_sim)
            nc_rows = nc_rows.copy()
            nc_rows["_scope"] = nc_init.map({True: "Initial", False: "Other"})
    elif slice_by == "physician" and "SupervisingPhysician" in work.columns:
        slice_col = "SupervisingPhysician"
    elif slice_by == "dept" and "Department" in work.columns:
        slice_col = "Department"

    fig = go.Figure()

    if not slice_by or not slice_col:
        regular_codes = [c for c in code_order if c != "No Charge"]
        counts = code_totals.reindex(regular_codes, fill_value=0)
        raw_codes = list(counts.index)
        vals = counts.tolist()
        labels = [_SIM_CPT_LABELS.get(c, c) for c in raw_codes]
        if n_nc > 0:
            vals = [n_nc] + vals
            labels = ["No Charge"] + labels
            raw_codes = ["No Charge"] + raw_codes

        descs = [_SIM_CPT_DESCRIPTIONS.get(c, c) for c in raw_codes]

        if mode == "pct":
            denom = len(dff)
            vals = [round(v / denom * 100, 1) if denom else 0.0 for v in vals]

        hover = [f"<b>{d}</b><br>{v:.1f}%<extra></extra>" if mode == "pct"
                 else f"<b>{d}</b><br>{v:,}<extra></extra>"
                 for d, v in zip(descs, vals)]

        fig.add_trace(go.Bar(
            x=vals, y=labels, orientation="h",
            marker_color=[("#9CA3AF" if l == "No Charge" else CHART_COLORWAY[0]) for l in labels],
            showlegend=False,
            text=[f"{v:.1f}%" for v in vals] if mode == "pct" else [f"{v:,}" for v in vals],
            textposition="auto",
            hovertemplate=hover,
        ))
    else:
        groups_list = sorted(work[slice_col].dropna().unique())
        if slice_by == "dept":
            colors = {g: DEPARTMENT_COLORS.get(g, CHART_COLORWAY[i % len(CHART_COLORWAY)])
                      for i, g in enumerate(groups_list)}
        elif slice_by == "scope":
            colors = {"Initial": CHART_COLORWAY[0], "Other": CHART_COLORWAY[2]}
        else:
            colors = {g: CHART_COLORWAY[i % len(CHART_COLORWAY)]
                      for i, g in enumerate(groups_list)}

        regular_codes = [c for c in code_order if c != "No Charge"]
        for grp in groups_list:
            subset = work[work[slice_col] == grp]
            counts = subset["_code"].value_counts().reindex(regular_codes, fill_value=0)
            raw_codes = list(counts.index)
            vals = counts.tolist()
            labels = [_SIM_CPT_LABELS.get(c, c) for c in raw_codes]

            if n_nc > 0:
                nc_slice = len(nc_rows[nc_rows[slice_col] == grp]) if slice_col in nc_rows.columns else 0
                vals = [nc_slice] + vals
                labels = ["No Charge"] + labels
                raw_codes = ["No Charge"] + raw_codes

            descs = [_SIM_CPT_DESCRIPTIONS.get(c, c) for c in raw_codes]

            if mode == "pct":
                denom = len(dff[dff[slice_col] == grp]) if slice_col in dff.columns else len(dff)
                vals = [round(v / denom * 100, 1) if denom else 0.0 for v in vals]

            grp_name = grp.split(",")[0] if "," in str(grp) else str(grp)
            hover = [f"<b>{d}</b><br>{grp_name}: {v:.1f}%<extra></extra>" if mode == "pct"
                     else f"<b>{d}</b><br>{grp_name}: {v:,}<extra></extra>"
                     for d, v in zip(descs, vals)]

            fig.add_trace(go.Bar(
                x=vals, y=labels, orientation="h",
                marker_color=colors.get(grp, CHART_COLORWAY[0]),
                name=grp_name,
                hovertemplate=hover,
            ))

    apply_default_layout(fig, barmode="stack")
    fig.update_layout(
        xaxis_title="", yaxis_title="",
        xaxis_visible=False,
        yaxis=dict(automargin="left+top+bottom", ticklabelstandoff=0),
        margin=dict(l=0, r=8, t=24, b=12),
        showlegend=bool(slice_by and slice_col),
    )
    if mode == "pct":
        fig.update_layout(xaxis=dict(ticksuffix="%"))
    return fig


def _build_detail_table(df):
    """Build AG Grid table data and column definitions."""
    display_cols = [
        "ScheduledDateTime", "PatientFullName", "Department",
        "SupervisingPhysician", "ActivityName", "Duration",
        "DaysFromClinicExamToSimulation", "DaysFromSimToTreatment",
        "DaysFromClinicExamToTreatment",
    ]

    available_cols = [c for c in display_cols if c in df.columns]

    if not available_cols:
        return [], []

    table_df = df[available_cols].copy()
    table_df["_row_idx"] = df.index

    # Apply display names for sim types
    if "ActivityName" in table_df.columns:
        table_df["ActivityName"] = table_df["ActivityName"].map(_sim_display_name)

    for c in table_df.select_dtypes(include=["datetime64"]).columns:
        table_df[c] = table_df[c].dt.strftime("%m/%d/%Y %I:%M %p")

    table_df = sanitize_for_grid(table_df)

    header_map = {
        "ScheduledDateTime": "Scheduled",
        "Department": "Department",
        "SupervisingPhysician": "Physician",
        "ActivityName": "Sim Type",
        "Duration": "Duration (min)",
        "PatientFullName": "Patient",
        "DaysFromClinicExamToSimulation": "Consult\u2192Sim (days)",
        "DaysFromSimToTreatment": "Sim\u2192Tx (days)",
        "DaysFromClinicExamToTreatment": "Consult\u2192Tx (days)",
    }

    col_defs = []
    for c in available_cols:
        d = {"field": c, "headerName": header_map.get(c, c)}
        if c == "ScheduledDateTime":
            d["sort"] = "desc"
        col_defs.append(d)
    col_defs.append({"field": "_row_idx", "hide": True})

    return table_df.to_dict("records"), col_defs


# ---------------------------------------------------------------------------
# CSV Export callback
# ---------------------------------------------------------------------------

clientside_callback(
    """function(n) {
        if (!n) return window.dash_clientside.no_update;
        gridExportCsv('sim-detail-grid', 'simulations.csv');
        return window.dash_clientside.no_update;
    }""",
    Output("sim-table-export", "n_clicks"),
    Input("sim-table-export", "n_clicks"),
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
    Output("sim-table-filter-rows", "data"),
    Output("sim-grid-filter-badge", "style"),
    Output("sim-table-clear-filters", "style"),
    Input("sim-detail-grid", "virtualRowData"),
    State("sim-detail-grid", "rowData"),
    State("sim-table-filter-rows", "data"),
    prevent_initial_call=True,
)


# Clear Filters button — reset grid filterModel
clientside_callback(
    """function(n) {
        if (!n) return window.dash_clientside.no_update;
        return {};
    }""",
    Output("sim-detail-grid", "filterModel"),
    Input("sim-table-clear-filters", "n_clicks"),
    prevent_initial_call=True,
)


# Badge click → scroll to the detail table
clientside_callback(
    """function(n) {
        if (!n) return window.dash_clientside.no_update;
        var el = document.getElementById('sim-detail-grid');
        if (el) el.scrollIntoView({behavior: 'smooth', block: 'start'});
        return window.dash_clientside.no_update;
    }""",
    Output("sim-grid-filter-badge", "n_clicks"),
    Input("sim-grid-filter-badge", "n_clicks"),
    prevent_initial_call=True,
)
