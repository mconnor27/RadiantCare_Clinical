"""OTVs page — weekly check volume, physician workload, and coverage analysis."""

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
    DEPARTMENTS, DEPARTMENT_COLORS, PRIMARY, NEUTRAL,
    SEMANTIC_COLORS, PHYSICIANS, CHART_COLORWAY,
    CHART_PAPER_HEIGHT_SM,
)
from components.filter_bar import department_chips
from components.kpi_card import kpi_card
from components.chart_card import chart_card, register_chart_callbacks
from components.detail_table import detail_table
from components.chart_settings import chart_settings_popover
from utils.charts import apply_default_layout, empty_figure
from utils.date_slider import (
    month_idx, idx_to_date, MAX_IDX, SLIDER_MARKS,
    preset_to_slider_val,
)
from utils.diagnosis_categories import (
    CATEGORIES as BODY_SYSTEMS,
    build_code_to_category,
    get_categories_for_codes,
    primary_category,
)

dash.register_page(__name__, path="/otvs", name="OTVs", order=6)

PAGE_ID = "otvs"

_DEFAULT_DATE_PRESET = "ytd" if pd.Timestamp.now().month > 1 else "3mo"


# ---------------------------------------------------------------------------
# Filter Bar (two-row layout matching simulations/tasks)
# ---------------------------------------------------------------------------

