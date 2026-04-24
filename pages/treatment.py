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
    DEPARTMENTS, DEPARTMENT_COLORS, CHART_COLORWAY, PRIMARY,
    DEFAULT_LAYOUT, FONT_FAMILY, SEMANTIC_COLORS, NEUTRAL,
    DEFAULT_COLUMN_DEFS, DEFAULT_GRID_OPTIONS, CHART_PAPER_HEIGHT,
    MACHINE_DEPT, MACHINE_COLORS, PRIOR_PERIOD_COLORS,
)
from components.filter_bar import department_chips
from components.diagnosis_filter import diagnosis_accordion, register_diagnosis_callbacks
from components.kpi_card import kpi_card, kpi_placeholder
from components.chart_card import chart_card, register_chart_callbacks
from components.detail_table import detail_table
from components.phi import apply_phi_grid_rules
from utils.charts import apply_default_layout, empty_figure, dept_color
from utils.holidays import get_holidays
from utils.date_slider import (
    month_idx, idx_to_date, MAX_IDX, SLIDER_MARKS,
    preset_to_slider_val, preset_to_exact_dates,
)

dash.register_page(__name__, path="/treatment", name="Treatment", order=8)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_SITE_DEPTS = set(DEPARTMENTS)  # {"Lacey", "Centralia", "Aberdeen"}
_DEFAULT_DATE_PRESET = "12mo"

# Physician role → column mapping
_TX_PHYS_COL = {
    "treating": "TreatingPhysician",
    "billing": "BillingPhysician",
    "consult": "ConsultPhysician",
}

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

_TECHNIQUE_ORDER = ["Electron", "3D Conformal", "IMRT", "VMAT", "SRS/SBRT", "Other"]

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
                    html.Div(
                        id="tx-dept-machine-group",
                        children=[
                            dmc.Group(
                                children=[department_chips("tx")],
                                gap="md",
                            ),
                            dmc.Paper(
                                children=[
                                    dmc.Text("Lacey Machines", size="xs", fw=500, c="#6B7280", mb=4),
                                    dmc.ChipGroup(
                                        children=[],
                                        id="tx-filter-machine",
                                        multiple=True,
                                        value=[],
                                    ),
                                ],
                                p="xs",
                                shadow="md",
                                withBorder=True,
                                radius="md",
                                className="tx-machine-hover-panel",
                            ),
                        ],
                        className="tx-dept-machines",
                    ),
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
                            dcc.Store(id="tx-physician-role", data="treating"),
                            dmc.Paper(
                                children=[
                                    dmc.SegmentedControl(
                                        id="tx-physician-role-ctrl",
                                        data=[
                                            {"value": "treating", "label": "Treating"},
                                            {"value": "billing", "label": "Billing"},
                                            {"value": "consult", "label": "Consult"},
                                        ],
                                        value="treating",
                                        size="xs",
                                        fullWidth=True,
                                        mb="xs",
                                    ),
                                    dmc.ChipGroup(
                                        children=[],
                                        id="tx-filter-physician",
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
                    # Diagnosis accordion
                    diagnosis_accordion("tx"),
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
                    # Table filter badge
                    html.Div(
                        id="tx-grid-filter-badge",
                        children=dmc.Tooltip(
                            label="Table column filters are active — click to scroll to table",
                            position="bottom", withArrow=True, multiline=True, w=220,
                            children=dmc.Badge(
                                "Table Filtered",
                                color="red", variant="filled", size="md",
                                leftSection=DashIconify(icon="mdi:filter", width=14),
                            ),
                        ),
                        style={"display": "none", "cursor": "pointer"},
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
        dmc.Grid(gutter="md", children=[
            dmc.GridCol(kpi_placeholder(), id="tx-kpi-volume", span={"base": 12, "sm": 6, "md": 2}),
            dmc.GridCol(kpi_placeholder(), id="tx-kpi-newstarts", span={"base": 12, "sm": 6, "md": 2}),
            dmc.GridCol(kpi_placeholder(), id="tx-kpi-patients", span={"base": 12, "sm": 6, "md": 2}),
            dmc.GridCol(kpi_placeholder(), id="tx-kpi-elapsed", span={"base": 12, "sm": 6, "md": 2}),
            dmc.GridCol(kpi_placeholder(), id="tx-kpi-fields", span={"base": 12, "sm": 6, "md": 2}),
            dmc.GridCol(kpi_placeholder(), id="tx-kpi-gating", span={"base": 12, "sm": 6, "md": 2}),
        ]),

        # Row 1: Treatment Volume + Cumulative Treatment Volume
        dmc.Grid(gutter="md", children=[
            dmc.GridCol(
                chart_card(
                    "tx-chart-volume",
                    "Treatment Volume",
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
                    extra_controls_left=[
                        dmc.SegmentedControl(
                            id="tx-groupby",
                            data=[
                                {"value": "", "label": "Total"},
                                {"value": "department", "label": "Dept"},
                                {"value": "machine", "label": "Machine"},
                            ],
                            value="department", size="xs",
                        ),
                        html.Div(
                            id="tx-vol-pct-wrap",
                            children=dmc.SegmentedControl(
                                id="tx-vol-pct",
                                data=[
                                    {"value": "count", "label": "Count"},
                                    {"value": "pct", "label": "%"},
                                ],
                                value="count", size="xs",
                            ),
                        ),
                    ],
                    extra_controls=[
                        dmc.SegmentedControl(
                            id="tx-vol-agg",
                            data=[
                                {"value": "D", "label": "Daily"},
                                {"value": "W", "label": "Weekly"},
                                {"value": "M", "label": "Monthly"},
                                {"value": "Y", "label": "Yearly"},
                            ],
                            value="D", size="xs",
                        ),
                    ],
                ),
                span={"base": 12, "md": 6},
            ),
            dmc.GridCol(
                chart_card(
                    "tx-chart-cumulative",
                    "Cumulative Treatment Volume",
                    settings_id="tx-cumulative",
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
                            id="tx-cumulative-mode",
                            data=[
                                {"value": "prior", "label": "Prior Periods"},
                                {"value": "slice", "label": "Slice By"},
                            ],
                            value="prior",
                            size="xs",
                        ),
                        dmc.SegmentedControl(
                            id="tx-cumulative-period-type",
                            data=[
                                {"value": "calendar", "label": "Calendar"},
                                {"value": "rolling", "label": "Rolling"},
                            ],
                            value="calendar",
                            size="xs",
                        ),
                        dmc.SegmentedControl(
                            id="tx-cumulative-slice",
                            data=[
                                {"value": "dept", "label": "Dept"},
                                {"value": "machine", "label": "Machine"},
                                {"value": "physician", "label": "MD"},
                                {"value": "technique", "label": "Technique"},
                            ],
                            value="dept",
                            size="xs",
                            style={"display": "none"},
                        ),
                    ],
                ),
                span={"base": 12, "md": 6},
            ),
        ]),

        # Row 2: Technique Mix + Field Type Mix
        dmc.Grid(gutter="md", children=[
            dmc.GridCol(
                chart_card(
                    "tx-chart-technique",
                    "Technique Mix",
                    settings_id="tx-technique",
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
                    extra_controls_left=[
                        dmc.SegmentedControl(
                            id="tx-tech-pct",
                            data=[
                                {"value": "count", "label": "Count"},
                                {"value": "pct", "label": "%"},
                            ],
                            value="count", size="xs",
                        ),
                    ],
                    extra_controls=[
                        dmc.SegmentedControl(
                            id="tx-tech-agg",
                            data=[
                                {"value": "D", "label": "Daily"},
                                {"value": "W", "label": "Weekly"},
                                {"value": "M", "label": "Monthly"},
                                {"value": "Y", "label": "Yearly"},
                            ],
                            value="D", size="xs",
                        ),
                    ],
                ),
                span={"base": 12, "md": 6},
            ),
            dmc.GridCol(
                chart_card(
                    "tx-chart-fieldtype",
                    "Field Type Mix",
                    settings_id="tx-fieldtype",
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
                    extra_controls_left=[
                        dmc.SegmentedControl(
                            id="tx-fieldtype-pct",
                            data=[
                                {"value": "count", "label": "Count"},
                                {"value": "pct", "label": "%"},
                            ],
                            value="count", size="xs",
                        ),
                    ],
                    extra_controls=[
                        dmc.SegmentedControl(
                            id="tx-fieldtype-agg",
                            data=[
                                {"value": "D", "label": "Daily"},
                                {"value": "W", "label": "Weekly"},
                                {"value": "M", "label": "Monthly"},
                                {"value": "Y", "label": "Yearly"},
                            ],
                            value="D", size="xs",
                        ),
                    ],
                ),
                span={"base": 12, "md": 6},
            ),
        ]),

        # Row 3: Session Duration + Image Guidance
        dmc.Grid(gutter="md", children=[
            dmc.GridCol(
                chart_card(
                    "tx-chart-elapsed",
                    "Duration Distribution",
                    settings_id="tx-elapsed",
                    show_smooth=False,
                    show_settings=True,
                    show_grouping=False,
                    paper_padding="md",
                    extra_controls_left=[
                        dmc.SegmentedControl(
                            id="tx-elapsed-metric",
                            data=[
                                {"value": "session", "label": "Session"},
                                {"value": "beam", "label": "Beam-On"},
                            ],
                            value="session", size="xs",
                        ),
                    ],
                    extra_controls=[
                        dmc.SegmentedControl(
                            id="tx-elapsed-slice",
                            data=[
                                {"value": "", "label": "Total"},
                                {"value": "department", "label": "Dept"},
                                {"value": "machine", "label": "Machine"},
                                {"value": "technique", "label": "Technique"},
                            ],
                            value="department", size="xs",
                        ),
                    ],
                    extra_settings=[
                        html.Div(
                            dmc.Stack(gap=4, children=[
                                dmc.Text("Density Smoothing", size="xs", fw=500, c="#6B7280"),
                                dmc.Slider(
                                    id="tx-elapsed-bw",
                                    min=0, max=5, step=0.25, value=0,
                                    size="xs", showLabelOnHover=True,
                                    updatemode="drag",
                                    marks=[{"value": 0, "label": "Auto", "style": {"fontSize": "9px"}}],
                                    mb=12,
                                ),
                            ]),
                        ),
                    ],
                ),
                span={"base": 12, "md": 6},
            ),
            dmc.GridCol(
                chart_card(
                    "tx-chart-igrt",
                    "Image Guidance",
                    settings_id="tx-igrt",
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
                    extra_controls_left=[
                        dmc.SegmentedControl(
                            id="tx-igrt-pct",
                            data=[
                                {"value": "count", "label": "Count"},
                                {"value": "per_session", "label": "/ Ses"},
                                {"value": "pct_sessions", "label": "% Ses"},
                            ],
                            value="pct_sessions", size="xs",
                        ),
                    ],
                    extra_controls=[
                        dmc.SegmentedControl(
                            id="tx-igrt-agg",
                            data=[
                                {"value": "D", "label": "Daily"},
                                {"value": "W", "label": "Weekly"},
                                {"value": "M", "label": "Monthly"},
                                {"value": "Y", "label": "Yearly"},
                            ],
                            value="D", size="xs",
                        ),
                    ],
                ),
                span={"base": 12, "md": 6},
            ),
        ]),

        # Row 4: New Starts + Gating Utilization
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
                    smooth_default=5,
                    store_data=True,
                    paper_padding="md",
                    extra_controls_left=[
                        dmc.SegmentedControl(
                            id="tx-newstarts-metric",
                            data=[
                                {"value": "course", "label": "By Course"},
                                {"value": "fraction", "label": "By Fraction"},
                            ],
                            value="course",
                            size="xs",
                        ),
                    ],
                    extra_controls=[
                        dmc.SegmentedControl(
                            id="tx-newstarts-agg",
                            data=[
                                {"value": "D", "label": "Daily"},
                                {"value": "W", "label": "Weekly"},
                                {"value": "M", "label": "Monthly"},
                                {"value": "Y", "label": "Yearly"},
                            ],
                            value="W", size="xs",
                        ),
                    ],
                ),
                span={"base": 12, "md": 6},
            ),
            dmc.GridCol(
                chart_card(
                    "tx-chart-gating",
                    "Motion Management",
                    settings_id="tx-gating",
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
                    extra_controls_left=[
                        dmc.Select(
                            id="tx-gating-metric",
                            data=[
                                {"value": "any", "label": "Any"},
                                {"value": "field", "label": "Field Gated"},
                                {"value": "BREATH HOLD", "label": "Breath Hold"},
                                {"value": "AMPLITUDE BASED", "label": "Amplitude"},
                                {"value": "PHASE BASED", "label": "Phase"},
                                {"value": "osms", "label": "OSMS"},
                            ],
                            value="any", size="xs", w=130,
                            allowDeselect=False,
                            comboboxProps={"zIndex": 500},
                        ),
                        dmc.SegmentedControl(
                            id="tx-gating-slice",
                            data=[
                                {"value": "", "label": "Total"},
                                {"value": "department", "label": "Dept"},
                                {"value": "machine", "label": "Machine"},
                            ],
                            value="", size="xs",
                        ),
                        html.Div(
                            id="tx-gating-pct-wrap",
                            children=dmc.SegmentedControl(
                                id="tx-gating-pct",
                                data=[
                                    {"value": "count", "label": "Count"},
                                    {"value": "pct", "label": "%"},
                                ],
                                value="count", size="xs",
                            ),
                        ),
                    ],
                    extra_controls=[
                        dmc.SegmentedControl(
                            id="tx-gating-agg",
                            data=[
                                {"value": "D", "label": "Daily"},
                                {"value": "W", "label": "Weekly"},
                                {"value": "M", "label": "Monthly"},
                                {"value": "Y", "label": "Yearly"},
                            ],
                            value="D", size="xs",
                        ),
                    ],
                ),
                span={"base": 12, "md": 6},
            ),
        ]),

        # Row 5: Multi-Iso Rate + Avg Fields
        dmc.Grid(gutter="md", children=[
            dmc.GridCol(
                chart_card(
                    "tx-chart-multiiso",
                    "Multi-Isocenter Rate",
                    settings_id="tx-multiiso",
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
                    extra_controls_left=[
                        dmc.SegmentedControl(
                            id="tx-multiiso-slice",
                            data=[
                                {"value": "", "label": "Total"},
                                {"value": "department", "label": "Dept"},
                                {"value": "machine", "label": "Machine"},
                                {"value": "technique", "label": "Technique"},
                            ],
                            value="machine", size="xs",
                        ),
                    ],
                    extra_controls=[
                        dmc.SegmentedControl(
                            id="tx-multiiso-agg",
                            data=[
                                {"value": "D", "label": "Daily"},
                                {"value": "W", "label": "Weekly"},
                                {"value": "M", "label": "Monthly"},
                                {"value": "Y", "label": "Yearly"},
                            ],
                            value="D", size="xs",
                        ),
                    ],
                ),
                span={"base": 12, "md": 6},
            ),
            dmc.GridCol(
                chart_card(
                    "tx-chart-avgfields",
                    "Avg Fields / Session",
                    settings_id="tx-avgfields",
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
                    extra_controls_left=[
                        dmc.SegmentedControl(
                            id="tx-avgfields-slice",
                            data=[
                                {"value": "", "label": "Total"},
                                {"value": "department", "label": "Dept"},
                                {"value": "machine", "label": "Machine"},
                                {"value": "technique", "label": "Technique"},
                            ],
                            value="machine", size="xs",
                        ),
                    ],
                    extra_controls=[
                        dmc.SegmentedControl(
                            id="tx-avgfields-agg",
                            data=[
                                {"value": "D", "label": "Daily"},
                                {"value": "W", "label": "Weekly"},
                                {"value": "M", "label": "Monthly"},
                                {"value": "Y", "label": "Yearly"},
                            ],
                            value="D", size="xs",
                        ),
                    ],
                ),
                span={"base": 12, "md": 6},
            ),
        ]),

        # Detail table
        detail_table(
            "tx-detail-grid",
            title="Session Detail",
            export_id="tx-detail-export",
            column_size=None,
            extra_controls=[
                dmc.Button(
                    "Clear Filters",
                    id="tx-table-clear-filters",
                    size="compact-xs",
                    variant="light",
                    color="red",
                    leftSection=DashIconify(icon="mdi:filter-remove", width=14),
                    style={"display": "none"},
                ),
            ],
        ),

        # Stores
        dcc.Store(id="tx-store-kpi-sparklines"),
        dcc.Store(id="tx-store-elapsed"),
        dcc.Store(id="tx-store-cumulative"),
        dcc.Store(id="tx-table-filter-rows"),

        # Interval for periodic refresh
        dcc.Interval(id="tx-interval", interval=300_000, n_intervals=0),
    ],
)


