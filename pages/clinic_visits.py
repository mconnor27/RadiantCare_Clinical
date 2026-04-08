"""Clinic Visits page — visit volumes, lead times, conversion rates, and detail grid."""

import dash
import dash_mantine_components as dmc
import dash_ag_grid as dag
from dash import callback, Input, Output, State, dcc, html, clientside_callback, ClientsideFunction
from dash_iconify import DashIconify
import plotly.graph_objects as go
import pandas as pd
import numpy as np

from config.settings import (
    DEPARTMENTS, DEPARTMENT_COLORS, CHART_COLORWAY,
    PRIMARY, DEFAULT_LAYOUT, FONT_FAMILY, DEFAULT_COLUMN_DEFS, DEFAULT_GRID_OPTIONS,
    CHART_PAPER_HEIGHT_SM, PRIOR_PERIOD_COLORS,
)
from components.filter_bar import department_chips
from components.kpi_card import kpi_card, kpi_placeholder
from components.chart_card import chart_card, register_chart_callbacks
from components.chart_settings import chart_settings_popover
from components.detail_table import detail_table
from components.outlier_panel import outlier_panel, register_outlier_callbacks
from utils.charts import apply_default_layout, empty_figure, dept_color
from utils.date_slider import (
    month_idx, idx_to_date, MAX_IDX, DEFAULT_SLIDER, SLIDER_MARKS,
    preset_to_slider_val,
)

dash.register_page(__name__, path="/clinic-visits", name="Clinic Visits", order=3)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_DEFAULT_DATE_PRESET = "ytd" if pd.Timestamp.now().month > 1 else "3mo"

VISIT_CATEGORIES = ["All", "Consult", "Follow-Up", "Re-eval", "Virtual"]
VISIT_TYPES = ["All", "Consult", "Follow-Up", "Virtual", "Other"]

_ACTIVITY_TO_CATEGORY = {
    "Consult": "Consult",
    "Consult - Special request": "Consult",
    "Consult- ADD ON": "Consult",
    "Follow-Up": "Follow-Up",
    "Re-eval": "Re-eval",
    "Virtual Consult/Follow Up": "Virtual",
}

from utils.diagnosis_categories import (
    CATEGORIES as BODY_SYSTEMS,
    build_code_to_category,
    get_categories_for_codes,
    primary_category,
)

# Outlier caps for KPI filtering
_LEAD_MAX = 30      # max days for consult lead time
_DAYS_TO_SIM_MAX = 21  # max days for consult-to-sim

# Billing code groups for Billing Mix chart
BILLING_GROUPS = {
    "new": {
        "label": "New Patient",
        "primary": ["99203", "99204", "99205"],
        "addons": ["G2211", "G2212", "99417"],
    },
    "established": {
        "label": "Established",
        "primary": ["99212", "99213", "99214", "99215"],
        "addons": ["G2211", "G2212", "99417"],
    },
    "inpatient": {
        "label": "Inpatient",
        "primary": ["99221", "99222", "99223"],
        "addons": [],
    },
    "telehealth": {
        "label": "Telehealth",
        "primary": ["98003", "98004", "98007", "98015"],
        "addons": [],
    },
}

_CPT_LABELS = {
    "99203": "99203", "99204": "99204", "99205": "99205",
    "99212": "99212", "99213": "99213", "99214": "99214", "99215": "99215",
    "99221": "99221", "99222": "99222", "99223": "99223",
    "98003": "98003", "98004": "98004", "98007": "98007", "98015": "98015",
    "G2211": "G2211", "G2212": "G2212", "99417": "99417",
}

_CPT_DESCRIPTIONS = {
    "99203": "New Patient, Low Complexity (30 min)",
    "99204": "New Patient, Moderate Complexity (45 min)",
    "99205": "New Patient, High Complexity (60 min)",
    "99212": "Established, Straightforward (10 min)",
    "99213": "Established, Low Complexity (20 min)",
    "99214": "Established, Moderate Complexity (30 min)",
    "99215": "Established, High Complexity (40 min)",
    "99221": "Initial Hospital, Low Complexity",
    "99222": "Initial Hospital, Moderate Complexity",
    "99223": "Initial Hospital, High Complexity",
    "98003": "Telehealth New Patient (60+ min)",
    "98004": "Telehealth Established (10-20 min)",
    "98007": "Telehealth Established (40+ min)",
    "98015": "Telephone E/M, Established",
    "G2211": "Complexity Add-on (serious/complex condition)",
    "G2212": "Prolonged Service Add-on",
    "99417": "Prolonged Service (+15 min beyond threshold)",
}


# ---------------------------------------------------------------------------
# Holiday Detection (mirrors workflow.py logic)
# ---------------------------------------------------------------------------

_CALL_STATUSES = frozenset({"ON CALL", "WEEKEND CALL"})
_HOLIDAY_OFF_STATUSES = frozenset({"OFF", "ON CALL", "WEEKEND CALL"})

def _derive_cv_holidays():
    """Derive holiday dates from physician schedule.

    A real clinic closure is a date where every core physician is OFF or
    on call, and **no** physician has VACATION status.  ARIA codes true
    holidays (Thanksgiving, Christmas, etc.) as OFF; personal time off
    is coded as VACATION.  Excluding VACATION prevents coincidental
    all-off days from being mistaken for holidays.
    """
    from data.loader import load_physician_schedule

    try:
        sched = load_physician_schedule()
    except Exception:
        return set()

    if sched.empty or "Date" not in sched.columns:
        return set()

    sched["_status_upper"] = sched["Status"].str.upper().str.strip()

    core = set(sched["Physician"].dropna().unique())
    if len(core) < 2:
        return set()

    holidays = set()
    for date, grp in sched.groupby(sched["Date"].dt.normalize()):
        physicians_present = set(grp["Physician"].unique())
        if not core.issubset(physicians_present):
            continue
        statuses = set(grp["_status_upper"])
        # Real holidays: all OFF/ON CALL, never VACATION or SICK LEAVE
        if not statuses - _HOLIDAY_OFF_STATUSES and "VACATION" not in statuses and "SICK LEAVE" not in statuses:
            holidays.add(date)

    return holidays

_cv_holidays_cache = None

def _get_cv_holidays():
    global _cv_holidays_cache
    if _cv_holidays_cache is None:
        _cv_holidays_cache = _derive_cv_holidays()
    return _cv_holidays_cache


def _get_cv_export_date():
    """Get the date suffix from the most recent Clinic Visits CSV file."""
    from config.settings import DATA_INCREMENTAL
    from pathlib import Path
    folder = DATA_INCREMENTAL / "ClinicVisits"
    dates = []
    for f in folder.glob("Clinic Visits_*.csv"):
        suffix = f.stem[len("Clinic Visits") + 1:]
        try:
            dates.append(int(suffix))
        except ValueError:
            continue
    if not dates:
        return None
    latest = str(max(dates))
    return pd.Timestamp(f"{latest[:4]}-{latest[4:6]}-{latest[6:8]}")


# ---------------------------------------------------------------------------
# Filter Bar
# ---------------------------------------------------------------------------