def _build_otvs_filter_bar():
    """Build the two-row filter bar for OTVs."""
    return dmc.Paper(
        children=[
            # Row 1: data filters
            dmc.Group(
                children=[
                    department_chips(PAGE_ID),
                    # Treating Physician dropdown
                    html.Div(
                        children=[
                            html.Div(
                                children=[
                                    dmc.Button(
                                        "Treating MD",
                                        id=f"{PAGE_ID}-treating-trigger",
                                        variant="default",
                                        size="sm",
                                        rightSection=DashIconify(icon="mdi:chevron-down", width=14),
                                    ),
                                    dmc.ActionIcon(
                                        DashIconify(icon="mdi:close-circle", width=18),
                                        id=f"{PAGE_ID}-treating-clear",
                                        variant="subtle",
                                        color="gray",
                                        size="sm",
                                        className="wf-filter-clear-btn",
                                    ),
                                ],
                                style={"position": "relative", "display": "inline-block"},
                            ),
                            dmc.Paper(
                                id=f"{PAGE_ID}-treating-panel",
                                children=[
                                    dmc.ChipGroup(
                                        children=[
                                            dmc.Chip(
                                                p.split(", ")[0],
                                                value=p,
                                                size="xs",
                                                variant="filled",
                                            )
                                            for p in PHYSICIANS
                                        ],
                                        id=f"{PAGE_ID}-filter-treating",
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
                    # Performing (Appointment) Physician dropdown
                    html.Div(
                        children=[
                            html.Div(
                                children=[
                                    dmc.Button(
                                        "Performing MD",
                                        id=f"{PAGE_ID}-performing-trigger",
                                        variant="default",
                                        size="sm",
                                        rightSection=DashIconify(icon="mdi:chevron-down", width=14),
                                    ),
                                    dmc.ActionIcon(
                                        DashIconify(icon="mdi:close-circle", width=18),
                                        id=f"{PAGE_ID}-performing-clear",
                                        variant="subtle",
                                        color="gray",
                                        size="sm",
                                        className="wf-filter-clear-btn",
                                    ),
                                ],
                                style={"position": "relative", "display": "inline-block"},
                            ),
                            dmc.Paper(
                                id=f"{PAGE_ID}-performing-panel",
                                children=[
                                    dmc.ChipGroup(
                                        children=[
                                            dmc.Chip(
                                                p.split(", ")[0],
                                                value=p,
                                                size="xs",
                                                variant="filled",
                                            )
                                            for p in PHYSICIANS
                                        ],
                                        id=f"{PAGE_ID}-filter-performing",
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
                                        id=f"{PAGE_ID}-diagnosis-trigger",
                                        variant="default",
                                        size="sm",
                                        rightSection=DashIconify(icon="mdi:chevron-down", width=14),
                                    ),
                                    dmc.ActionIcon(
                                        DashIconify(icon="mdi:close-circle", width=18),
                                        id=f"{PAGE_ID}-diagnosis-clear",
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
                                    id=f"{PAGE_ID}-filter-diagnosis",
                                    multiple=True,
                                    value=[],
                                ),
                                id=f"{PAGE_ID}-diagnosis-panel",
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
                    # Smoothing
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
                dmc.Title("OTVs", order=2, className="page-title",
                          style={"margin": 0, "textAlign": "center"}),
                _build_otvs_filter_bar(),
            ],
        ),

        # KPI row — 6 cards with sparklines
        dmc.Grid(id=f"{PAGE_ID}-kpi-row", gutter="md", children=[
            dmc.GridCol(id=f"{PAGE_ID}-kpi-total", span={"base": 6, "md": 2}),
            dmc.GridCol(id=f"{PAGE_ID}-kpi-lacey", span={"base": 6, "md": 2}),
            dmc.GridCol(id=f"{PAGE_ID}-kpi-centralia", span={"base": 6, "md": 2}),
            dmc.GridCol(id=f"{PAGE_ID}-kpi-aberdeen", span={"base": 6, "md": 2}),
            dmc.GridCol(id=f"{PAGE_ID}-kpi-avg", span={"base": 6, "md": 2}),
            dmc.GridCol(id=f"{PAGE_ID}-kpi-self-rate", span={"base": 6, "md": 2}),
        ]),

        # Row 1: Volume Trend + Cumulative Volume
        dmc.Grid(gutter="md", children=[
            dmc.GridCol(
                chart_card(
                    f"{PAGE_ID}-chart-volume",
                    "Weekly Check Volume Trend",
                    settings_id=f"{PAGE_ID}-volume",
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
                            id=f"{PAGE_ID}-volume-slice",
                            data=[
                                {"value": "", "label": "Total"},
                                {"value": "treating", "label": "Treating MD"},
                                {"value": "performing", "label": "Completing MD"},
                                {"value": "dept", "label": "Site"},
                            ],
                            value="",
                            size="xs",
                        ),
                    ],
                    extra_controls=[
                        dmc.SegmentedControl(
                            id=f"{PAGE_ID}-volume-agg",
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
                    f"{PAGE_ID}-chart-cumulative",
                    "Cumulative Weekly Check Volume",
                    settings_id=f"{PAGE_ID}-cumulative",
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
                            id=f"{PAGE_ID}-cumulative-mode",
                            data=[
                                {"value": "prior", "label": "Prior Periods"},
                                {"value": "slice", "label": "Slice By"},
                            ],
                            value="prior",
                            size="xs",
                        ),
                        dmc.SegmentedControl(
                            id=f"{PAGE_ID}-cumulative-period-type",
                            data=[
                                {"value": "calendar", "label": "Calendar"},
                                {"value": "rolling", "label": "Rolling"},
                            ],
                            value="calendar",
                            size="xs",
                        ),
                        dmc.SegmentedControl(
                            id=f"{PAGE_ID}-cumulative-slice",
                            data=[
                                {"value": "treating", "label": "Treating MD"},
                                {"value": "performing", "label": "Completing MD"},
                                {"value": "dept", "label": "Site"},
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

        # Row 2: Coverage Analysis + Billing
        dmc.Grid(gutter="md", children=[
            dmc.GridCol(
                dmc.Paper(
                    children=[
                        dmc.Group(
                            justify="space-between", mb=8,
                            children=[
                                dmc.Group(gap="xs", align="center", children=[
                                    dmc.Text("Coverage Analysis", size="sm", fw=500, c="#6B7280"),
                                ]),
                                chart_settings_popover(
                                    f"{PAGE_ID}-coverage",
                                    chart_types=None,
                                    show_smooth=False,
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
                                        dmc.LoadingOverlay(id=f"{PAGE_ID}-coverage-loading", visible=False,
                                                           loaderProps={"type": "dots", "color": PRIMARY}),
                                        dcc.Graph(id=f"{PAGE_ID}-chart-coverage",
                                                  config={"displayModeBar": False},
                                                  style={"height": "100%"}),
                                    ],
                                ),
                            ],
                        ),
                    ],
                    p="sm", pb=8, radius="md", shadow="xs", withBorder=True,
                    h="440px", style={"display": "flex", "flexDirection": "column"},
                ),
                span={"base": 12, "md": 6},
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
                                        id=f"{PAGE_ID}-billing-slice",
                                        data=[
                                            {"value": "", "label": "Total"},
                                            {"value": "treating", "label": "Treating MD"},
                                            {"value": "performing", "label": "Completing MD"},
                                            {"value": "dept", "label": "Site"},
                                        ],
                                        value="",
                                        size="xs",
                                    ),
                                    dmc.SegmentedControl(
                                        id=f"{PAGE_ID}-billing-mode",
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
                                    f"{PAGE_ID}-billing",
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
                                        dmc.LoadingOverlay(id=f"{PAGE_ID}-billing-loading", visible=False,
                                                           loaderProps={"type": "dots", "color": PRIMARY}),
                                        dcc.Graph(id=f"{PAGE_ID}-chart-billing",
                                                  config={"displayModeBar": False},
                                                  style={"height": "100%"}),
                                    ],
                                ),
                            ],
                        ),
                    ],
                    p="sm", pb=8, radius="md", shadow="xs", withBorder=True,
                    h="440px", style={"display": "flex", "flexDirection": "column"},
                ),
                span={"base": 12, "md": 6},
            ),
        ]),

        # Detail table — full width, collapsible
        detail_table(f"{PAGE_ID}-detail-grid", title="Weekly Visit Detail",
                     export_id=f"{PAGE_ID}-table-export"),

        dcc.Interval(id=f"{PAGE_ID}-interval", interval=300_000, n_intervals=0),

        # Stores for clientside rendering
        dcc.Store(id=f"{PAGE_ID}-store-volume"),
        dcc.Store(id=f"{PAGE_ID}-store-cumulative"),
        dcc.Store(id=f"{PAGE_ID}-store-kpi-sparklines"),
    ],
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

def _register_otvs_filter_callbacks():
    """Register all filter-sync callbacks for the OTVs page."""

    # A) Preset → Slider + DatePicker
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
        s = idx_to_date(sv[0]).strftime("%Y-%m-%d")
        e_ts = idx_to_date(sv[1], end_of_month=True)
        today = pd.Timestamp.now().normalize()
        if e_ts > today:
            e_ts = today
        e = e_ts.strftime("%Y-%m-%d")
        return sv, s, e

    # B) Slider → DatePicker + Label (clientside for speed)
    clientside_callback(
        ClientsideFunction(namespace="otvsDateSlider", function_name="syncSlider"),
        Output(f"{PAGE_ID}-filter-daterange", "start_date", allow_duplicate=True),
        Output(f"{PAGE_ID}-filter-daterange", "end_date", allow_duplicate=True),
        Output(f"{PAGE_ID}-date-range-label", "children"),
        Input(f"{PAGE_ID}-date-slider", "value"),
        State(f"{PAGE_ID}-filter-daterange", "start_date"),
        State(f"{PAGE_ID}-filter-daterange", "end_date"),
        prevent_initial_call=True,
    )

    # C) DatePicker → Slider
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

    # D) Slider → auto-set preset to "Custom" when it doesn't match
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
            if (!val) return "Treating MD";
            return val.split(", ")[0];
        }""",
        Output(f"{PAGE_ID}-treating-trigger", "children"),
        Input(f"{PAGE_ID}-filter-treating", "value"),
    )
    clientside_callback(
        """function(val) {
            if (!val) return "Performing MD";
            return val.split(", ")[0];
        }""",
        Output(f"{PAGE_ID}-performing-trigger", "children"),
        Input(f"{PAGE_ID}-filter-performing", "value"),
    )
    clientside_callback(
        "function(vals) {"
        "  if (!vals || vals.length === 0) return 'Diagnosis';"
        "  if (vals.length === 1) return vals[0];"
        "  return vals.length + ' selected';"
        "}",
        Output(f"{PAGE_ID}-diagnosis-trigger", "children"),
        Input(f"{PAGE_ID}-filter-diagnosis", "value"),
    )

    # --- Clear-button visibility ---
    clientside_callback(
        """function(val) { return val ? {"display": "inline-flex"} : {"display": "none"}; }""",
        Output(f"{PAGE_ID}-treating-clear", "style"),
        Input(f"{PAGE_ID}-filter-treating", "value"),
    )
    clientside_callback(
        """function(val) { return val ? {"display": "inline-flex"} : {"display": "none"}; }""",
        Output(f"{PAGE_ID}-performing-clear", "style"),
        Input(f"{PAGE_ID}-filter-performing", "value"),
    )
    clientside_callback(
        """function(vals) { return vals && vals.length > 0 ? {"display": "inline-flex"} : {"display": "none"}; }""",
        Output(f"{PAGE_ID}-diagnosis-clear", "style"),
        Input(f"{PAGE_ID}-filter-diagnosis", "value"),
    )

    # --- Clear-button actions ---
    clientside_callback(
        """function(n) { return null; }""",
        Output(f"{PAGE_ID}-filter-treating", "value", allow_duplicate=True),
        Input(f"{PAGE_ID}-treating-clear", "n_clicks"),
        prevent_initial_call=True,
    )
    clientside_callback(
        """function(n) { return null; }""",
        Output(f"{PAGE_ID}-filter-performing", "value", allow_duplicate=True),
        Input(f"{PAGE_ID}-performing-clear", "n_clicks"),
        prevent_initial_call=True,
    )
    clientside_callback(
        """function(n) { return []; }""",
        Output(f"{PAGE_ID}-filter-diagnosis", "value", allow_duplicate=True),
        Input(f"{PAGE_ID}-diagnosis-clear", "n_clicks"),
        prevent_initial_call=True,
    )


# Register filter callbacks
_register_otvs_filter_callbacks()


# ---------------------------------------------------------------------------
# Main callback
# ---------------------------------------------------------------------------

@callback(
    Output(f"{PAGE_ID}-kpi-total", "children"),
    Output(f"{PAGE_ID}-kpi-lacey", "children"),
    Output(f"{PAGE_ID}-kpi-centralia", "children"),
    Output(f"{PAGE_ID}-kpi-aberdeen", "children"),
    Output(f"{PAGE_ID}-kpi-avg", "children"),
    Output(f"{PAGE_ID}-kpi-self-rate", "children"),
    Output(f"{PAGE_ID}-store-volume", "data"),
    Output(f"{PAGE_ID}-store-cumulative", "data"),
    Output(f"{PAGE_ID}-chart-coverage", "figure"),
    Output(f"{PAGE_ID}-chart-billing", "figure"),
    Output(f"{PAGE_ID}-detail-grid", "rowData"),
    Output(f"{PAGE_ID}-detail-grid", "columnDefs"),
    Output(f"{PAGE_ID}-store-kpi-sparklines", "data"),
    Input(f"{PAGE_ID}-interval", "n_intervals"),
    Input(f"{PAGE_ID}-volume-agg", "value"),
    Input(f"{PAGE_ID}-volume-slice", "value"),
    Input(f"{PAGE_ID}-cumulative-mode", "value"),
    Input(f"{PAGE_ID}-cumulative-period-type", "value"),
    Input(f"{PAGE_ID}-cumulative-slice", "value"),
    Input(f"{PAGE_ID}-billing-slice", "value"),
    Input(f"{PAGE_ID}-billing-mode", "value"),
    Input(f"{PAGE_ID}-filter-department", "value"),
    Input(f"{PAGE_ID}-filter-treating", "value"),
    Input(f"{PAGE_ID}-filter-performing", "value"),
    Input(f"{PAGE_ID}-filter-diagnosis", "value"),
    Input(f"{PAGE_ID}-date-slider", "value"),
    Input(f"{PAGE_ID}-filter-date-preset", "value"),
    running=[
        (Output(f"{PAGE_ID}-chart-volume-loading", "visible"), True, False),
        (Output(f"{PAGE_ID}-chart-cumulative-loading", "visible"), True, False),
        (Output(f"{PAGE_ID}-coverage-loading", "visible"), True, False),
        (Output(f"{PAGE_ID}-billing-loading", "visible"), True, False),
    ],
)
def update_otvs(_n, agg, volume_slice,
                cumul_mode, cumul_period_type, cumul_slice,
                billing_slice, billing_mode,
                departments, treating_md, performing_md,
                body_sites, slider_val, date_preset):
    from data.loader import load_weekly_visits, load_diagnosis

    na_card = kpi_card("--", "N/A")
    empty = empty_figure()
    _empty_store = {"dates": [], "series": []}
    empty_result = (na_card,) * 6 + (_empty_store, None, empty, empty, [], [], {})

    try:
        df = load_weekly_visits()
    except Exception:
        return empty_result

    if df.empty:
        return empty_result

    date_col = "AppointmentDateTime"
    if date_col not in df.columns:
        return empty_result

    # --- Dimension filters ---
    if departments and "Department" in df.columns:
        df = df[df["Department"].isin(departments)]

    if treating_md and "TreatingPhysician" in df.columns:
        df = df[df["TreatingPhysician"] == treating_md]

    if performing_md and "AppointmentPhysician" in df.columns:
        df = df[df["AppointmentPhysician"] == performing_md]

    # Diagnosis body site filter
    try:
        diag_df = load_diagnosis()
    except Exception:
        diag_df = None
    c2b = build_code_to_category(diag_df)

    if body_sites and "DiagnosisCodes" in df.columns and c2b:
        bs_set = set(body_sites)
        row_bs = df["DiagnosisCodes"].apply(
            lambda s: get_categories_for_codes(s, c2b) if pd.notna(s) else set()
        )
        df = df[row_bs.apply(lambda cats: bool(cats & bs_set))]

    if df.empty:
        return empty_result

    # Date range from slider
    start, end = _get_date_range(slider_val)

    # Keep pre-date-filtered copy for prior-period comparisons and cumulative
    df_all = df.copy()

    df = df[(df[date_col] >= start) & (df[date_col] <= end)]

    if df.empty:
        return empty_result

    # ------------------------------------------------------------------
    # Date-aware KPI helpers
    # ------------------------------------------------------------------
    PERIOD_LABELS = {
        "30d": "30 Days", "3mo": "3 Mo", "6mo": "6 Mo", "12mo": "12 Mo",
        "ytd": "YTD", "last_year": "Last Year", "this_month": "This Mo",
        "last_month": "Last Mo", "all": "All Time", "custom": "Custom",
    }
    TREND_LABELS = {
        "30d": "vs prior 30d", "3mo": "vs prior 3 mo", "6mo": "vs prior 6 mo",
        "12mo": "vs prior 12 mo", "ytd": "vs prior year",
        "last_year": "vs prior year", "this_month": "vs prior month",
        "last_month": "vs 2 months ago", "all": "", "custom": "",
    }
    period_label = PERIOD_LABELS.get(date_preset, "YTD")
    trend_label = TREND_LABELS.get(date_preset, "")

    def _kpi_prior_range(last_date):
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

    def _trend(curr, prior, invert=False):
        if prior is None or prior == 0:
            return None, None, None
        pct = (curr - prior) / prior * 100
        direction = ("down" if pct > 0 else "up") if invert else ("up" if pct > 0 else "down")
        return f"{abs(pct):.0f}%", direction, prior

    # Adaptive sparkline granularity
    range_months = (end.year - start.year) * 12 + (end.month - start.month) + 1
    _spark_period = "D" if range_months <= 3 else "W"

    def _spark_bucket(series):
        if _spark_period == "D":
            return series.dt.normalize()
        return series.dt.to_period("W").dt.to_timestamp()

    def _count_spark_raw(sub_df):
        if sub_df.empty or date_col not in sub_df.columns:
            return None
        temp = sub_df.copy()
        temp["_sp"] = _spark_bucket(temp[date_col])
        grp = temp.groupby("_sp").size()
        if len(grp) < 3:
            return None
        return {
            "labels": [d.isoformat() for d in grp.index],
            "values": grp.tolist(),
        }

    def _mean_weekly_spark(sub_df):
        """Weekly mean for sparkline (rolling 4-week avg)."""
        if sub_df.empty or date_col not in sub_df.columns:
            return None
        temp = sub_df.copy()
        temp["_wk"] = temp[date_col].dt.to_period("W").dt.to_timestamp()
        weekly = temp.groupby("_wk").size()
        if len(weekly) < 3:
            return None
        return {
            "labels": [d.isoformat() for d in weekly.index],
            "values": weekly.tolist(),
        }

    sparkline_data = {}

    # ------------------------------------------------------------------
    # KPI 1: Total Checks
    # ------------------------------------------------------------------
    total_checks = len(df)
    total_spark = _count_spark_raw(df)
    if total_spark:
        sparkline_data["total"] = {**total_spark, "color": PRIMARY,
                                    "hover_fmt": "%{x|%b %d}: %{customdata:,.0f}<extra></extra>"}

    ps, pe = _kpi_prior_range(end)
    if ps is not None:
        prior_total = len(df_all[(df_all[date_col] >= ps) & (df_all[date_col] <= pe)])
    else:
        prior_total = None
    tt_pct, tt_dir, tt_pv = _trend(total_checks, prior_total)
    kpi_total_card = kpi_card(
        f"Total Checks ({period_label})", f"{total_checks:,}",
        trend_text=f"{tt_pct} {trend_label} ({tt_pv:,})" if tt_pct else None,
        trend_direction=tt_dir,
        accent_color=PRIMARY,
        sparkline_id=f"{PAGE_ID}-spark-total",
    )

    # ------------------------------------------------------------------
    # KPI 2-4: Mean weekly checks per department
    # ------------------------------------------------------------------
    def _dept_weekly_mean_kpi(dept_name, color, spark_key):
        dept_df = df[df["Department"] == dept_name] if "Department" in df.columns else pd.DataFrame()
        if dept_df.empty:
            return kpi_card(f"{dept_name} Mean/Wk ({period_label})", "0",
                            accent_color=color, sparkline_id=f"{PAGE_ID}-spark-{spark_key}")

        dept_df_wk = dept_df.copy()
        dept_df_wk["_wk"] = dept_df_wk[date_col].dt.to_period("W").dt.to_timestamp()
        weekly_counts = dept_df_wk.groupby("_wk").size()
        mean_val = weekly_counts.mean()

        # Sparkline
        if len(weekly_counts) >= 3:
            sparkline_data[spark_key] = {
                "labels": [d.isoformat() for d in weekly_counts.index],
                "values": weekly_counts.tolist(),
                "color": color,
                "hover_fmt": "%{x|%b %d}: %{customdata:,.0f}<extra></extra>",
            }

        # Prior period trend
        if ps is not None and "Department" in df_all.columns:
            prior_dept = df_all[(df_all[date_col] >= ps) & (df_all[date_col] <= pe) &
                                (df_all["Department"] == dept_name)]
            if not prior_dept.empty:
                prior_wk = prior_dept.copy()
                prior_wk["_wk"] = prior_wk[date_col].dt.to_period("W").dt.to_timestamp()
                prior_mean = prior_wk.groupby("_wk").size().mean()
            else:
                prior_mean = None
        else:
            prior_mean = None

        d_pct, d_dir, d_pv = _trend(mean_val, prior_mean)
        return kpi_card(
            f"{dept_name} Mean/Wk ({period_label})", f"{mean_val:.1f}",
            trend_text=f"{d_pct} {trend_label} ({d_pv:.1f})" if d_pct else None,
            trend_direction=d_dir,
            accent_color=color,
            sparkline_id=f"{PAGE_ID}-spark-{spark_key}",
        )

    kpi_lacey = _dept_weekly_mean_kpi("Lacey", DEPARTMENT_COLORS.get("Lacey", "#2196F3"), "lacey")
    kpi_centralia = _dept_weekly_mean_kpi("Centralia", DEPARTMENT_COLORS.get("Centralia", "#F44336"), "centralia")
    kpi_aberdeen = _dept_weekly_mean_kpi("Aberdeen", DEPARTMENT_COLORS.get("Aberdeen", "#4CAF50"), "aberdeen")

    # ------------------------------------------------------------------
    # KPI 5: Avg Checks per Patient Course
    # ------------------------------------------------------------------
    unique_patients = df["PatientId"].nunique() if "PatientId" in df.columns else 0
    avg_per_patient = total_checks / unique_patients if unique_patients > 0 else 0

    if ps is not None and "PatientId" in df_all.columns:
        prior_df = df_all[(df_all[date_col] >= ps) & (df_all[date_col] <= pe)]
        prior_pts = prior_df["PatientId"].nunique()
        prior_avg = len(prior_df) / prior_pts if prior_pts > 0 else None
    else:
        prior_avg = None
    ap_pct, ap_dir, ap_pv = _trend(avg_per_patient, prior_avg)
    kpi_avg_card = kpi_card(
        f"Avg Checks/Patient ({period_label})", f"{avg_per_patient:.1f}",
        trend_text=f"{ap_pct} {trend_label} ({ap_pv:.1f})" if ap_pct else None,
        trend_direction=ap_dir,
        accent_color=SEMANTIC_COLORS["info"],
        sparkline_id=f"{PAGE_ID}-spark-avg",
    )

    # Avg per patient sparkline (weekly unique patient count trend)
    if "PatientId" in df.columns:
        temp_avg = df.copy()
        temp_avg["_wk"] = temp_avg[date_col].dt.to_period("W").dt.to_timestamp()
        wk_total = temp_avg.groupby("_wk").size()
        wk_pts = temp_avg.groupby("_wk")["PatientId"].nunique()
        wk_avg = (wk_total / wk_pts).dropna()
        if len(wk_avg) >= 3:
            sparkline_data["avg"] = {
                "labels": [d.isoformat() for d in wk_avg.index],
                "values": wk_avg.tolist(),
                "color": SEMANTIC_COLORS["info"],
                "hover_fmt": "%{x|%b %d}: %{customdata:.1f}<extra></extra>",
            }

    # ------------------------------------------------------------------
    # KPI 6: Self-Coverage Rate
    # ------------------------------------------------------------------
    if "TreatingPhysician" in df.columns and "AppointmentPhysician" in df.columns:
        matched = df.dropna(subset=["TreatingPhysician", "AppointmentPhysician"])
        self_checks = (matched["TreatingPhysician"] == matched["AppointmentPhysician"]).sum()
        self_rate = (self_checks / len(matched) * 100) if len(matched) > 0 else 0
    else:
        self_rate = 0

    if ps is not None and "TreatingPhysician" in df_all.columns and "AppointmentPhysician" in df_all.columns:
        prior_df = df_all[(df_all[date_col] >= ps) & (df_all[date_col] <= pe)]
        prior_m = prior_df.dropna(subset=["TreatingPhysician", "AppointmentPhysician"])
        prior_self = (prior_m["TreatingPhysician"] == prior_m["AppointmentPhysician"]).sum()
        prior_self_rate = (prior_self / len(prior_m) * 100) if len(prior_m) > 0 else None
    else:
        prior_self_rate = None
    sr_pct, sr_dir, sr_pv = _trend(self_rate, prior_self_rate)

    # Self-coverage sparkline
    if "TreatingPhysician" in df.columns and "AppointmentPhysician" in df.columns:
        temp_sr = df.dropna(subset=["TreatingPhysician", "AppointmentPhysician"]).copy()
        temp_sr["_wk"] = temp_sr[date_col].dt.to_period("W").dt.to_timestamp()
        temp_sr["_self"] = temp_sr["TreatingPhysician"] == temp_sr["AppointmentPhysician"]
        wk_self = temp_sr.groupby("_wk")["_self"].mean() * 100
        if len(wk_self) >= 3:
            sparkline_data["selfrate"] = {
                "labels": [d.isoformat() for d in wk_self.index],
                "values": wk_self.tolist(),
                "color": SEMANTIC_COLORS["success"],
                "hover_fmt": "%{x|%b %d}: %{customdata:.0f}%<extra></extra>",
            }

    kpi_self_card = kpi_card(
        f"Self-Coverage ({period_label})", f"{self_rate:.0f}%",
        trend_text=f"{sr_pct} {trend_label} ({sr_pv:.0f}%)" if sr_pct else None,
        trend_direction=sr_dir,
        accent_color=(SEMANTIC_COLORS["success"] if self_rate >= 50
                      else SEMANTIC_COLORS["warning"]),
        sparkline_id=f"{PAGE_ID}-spark-selfrate",
    )

    # --- Data for clientside charts ---
    volume_data = _prepare_volume_data(df, agg, slice_by=volume_slice or "")
    cumulative_data = _prepare_cumulative_data(
        df_all, start, end, date_preset,
        mode=cumul_mode or "prior",
        period_type=cumul_period_type or "calendar",
        slice_by=cumul_slice or "dept",
    )

    # Server-side charts
    fig_coverage = _build_coverage_chart(df)
    fig_billing = _build_billing_mix(df, slice_by=billing_slice or "", mode=billing_mode or "count")

    # Detail table
    row_data, col_defs = _build_detail_table(df)

    return (
        kpi_total_card, kpi_lacey, kpi_centralia, kpi_aberdeen,
        kpi_avg_card, kpi_self_card,
        volume_data, cumulative_data,
        fig_coverage, fig_billing,
        row_data, col_defs, sparkline_data,
    )


# ---------------------------------------------------------------------------
# Clientside callbacks for charts
# ---------------------------------------------------------------------------

clientside_callback(
    ClientsideFunction(namespace="census", function_name="smoothChartWithType"),
    Output(f"{PAGE_ID}-chart-volume", "figure"),
    Input(f"{PAGE_ID}-store-volume", "data"),
    Input(f"{PAGE_ID}-volume-settings-smooth", "value"),
    Input(f"{PAGE_ID}-volume-settings-type", "value"),
    State(f"{PAGE_ID}-chart-volume", "figure"),
)

clientside_callback(
    ClientsideFunction(namespace="cumulative", function_name="renderCumulative"),
    Output(f"{PAGE_ID}-chart-cumulative", "figure"),
    Input(f"{PAGE_ID}-store-cumulative", "data"),
    Input(f"{PAGE_ID}-cumulative-settings-smooth", "value"),
    Input(f"{PAGE_ID}-cumulative-settings-type", "value"),
    State(f"{PAGE_ID}-chart-cumulative", "figure"),
)

# Show/hide cumulative sub-controls based on mode
clientside_callback(
    """function(mode) {
        var isSlice = mode === "slice";
        return [
            isSlice ? {"display": "flex"} : {"display": "none"},
            isSlice ? {"display": "none"} : {"display": "flex"}
        ];
    }""",
    Output(f"{PAGE_ID}-cumulative-slice", "style"),
    Output(f"{PAGE_ID}-cumulative-period-type", "style"),
    Input(f"{PAGE_ID}-cumulative-mode", "value"),
)

# Register chart_card settings callbacks
register_chart_callbacks([
    (f"{PAGE_ID}-volume", f"{PAGE_ID}-chart-volume"),
    (f"{PAGE_ID}-cumulative", f"{PAGE_ID}-chart-cumulative"),
])

# Slice-by dim styling
_SLICE_CLASS_JS = """function(val) {
    return val ? "slice-group-active" : "slice-total-active";
}"""

clientside_callback(
    _SLICE_CLASS_JS,
    Output(f"{PAGE_ID}-volume-slice", "className"),
    Input(f"{PAGE_ID}-volume-slice", "value"),
)


# ---------------------------------------------------------------------------
# Clientside callbacks for KPI sparklines
# ---------------------------------------------------------------------------

for _out_id in [
    f"{PAGE_ID}-spark-total",
    f"{PAGE_ID}-spark-lacey",
    f"{PAGE_ID}-spark-centralia",
    f"{PAGE_ID}-spark-aberdeen",
    f"{PAGE_ID}-spark-avg",
    f"{PAGE_ID}-spark-selfrate",
]:
    clientside_callback(
        ClientsideFunction(namespace="sparklines", function_name="updateFromStore"),
        Output(_out_id, "figure"),
        Input(f"{PAGE_ID}-store-kpi-sparklines", "data"),
        Input(_out_id, "id"),
        Input(f"{PAGE_ID}-smooth-slider", "value"),
    )


# ---------------------------------------------------------------------------
# Volume data preparation
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


def _prepare_volume_data(df, agg, slice_by=""):
    """Prepare volume trend data for clientside rendering."""
    date_col = "AppointmentDateTime"
    if df.empty or date_col not in df.columns:
        return None

    df = df.copy()
    period_code = "Y" if agg == "Y" else agg
    df["period"] = df[date_col].dt.to_period(period_code).dt.to_timestamp()

    all_periods = sorted(df["period"].unique())
    dates = [d.isoformat() for d in all_periods]

    series = []

    if not slice_by:
        counts = df.groupby("period").size().reindex(all_periods, fill_value=0)
        series.append({
            "name": "Total",
            "values": _trim_edges(counts.tolist()),
            "color": PRIMARY,
        })

    elif slice_by == "treating":
        col = "TreatingPhysician"
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

    elif slice_by == "performing":
        col = "AppointmentPhysician"
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

    return {
        "dates": dates,
        "series": series,
        "hideLegend": len(series) <= 1,
    }


# ---------------------------------------------------------------------------
# Cumulative data preparation
# ---------------------------------------------------------------------------

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

    pos, lbl = [], []
    for i in range(0, n_days, 7):
        d = start_norm + pd.Timedelta(days=i)
        pos.append(i)
        lbl.append(d.strftime("%m/%d"))
    candidates.append((pos, lbl))

    pos, lbl = [], []
    prev_month = None
    for i in range(n_days):
        d = start_norm + pd.Timedelta(days=i)
        if d.month != prev_month:
            pos.append(i)
            lbl.append(d.strftime("%b") if n_days > 180 else d.strftime("%b %d"))
            prev_month = d.month
    candidates.append((pos, lbl))

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

    for p, l in candidates:
        if len(p) <= max_ticks:
            return p, l
    return candidates[-1]


def _prepare_cumulative_data(df_all, start, end, date_preset,
                              mode="prior", period_type="calendar",
                              slice_by="dept"):
    """Prepare cumulative volume data for overlay chart."""
    date_col = "AppointmentDateTime"
    if df_all.empty or date_col not in df_all.columns:
        return None

    today = pd.Timestamp.now().normalize()
    if end.normalize() > today:
        end = today

    period_days = (end - start).days + 1
    if period_days < 2:
        return None

    dff_all = df_all.copy()
    if dff_all.empty:
        return None

    def _cumulative_for_window(dfa, w_start, w_end):
        mask = (dfa[date_col] >= w_start) & (dfa[date_col] <= w_end)
        sub = dfa.loc[mask]
        if sub.empty:
            return []
        daily = sub.groupby(sub[date_col].dt.normalize()).size()
        idx = pd.date_range(w_start.normalize(), w_end.normalize(), freq="D")
        daily = daily.reindex(idx, fill_value=0)
        return daily.cumsum().tolist()

    def _slice_totals_for_window(dfa, w_start, w_end, sb):
        mask = (dfa[date_col] >= w_start) & (dfa[date_col] <= w_end)
        sub = dfa.loc[mask]
        if sub.empty:
            return {}
        if sb == "dept" and "Department" in sub.columns:
            return sub.groupby("Department").size().to_dict()
        elif sb == "treating" and "TreatingPhysician" in sub.columns:
            counts = sub.groupby("TreatingPhysician").size()
            return {(k.split(",")[0] if "," in k else k): v for k, v in counts.items()}
        elif sb == "performing" and "AppointmentPhysician" in sub.columns:
            counts = sub.groupby("AppointmentPhysician").size()
            return {(k.split(",")[0] if "," in k else k): v for k, v in counts.items()}
        return {}

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

    n_days = period_days
    start_norm = start.normalize()

    tick_positions, tick_labels = _build_day_index_ticks(start_norm, n_days)

    current_vals = _cumulative_for_window(dff_all, start, end) if not dff_all.empty else [0] * n_days
    data_min = dff_all[date_col].min() if not dff_all.empty else start

    def _period_label(p_start, p_end):
        same_year = p_start.year == p_end.year
        same_month = same_year and p_start.month == p_end.month
        if same_month:
            return p_start.strftime("%b %Y")
        if same_year:
            # Only use year-only label for calendar mode (rolling windows
            # within the same year would all get identical "2025" labels)
            if period_type == "calendar" and (
                date_preset in ("ytd", "last_year")
                or (p_start.month == 1 and p_end.month == 12)
            ):
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
    else:
        slice_colors = {k: CHART_COLORWAY[i % len(CHART_COLORWAY)]
                       for i, k in enumerate(slice_keys_sorted)}

    # Build sliceBreakdown for bar mode (reversed so oldest is first)
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
            "dayIndices": list(range(n_days)),
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
            "yTitle": "Cumulative Weekly Checks",
        }

    # --- Slice mode ---
    mask = (dff_all[date_col] >= start) & (dff_all[date_col] <= end)
    dff_period = dff_all.loc[mask]

    dates_range = pd.date_range(start.normalize(), end.normalize(), freq="D")

    series = []

    if slice_by == "dept" and "Department" in dff_period.columns:
        for dept in sorted(dff_period["Department"].dropna().unique()):
            sub = dff_period[dff_period["Department"] == dept]
            daily = sub.groupby(sub[date_col].dt.normalize()).size()
            daily = daily.reindex(dates_range, fill_value=0)
            series.append({
                "name": dept,
                "values": _trimmed_cumsum(daily),
                "color": DEPARTMENT_COLORS.get(dept, CHART_COLORWAY[0]),
            })

    elif slice_by == "treating" and "TreatingPhysician" in dff_period.columns:
        for i, phys in enumerate(sorted(dff_period["TreatingPhysician"].dropna().unique())):
            sub = dff_period[dff_period["TreatingPhysician"] == phys]
            daily = sub.groupby(sub[date_col].dt.normalize()).size()
            daily = daily.reindex(dates_range, fill_value=0)
            series.append({
                "name": phys.split(",")[0] if "," in phys else phys,
                "values": _trimmed_cumsum(daily),
                "color": CHART_COLORWAY[i % len(CHART_COLORWAY)],
            })

    elif slice_by == "performing" and "AppointmentPhysician" in dff_period.columns:
        for i, phys in enumerate(sorted(dff_period["AppointmentPhysician"].dropna().unique())):
            sub = dff_period[dff_period["AppointmentPhysician"] == phys]
            daily = sub.groupby(sub[date_col].dt.normalize()).size()
            daily = daily.reindex(dates_range, fill_value=0)
            series.append({
                "name": phys.split(",")[0] if "," in phys else phys,
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
        "yTitle": "Cumulative Weekly Checks",
    }


# ---------------------------------------------------------------------------
# Coverage heatmap
# ---------------------------------------------------------------------------

def _build_coverage_chart(df):
    """Heatmap of treating physician vs appointment physician."""
    if df.empty:
        return empty_figure("No weekly visit data")

    if "TreatingPhysician" not in df.columns or "AppointmentPhysician" not in df.columns:
        return empty_figure("Physician columns not available")

    coverage = (
        df.groupby(["TreatingPhysician", "AppointmentPhysician"])
        .size()
        .unstack(fill_value=0)
    )

    if coverage.empty:
        return empty_figure("No coverage data")

    rows = [p for p in PHYSICIANS if p in coverage.index]
    cols = [p for p in PHYSICIANS if p in coverage.columns]

    if not rows or not cols:
        return empty_figure("No physician coverage data")

    coverage = coverage.loc[rows, cols]

    short_rows = [r.split(",")[0] for r in rows]
    short_cols = [c.split(",")[0] for c in cols]

    fig = go.Figure(go.Heatmap(
        x=short_cols,
        y=short_rows,
        z=coverage.values,
        colorscale="Blues",
        text=coverage.values,
        texttemplate="%{text}",
        textfont={"size": 12},
        hovertemplate=(
            "Treating: %{y}<br>Appointment: %{x}<br>Count: %{z}<extra></extra>"
        ),
    ))
    apply_default_layout(fig, height=380)
    fig.update_layout(
        xaxis_title=dict(text="Appointment Physician", font=dict(size=12, color="#6B7280")),
        yaxis_title=dict(text="Treating Physician", font=dict(size=12, color="#6B7280")),
        margin=dict(l=80, r=16, t=24, b=48),
    )
    return fig


# ---------------------------------------------------------------------------
# Billing mix chart (horizontal bar)
# ---------------------------------------------------------------------------

# Weekly visit procedure codes and descriptions
_OTV_CPT_LABELS = {
    "77427": "77427",
    "77435": "77435",
    "77432": "77432",
    "77431": "77431",
}
_OTV_CPT_DESCRIPTIONS = {
    "77427": "Weekly Radiation Management",
    "77435": "SBRT Management",
    "77432": "Stereotactic Treatment Management",
    "77431": "Radiation Treatment Mgmt, 1-2 Fractions",
}
# Codes to exclude from billing chart
_OTV_CPT_EXCLUDE = frozenset({"77336"})


def _build_billing_mix(dff, slice_by="", mode="count"):
    """Horizontal bar chart of OTV billing codes."""
    if dff.empty or "ProcedureCodes" not in dff.columns:
        return empty_figure("Billing data unavailable")

    cols = ["ProcedureCodes"]
    slice_col = None
    if slice_by == "treating" and "TreatingPhysician" in dff.columns:
        cols.append("TreatingPhysician")
        slice_col = "TreatingPhysician"
    elif slice_by == "performing" and "AppointmentPhysician" in dff.columns:
        cols.append("AppointmentPhysician")
        slice_col = "AppointmentPhysician"
    elif slice_by == "dept" and "Department" in dff.columns:
        cols.append("Department")
        slice_col = "Department"

    work = dff[cols].copy()
    work = work.dropna(subset=["ProcedureCodes"])
    work = work[work["ProcedureCodes"].str.strip() != ""]

    if work.empty:
        return empty_figure("No billing data found")

    # Explode comma-separated codes
    work["_code"] = work["ProcedureCodes"].str.split(",")
    work = work.explode("_code")
    work["_code"] = work["_code"].str.strip()

    # Separate NC-modifier codes
    nc_mask = work["_code"].str.endswith(" NC", na=False)
    nc_rows = work[nc_mask].copy()
    work = work[~nc_mask]

    # Strip modifiers
    work["_base"] = work["_code"].str.split(" ").str[0]
    work["_base"] = work["_base"].str.split("-").str[0]
    work["_code"] = work["_base"]

    # Filter out excluded codes
    work = work[~work["_code"].isin(_OTV_CPT_EXCLUDE)]

    n_nc = len(nc_rows)
    if work.empty and n_nc == 0:
        return empty_figure("No billing codes found")

    code_totals = work["_code"].value_counts() if not work.empty else pd.Series(dtype=int)
    code_order = list(reversed(code_totals.index.tolist()))
    if n_nc > 0:
        code_order = ["No Charge"] + code_order

    fig = go.Figure()

    if not slice_by or not slice_col:
        regular_codes = [c for c in code_order if c != "No Charge"]
        counts = code_totals.reindex(regular_codes, fill_value=0)
        raw_codes = list(counts.index)
        vals = counts.tolist()
        labels = [_OTV_CPT_LABELS.get(c, c) for c in raw_codes]
        if n_nc > 0:
            vals = [n_nc] + vals
            labels = ["No Charge"] + labels
            raw_codes = ["No Charge"] + raw_codes

        descs = [_OTV_CPT_DESCRIPTIONS.get(c, c) for c in raw_codes]

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
        else:
            colors = {g: CHART_COLORWAY[i % len(CHART_COLORWAY)]
                      for i, g in enumerate(groups_list)}

        regular_codes = [c for c in code_order if c != "No Charge"]
        for grp in groups_list:
            subset = work[work[slice_col] == grp]
            counts = subset["_code"].value_counts().reindex(regular_codes, fill_value=0)
            raw_codes = list(counts.index)
            vals = counts.tolist()
            labels = [_OTV_CPT_LABELS.get(c, c) for c in raw_codes]

            if n_nc > 0:
                nc_slice = len(nc_rows[nc_rows[slice_col] == grp]) if slice_col in nc_rows.columns else 0
                vals = [nc_slice] + vals
                labels = ["No Charge"] + labels
                raw_codes = ["No Charge"] + raw_codes

            descs = [_OTV_CPT_DESCRIPTIONS.get(c, c) for c in raw_codes]

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


# ---------------------------------------------------------------------------
# Detail table
# ---------------------------------------------------------------------------

def _build_detail_table(df):
    """Build AG Grid table data and column definitions."""
    display_cols = [
        "AppointmentDateTime", "Department", "TreatingPhysician",
        "AppointmentPhysician", "ActivityName", "PatientFullName",
        "ProcedureCodes", "DurationMinutes",
    ]
    available_cols = [c for c in display_cols if c in df.columns]
    if not available_cols:
        return [], []

    table_df = df[available_cols].head(200).copy()

    for c in table_df.select_dtypes(include=["datetime64"]).columns:
        table_df[c] = table_df[c].dt.strftime("%m/%d/%Y %I:%M %p")

    table_df = table_df.fillna("\u2014")

    col_labels = {
        "AppointmentDateTime": "Date",
        "Department": "Department",
        "TreatingPhysician": "Treating MD",
        "AppointmentPhysician": "Performing MD",
        "ActivityName": "Activity",
        "PatientFullName": "Patient",
        "ProcedureCodes": "CPT",
        "DurationMinutes": "Duration (min)",
    }

    col_defs = [
        {"field": c, "headerName": col_labels.get(c, c),
         "sortable": True, "filter": True, "resizable": True}
        for c in available_cols
    ]

    return table_df.to_dict("records"), col_defs