# ---------------------------------------------------------------------------
# Register chart settings callbacks
# ---------------------------------------------------------------------------
register_chart_callbacks([
    {"sid": "tx-elapsed", "gid": "tx-chart-elapsed", "show_smooth": False, "show_grouping": False},
    {"sid": "tx-cumulative", "gid": "tx-chart-cumulative", "show_grouping": False},
    ("tx-volume", "tx-chart-volume", "tx-chart-volume-store"),
    ("tx-technique", "tx-chart-technique", "tx-chart-technique-store"),
    ("tx-fieldtype", "tx-chart-fieldtype", "tx-chart-fieldtype-store"),
    ("tx-igrt", "tx-chart-igrt", "tx-chart-igrt-store"),
    ("tx-newstarts", "tx-chart-newstarts", "tx-chart-newstarts-store"),
    ("tx-gating", "tx-chart-gating", "tx-chart-gating-store"),
    ("tx-multiiso", "tx-chart-multiiso", "tx-chart-multiiso-store"),
    ("tx-avgfields", "tx-chart-avgfields", "tx-chart-avgfields-store"),
])

register_diagnosis_callbacks("tx")


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
        s, e = preset_to_exact_dates(preset)
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
        """function(vals) {
            if (!vals || vals.length === 0) return "Physician";
            if (vals.length === 1) return vals[0].split(", ")[0];
            return vals.length + " selected";
        }""",
        Output("tx-physician-trigger", "children"),
        Input("tx-filter-physician", "value"),
    )

    # --- Physician clear-button visibility ---
    clientside_callback(
        """function(vals) {
            return (vals && vals.length > 0) ? {"display": "inline-flex"} : {"display": "none"};
        }""",
        Output("tx-physician-clear", "style"),
        Input("tx-filter-physician", "value"),
    )

    # --- Physician clear-button action ---
    clientside_callback(
        """function(n) { return []; }""",
        Output("tx-filter-physician", "value", allow_duplicate=True),
        Input("tx-physician-clear", "n_clicks"),
        prevent_initial_call=True,
    )

    # --- Physician role toggle → store + clear selection ---
    clientside_callback(
        """function(role) { return [role, []]; }""",
        Output("tx-physician-role", "data"),
        Output("tx-filter-physician", "value", allow_duplicate=True),
        Input("tx-physician-role-ctrl", "value"),
        prevent_initial_call=True,
    )

    # --- Toggle hover-panel class when Lacey is selected ---
    clientside_callback(
        """function(depts) {
            var hasLacey = depts && depts.indexOf("Lacey") !== -1;
            return hasLacey ? "tx-dept-machines tx-lacey-active"
                            : "tx-dept-machines";
        }""",
        Output("tx-dept-machine-group", "className"),
        Input("tx-filter-department", "value"),
    )

    # --- Clear machine selection when Lacey is deselected ---
    clientside_callback(
        """function(depts, cur) {
            if (!cur || cur.length === 0) return window.dash_clientside.no_update;
            if (depts && depts.indexOf("Lacey") !== -1) return window.dash_clientside.no_update;
            return [];
        }""",
        Output("tx-filter-machine", "value", allow_duplicate=True),
        Input("tx-filter-department", "value"),
        State("tx-filter-machine", "value"),
        prevent_initial_call=True,
    )

    # --- Prune stale machine selections when chips repopulate ---
    clientside_callback(
        """function(chipChildren, currentMachines) {
            if (!currentMachines || currentMachines.length === 0)
                return window.dash_clientside.no_update;
            var vis = [];
            if (chipChildren) {
                var kids = Array.isArray(chipChildren) ? chipChildren : [chipChildren];
                for (var i = 0; i < kids.length; i++) {
                    var v = kids[i] && kids[i].props && kids[i].props.value;
                    if (v) vis.push(v);
                }
            }
            var result = currentMachines.filter(function(m) { return vis.indexOf(m) !== -1; });
            if (result.length === currentMachines.length)
                return window.dash_clientside.no_update;
            return result;
        }""",
        Output("tx-filter-machine", "value", allow_duplicate=True),
        Input("tx-filter-machine", "children"),
        State("tx-filter-machine", "value"),
        prevent_initial_call=True,
    )


_register_tx_filter_callbacks()


# ---------------------------------------------------------------------------
# Physician filter — dynamic from data
# ---------------------------------------------------------------------------
@callback(
    Output("tx-filter-physician", "children"),
    Input("tx-interval", "n_intervals"),
    Input("tx-date-slider", "value"),
    Input("tx-filter-department", "value"),
    Input("tx-filter-machine", "value"),
    Input("tx-diag-store", "data"),
    Input("tx-diag-mode", "data"),
    Input("tx-physician-role", "data"),
)
def _populate_physician_chips(_n, slider_val, departments, machines,
                              diagnosis_cats, diag_mode, physician_role):
    from data.loader import load_treatment_detail
    from utils.diagnosis_categories import build_code_to_category, filter_by_diagnosis
    col = _TX_PHYS_COL.get(physician_role or "treating", "TreatingPhysician")
    try:
        df = load_treatment_detail()
    except Exception:
        return []
    if df.empty or col not in df.columns:
        return []
    # Department
    if departments:
        df = df[df["Department"].isin(departments)]
    # Machine (Lacey only — other sites have single machine)
    if machines and "Machine" in df.columns:
        df = df[(df["Department"] != "Lacey") | df["Machine"].isin(machines)]
    # Diagnosis
    if diagnosis_cats:
        c2b = build_code_to_category()
        if c2b:
            df = filter_by_diagnosis(df, diagnosis_cats, c2b, mode=diag_mode or "primary")
    # Date
    start, end = _get_date_range(slider_val, None)
    df = df[(df["ScheduledDateTime"] >= start) & (df["ScheduledDateTime"] <= end)]
    if df.empty:
        return []
    from components.filter_bar import physician_options, physician_short_name
    return [
        dmc.Chip(physician_short_name(opt["label"]), value=opt["value"], size="xs", variant="filled")
        for opt in physician_options(df[col])
    ]