def _build_cv_filter_bar():
    """Build the workflow-style two-row filter bar for clinic visits."""
    return dmc.Paper(
        children=[
            # Row 1: data filters
            dmc.Group(
                children=[
                    department_chips("cv"),
                    # Physician dropdown
                    html.Div(
                        children=[
                            html.Div(
                                children=[
                                    dmc.Button(
                                        "Physician",
                                        id="cv-physician-trigger",
                                        variant="default",
                                        size="sm",
                                        rightSection=DashIconify(icon="mdi:chevron-down", width=14),
                                    ),
                                    dmc.ActionIcon(
                                        DashIconify(icon="mdi:close-circle", width=18),
                                        id="cv-physician-clear",
                                        variant="subtle",
                                        color="gray",
                                        size="sm",
                                        className="wf-filter-clear-btn",
                                    ),
                                ],
                                style={"position": "relative", "display": "inline-block"},
                            ),
                            dmc.Paper(
                                id="cv-physician-panel",
                                children=[
                                    dmc.ChipGroup(
                                        children=[],
                                        id="cv-filter-physician",
                                        multiple=True,
                                        value=[],
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
                                        id="cv-body-system-trigger",
                                        variant="default",
                                        size="sm",
                                        rightSection=DashIconify(icon="mdi:chevron-down", width=14),
                                    ),
                                    dmc.ActionIcon(
                                        DashIconify(icon="mdi:close-circle", width=18),
                                        id="cv-body-system-clear",
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
                                    id="cv-filter-body-system",
                                    multiple=True,
                                    value=[],
                                ),
                                id="cv-body-system-panel",
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
                    # Visit Category (from ActivityName mapping)
                    html.Div(
                        children=[
                            html.Div(
                                children=[
                                    dmc.Button(
                                        "Category: All",
                                        id="cv-visit-type-trigger",
                                        variant="default",
                                        size="sm",
                                        rightSection=DashIconify(icon="mdi:chevron-down", width=14),
                                    ),
                                ],
                                style={"position": "relative", "display": "inline-block"},
                            ),
                            dmc.Paper(
                                dmc.ChipGroup(
                                    children=[
                                        dmc.Chip(v, value=v, size="xs", variant="filled")
                                        for v in VISIT_CATEGORIES
                                    ],
                                    id="cv-filter-visit-type",
                                    multiple=False,
                                    value="All",
                                ),
                                id="cv-visit-type-panel",
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
                    # Classified Type (duration/notes reclassification: consult vs follow-up)
                    html.Div(
                        children=[
                            html.Div(
                                children=[
                                    dmc.Button(
                                        "Type: All",
                                        id="cv-classified-type-trigger",
                                        variant="default",
                                        size="sm",
                                        rightSection=DashIconify(icon="mdi:chevron-down", width=14),
                                    ),
                                ],
                                style={"position": "relative", "display": "inline-block"},
                            ),
                            dmc.Paper(
                                dmc.ChipGroup(
                                    children=[
                                        dmc.Chip("All", value="All", size="xs", variant="filled"),
                                        dmc.Chip("Consult", value="Consult", size="xs", variant="filled"),
                                        dmc.Chip("Follow-Up", value="Follow-Up", size="xs", variant="filled"),
                                    ],
                                    id="cv-filter-classified-type",
                                    multiple=False,
                                    value="All",
                                ),
                                id="cv-classified-type-panel",
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
                    # Hidden status store — exclude cancelled/deleted/future-open
                    dcc.Store(id="cv-filter-status", data="Attended"),
                    # Inpatient
                    dmc.Switch(
                        id="cv-inpatient-switch",
                        label="Inpatient",
                        size="xs",
                        checked=False,
                    ),
                    # Weekend / Holiday
                    dmc.Switch(
                        id="cv-weekend-switch",
                        label="Weekend",
                        size="xs",
                        checked=False,
                    ),
                    # Smoothing
                    dmc.Group(
                        children=[
                            dmc.Text("Smoothing", size="xs", c="#6B7280", fw=500),
                            dmc.Slider(
                                id="cv-smooth-slider",
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
                    # Outlier caps
                    outlier_panel("cv", transitions=[
                        ("Booking Lead Time", _LEAD_MAX),
                        ("Consult \u2192 Sim", _DAYS_TO_SIM_MAX),
                    ]),
                ],
                gap="md",
                wrap="wrap",
                align="center",
            ),
            # Row 2: date controls
            dmc.Group(
                children=[
                    dmc.Select(
                        id="cv-filter-date-preset",
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
                            id="cv-filter-daterange",
                            display_format="MMM D, YYYY",
                            start_date_placeholder_text="Start",
                            end_date_placeholder_text="End",
                            clearable=True,
                            number_of_months_shown=2,
                            minimum_nights=0,
                            start_date=idx_to_date(preset_to_slider_val(_DEFAULT_DATE_PRESET, MAX_IDX)[0]).strftime("%Y-%m-%d"),
                            end_date=min(
                                idx_to_date(preset_to_slider_val(_DEFAULT_DATE_PRESET, MAX_IDX)[1], end_of_month=True),
                                pd.Timestamp.now().normalize(),
                            ).strftime("%Y-%m-%d"),
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
                            html.Div(id="cv-date-range-label", style={"display": "none"}),
                            dmc.RangeSlider(
                                id="cv-date-slider",
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
                dmc.Title("Clinic Visits", order=2, className="page-title", style={"margin": 0, "textAlign": "center"}),
                _build_cv_filter_bar(),
            ],
        ),

        # KPI row — 6 cards with sparklines
        dmc.Grid(id="cv-kpi-row", gutter="md", children=[
            dmc.GridCol(kpi_placeholder(), id="cv-kpi-total", span={"base": 12, "sm": 6, "md": 2}),
            dmc.GridCol(kpi_placeholder(), id="cv-kpi-consults", span={"base": 12, "sm": 6, "md": 2}),
            dmc.GridCol(kpi_placeholder(), id="cv-kpi-followups", span={"base": 12, "sm": 6, "md": 2}),
            dmc.GridCol(kpi_placeholder(), id="cv-kpi-lead-time", span={"base": 12, "sm": 6, "md": 2}),
            dmc.GridCol(kpi_placeholder(), id="cv-kpi-sim-conversion", span={"base": 12, "sm": 6, "md": 2}),
            dmc.GridCol(kpi_placeholder(), id="cv-kpi-days-to-sim", span={"base": 12, "sm": 6, "md": 2}),
        ]),

        # Row 1: Visit Volume Trend + Cumulative (half-width each)
        dmc.Grid(gutter="md", children=[
            dmc.GridCol(
                chart_card(
                    "cv-chart-volume",
                    "Visit Volume Trend",
                    settings_id="cv-volume",
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
                            id="cv-volume-slice",
                            data=[
                                {"value": "", "label": "Total"},
                                {"value": "category", "label": "Category"},
                                {"value": "type", "label": "Type"},
                                {"value": "physician", "label": "MD"},
                                {"value": "site", "label": "Site"},
                                {"value": "diagnosis", "label": "Dx"},
                            ],
                            value="category",
                            size="xs",
                        ),
                    ],
                    extra_controls=[
                        dmc.SegmentedControl(
                            id="cv-volume-agg",
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
                    "cv-chart-cumulative",
                    "Cumulative Visit Volume",
                    settings_id="cv-cumulative",
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
                    smooth_default=0.15,
                    slider_label="Smoothing",
                    paper_padding="md",
                    extra_controls=[
                        dmc.SegmentedControl(
                            id="cv-cumulative-mode",
                            data=[
                                {"value": "prior", "label": "Prior Periods"},
                                {"value": "slice", "label": "Slice By"},
                            ],
                            value="prior",
                            size="xs",
                        ),
                        dmc.SegmentedControl(
                            id="cv-cumulative-period-type",
                            data=[
                                {"value": "calendar", "label": "Calendar"},
                                {"value": "rolling", "label": "Rolling"},
                            ],
                            value="calendar",
                            size="xs",
                        ),
                        dmc.SegmentedControl(
                            id="cv-cumulative-slice",
                            data=[
                                {"value": "total", "label": "Total"},
                                {"value": "category", "label": "Category"},
                                {"value": "type", "label": "Type"},
                                {"value": "physician", "label": "MD"},
                                {"value": "site", "label": "Site"},
                                {"value": "diagnosis", "label": "Dx"},
                            ],
                            value="total",
                            size="xs",
                            orientation="horizontal",
                            style={"display": "none"},
                        ),
                    ],
                ),
                span={"base": 12, "md": 6},
            ),
        ]),

        # Row 2: Lead Time (half) + Conversion Rate (half)
        dmc.Grid(gutter="md", children=[
            dmc.GridCol(
                chart_card(
                    "cv-chart-lead-time",
                    "Lead Time Trend (median days)",
                    settings_id="cv-lead",
                    chart_types=[
                        {"value": "line", "label": "Line"},
                        {"value": "area", "label": "Area"},
                        {"value": "bar", "label": "Bar"},
                    ],
                    show_smooth=True,
                    smooth_max=6,
                    smooth_default=1,
                    show_grouping=False,
                    paper_padding="md",
                    extra_controls_left=[
                        dmc.SegmentedControl(
                            id="cv-lead-slice",
                            data=[
                                {"value": "", "label": "Total"},
                                {"value": "category", "label": "Category"},
                                {"value": "type", "label": "Type"},
                                {"value": "physician", "label": "MD"},
                                {"value": "site", "label": "Site"},
                            ],
                            value="site",
                            size="xs",
                        ),
                    ],
                    extra_controls=[
                        dmc.SegmentedControl(
                            id="cv-lead-agg",
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
                    "cv-chart-conversion",
                    "Consult \u2192 Sim Conversion Rate",
                    settings_id="cv-conversion",
                    chart_types=[
                        {"value": "line", "label": "Line"},
                        {"value": "area", "label": "Area"},
                        {"value": "bar", "label": "Bar"},
                    ],
                    show_smooth=True,
                    smooth_max=6,
                    smooth_default=1,
                    show_grouping=False,
                    paper_padding="md",
                    extra_controls_left=[
                        dmc.SegmentedControl(
                            id="cv-conversion-slice",
                            data=[
                                {"value": "", "label": "Total"},
                                {"value": "category", "label": "Category"},
                                {"value": "type", "label": "Type"},
                                {"value": "physician", "label": "MD"},
                                {"value": "site", "label": "Site"},
                            ],
                            value="",
                            size="xs",
                        ),
                    ],
                    extra_controls=[
                        dmc.SegmentedControl(
                            id="cv-conversion-agg",
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
        ]),

        # Row 3: Cancellation Rate (1/3) + Diagnosis Mix (1/3) + Billing (1/3)
        dmc.Grid(gutter="md", children=[
            dmc.GridCol(
                chart_card(
                    "cv-chart-cancel-rate",
                    "Cancellation Rate",
                    settings_id="cv-cancel",
                    paper_height=CHART_PAPER_HEIGHT_SM,
                    chart_types=[
                        {"value": "line", "label": "Line"},
                        {"value": "area", "label": "Area"},
                        {"value": "bar", "label": "Bar"},
                    ],
                    show_smooth=True,
                    smooth_max=12,
                    smooth_default=1,
                    show_grouping=False,
                    extra_controls_left=[
                        dmc.SegmentedControl(
                            id="cv-cancel-slice",
                            data=[
                                {"value": "", "label": "Total"},
                                {"value": "type", "label": "Type"},
                                {"value": "site", "label": "Site"},
                            ],
                            value="",
                            size="xs",
                        ),
                    ],
                    extra_controls=[
                        dmc.SegmentedControl(
                            id="cv-cancel-agg",
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
                                        id="cv-diagnosis-compare",
                                        data=[
                                            {"value": "off", "label": "Current"},
                                            {"value": "prior", "label": "vs Prior"},
                                        ],
                                        value="off",
                                        size="xs",
                                    ),
                                    dmc.SegmentedControl(
                                        id="cv-diagnosis-slice",
                                        data=[
                                            {"value": "", "label": "Total"},
                                            {"value": "category", "label": "Category"},
                                            {"value": "type", "label": "Type"},
                                            {"value": "physician", "label": "MD"},
                                            {"value": "site", "label": "Site"},
                                        ],
                                        value="",
                                        size="xs",
                                    ),
                                    dmc.SegmentedControl(
                                        id="cv-diagnosis-mode",
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
                                    "cv-diagnosis",
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
                                        dmc.LoadingOverlay(id="cv-diagnosis-loading", visible=False, loaderProps={"type": "dots", "color": "#7C2A83"}),
                                        dcc.Graph(id="cv-chart-diagnosis", config={"displayModeBar": False}, style={"height": "100%"}),
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
                                dmc.Group(gap="xs", wrap="nowrap", align="center", children=[
                                    dmc.Text("Billing", size="sm", fw=500, c="#6B7280"),
                                    dmc.SegmentedControl(
                                        id="cv-billing-slice",
                                        data=[
                                            {"value": "", "label": "Total"},
                                            {"value": "physician", "label": "MD"},
                                            {"value": "site", "label": "Site"},
                                        ],
                                        value="physician",
                                        size="xs",
                                    ),
                                    dmc.SegmentedControl(
                                        id="cv-billing-group",
                                        data=[
                                            {"value": "new", "label": "New"},
                                            {"value": "established", "label": "Established"},
                                            {"value": "inpatient", "label": "Inpatient"},
                                            {"value": "telehealth", "label": "Telehealth"},
                                        ],
                                        value="new",
                                        size="xs",
                                    ),
                                    dmc.SegmentedControl(
                                        id="cv-billing-mode",
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
                                    "cv-billing",
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
                                        dmc.LoadingOverlay(id="cv-billing-loading", visible=False, loaderProps={"type": "dots", "color": "#7C2A83"}),
                                        dcc.Graph(id="cv-chart-billing", config={"displayModeBar": False}, style={"height": "100%"}),
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
        detail_table("cv-detail-grid", title="Visit Details", export_id="cv-table-export"),

        dcc.Interval(id="cv-interval", interval=300_000, n_intervals=0),

        # Stores for clientside rendering
        dcc.Store(id="cv-store-volume"),
        dcc.Store(id="cv-store-lead"),
        dcc.Store(id="cv-lead-settings-stack", data="stacked"),
        dcc.Store(id="cv-store-conversion"),
        dcc.Store(id="cv-conversion-settings-stack", data="stacked"),
        dcc.Store(id="cv-store-cumulative"),
        dcc.Store(id="cv-store-cancel"),
        dcc.Store(id="cv-cancel-settings-stack", data="stacked"),
        dcc.Store(id="cv-store-kpi-sparklines"),
        dcc.Store(id="cv-filter-options"),
        html.Div(id="cv-filter-options-applier", style={"display": "none"}),
    ],
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

import re as _re

_FOLLOWUP_RE = _re.compile(r'follow[\s-]?up|re[\s-]?eval|followup|reeval', _re.IGNORECASE)
_EXPLICIT_FOLLOWUP_RE = _re.compile(
    r'\bphone\b|\btelephone\b|follow[\s-]?up|f/u|re[\s-]?eval|reeval', _re.IGNORECASE
)
_CONTEXT_FOLLOWUP_RE = _re.compile(r'review|discuss|go\s+over', _re.IGNORECASE)
_NEW_PATIENT_RE = _re.compile(r'working\s+chart|bookmarked', _re.IGNORECASE)
_STANDARD_CONSULT_NAMES = {'Consult', 'Consult - Special request', 'Consult- ADD ON'}


def _classify_visit_type(row):
    """Classify a visit as Consult / Follow-Up / Virtual based on duration,
    activity name, and appointment notes.

    Ported from archive/data/loader.py classify_appointment_type.
    Uses columns: ActivityName, DurationMinutes, AppointmentNotes.

    Decision tree (from legacy-logic.md):
    1. ActivityName = "Re-eval" or "Follow-Up" → Follow-Up
    2. Duration > 60 min → Consult
    3. Standard consult names → Consult, unless notes mention follow-up
    4. "Virtual Consult/Follow Up":
       - <60 min: note keywords decide; default Follow-Up
       - =60 min: note keywords decide; default Consult
       - unknown duration: note keywords decide; default Consult
    5. Fallback → Other
    """
    activity_name = str(row.get("ActivityName", "")).strip() if pd.notna(row.get("ActivityName")) else ""
    name_lower = activity_name.lower()

    # Explicit Follow-Up or Re-eval activity names
    if name_lower == "follow-up" or "re-eval" in name_lower or "reeval" in name_lower:
        return "Follow-Up"

    duration = pd.to_numeric(row.get("DurationMinutes"), errors="coerce")
    notes = str(row.get("AppointmentNotes", "")) if pd.notna(row.get("AppointmentNotes")) else ""

    # Rule 1: >60 minutes → Consult
    if pd.notna(duration) and duration > 60:
        return "Consult"

    # Rule 2: Standard consult names
    if activity_name in _STANDARD_CONSULT_NAMES:
        if _FOLLOWUP_RE.search(notes):
            return "Follow-Up"
        return "Consult"

    # Rule 3: Virtual Consult/Follow Up
    if "virtual" in name_lower or "tele" in name_lower:
        if pd.notna(duration) and 0 < duration < 60:
            if _EXPLICIT_FOLLOWUP_RE.search(notes):
                return "Follow-Up"
            if _CONTEXT_FOLLOWUP_RE.search(notes):
                return "Follow-Up"
            if _NEW_PATIENT_RE.search(notes):
                return "Consult"
            return "Follow-Up"  # conservative default
        elif pd.notna(duration) and duration == 60:
            if _FOLLOWUP_RE.search(notes):
                return "Follow-Up"
            return "Consult"
        else:
            if _FOLLOWUP_RE.search(notes):
                return "Follow-Up"
            return "Virtual"

    # Rule 4: Any other consult-like name
    if "consult" in name_lower:
        return "Consult"

    return "Other"


def _diag_period_label(p_start, p_end, date_preset=None):
    """Smart period label — mirrors cumulative chart's _period_label logic."""
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


def _get_date_range(slider_val, daterange):
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


def _build_diag_code_to_body_system(diag_lookup):
    """Build a DiagnosisCode → category dict from the lookup table."""
    return build_code_to_category(diag_lookup)


def _get_body_systems_for_rows(df, c2b):
    """For each row, extract categories from comma-separated DiagnosisCodes."""
    if "DiagnosisCodes" not in df.columns or not c2b:
        return pd.Series(dtype=object, index=df.index)
    return df["DiagnosisCodes"].apply(
        lambda s: get_categories_for_codes(s, c2b) if pd.notna(s) else set()
    )


def _apply_cv_filters(df, departments, physician, body_systems, visit_type,
                       status, inpatient, c2b, classified_type=None, skip=None):
    """Apply all dimension filters except the one named by `skip`."""
    d = df
    if skip != "department" and departments and "Department" in d.columns:
        d = d[d["Department"].isin(departments)]
    if skip != "physician" and physician and "AppointmentPhysician" in d.columns:
        d = d[d["AppointmentPhysician"].isin(physician)]
    if skip != "body_system" and body_systems and "DiagnosisCodes" in d.columns and c2b:
        bs_set = set(body_systems)
        row_bs = _get_body_systems_for_rows(d, c2b)
        d = d[row_bs.apply(lambda s: bool(s & bs_set))]
    if skip != "visit_type" and visit_type and visit_type != "All" and "VisitCategory" in d.columns:
        d = d[d["VisitCategory"] == visit_type]
    if skip != "classified_type" and classified_type and classified_type != "All" and "VisitType" in d.columns:
        d = d[d["VisitType"] == classified_type]
    if skip != "status" and status and status != "All" and "Status" in d.columns:
        if status == "Attended":
            # Exclude cancelled, no-shows, deleted, and future open
            _EXCLUDE_STATUSES = {"Cancelled", "Cancelled - Patient No-Show", "Deleted"}
            d = d[~d["Status"].isin(_EXCLUDE_STATUSES)]
            export_date = _get_cv_export_date()
            if export_date is not None:
                future_open = (
                    (d["Status"] == "Open")
                    & (d["ScheduledDateTime"].dt.normalize() >= export_date)
                )
                d = d[~future_open]
        else:
            d = d[d["Status"].str.contains(status, case=False, na=False)]
    if skip != "inpatient" and inpatient and "InPatientFlag" in d.columns:
        d = d[d["InPatientFlag"].str.upper() == "YES"]
    return d


def _compute_cv_available_options(df, departments, physician, body_systems,
                                   visit_type, status, inpatient, c2b,
                                   classified_type=None):
    """Cross-filter: for each dimension, apply all OTHER filters and return available values."""
    # Department options
    d_nd = _apply_cv_filters(df, departments, physician, body_systems,
                              visit_type, status, inpatient, c2b,
                              classified_type=classified_type, skip="department")
    dept_opts = sorted(d_nd["Department"].dropna().unique().tolist()) if "Department" in d_nd.columns else []

    # Physician options
    d_np = _apply_cv_filters(df, departments, physician, body_systems,
                              visit_type, status, inpatient, c2b,
                              classified_type=classified_type, skip="physician")
    phys_opts = sorted(d_np["AppointmentPhysician"].dropna().unique().tolist()) if "AppointmentPhysician" in d_np.columns else []

    # Body system options
    d_nb = _apply_cv_filters(df, departments, physician, body_systems,
                              visit_type, status, inpatient, c2b,
                              classified_type=classified_type, skip="body_system")
    bs_opts = []
    if c2b and "DiagnosisCodes" in d_nb.columns:
        all_bs = set()
        for val in d_nb["DiagnosisCodes"].dropna():
            for code in str(val).split(","):
                b = c2b.get(code.strip(), "")
                if b:
                    all_bs.add(b)
        bs_opts = sorted(all_bs)

    return {
        "_prefix": "cv",
        "departments": dept_opts,
        "physicians": phys_opts,
        "bodySystems": bs_opts,
    }


# ---------------------------------------------------------------------------
# Filter Callbacks
# ---------------------------------------------------------------------------

def _register_cv_filter_callbacks():
    """Register all filter-sync callbacks for the clinic visits page."""

    # A) Preset → Slider + DatePicker
    @callback(
        Output("cv-date-slider", "value"),
        Output("cv-filter-daterange", "start_date", allow_duplicate=True),
        Output("cv-filter-daterange", "end_date", allow_duplicate=True),
        Input("cv-filter-date-preset", "value"),
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
        ClientsideFunction(namespace="cvDateSlider", function_name="syncSlider"),
        Output("cv-filter-daterange", "start_date", allow_duplicate=True),
        Output("cv-filter-daterange", "end_date", allow_duplicate=True),
        Output("cv-date-range-label", "children"),
        Input("cv-date-slider", "value"),
        State("cv-filter-daterange", "start_date"),
        State("cv-filter-daterange", "end_date"),
        prevent_initial_call=True,
    )

    # C) DatePicker → Slider
    @callback(
        Output("cv-date-slider", "value", allow_duplicate=True),
        Input("cv-filter-daterange", "start_date"),
        Input("cv-filter-daterange", "end_date"),
        State("cv-date-slider", "value"),
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
        Output("cv-filter-date-preset", "value", allow_duplicate=True),
        Input("cv-date-slider", "value"),
        State("cv-filter-date-preset", "value"),
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
        """function(vals) {
            if (!vals || vals.length === 0) return "Physician";
            if (vals.length === 1) return vals[0].split(", ")[0];
            return vals.length + " selected";
        }""",
        Output("cv-physician-trigger", "children"),
        Input("cv-filter-physician", "value"),
    )
    clientside_callback(
        """function(vals) {
            if (!vals || vals.length === 0) return "Diagnosis";
            if (vals.length === 1) return vals[0];
            return vals.length + " selected";
        }""",
        Output("cv-body-system-trigger", "children"),
        Input("cv-filter-body-system", "value"),
    )

    # --- Clear-button visibility ---
    clientside_callback(
        """function(vals) { return vals && vals.length > 0 ? {"display": "inline-flex"} : {"display": "none"}; }""",
        Output("cv-physician-clear", "style"),
        Input("cv-filter-physician", "value"),
    )
    clientside_callback(
        """function(vals) { return vals && vals.length > 0 ? {"display": "inline-flex"} : {"display": "none"}; }""",
        Output("cv-body-system-clear", "style"),
        Input("cv-filter-body-system", "value"),
    )

    # --- Clear-button actions ---
    clientside_callback(
        """function(n) { return []; }""",
        Output("cv-filter-physician", "value", allow_duplicate=True),
        Input("cv-physician-clear", "n_clicks"),
        prevent_initial_call=True,
    )
    clientside_callback(
        """function(n) { return []; }""",
        Output("cv-filter-body-system", "value", allow_duplicate=True),
        Input("cv-body-system-clear", "n_clicks"),
        prevent_initial_call=True,
    )



# Register filter callbacks
_register_cv_filter_callbacks()


# ---------------------------------------------------------------------------
# Physician filter — dynamic from data
# ---------------------------------------------------------------------------
@callback(
    Output("cv-filter-physician", "children"),
    Input("cv-interval", "n_intervals"),
)
def _populate_cv_physician_chips(_n):
    from data.loader import load_clinic_visits
    try:
        df = load_clinic_visits()
    except Exception:
        return []
    if df.empty or "AppointmentPhysician" not in df.columns:
        return []
    from components.filter_bar import physician_options, physician_short_name
    return [
        dmc.Chip(physician_short_name(opt["label"]), value=opt["value"], size="xs", variant="filled")
        for opt in physician_options(df["AppointmentPhysician"])
    ]


# ---------------------------------------------------------------------------
# Shared data loading/filtering helper
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
        s - pd.DateOffset(months=1),
        e - pd.DateOffset(months=1),
    )),
    "last_month": ("vs month before", lambda s, e: (
        s - pd.DateOffset(months=1),
        s - pd.Timedelta(days=1),
    )),
}


def _cv_trend(curr, prior, invert=False):
    if prior is None or prior == 0:
        return None, None
    pct = (curr - prior) / abs(prior) * 100
    direction = ("down" if pct > 0 else "up") if invert else ("up" if pct > 0 else "down")
    return f"{abs(pct):.0f}%", direction


def _load_and_filter_cv(slider_val, departments, physician, body_systems,
                         visit_type, classified_type, status, inpatient,
                         weekend_only, date_preset, outlier_enabled,
                         outlier_cap_0, outlier_cap_1):
    """Load clinic visits data, classify, filter, and return shared context.

    Returns a dict with keys: df_all, dff, dff_all_status, dff_prior, c2b,
    start, end, date_preset, trend_label, lead_max, days_to_sim_max,
    filter_options.  Returns None if data is empty.
    """
    from data.loader import load_clinic_visits, load_diagnosis

    if not outlier_enabled:
        lead_max = 365
        days_to_sim_max = 365
    else:
        lead_max = outlier_cap_0 or _LEAD_MAX
        days_to_sim_max = outlier_cap_1 or _DAYS_TO_SIM_MAX

    try:
        df = load_clinic_visits().copy()
    except Exception:
        return None

    if df.empty:
        return None

    # Classify visit types
    if "ActivityName" in df.columns:
        df["VisitType"] = df.apply(_classify_visit_type, axis=1)
        df["VisitCategory"] = df["ActivityName"].map(_ACTIVITY_TO_CATEGORY).fillna("Other")
    else:
        df["VisitType"] = "Other"
        df["VisitCategory"] = "Other"

    # Diagnosis lookup
    try:
        diag_df = load_diagnosis()
    except Exception:
        diag_df = None
    c2b = _build_diag_code_to_body_system(diag_df)

    # Date range from slider
    start, end = _get_date_range(slider_val, None)

    # Weekend / holiday filter (before date slicing)
    if weekend_only and "ScheduledDateTime" in df.columns:
        holidays = _get_cv_holidays()
        is_wk = df["ScheduledDateTime"].dt.dayofweek >= 5
        is_hol = df["ScheduledDateTime"].dt.normalize().isin(holidays)
        df = df[is_wk | is_hol]
        if df.empty:
            return None

    df_all = df.copy()

    # Date filter
    if "ScheduledDateTime" in df.columns:
        df = df[
            (df["ScheduledDateTime"] >= start)
            & (df["ScheduledDateTime"] <= end)
        ]
    if df.empty:
        return None

    # Cross-filter options BEFORE dimension filters
    filter_options = _compute_cv_available_options(
        df, departments, physician, body_systems,
        visit_type, status, inpatient, c2b,
        classified_type=classified_type,
    )

    # Apply dimension filters
    dff = _apply_cv_filters(
        df, departments, physician, body_systems,
        visit_type, status, inpatient, c2b,
        classified_type=classified_type,
    )

    # Cancel rate needs all-status filtered frame
    dff_all_status = _apply_cv_filters(
        df, departments, physician, body_systems,
        visit_type, "All", inpatient, c2b,
        classified_type=classified_type,
    )

    # Prior-period comparison
    trend_label = None
    dff_prior = pd.DataFrame()
    if date_preset and date_preset in _PRIOR_MAP and "ScheduledDateTime" in df_all.columns:
        trend_label, prior_fn = _PRIOR_MAP[date_preset]
        prior_start, prior_end = prior_fn(start, end)
        df_prior = df_all[
            (df_all["ScheduledDateTime"] >= prior_start)
            & (df_all["ScheduledDateTime"] <= prior_end)
        ]
        dff_prior = _apply_cv_filters(
            df_prior, departments, physician, body_systems,
            visit_type, status, inpatient, c2b,
            classified_type=classified_type,
        )

    return {
        "df_all": df_all, "dff": dff, "dff_all_status": dff_all_status,
        "dff_prior": dff_prior, "c2b": c2b,
        "start": start, "end": end, "date_preset": date_preset,
        "trend_label": trend_label, "lead_max": lead_max,
        "days_to_sim_max": days_to_sim_max, "filter_options": filter_options,
        "departments": departments,
    }


# Common filter inputs shared by all split callbacks
_CV_FILTER_INPUTS = [
    Input("cv-interval", "n_intervals"),
    Input("cv-date-slider", "value"),
    Input("cv-filter-department", "value"),
    Input("cv-filter-physician", "value"),
    Input("cv-filter-body-system", "value"),
    Input("cv-filter-visit-type", "value"),
    Input("cv-filter-classified-type", "value"),
    Input("cv-filter-status", "value"),
    Input("cv-inpatient-switch", "checked"),
    Input("cv-weekend-switch", "checked"),
    Input("cv-filter-date-preset", "value"),
    Input("cv-outlier-enabled", "data"),
    Input("cv-outlier-cap-0", "value"),
    Input("cv-outlier-cap-1", "value"),
]


def _unpack_filter_args(args):
    """Unpack the 14 common filter args into a dict for _load_and_filter_cv."""
    (_n, slider_val, departments, physician, body_systems,
     visit_type, classified_type, status, inpatient,
     weekend_only, date_preset, outlier_enabled,
     outlier_cap_0, outlier_cap_1) = args[:14]
    return dict(
        slider_val=slider_val, departments=departments, physician=physician,
        body_systems=body_systems, visit_type=visit_type,
        classified_type=classified_type, status=status, inpatient=inpatient,
        weekend_only=weekend_only, date_preset=date_preset,
        outlier_enabled=outlier_enabled, outlier_cap_0=outlier_cap_0,
        outlier_cap_1=outlier_cap_1,
    )


# ---------------------------------------------------------------------------
# Callback 1: KPIs + Sparklines + Filter Options + Detail Table
# ---------------------------------------------------------------------------

@callback(
    Output("cv-kpi-total", "children"),
    Output("cv-kpi-consults", "children"),
    Output("cv-kpi-followups", "children"),
    Output("cv-kpi-lead-time", "children"),
    Output("cv-kpi-sim-conversion", "children"),
    Output("cv-kpi-days-to-sim", "children"),
    Output("cv-store-kpi-sparklines", "data"),
    Output("cv-filter-options", "data"),
    Output("cv-detail-grid", "rowData"),
    Output("cv-detail-grid", "columnDefs"),
    *_CV_FILTER_INPUTS,
)
def _update_cv_kpis(*args):
    ctx = _unpack_filter_args(args)
    data = _load_and_filter_cv(**ctx)

    na_kpi = kpi_card("--", "N/A")
    empty_kpis = (na_kpi,) * 6 + ({}, None, [], [])
    if data is None:
        return empty_kpis

    dff = data["dff"]
    if dff.empty:
        return (na_kpi,) * 6 + ({}, data["filter_options"], [], [])

    dff_prior = data["dff_prior"]
    trend_label = data["trend_label"]
    lead_max = data["lead_max"]
    days_to_sim_max = data["days_to_sim_max"]
    c2b = data["c2b"]
    start, end = data["start"], data["end"]

    sparkline_data = {}
    total_visits = len(dff)
    consult_count = len(dff[dff["VisitType"] == "Consult"]) if "VisitType" in dff.columns else 0
    followup_count = len(dff[dff["VisitType"] == "Follow-Up"]) if "VisitType" in dff.columns else 0

    range_months = (end.year - start.year) * 12 + (end.month - start.month) + 1
    _spark_period = "D" if range_months <= 3 else "W"

    # Build visit count sparklines
    if "ScheduledDateTime" in dff.columns:
        dff_temp = dff.copy()
        if _spark_period == "D":
            dff_temp["_sp"] = dff_temp["ScheduledDateTime"].dt.normalize()
        else:
            dff_temp["_sp"] = dff_temp["ScheduledDateTime"].dt.to_period("W").dt.to_timestamp()
        grp = dff_temp.groupby("_sp").size()
        if len(grp) > 2:
            sparkline_data["total"] = {
                "labels": [d.isoformat() for d in grp.index],
                "values": grp.tolist(),
                "color": PRIMARY,
            }
        consults_grp = dff_temp[dff_temp["VisitType"] == "Consult"].groupby("_sp").size()
        if len(consults_grp) > 2:
            sparkline_data["consults"] = {
                "labels": [d.isoformat() for d in consults_grp.index],
                "values": consults_grp.tolist(),
                "color": CHART_COLORWAY[0],
            }
        followups_grp = dff_temp[dff_temp["VisitType"] == "Follow-Up"].groupby("_sp").size()
        if len(followups_grp) > 2:
            sparkline_data["followups"] = {
                "labels": [d.isoformat() for d in followups_grp.index],
                "values": followups_grp.tolist(),
                "color": CHART_COLORWAY[1],
            }

    # Prior-period trends
    _t_total = (None, None)
    _t_consult = (None, None)
    _t_followup = (None, None)
    if trend_label and not dff_prior.empty:
        prior_total = len(dff_prior)
        _t_total = _cv_trend(total_visits, prior_total)
        if "VisitType" in dff_prior.columns:
            _t_consult = _cv_trend(consult_count, len(dff_prior[dff_prior["VisitType"] == "Consult"]))
            _t_followup = _cv_trend(followup_count, len(dff_prior[dff_prior["VisitType"] == "Follow-Up"]))

    kpi_total = kpi_card(
        "Total Visits", f"{total_visits:,}", accent_color=PRIMARY, sparkline_id="cv-spark-total",
        trend_text=f"{_t_total[0]} {trend_label}" if _t_total[0] else None, trend_direction=_t_total[1],
    )
    kpi_consults = kpi_card(
        "Consults", f"{consult_count:,}", accent_color=CHART_COLORWAY[0], sparkline_id="cv-spark-consults",
        trend_text=f"{_t_consult[0]} {trend_label}" if _t_consult[0] else None, trend_direction=_t_consult[1],
    )
    kpi_followups = kpi_card(
        "Follow-Ups", f"{followup_count:,}", accent_color=CHART_COLORWAY[1], sparkline_id="cv-spark-followups",
        trend_text=f"{_t_followup[0]} {trend_label}" if _t_followup[0] else None, trend_direction=_t_followup[1],
    )

    # Lead time KPI
    lead_vals = pd.Series(dtype=float)
    if "DaysFromCreatedToAppt" in dff.columns:
        _lv = pd.to_numeric(dff["DaysFromCreatedToAppt"], errors="coerce").dropna()
        lead_vals = _lv[(_lv >= 0) & (_lv <= lead_max)]
        lead_time_str = f"{lead_vals.median():.0f}" if len(lead_vals) > 0 else "N/A"
    else:
        lead_time_str = "N/A"

    if "DaysFromCreatedToAppt" in dff.columns and "ScheduledDateTime" in dff.columns:
        lt = dff[["ScheduledDateTime", "DaysFromCreatedToAppt"]].copy()
        lt["val"] = pd.to_numeric(lt["DaysFromCreatedToAppt"], errors="coerce")
        lt = lt.dropna(subset=["val"])
        lt = lt[(lt["val"] >= 0) & (lt["val"] <= lead_max)]
        if _spark_period == "D":
            lt["_sp"] = lt["ScheduledDateTime"].dt.normalize()
        else:
            lt["_sp"] = lt["ScheduledDateTime"].dt.to_period("W").dt.to_timestamp()
        lt_grp = lt.groupby("_sp")["val"].median()
        if len(lt_grp) > 2:
            sparkline_data["lead_time"] = {
                "labels": [d.isoformat() for d in lt_grp.index],
                "values": lt_grp.tolist(),
                "color": CHART_COLORWAY[2],
                "hover_fmt": "%{x|%b %d}: %{customdata:,.1f} days<extra></extra>",
            }

    _t_lead = (None, None)
    if trend_label and not dff_prior.empty and "DaysFromCreatedToAppt" in dff_prior.columns:
        _plv = pd.to_numeric(dff_prior["DaysFromCreatedToAppt"], errors="coerce").dropna()
        prior_lead = _plv[(_plv >= 0) & (_plv <= lead_max)]
        if len(prior_lead) > 0 and len(lead_vals) > 0:
            _t_lead = _cv_trend(lead_vals.median(), prior_lead.median(), invert=True)

    _lead_info = dmc.Tooltip(
        dmc.Group(gap=2, children=[
            DashIconify(icon="mdi:information-outline", width=16, color="#9CA3AF", style={"cursor": "help"}),
        ]),
        label=f"Median booking lead time. Excludes values >{lead_max} days to filter purposeful waits and delays.",
        position="top", withArrow=True, multiline=True, w=240,
    )
    kpi_lead = kpi_card(
        "Lead Time (median days)", lead_time_str, accent_color=CHART_COLORWAY[2], sparkline_id="cv-spark-lead",
        trend_text=f"{_t_lead[0]} {trend_label}" if _t_lead[0] else None, trend_direction=_t_lead[1],
        header_control=_lead_info,
    )

    # Sim conversion KPI
    consults_df = dff[dff["VisitType"] == "Consult"] if "VisitType" in dff.columns else pd.DataFrame()
    sim_rate = None
    sim_rate_str = "N/A"
    if "SimulationStatus" in consults_df.columns and len(consults_df) > 0:
        _sim_status = consults_df["SimulationStatus"].str.lower().str.strip()
        has_sim = _sim_status.isin(["completed", "scheduled"])
        if "DaysToSimulation" in consults_df.columns:
            days_val = pd.to_numeric(consults_df["DaysToSimulation"], errors="coerce")
            has_sim = has_sim & (days_val.fillna(999) <= 180)
        sim_rate = has_sim.mean() * 100
        sim_rate_str = f"{sim_rate:.1f}%"

    if "SimulationStatus" in consults_df.columns and "ScheduledDateTime" in consults_df.columns and len(consults_df) > 0:
        sc = consults_df[["ScheduledDateTime", "SimulationStatus"]].copy()
        _sc_status = sc["SimulationStatus"].str.lower().str.strip()
        if "DaysToSimulation" in consults_df.columns:
            sc["days"] = pd.to_numeric(consults_df["DaysToSimulation"], errors="coerce")
        else:
            sc["days"] = 0
        sc["converted"] = _sc_status.isin(["completed", "scheduled"]) & (sc["days"].fillna(999) <= 180)
        if _spark_period == "D":
            sc["_sp"] = sc["ScheduledDateTime"].dt.normalize()
        else:
            sc["_sp"] = sc["ScheduledDateTime"].dt.to_period("W").dt.to_timestamp()
        sc_grp = sc.groupby("_sp")["converted"]
        sc_rate = (sc_grp.sum() / sc_grp.count() * 100)
        if len(sc_rate) > 2:
            sparkline_data["sim_conv"] = {
                "labels": [d.isoformat() for d in sc_rate.index],
                "values": [round(v, 1) for v in sc_rate.tolist()],
                "color": CHART_COLORWAY[3],
                "hover_fmt": "%{x|%b %d}: %{customdata:.1f}%<extra></extra>",
            }

    _t_sim = (None, None)
    if trend_label and not dff_prior.empty and "SimulationStatus" in dff_prior.columns:
        prior_consults = dff_prior[dff_prior["VisitType"] == "Consult"] if "VisitType" in dff_prior.columns else pd.DataFrame()
        if len(prior_consults) > 0 and "SimulationStatus" in prior_consults.columns:
            _p_status = prior_consults["SimulationStatus"].str.lower().str.strip()
            p_sim = _p_status.isin(["completed", "scheduled"])
            if "DaysToSimulation" in prior_consults.columns:
                p_days = pd.to_numeric(prior_consults["DaysToSimulation"], errors="coerce")
                p_sim = p_sim & (p_days.fillna(999) <= 180)
            prior_rate = p_sim.mean() * 100
            if sim_rate is not None:
                _t_sim = _cv_trend(sim_rate, prior_rate)

    _sim_info = dmc.Tooltip(
        DashIconify(icon="mdi:information-outline", width=16, color="#9CA3AF", style={"cursor": "help"}),
        label="Consults with completed or scheduled sim within 180 days / total consults.",
        position="top", withArrow=True, multiline=True, w=260,
    )
    kpi_sim_conv = kpi_card(
        "Sim Conversion", sim_rate_str, accent_color=CHART_COLORWAY[3], sparkline_id="cv-spark-sim-conv",
        trend_text=f"{_t_sim[0]} {trend_label}" if _t_sim[0] else None, trend_direction=_t_sim[1],
        header_control=_sim_info,
    )

    # Days to sim KPI
    days_sim = pd.Series(dtype=float)
    if "DaysToSimulation" in consults_df.columns and len(consults_df) > 0:
        _dsv = pd.to_numeric(consults_df["DaysToSimulation"], errors="coerce").dropna()
        days_sim = _dsv[(_dsv >= 0) & (_dsv <= days_to_sim_max)]
        days_sim_str = f"{days_sim.median():.0f}" if len(days_sim) > 0 else "N/A"
    else:
        days_sim_str = "N/A"

    if "DaysToSimulation" in consults_df.columns and "ScheduledDateTime" in consults_df.columns and len(consults_df) > 0:
        ds = consults_df[["ScheduledDateTime", "DaysToSimulation"]].copy()
        ds["val"] = pd.to_numeric(ds["DaysToSimulation"], errors="coerce")
        ds = ds.dropna(subset=["val"])
        ds = ds[(ds["val"] >= 0) & (ds["val"] <= days_to_sim_max)]
        if _spark_period == "D":
            ds["_sp"] = ds["ScheduledDateTime"].dt.normalize()
        else:
            ds["_sp"] = ds["ScheduledDateTime"].dt.to_period("W").dt.to_timestamp()
        ds_grp = ds.groupby("_sp")["val"].median()
        if len(ds_grp) > 2:
            sparkline_data["days_to_sim"] = {
                "labels": [d.isoformat() for d in ds_grp.index],
                "values": ds_grp.tolist(),
                "color": CHART_COLORWAY[4],
                "hover_fmt": "%{x|%b %d}: %{customdata:,.1f} days<extra></extra>",
            }

    _t_days = (None, None)
    if trend_label and not dff_prior.empty and "DaysToSimulation" in dff_prior.columns:
        prior_consults_d = dff_prior[dff_prior["VisitType"] == "Consult"] if "VisitType" in dff_prior.columns else pd.DataFrame()
        if "DaysToSimulation" in prior_consults_d.columns and len(prior_consults_d) > 0:
            _pdsv = pd.to_numeric(prior_consults_d["DaysToSimulation"], errors="coerce").dropna()
            p_days_sim = _pdsv[(_pdsv >= 0) & (_pdsv <= days_to_sim_max)]
            if len(p_days_sim) > 0 and days_sim_str != "N/A":
                _t_days = _cv_trend(days_sim.median(), p_days_sim.median(), invert=True)

    _days_sim_info = dmc.Tooltip(
        DashIconify(icon="mdi:information-outline", width=16, color="#9CA3AF", style={"cursor": "help"}),
        label=f"Median consult-to-sim interval. Excludes values >{days_to_sim_max} days to filter purposeful waits and delays.",
        position="top", withArrow=True, multiline=True, w=240,
    )
    kpi_days_sim = kpi_card(
        "Median Days to Sim", days_sim_str, accent_color=CHART_COLORWAY[4], sparkline_id="cv-spark-days-sim",
        trend_text=f"{_t_days[0]} {trend_label}" if _t_days[0] else None, trend_direction=_t_days[1],
        header_control=_days_sim_info,
    )

    row_data, col_defs = _build_detail_table(dff, c2b)

    return (
        kpi_total, kpi_consults, kpi_followups, kpi_lead, kpi_sim_conv, kpi_days_sim,
        sparkline_data, data["filter_options"],
        row_data, col_defs,
    )


# ---------------------------------------------------------------------------
# Callback 2: Volume Store
# ---------------------------------------------------------------------------

@callback(
    Output("cv-store-volume", "data"),
    *_CV_FILTER_INPUTS,
    Input("cv-volume-agg", "value"),
    Input("cv-volume-slice", "value"),
    running=[(Output("cv-chart-volume-loading", "visible"), True, False)],
)
def _update_cv_volume(*args):
    ctx = _unpack_filter_args(args)
    agg, volume_slice = args[14], args[15]
    data = _load_and_filter_cv(**ctx)
    if data is None or data["dff"].empty:
        return None
    return _prepare_volume_data(data["dff"], agg, volume_slice, c2b=data["c2b"])


# ---------------------------------------------------------------------------
# Callback 3: Lead Time Store
# ---------------------------------------------------------------------------

@callback(
    Output("cv-store-lead", "data"),
    *_CV_FILTER_INPUTS,
    Input("cv-lead-agg", "value"),
    Input("cv-lead-slice", "value"),
    running=[(Output("cv-chart-lead-time-loading", "visible"), True, False)],
)
def _update_cv_lead(*args):
    ctx = _unpack_filter_args(args)
    lead_agg, lead_slice = args[14], args[15]
    data = _load_and_filter_cv(**ctx)
    if data is None or data["dff"].empty:
        return None
    return _prepare_lead_data(data["dff"], data["departments"], lead_agg, lead_slice)


# ---------------------------------------------------------------------------
# Callback 4: Conversion Store
# ---------------------------------------------------------------------------

@callback(
    Output("cv-store-conversion", "data"),
    *_CV_FILTER_INPUTS,
    Input("cv-conversion-agg", "value"),
    Input("cv-conversion-slice", "value"),
    running=[(Output("cv-chart-conversion-loading", "visible"), True, False)],
)
def _update_cv_conversion(*args):
    ctx = _unpack_filter_args(args)
    conv_agg, conv_slice = args[14], args[15]
    data = _load_and_filter_cv(**ctx)
    if data is None or data["dff"].empty:
        return None
    return _prepare_conversion_data(data["dff"], data["departments"], conv_agg, conv_slice)


# ---------------------------------------------------------------------------
# Callback 5: Cumulative Store
# ---------------------------------------------------------------------------

@callback(
    Output("cv-store-cumulative", "data"),
    *_CV_FILTER_INPUTS,
    Input("cv-cumulative-mode", "value"),
    Input("cv-cumulative-period-type", "value"),
    Input("cv-cumulative-slice", "value"),
    running=[(Output("cv-chart-cumulative-loading", "visible"), True, False)],
)
def _update_cv_cumulative(*args):
    ctx = _unpack_filter_args(args)
    cumul_mode, cumul_period_type, cumul_slice = args[14], args[15], args[16]
    data = _load_and_filter_cv(**ctx)
    if data is None:
        return None
    return _prepare_cumulative_data(
        data["df_all"], data["start"], data["end"], data["date_preset"],
        data["departments"], ctx["physician"], ctx["body_systems"],
        ctx["visit_type"], ctx["status"], ctx["inpatient"], data["c2b"],
        ctx["classified_type"], mode=cumul_mode or "prior",
        period_type=cumul_period_type or "calendar",
        slice_by=cumul_slice or "category",
        max_prior=5,
    )


# ---------------------------------------------------------------------------
# Callback 6: Cancel Rate Store
# ---------------------------------------------------------------------------

@callback(
    Output("cv-store-cancel", "data"),
    *_CV_FILTER_INPUTS,
    Input("cv-cancel-agg", "value"),
    Input("cv-cancel-slice", "value"),
    running=[(Output("cv-chart-cancel-rate-loading", "visible"), True, False)],
)
def _update_cv_cancel(*args):
    ctx = _unpack_filter_args(args)
    cancel_agg, cancel_slice = args[14], args[15]
    data = _load_and_filter_cv(**ctx)
    if data is None or data["dff_all_status"].empty:
        return None
    return _prepare_cancel_data(data["dff_all_status"], cancel_agg, cancel_slice)


# ---------------------------------------------------------------------------
# Callback 7: Diagnosis + Billing Figures
# ---------------------------------------------------------------------------

@callback(
    Output("cv-chart-diagnosis", "figure"),
    Output("cv-chart-billing", "figure"),
    *_CV_FILTER_INPUTS,
    Input("cv-diagnosis-slice", "value"),
    Input("cv-diagnosis-mode", "value"),
    Input("cv-diagnosis-compare", "value"),
    Input("cv-billing-group", "value"),
    Input("cv-billing-slice", "value"),
    Input("cv-billing-mode", "value"),
    running=[
        (Output("cv-diagnosis-loading", "visible"), True, False),
        (Output("cv-billing-loading", "visible"), True, False),
    ],
)
def _update_cv_diag_billing(*args):
    ctx = _unpack_filter_args(args)
    (diagnosis_slice, diagnosis_mode, diagnosis_compare,
     billing_group, billing_slice, billing_mode) = args[14:20]
    data = _load_and_filter_cv(**ctx)

    empty = empty_figure()
    if data is None or data["dff"].empty:
        return empty, empty

    dff = data["dff"]
    dff_prior = data["dff_prior"]
    c2b = data["c2b"]
    start, end = data["start"], data["end"]
    date_preset = data["date_preset"]

    _diag_prior_df = None
    _diag_period_labels = None
    if diagnosis_compare == "prior" and not dff_prior.empty:
        _diag_prior_df = dff_prior
        _diag_period_labels = (_diag_period_label(start, end, date_preset),)
        if date_preset in _PRIOR_MAP:
            _p_start, _p_end = _PRIOR_MAP[date_preset][1](start, end)
            _diag_period_labels = (
                _diag_period_labels[0],
                _diag_period_label(_p_start, _p_end, date_preset),
            )
    fig_diagnosis = _build_diagnosis_mix(
        dff, c2b, slice_by=diagnosis_slice or "",
        mode=diagnosis_mode or "count",
        prior_df=_diag_prior_df,
        period_labels=_diag_period_labels,
    )
    fig_billing = _build_billing_mix(
        dff, group=billing_group or "new",
        slice_by=billing_slice or "", mode=billing_mode or "count",
    )

    return fig_diagnosis, fig_billing


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Slice-by dim styling — dim "Total" when a group is active, dim groups when "Total" active
# ---------------------------------------------------------------------------

_SLICE_CLASS_JS = """function(val) {
    return (val && val !== "total") ? "slice-group-active" : "slice-total-active";
}"""

for _sid in ["cv-volume-slice", "cv-lead-slice", "cv-conversion-slice", "cv-cancel-slice", "cv-diagnosis-slice", "cv-billing-slice", "cv-cumulative-slice"]:
    clientside_callback(
        _SLICE_CLASS_JS,
        Output(_sid, "className"),
        Input(_sid, "value"),
    )

# Hide diagnosis slice control when "vs Prior" is active (prior ignores slicing)
clientside_callback(
    """function(compare) {
        if (compare === "prior") return {display: "none"};
        return {};
    }""",
    Output("cv-diagnosis-slice", "style"),
    Input("cv-diagnosis-compare", "value"),
)


# ---------------------------------------------------------------------------
# Clientside callbacks for charts
# ---------------------------------------------------------------------------

_CENSUS_WITH_STACK = """function(rawData, smoothPct, chartType, stackVal, currentFig) {
    return window.dash_clientside.census.smoothChartWithType(rawData, smoothPct, chartType, currentFig, stackVal);
}"""

_CUMULATIVE_WITH_STACK = """function(rawData, smoothPct, chartType, stackVal, maxPrior, currentFig) {
    return window.dash_clientside.cumulative.renderCumulative(rawData, smoothPct, chartType, currentFig, stackVal, maxPrior);
}"""

clientside_callback(
    _CENSUS_WITH_STACK,
    Output("cv-chart-volume", "figure"),
    Input("cv-store-volume", "data"),
    Input("cv-volume-settings-smooth", "value"),
    Input("cv-volume-settings-type", "value"),
    Input("cv-volume-settings-stack", "value"),
    State("cv-chart-volume", "figure"),
)

clientside_callback(
    _CENSUS_WITH_STACK,
    Output("cv-chart-lead-time", "figure"),
    Input("cv-store-lead", "data"),
    Input("cv-lead-settings-smooth", "value"),
    Input("cv-lead-settings-type", "value"),
    Input("cv-lead-settings-stack", "value"),
    State("cv-chart-lead-time", "figure"),
)

clientside_callback(
    _CENSUS_WITH_STACK,
    Output("cv-chart-conversion", "figure"),
    Input("cv-store-conversion", "data"),
    Input("cv-conversion-settings-smooth", "value"),
    Input("cv-conversion-settings-type", "value"),
    Input("cv-conversion-settings-stack", "value"),
    State("cv-chart-conversion", "figure"),
)

clientside_callback(
    _CUMULATIVE_WITH_STACK,
    Output("cv-chart-cumulative", "figure"),
    Input("cv-store-cumulative", "data"),
    Input("cv-cumulative-settings-smooth", "value"),
    Input("cv-cumulative-settings-type", "value"),
    Input("cv-cumulative-settings-stack", "value"),
    Input("cv-cumulative-settings-prior-periods", "value"),
    State("cv-chart-cumulative", "figure"),
)

clientside_callback(
    _CENSUS_WITH_STACK,
    Output("cv-chart-cancel-rate", "figure"),
    Input("cv-store-cancel", "data"),
    Input("cv-cancel-settings-smooth", "value"),
    Input("cv-cancel-settings-type", "value"),
    Input("cv-cancel-settings-stack", "value"),
    State("cv-chart-cancel-rate", "figure"),
)


# ---------------------------------------------------------------------------
# Clientside callbacks for KPI sparklines
# ---------------------------------------------------------------------------

clientside_callback(
    ClientsideFunction(namespace="sparklines", function_name="smoothCvTotal"),
    Output("cv-spark-total", "figure"),
    Input("cv-store-kpi-sparklines", "data"),
    Input("cv-smooth-slider", "value"),
)

clientside_callback(
    ClientsideFunction(namespace="sparklines", function_name="smoothCvConsults"),
    Output("cv-spark-consults", "figure"),
    Input("cv-store-kpi-sparklines", "data"),
    Input("cv-smooth-slider", "value"),
)

clientside_callback(
    ClientsideFunction(namespace="sparklines", function_name="smoothCvFollowups"),
    Output("cv-spark-followups", "figure"),
    Input("cv-store-kpi-sparklines", "data"),
    Input("cv-smooth-slider", "value"),
)

clientside_callback(
    ClientsideFunction(namespace="sparklines", function_name="smoothCvLead"),
    Output("cv-spark-lead", "figure"),
    Input("cv-store-kpi-sparklines", "data"),
    Input("cv-smooth-slider", "value"),
)

clientside_callback(
    ClientsideFunction(namespace="sparklines", function_name="smoothCvSimConv"),
    Output("cv-spark-sim-conv", "figure"),
    Input("cv-store-kpi-sparklines", "data"),
    Input("cv-smooth-slider", "value"),
)

clientside_callback(
    ClientsideFunction(namespace="sparklines", function_name="smoothCvDaysToSim"),
    Output("cv-spark-days-sim", "figure"),
    Input("cv-store-kpi-sparklines", "data"),
    Input("cv-smooth-slider", "value"),
)


# ---------------------------------------------------------------------------
# Settings panel toggles + PNG exports (via shared chart framework)
# ---------------------------------------------------------------------------

register_chart_callbacks([
    ("cv-volume", "cv-chart-volume", "cv-store-volume"),
    ("cv-cumulative", "cv-chart-cumulative", "cv-store-cumulative"),
    {"sid": "cv-lead", "gid": "cv-chart-lead-time", "store_id": "cv-store-lead", "show_grouping": False},
    {"sid": "cv-conversion", "gid": "cv-chart-conversion", "store_id": "cv-store-conversion", "show_grouping": False},
    {"sid": "cv-cancel", "gid": "cv-chart-cancel-rate", "store_id": "cv-store-cancel", "show_grouping": False},
    ("cv-diagnosis", "cv-chart-diagnosis"),
    ("cv-billing", "cv-chart-billing"),
])

register_outlier_callbacks("cv", n_transitions=2, defaults=[_LEAD_MAX, _DAYS_TO_SIM_MAX])

# Category / Type button labels
clientside_callback(
    """function(v) { return "Category: " + (v || "All"); }""",
    Output("cv-visit-type-trigger", "children"),
    Input("cv-filter-visit-type", "value"),
)
clientside_callback(
    """function(v) { return "Type: " + (v || "All"); }""",
    Output("cv-classified-type-trigger", "children"),
    Input("cv-filter-classified-type", "value"),
)


# --- Cumulative chart mode toggle: show/hide sub-controls ---
# Bar mode hides mode toggle, shows both period-type and slice controls
clientside_callback(
    """function(mode, chartType) {
        if (chartType === "bar") {
            return [{display: "none"}, {}, {}];
        }
        if (mode === "prior") {
            return [{}, {}, {display: "none"}];
        }
        return [{}, {display: "none"}, {}];
    }""",
    Output("cv-cumulative-mode", "style"),
    Output("cv-cumulative-period-type", "style"),
    Output("cv-cumulative-slice", "style"),
    Input("cv-cumulative-mode", "value"),
    Input("cv-cumulative-settings-type", "value"),
)


# ---------------------------------------------------------------------------
# Data preparation for clientside charts
# ---------------------------------------------------------------------------


def _trim_edges(series_or_list):
    """Replace leading/trailing zeros/NaN with None so Plotly gaps the line.

    Interior zeros are preserved — only the edges where a trace has no data
    are nulled out.  Accepts a pandas Series or plain list.
    """
    import math
    raw = list(series_or_list)
    n = len(raw)
    # Normalise NaN → None
    for i in range(n):
        v = raw[i]
        if v is None:
            continue
        try:
            if math.isnan(v):
                raw[i] = None
        except (TypeError, ValueError):
            pass
    # Find first non-zero, non-None value
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
    """Build tick positions/labels for a day-index x-axis.

    Automatically selects granularity (daily → weekly → monthly → quarterly →
    yearly) to stay under *max_ticks*.  Works for any period from a few days
    to 20+ years.
    """
    tick_positions = []
    tick_labels = []

    # Collect candidate ticks at each granularity, pick the coarsest that
    # stays ≤ max_ticks.  We try finest → coarsest and stop early.
    candidates = []  # list of (positions, labels)

    # --- Daily ---
    if n_days <= max_ticks:
        pos, lbl = [], []
        for i in range(n_days):
            d = start_norm + pd.Timedelta(days=i)
            pos.append(i)
            lbl.append(d.strftime("%m/%d"))
        candidates.append((pos, lbl))

    # --- Weekly ---
    pos, lbl = [], []
    for i in range(0, n_days, 7):
        d = start_norm + pd.Timedelta(days=i)
        pos.append(i)
        lbl.append(d.strftime("%m/%d"))
    candidates.append((pos, lbl))

    # --- Monthly ---
    pos, lbl = [], []
    prev_month = None
    for i in range(n_days):
        d = start_norm + pd.Timedelta(days=i)
        if d.month != prev_month:
            pos.append(i)
            lbl.append(d.strftime("%b") if n_days > 180 else d.strftime("%b %d"))
            prev_month = d.month
    candidates.append((pos, lbl))

    # --- Quarterly ---
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

    # --- Yearly ---
    pos, lbl = [], []
    prev_year = None
    for i in range(n_days):
        d = start_norm + pd.Timedelta(days=i)
        if d.year != prev_year:
            pos.append(i)
            lbl.append(str(d.year))
            prev_year = d.year
    candidates.append((pos, lbl))

    # --- Every 2 years ---
    pos, lbl = [], []
    prev_year = None
    for i in range(n_days):
        d = start_norm + pd.Timedelta(days=i)
        if d.year != prev_year and d.year % 2 == 0:
            pos.append(i)
            lbl.append(str(d.year))
            prev_year = d.year
    candidates.append((pos, lbl))

    # --- Every 5 years ---
    pos, lbl = [], []
    prev_year = None
    for i in range(n_days):
        d = start_norm + pd.Timedelta(days=i)
        if d.year != prev_year and d.year % 5 == 0:
            pos.append(i)
            lbl.append(str(d.year))
            prev_year = d.year
    candidates.append((pos, lbl))

    # Pick the finest granularity that stays ≤ max_ticks
    for p, l in candidates:
        if len(p) <= max_ticks:
            return p, l

    # Fallback: just use the coarsest
    return candidates[-1]


def _prepare_volume_data(dff, agg, slice_by="category", c2b=None):
    """Prepare volume trend data for clientside rendering.

    slice_by controls how the stacked series are split:
      - "category": VisitCategory (Consult, Follow-Up, Re-eval, Virtual, Other)
      - "type":     VisitType (classified via _classify_visit_type)
      - "physician": AppointmentPhysician
      - "site":     Department
      - "diagnosis": Body system (via diagnosis lookup)
    """
    if dff.empty or "ScheduledDateTime" not in dff.columns:
        return None

    dff = dff.copy()
    period_code = "Y" if agg == "Y" else agg
    dff["period"] = dff["ScheduledDateTime"].dt.to_period(period_code).dt.to_timestamp()

    all_periods = sorted(dff["period"].unique())
    dates = [d.isoformat() for d in all_periods]

    series = []

    if not slice_by:
        # No grouping — single total line
        counts = dff.groupby("period").size().reindex(all_periods, fill_value=0)
        series.append({
            "name": "Total",
            "values": _trim_edges(counts.tolist()),
            "color": PRIMARY,
        })

    elif slice_by == "category":
        type_colors = {
            "Consult": CHART_COLORWAY[0],
            "Follow-Up": CHART_COLORWAY[1],
            "Re-eval": CHART_COLORWAY[2],
            "Virtual": CHART_COLORWAY[3],
            "Other": CHART_COLORWAY[4],
        }
        for vtype in ["Consult", "Follow-Up", "Re-eval", "Virtual", "Other"]:
            subset = dff[dff["VisitCategory"] == vtype]
            if subset.empty:
                continue
            counts = subset.groupby("period").size().reindex(all_periods, fill_value=0)
            series.append({
                "name": vtype,
                "values": _trim_edges(counts.tolist()),
                "color": type_colors.get(vtype, CHART_COLORWAY[5]),
            })

    elif slice_by == "type":
        type_colors = {
            "Consult": CHART_COLORWAY[0],
            "Follow-Up": CHART_COLORWAY[1],
            "Virtual": CHART_COLORWAY[3],
            "Other": CHART_COLORWAY[4],
        }
        col = "VisitType" if "VisitType" in dff.columns else "VisitCategory"
        for vtype in ["Consult", "Follow-Up", "Virtual", "Other"]:
            subset = dff[dff[col] == vtype]
            if subset.empty:
                continue
            counts = subset.groupby("period").size().reindex(all_periods, fill_value=0)
            series.append({
                "name": vtype,
                "values": _trim_edges(counts.tolist()),
                "color": type_colors.get(vtype, CHART_COLORWAY[5]),
            })

    elif slice_by == "physician":
        col = "AppointmentPhysician"
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

    return {"dates": dates, "series": series, "height": 350, "yTitle": "Visits", "hideLegend": len(series) <= 1}


def _prepare_lead_data(dff, departments, agg="M", slice_by="site"):
    """Prepare lead time trend data.

    agg: time aggregation — "W", "M", or "Y".
    slice_by: "category", "type", "physician", or "site" (department).
    """
    if dff.empty or "ScheduledDateTime" not in dff.columns or "DaysFromCreatedToAppt" not in dff.columns:
        return None

    dff = dff.copy()
    dff["DaysFromCreatedToAppt"] = pd.to_numeric(dff["DaysFromCreatedToAppt"], errors="coerce")
    dff = dff.dropna(subset=["DaysFromCreatedToAppt"])

    period_code = "Y" if agg == "Y" else agg
    dff["period"] = dff["ScheduledDateTime"].dt.to_period(period_code).dt.to_timestamp()

    if dff.empty:
        return None

    all_periods = sorted(dff["period"].unique())
    dates = [d.isoformat() for d in all_periods]
    val_col = "DaysFromCreatedToAppt"

    series = []

    if not slice_by:
        # No grouping — single total median line
        grouped = dff.groupby("period")[val_col].median().reindex(all_periods)
        series.append({
            "name": "Total",
            "values": _trim_edges(grouped.tolist()),
            "color": PRIMARY,
        })

    elif slice_by == "site":
        active_depts = dff["Department"].unique() if "Department" in dff.columns else []
        for dept in (departments or DEPARTMENTS):
            if dept not in active_depts:
                continue
            subset = dff[dff["Department"] == dept]
            grouped = subset.groupby("period")[val_col].median().reindex(all_periods)
            series.append({
                "name": dept,
                "values": _trim_edges(grouped.tolist()),
                "color": dept_color(dept),
            })

    elif slice_by == "category":
        type_colors = {
            "Consult": CHART_COLORWAY[0], "Follow-Up": CHART_COLORWAY[1],
            "Re-eval": CHART_COLORWAY[2], "Virtual": CHART_COLORWAY[3], "Other": CHART_COLORWAY[4],
        }
        col = "VisitCategory" if "VisitCategory" in dff.columns else None
        if col:
            for vtype in ["Consult", "Follow-Up", "Re-eval", "Virtual", "Other"]:
                subset = dff[dff[col] == vtype]
                if subset.empty:
                    continue
                grouped = subset.groupby("period")[val_col].median().reindex(all_periods)
                series.append({
                    "name": vtype,
                    "values": _trim_edges(grouped.tolist()),
                    "color": type_colors.get(vtype, CHART_COLORWAY[5]),
                })

    elif slice_by == "type":
        type_colors = {
            "Consult": CHART_COLORWAY[0], "Follow-Up": CHART_COLORWAY[1],
            "Virtual": CHART_COLORWAY[3], "Other": CHART_COLORWAY[4],
        }
        col = "VisitType" if "VisitType" in dff.columns else "VisitCategory"
        for vtype in ["Consult", "Follow-Up", "Virtual", "Other"]:
            subset = dff[dff[col] == vtype]
            if subset.empty:
                continue
            grouped = subset.groupby("period")[val_col].median().reindex(all_periods)
            series.append({
                "name": vtype,
                "values": _trim_edges(grouped.tolist()),
                "color": type_colors.get(vtype, CHART_COLORWAY[5]),
            })

    elif slice_by == "physician":
        col = "AppointmentPhysician"
        if col in dff.columns:
            physicians = sorted(dff[col].dropna().unique())
            for i, phys in enumerate(physicians):
                subset = dff[dff[col] == phys]
                grouped = subset.groupby("period")[val_col].median().reindex(all_periods)
                series.append({
                    "name": phys.split(",")[0] if "," in phys else phys,
                    "values": _trim_edges(grouped.tolist()),
                    "color": CHART_COLORWAY[i % len(CHART_COLORWAY)],
                })

    return {"dates": dates, "series": series, "height": 350, "yTitle": "Median Lead Time (days)", "stacked": False, "hideLegend": len(series) <= 1}


def _prepare_conversion_data(dff, departments, agg="M", slice_by="site"):
    """Prepare conversion rate data using SimulationStatus.

    agg: time aggregation — "W", "M", or "Y".
    slice_by: "category", "type", "physician", or "site" (department).
    """
    # For "type" slicing, use full dataset so each VisitType gets its own rate.
    # For all other slices, pre-filter to consults only.
    if slice_by == "type" and "VisitType" in dff.columns:
        consults = dff.copy()
    else:
        consults = dff[dff["VisitType"] == "Consult"].copy() if "VisitType" in dff.columns else pd.DataFrame()

    if consults.empty or "SimulationStatus" not in consults.columns:
        return None

    # Derive has-sim boolean: completed or scheduled simulation within 180 days
    _status = consults["SimulationStatus"].str.lower().str.strip()
    has_sim = _status.isin(["completed", "scheduled"])
    if "DaysToSimulation" in consults.columns:
        days_val = pd.to_numeric(consults["DaysToSimulation"], errors="coerce")
        has_sim = has_sim & (days_val.fillna(999) <= 180)
    consults["_has_sim"] = has_sim.astype(int)

    period_code = "Y" if agg == "Y" else agg
    consults["period"] = consults["ScheduledDateTime"].dt.to_period(period_code).dt.to_timestamp()

    all_periods = sorted(consults["period"].unique())
    dates = [d.isoformat() for d in all_periods]

    series = []

    if not slice_by:
        # No grouping — single overall line
        overall = consults.groupby("period")["_has_sim"].mean().reindex(all_periods) * 100
        series.append({
            "name": "Overall",
            "values": _trim_edges(overall.tolist()),
            "color": PRIMARY,
        })

    elif slice_by == "site":
        active_depts = consults["Department"].unique() if "Department" in consults.columns else []
        for dept in (departments or DEPARTMENTS):
            if dept not in active_depts:
                continue
            subset = consults[consults["Department"] == dept]
            grouped = subset.groupby("period")["_has_sim"].mean().reindex(all_periods) * 100
            series.append({"name": dept, "values": _trim_edges(grouped.tolist()), "color": dept_color(dept)})

    elif slice_by == "category":
        type_colors = {
            "Consult": CHART_COLORWAY[0], "Follow-Up": CHART_COLORWAY[1],
            "Re-eval": CHART_COLORWAY[2], "Virtual": CHART_COLORWAY[3], "Other": CHART_COLORWAY[4],
        }
        col = "VisitCategory" if "VisitCategory" in consults.columns else None
        if col:
            for vtype in ["Consult", "Follow-Up", "Re-eval", "Virtual", "Other"]:
                subset = consults[consults[col] == vtype]
                if subset.empty:
                    continue
                grouped = subset.groupby("period")["_has_sim"].mean().reindex(all_periods) * 100
                series.append({"name": vtype, "values": _trim_edges(grouped.tolist()), "color": type_colors.get(vtype, CHART_COLORWAY[5])})

    elif slice_by == "type":
        type_colors = {
            "Consult": CHART_COLORWAY[0], "Follow-Up": CHART_COLORWAY[1],
            "Virtual": CHART_COLORWAY[3], "Other": CHART_COLORWAY[4],
        }
        col = "VisitType" if "VisitType" in consults.columns else "VisitCategory"
        for vtype in ["Consult", "Follow-Up", "Virtual", "Other"]:
            subset = consults[consults[col] == vtype]
            if subset.empty:
                continue
            grouped = subset.groupby("period")["_has_sim"].mean().reindex(all_periods) * 100
            series.append({"name": vtype, "values": _trim_edges(grouped.tolist()), "color": type_colors.get(vtype, CHART_COLORWAY[5])})

    elif slice_by == "physician":
        col = "AppointmentPhysician"
        if col in consults.columns:
            physicians = sorted(consults[col].dropna().unique())
            for i, phys in enumerate(physicians):
                subset = consults[consults[col] == phys]
                grouped = subset.groupby("period")["_has_sim"].mean().reindex(all_periods) * 100
                series.append({
                    "name": phys.split(",")[0] if "," in phys else phys,
                    "values": _trim_edges(grouped.tolist()),
                    "color": CHART_COLORWAY[i % len(CHART_COLORWAY)],
                })

    return {"dates": dates, "series": series, "height": 350, "yTitle": "Conversion Rate (%)", "stacked": False, "hideLegend": len(series) <= 1}


def _prepare_cumulative_data(df_all, start, end, date_preset,
                              departments, physician, body_systems,
                              visit_type, status, inpatient, c2b,
                              classified_type, mode="prior",
                              period_type="calendar", slice_by="category",
                              max_prior=5):
    """Prepare cumulative visit volume data for overlay chart.

    mode="prior": Current period cumulative + up to 5 prior equivalent periods (gray lines).
    mode="slice": Current period only, split by dimension (colored lines).

    period_type (only for mode="prior"):
      - "calendar": same calendar dates shifted back by year
      - "rolling":  shift back by period length
    """
    if df_all.empty or "ScheduledDateTime" not in df_all.columns:
        return None

    # Exclude future "Open" appointments — these are scheduled but haven't happened.
    # "Future" = on or after the most recent CSV export date. Open appointments
    # before the export date are stale (never updated) and should still count.
    if "Status" in df_all.columns:
        export_date = _get_cv_export_date()
        if export_date is not None:
            future_open = (
                (df_all["Status"] == "Open")
                & (df_all["ScheduledDateTime"].dt.normalize() >= export_date)
            )
            df_all = df_all[~future_open]
    if df_all.empty:
        return None
    last_data = df_all["ScheduledDateTime"].dt.normalize().max()
    if end.normalize() > last_data:
        end = last_data

    period_days = (end - start).days + 1
    if period_days < 2:
        return None

    def _cumulative_for_window(df, w_start, w_end):
        """Count visits per day within [w_start, w_end], return cumulative list."""
        mask = (df["ScheduledDateTime"] >= w_start) & (df["ScheduledDateTime"] <= w_end)
        sub = df.loc[mask]
        if sub.empty:
            return []
        daily = sub.groupby(sub["ScheduledDateTime"].dt.normalize()).size()
        # Reindex to full day range
        idx = pd.date_range(w_start.normalize(), w_end.normalize(), freq="D")
        daily = daily.reindex(idx, fill_value=0)
        return daily.cumsum().tolist()

    def _slice_totals_for_window(df, w_start, w_end, slice_by):
        """Count total visits per slice dimension within a window."""
        mask = (df["ScheduledDateTime"] >= w_start) & (df["ScheduledDateTime"] <= w_end)
        sub = df.loc[mask]
        if sub.empty:
            return {}
        if slice_by == "total":
            return {"Total": len(sub)}
        if slice_by == "site" and "Department" in sub.columns:
            return sub.groupby("Department").size().to_dict()
        elif slice_by == "category" and "VisitCategory" in sub.columns:
            return sub.groupby("VisitCategory").size().to_dict()
        elif slice_by == "type" and "VisitType" in sub.columns:
            return sub.groupby("VisitType").size().to_dict()
        elif slice_by == "physician" and "AppointmentPhysician" in sub.columns:
            counts = sub.groupby("AppointmentPhysician").size()
            return {(k.split(",")[0] if "," in k else k): v for k, v in counts.items()}
        elif slice_by == "diagnosis" and c2b and "DiagnosisCodes" in sub.columns:
            sub = sub.copy()
            sub["_bs"] = sub["DiagnosisCodes"].apply(lambda v: primary_category(v, c2b))
            sub = sub[sub["_bs"] != "Unknown"]
            return sub.groupby("_bs").size().to_dict()
        return {}

    # Apply dimension filters to full dataset (no date filter)
    dff_all = _apply_cv_filters(
        df_all, departments, physician, body_systems,
        visit_type, status, inpatient, c2b,
        classified_type=classified_type,
    )

    # Use numeric day indices as x-values (0, 1, 2, ...) to avoid duplicate category issue.
    # Build tick positions + labels for display.
    n_days = period_days
    start_norm = start.normalize()
    day_indices = list(range(n_days))

    # Build tick marks — target ~10-15 labels regardless of period length.
    tick_positions, tick_labels = _build_day_index_ticks(start_norm, n_days)

    # --- Always compute prior period windows + slice breakdown (needed for bar mode) ---
    if dff_all.empty:
        current_vals = [0] * n_days
    else:
        current_vals = _cumulative_for_window(dff_all, start, end)

    # Find earliest data date to avoid generating windows before data exists
    if dff_all.empty:
        data_min = start  # no data — priors will also be empty
    else:
        data_min = dff_all["ScheduledDateTime"].min()

    def _period_label(p_start, p_end):
        """Smart label based on the date preset and range."""
        same_year = p_start.year == p_end.year
        same_month = same_year and p_start.month == p_end.month
        # Single month → "Feb 2026"
        if same_month:
            return p_start.strftime("%b %Y")
        if same_year:
            # Full year (Jan–Dec) or YTD → just the year
            if date_preset in ("ytd", "last_year") or (p_start.month == 1 and p_end.month == 12):
                return str(p_start.year)
            # Partial year → "Jan – Mar 2026"
            return f"{p_start.strftime('%b')} – {p_end.strftime('%b %Y')}"
        # Cross-year → "Apr '25 – Mar '26"
        fmt = "%b '%y"
        return f"{p_start.strftime(fmt)} – {p_end.strftime(fmt)}"

    windows = []
    # "All time" has no meaningful prior periods — skip
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
            # Stop if the window ends before the earliest data
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
            "yTitle": "Cumulative Visits",
        }

    else:  # mode == "slice"
        # Within current period, group by slice dimension
        mask = (dff_all["ScheduledDateTime"] >= start) & (dff_all["ScheduledDateTime"] <= end)
        dff_period = dff_all.loc[mask]

        dates_range = pd.date_range(start.normalize(), end.normalize(), freq="D")
        dates_iso = [d.isoformat() for d in dates_range]

        def _trimmed_cumsum(daily_counts):
            """Cumsum with None before first data and after last data."""
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
                daily = sub.groupby(sub["ScheduledDateTime"].dt.normalize()).size()
                daily = daily.reindex(dates_range, fill_value=0)
                series.append({
                    "name": dept,
                    "values": _trimmed_cumsum(daily),
                    "color": DEPARTMENT_COLORS.get(dept, CHART_COLORWAY[0]),
                })

        elif slice_by == "category" and "VisitCategory" in dff_period.columns:
            type_colors = {
                "Consult": CHART_COLORWAY[0], "Follow-Up": CHART_COLORWAY[1],
                "Re-eval": CHART_COLORWAY[2], "Virtual": CHART_COLORWAY[3], "Other": CHART_COLORWAY[4],
            }
            for vtype in ["Consult", "Follow-Up", "Re-eval", "Virtual", "Other"]:
                sub = dff_period[dff_period["VisitCategory"] == vtype]
                if sub.empty:
                    continue
                daily = sub.groupby(sub["ScheduledDateTime"].dt.normalize()).size()
                daily = daily.reindex(dates_range, fill_value=0)
                series.append({
                    "name": vtype,
                    "values": _trimmed_cumsum(daily),
                    "color": type_colors.get(vtype, CHART_COLORWAY[5]),
                })

        elif slice_by == "type" and "VisitType" in dff_period.columns:
            type_colors = {
                "Consult": CHART_COLORWAY[0], "Follow-Up": CHART_COLORWAY[1],
                "Virtual": CHART_COLORWAY[3], "Other": CHART_COLORWAY[4],
            }
            for vtype in ["Consult", "Follow-Up", "Virtual", "Other"]:
                sub = dff_period[dff_period["VisitType"] == vtype]
                if sub.empty:
                    continue
                daily = sub.groupby(sub["ScheduledDateTime"].dt.normalize()).size()
                daily = daily.reindex(dates_range, fill_value=0)
                series.append({
                    "name": vtype,
                    "values": _trimmed_cumsum(daily),
                    "color": type_colors.get(vtype, CHART_COLORWAY[5]),
                })

        elif slice_by == "physician" and "AppointmentPhysician" in dff_period.columns:
            physicians = sorted(dff_period["AppointmentPhysician"].dropna().unique())
            for i, phys in enumerate(physicians):
                sub = dff_period[dff_period["AppointmentPhysician"] == phys]
                daily = sub.groupby(sub["ScheduledDateTime"].dt.normalize()).size()
                daily = daily.reindex(dates_range, fill_value=0)
                series.append({
                    "name": phys.split(",")[0] if "," in phys else phys,
                    "values": _trimmed_cumsum(daily),
                    "color": CHART_COLORWAY[i % len(CHART_COLORWAY)],
                })

        elif slice_by == "diagnosis" and c2b and "DiagnosisCodes" in dff_period.columns:
            dff_period = dff_period.copy()
            dff_period["_bs"] = dff_period["DiagnosisCodes"].apply(lambda v: primary_category(v, c2b))
            dff_bs = dff_period[dff_period["_bs"] != "Unknown"]
            top_bs = dff_bs["_bs"].value_counts().head(8).index.tolist()
            for i, bs in enumerate(top_bs):
                sub = dff_bs[dff_bs["_bs"] == bs]
                daily = sub.groupby(sub["ScheduledDateTime"].dt.normalize()).size()
                daily = daily.reindex(dates_range, fill_value=0)
                series.append({
                    "name": bs,
                    "values": _trimmed_cumsum(daily),
                    "color": CHART_COLORWAY[i % len(CHART_COLORWAY)],
                })

        return {
            "mode": "slice",
            "dates": dates_iso,
            "series": series,
            "sliceBreakdown": slice_breakdown,
            "height": 350,
            "yTitle": "Cumulative Visits",
        }


# ---------------------------------------------------------------------------
# Server-side chart builders
# ---------------------------------------------------------------------------

def _prepare_cancel_data(dff_all, agg="M", slice_by="type"):
    """Prepare cancellation rate data for clientside rendering.

    Computes cancel/no-show percentage per period, optionally sliced by type or site.
    """
    if dff_all.empty or "Status" not in dff_all.columns or "ScheduledDateTime" not in dff_all.columns:
        return None

    dff = dff_all.copy()
    period_code = "Y" if agg == "Y" else agg
    dff["period"] = dff["ScheduledDateTime"].dt.to_period(period_code).dt.to_timestamp()
    dff["_cancelled"] = dff["Status"].str.lower().str.contains("cancel|no-show|no show", na=False)

    all_periods = sorted(dff["period"].unique())
    dates = [d.isoformat() for d in all_periods]

    series = []

    if not slice_by or slice_by not in ("type", "site"):
        # Overall rate
        totals = dff.groupby("period").size().reindex(all_periods, fill_value=0)
        cancels = dff[dff["_cancelled"]].groupby("period").size().reindex(all_periods, fill_value=0)
        rates = ((cancels / totals) * 100).fillna(0)
        series.append({
            "name": "Cancel Rate",
            "values": _trim_edges(rates.tolist()),
            "color": PRIMARY,
        })

    elif slice_by == "type":
        col = "VisitCategory" if "VisitCategory" in dff.columns else "VisitType"
        type_colors = {
            "Consult": CHART_COLORWAY[0],
            "Follow-Up": CHART_COLORWAY[1],
            "Re-eval": CHART_COLORWAY[2],
            "Virtual": CHART_COLORWAY[3],
            "Other": CHART_COLORWAY[4],
        }
        for vtype in sorted(dff[col].dropna().unique()):
            subset = dff[dff[col] == vtype]
            if subset.empty:
                continue
            totals = subset.groupby("period").size().reindex(all_periods, fill_value=0)
            cancels = subset[subset["_cancelled"]].groupby("period").size().reindex(all_periods, fill_value=0)
            rates = ((cancels / totals) * 100).fillna(0)
            series.append({
                "name": vtype,
                "values": _trim_edges(rates.tolist()),
                "color": type_colors.get(vtype, CHART_COLORWAY[len(series) % len(CHART_COLORWAY)]),
            })

    elif slice_by == "site":
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


def _build_diagnosis_mix(dff, c2b=None, slice_by="", mode="count", prior_df=None, period_labels=None):
    """Horizontal bar chart of visits by body system (via diagnosis lookup).

    slice_by: "" for total, or "category"/"type"/"physician"/"site" for stacked bars.
    mode: "count" (absolute) or "pct" (% of total visits).
    prior_df: if provided, show paired current/prior bars (ignores slice_by).
    period_labels: tuple (current_label, prior_label) with date range strings for tooltips.
    """
    if dff.empty:
        return empty_figure("Diagnosis data unavailable")

    # Assign body system to each row
    if not (c2b and "DiagnosisCodes" in dff.columns):
        return empty_figure("Diagnosis data unavailable")

    work = dff.copy()
    work["_bs"] = work["DiagnosisCodes"].apply(lambda v: primary_category(v, c2b))
    work = work[work["_bs"] != "Unknown"]

    if work.empty:
        return empty_figure("No diagnosis data")

    # Get top 12 body systems by total count for consistent ordering
    top_bs = work["_bs"].value_counts().head(12)
    top_bs_names = top_bs.index.tolist()
    work = work[work["_bs"].isin(top_bs_names)]
    # Sort ascending for horizontal bars (largest at top)
    bs_order = list(reversed(top_bs_names))

    total_current = len(work)

    fig = go.Figure()

    # --- Prior-period comparison mode ---
    if prior_df is not None and not prior_df.empty and "DiagnosisCodes" in prior_df.columns:
        prior_work = prior_df.copy()
        prior_work["_bs"] = prior_work["DiagnosisCodes"].apply(lambda v: primary_category(v, c2b))
        prior_work = prior_work[prior_work["_bs"] != "Unknown"]
        # Use same body system order as current period
        prior_work = prior_work[prior_work["_bs"].isin(top_bs_names)]
        total_prior = len(prior_work)

        curr_counts = work["_bs"].value_counts().reindex(bs_order, fill_value=0)
        prior_counts = prior_work["_bs"].value_counts().reindex(bs_order, fill_value=0)

        curr_label = period_labels[0] if period_labels else "Current"
        prior_label = period_labels[1] if period_labels else "Prior"

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

        # Prior bars first (behind), then current bars (in front)
        fig.add_trace(go.Bar(
            x=list(prior_vals), y=[str(b) for b in bs_order], orientation="h",
            marker_color="rgba(156, 163, 175, 0.5)",
            name=prior_label,
            hovertemplate=prior_hover,
        ))
        fig.add_trace(go.Bar(
            x=list(curr_vals), y=[str(b) for b in bs_order], orientation="h",
            marker_color=CHART_COLORWAY[0],
            name=curr_label,
            hovertemplate=curr_hover,
        ))

        apply_default_layout(fig, barmode="group")
        fig.update_layout(
            xaxis_title="", yaxis_title="",
            xaxis_visible=False,
            yaxis=dict(automargin="left+top+bottom", ticklabelstandoff=0),
            margin=dict(l=0, r=8, t=24, b=12),
            showlegend=True,
            bargroupgap=0.15,
        )
        if mode == "pct":
            fig.update_layout(xaxis=dict(ticksuffix="%"))
        return fig

    # --- Standard mode (no prior comparison) ---
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
            x=list(vals),
            y=[str(b) for b in bs_order],
            orientation="h",
            marker_color=CHART_COLORWAY[0],
            showlegend=False,
            text=text, textposition="outside", textfont=dict(size=12),
            cliponaxis=False,
            hovertemplate=hover,
        ))
    else:
        # Determine slice column and groups
        if slice_by == "category":
            col = "VisitCategory" if "VisitCategory" in work.columns else None
            groups = ["Consult", "Follow-Up", "Re-eval", "Virtual", "Other"]
            colors = {
                "Consult": CHART_COLORWAY[0], "Follow-Up": CHART_COLORWAY[1],
                "Re-eval": CHART_COLORWAY[2], "Virtual": CHART_COLORWAY[3], "Other": CHART_COLORWAY[4],
            }
        elif slice_by == "type":
            col = "VisitType" if "VisitType" in work.columns else None
            groups = ["Consult", "Follow-Up", "Virtual", "Other"]
            colors = {
                "Consult": CHART_COLORWAY[0], "Follow-Up": CHART_COLORWAY[1],
                "Virtual": CHART_COLORWAY[3], "Other": CHART_COLORWAY[4],
            }
        elif slice_by == "physician":
            col = "AppointmentPhysician" if "AppointmentPhysician" in work.columns else None
            groups = sorted(work[col].dropna().unique()) if col else []
            colors = {g: CHART_COLORWAY[i % len(CHART_COLORWAY)] for i, g in enumerate(groups)}
        elif slice_by == "site":
            col = "Department" if "Department" in work.columns else None
            groups = sorted(work[col].dropna().unique()) if col else []
            colors = {g: DEPARTMENT_COLORS.get(g, CHART_COLORWAY[i % len(CHART_COLORWAY)]) for i, g in enumerate(groups)}
        else:
            col = None
            groups = []

        if col:
            for grp in groups:
                subset = work[work[col] == grp]
                if subset.empty:
                    continue
                counts = subset["_bs"].value_counts().reindex(bs_order, fill_value=0)
                name = grp.split(",")[0] if "," in grp else grp
                if mode == "pct":
                    grp_total = len(subset)
                    vals = (counts / grp_total * 100).round(1) if grp_total else counts * 0
                else:
                    vals = counts
                fig.add_trace(go.Bar(
                    x=list(vals),
                    y=[str(b) for b in bs_order],
                    orientation="h",
                    marker_color=colors.get(grp, CHART_COLORWAY[0]),
                    name=name,
                ))

    apply_default_layout(fig, barmode="stack")
    fig.update_layout(
        xaxis_title="", yaxis_title="",
        xaxis_visible=False,
        yaxis=dict(automargin="left+top+bottom", ticklabelstandoff=0),
        margin=dict(l=0, r=40, t=24, b=12),
        showlegend=bool(slice_by),
    )
    if mode == "pct":
        fig.update_layout(xaxis=dict(ticksuffix="%"))
    return fig


def _build_billing_mix(dff, group="new", slice_by="", mode="count"):
    """Horizontal bar chart of CPT billing codes for a selected group.

    group: "new", "established", "inpatient", or "telehealth"
    slice_by: "" (total), "physician", or "site"
    mode: "count" (absolute) or "pct" (% within each slice)
    """
    if dff.empty or "ProcedureCodes" not in dff.columns:
        return empty_figure("Billing data unavailable")

    group_info = BILLING_GROUPS.get(group, BILLING_GROUPS["new"])
    primary_set = set(group_info["primary"])
    addon_set = set(group_info["addons"])
    target_codes = primary_set | addon_set

    # Build working df — drop visits with no procedure codes
    cols = ["ProcedureCodes"]
    if slice_by == "physician" and "AppointmentPhysician" in dff.columns:
        cols.append("AppointmentPhysician")
    elif slice_by == "site" and "Department" in dff.columns:
        cols.append("Department")

    work = dff[cols].copy()
    work = work.dropna(subset=["ProcedureCodes"])
    work = work[work["ProcedureCodes"].str.strip() != ""]

    if work.empty:
        return empty_figure("No billed visits found")

    # Explode comma-separated codes into individual rows
    work["_code"] = work["ProcedureCodes"].str.split(",")
    work = work.explode("_code")
    work["_code"] = work["_code"].str.strip()

    # Separate NC-modifier codes into "No Charge" bucket
    nc_modifier_mask = work["_code"].str.endswith(" NC", na=False)
    nc_rows = work[nc_modifier_mask].copy()
    work = work[~nc_modifier_mask]

    # Strip modifiers (e.g., "99205 25" → "99205") for matching
    work["_base"] = work["_code"].str.split(" ").str[0]

    # Find visits that have a primary code from this group
    primary_visit_idx = work[work["_base"].isin(primary_set)].index.unique()
    # Keep only rows from those visits that match target codes (primary + addons)
    work = work[work.index.isin(primary_visit_idx) & work["_base"].isin(target_codes)]
    work["_code"] = work["_base"]

    n_nc = len(nc_rows)

    if work.empty and n_nc == 0:
        return empty_figure(f"No {group_info['label']} codes found")

    # Determine slice column
    slice_col = None
    if slice_by == "physician" and "AppointmentPhysician" in work.columns:
        slice_col = "AppointmentPhysician"
    elif slice_by == "site" and "Department" in work.columns:
        slice_col = "Department"

    # Code ordering: primary codes descending by complexity, then addons
    # (reversed for horizontal bars so highest complexity is at top)
    code_totals = work["_code"].value_counts() if not work.empty else pd.Series(dtype=int)
    primary_order = list(reversed(group_info["primary"]))  # highest complexity first
    addon_order = group_info["addons"]  # complexity, then extra time
    # Only include codes that actually appear in the data
    present = set(code_totals.index)
    code_order = [c for c in primary_order if c in present] + [c for c in addon_order if c in present]
    # Reverse for horizontal bars (first = bottom, last = top)
    code_order = list(reversed(code_order))
    if n_nc > 0:
        code_order = ["No Charge"] + code_order

    # For % mode: denominator = unique visits with a primary code
    # (not code-row count, since one visit can have multiple codes)
    primary_visits = work[work["_code"].isin(primary_set)]

    fig = go.Figure()

    def _hover_descs(codes):
        """Build hover description list from code list."""
        return [_CPT_DESCRIPTIONS.get(c, c) for c in codes]

    if not slice_by or not slice_col:
        regular_codes = [c for c in code_order if c != "No Charge"]
        counts = code_totals.reindex(regular_codes, fill_value=0)
        raw_codes = list(counts.index)
        vals = counts.tolist()
        labels = [_CPT_LABELS.get(c, c) for c in raw_codes]
        if n_nc > 0:
            vals = [n_nc] + vals
            labels = ["No Charge"] + labels
            raw_codes = ["No Charge"] + raw_codes

        descs = _hover_descs(raw_codes)

        if mode == "pct":
            denom = primary_visits.index.nunique()
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
        # Stacked bars by slice
        if slice_by == "site":
            groups_list = sorted(work[slice_col].dropna().unique())
            colors = {g: DEPARTMENT_COLORS.get(g, CHART_COLORWAY[i % len(CHART_COLORWAY)])
                      for i, g in enumerate(groups_list)}
        else:
            groups_list = sorted(work[slice_col].dropna().unique())
            colors = {g: CHART_COLORWAY[i % len(CHART_COLORWAY)]
                      for i, g in enumerate(groups_list)}

        regular_codes = [c for c in code_order if c != "No Charge"]
        for grp in groups_list:
            subset = work[work[slice_col] == grp]
            counts = subset["_code"].value_counts().reindex(regular_codes, fill_value=0)
            raw_codes = list(counts.index)
            vals = counts.tolist()
            labels = [_CPT_LABELS.get(c, c) for c in raw_codes]

            if n_nc > 0:
                nc_slice = len(nc_rows[nc_rows[slice_col] == grp]) if slice_col in nc_rows.columns else 0
                vals = [nc_slice] + vals
                labels = ["No Charge"] + labels
                raw_codes = ["No Charge"] + raw_codes

            descs = _hover_descs(raw_codes)

            if mode == "pct":
                grp_primary = primary_visits[primary_visits[slice_col] == grp] if slice_col in primary_visits.columns else primary_visits.iloc[0:0]
                denom = grp_primary.index.nunique()
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


def _build_detail_table(dff, c2b=None):
    """Build the AG Grid detail table."""
    if dff.empty:
        return [], []

    # Derive diagnosis category from codes
    if c2b and "DiagnosisCodes" in dff.columns:
        dff = dff.copy()
        dff["DiagnosisCategory"] = dff["DiagnosisCodes"].apply(
            lambda v: primary_category(v, c2b) if pd.notna(v) else ""
        )

    col_header_map = {
        "PatientFullName": "Patient",
        "ScheduledDateTime": "Scheduled",
        "Department": "Department",
        "AppointmentPhysician": "Physician",
        "VisitType": "Visit Type",
        "DiagnosisCategory": "Diagnosis",
        "DiagnosisCodes": "Dx Code",
        "ProcedureCodes": "CPT",
        "Status": "Status",
        "DaysFromCreatedToAppt": "Lead Time (days)",
        "SimulationStatus": "Sim Status",
        "DaysToSimulation": "Days to Sim",
    }

    display_cols = [col for col in col_header_map if col in dff.columns]
    if not display_cols:
        return [], []

    table_df = dff[display_cols].copy()
    if "ScheduledDateTime" in table_df.columns:
        table_df = table_df.sort_values("ScheduledDateTime", ascending=False)
    table_df = table_df.head(500)
    for c in table_df.select_dtypes(include=["datetime64"]).columns:
        table_df[c] = table_df[c].dt.strftime("%m/%d/%Y %I:%M %p")
    table_df = table_df.fillna("--")

    col_defs = []
    for c in display_cols:
        cd = {"field": c, "headerName": col_header_map.get(c, c)}
        if c == "ScheduledDateTime":
            cd["sort"] = "desc"
        col_defs.append(cd)

    return table_df.to_dict("records"), col_defs


clientside_callback(
    """function(n) {
        if (!n) return window.dash_clientside.no_update;
        var gridApi = window.dash_ag_grid && window.dash_ag_grid['cv-detail-grid'];
        if (gridApi && gridApi.api) gridApi.api.exportDataAsCsv({fileName: 'clinic_visits.csv'});
        return window.dash_clientside.no_update;
    }""",
    Output("cv-table-export", "n_clicks"),
    Input("cv-table-export", "n_clicks"),
    prevent_initial_call=True,
)
