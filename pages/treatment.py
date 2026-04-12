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
    MACHINE_DEPT, MACHINE_COLORS,
)
from components.filter_bar import department_chips
from components.diagnosis_filter import diagnosis_accordion, register_diagnosis_callbacks
from components.kpi_card import kpi_card, kpi_placeholder
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
                                id="tx-machine-wrap",
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
                                id="tx-physician-panel",
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
            dmc.GridCol(kpi_placeholder(), id="tx-kpi-volume", span={"base": 12, "sm": 6, "md": 2}),
            dmc.GridCol(kpi_placeholder(), id="tx-kpi-newstarts", span={"base": 12, "sm": 6, "md": 2}),
            dmc.GridCol(kpi_placeholder(), id="tx-kpi-patients", span={"base": 12, "sm": 6, "md": 2}),
            dmc.GridCol(kpi_placeholder(), id="tx-kpi-elapsed", span={"base": 12, "sm": 6, "md": 2}),
            dmc.GridCol(kpi_placeholder(), id="tx-kpi-fields", span={"base": 12, "sm": 6, "md": 2}),
            dmc.GridCol(kpi_placeholder(), id="tx-kpi-gating", span={"base": 12, "sm": 6, "md": 2}),
        ]),

        # Row 1: Treatment Volume + Technique Mix
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
                                    {"value": "count", "label": "#"},
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
                                {"value": "count", "label": "#"},
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
        ]),

        # Row 2: Session Duration + Field Type Breakdown
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
                    "tx-chart-fields",
                    "Field Type Breakdown",
                    settings_id="tx-fields",
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
                            id="tx-fields-pct",
                            data=[
                                {"value": "count", "label": "#"},
                                {"value": "pct", "label": "%"},
                            ],
                            value="count", size="xs",
                        ),
                    ],
                    extra_controls=[
                        dmc.SegmentedControl(
                            id="tx-fields-agg",
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
                                    {"value": "count", "label": "#"},
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

        # Row 4: Multi-Iso Rate + Avg Fields
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
    ("tx-volume", "tx-chart-volume", "tx-chart-volume-store"),
    ("tx-technique", "tx-chart-technique", "tx-chart-technique-store"),
    ("tx-fields", "tx-chart-fields", "tx-chart-fields-store"),
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
                   machines, diagnosis_cats, diag_mode, physician_role):
    """Load and filter both Treatment and Treatment-Detail DataFrames.

    Returns (df_agg_filtered, df_det_filtered, df_agg_prior, df_det_prior,
             start, end, trend_label).
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

    return df_agg_filtered, df_det_filtered, df_agg_prior, df_det_prior, start, end, trend_label


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
    df_agg_filtered, df_det_filtered, df_agg_prior, df_det_prior, start, end, trend_label = \
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

    # 1. Daily Treatments (avg per business day) — sum across sites, then avg
    if not df_agg_filtered.empty and "CompletedAppointments" in df_agg_filtered.columns:
        daily_tx = df_agg_filtered.groupby("ScheduledDate")["CompletedAppointments"].sum()
        val = daily_tx.mean()
        t_text, t_dir = None, None
        if not df_agg_prior.empty:
            prior_daily = df_agg_prior.groupby("ScheduledDate")["CompletedAppointments"].sum()
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

    # 3. Unique Patients (avg per day) — sum across sites, then avg
    if not df_agg_filtered.empty and "UniquePatients" in df_agg_filtered.columns:
        daily_pts = df_agg_filtered.groupby("ScheduledDate")["UniquePatients"].sum()
        val = daily_pts.mean()
        t_text, t_dir = None, None
        if not df_agg_prior.empty:
            prior_daily = df_agg_prior.groupby("ScheduledDate")["UniquePatients"].sum()
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
    df_agg_filtered, df_det_filtered, *_ = _apply_filters(*filt_args)
    df_det_filtered = _apply_grid_row_filter(df_det_filtered, grid_rows)

    _vol_agg = vol_agg or "D"
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
    if _by_total and not df_agg_filtered.empty and "CompletedAppointments" in df_agg_filtered.columns:
        tdf = df_agg_filtered[["ScheduledDate", "CompletedAppointments"]].copy()
        tdf["_grp"] = "Total"
        result = _build_census_store(
            tdf, "ScheduledDate", "_grp", "CompletedAppointments",
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
    elif not df_agg_filtered.empty and "CompletedAppointments" in df_agg_filtered.columns:
        result = _build_census_store(
            df_agg_filtered, "ScheduledDate", "Department", "CompletedAppointments",
            DEPARTMENTS, DEPARTMENT_COLORS,
            agg=_vol_agg, agg_func="sum", y_title="Treatments",
        )
    return _to_pct(result) if vol_pct == "pct" and result else result


# ---------------------------------------------------------------------------
# Callback 3: Technique Mix store (tech_agg)
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
    _, df_det_filtered, *_ = _apply_filters(*filt_args)
    df_det_filtered = _apply_grid_row_filter(df_det_filtered, grid_rows)

    _tech_agg = tech_agg or "D"
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
# Callback 5a: Field Type Breakdown (own agg toggle)
# ---------------------------------------------------------------------------
@callback(
    Output("tx-chart-fields-store", "data"),
    *_TX_FILTER_INPUTS,
    Input("tx-fields-agg", "value"),
    Input("tx-fields-pct", "value"),
    Input("tx-table-filter-rows", "data"),
    running=[(Output("tx-chart-fields-loading", "visible"), True, False)],
)
def _update_fields(*args):
    fields_agg, fields_pct, grid_rows = args[-3], args[-2], args[-1]
    filt_args = args[:-3]
    _, df_det_filtered, *_ = _apply_filters(*filt_args)
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
        agg=fields_agg or "D", agg_func="sum", y_title="Fields",
    )
    return _to_pct(result) if fields_pct == "pct" and result else result


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
    df_agg_filtered, df_det_filtered, *_ = _apply_filters(*filt_args)
    df_det_filtered = _apply_grid_row_filter(df_det_filtered, grid_rows)

    _by_machine = groupby == "machine"
    _by_total = not groupby
    _agg = ns_agg or "D"

    if _by_machine and not df_det_filtered.empty and "Machine" in df_det_filtered.columns:
        _machines = sorted(df_det_filtered["Machine"].dropna().unique())
        _machine_colors = {
            m: MACHINE_COLORS.get(m, CHART_COLORWAY[i % len(CHART_COLORWAY)])
            for i, m in enumerate(_machines)
        }
    else:
        _machines, _machine_colors = [], {}

    ns_metric_agg = ("NewStarts_ByCourseFirstTreatmentDate"
                     if newstarts_metric == "course"
                     else "NewStarts_ByFraction")
    ns_metric_det = ("IsNewStart_ByCourseFirstTreatmentDate"
                     if newstarts_metric == "course"
                     else "IsNewStart_ByFraction")
    if _by_total and not df_agg_filtered.empty and ns_metric_agg in df_agg_filtered.columns:
        nsdf = df_agg_filtered[["ScheduledDate", ns_metric_agg]].copy()
        nsdf["_grp"] = "Total"
        return _build_census_store(
            nsdf, "ScheduledDate", "_grp", ns_metric_agg,
            ["Total"], {"Total": PRIMARY},
            agg=_agg, agg_func="sum", y_title="New Starts",
        )
    elif _by_machine and _machines and not df_det_filtered.empty and ns_metric_det in df_det_filtered.columns:
        nsdf = df_det_filtered[["ScheduledDateTime", "Machine", ns_metric_det]].copy()
        nsdf["_d"] = nsdf["ScheduledDateTime"].dt.normalize()
        return _build_census_store(
            nsdf, "_d", "Machine", ns_metric_det, _machines, _machine_colors,
            agg=_agg, agg_func="sum", y_title="New Starts",
        )
    elif not df_agg_filtered.empty and ns_metric_agg in df_agg_filtered.columns:
        return _build_census_store(
            df_agg_filtered, "ScheduledDate", "Department", ns_metric_agg,
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
    _, df_det_filtered, *_ = _apply_filters(*filt_args)
    df_det_filtered = _apply_grid_row_filter(df_det_filtered, grid_rows)

    if df_det_filtered.empty or "UniqueIsocenters" not in df_det_filtered.columns:
        return None
    cols = ["ScheduledDateTime", "UniqueIsocenters", "Department", "Machine"]
    if "PlanTechniques" in df_det_filtered.columns:
        cols.append("PlanTechniques")
    cdf = df_det_filtered[cols].dropna(subset=["UniqueIsocenters"]).copy()
    cdf["_d"] = cdf["ScheduledDateTime"].dt.normalize()
    cdf["_multi"] = (cdf["UniqueIsocenters"] > 1).astype(float) * 100
    return _sliced_store(cdf, "_d", "_multi", sliceby, agg or "D", "mean",
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
    _, df_det_filtered, *_ = _apply_filters(*filt_args)
    df_det_filtered = _apply_grid_row_filter(df_det_filtered, grid_rows)

    if df_det_filtered.empty or "FieldCount" not in df_det_filtered.columns:
        return None
    cols = ["ScheduledDateTime", "FieldCount", "Department", "Machine"]
    if "PlanTechniques" in df_det_filtered.columns:
        cols.append("PlanTechniques")
    cdf = df_det_filtered[cols].dropna(subset=["FieldCount"]).copy()
    cdf["_d"] = cdf["ScheduledDateTime"].dt.normalize()
    return _sliced_store(cdf, "_d", "FieldCount", sliceby, agg or "D", "mean",
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
    _, df_det_filtered, *_ = _apply_filters(*filt_args)
    df_det_filtered = _apply_grid_row_filter(df_det_filtered, grid_rows)

    if df_det_filtered.empty:
        return None

    _metric = gating_metric or "any"
    _slice = gating_slice or ""
    _agg = gating_agg or "D"

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

        var layout = Object.assign({}, window._defaultLayout || {}, {
            showlegend: false,
            margin: {l: 48, r: 16, t: isDensity ? 28 : 8, b: isDensity ? 36 : 24},
            violinmode: "group"
        });

        if (isDensity) {
            layout.xaxis = {title: {text: "Minutes", font: {size: 11}}, range: [0, yUpper]};
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
                    showarrow: false, font: {size: 11, color: "#374151"},
                    yshift: 4
                }];
            }
        } else {
            layout.yaxis = {title: {text: "Minutes", font: {size: 11}}, range: [0, yUpper]};
        }

        return {data: traces, layout: layout};
    }""",
    Output("tx-chart-elapsed", "figure"),
    Input("tx-store-elapsed", "data"),
    Input("tx-elapsed-bw", "value"),
)