# ---------------------------------------------------------------------------
# Machine filter — dynamic from data
# ---------------------------------------------------------------------------
@callback(
    Output("tx-filter-machine", "children"),
    Input("tx-interval", "n_intervals"),
    Input("tx-date-slider", "value"),
    Input("tx-filter-department", "value"),
)
def _populate_machine_chips(_n, slider_val, departments):
    """Only show Lacey machines — the only site with multiple machines."""
    from data.loader import load_treatment_detail
    try:
        df = load_treatment_detail()
    except Exception:
        return []
    if df.empty or "Machine" not in df.columns:
        return []
    # Only Lacey rows — Centralia/Aberdeen have 1 machine each (dept == machine)
    df = df[df["Department"] == "Lacey"]
    start, end = _get_date_range(slider_val, None)
    df = df[(df["ScheduledDateTime"] >= start) & (df["ScheduledDateTime"] <= end)]
    if df.empty:
        return []
    machines = sorted(df["Machine"].dropna().unique())
    return [
        dmc.Chip(m, value=m, size="xs", variant="filled")
        for m in machines
    ]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_census_store(df, date_col, group_col, value_col, groups, colors,
                        agg="D", agg_func="sum", y_title="", height=380):
    """Build census-format store data with optional time aggregation.

    Args:
        df: DataFrame with date_col, group_col, and value_col columns.
        agg: "D" (daily), "W" (weekly), "M" (monthly), "Y" (yearly).
        agg_func: "sum", "mean", or "count".
        colors: dict mapping group name → hex color.
    """
    if df.empty:
        return None
    df = df.copy()

    if agg in ("W", "M", "Y"):
        df["_period"] = df[date_col].dt.to_period(agg).dt.to_timestamp()
        dk = "_period"
    else:
        dk = date_col

    if agg_func == "count":
        grouped = df.groupby([dk, group_col]).size().reset_index(name="_v")
    elif agg_func == "mean":
        grouped = df.groupby([dk, group_col])[value_col].mean().reset_index(name="_v")
    else:
        grouped = df.groupby([dk, group_col])[value_col].sum().reset_index(name="_v")

    dates_all = sorted(grouped[dk].dropna().unique())
    if not dates_all:
        return None
    dates_str = [pd.Timestamp(d).isoformat() for d in dates_all]

    series = []
    for grp in groups:
        sub = grouped[grouped[group_col] == grp]
        vals = sub.set_index(dk)["_v"].reindex(dates_all, fill_value=0)
        series.append({
            "name": grp,
            "values": [round(float(v), 2) if pd.notna(v) else 0 for v in vals],
            "color": colors.get(grp, CHART_COLORWAY[0]),
        })

    if not any(any(v > 0 for v in s["values"]) for s in series):
        return None

    return {
        "dates": dates_str,
        "series": series,
        "yTitle": y_title,
        "height": height,
    }


def _to_pct(store_data):
    """Convert census store values from counts to % of total per date."""
    if not store_data or not store_data.get("series"):
        return store_data
    series = store_data["series"]
    n_dates = len(store_data["dates"])
    for di in range(n_dates):
        total = sum(s["values"][di] for s in series if s["values"][di])
        if total > 0:
            for s in series:
                s["values"][di] = round(s["values"][di] / total * 100, 1)
    store_data["yTitle"] = "% of Total"
    return store_data


def _build_day_index_ticks(start_norm, n_days, max_ticks=12):
    """Build tick positions and labels for day-indexed cumulative charts."""
    dates = pd.date_range(start_norm, periods=n_days, freq="D")
    if n_days <= max_ticks:
        positions = list(range(n_days))
        labels = [d.strftime("%-m/%-d") for d in dates]
        return positions, labels
    step = max(1, n_days // max_ticks)
    positions, labels = [], []
    for i in range(0, n_days, step):
        positions.append(i)
        labels.append(dates[i].strftime("%-m/%-d"))
    if positions[-1] != n_days - 1:
        positions.append(n_days - 1)
        labels.append(dates[-1].strftime("%-m/%-d"))
    return positions, labels


def _prepare_cumulative_data(df, start, end, date_preset,
                              mode="prior", period_type="calendar",
                              slice_by="dept", max_prior=10):
    """Prepare cumulative treatment volume data for overlay chart."""
    if df.empty or "ScheduledDateTime" not in df.columns:
        return None

    from utils.cumulative_current_year import setup_current_year_range, apply_current_year_projection
    today = pd.Timestamp.now().normalize()
    start, end, _cy_last_actual = setup_current_year_range(date_preset, mode, start, end)
    if _cy_last_actual is None and end.normalize() > today:
        end = today

    period_days = (end - start).days + 1
    if period_days < 2:
        return None

    if period_days > 365 and period_type == "calendar":
        period_type = "rolling"

    dff_all = df.copy()
    if dff_all.empty:
        return None

    def _cumulative_for_window(dfa, w_start, w_end):
        mask = (dfa["ScheduledDateTime"] >= w_start) & (dfa["ScheduledDateTime"] <= w_end)
        sub = dfa.loc[mask]
        if sub.empty:
            return []
        daily = sub.groupby(sub["ScheduledDateTime"].dt.normalize()).size()
        idx = pd.date_range(w_start.normalize(), w_end.normalize(), freq="D")
        daily = daily.reindex(idx, fill_value=0)
        return daily.cumsum().tolist()

    def _slice_totals_for_window(dfa, w_start, w_end, sb):
        mask = (dfa["ScheduledDateTime"] >= w_start) & (dfa["ScheduledDateTime"] <= w_end)
        sub = dfa.loc[mask]
        if sub.empty:
            return {}
        if sb == "total":
            return {"Total": len(sub)}
        if sb == "dept" and "Department" in sub.columns:
            return sub.groupby("Department").size().to_dict()
        elif sb == "machine" and "Machine" in sub.columns:
            return sub.groupby("Machine").size().to_dict()
        elif sb == "physician" and "TreatingPhysician" in sub.columns:
            counts = sub.groupby("TreatingPhysician").size()
            return {(k.split(",")[0] if "," in k else k): v for k, v in counts.items()}
        elif sb == "technique" and "PlanTechniques" in sub.columns:
            sub = sub.copy()
            sub["_tech"] = sub["PlanTechniques"].apply(_bucket_technique)
            return sub.groupby("_tech").size().to_dict()
        return {}

    n_days = period_days
    start_norm = start.normalize()
    day_indices = list(range(n_days))
    tick_positions, tick_labels = _build_day_index_ticks(start_norm, n_days)

    current_vals = _cumulative_for_window(dff_all, start, end) if not dff_all.empty else [0] * n_days
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
            prior.append({"label": label, "values": vals,
                          "color": PRIOR_PERIOD_COLORS[min(pi, len(PRIOR_PERIOD_COLORS) - 1)]})
            last_prior_start = p_start

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
        slice_colors = {k: MACHINE_COLORS.get(k, CHART_COLORWAY[i % len(CHART_COLORWAY)])
                       for i, k in enumerate(slice_keys_sorted)}
    elif slice_by == "technique":
        slice_colors = {k: _TECHNIQUE_COLORS.get(k, CHART_COLORWAY[i % len(CHART_COLORWAY)])
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
            **_prior_meta,
            "height": 350,
            "yTitle": "Cumulative Treatments",
        }
        if _cy_last_actual is not None:
            apply_current_year_projection(_result, _cy_last_actual, start)
        return _result

    # Slice mode
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
                "color": DEPARTMENT_COLORS.get(dept, CHART_COLORWAY[0]),
            })

    elif slice_by == "machine" and "Machine" in dff_period.columns:
        for m in sorted(dff_period["Machine"].dropna().unique()):
            sub = dff_period[dff_period["Machine"] == m]
            daily = sub.groupby(sub["ScheduledDateTime"].dt.normalize()).size()
            daily = daily.reindex(dates_range, fill_value=0)
            series.append({
                "name": m,
                "values": _trimmed_cumsum(daily),
                "color": MACHINE_COLORS.get(m, CHART_COLORWAY[len(series) % len(CHART_COLORWAY)]),
            })

    elif slice_by == "physician" and "TreatingPhysician" in dff_period.columns:
        for i, phys in enumerate(sorted(dff_period["TreatingPhysician"].dropna().unique())):
            sub = dff_period[dff_period["TreatingPhysician"] == phys]
            daily = sub.groupby(sub["ScheduledDateTime"].dt.normalize()).size()
            daily = daily.reindex(dates_range, fill_value=0)
            series.append({
                "name": phys.split(",")[0] if "," in phys else phys,
                "values": _trimmed_cumsum(daily),
                "color": CHART_COLORWAY[i % len(CHART_COLORWAY)],
            })

    elif slice_by == "technique" and "PlanTechniques" in dff_period.columns:
        dff_period = dff_period.copy()
        dff_period["_tech"] = dff_period["PlanTechniques"].apply(_bucket_technique)
        for tech in [t for t in _TECHNIQUE_ORDER if t in dff_period["_tech"].values]:
            sub = dff_period[dff_period["_tech"] == tech]
            daily = sub.groupby(sub["ScheduledDateTime"].dt.normalize()).size()
            daily = daily.reindex(dates_range, fill_value=0)
            series.append({
                "name": tech,
                "values": _trimmed_cumsum(daily),
                "color": _TECHNIQUE_COLORS.get(tech, CHART_COLORWAY[len(series) % len(CHART_COLORWAY)]),
            })

    dates_iso = [d.isoformat() for d in dates_range]

    return {
        "mode": "slice",
        "dates": dates_iso,
        "series": series,
        "sliceBreakdown": slice_breakdown,
        **_prior_meta,
        "height": 350,
        "yTitle": "Cumulative Treatments",
    }


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
# Shared filter helper — used by all callbacks (data is cached, filtering is fast)
# ---------------------------------------------------------------------------
_TX_FILTER_INPUTS = [
    Input("tx-interval", "n_intervals"),
    Input("tx-date-slider", "value"),
    Input("tx-filter-date-preset", "value"),
    Input("tx-filter-department", "value"),
    Input("tx-filter-physician", "value"),
    Input("tx-filter-machine", "value"),
    Input("tx-diag-store", "data"),
    Input("tx-diag-mode", "data"),
    Input("tx-physician-role", "data"),
]


def _apply_grid_row_filter(df, grid_rows):
    """Filter DataFrame to only rows matching the grid's visible row indices."""
    if grid_rows is None or df is None or df.empty:
        return df
    idx_set = set(int(i) for i in grid_rows)
    return df.loc[df.index.isin(idx_set)]


def _apply_filters(_n, slider_val, date_preset, departments, physician,
                   machines, diagnosis_cats, diag_mode, physician_role,
                   business_days_only=True):
    """Load and filter both Treatment and Treatment-Detail DataFrames.

    When `business_days_only` is True (default), weekends and observed
    holidays are dropped — appropriate for KPIs like "Daily Treatments (avg)"
    and for daily-aggregation charts where weekend zero-points would create
    visual dips. Chart callbacks with a D/W/M/Y toggle pass
    `business_days_only=(agg == "D")` so weekly+ views reflect all activity.

    Returns (df_agg_filtered, df_det_filtered, df_agg_prior, df_det_prior,
             start, end, trend_label, df_det_f).
    """
    from data.loader import load_treatment, load_treatment_detail
    from utils.diagnosis_categories import build_code_to_category, filter_by_diagnosis

    try:
        df_agg = load_treatment()
        df_det = load_treatment_detail()
    except Exception:
        empty = pd.DataFrame()
        return empty, empty, empty, empty, None, None, None

    c2b = build_code_to_category() if diagnosis_cats else {}
    holidays = get_holidays()
    start, end = _get_date_range(slider_val, None)

    # ---- Filter Treatment.csv (aggregated) to site-level rows ----
    if not df_agg.empty:
        df_agg = df_agg[df_agg["Department"].isin(_SITE_DEPTS)].copy()
        if departments:
            df_agg = df_agg[df_agg["Department"].isin(departments)]
        if business_days_only:
            df_agg = df_agg[df_agg["ScheduledDate"].dt.weekday < 5]
            if holidays:
                df_agg = df_agg[~df_agg["ScheduledDate"].dt.normalize().isin(holidays)]
        df_agg_filtered = df_agg[
            (df_agg["ScheduledDate"] >= start) & (df_agg["ScheduledDate"] <= end)
        ]
    else:
        df_agg = pd.DataFrame()
        df_agg_filtered = pd.DataFrame()

    # ---- Filter Treatment-Detail ----
    if not df_det.empty:
        df_det_f = df_det
        if departments:
            df_det_f = df_det_f[df_det_f["Department"].isin(departments)]
        if physician:
            _phys_col = _TX_PHYS_COL.get(physician_role or "treating", "TreatingPhysician")
            if _phys_col in df_det_f.columns:
                df_det_f = df_det_f[df_det_f[_phys_col].isin(physician)]
        if machines and "Machine" in df_det_f.columns:
            df_det_f = df_det_f[(df_det_f["Department"] != "Lacey") | df_det_f["Machine"].isin(machines)]
        if diagnosis_cats:
            df_det_f = filter_by_diagnosis(df_det_f, diagnosis_cats, c2b, mode=diag_mode or "primary")
        if business_days_only:
            df_det_f = df_det_f[df_det_f["ScheduledDateTime"].dt.weekday < 5]
            if holidays:
                df_det_f = df_det_f[~df_det_f["ScheduledDateTime"].dt.normalize().isin(holidays)]
        df_det_filtered = df_det_f[
            (df_det_f["ScheduledDateTime"] >= start) & (df_det_f["ScheduledDateTime"] <= end)
        ]
    else:
        df_det_f = pd.DataFrame()
        df_det_filtered = pd.DataFrame()

    # ---- Prior period for trends ----
    prior_start, prior_end, trend_label = _prior_range(start, end, date_preset)
    df_agg_prior = pd.DataFrame()
    df_det_prior = pd.DataFrame()
    if prior_start is not None and not df_agg.empty:
        df_agg_prior = df_agg[
            (df_agg["ScheduledDate"] >= prior_start) & (df_agg["ScheduledDate"] <= prior_end)
        ]
    if prior_start is not None and not df_det_f.empty:
        df_det_prior = df_det_f[
            (df_det_f["ScheduledDateTime"] >= prior_start) & (df_det_f["ScheduledDateTime"] <= prior_end)
        ]

    return df_agg_filtered, df_det_filtered, df_agg_prior, df_det_prior, start, end, trend_label, df_det_f


# ---------------------------------------------------------------------------
# Callback 1: KPIs + sparklines + detail table (data-filter inputs only)
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Callback 1a: Detail table (no grid filter — it PRODUCES the data)
# ---------------------------------------------------------------------------
@callback(
    Output("tx-detail-grid", "rowData"),
    Output("tx-detail-grid", "columnDefs"),
    *_TX_FILTER_INPUTS,
)
def _update_table(*filt_args):
    _, df_det_filtered, *_ = _apply_filters(*filt_args)
    if df_det_filtered.empty:
        return [], []

    table_cols = [
        ("ScheduledDateTime", "Date", 110),
        ("PatientFullName", "Patient", 160),
        ("Department", "Dept", 90),
        ("Machine", "Machine", 120),
        ("TreatingPhysician", "Supervising MD", 140),
        ("BillingPhysician", "Attending MD", 140),
        ("CourseName", "Course", 120),
        ("PlanNames", "Plan", 200),
        ("PlanTechniques", "Technique", 130),
        ("FractionNumber", "Fx #", 85),
        ("TotalFractions", "Total Fx", 100),
        ("SessionElapsedMinutes", "Session min", 130),
        ("BeamElapsedMinutes", "Beam min", 120),
        ("FieldCount", "Fields", 90),
        ("UniqueIsocenters", "Isocenters", 120),
        ("FieldGating", "Field Gated", 120),
        ("RxGating", "Rx Gating", 140),
        ("HasOSMS", "OSMS", 85),
        ("IsNewStart_ByFraction", "New Start", 115),
    ]
    available_cols = [(c, h, w) for c, h, w in table_cols if c in df_det_filtered.columns]

    col_defs = []
    for col_name, header, width in available_cols:
        cd = {"field": col_name, "headerName": header, "width": width}
        if col_name in ("ScheduledDateTime", "PatientFullName"):
            cd["pinned"] = "left"
        if col_name == "ScheduledDateTime":
            cd["sort"] = "desc"
        elif col_name in ("SessionElapsedMinutes", "BeamElapsedMinutes"):
            cd["valueFormatter"] = {"function": "params.value != null ? params.value.toFixed(1) : ''"}
        col_defs.append(cd)
    # Hidden _row_idx column for grid filter sync
    col_defs.append({"field": "_row_idx", "hide": True})
    col_defs = apply_phi_grid_rules(col_defs)

    tbl = df_det_filtered.sort_values("ScheduledDateTime", ascending=False).head(5000)
    tbl = tbl.copy()
    tbl["_row_idx"] = tbl.index
    if "ScheduledDateTime" in tbl.columns:
        tbl["ScheduledDateTime"] = tbl["ScheduledDateTime"].dt.strftime("%m/%d/%Y")
    row_data = tbl[[c for c, _, _ in available_cols] + ["_row_idx"]].to_dict("records")

    return row_data, col_defs


# ---------------------------------------------------------------------------
# Callback 1b: KPIs + sparklines (WITH grid filter)
# ---------------------------------------------------------------------------
@callback(
    Output("tx-kpi-volume", "children"),
    Output("tx-kpi-newstarts", "children"),
    Output("tx-kpi-patients", "children"),
    Output("tx-kpi-elapsed", "children"),
    Output("tx-kpi-fields", "children"),
    Output("tx-kpi-gating", "children"),
    Output("tx-store-kpi-sparklines", "data"),
    *_TX_FILTER_INPUTS,
    Input("tx-table-filter-rows", "data"),
)
def _update_kpis(*args):
    grid_rows = args[-1]
    filt_args = args[:-1]
    na_kpi = kpi_card("--", "N/A")
    df_agg_filtered, df_det_filtered, df_agg_prior, df_det_prior, start, end, trend_label, *_ = \
        _apply_filters(*filt_args)

    # Apply grid row filter
    df_det_filtered = _apply_grid_row_filter(df_det_filtered, grid_rows)

    if df_agg_filtered.empty and df_det_filtered.empty:
        return (na_kpi,) * 6 + ({},)

    # ==================================================================
    # KPIs + sparkline data
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

    # 1. Daily Treatments (avg per business day) — Treatment-Detail session count.
    # Detail is the canonical source (matches actual machine beam-delivery log);
    # Treatment.csv's CompletedAppointments counts scheduled appointments capped
    # at session count, which diverges on multi-session days and the occasional
    # scheduled-no-delivery appointment.
    if not df_det_filtered.empty and "ScheduledDateTime" in df_det_filtered.columns:
        daily_tx = df_det_filtered.groupby(df_det_filtered["ScheduledDateTime"].dt.normalize()).size()
        val = daily_tx.mean()
        t_text, t_dir = None, None
        if not df_det_prior.empty and "ScheduledDateTime" in df_det_prior.columns:
            prior_daily = df_det_prior.groupby(df_det_prior["ScheduledDateTime"].dt.normalize()).size()
            t_text, t_dir = _trend(val, prior_daily.mean())
            if t_text:
                t_text = f"{t_text} {trend_label}"
        spark_s = daily_tx.sort_index()
        _build_spark(spark_s, "volume", DEPARTMENT_COLORS["Lacey"])
        kpis.append(kpi_card(
            "Daily Treatments (avg)", f"{val:,.1f}",
            accent_color=DEPARTMENT_COLORS["Lacey"],
            trend_text=t_text, trend_direction=t_dir,
            sparkline_id="tx-spark-volume",
        ))
    else:
        kpis.append(na_kpi)

    # 2. New Starts (by fraction — count of Treatment-Detail rows where FractionNumber=1)
    ns_col = "IsNewStart_ByFraction"
    if not df_det_filtered.empty and ns_col in df_det_filtered.columns:
        ns_val = int(df_det_filtered[ns_col].sum())
        t_text, t_dir = None, None
        if not df_det_prior.empty and ns_col in df_det_prior.columns:
            ns_prior = int(df_det_prior[ns_col].sum())
            t_text, t_dir = _trend(ns_val, ns_prior)
            if t_text:
                t_text = f"{t_text} {trend_label}"
        tmp = df_det_filtered[["ScheduledDateTime", ns_col]].copy()
        tmp["_d"] = tmp["ScheduledDateTime"].dt.normalize()
        spark_s = tmp.groupby("_d")[ns_col].sum().sort_index()
        spark_w = spark_s.resample("W").sum()
        if len(spark_w) >= 3:
            sparkline_data["newstarts"] = {
                "labels": [d.isoformat() for d in spark_w.index],
                "values": spark_w.tolist(),
                "color": SEMANTIC_COLORS["info"],
            }
        kpis.append(kpi_card(
            "New Starts (period)", f"{ns_val:,}",
            accent_color=SEMANTIC_COLORS["info"],
            trend_text=t_text, trend_direction=t_dir,
            sparkline_id="tx-spark-newstarts",
        ))
    else:
        kpis.append(na_kpi)

    # 3. Unique Patients (avg per day) — distinct PatientIds per day in Treatment-Detail
    if not df_det_filtered.empty and "PatientId" in df_det_filtered.columns:
        daily_pts = df_det_filtered.groupby(df_det_filtered["ScheduledDateTime"].dt.normalize())["PatientId"].nunique()
        val = daily_pts.mean()
        t_text, t_dir = None, None
        if not df_det_prior.empty and "PatientId" in df_det_prior.columns:
            prior_daily = df_det_prior.groupby(df_det_prior["ScheduledDateTime"].dt.normalize())["PatientId"].nunique()
            t_text, t_dir = _trend(val, prior_daily.mean())
            if t_text:
                t_text = f"{t_text} {trend_label}"
        spark_s = daily_pts.sort_index()
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

    return (*kpis, sparkline_data)