# ---------------------------------------------------------------------------
# Groupby toggle: CSS dim class + hide stacked/grouped in Total mode
# ---------------------------------------------------------------------------
_SLICE_CLASS_JS = """function(val) {
    return (val && val !== "total") ? "slice-group-active" : "slice-total-active";
}"""
for _sc_id in ["tx-groupby", "tx-elapsed-slice", "tx-gating-slice",
                "tx-multiiso-slice", "tx-avgfields-slice"]:
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
    _CENSUS_RENDER,
    Output("tx-chart-volume", "figure"),
    Input("tx-chart-volume-store", "data"),
    Input("tx-volume-settings-smooth", "value"),
    Input("tx-volume-settings-type", "value"),
    Input("tx-volume-settings-stack", "value"),
    State("tx-chart-volume", "figure"),
)

clientside_callback(
    _CENSUS_RENDER,
    Output("tx-chart-technique", "figure"),
    Input("tx-chart-technique-store", "data"),
    Input("tx-technique-settings-smooth", "value"),
    Input("tx-technique-settings-type", "value"),
    Input("tx-technique-settings-stack", "value"),
    State("tx-chart-technique", "figure"),
)

clientside_callback(
    _CENSUS_RENDER,
    Output("tx-chart-fields", "figure"),
    Input("tx-chart-fields-store", "data"),
    Input("tx-fields-settings-smooth", "value"),
    Input("tx-fields-settings-type", "value"),
    Input("tx-fields-settings-stack", "value"),
    State("tx-chart-fields", "figure"),
)