# ---------------------------------------------------------------------------
# Callback 2: Treatment Volume store (groupby + vol_agg)
# ---------------------------------------------------------------------------
@callback(
    Output("tx-chart-volume-store", "data"),
    *_TX_FILTER_INPUTS,
    Input("tx-groupby", "value"),
    Input("tx-vol-agg", "value"),
    Input("tx-vol-pct", "value"),
    Input("tx-table-filter-rows", "data"),
    running=[(Output("tx-chart-volume-loading", "visible"), True, False)],
)
def _update_volume(*args):
    groupby, vol_agg, vol_pct, grid_rows = args[-4], args[-3], args[-2], args[-1]
    filt_args = args[:-4]
    _vol_agg = vol_agg or "D"
    df_agg_filtered, df_det_filtered, *_ = _apply_filters(
        *filt_args, business_days_only=(_vol_agg == "D")
    )
    df_det_filtered = _apply_grid_row_filter(df_det_filtered, grid_rows)
    _by_machine = groupby == "machine"
    _by_total = not groupby

    if _by_machine and not df_det_filtered.empty and "Machine" in df_det_filtered.columns:
        _machines = sorted(df_det_filtered["Machine"].dropna().unique())
        _machine_colors = {
            m: MACHINE_COLORS.get(m, CHART_COLORWAY[i % len(CHART_COLORWAY)])
            for i, m in enumerate(_machines)
        }
    else:
        _machines, _machine_colors = [], {}

    result = None
    # All three slices (Total / Machine / Department) count Treatment-Detail rows
    # so the numbers are internally consistent across slice toggles.
    if _by_total and not df_det_filtered.empty:
        vdf = df_det_filtered[["ScheduledDateTime"]].copy()
        vdf["_d"] = vdf["ScheduledDateTime"].dt.normalize()
        vdf["_grp"] = "Total"
        vdf["_count"] = 1
        result = _build_census_store(
            vdf, "_d", "_grp", "_count",
            ["Total"], {"Total": PRIMARY},
            agg=_vol_agg, agg_func="sum", y_title="Treatments",
        )
    elif _by_machine and _machines and not df_det_filtered.empty:
        vdf = df_det_filtered[["ScheduledDateTime", "Machine"]].copy()
        vdf["_d"] = vdf["ScheduledDateTime"].dt.normalize()
        vdf["_count"] = 1
        result = _build_census_store(
            vdf, "_d", "Machine", "_count", _machines, _machine_colors,
            agg=_vol_agg, agg_func="sum", y_title="Treatments",
        )
    elif not df_det_filtered.empty and "Department" in df_det_filtered.columns:
        vdf = df_det_filtered[["ScheduledDateTime", "Department"]].copy()
        vdf["_d"] = vdf["ScheduledDateTime"].dt.normalize()
        vdf["_count"] = 1
        result = _build_census_store(
            vdf, "_d", "Department", "_count",
            DEPARTMENTS, DEPARTMENT_COLORS,
            agg=_vol_agg, agg_func="sum", y_title="Treatments",
        )
    return _to_pct(result) if vol_pct == "pct" and result else result


# ---------------------------------------------------------------------------
# Callback 3: Technique Mix store
# ---------------------------------------------------------------------------
@callback(
    Output("tx-chart-technique-store", "data"),
    *_TX_FILTER_INPUTS,
    Input("tx-tech-agg", "value"),
    Input("tx-tech-pct", "value"),
    Input("tx-table-filter-rows", "data"),
    running=[(Output("tx-chart-technique-loading", "visible"), True, False)],
)
def _update_technique(*args):
    tech_agg, tech_pct, grid_rows = args[-3], args[-2], args[-1]
    filt_args = args[:-3]
    _tech_agg = tech_agg or "D"
    _, df_det_filtered, *_ = _apply_filters(
        *filt_args, business_days_only=(_tech_agg == "D")
    )
    df_det_filtered = _apply_grid_row_filter(df_det_filtered, grid_rows)

    if not df_det_filtered.empty and "PlanTechniques" in df_det_filtered.columns:
        tdf = df_det_filtered[["ScheduledDateTime", "PlanTechniques"]].copy()
        tdf["Technique"] = tdf["PlanTechniques"].apply(_bucket_technique)
        tdf["_d"] = tdf["ScheduledDateTime"].dt.normalize()
        tdf["_count"] = 1
        present_techs = [t for t in _TECHNIQUE_ORDER if t in tdf["Technique"].values]
        result = _build_census_store(
            tdf, "_d", "Technique", "_count", present_techs, _TECHNIQUE_COLORS,
            agg=_tech_agg, agg_func="sum", y_title="Sessions",
        )
        return _to_pct(result) if tech_pct == "pct" and result else result
    return None


# ---------------------------------------------------------------------------
# Callback 3b: Field Type Mix store
# ---------------------------------------------------------------------------
@callback(
    Output("tx-chart-fieldtype-store", "data"),
    *_TX_FILTER_INPUTS,
    Input("tx-fieldtype-agg", "value"),
    Input("tx-fieldtype-pct", "value"),
    Input("tx-table-filter-rows", "data"),
    running=[(Output("tx-chart-fieldtype-loading", "visible"), True, False)],
)
def _update_fieldtype(*args):
    ft_agg, ft_pct, grid_rows = args[-3], args[-2], args[-1]
    filt_args = args[:-3]
    _ft_agg = ft_agg or "D"
    _, df_det_filtered, *_ = _apply_filters(
        *filt_args, business_days_only=(_ft_agg == "D")
    )
    df_det_filtered = _apply_grid_row_filter(df_det_filtered, grid_rows)

    if df_det_filtered.empty:
        return None
    field_cols = {
        "Fields_Arc": "Arc",
        "Fields_DynamicMLC": "Dynamic MLC",
        "Fields_StaticMLC": "Static MLC",
        "Fields_Electron": "Electron",
    }
    available = {k: v for k, v in field_cols.items() if k in df_det_filtered.columns}
    if not available:
        return None
    fdf = df_det_filtered[["ScheduledDateTime"] + list(available.keys())].copy().fillna(0)
    fdf["_d"] = fdf["ScheduledDateTime"].dt.normalize()
    fdf = fdf.melt(id_vars=["_d"], value_vars=list(available.keys()), var_name="_col", value_name="_val")
    fdf["FieldType"] = fdf["_col"].map(available)
    field_types = [v for v in field_cols.values() if v in fdf["FieldType"].values]
    result = _build_census_store(
        fdf, "_d", "FieldType", "_val", field_types, _FIELD_COLORS,
        agg=_ft_agg, agg_func="sum", y_title="Fields",
    )
    return _to_pct(result) if ft_pct == "pct" and result else result


# ---------------------------------------------------------------------------
# Callback 3c: Cumulative Treatment Volume store
# ---------------------------------------------------------------------------
@callback(
    Output("tx-store-cumulative", "data"),
    *_TX_FILTER_INPUTS,
    Input("tx-cumulative-mode", "value"),
    Input("tx-cumulative-period-type", "value"),
    Input("tx-cumulative-slice", "value"),
    Input("tx-table-filter-rows", "data"),
    running=[(Output("tx-chart-cumulative-loading", "visible"), True, False)],
)
def _update_cumulative(*args):
    cumul_mode, cumul_period_type, cumul_slice, grid_rows = args[-4], args[-3], args[-2], args[-1]
    filt_args = args[:-4]
    # Cumulative chart monotonically accumulates — a Saturday is a small step
    # up, not a dip — so include weekends/holidays to match the underlying
    # session log (and the home page's YTD count).
    results = _apply_filters(*filt_args, business_days_only=False)
    # df_det_f (index 7) is dimension-filtered but NOT date-filtered — needed for prior periods
    df_det_all = results[7] if len(results) > 7 else results[1]
    df_det_all = _apply_grid_row_filter(df_det_all, grid_rows)
    if df_det_all.empty:
        return None
    start, end = results[4], results[5]
    date_preset = filt_args[2]
    return _prepare_cumulative_data(
        df_det_all, start, end, date_preset,
        mode=cumul_mode or "prior",
        period_type=cumul_period_type or "calendar",
        slice_by=cumul_slice or "dept",
        max_prior=10,
    )


# ---------------------------------------------------------------------------
# Callback 4: Session Duration — raw data to store (server-side)
# Bandwidth slider handled clientside for instant feedback.
# ---------------------------------------------------------------------------
@callback(
    Output("tx-store-elapsed", "data"),
    *_TX_FILTER_INPUTS,
    Input("tx-elapsed-slice", "value"),
    Input("tx-elapsed-metric", "value"),
    Input("tx-table-filter-rows", "data"),
    running=[(Output("tx-chart-elapsed-loading", "visible"), True, False)],
)
def _update_elapsed_store(*args):
    elapsed_slice, elapsed_metric, grid_rows = args[-3], args[-2], args[-1]
    filt_args = args[:-3]
    _, df_det_filtered, *_ = _apply_filters(*filt_args)
    df_det_filtered = _apply_grid_row_filter(df_det_filtered, grid_rows)

    _metric_col = "BeamElapsedMinutes" if elapsed_metric == "beam" else "SessionElapsedMinutes"
    if df_det_filtered.empty or _metric_col not in df_det_filtered.columns:
        return None

    need_cols = [_metric_col, "Department", "Machine"]
    if "PlanTechniques" in df_det_filtered.columns:
        need_cols.append("PlanTechniques")
    edf = df_det_filtered[need_cols].copy()
    edf = edf[(edf[_metric_col] > 0) & (edf[_metric_col] <= 60)]
    if edf.empty:
        return None

    _eslice = elapsed_slice or ""
    y_upper = float(min(60, edf[_metric_col].quantile(0.99) + 5))
    _unit = "min"

    # Build groups: [{name, values, color}]
    groups = []
    if not _eslice:
        r, g, b = int(PRIMARY[1:3], 16), int(PRIMARY[3:5], 16), int(PRIMARY[5:7], 16)
        groups.append({
            "name": "",
            "values": edf[_metric_col].tolist(),
            "color": PRIMARY,
            "fillcolor": f"rgba({r},{g},{b},0.35)",
        })
    elif _eslice == "technique":
        if "PlanTechniques" in edf.columns:
            edf["_tech"] = edf["PlanTechniques"].apply(_bucket_technique)
        else:
            edf["_tech"] = "Other"
        for tech in _TECHNIQUE_ORDER:
            sub = edf[edf["_tech"] == tech][_metric_col]
            if sub.empty:
                continue
            color = _TECHNIQUE_COLORS.get(tech, CHART_COLORWAY[0])
            groups.append({"name": tech, "values": sub.tolist(), "color": color})
    else:
        group_col = "Department" if _eslice == "department" else "Machine"
        for grp in sorted(edf[group_col].dropna().unique()):
            sub = edf[edf[group_col] == grp][_metric_col]
            if group_col == "Department":
                color = DEPARTMENT_COLORS.get(grp, CHART_COLORWAY[0])
            else:
                color = MACHINE_COLORS.get(grp, CHART_COLORWAY[0])
            groups.append({"name": grp, "values": sub.tolist(), "color": color})

    result = {
        "groups": groups,
        "yUpper": y_upper,
        "mode": "density" if not _eslice else "violin",
        "unit": _unit,
    }
    if not _eslice and groups:
        vals = groups[0]["values"]
        result["median"] = float(np.median(vals))
    return result


# ---------------------------------------------------------------------------
# Callback 5a: Image Guidance (CBCT / PortFilm from Downtime-Fields)
# ---------------------------------------------------------------------------
_IGRT_COLORS = {
    "CBCT": CHART_COLORWAY[1],       # blue
    "Port Film": CHART_COLORWAY[4],  # orange
}

_IGRT_TYPE_MAP = {
    "Image": "CBCT",
    "PortFilm": "Port Film",
}


def _igrt_per_session(store_data, sessions_with_type):
    """Convert IGRT counts to average per session when that image type is used.

    sessions_with_type: dict mapping (date_iso, image_type) → count of
    unique sessions that had at least one image of that type.
    """
    if not store_data or not store_data.get("series") or not sessions_with_type:
        return store_data
    for di, d in enumerate(store_data["dates"]):
        for s in store_data["series"]:
            denom = sessions_with_type.get((d, s["name"]), 0)
            if denom > 0:
                s["values"][di] = round(s["values"][di] / denom, 2)
            else:
                s["values"][di] = 0
    store_data["yTitle"] = "per Session"
    return store_data


def _igrt_pct_sessions(store_data, sessions_with_type, tx_sessions):
    """Convert to % of treatment sessions containing each image type.

    sessions_with_type: dict mapping (date_iso, image_type) → count of
    unique sessions that had at least one image of that type.
    tx_sessions: dict mapping date_iso → total session count.
    """
    if not store_data or not store_data.get("series") or not tx_sessions:
        return store_data
    for di, d in enumerate(store_data["dates"]):
        denom = tx_sessions.get(d, 0)
        if denom > 0:
            for s in store_data["series"]:
                numerator = sessions_with_type.get((d, s["name"]), 0)
                s["values"][di] = round(numerator / denom * 100, 1)
        else:
            for s in store_data["series"]:
                s["values"][di] = 0
    store_data["yTitle"] = "% of Sessions"
    return store_data


@callback(
    Output("tx-chart-igrt-store", "data"),
    Input("tx-interval", "n_intervals"),
    Input("tx-date-slider", "value"),
    Input("tx-filter-date-preset", "value"),
    Input("tx-filter-department", "value"),
    Input("tx-igrt-agg", "value"),
    Input("tx-igrt-pct", "value"),
    running=[(Output("tx-chart-igrt-loading", "visible"), True, False)],
)
def _update_igrt(_n, slider_val, date_preset, departments,
                 igrt_agg, igrt_pct):
    from data.loader import load_downtime_fields_imaging

    df_all = load_downtime_fields_imaging()
    if df_all.empty:
        return None

    # Date filter
    start, end = _get_date_range(slider_val, None)
    df_all = df_all[(df_all["ActivityDate"] >= start) & (df_all["ActivityDate"] <= end)]

    _agg = igrt_agg or "D"
    # Exclude weekends/holidays only for daily aggregation (avoids visual
    # zero-dips); weekly+ rolls up all activity.
    if _agg == "D":
        df_all = df_all[df_all["ActivityDate"].dt.weekday < 5]
        holidays = get_holidays()
        if holidays:
            df_all = df_all[~df_all["ActivityDate"].dt.normalize().isin(holidays)]

    # Department filter via Site
    if departments:
        df_all = df_all[df_all["Site"].isin(departments)]

    if df_all.empty:
        return None

    df_all["_d"] = df_all["ActivityDate"].dt.normalize()

    # Imaging rows only for the chart
    df = df_all[df_all["RecordType"].isin(["Image", "PortFilm"])].copy()
    if df.empty:
        return None

    df["ImageType"] = df["RecordType"].map(_IGRT_TYPE_MAP).fillna(df["RecordType"])
    df["_count"] = 1

    present = [t for t in _IGRT_TYPE_MAP.values() if t in df["ImageType"].values]
    if not present:
        return None
    result = _build_census_store(
        df, "_d", "ImageType", "_count", present, _IGRT_COLORS,
        agg=_agg, agg_func="sum", y_title="Acquisitions",
    )

    # Rate modes: per session or % of sessions
    if igrt_pct in ("per_session", "pct_sessions") and result and result.get("dates"):
        # Sessions with each image type (unique patients per period)
        img = df.copy()
        if _agg in ("W", "M", "Y"):
            img["_pd"] = img["_d"].dt.to_period(_agg).dt.to_timestamp()
        else:
            img["_pd"] = img["_d"]
        sess_by_type = (
            img.groupby(["_pd", "ImageType"])["PatientId"]
            .nunique()
            .to_dict()
        )
        swt_map = {
            (pd.Timestamp(d).isoformat(), t): int(c)
            for (d, t), c in sess_by_type.items()
        }

        if igrt_pct == "per_session":
            result = _igrt_per_session(result, swt_map)
        else:
            # Total treatment sessions for the denominator
            df_tx = df_all[df_all["RecordType"] == "Treatment"]
            if not df_tx.empty:
                tx_sess = df_tx.copy()
                if _agg in ("W", "M", "Y"):
                    tx_sess["_pd"] = tx_sess["_d"].dt.to_period(_agg).dt.to_timestamp()
                else:
                    tx_sess["_pd"] = tx_sess["_d"]
                tx_counts = tx_sess.groupby("_pd")["PatientId"].nunique()
                tx_map = {d.isoformat(): int(c) for d, c in tx_counts.items()}
                result = _igrt_pct_sessions(result, swt_map, tx_map)

    return result


# ---------------------------------------------------------------------------
# Callback 5b: New Starts (own metric + agg toggles)
# ---------------------------------------------------------------------------
@callback(
    Output("tx-chart-newstarts-store", "data"),
    *_TX_FILTER_INPUTS,
    Input("tx-groupby", "value"),
    Input("tx-newstarts-metric", "value"),
    Input("tx-newstarts-agg", "value"),
    Input("tx-table-filter-rows", "data"),
    running=[(Output("tx-chart-newstarts-loading", "visible"), True, False)],
)
def _update_newstarts(*args):
    groupby, newstarts_metric, ns_agg, grid_rows = args[-4], args[-3], args[-2], args[-1]
    filt_args = args[:-4]
    _agg = ns_agg or "D"
    df_agg_filtered, df_det_filtered, *_ = _apply_filters(
        *filt_args, business_days_only=(_agg == "D")
    )
    df_det_filtered = _apply_grid_row_filter(df_det_filtered, grid_rows)

    _by_machine = groupby == "machine"
    _by_total = not groupby

    if _by_machine and not df_det_filtered.empty and "Machine" in df_det_filtered.columns:
        _machines = sorted(df_det_filtered["Machine"].dropna().unique())
        _machine_colors = {
            m: MACHINE_COLORS.get(m, CHART_COLORWAY[i % len(CHART_COLORWAY)])
            for i, m in enumerate(_machines)
        }
    else:
        _machines, _machine_colors = [], {}

    # All slices count Treatment-Detail rows where the new-start flag is true.
    # "fraction" mode uses IsNewStart_ByFraction (one row per first-fraction of a plan);
    # "course" mode uses IsNewStart_ByCourse (one row per first-ever course fraction).
    ns_metric_det = ("IsNewStart_ByCourse"
                     if newstarts_metric == "course"
                     else "IsNewStart_ByFraction")
    if df_det_filtered.empty or ns_metric_det not in df_det_filtered.columns:
        return None
    nsdf = df_det_filtered[["ScheduledDateTime", "Department", "Machine", ns_metric_det]].copy()
    nsdf["_d"] = nsdf["ScheduledDateTime"].dt.normalize()
    if _by_total:
        nsdf["_grp"] = "Total"
        return _build_census_store(
            nsdf, "_d", "_grp", ns_metric_det,
            ["Total"], {"Total": PRIMARY},
            agg=_agg, agg_func="sum", y_title="New Starts",
        )
    elif _by_machine and _machines:
        return _build_census_store(
            nsdf, "_d", "Machine", ns_metric_det, _machines, _machine_colors,
            agg=_agg, agg_func="sum", y_title="New Starts",
        )
    elif "Department" in nsdf.columns:
        return _build_census_store(
            nsdf, "_d", "Department", ns_metric_det,
            DEPARTMENTS, DEPARTMENT_COLORS,
            agg=_agg, agg_func="sum", y_title="New Starts",
        )
    return None


# ---------------------------------------------------------------------------
# Shared helper for sliced census store
# ---------------------------------------------------------------------------
def _sliced_store(df, date_col, val_col, sliceby, agg, agg_func, y_title):
    """Build census store sliced by Total/Dept/Machine/Technique."""
    _slice = sliceby or ""
    if _slice == "technique" and "PlanTechniques" in df.columns:
        df = df.copy()
        df["Technique"] = df["PlanTechniques"].apply(_bucket_technique)

    if not _slice:
        df = df.copy()
        df["_grp"] = "Total"
        return _build_census_store(
            df, date_col, "_grp", val_col, ["Total"], {"Total": PRIMARY},
            agg=agg, agg_func=agg_func, y_title=y_title,
        )
    elif _slice == "technique" and "Technique" in df.columns:
        present = [t for t in _TECHNIQUE_ORDER if t in df["Technique"].values]
        return _build_census_store(
            df, date_col, "Technique", val_col, present, _TECHNIQUE_COLORS,
            agg=agg, agg_func=agg_func, y_title=y_title,
        )
    elif _slice == "machine":
        machines = sorted(df["Machine"].dropna().unique())
        mc = {m: MACHINE_COLORS.get(m, CHART_COLORWAY[i % len(CHART_COLORWAY)])
              for i, m in enumerate(machines)}
        return _build_census_store(
            df, date_col, "Machine", val_col, machines, mc,
            agg=agg, agg_func=agg_func, y_title=y_title,
        )
    else:
        return _build_census_store(
            df, date_col, "Department", val_col, DEPARTMENTS, DEPARTMENT_COLORS,
            agg=agg, agg_func=agg_func, y_title=y_title,
        )


# ---------------------------------------------------------------------------
# Callback 5c: Multi-Isocenter Rate
# ---------------------------------------------------------------------------
@callback(
    Output("tx-chart-multiiso-store", "data"),
    *_TX_FILTER_INPUTS,
    Input("tx-multiiso-slice", "value"),
    Input("tx-multiiso-agg", "value"),
    Input("tx-table-filter-rows", "data"),
    running=[(Output("tx-chart-multiiso-loading", "visible"), True, False)],
)
def _update_multiiso(*args):
    sliceby, agg, grid_rows = args[-3], args[-2], args[-1]
    filt_args = args[:-3]
    _agg = agg or "D"
    _, df_det_filtered, *_ = _apply_filters(
        *filt_args, business_days_only=(_agg == "D")
    )
    df_det_filtered = _apply_grid_row_filter(df_det_filtered, grid_rows)

    if df_det_filtered.empty or "UniqueIsocenters" not in df_det_filtered.columns:
        return None
    cols = ["ScheduledDateTime", "UniqueIsocenters", "Department", "Machine"]
    if "PlanTechniques" in df_det_filtered.columns:
        cols.append("PlanTechniques")
    cdf = df_det_filtered[cols].dropna(subset=["UniqueIsocenters"]).copy()
    cdf["_d"] = cdf["ScheduledDateTime"].dt.normalize()
    cdf["_multi"] = (cdf["UniqueIsocenters"] > 1).astype(float) * 100
    return _sliced_store(cdf, "_d", "_multi", sliceby, _agg, "mean",
                         "% Multi-Iso Sessions")


# ---------------------------------------------------------------------------
# Callback 5d: Avg Fields / Session
# ---------------------------------------------------------------------------
@callback(
    Output("tx-chart-avgfields-store", "data"),
    *_TX_FILTER_INPUTS,
    Input("tx-avgfields-slice", "value"),
    Input("tx-avgfields-agg", "value"),
    Input("tx-table-filter-rows", "data"),
    running=[(Output("tx-chart-avgfields-loading", "visible"), True, False)],
)
def _update_avgfields(*args):
    sliceby, agg, grid_rows = args[-3], args[-2], args[-1]
    filt_args = args[:-3]
    _agg = agg or "D"
    _, df_det_filtered, *_ = _apply_filters(
        *filt_args, business_days_only=(_agg == "D")
    )
    df_det_filtered = _apply_grid_row_filter(df_det_filtered, grid_rows)

    if df_det_filtered.empty or "FieldCount" not in df_det_filtered.columns:
        return None
    cols = ["ScheduledDateTime", "FieldCount", "Department", "Machine"]
    if "PlanTechniques" in df_det_filtered.columns:
        cols.append("PlanTechniques")
    cdf = df_det_filtered[cols].dropna(subset=["FieldCount"]).copy()
    cdf["_d"] = cdf["ScheduledDateTime"].dt.normalize()
    return _sliced_store(cdf, "_d", "FieldCount", sliceby, _agg, "mean",
                         "Avg Fields / Session")