clientside_callback(
    _CENSUS_RENDER,
    Output("tx-chart-newstarts", "figure"),
    Input("tx-chart-newstarts-store", "data"),
    Input("tx-newstarts-settings-smooth", "value"),
    Input("tx-newstarts-settings-type", "value"),
    Input("tx-newstarts-settings-stack", "value"),
    State("tx-chart-newstarts", "figure"),
)

clientside_callback(
    _CENSUS_RENDER,
    Output("tx-chart-gating", "figure"),
    Input("tx-chart-gating-store", "data"),
    Input("tx-gating-settings-smooth", "value"),
    Input("tx-gating-settings-type", "value"),
    Input("tx-gating-settings-stack", "value"),
    State("tx-chart-gating", "figure"),
)

clientside_callback(
    _CENSUS_RENDER,
    Output("tx-chart-multiiso", "figure"),
    Input("tx-chart-multiiso-store", "data"),
    Input("tx-multiiso-settings-smooth", "value"),
    Input("tx-multiiso-settings-type", "value"),
    Input("tx-multiiso-settings-stack", "value"),
    State("tx-chart-multiiso", "figure"),
)

clientside_callback(
    _CENSUS_RENDER,
    Output("tx-chart-avgfields", "figure"),
    Input("tx-chart-avgfields-store", "data"),
    Input("tx-avgfields-settings-smooth", "value"),
    Input("tx-avgfields-settings-type", "value"),
    Input("tx-avgfields-settings-stack", "value"),
    State("tx-chart-avgfields", "figure"),
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