# ---------------------------------------------------------------------------
# Callback 6: Motion Management (gating_metric + gating_slice)
# ---------------------------------------------------------------------------
@callback(
    Output("tx-chart-gating-store", "data"),
    *_TX_FILTER_INPUTS,
    Input("tx-gating-metric", "value"),
    Input("tx-gating-slice", "value"),
    Input("tx-gating-agg", "value"),
    Input("tx-gating-pct", "value"),
    Input("tx-table-filter-rows", "data"),
    running=[(Output("tx-chart-gating-loading", "visible"), True, False)],
)
def _update_gating(*args):
    gating_metric, gating_slice, gating_agg, gating_pct, grid_rows = args[-5], args[-4], args[-3], args[-2], args[-1]
    filt_args = args[:-5]
    _metric = gating_metric or "any"
    _slice = gating_slice or ""
    _agg = gating_agg or "D"
    _, df_det_filtered, *_ = _apply_filters(
        *filt_args, business_days_only=(_agg == "D")
    )
    df_det_filtered = _apply_grid_row_filter(df_det_filtered, grid_rows)

    if df_det_filtered.empty:
        return None

    # Build boolean flag column based on selected metric
    gdf = df_det_filtered[["ScheduledDateTime", "Department", "Machine",
                           "FieldGating", "RxGating", "HasOSMS"]].copy()
    gdf["_d"] = gdf["ScheduledDateTime"].dt.normalize()

    if _metric == "any":
        gdf["_flag"] = (
            (gdf["FieldGating"] == 1)
            | gdf["RxGating"].fillna("").ne("")
            | (gdf["HasOSMS"] == 1)
        ).astype(float)
    elif _metric == "field":
        gdf["_flag"] = gdf["FieldGating"].fillna(0).astype(float)
    elif _metric == "osms":
        gdf["_flag"] = gdf["HasOSMS"].fillna(0).astype(float)
    else:
        gdf["_flag"] = (gdf["RxGating"].fillna("") == _metric).astype(float)

    gdf["_pct"] = gdf["_flag"] * 100

    if not _slice:
        gdf["_grp"] = "Total"
        result = _build_census_store(
            gdf, "_d", "_grp", "_pct", ["Total"], {"Total": PRIMARY},
            agg=_agg, agg_func="mean", y_title="% of Sessions",
        )
    elif _slice == "machine":
        machines = sorted(gdf["Machine"].dropna().unique())
        mc = {m: MACHINE_COLORS.get(m, CHART_COLORWAY[i % len(CHART_COLORWAY)])
              for i, m in enumerate(machines)}
        result = _build_census_store(
            gdf, "_d", "Machine", "_pct", machines, mc,
            agg=_agg, agg_func="mean", y_title="% of Sessions",
        )
    else:
        result = _build_census_store(
            gdf, "_d", "Department", "_pct", DEPARTMENTS, DEPARTMENT_COLORS,
            agg=_agg, agg_func="mean", y_title="% of Sessions",
        )

    if result and result.get("series") and len(result["series"]) > 1:
        result["stacked"] = False
    if gating_pct == "pct" and result:
        result = _to_pct(result)
    return result


# ---------------------------------------------------------------------------
# Clientside callbacks — KPI sparklines via store + smooth slider
# ---------------------------------------------------------------------------

clientside_callback("""function() {
        var fig = window.dash_clientside.sparklines.smoothTxVolume.apply(null, arguments);
        return window.dash_clientside.chartDeferred.wrap("tx-spark-volume", fig);
    }""",
    Output("tx-spark-volume", "figure"),
    Input("tx-store-kpi-sparklines", "data"),
    Input("tx-smooth-slider", "value"),
    prevent_initial_call=True,
)

clientside_callback("""function() {
        var fig = window.dash_clientside.sparklines.smoothTxNewstarts.apply(null, arguments);
        return window.dash_clientside.chartDeferred.wrap("tx-spark-newstarts", fig);
    }""",
    Output("tx-spark-newstarts", "figure"),
    Input("tx-store-kpi-sparklines", "data"),
    Input("tx-smooth-slider", "value"),
    prevent_initial_call=True,
)

clientside_callback("""function() {
        var fig = window.dash_clientside.sparklines.smoothTxPatients.apply(null, arguments);
        return window.dash_clientside.chartDeferred.wrap("tx-spark-patients", fig);
    }""",
    Output("tx-spark-patients", "figure"),
    Input("tx-store-kpi-sparklines", "data"),
    Input("tx-smooth-slider", "value"),
    prevent_initial_call=True,
)

clientside_callback("""function() {
        var fig = window.dash_clientside.sparklines.smoothTxElapsed.apply(null, arguments);
        return window.dash_clientside.chartDeferred.wrap("tx-spark-elapsed", fig);
    }""",
    Output("tx-spark-elapsed", "figure"),
    Input("tx-store-kpi-sparklines", "data"),
    Input("tx-smooth-slider", "value"),
    prevent_initial_call=True,
)

clientside_callback("""function() {
        var fig = window.dash_clientside.sparklines.smoothTxFields.apply(null, arguments);
        return window.dash_clientside.chartDeferred.wrap("tx-spark-fields", fig);
    }""",
    Output("tx-spark-fields", "figure"),
    Input("tx-store-kpi-sparklines", "data"),
    Input("tx-smooth-slider", "value"),
    prevent_initial_call=True,
)

clientside_callback("""function() {
        var fig = window.dash_clientside.sparklines.smoothTxGating.apply(null, arguments);
        return window.dash_clientside.chartDeferred.wrap("tx-spark-gating", fig);
    }""",
    Output("tx-spark-gating", "figure"),
    Input("tx-store-kpi-sparklines", "data"),
    Input("tx-smooth-slider", "value"),
    prevent_initial_call=True,
)


# ---------------------------------------------------------------------------
# Clientside: elapsed violin/density from store + bandwidth (instant feedback)
# ---------------------------------------------------------------------------
clientside_callback(
    """function(storeData, bw) {
        if (!storeData || !storeData.groups || storeData.groups.length === 0) {
            return window.dash_clientside.no_update;
        }
        var groups = storeData.groups;
        var yUpper = storeData.yUpper || 30;
        var isDensity = storeData.mode === "density";
        var bwVal = (bw && bw > 0) ? bw : 0;
        var traces = [];

        for (var i = 0; i < groups.length; i++) {
            var g = groups[i];
            var traceObj = {
                type: "violin",
                name: g.name,
                line: {color: g.color},
                meanline: {visible: true},
                points: false,
                spanmode: "soft"
            };
            if (bwVal > 0) traceObj.bandwidth = bwVal;

            if (isDensity) {
                traceObj.x = g.values;
                traceObj.side = "positive";
                traceObj.fillcolor = g.fillcolor || g.color;
                traceObj.hoverinfo = "none";
                traceObj.meanline = {visible: false};
            } else {
                traceObj.y = g.values;
                traceObj.fillcolor = g.color;
                traceObj.opacity = 0.6;
                traceObj.box = {visible: true};
                traceObj.scalemode = "width";
                traceObj.width = 0.6;
            }
            traces.push(traceObj);
        }

        var _isDark = document.documentElement.getAttribute("data-theme") === "dark";
        var layout = Object.assign({}, window._defaultLayout || {}, {
            showlegend: false,
            margin: {l: 48, r: 16, t: isDensity ? 28 : 8, b: isDensity ? 36 : 24},
            violinmode: "group",
            plot_bgcolor: "rgba(0,0,0,0)",
            paper_bgcolor: "rgba(0,0,0,0)",
            font: {color: _isDark ? "#E6E7EC" : "#1A1A2E"}
        });

        var _gridColor = _isDark ? "#262932" : "#F0F0F0";
        var _medianTextColor = _isDark ? "#D1D5DB" : "#374151";
        if (isDensity) {
            layout.xaxis = {title: {text: "Minutes", font: {size: 11}}, range: [0, yUpper], gridcolor: _gridColor};
            layout.yaxis = {title: {text: "Density", font: {size: 11}}, showticklabels: false, showgrid: false};
            var med = storeData.median;
            if (med != null) {
                layout.shapes = [{
                    type: "line", x0: med, x1: med, yref: "paper", y0: 0, y1: 1,
                    line: {color: "#6B7280", width: 1, dash: "dot"}
                }];
                layout.annotations = [{
                    x: med, yref: "paper", y: 1, yanchor: "bottom", xanchor: "center",
                    text: "Median " + med.toFixed(1) + " min",
                    showarrow: false, font: {size: 11, color: _medianTextColor},
                    yshift: 4
                }];
            }
        } else {
            layout.yaxis = {title: {text: "Minutes", font: {size: 11}}, range: [0, yUpper], gridcolor: _gridColor};
            layout.xaxis = {gridcolor: _gridColor};
        }

        var __fig = ({data: traces, layout: layout});
        return window.dash_clientside.chartDeferred.wrap("tx-chart-elapsed", __fig);
    }""",
    Output("tx-chart-elapsed", "figure"),
    Input("tx-store-elapsed", "data"),
    Input("tx-elapsed-bw", "value"),
    prevent_initial_call=True,
)


# ---------------------------------------------------------------------------
# Groupby toggle: CSS dim class + hide stacked/grouped in Total mode
# ---------------------------------------------------------------------------
_SLICE_CLASS_JS = """function(val) {
    return (val && val !== "total") ? "slice-group-active" : "slice-total-active";
}"""
for _sc_id in ["tx-groupby", "tx-elapsed-slice", "tx-gating-slice",
                "tx-multiiso-slice", "tx-avgfields-slice", "tx-cumulative-slice"]:
    clientside_callback(
        _SLICE_CLASS_JS,
        Output(_sc_id, "className"),
        Input(_sc_id, "value"),
    )

# Hide stacked/grouped toggle when Total (single series) or line chart
_HIDE_STACK_JS = """function(sliceVal, chartType) {
    var single = !sliceVal || sliceVal === "" || sliceVal === "total";
    return (single || chartType === "line") ? {"display": "none"} : {};
}"""
clientside_callback(
    _HIDE_STACK_JS,
    Output("tx-volume-settings-stack-wrap", "style", allow_duplicate=True),
    Input("tx-groupby", "value"),
    Input("tx-volume-settings-type", "value"),
    prevent_initial_call="initial_duplicate",
)

# Hide #/% toggle and force # when Total (single series)
_HIDE_PCT_JS = """function(sliceVal) {
    return (!sliceVal || sliceVal === "") ? {"display": "none"} : {};
}"""
_RESET_PCT_JS = """function(sliceVal) {
    return (!sliceVal || sliceVal === "") ? "count" : window.dash_clientside.no_update;
}"""
clientside_callback(_HIDE_PCT_JS, Output("tx-vol-pct-wrap", "style"), Input("tx-groupby", "value"))
clientside_callback(_RESET_PCT_JS, Output("tx-vol-pct", "value", allow_duplicate=True), Input("tx-groupby", "value"), prevent_initial_call=True)
clientside_callback(_HIDE_PCT_JS, Output("tx-gating-pct-wrap", "style"), Input("tx-gating-slice", "value"))
clientside_callback(_RESET_PCT_JS, Output("tx-gating-pct", "value", allow_duplicate=True), Input("tx-gating-slice", "value"), prevent_initial_call=True)

clientside_callback(
    _HIDE_STACK_JS,
    Output("tx-gating-settings-stack-wrap", "style", allow_duplicate=True),
    Input("tx-gating-slice", "value"),
    Input("tx-gating-settings-type", "value"),
    prevent_initial_call="initial_duplicate",
)

for _cx_sid, _cx_slice in [("tx-multiiso", "tx-multiiso-slice"),
                           ("tx-avgfields", "tx-avgfields-slice")]:
    clientside_callback(
        _HIDE_STACK_JS,
        Output(f"{_cx_sid}-settings-stack-wrap", "style", allow_duplicate=True),
        Input(_cx_slice, "value"),
        Input(f"{_cx_sid}-settings-type", "value"),
        prevent_initial_call="initial_duplicate",
    )


# ---------------------------------------------------------------------------
# Clientside callbacks — chart rendering with stacked/grouped support
# ---------------------------------------------------------------------------
# Inline wrapper reorders args so Dash Input/State ordering matches the
# smoothChartWithType(rawData, smoothPct, chartType, currentFig, stackOverride)
# signature (Inputs before States).
def _census_render(chart_id):
    """Per-chart factory: bakes chart_id into the callback JS so the wrapped
    figure can be routed through chartDeferred.wrap() for staggered render."""
    return f"""function(rawData, smoothPct, chartType, stackOverride, currentFig) {{
        var fig = window.dash_clientside.census.smoothChartWithType(
            rawData, smoothPct, chartType, currentFig, stackOverride
        );
        if (fig && fig !== window.dash_clientside.no_update && rawData && rawData.series) {{
            if (rawData.series.length <= 1) {{
                fig.layout = fig.layout || {{}};
                fig.layout.showlegend = false;
            }}
        }}
        return window.dash_clientside.chartDeferred.wrap("{chart_id}", fig);
    }}"""


_CENSUS_RENDER = """function(rawData, smoothPct, chartType, stackOverride, currentFig) {
    var fig = window.dash_clientside.census.smoothChartWithType(
        rawData, smoothPct, chartType, currentFig, stackOverride
    );
    if (fig && fig !== window.dash_clientside.no_update && rawData && rawData.series) {
        if (rawData.series.length <= 1) {
            fig.layout = fig.layout || {};
            fig.layout.showlegend = false;
        }
    }
    return fig;
}"""

clientside_callback(
    _census_render("tx-chart-volume"),
    Output("tx-chart-volume", "figure"),
    Input("tx-chart-volume-store", "data"),
    Input("tx-volume-settings-smooth", "value"),
    Input("tx-volume-settings-type", "value"),
    Input("tx-volume-settings-stack", "value"),
    State("tx-chart-volume", "figure"),
    prevent_initial_call=True,
)

clientside_callback(
    _census_render("tx-chart-technique"),
    Output("tx-chart-technique", "figure"),
    Input("tx-chart-technique-store", "data"),
    Input("tx-technique-settings-smooth", "value"),
    Input("tx-technique-settings-type", "value"),
    Input("tx-technique-settings-stack", "value"),
    State("tx-chart-technique", "figure"),
    prevent_initial_call=True,
)

clientside_callback(
    _census_render("tx-chart-fieldtype"),
    Output("tx-chart-fieldtype", "figure"),
    Input("tx-chart-fieldtype-store", "data"),
    Input("tx-fieldtype-settings-smooth", "value"),
    Input("tx-fieldtype-settings-type", "value"),
    Input("tx-fieldtype-settings-stack", "value"),
    State("tx-chart-fieldtype", "figure"),
    prevent_initial_call=True,
)

clientside_callback("""function() {
        var fig = window.dash_clientside.cumulative.renderWithProjectToggle.apply(null, arguments);
        return window.dash_clientside.chartDeferred.wrap("tx-chart-cumulative", fig);
    }""",
    Output("tx-chart-cumulative", "figure"),
    Input("tx-store-cumulative", "data"),
    Input("tx-cumulative-settings-smooth", "value"),
    Input("tx-cumulative-settings-type", "value"),
    Input("tx-cumulative-settings-stack", "value"),
    Input("tx-cumulative-settings-prior-periods", "value"),

    Input("tx-cumulative-project", "checked"),
    State("tx-chart-cumulative", "figure"),
    prevent_initial_call=True,
)

# Cumulative: show/hide slice selector vs period-type based on mode
clientside_callback(
    """function(mode) {
        var isSlice = mode === "slice";
        return [
            isSlice ? {"display": "flex"} : {"display": "none"},
            isSlice ? {"display": "none"} : {"display": "flex"}
        ];
    }""",
    Output("tx-cumulative-slice", "style"),
    Output("tx-cumulative-period-type", "style"),
    Input("tx-cumulative-mode", "value"),
)

# Cumulative: cap prior-periods slider to available data
clientside_callback(
    """function(storeData, currentPtValue) {
        return window.dash_clientside.cumulative.updatePriorControls(storeData, currentPtValue);
    }""",
    Output("tx-cumulative-period-type", "data"),
    Output("tx-cumulative-period-type", "value", allow_duplicate=True),
    Output("tx-cumulative-settings-prior-periods", "max"),
    Output("tx-cumulative-settings-prior-periods", "marks"),
    Input("tx-store-cumulative", "data"),
    State("tx-cumulative-period-type", "value"),
    prevent_initial_call=True,
)

# Cumulative: hide "Total" slice option in line/area mode
_TX_CUMUL_SLICE_ALL = [
    {"value": "total", "label": "Total"},
    {"value": "dept", "label": "Dept"},
    {"value": "machine", "label": "Machine"},
    {"value": "physician", "label": "MD"},
    {"value": "technique", "label": "Technique"},
]
_TX_CUMUL_SLICE_NO_TOTAL = [o for o in _TX_CUMUL_SLICE_ALL if o["value"] != "total"]

clientside_callback(
    """function(chartType, sliceVal) {
        var all = %s;
        var noTotal = %s;
        if (chartType === "bar") {
            return [all, window.dash_clientside.no_update];
        }
        var newVal = (sliceVal === "total") ? "dept" : window.dash_clientside.no_update;
        return [noTotal, newVal];
    }""" % (str(_TX_CUMUL_SLICE_ALL).replace("'", '"'), str(_TX_CUMUL_SLICE_NO_TOTAL).replace("'", '"')),
    Output("tx-cumulative-slice", "data"),
    Output("tx-cumulative-slice", "value", allow_duplicate=True),
    Input("tx-cumulative-settings-type", "value"),
    State("tx-cumulative-slice", "value"),
    prevent_initial_call=True,
)

# Cumulative: hide grouping in Prior Periods mode (single dimension)
clientside_callback(
    """function(mode, sliceVal, chartType) {
        var single = !sliceVal || sliceVal === "total" || sliceVal === "";
        if (single) return {"display": "none"};
        if (chartType === "bar") return {};
        var isPrior = mode === "prior";
        var noStack = chartType === "line";
        return (isPrior || noStack) ? {"display": "none"} : {};
    }""",
    Output("tx-cumulative-settings-stack-wrap", "style"),
    Input("tx-cumulative-mode", "value"),
    Input("tx-cumulative-slice", "value"),
    Input("tx-cumulative-settings-type", "value"),
)

clientside_callback(
    _census_render("tx-chart-igrt"),
    Output("tx-chart-igrt", "figure"),
    Input("tx-chart-igrt-store", "data"),
    Input("tx-igrt-settings-smooth", "value"),
    Input("tx-igrt-settings-type", "value"),
    Input("tx-igrt-settings-stack", "value"),
    State("tx-chart-igrt", "figure"),
    prevent_initial_call=True,
)

clientside_callback(
    _census_render("tx-chart-newstarts"),
    Output("tx-chart-newstarts", "figure"),
    Input("tx-chart-newstarts-store", "data"),
    Input("tx-newstarts-settings-smooth", "value"),
    Input("tx-newstarts-settings-type", "value"),
    Input("tx-newstarts-settings-stack", "value"),
    State("tx-chart-newstarts", "figure"),
    prevent_initial_call=True,
)

clientside_callback(
    _census_render("tx-chart-gating"),
    Output("tx-chart-gating", "figure"),
    Input("tx-chart-gating-store", "data"),
    Input("tx-gating-settings-smooth", "value"),
    Input("tx-gating-settings-type", "value"),
    Input("tx-gating-settings-stack", "value"),
    State("tx-chart-gating", "figure"),
    prevent_initial_call=True,
)

clientside_callback(
    _census_render("tx-chart-multiiso"),
    Output("tx-chart-multiiso", "figure"),
    Input("tx-chart-multiiso-store", "data"),
    Input("tx-multiiso-settings-smooth", "value"),
    Input("tx-multiiso-settings-type", "value"),
    Input("tx-multiiso-settings-stack", "value"),
    State("tx-chart-multiiso", "figure"),
    prevent_initial_call=True,
)

clientside_callback(
    _census_render("tx-chart-avgfields"),
    Output("tx-chart-avgfields", "figure"),
    Input("tx-chart-avgfields-store", "data"),
    Input("tx-avgfields-settings-smooth", "value"),
    Input("tx-avgfields-settings-type", "value"),
    Input("tx-avgfields-settings-stack", "value"),
    State("tx-chart-avgfields", "figure"),
    prevent_initial_call=True,
)


# ---------------------------------------------------------------------------
# Detail table CSV export
# ---------------------------------------------------------------------------
clientside_callback(
    """function(n) {
        if (!n) return window.dash_clientside.no_update;
        gridExportCsv('tx-detail-grid', 'treatment_sessions.csv');
        return window.dash_clientside.no_update;
    }""",
    Output("tx-detail-export", "n_clicks"),
    Input("tx-detail-export", "n_clicks"),
    prevent_initial_call=True,
)

# Detail table filter badge + clear button
clientside_callback(
    """function(virtual, rowData, prev) {
        var nu = window.dash_clientside.no_update;
        var hidden = {"display": "none"};
        if (!rowData || !rowData.length || !virtual)
            return [null, hidden, hidden];
        if (virtual.length >= rowData.length)
            return prev == null ? [nu, nu, nu] : [null, hidden, hidden];
        var idxs = [];
        for (var i = 0; i < virtual.length; i++) {
            if (virtual[i]._row_idx != null) idxs.push(virtual[i]._row_idx);
        }
        if (!idxs.length)
            return prev == null ? [nu, nu, nu] : [null, hidden, hidden];
        if (prev && prev.length === idxs.length) {
            var same = true;
            for (var j = 0; j < idxs.length; j++) {
                if (prev[j] !== idxs[j]) { same = false; break; }
            }
            if (same) return [nu, nu, nu];
        }
        return [idxs, {"cursor": "pointer"}, {}];
    }""",
    Output("tx-table-filter-rows", "data"),
    Output("tx-grid-filter-badge", "style"),
    Output("tx-table-clear-filters", "style"),
    Input("tx-detail-grid", "virtualRowData"),
    State("tx-detail-grid", "rowData"),
    State("tx-table-filter-rows", "data"),
    prevent_initial_call=True,
)

# Clear filters button → reset filterModel
clientside_callback(
    """function(n) {
        if (!n) return window.dash_clientside.no_update;
        return {};
    }""",
    Output("tx-detail-grid", "filterModel"),
    Input("tx-table-clear-filters", "n_clicks"),
    prevent_initial_call=True,
)

# Badge click → scroll to grid
clientside_callback(
    """function(n) {
        if (!n) return window.dash_clientside.no_update;
        var el = document.getElementById('tx-detail-grid');
        if (el) el.scrollIntoView({behavior: 'smooth', block: 'start'});
        return window.dash_clientside.no_update;
    }""",
    Output("tx-grid-filter-badge", "n_clicks"),
    Input("tx-grid-filter-badge", "n_clicks"),
    prevent_initial_call=True,
)


# Project-to-year-end toggle visibility (shown only for current_year preset)
clientside_callback(
    """function(preset) {
        return preset === "current_year" ? {} : {"display": "none"};
    }""",
    Output("tx-cumulative" + "-project-wrap", "style"),
    Input("tx-filter-date-preset", "value"),
)

