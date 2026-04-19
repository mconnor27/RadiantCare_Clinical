"""Machine Downtime page — multi-level drill-down analysis of linac downtime,
patient impact, and course-level disruption across all treatment machines."""

import dash
import dash_mantine_components as dmc
import dash_ag_grid as dag
from dash import callback, clientside_callback, ClientsideFunction, Input, Output, State, dcc, html, no_update, ctx, ALL
from dash_iconify import DashIconify
import plotly.graph_objects as go
import pandas as pd
import numpy as np
from datetime import timedelta

from config.settings import (
    DEPARTMENT_COLORS, CHART_COLORWAY, PRIMARY, MACHINE_DEPT, MACHINE_COLORS,
    DEFAULT_LAYOUT, FONT_FAMILY, NEUTRAL, SEMANTIC_COLORS,
    DEFAULT_COLUMN_DEFS, DEFAULT_GRID_OPTIONS, DEFAULT_GRID_STYLE, DEFAULT_GRID_CLASS,
)
from components.kpi_card import kpi_card, kpi_placeholder
from components.chart_card import chart_card, register_chart_callbacks
from components.detail_table import detail_table
from components.phi import apply_phi_grid_rules
from utils.charts import apply_default_layout, empty_figure
from utils.date_slider import (
    month_idx, idx_to_date, MAX_IDX, SLIDER_MARKS, DEFAULT_SLIDER,
    preset_to_slider_val, preset_to_exact_dates,
)

dash.register_page(__name__, path="/machines", name="Machine Downtime", order=8)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ALL_MACHINES = ["TrueBeamNorth", "21EX", "21iX_CEN", "21iX_AB", "6EX"]
ACTIVE_MACHINES = ["TrueBeamNorth", "21EX", "21iX_CEN", "21iX_AB"]

CONFIDENCE_COLORS = {"High": "#D32F2F", "Medium": "#FF9800", "Low": "#FFC107"}

PAGE_ID = "machines"


def _machine_color(machine):
    return MACHINE_COLORS.get(machine, CHART_COLORWAY[0])


# ---------------------------------------------------------------------------
# Condition Builder — field registry, operator labels, presets
# ---------------------------------------------------------------------------

FILTER_FIELDS = {
    "GapMinutes":      {"label": "Duration (min)",    "type": "slider",  "ops": [">=", "<=", ">", "<", "between"],
                        "slider_min": 10, "slider_max": 180, "slider_step": 5},
    "RowType":         {"label": "Event Type",        "type": "multi",   "ops": ["is_any_of"],
                        "options": [
                            {"value": "Gap", "label": "Intraday Gap"},
                            {"value": "StartOfDay", "label": "Start of Day"},
                            {"value": "EndOfDay", "label": "End of Day"},
                            {"value": "FullDay", "label": "Full Day Down"},
                        ]},
    "DowntimeType":    {"label": "Downtime Type",     "type": "multi",   "ops": ["is_any_of"],
                        "options": [
                            {"value": "Equipment Fault", "label": "Equipment Fault"},
                            {"value": "Vendor Response", "label": "Vendor Response"},
                            {"value": "Patient Logistics", "label": "Patient Logistics"},
                            {"value": "Unclassified", "label": "Unclassified"},
                        ]},
    "LocalConfidence": {"label": "Confidence",        "type": "multi",   "ops": ["is_any_of"],
                        "options": [
                            {"value": "High", "label": "High"},
                            {"value": "Medium", "label": "Medium"},
                            {"value": "Low", "label": "Low"},
                        ]},
    "CancelledInGap":  {"label": "Cancelled Appts",   "type": "slider",  "ops": [">=", "<=", ">", "<", "=="],
                        "slider_min": 0, "slider_max": 10, "slider_step": 1},
    "MachineErrorsNearGap": {"label": "Machine Errors", "type": "number", "ops": [">=", "<=", ">", "<", "=="]},
    "LastFieldTerminationStatus": {"label": "Termination", "type": "select", "ops": ["=="],
                        "options": [
                            {"value": "MACHINE", "label": "Machine"},
                        ]},
    "EventNote":       {"label": "Downtime Note",     "type": "exists",  "ops": ["exists", "not_exists"]},
    "MUDeliveredPct":  {"label": "MU Delivered %",     "type": "slider",  "ops": ["<=", ">=", "<", ">", "between"],
                        "slider_min": 0, "slider_max": 100, "slider_step": 5},
    "RerouteMachine":  {"label": "Reroute",           "type": "exists",  "ops": ["exists", "not_exists"]},
}

OP_LABELS = {
    ">=": ">=", "<=": "<=", ">": ">", "<": "<", "==": "is", "between": "between",
    "is_any_of": "is any of", "exists": "exists", "not_exists": "does not exist",
}

FIELD_OPTIONS = [{"value": k, "label": v["label"]} for k, v in FILTER_FIELDS.items()]

DEFAULT_FILTER_RULES = {
    "groupJoin": "OR",
    "groups": [
        {"join": "AND", "rules": [
            {"field": "EventNote", "op": "exists", "value": True},
            {"field": "CancelledInGap", "op": ">=", "value": 1},
        ]},
        {"join": "OR", "rules": [
            {"field": "LastFieldTerminationStatus", "op": "==", "value": "MACHINE"},
        ]},
        {"join": "OR", "rules": [
            {"field": "RowType", "op": "is_any_of", "value": ["FullDay"]},
        ]},
    ],
}

FILTER_PRESETS = {
    "cancelled": {
        "groupJoin": "AND",
        "groups": [
            {"join": "AND", "rules": [
                {"field": "EventNote", "op": "exists", "value": True},
                {"field": "CancelledInGap", "op": ">=", "value": 1},
            ]},
        ],
    },
    "probable": {
        "groupJoin": "OR",
        "groups": [
            {"join": "AND", "rules": [
                {"field": "EventNote", "op": "exists", "value": True},
                {"field": "CancelledInGap", "op": ">=", "value": 1},
            ]},
            {"join": "OR", "rules": [
                {"field": "LastFieldTerminationStatus", "op": "==", "value": "MACHINE"},
            ]},
            {"join": "OR", "rules": [
                {"field": "RowType", "op": "is_any_of", "value": ["FullDay"]},
            ]},
        ],
    },
    "clear": {"groupJoin": "AND", "groups": []},
}


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------

layout = dmc.Stack(
    gap=16,
    className="page-content",
    children=[
        # --- Sticky header ---
        dmc.Box(
            className="page-sticky-header",
            children=[
                html.Div(
                    style={"position": "relative"},
                    children=[
                        dmc.Title("Machine Downtime", order=2, className="page-title"),
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
                                "position": "absolute", "top": -4, "right": 8,
                                "zIndex": 10, "display": "none", "cursor": "pointer",
                            },
                        ),
                    ],
                ),
                dmc.Paper(
                    children=[
                        dmc.Group(
                            children=[
                                # Machine filter
                                dmc.Group(gap=8, align="center", children=[
                                    dmc.Text("Machine", size="sm", c="#9CA3AF", fw=500),
                                    dmc.ChipGroup(
                                        id=f"{PAGE_ID}-filter-machine",
                                        children=[
                                            dmc.Chip(m, value=m, size="sm", variant="filled",
                                                     color={"TrueBeamNorth": "blue", "21EX": "blue",
                                                            "21iX_CEN": "red", "21iX_AB": "green",
                                                            "6EX": "gray"}.get(m, "blue"))
                                            for m in ALL_MACHINES
                                        ],
                                        value=list(ACTIVE_MACHINES),
                                        multiple=True,
                                    ),
                                ]),
                                # Signal filters — condition builder panel
                                html.Div(
                                    style={"position": "relative", "display": "inline-block"},
                                    children=[
                                        dmc.Button(
                                            id=f"{PAGE_ID}-filter-trigger",
                                            variant="light",
                                            size="sm",
                                            color="violet",
                                            leftSection=DashIconify(icon="mdi:filter-variant", width=16),
                                            rightSection=DashIconify(icon="mdi:chevron-down", width=14),
                                            children=[
                                                html.Span("Filters", id=f"{PAGE_ID}-filter-trigger-label"),
                                            ],
                                        ),
                                        dmc.Paper(
                                            id=f"{PAGE_ID}-filter-panel",
                                            p="sm",
                                            shadow="md",
                                            withBorder=True,
                                            radius="md",
                                            className="wf-chip-dropdown mcb-panel",
                                            style={"display": "none"},
                                            children=[
                                                # Preset buttons
                                                dmc.Group(gap=6, mb="xs", className="mcb-preset-row", children=[
                                                    dmc.Button("Probable Downtime", id=f"{PAGE_ID}-preset-probable",
                                                               size="compact-xs", variant="light", color="orange",
                                                               leftSection=DashIconify(icon="mdi:alert-circle-outline", width=14)),
                                                    dmc.Button("Cancelled Appts", id=f"{PAGE_ID}-preset-cancelled",
                                                               size="compact-xs", variant="light", color="red",
                                                               leftSection=DashIconify(icon="mdi:calendar-remove", width=14)),
                                                    dmc.Button("Clear", id=f"{PAGE_ID}-preset-clear",
                                                               size="compact-xs", variant="subtle", color="gray",
                                                               leftSection=DashIconify(icon="mdi:close", width=14)),
                                                ]),
                                                dmc.Divider(my="xs"),
                                                # Builder container — rebuilt dynamically
                                                html.Div(id=f"{PAGE_ID}-builder-container"),
                                            ],
                                        ),
                                    ],
                                ),
                            ],
                            gap="lg", wrap="wrap",
                        ),
                        # Date controls row — matches courses/plans pattern
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
                                    value="12mo",
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
                                        start_date=idx_to_date(preset_to_slider_val("12mo", MAX_IDX)[0]).strftime("%Y-%m-%d"),
                                        end_date=idx_to_date(preset_to_slider_val("12mo", MAX_IDX)[1], end_of_month=True).strftime("%Y-%m-%d"),
                                        className="wf-date-picker-range",
                                    ),
                                    px="xs", py=4, radius="sm", withBorder=True,
                                    className="wf-datepicker-wrapper",
                                ),
                                dmc.Box(
                                    children=[
                                        html.Div(id=f"{PAGE_ID}-date-range-label", style={"display": "none"}),
                                        dmc.RangeSlider(
                                            id=f"{PAGE_ID}-date-slider",
                                            min=0, max=MAX_IDX, step=1,
                                            value=preset_to_slider_val("12mo", MAX_IDX),
                                            marks=SLIDER_MARKS,
                                            color="violet", size="sm", minRange=0,
                                        ),
                                    ],
                                    style={"flex": "1", "minWidth": "280px"},
                                ),
                            ],
                            gap="md", align="center", mt="xs",
                        ),
                    ],
                    p="sm", px="md", radius="md", shadow="xs", withBorder=True,
                ),
            ],
        ),

        # --- KPI row ---
        dmc.Grid(id=f"{PAGE_ID}-kpi-row", gutter=16, children=[
            dmc.GridCol(kpi_placeholder(), span={"base": 12, "sm": 6, "md": 2.4}) for _ in range(5)
        ]),

        # --- Narrative summary ---
        dmc.Paper(
            dmc.Text(id=f"{PAGE_ID}-narrative", size="sm", c=NEUTRAL["text_primary"],
                     style={"lineHeight": 1.7},
                     children=[
                         dmc.Stack(gap=6, children=[
                             dmc.Skeleton(height=12, width="90%", radius="sm"),
                             dmc.Skeleton(height=12, width="75%", radius="sm"),
                             dmc.Skeleton(height=12, width="60%", radius="sm"),
                         ]),
                     ]),
            p="md", radius="md", shadow="xs", withBorder=True,
            style={"borderLeft": f"4px solid {PRIMARY}"},
        ),

        # --- Breadcrumb navigation ---
        html.Div("All Years", id=f"{PAGE_ID}-breadcrumb", className="machines-breadcrumb"),

        # --- Drill-down containers ---
        # Level 1: Year overview cards (SVG rendered by clientside)
        dmc.Box(id=f"{PAGE_ID}-level1-container", children=[
            html.Div(id=f"{PAGE_ID}-year-cards-container", children=[
                dmc.Group(gap="md", wrap="nowrap", style={"overflowX": "auto"}, children=[
                    dmc.Paper(
                        dmc.Stack(gap=8, children=[
                            dmc.Skeleton(height=14, width="50%", radius="sm"),
                            dmc.Skeleton(height=72, radius="sm"),
                            dmc.Group(gap="xs", children=[
                                dmc.Skeleton(height=10, width="40%", radius="sm"),
                                dmc.Skeleton(height=10, width="40%", radius="sm"),
                            ]),
                        ]),
                        p="sm", radius="md", withBorder=True,
                        style={"minWidth": 200, "height": 146, "flex": "1"},
                    )
                    for _ in range(7)
                ]),
            ]),
        ]),

        # Level 2: Month heatmap (SVG rendered)
        dmc.Box(id=f"{PAGE_ID}-level2-container", style={"display": "none"}, children=[
            html.Div(id=f"{PAGE_ID}-month-heatmap-container"),
        ]),

        # Level 3: Daily timeline strip
        dmc.Box(id=f"{PAGE_ID}-level3-container", style={"display": "none"}, children=[
            dmc.Group(gap="sm", justify="center", mb=4, children=[
                dmc.ActionIcon(
                    DashIconify(icon="tabler:chevron-left", width=18),
                    id=f"{PAGE_ID}-timeline-prev", variant="subtle", color="gray", size="sm",
                ),
                dmc.Text(id=f"{PAGE_ID}-timeline-date-label", size="sm", fw=500, c=NEUTRAL["text_primary"]),
                dmc.ActionIcon(
                    DashIconify(icon="tabler:chevron-right", width=18),
                    id=f"{PAGE_ID}-timeline-next", variant="subtle", color="gray", size="sm",
                ),
                dmc.Switch(
                    id=f"{PAGE_ID}-timeline-show-unmatched",
                    label="Show unmatched gaps",
                    size="xs",
                    checked=False,
                    ml="md",
                ),
            ]),
            html.Div(id=f"{PAGE_ID}-timeline-svg-container", className="machines-timeline-container"),
        ]),

        # --- Continuous Strip View ---
        dmc.Paper(
            children=[
                dmc.Group(justify="space-between", mb=0, children=[
                    dmc.Text("Treatment Activity Strip", size="sm", fw=500, c=NEUTRAL["text_secondary"]),
                    dmc.SegmentedControl(
                        id=f"{PAGE_ID}-strip-range",
                        data=[
                            {"value": "3mo", "label": "3 Mo"},
                            {"value": "6mo", "label": "6 Mo"},
                            {"value": "1yr", "label": "1 Year"},
                            {"value": "3yr", "label": "3 Years"},
                            {"value": "all", "label": "All"},
                        ],
                        value="1yr", size="xs",
                    ),
                ]),
                dmc.Text(
                    "Each column = one workday  |  Y-axis = time of day  |  Click a day to drill in",
                    size="xs", c="#9CA3AF", mb=4,
                ),
                html.Div(id=f"{PAGE_ID}-strip-svg-container", className="machines-strip-container",
                         children=[
                             dmc.Stack(gap=4, children=[
                                 dmc.Skeleton(height=20, radius="sm"),
                                 dmc.Skeleton(height=20, radius="sm"),
                                 dmc.Skeleton(height=20, radius="sm"),
                                 dmc.Skeleton(height=20, radius="sm"),
                             ]),
                         ]),
            ],
            p="sm", radius="md", shadow="xs", withBorder=True,
        ),

        # --- Always-visible charts ---
        dmc.Grid(gutter=16, children=[
            dmc.GridCol(
                chart_card(
                    f"{PAGE_ID}-chart-trend", "Downtime Trend",
                    chart_types=[
                        {"value": "line", "label": "Line"},
                        {"value": "area", "label": "Area"},
                        {"value": "bar", "label": "Bar"},
                    ],
                    chart_type_default="area",
                    smooth_max=40, smooth_default=10, store_data=True,
                    extra_controls_left=[
                        dmc.SegmentedControl(
                            id=f"{PAGE_ID}-trend-metric",
                            data=[
                                {"value": "hours", "label": "Hours"},
                                {"value": "events", "label": "Events"},
                            ],
                            value="hours", size="xs",
                        ),
                    ],
                    extra_controls=[
                        dmc.SegmentedControl(
                            id=f"{PAGE_ID}-trend-agg",
                            data=[
                                {"value": "D", "label": "Daily"},
                                {"value": "W", "label": "Weekly"},
                                {"value": "M", "label": "Monthly"},
                            ],
                            value="M", size="xs",
                        ),
                    ],
                ),
                span={"base": 12, "md": 6},
            ),
            dmc.GridCol(
                chart_card(
                    f"{PAGE_ID}-chart-patient-impact", "Patient Impact",
                    chart_types=[
                        {"value": "line", "label": "Line"},
                        {"value": "area", "label": "Area"},
                        {"value": "bar", "label": "Bar"},
                    ],
                    chart_type_default="area",
                    smooth_max=30, smooth_default=4, store_data=True,
                    extra_controls_left=[
                        dmc.SegmentedControl(
                            id=f"{PAGE_ID}-patient-impact-mode",
                            data=[
                                {"value": "appt", "label": "Appt"},
                                {"value": "course", "label": "Course"},
                            ],
                            value="appt", size="xs",
                        ),
                    ],
                    extra_controls=[
                        dmc.SegmentedControl(
                            id=f"{PAGE_ID}-patient-impact-agg",
                            data=[
                                {"value": "D", "label": "Daily"},
                                {"value": "W", "label": "Weekly"},
                                {"value": "M", "label": "Monthly"},
                            ],
                            value="M", size="xs",
                        ),
                    ],
                ),
                span={"base": 12, "md": 6},
            ),
        ]),

        # --- Detail table ---
        detail_table(
            f"{PAGE_ID}-detail-table",
            title="Downtime Gap Detail",
            export_id=f"{PAGE_ID}-table-export",
            column_size="autoSize",
            extra_controls=[
                dmc.Button(
                    "Clear Filters",
                    id=f"{PAGE_ID}-table-clear-filters",
                    size="compact-xs",
                    variant="light",
                    color="red",
                    leftSection=DashIconify(icon="mdi:filter-remove", width=14),
                    style={"display": "none"},
                ),
            ],
        ),

        # --- Stores ---
        dcc.Store(id=f"{PAGE_ID}-store-drill", data={"level": 1, "year": None, "month": None, "day": None}),
        dcc.Store(id=f"{PAGE_ID}-store-filter-rules", data=DEFAULT_FILTER_RULES),
        dcc.Store(id=f"{PAGE_ID}-store-gaps-agg", data=None),
        dcc.Store(id=f"{PAGE_ID}-store-gaps-daily", data=None),
        dcc.Store(id=f"{PAGE_ID}-store-timeline", data={}),
        dcc.Store(id=f"{PAGE_ID}-store-strip", data=None),
        dcc.Store(id=f"{PAGE_ID}-table-filter-rows"),
        dcc.Store(id=f"{PAGE_ID}-store-year-click", data=None),
        dcc.Store(id=f"{PAGE_ID}-store-day-click", data=None),
        dcc.Store(id=f"{PAGE_ID}-store-kpi-sparklines", data={}),

        # Interval for periodic refresh
        dcc.Interval(id=f"{PAGE_ID}-interval", interval=300_000, n_intervals=0),
    ],
)


# ---------------------------------------------------------------------------
# Register chart settings callbacks
# ---------------------------------------------------------------------------
register_chart_callbacks([
    (f"{PAGE_ID}-chart-trend", f"{PAGE_ID}-chart-trend", f"{PAGE_ID}-chart-trend-store"),
    {"sid": f"{PAGE_ID}-chart-patient-impact", "gid": f"{PAGE_ID}-chart-patient-impact",
     "store_id": f"{PAGE_ID}-chart-patient-impact-store", "show_grouping": False},
])


# ---------------------------------------------------------------------------
# Condition Builder — layout helpers
# ---------------------------------------------------------------------------

def _build_condition_row(rule, index_str):
    """Render a single condition row with field/op/value selects + remove button."""
    field = rule.get("field")
    op = rule.get("op")
    value = rule.get("value")

    field_meta = FILTER_FIELDS.get(field, {}) if field else {}
    ops = field_meta.get("ops", [])
    op_data = [{"value": o, "label": OP_LABELS.get(o, o)} for o in ops]

    # Value widget depends on field type
    value_widget = html.Div()  # placeholder for exists / not_exists / no field
    ftype = field_meta.get("type", "")

    if ftype == "slider":
        s_min = field_meta.get("slider_min", 0)
        s_max = field_meta.get("slider_max", 100)
        s_step = field_meta.get("slider_step", 1)
        if op == "between":
            lo = value[0] if isinstance(value, list) and len(value) > 0 else s_min
            hi = value[1] if isinstance(value, list) and len(value) > 1 else s_max
            value_widget = dmc.Box(className="mcb-value-widget", style={"minWidth": 160}, children=[
                dmc.RangeSlider(
                    id={"type": "mcb-value", "index": index_str},
                    min=s_min, max=s_max, step=s_step,
                    value=[lo or s_min, hi or s_max],
                    size="sm", color="violet",
                    marks=[{"value": s_min, "label": str(s_min)}, {"value": s_max, "label": str(s_max)}],
                    styles={"markLabel": {"fontSize": "10px"}},
                ),
                dmc.NumberInput(
                    id={"type": "mcb-value2", "index": index_str},
                    value=None, size="xs", style={"display": "none"},
                ),
            ])
        else:
            val = value if value is not None else (s_max if op in ("<=", "<") else s_min)
            value_widget = dmc.Box(className="mcb-value-widget", style={"minWidth": 160}, children=[
                dmc.Slider(
                    id={"type": "mcb-value", "index": index_str},
                    min=s_min, max=s_max, step=s_step,
                    value=val, size="sm", color="violet",
                    marks=[{"value": s_min, "label": str(s_min)}, {"value": s_max, "label": str(s_max)}],
                    styles={"markLabel": {"fontSize": "10px"}},
                ),
                dmc.NumberInput(
                    id={"type": "mcb-value2", "index": index_str},
                    value=None, size="xs", style={"display": "none"},
                ),
            ])
    elif ftype == "number" and op == "between":
        lo = value[0] if isinstance(value, list) and len(value) > 0 else None
        hi = value[1] if isinstance(value, list) and len(value) > 1 else None
        value_widget = dmc.Group(gap=4, wrap="nowrap", className="mcb-value-widget", children=[
            dmc.NumberInput(
                id={"type": "mcb-value", "index": index_str},
                value=lo, size="xs", placeholder="min",
                style={"flex": "1"},
            ),
            dmc.NumberInput(
                id={"type": "mcb-value2", "index": index_str},
                value=hi, size="xs", placeholder="max",
                style={"flex": "1"},
            ),
        ])
    elif ftype == "number":
        value_widget = dmc.NumberInput(
            id={"type": "mcb-value", "index": index_str},
            value=value, size="xs", placeholder="0",
            className="mcb-value-widget",
        )
    elif ftype == "multi":
        value_widget = dmc.MultiSelect(
            id={"type": "mcb-value", "index": index_str},
            data=field_meta.get("options", []),
            value=value if isinstance(value, list) else [],
            size="xs", placeholder="Select...",
            className="mcb-value-widget",
            comboboxProps={"zIndex": 10000, "offset": 2}, maxDropdownHeight=300,
        )
    elif ftype == "select":
        value_widget = dmc.Select(
            id={"type": "mcb-value", "index": index_str},
            data=field_meta.get("options", []),
            value=value if isinstance(value, str) else None,
            size="xs", placeholder="Select...",
            className="mcb-value-widget",
            comboboxProps={"zIndex": 10000, "offset": 2}, maxDropdownHeight=300,
        )
    else:
        # exists/not_exists or no field — hidden placeholder to keep pattern-matching happy
        value_widget = dmc.Select(
            id={"type": "mcb-value", "index": index_str},
            data=[], value=None, size="xs",
            style={"display": "none"},
            className="mcb-value-widget",
        )

    # For between, we need the value2 ID to exist even when not between
    between_extra = []
    if not (ftype == "number" and op == "between"):
        between_extra = [dmc.NumberInput(
            id={"type": "mcb-value2", "index": index_str},
            value=None, size="xs",
            style={"display": "none"},
        )]

    return dmc.Group(
        gap=6, wrap="nowrap", align="center", className="mcb-condition-row",
        children=[
            dmc.Select(
                id={"type": "mcb-field", "index": index_str},
                data=FIELD_OPTIONS,
                value=field,
                size="xs", placeholder="Field...",
                className="mcb-field-select",
                comboboxProps={"zIndex": 10000, "offset": 2}, maxDropdownHeight=300,
            ),
            dmc.Select(
                id={"type": "mcb-op", "index": index_str},
                data=op_data,
                value=op if op in [o["value"] for o in op_data] else (op_data[0]["value"] if op_data else None),
                size="xs", placeholder="Op",
                className="mcb-op-select",
                comboboxProps={"zIndex": 10000, "offset": 2}, maxDropdownHeight=300,
            ),
            value_widget,
            *between_extra,
            dmc.ActionIcon(
                DashIconify(icon="mdi:close", width=14),
                id={"type": "mcb-remove", "index": index_str},
                variant="subtle", color="gray", size="xs",
            ),
        ],
    )


def _build_group_card(group, group_idx):
    """Render a single group card with its ALL/ANY header and condition rows."""
    join_val = group.get("join", "AND")
    rules = group.get("rules", [])

    rows = []
    for i, rule in enumerate(rules):
        idx_str = f"{group_idx}-{i}"
        rows.append(_build_condition_row(rule, idx_str))

    header = dmc.Group(
        gap=8, wrap="nowrap", align="center", mb=6,
        children=[
            dmc.SegmentedControl(
                id={"type": "mcb-join", "index": str(group_idx)},
                data=[
                    {"value": "AND", "label": "ALL"},
                    {"value": "OR", "label": "ANY"},
                ],
                value=join_val, size="xs", color="violet",
            ),
            dmc.Text("of these", size="xs", c="#9CA3AF"),
            dmc.Button(
                "Condition",
                id={"type": "mcb-add-rule", "index": str(group_idx)},
                size="compact-xs", variant="subtle", color="gray",
                leftSection=DashIconify(icon="mdi:plus", width=14),
            ),
            dmc.ActionIcon(
                DashIconify(icon="mdi:close", width=16),
                id={"type": "mcb-remove-group", "index": str(group_idx)},
                variant="subtle", color="gray", size="xs",
                ml="auto",
            ),
        ],
    )

    return dmc.Paper(
        children=[header, *rows],
        p="xs", radius="md", withBorder=True,
        className="mcb-group-card",
    )


# ---------------------------------------------------------------------------
# Condition Builder — callbacks
# ---------------------------------------------------------------------------

@callback(
    Output(f"{PAGE_ID}-builder-container", "children"),
    Input(f"{PAGE_ID}-store-filter-rules", "data"),
)
def render_condition_builder(rules_data):
    """Rebuild the condition builder UI from the filter rules store."""
    if not rules_data:
        rules_data = {"groupJoin": "AND", "groups": []}

    groups = rules_data.get("groups", [])
    group_join = rules_data.get("groupJoin", "AND")

    children = []

    # Top bar: group join toggle + add group button (only show toggle if >1 group)
    top_children = []
    if len(groups) > 1:
        top_children.extend([
            dmc.Text("Groups match by", size="xs", c="#9CA3AF"),
            dmc.SegmentedControl(
                id=f"{PAGE_ID}-group-join",
                data=[
                    {"value": "AND", "label": "ALL"},
                    {"value": "OR", "label": "ANY"},
                ],
                value=group_join, size="xs", color="orange",
            ),
        ])
    else:
        # Hidden placeholder for the group join toggle
        top_children.append(
            dmc.SegmentedControl(
                id=f"{PAGE_ID}-group-join",
                data=[{"value": "AND", "label": "ALL"}, {"value": "OR", "label": "ANY"}],
                value=group_join, size="xs",
                style={"display": "none"},
            ),
        )

    top_children.append(
        dmc.Button(
            "Group",
            id=f"{PAGE_ID}-add-group",
            size="compact-xs", variant="subtle", color="violet",
            leftSection=DashIconify(icon="mdi:plus-circle-outline", width=14),
            ml="auto",
        ),
    )

    children.append(dmc.Group(gap=8, align="center", mb="xs", children=top_children))

    # Render each group card with connector labels between them
    for i, group in enumerate(groups):
        if i > 0 and len(groups) > 1:
            connector_label = "OR" if group_join == "OR" else "AND"
            connector_color = "#E8590C" if group_join == "OR" else "#7C2A83"
            children.append(
                dmc.Text(
                    connector_label, size="xs", fw=700, c=connector_color,
                    ta="center", my=2,
                )
            )
        children.append(_build_group_card(group, i))

    if not groups:
        children.append(
            dmc.Text("No filter groups. Click + Group to add one.", size="xs", c="#9CA3AF", ta="center", py="md")
        )

    return dmc.Stack(gap=4, children=children)


def _collect_groups_from_components(fields, ops, values, values2, joins,
                                    field_ids, op_ids, value_ids, value2_ids, join_ids):
    """Reconstruct the groups list from pattern-matching component values."""
    # Build flat map: "groupIdx-ruleIdx" → {field, op, value}
    conditions = {}
    for fid, f_val in zip(field_ids, fields):
        conditions.setdefault(fid["index"], {})["field"] = f_val
    for oid, o_val in zip(op_ids, ops):
        conditions.setdefault(oid["index"], {})["op"] = o_val
    for vid, v_val in zip(value_ids, values):
        conditions.setdefault(vid["index"], {})["value"] = v_val
    for vid, v_val in zip(value2_ids, values2):
        conditions.setdefault(vid["index"], {})["value2"] = v_val

    # Build join map: group_idx → join value
    join_map = {}
    for jid, j_val in zip(join_ids, joins):
        join_map[jid["index"]] = j_val

    # Find all group indices
    group_indices = sorted({idx.split("-")[0] for idx in conditions}, key=lambda x: int(x))

    groups = []
    for gi in group_indices:
        group_join = join_map.get(gi, "AND")
        rule_indices = sorted(
            [idx for idx in conditions if idx.startswith(f"{gi}-")],
            key=lambda x: int(x.split("-")[1]),
        )
        rules = []
        for ri in rule_indices:
            cond = conditions[ri]
            rule = {"field": cond.get("field"), "op": cond.get("op")}
            if cond.get("op") == "between" and cond.get("value2") is not None:
                rule["value"] = [cond.get("value"), cond.get("value2")]
            else:
                rule["value"] = cond.get("value")
            rules.append(rule)
        groups.append({"join": group_join, "rules": rules})

    return groups


@callback(
    Output(f"{PAGE_ID}-store-filter-rules", "data", allow_duplicate=True),
    # Value changes
    Input({"type": "mcb-field", "index": ALL}, "value"),
    Input({"type": "mcb-op", "index": ALL}, "value"),
    Input({"type": "mcb-value", "index": ALL}, "value"),
    Input({"type": "mcb-value2", "index": ALL}, "value"),
    Input({"type": "mcb-join", "index": ALL}, "value"),
    # Structural buttons
    Input({"type": "mcb-add-rule", "index": ALL}, "n_clicks"),
    Input({"type": "mcb-remove", "index": ALL}, "n_clicks"),
    Input({"type": "mcb-remove-group", "index": ALL}, "n_clicks"),
    # Top-level controls
    Input(f"{PAGE_ID}-group-join", "value"),
    Input(f"{PAGE_ID}-add-group", "n_clicks"),
    State(f"{PAGE_ID}-store-filter-rules", "data"),
    prevent_initial_call=True,
)
def update_filter_rules(fields, ops, values, values2, joins,
                        add_rule_clicks, remove_clicks, remove_group_clicks,
                        group_join_val, add_group_clicks,
                        current_rules):
    """Handle all condition builder interactions → update the filter rules store."""
    triggered = ctx.triggered_id
    if not triggered:
        return no_update

    current_rules = current_rules or {"groupJoin": "AND", "groups": []}

    # Top-level group join toggle
    if triggered == f"{PAGE_ID}-group-join":
        current_rules["groupJoin"] = group_join_val or "AND"
        return current_rules

    # Add new group
    if triggered == f"{PAGE_ID}-add-group":
        current_rules["groups"].append({
            "join": "AND",
            "rules": [{"field": None, "op": None, "value": None}],
        })
        return current_rules

    if not isinstance(triggered, dict):
        return no_update

    action_type = triggered.get("type", "")
    action_index = triggered.get("index", "")

    # Collect current state from components
    field_ids = [item["id"] for item in ctx.inputs_list[0]]
    op_ids = [item["id"] for item in ctx.inputs_list[1]]
    value_ids = [item["id"] for item in ctx.inputs_list[2]]
    value2_ids = [item["id"] for item in ctx.inputs_list[3]]
    join_ids = [item["id"] for item in ctx.inputs_list[4]]

    groups = _collect_groups_from_components(
        fields, ops, values, values2, joins,
        field_ids, op_ids, value_ids, value2_ids, join_ids,
    )
    result = {"groupJoin": current_rules.get("groupJoin", "AND"), "groups": groups}

    # Field change — reset op/value
    if action_type == "mcb-field":
        gi, ri = action_index.split("-")
        gi, ri = int(gi), int(ri)
        if gi < len(result["groups"]) and ri < len(result["groups"][gi]["rules"]):
            rule = result["groups"][gi]["rules"][ri]
            field = rule.get("field")
            if field and field in FILTER_FIELDS:
                meta = FILTER_FIELDS[field]
                rule["op"] = meta["ops"][0] if meta["ops"] else None
                ftype = meta["type"]
                if ftype == "exists":
                    rule["value"] = True
                elif ftype == "multi":
                    rule["value"] = []
                elif ftype == "slider":
                    rule["value"] = meta.get("slider_max", 100) if rule["op"] in ("<=", "<") else meta.get("slider_min", 0)
                else:
                    rule["value"] = None

    # Add rule to group
    if action_type == "mcb-add-rule":
        gi = int(action_index)
        if gi < len(result["groups"]):
            result["groups"][gi]["rules"].append({"field": None, "op": None, "value": None})

    # Remove rule
    if action_type == "mcb-remove":
        gi, ri = action_index.split("-")
        gi, ri = int(gi), int(ri)
        if gi < len(result["groups"]) and ri < len(result["groups"][gi]["rules"]):
            result["groups"][gi]["rules"].pop(ri)
            if not result["groups"][gi]["rules"]:
                result["groups"].pop(gi)

    # Remove group
    if action_type == "mcb-remove-group":
        gi = int(action_index)
        if gi < len(result["groups"]):
            result["groups"].pop(gi)

    return result


# Preset buttons
@callback(
    Output(f"{PAGE_ID}-store-filter-rules", "data", allow_duplicate=True),
    Input(f"{PAGE_ID}-preset-cancelled", "n_clicks"),
    Input(f"{PAGE_ID}-preset-probable", "n_clicks"),
    Input(f"{PAGE_ID}-preset-clear", "n_clicks"),
    prevent_initial_call=True,
)
def apply_preset(_c1, _c2, _c3):
    triggered = ctx.triggered_id
    if not triggered:
        return no_update
    key = triggered.replace(f"{PAGE_ID}-preset-", "")
    import copy
    return copy.deepcopy(FILTER_PRESETS.get(key, DEFAULT_FILTER_RULES))


# Filter label — show rule count on trigger button
clientside_callback(
    """function(filterRules) {
        if (!filterRules || !filterRules.groups || filterRules.groups.length === 0) {
            return "Filters";
        }
        var count = 0;
        filterRules.groups.forEach(function(g) {
            (g.rules || []).forEach(function(r) {
                if (r.field) count++;
            });
        });
        if (count === 0) return "Filters";
        var nGroups = filterRules.groups.length;
        if (nGroups > 1) return "Filters (" + count + " rules, " + nGroups + " groups)";
        return "Filters (" + count + ")";
    }""",
    Output(f"{PAGE_ID}-filter-trigger-label", "children"),
    Input(f"{PAGE_ID}-store-filter-rules", "data"),
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _machine_lifespans(df):
    """Derive each machine's active lifespan (first/last date with Gap rows)."""
    if df.empty:
        return {}
    gap_rows = df[df["RowType"] == "Gap"]
    if gap_rows.empty:
        return {}
    spans = gap_rows.groupby("Machine")["DowntimeDate"].agg(["min", "max"])
    return {m: (row["min"], row["max"]) for m, row in spans.iterrows()}


def _apply_lifespan_filter(df):
    """Filter FullDay rows to each machine's active lifespan.

    Avoids counting downtime before install or after decommission.
    """
    if df.empty:
        return df
    lifespans = _machine_lifespans(df)
    if not lifespans:
        return df
    fd_mask = df["RowType"] == "FullDay"
    if not fd_mask.any():
        return df
    span_df = pd.DataFrame(
        [(m, s, e) for m, (s, e) in lifespans.items()],
        columns=["Machine", "_life_start", "_life_end"],
    )
    fd_sub = df.loc[fd_mask].copy()
    fd_sub["_orig_idx"] = fd_sub.index
    fd_rows = fd_sub.merge(span_df, on="Machine", how="left")
    in_range = (
        fd_rows["_life_start"].notna()
        & (fd_rows["DowntimeDate"] >= fd_rows["_life_start"])
        & (fd_rows["DowntimeDate"] <= fd_rows["_life_end"])
    )
    drop_idx = fd_rows.loc[~in_range, "_orig_idx"]
    return df.drop(index=drop_idx)


_ALL_ROW_TYPES = {"Gap", "StartOfDay", "EndOfDay", "FullDay"}


# ---------------------------------------------------------------------------
# Condition Builder — evaluation engine
# ---------------------------------------------------------------------------

def _evaluate_condition(df, rule):
    """Evaluate a single condition rule, returning a boolean Series or None if incomplete."""
    field = rule.get("field")
    op = rule.get("op")
    value = rule.get("value")

    if not field or not op:
        return None
    if field not in df.columns:
        return None

    col = df[field]

    # For GapMinutes, only apply to Gap rows — other RowTypes always pass
    if field == "GapMinutes" and op in (">=", "<=", ">", "<", "between"):
        gap_mask = df["RowType"] == "Gap"
        if op == ">=":
            return ~gap_mask | (col.fillna(0) >= (value or 0))
        elif op == "<=":
            return ~gap_mask | (col.fillna(0) <= (value or 0))
        elif op == ">":
            return ~gap_mask | (col.fillna(0) > (value or 0))
        elif op == "<":
            return ~gap_mask | (col.fillna(0) < (value or 0))
        elif op == "between":
            if not isinstance(value, list) or len(value) < 2:
                return None
            lo, hi = value[0] or 0, value[1] or 0
            return ~gap_mask | ((col.fillna(0) >= lo) & (col.fillna(0) <= hi))

    if op == ">=":
        return col.notna() & (col >= (value or 0))
    elif op == "<=":
        return col.notna() & (col <= (value or 0))
    elif op == ">":
        return col.notna() & (col > (value or 0))
    elif op == "<":
        return col.notna() & (col < (value or 0))
    elif op == "==":
        return col == value
    elif op == "between":
        if not isinstance(value, list) or len(value) < 2:
            return None
        lo, hi = value[0] or 0, value[1] or 0
        return col.notna() & (col >= lo) & (col <= hi)
    elif op == "is_any_of":
        if not value:
            return None
        return col.isin(value)
    elif op == "exists":
        return col.notna() & (col.astype(str) != "") & (col.astype(str).str.lower() != "none")
    elif op == "not_exists":
        return col.isna() | (col.astype(str) == "") | (col.astype(str).str.lower() == "none")

    return None


def _evaluate_group(df, group):
    """Evaluate a single group's rules against a DataFrame, returning a boolean mask."""
    if df.empty or not group or not group.get("rules"):
        return pd.Series(True, index=df.index)

    masks = []
    for rule in group["rules"]:
        mask = _evaluate_condition(df, rule)
        if mask is not None:
            masks.append(mask)

    if not masks:
        return pd.Series(True, index=df.index)

    combined = masks[0]
    if group.get("join") == "OR":
        for m in masks[1:]:
            combined = combined | m
    else:
        for m in masks[1:]:
            combined = combined & m

    return combined


def _evaluate_filter_rules(df, filter_rules):
    """Evaluate the full filter rules (multiple peer groups joined by groupJoin)."""
    if df.empty or not filter_rules:
        return pd.Series(True, index=df.index)

    groups = filter_rules.get("groups", [])
    if not groups:
        return pd.Series(True, index=df.index)

    group_masks = []
    for group in groups:
        group_masks.append(_evaluate_group(df, group))

    if not group_masks:
        return pd.Series(True, index=df.index)

    combined = group_masks[0]
    if filter_rules.get("groupJoin") == "OR":
        for m in group_masks[1:]:
            combined = combined | m
    else:
        for m in group_masks[1:]:
            combined = combined & m

    return combined


def _filter_gaps(df, machines, filter_rules, slider_val):
    """Apply machine filter, condition builder rules, and date filter."""
    if df.empty:
        return df

    df = _apply_lifespan_filter(df.copy())

    # Machine filter (from chips — separate from condition builder)
    if machines:
        df = df[df["Machine"].isin(machines)]

    # Apply condition builder rules
    if filter_rules and filter_rules.get("groups"):
        mask = _evaluate_filter_rules(df, filter_rules)
        df = df[mask]

    # Date filter from slider
    if slider_val:
        start_date = idx_to_date(slider_val[0])
        end_date = idx_to_date(slider_val[1], end_of_month=True)
        df = df[(df["DowntimeDate"] >= start_date) & (df["DowntimeDate"] <= end_date)]

    return df


def _build_yearly_summary(df):
    """Aggregate gaps by year for Level 1 year cards."""
    if df.empty:
        return []

    holidays = _get_holidays_set()
    df = df.copy()

    # Use pre-deduped events from cache when possible
    gap_evt, _ = _get_deduped_events(df)

    # Filter fullday rows — exclude weekends/holidays
    fd_rows = df[df["RowType"] == "FullDay"]
    if not fd_rows.empty:
        _wd = fd_rows["DowntimeDate"].dt.dayofweek
        fd_rows = fd_rows[(_wd < 5) & (~fd_rows["DowntimeDate"].dt.normalize().isin(holidays))]

    # Aggregate gap events by year
    if not gap_evt.empty:
        gap_evt = gap_evt.copy()
        gap_evt["_year"] = gap_evt["DowntimeDate"].dt.year
        gap_evt["_month"] = gap_evt["DowntimeDate"].dt.month
        gap_by_year = gap_evt.groupby("_year").agg(
            gap_hours=("GapMinutes", "sum"),
            gapCount=("RowKey", "count"),
        )
        gap_by_year["gap_hours"] = gap_by_year["gap_hours"] / 60
        # Monthly breakdown via pivot
        monthly_pivot = gap_evt.groupby(["_year", "_month"])["GapMinutes"].sum().unstack(fill_value=0) / 60
    else:
        gap_by_year = pd.DataFrame(columns=["gap_hours", "gapCount"])
        monthly_pivot = pd.DataFrame()

    # Aggregate fullday by year
    if not fd_rows.empty:
        fd_unique = fd_rows.drop_duplicates(subset=["Machine", "DowntimeDate"])
        fd_by_year = fd_unique.groupby(fd_unique["DowntimeDate"].dt.year).size().rename("fullDayCount")
    else:
        fd_by_year = pd.Series(dtype=int, name="fullDayCount")

    # Operating hours per year (from all rows)
    df["_year"] = df["DowntimeDate"].dt.year
    year_stats = df.groupby("_year").agg(
        machines=("Machine", "nunique"),
        workdays=("DowntimeDate", lambda x: x.dt.normalize().nunique()),
    )

    all_years = sorted(set(gap_by_year.index) | set(fd_by_year.index) | set(year_stats.index), reverse=True)

    yearly = []
    for year in all_years:
        gap_hours = float(gap_by_year.at[year, "gap_hours"]) if year in gap_by_year.index else 0.0
        gap_count = int(gap_by_year.at[year, "gapCount"]) if year in gap_by_year.index else 0
        fd_count = int(fd_by_year.get(year, 0))
        total_hours = gap_hours + fd_count * 10

        n_machines = int(year_stats.at[year, "machines"]) if year in year_stats.index else 1
        workdays = int(year_stats.at[year, "workdays"]) if year in year_stats.index else 1
        op_hours = max(workdays * 10 * n_machines, 1)
        availability = max(0, (1 - total_hours / op_hours)) * 100

        monthly = [0.0] * 12
        if year in monthly_pivot.index:
            for m in monthly_pivot.columns:
                monthly[int(m) - 1] = float(monthly_pivot.at[year, m])

        yearly.append({
            "year": int(year),
            "hours": round(total_hours, 1),
            "availability": round(availability, 1),
            "gapCount": gap_count,
            "fullDayCount": fd_count,
            "monthly": [round(v, 1) for v in monthly],
        })

    return yearly


def _build_daily_summary(df):
    """Aggregate gaps + full-day outages by date for Level 2 heatmap."""
    if df.empty:
        return []

    gap_rows = df[df["RowType"].isin(["Gap", "StartOfDay", "EndOfDay"])]
    fd_rows = df[df["RowType"] == "FullDay"]
    if gap_rows.empty and fd_rows.empty:
        return []

    # Use pre-deduped events from cache, then aggregate
    gap_evt, fd_evt = _get_deduped_events(df)
    gap_daily = pd.DataFrame()
    if not gap_evt.empty:
        gap_evt = gap_evt.copy()
        gap_evt["_date"] = gap_evt["DowntimeDate"].dt.normalize()
        gap_daily = gap_evt.groupby("_date").agg(
            minutes=("GapMinutes", "sum"),
            gapCount=("RowKey", "count"),
            machines=("Machine", "unique"),
            cancelled=("CancelledInGap", "sum"),
            errors=("MachineErrorsNearGap", "sum"),
        )
        gap_daily["fullDay"] = False

    fd_daily = pd.DataFrame()
    if not fd_evt.empty:
        fd_evt = fd_evt.copy()
        fd_evt["_date"] = fd_evt["DowntimeDate"].dt.normalize()
        fd_daily = fd_evt.groupby("_date").agg(
            machines=("Machine", "unique"),
            cancelled=("CancelledInGap", "sum"),
            errors=("MachineErrorsNearGap", "sum"),
        )
        fd_daily["minutes"] = fd_daily["machines"].apply(len) * 600.0
        fd_daily["gapCount"] = fd_daily["machines"].apply(len)
        fd_daily["fullDay"] = True

    # Merge gap and fullday summaries
    if not gap_daily.empty and not fd_daily.empty:
        # For dates that have both gap and fullday entries, combine them
        both = gap_daily.index.intersection(fd_daily.index)
        for d in both:
            gap_daily.at[d, "minutes"] += fd_daily.at[d, "minutes"]
            gap_daily.at[d, "machines"] = np.unique(
                np.concatenate([gap_daily.at[d, "machines"], fd_daily.at[d, "machines"]])
            )
            gap_daily.at[d, "cancelled"] += fd_daily.at[d, "cancelled"]
            gap_daily.at[d, "fullDay"] = True
        fd_only = fd_daily.drop(both)
        combined = pd.concat([gap_daily, fd_only]).sort_index()
    elif not gap_daily.empty:
        combined = gap_daily.sort_index()
    else:
        combined = fd_daily.sort_index()

    # Convert to list of dicts (vectorized)
    records = []
    for date_val, row in combined.iterrows():
        records.append({
            "date": date_val.strftime("%Y-%m-%d"),
            "minutes": round(float(row["minutes"]), 1),
            "gapCount": int(row["gapCount"]),
            "machines": list(row["machines"]),
            "cancelled": int(row["cancelled"]),
            "errors": int(row["errors"]),
            "fullDay": bool(row["fullDay"]),
        })

    return records



def _build_trend_data(df):
    """Compute daily downtime data — clientside JS handles D/W/M aggregation.

    Uses neighbor-interpolated gap minutes (pre-computed in cache) matching
    the strip's visual rendering for all gap types including FullDay.
    """
    if df.empty:
        return {"dates": [], "series": [], "eventsSeries": []}

    gap_evt, fd_evt = _get_deduped_events(df)
    # Both already have interpolated GapMinutes from cache

    # Combine gap events + fullday events
    parts = []
    if not gap_evt.empty:
        parts.append(gap_evt[["Machine", "DowntimeDate", "GapMinutes"]])
    if not fd_evt.empty:
        parts.append(fd_evt[["Machine", "DowntimeDate", "GapMinutes"]])
    if not parts:
        return {"dates": [], "series": [], "eventsSeries": []}

    combined = pd.concat(parts, ignore_index=True)
    combined["Date"] = combined["DowntimeDate"].dt.normalize()
    machines = sorted(combined["Machine"].unique())
    all_dates = sorted(combined["Date"].unique())
    date_labels = [d.strftime("%Y-%m-%d") for d in all_dates]

    hours_series = []
    events_series = []
    for machine in machines:
        mdf = combined[combined["Machine"] == machine]
        daily_hrs = mdf.groupby("Date")["GapMinutes"].sum() / 60
        daily_cnt = mdf.groupby("Date").size()
        dept = MACHINE_DEPT.get(machine, "Unknown")
        color = DEPARTMENT_COLORS.get(dept, CHART_COLORWAY[0])
        hours_series.append({
            "name": machine,
            "values": [round(float(daily_hrs.get(d, 0)), 2) for d in all_dates],
            "color": color,
        })
        events_series.append({
            "name": machine,
            "values": [int(daily_cnt.get(d, 0)) for d in all_dates],
            "color": color,
        })

    return {
        "dates": date_labels,
        "series": hours_series,
        "eventsSeries": events_series,
    }


def _build_patient_impact_data(df):
    """Build daily cancelled/rerouted + course impact data — clientside JS handles D/W/M aggregation."""
    empty = {"dates": [], "cancelled": [], "rerouted": [], "courses": []}
    if df.empty:
        return empty

    # Patient-level rows for reroute counts, deduped events for cancellation counts
    gap_rows = df[df["RowType"].isin(["Gap", "StartOfDay", "EndOfDay"])].copy()
    if gap_rows.empty:
        return empty

    gap_rows["Date"] = gap_rows["DowntimeDate"].dt.normalize()
    gap_rows_evt, _ = _get_deduped_events(df)
    gap_rows_evt = gap_rows_evt.copy() if not gap_rows_evt.empty else pd.DataFrame()
    if not gap_rows_evt.empty:
        gap_rows_evt["Date"] = gap_rows_evt["DowntimeDate"].dt.normalize()
    all_dates = sorted(gap_rows["Date"].unique())
    date_labels = [d.strftime("%Y-%m-%d") for d in all_dates]

    # Vectorized aggregation instead of per-date loop
    daily_cancel = gap_rows_evt.groupby("Date")["CancelledInGap"].sum()
    daily_reroute = gap_rows.groupby("Date")["RerouteMachine"].apply(lambda x: (x.notna() & (x != "")).sum())
    cancelled = [int(daily_cancel.get(d, 0)) for d in all_dates]
    rerouted = [int(daily_reroute.get(d, 0)) for d in all_dates]

    # Course impact: unique courses interrupted per day
    # Index each course by the date of its first cancellation (not rerouted)
    courses = [0] * len(all_dates)
    ci_gaps = gap_rows[
        (gap_rows["CancelledInGap"] > 0)
        & (gap_rows["PatientOutcome"] != "Rerouted")
    ]
    if (not ci_gaps.empty
            and "PatientId" in ci_gaps.columns
            and "CourseName" in ci_gaps.columns):
        ci_valid = ci_gaps[ci_gaps["PatientId"].notna() & ci_gaps["CourseName"].notna()]
        if not ci_valid.empty:
            # First cancellation date per course
            first_cancel = ci_valid.groupby(["PatientId", "CourseName"])["Date"].min().reset_index()
            daily_courses = first_cancel.groupby("Date").size()
            date_to_idx = {d: i for i, d in enumerate(all_dates)}
            for d, count in daily_courses.items():
                if d in date_to_idx:
                    courses[date_to_idx[d]] = int(count)

    return {"dates": date_labels, "cancelled": cancelled, "rerouted": rerouted, "courses": courses}




def _build_detail_table(df):
    """Build detail table records from filtered gaps."""
    if df.empty:
        return []

    tdf = df.sort_values("DowntimeDate", ascending=False).head(500)
    records = []
    for i, (_, row) in enumerate(tdf.iterrows()):
        records.append({
            "_row_idx": i,
            "Date": row["DowntimeDate"].strftime("%Y-%m-%d") if pd.notna(row["DowntimeDate"]) else "\u2013",
            "Patient": str(row.get("PatientName") or row.get("PatientFullName", "")) if pd.notna(row.get("PatientName") or row.get("PatientFullName")) else "\u2013",
            "Machine": row.get("Machine") or "\u2013",
            "Start": str(row.get("GapStartTime", ""))[:5] if pd.notna(row.get("GapStartTime")) else "\u2013",
            "End": str(row.get("GapEndTime", ""))[:5] if pd.notna(row.get("GapEndTime")) else "\u2013",
            "Minutes": str(int(row["GapMinutes"])) if pd.notna(row.get("GapMinutes")) else "\u2013",
            "Type": row.get("DowntimeType") or "\u2013",
            "Classification": row.get("GapClassification") or "\u2013",
            "Cancellations": str(int(row["CancelledInGap"])) if pd.notna(row.get("CancelledInGap")) else "0",
            "Errors": str(int(row["MachineErrorsNearGap"])) if pd.notna(row.get("MachineErrorsNearGap")) else "0",
            "Reroute": str(row["RerouteMachine"]) if pd.notna(row.get("RerouteMachine")) and row.get("RerouteMachine") != "" else "\u2013",
            "Outcome": str(row.get("PatientOutcome", "")) if pd.notna(row.get("PatientOutcome")) else "\u2013",
            "CourseName": str(row.get("CourseName", "")) if pd.notna(row.get("CourseName")) else "\u2013",
            "DowntimeNote": str(row.get("DowntimeNoteMatch", "")) if pd.notna(row.get("DowntimeNoteMatch")) else "\u2013",
            "AppointmentNote": str(row.get("AppointmentNote", "")) if pd.notna(row.get("AppointmentNote")) else "\u2013",
        })
    return records


def _time_str_to_min(t):
    """Convert HH:MM:SS string to minutes from midnight."""
    if pd.isna(t):
        return None
    s = str(t)[:5]
    parts = s.split(":")
    try:
        return int(parts[0]) * 60 + int(parts[1])
    except (ValueError, IndexError):
        return None


def _get_holidays_set():
    """Get set of holiday dates (schedule-derived + static fallback)."""
    from utils.holidays import get_holidays
    try:
        return get_holidays()
    except Exception:
        return set()


_EVENT_KEYS = ("RowType", "Machine", "DowntimeDate", "GapStartTime")

_CONFIDENCE_ORDER = {"High": 3, "Medium": 2, "Low": 1}


def _dedup_events(df):
    """Deduplicate to one row per gap event for event-level aggregation.

    The SQL output is dual-grain:
      - A-branch: one row per affected patient (PatientId populated)
      - B-branch: one row per event with no patients (PatientId NULL)

    Event-level columns (GapMinutes, CancelledInGap, MachineErrorsNearGap,
    etc.) carry the same value on every A-branch row for a given gap. Summing
    without deduplication inflates counts by the number of affected patients.

    Propagation rules applied before collapsing:
      - DowntimeNoteMatch: best (first non-null) from any A-branch row
      - LocalConfidence: highest severity from any row in the event group
    """
    if df.empty:
        return df
    keys = [c for c in _EVENT_KEYS if c in df.columns]
    if not keys:
        return df

    # Sort so rows with non-null notes and highest confidence come first,
    # then a single drop_duplicates keeps the best row per event.
    df_sorted = df.copy()
    has_note = df_sorted["DowntimeNoteMatch"].notna() if "DowntimeNoteMatch" in df_sorted.columns else pd.Series(False, index=df_sorted.index)
    conf_rank = df_sorted["LocalConfidence"].map(_CONFIDENCE_ORDER).fillna(0) if "LocalConfidence" in df_sorted.columns else pd.Series(0, index=df_sorted.index)
    df_sorted["_note_rank"] = has_note.astype(int)
    df_sorted["_conf_rank"] = conf_rank
    df_sorted = df_sorted.sort_values(["_note_rank", "_conf_rank"], ascending=False)
    deduped = df_sorted.drop_duplicates(subset=keys).drop(columns=["_note_rank", "_conf_rank"])

    return deduped


_NOTE_TYPE_MAP = {
    "Machine Down": "Equipment Fault",
    "Component Down": "Equipment Fault",
    "Power": "Equipment Fault",
    "Varian Called": "Vendor Response",
    "Patient Redirected": "Patient Logistics",
}


def _compute_downtime_type(df):
    """Add DowntimeType column derived from DowntimeNoteMatch.

    Equipment Fault   — Machine Down, Component Down, Power
    Vendor Response   — Varian Called
    Patient Logistics — Patient Redirected
    Unclassified      — no note match
    """
    if df.empty or "DowntimeNoteMatch" not in df.columns:
        return df
    df = df.copy()
    df["DowntimeType"] = df["DowntimeNoteMatch"].map(_NOTE_TYPE_MAP).fillna("Unclassified")
    return df


def _compute_true_availability(df_events, start, end, machines, holidays):
    """Compute availability using actual treatment operating windows.

    Denominator: sum of per-machine-day operating windows (first_tx → last_tx)
    from Treatment-Detail for days with treatments. FullDay outage days are
    absent from Treatment-Detail — their window is estimated from that machine's
    median daily window (computed from all-time Treatment-Detail data).

    This replaces the 10-hr/day flat assumption with real schedule data.

    Returns (availability_pct, fullday_estimated_hours) or (None, None) if
    Treatment-Detail is unavailable.
    """
    from data.loader import load_treatment_detail

    if start is None or end is None:
        return None, None

    td = load_treatment_detail()
    if td.empty:
        return None, None

    td = td.copy()
    td["_date"] = td["ScheduledDateTime"].dt.normalize()
    # Minutes from midnight for first/last beam
    td["_start_min"] = td["TreatmentStartTime"].dt.hour * 60 + td["TreatmentStartTime"].dt.minute
    td["_end_min"] = td["TreatmentEndTime"].dt.hour * 60 + td["TreatmentEndTime"].dt.minute

    active = machines or ACTIVE_MACHINES
    td_m = td[td["Machine"].isin(active)]
    if td_m.empty:
        return None, None

    # Per-machine median daily operating window from all-time data
    # (used to estimate FullDay outage duration and to fill any gaps)
    all_daily = td_m.groupby(["Machine", "_date"]).agg(
        first_min=("_start_min", "min"),
        last_min=("_end_min", "max"),
    ).reset_index()
    all_daily["window_min"] = (all_daily["last_min"] - all_daily["first_min"]).clip(lower=0)
    machine_median_min = all_daily.groupby("Machine")["window_min"].median().to_dict()

    # Operating windows within the selected date range (workdays only)
    range_td = td_m[(td_m["_date"] >= start) & (td_m["_date"] <= end)]
    range_td = range_td[range_td["_date"].dt.dayofweek < 5]
    if holidays:
        range_td = range_td[~range_td["_date"].isin(holidays)]

    if not range_td.empty:
        range_daily = range_td.groupby(["Machine", "_date"]).agg(
            first_min=("_start_min", "min"),
            last_min=("_end_min", "max"),
        ).reset_index()
        range_daily["window_min"] = (range_daily["last_min"] - range_daily["first_min"]).clip(lower=0)
        total_op_min = float(range_daily["window_min"].sum())
    else:
        total_op_min = 0.0

    # FullDay outage days are missing from Treatment-Detail — add their estimated
    # operating window to both the denominator (they count as lost operating time)
    # and to the downtime total.
    fullday_est_min = 0.0
    gap_evt, fd_evt = _get_deduped_events(df_events) if not df_events.empty else (pd.DataFrame(), pd.DataFrame())
    if not fd_evt.empty:
        fd_evt = fd_evt.copy()
        fd_evt["_med"] = fd_evt["Machine"].map(machine_median_min).fillna(600)
        fullday_est_min = float(fd_evt["_med"].sum())
        total_op_min += fullday_est_min

    if total_op_min <= 0:
        return 100.0, 0.0

    gap_min = float(gap_evt["GapMinutes"].sum()) if not gap_evt.empty else 0.0

    total_downtime_min = gap_min + fullday_est_min
    availability = max(0.0, (1.0 - total_downtime_min / total_op_min)) * 100.0
    return availability, fullday_est_min / 60.0


def _compute_local_confidence(df):
    """Add LocalConfidence column based on agreed scoring tiers.

    All rows — if the gap detection algorithm found a gap in field records, it is
    real downtime. CompletedInGap reflects scheduling decisions made around the
    outage, not evidence the machine was running. Confidence tiers reflect only
    how certain we are of the cause:

    Gap / StartOfDay / EndOfDay:
      High   — DowntimeNoteMatch is not null
      Medium — LastFieldTerminationStatus == 'MACHINE'
      Low    — everything else

    FullDay rows — CancelledInGap replaces termination status as the Medium signal
    (multi-day outages often lack a note after day 1 but will show cancellations):
      High   — DowntimeNoteMatch is not null
      Medium — CancelledInGap > 0
      Low    — everything else
    """
    if df.empty:
        return df
    df = df.copy()

    has_note = df["DowntimeNoteMatch"].notna()
    is_fullday = df["RowType"] == "FullDay"
    has_cancellations = df["CancelledInGap"].fillna(0) > 0
    is_machine_term = df.get("LastFieldTerminationStatus", pd.Series("", index=df.index)) == "MACHINE"

    # Vectorized scoring with np.select (order matters — first match wins)
    conditions = [
        has_note,                                # High for any row with a note
        is_fullday & has_cancellations,          # Medium for FullDay with cancellations
        ~is_fullday & is_machine_term,           # Medium for Gap/SOD/EOD with machine termination
    ]
    choices = ["High", "Medium", "Medium"]
    df["LocalConfidence"] = np.select(conditions, choices, default="Low")

    return df


def _propagate_event_note(df):
    """Add EventNote column: the event's best non-null DowntimeNoteMatch broadcast to all rows.

    B-branch rows have null DowntimeNoteMatch in the SQL output. This propagates
    the A-branch note to all rows sharing the same event keys so that the note
    filter operates at the event level (not just on the row that happens to have it).
    Also normalises the string 'None' value (which can appear in the CSV) to NaN.
    """
    if df.empty or "DowntimeNoteMatch" not in df.columns:
        return df
    df = df.copy()
    # Normalise string 'None' → NaN
    df["DowntimeNoteMatch"] = df["DowntimeNoteMatch"].replace("None", np.nan)
    evt_keys = [c for c in _EVENT_KEYS if c in df.columns]
    if not evt_keys:
        df["EventNote"] = np.nan
        return df
    # Take first non-null note per event
    best = (
        df[df["DowntimeNoteMatch"].notna()]
        .drop_duplicates(subset=evt_keys)[evt_keys + ["DowntimeNoteMatch"]]
        .rename(columns={"DowntimeNoteMatch": "EventNote"})
    )
    df = df.drop(columns=["EventNote"], errors="ignore")
    if not best.empty:
        df = df.merge(best, on=evt_keys, how="left")
    else:
        df["EventNote"] = np.nan
    return df


# ---------------------------------------------------------------------------
# Cached transformed dataset — avoids recomputing on every callback
# ---------------------------------------------------------------------------

_transformed_cache = {"hash": None, "df": None, "gap_evt": None, "fd_evt": None}


def _get_transformed_gaps():
    """Return the fully transformed downtime gaps dataframe, cached across callbacks.

    Cache invalidates when the underlying loader returns a new object
    (i.e., after load_downtime_gaps.cache_clear() or app restart).
    On cold start, tries to load pre-computed results from disk parquet cache
    (transform + dedup + interpolation) to avoid the full 4+ second rebuild.
    """
    from data.loader import load_downtime_gaps, _read_parquet_cache, _write_parquet_cache
    from pathlib import Path
    from config.settings import DATA_INCREMENTAL

    raw = load_downtime_gaps()
    raw_id = id(raw)
    if _transformed_cache["hash"] != raw_id:
        # Try disk cache first — check if parquet is newer than source CSVs
        _src_files = sorted((DATA_INCREMENTAL / "MachineDowntimeGaps").glob("*.csv"))
        df_cached = _read_parquet_cache("DowntimeGaps_transformed", _src_files)
        gap_cached = _read_parquet_cache("DowntimeGaps_gap_evt", _src_files)
        fd_cached = _read_parquet_cache("DowntimeGaps_fd_evt", _src_files)

        if df_cached is not None and gap_cached is not None and fd_cached is not None:
            df = df_cached
            gap_evt = gap_cached
            fd_evt = fd_cached
        else:
            # Full rebuild
            df = _compute_downtime_type(
                _compute_local_confidence(
                    _propagate_event_note(raw.copy())
                )
            )
            # Compute MU Delivered % from last field before gap
            if "LastFieldPlannedMU" in df.columns and "LastFieldDeliveredMU" in df.columns:
                planned = df["LastFieldPlannedMU"].fillna(0)
                delivered = df["LastFieldDeliveredMU"].fillna(0)
                df["MUDeliveredPct"] = np.where(planned > 0, (delivered / planned * 100).round(1), np.nan)
            gap_rows = df[df["RowType"].isin(["Gap", "StartOfDay", "EndOfDay"])]
            fd_rows = df[df["RowType"] == "FullDay"]
            gap_evt = _dedup_events(gap_rows) if not gap_rows.empty else pd.DataFrame()
            fd_evt = _dedup_events(fd_rows) if not fd_rows.empty else pd.DataFrame()
            # Apply interpolated gap minutes so all consumers get consistent values
            if not gap_evt.empty or not fd_evt.empty:
                interp_map = _compute_interpolated_gap_minutes(gap_evt, fd_evt)
                gap_evt, fd_evt = _apply_interpolated_minutes(gap_evt, fd_evt, interp_map)
            # Persist to disk — convert object columns to strings for parquet compatibility
            # (datetime.time objects in mixed-type columns cause pyarrow errors)
            def _prep_for_parquet(frame):
                if frame.empty:
                    return frame
                frame = frame.copy()
                for col in frame.columns:
                    if frame[col].dtype == object:
                        frame[col] = frame[col].astype(str).replace({"NaT": "", "None": "", "nan": ""})
                return frame
            _write_parquet_cache("DowntimeGaps_transformed", _prep_for_parquet(df))
            _write_parquet_cache("DowntimeGaps_gap_evt", _prep_for_parquet(gap_evt))
            _write_parquet_cache("DowntimeGaps_fd_evt", fd_evt)

        _transformed_cache["hash"] = raw_id
        _transformed_cache["df"] = df
        _transformed_cache["gap_evt"] = gap_evt
        _transformed_cache["fd_evt"] = fd_evt
    return _transformed_cache["df"]


def _get_deduped_events(df):
    """Return pre-deduped gap and fullday event DataFrames, filtered to match df.

    Uses the cached full-dataset dedup and filters down to the rows present in df,
    avoiding redundant dedup computation. Falls back to direct dedup for subsets
    that don't align with the cached data (e.g., prior-period slices).
    """
    full_gap_evt = _transformed_cache.get("gap_evt")
    full_fd_evt = _transformed_cache.get("fd_evt")
    full_df = _transformed_cache.get("df")

    if full_gap_evt is None or full_fd_evt is None:
        # Cache not populated — fall back to direct dedup
        gap_rows = df[df["RowType"].isin(["Gap", "StartOfDay", "EndOfDay"])]
        fd_rows = df[df["RowType"] == "FullDay"]
        return (
            _dedup_events(gap_rows) if not gap_rows.empty else pd.DataFrame(),
            _dedup_events(fd_rows) if not fd_rows.empty else pd.DataFrame(),
        )

    # Fast path: if df is the full cached dataset (same object), return cached directly
    if full_df is not None and df is full_df:
        return full_gap_evt, full_fd_evt

    # Fast path: if df has the same length as full dataset, likely the same
    if full_df is not None and len(df) == len(full_df):
        return full_gap_evt, full_fd_evt

    # Filter cached deduped rows to only those present in df (by index intersection)
    df_idx = df.index
    gap_evt = full_gap_evt.loc[full_gap_evt.index.intersection(df_idx)] if not full_gap_evt.empty else pd.DataFrame()
    fd_evt = full_fd_evt.loc[full_fd_evt.index.intersection(df_idx)] if not full_fd_evt.empty else pd.DataFrame()
    return gap_evt, fd_evt


def _compute_interpolated_gap_minutes(gap_evt, fd_evt):
    """Compute interpolated gap minutes matching the strip's visual rendering.

    For each gap event, returns an adjusted GapMinutes value:
    - Intraday Gap: uses source GapMinutes as-is.
    - EndOfDay: interpolates the gap end from neighboring days' latest treatment
      time, then recomputes duration from gap start to interpolated end.
    - StartOfDay: interpolates the gap start from neighboring days' earliest
      treatment time, then recomputes duration from interpolated start to gap end.
    - FullDay: interpolates the full operating window from neighbor days.

    Returns a dict: {(Machine, DowntimeDate_str, RowType, GapStartTime_str): minutes}
    """
    from data.loader import load_treatment_detail

    td = load_treatment_detail()
    if td.empty:
        return {}

    td = td.copy()
    td["_date"] = td["ScheduledDateTime"].dt.normalize()
    td["_start_min"] = td["TreatmentStartTime"].dt.hour * 60 + td["TreatmentStartTime"].dt.minute
    td["_end_min"] = td["TreatmentEndTime"].dt.hour * 60 + td["TreatmentEndTime"].dt.minute

    # Per-machine per-day treatment windows
    tx_daily = td.groupby(["Machine", "_date"]).agg(
        ft=("_start_min", "min"),
        lt=("_end_min", "max"),
    ).reset_index()

    # Build sorted arrays per machine for O(log n) neighbor lookups
    machine_tx = {}
    for machine, grp in tx_daily.groupby("Machine"):
        grp = grp.sort_values("_date")
        dates = grp["_date"].values.astype("datetime64[ns]")
        fts = grp["ft"].values.astype(int)
        lts = grp["lt"].values.astype(int)
        machine_tx[machine] = (dates, fts, lts)

    def _neighbor_interp(machine, target_date):
        """Find nearest prev/next treatment day via binary search, return interpolated (ft, lt)."""
        if machine not in machine_tx:
            return 480, 1020
        dates, fts, lts = machine_tx[machine]
        td64 = np.datetime64(target_date)
        idx = np.searchsorted(dates, td64)

        prev_ft, prev_lt = (None, None)
        if idx > 0:
            prev_ft, prev_lt = int(fts[idx - 1]), int(lts[idx - 1])

        next_ft, next_lt = (None, None)
        # idx might point at the target date itself (if it has treatments); skip it
        ni = idx
        if ni < len(dates) and dates[ni] == td64:
            ni += 1
        if ni < len(dates):
            next_ft, next_lt = int(fts[ni]), int(lts[ni])

        if prev_ft is not None and next_ft is not None:
            return round((prev_ft + next_ft) / 2), round((prev_lt + next_lt) / 2)
        elif prev_ft is not None:
            return prev_ft, prev_lt
        elif next_ft is not None:
            return next_ft, next_lt
        return 480, 1020

    result = {}

    # Process FullDay events — interpolate full window from neighbors
    if not fd_evt.empty:
        for machine, dt in fd_evt[["Machine", "DowntimeDate"]].drop_duplicates().itertuples(index=False):
            dt_n = dt.normalize()
            ds = dt_n.strftime("%Y-%m-%d")
            interp_ft, interp_lt = _neighbor_interp(machine, dt_n)
            result[(machine, ds, "FullDay", "")] = max(0, interp_lt - interp_ft)

    # Process EndOfDay / StartOfDay gaps — interpolate boundary from neighbors
    if not gap_evt.empty:
        boundary = gap_evt[gap_evt["RowType"].isin(["EndOfDay", "StartOfDay"])].copy()
        if not boundary.empty:
            boundary["_gs"] = boundary["GapStartTime"].apply(_time_str_to_min)
            boundary["_ge"] = boundary["GapEndTime"].apply(_time_str_to_min)
            for row_type, machine, dt, gs, ge, gs_raw in zip(
                boundary["RowType"], boundary["Machine"], boundary["DowntimeDate"],
                boundary["_gs"], boundary["_ge"], boundary["GapStartTime"],
            ):
                dt_n = dt.normalize()
                ds = dt_n.strftime("%Y-%m-%d")
                gs_str = str(gs_raw)[:8] if pd.notna(gs_raw) else ""
                interp_ft, interp_lt = _neighbor_interp(machine, dt_n)

                if row_type == "EndOfDay" and gs is not None:
                    result[(machine, ds, "EndOfDay", gs_str)] = max(0, interp_lt - int(gs))
                elif row_type == "StartOfDay" and ge is not None:
                    result[(machine, ds, "StartOfDay", gs_str)] = max(0, int(ge) - interp_ft)

    return result


def _apply_interpolated_minutes(gap_evt, fd_evt, interp_map):
    """Apply interpolated minutes to gap and fullday event dataframes.

    Returns (gap_evt_with_adjusted_minutes, fd_evt_with_minutes).
    """
    if not gap_evt.empty:
        gap_evt = gap_evt.copy()
        is_boundary = gap_evt["RowType"].isin(["EndOfDay", "StartOfDay"])
        if is_boundary.any():
            keys = (
                gap_evt.loc[is_boundary, "Machine"]
                + "|" + gap_evt.loc[is_boundary, "DowntimeDate"].dt.strftime("%Y-%m-%d")
                + "|" + gap_evt.loc[is_boundary, "RowType"]
                + "|" + gap_evt.loc[is_boundary, "GapStartTime"].fillna("").astype(str).str[:8]
            )
            # Build a fast lookup from the interp_map
            flat_map = {f"{m}|{d}|{rt}|{gs}": v for (m, d, rt, gs), v in interp_map.items()
                        if rt in ("EndOfDay", "StartOfDay")}
            gap_evt.loc[is_boundary, "GapMinutes"] = keys.map(flat_map).fillna(
                gap_evt.loc[is_boundary, "GapMinutes"]
            ).astype(float)

    if not fd_evt.empty:
        fd_evt = fd_evt.copy()
        keys = fd_evt["Machine"] + "|" + fd_evt["DowntimeDate"].dt.strftime("%Y-%m-%d") + "|FullDay|"
        flat_map = {f"{m}|{d}|FullDay|": v for (m, d, rt, gs), v in interp_map.items() if rt == "FullDay"}
        fd_evt["GapMinutes"] = keys.map(flat_map).fillna(600).astype(float)

    return gap_evt, fd_evt


def _build_strip_data(gaps_df, machines, start_date, end_date):
    """Build per-machine per-day strip data for the continuous activity strip.

    Uses Treatment-Detail for the base treatment windows (all workdays),
    overlays downtime gaps, and marks full-day outages.
    Excludes weekends and holidays so there are no empty columns.

    Day format: [date_str, firstMin, lastMin, gaps, fullDayDown]
      - fullDayDown: true if machine was completely offline that day

    Returns compact format:
        {machines, colors, data: {machine: [...]}}
    """
    from data.loader import load_treatment_detail

    td = load_treatment_detail()
    if td.empty:
        return {"machines": [], "colors": {}, "data": {}}

    # Get holidays to exclude from the date index
    holidays = _get_holidays_set()

    # Filter Treatment-Detail to date range + machines
    td = td.copy()
    td["_date"] = td["ScheduledDateTime"].dt.normalize()
    td = td[(td["_date"] >= start_date) & (td["_date"] <= end_date)]
    if machines:
        td = td[td["Machine"].isin(machines)]
    if td.empty:
        return {"machines": [], "colors": {}, "data": {}}

    active_machines = sorted(td["Machine"].unique())
    colors = {m: DEPARTMENT_COLORS.get(MACHINE_DEPT.get(m, ""), CHART_COLORWAY[0])
              for m in active_machines}

    # Build the master workday index: all business days in range, minus holidays
    all_bdays = pd.bdate_range(start_date, end_date)
    if holidays:
        all_bdays = all_bdays[~all_bdays.isin(holidays)]
    workday_set = set(all_bdays.normalize())

    # Build treatment windows: per machine per day → first/last treatment time
    td["_start_min"] = td["TreatmentStartTime"].dt.hour * 60 + td["TreatmentStartTime"].dt.minute
    td["_end_min"] = td["TreatmentEndTime"].dt.hour * 60 + td["TreatmentEndTime"].dt.minute
    tx_daily = td.groupby(["Machine", "_date"]).agg(
        ft=("_start_min", "min"),
        lt=("_end_min", "max"),
    ).reset_index()
    tx_daily["_date_str"] = tx_daily["_date"].dt.strftime("%Y-%m-%d")

    # Build gap lookup: (machine, date_str) → [[gs, ge, conf], ...]
    gap_lookup = {}
    fullday_lookup = set()  # (machine, date_str) for full-day outages

    if not gaps_df.empty:
        # Include Gap, EndOfDay, and StartOfDay rows — all have valid start/end times
        # Dedup to one row per event to avoid rendering duplicate overlays
        gap_rows = gaps_df[gaps_df["RowType"].isin(["Gap", "EndOfDay", "StartOfDay"])]
        gap_rows = _dedup_events(gap_rows) if not gap_rows.empty else gap_rows
        gap_rows = gap_rows.copy()
        if not gap_rows.empty:
            gap_rows["_gs"] = gap_rows["GapStartTime"].apply(_time_str_to_min)
            gap_rows["_ge"] = gap_rows["GapEndTime"].apply(_time_str_to_min)
            conf_col = "LocalConfidence" if "LocalConfidence" in gap_rows.columns else "DowntimeConfidence"
            gap_rows["_conf"] = gap_rows[conf_col].str[0].fillna("L")
            gap_rows["_date_str"] = gap_rows["DowntimeDate"].dt.strftime("%Y-%m-%d")
            # Tag EndOfDay/StartOfDay gaps so JS can interpolate their boundary times
            gap_rows["_is_eod"] = gap_rows["RowType"] == "EndOfDay"
            gap_rows["_is_bod"] = gap_rows["RowType"] == "StartOfDay"

            for (machine, date_str), dg in gap_rows.groupby(["Machine", "_date_str"]):
                valid = dg[dg["_gs"].notna() & dg["_ge"].notna()]
                if not valid.empty:
                    gap_lookup[(machine, date_str)] = list(zip(
                        valid["_gs"].astype(int).tolist(),
                        valid["_ge"].astype(int).tolist(),
                        valid["_conf"].tolist(),
                        valid["_is_eod"].tolist(),
                        valid["_is_bod"].tolist(),
                    ))

        # Full-day outages (RowType == "FullDay")
        fd_rows = gaps_df[gaps_df["RowType"] == "FullDay"]
        if not fd_rows.empty:
            for _, r in fd_rows[["Machine", "DowntimeDate"]].drop_duplicates().iterrows():
                ds = r["DowntimeDate"].strftime("%Y-%m-%d") if pd.notna(r["DowntimeDate"]) else None
                if ds:
                    fullday_lookup.add((r["Machine"], ds))

    # Assemble per-machine day arrays
    # Include ALL workdays — treatment days get their window, non-treatment
    # workdays are included too (either full-day outage or no activity).
    workday_strs = sorted(d.strftime("%Y-%m-%d") for d in workday_set)

    result = {}
    for machine in active_machines:
        # Build lookup of treatment windows for this machine
        mtx = tx_daily[tx_daily["Machine"] == machine]
        tx_lookup = {}
        for ds, ft, lt in zip(
            mtx["_date_str"].tolist(),
            mtx["ft"].astype(int).tolist(),
            mtx["lt"].astype(int).tolist(),
        ):
            tx_lookup[ds] = (ft, lt)

        # Determine machine's active lifespan (first→last treatment date)
        # to avoid showing full-day outages for dates before install or after decommission
        tx_dates = sorted(tx_lookup.keys())
        machine_first = tx_dates[0] if tx_dates else None
        machine_last = tx_dates[-1] if tx_dates else None

        days = []
        for ds in workday_strs:
            tx = tx_lookup.get(ds)
            is_fullday = (machine, ds) in fullday_lookup

            if tx:
                ft, lt = tx
                gaps = gap_lookup.get((machine, ds), [])
                if gaps:
                    # [start, end, confidence, isEndOfDay, isStartOfDay]
                    gaps = [[s, e, c, eod, bod] for s, e, c, eod, bod in gaps]
                days.append([ds, ft, lt, gaps, False])
            elif is_fullday and machine_first and machine_last and machine_first <= ds <= machine_last:
                # Full-day outage — only within the machine's active lifespan
                days.append([ds, None, None, [], True])
            # else: skip — machine not yet installed, already decommissioned,
            # or simply no activity on this day

        result[machine] = days

    return {"machines": active_machines, "colors": colors, "data": result}


# ---------------------------------------------------------------------------
# Main data callback
# ---------------------------------------------------------------------------

@callback(
    Output(f"{PAGE_ID}-kpi-row", "children"),
    Output(f"{PAGE_ID}-narrative", "children"),
    Output(f"{PAGE_ID}-store-gaps-agg", "data"),
    Output(f"{PAGE_ID}-chart-trend-store", "data"),
    Output(f"{PAGE_ID}-chart-patient-impact-store", "data"),
    Output(f"{PAGE_ID}-detail-table", "columnDefs"),
    Output(f"{PAGE_ID}-detail-table", "rowData"),
    Output(f"{PAGE_ID}-store-kpi-sparklines", "data"),
    Input(f"{PAGE_ID}-interval", "n_intervals"),
    Input(f"{PAGE_ID}-filter-machine", "value"),
    Input(f"{PAGE_ID}-store-filter-rules", "data"),
    Input(f"{PAGE_ID}-date-slider", "value"),
    Input(f"{PAGE_ID}-filter-date-preset", "value"),
    Input(f"{PAGE_ID}-table-filter-rows", "data"),
    running=[
        (Output(f"{PAGE_ID}-chart-trend-loading", "visible"), True, False),
        (Output(f"{PAGE_ID}-chart-patient-impact-loading", "visible"), True, False),
    ],
)
def update_main_data(_n, machines, filter_rules, slider_val, date_preset, grid_filter_rows):
    # Resolve date range early — needed for availability and prior-period calcs
    start = idx_to_date(slider_val[0]) if slider_val else None
    end = idx_to_date(slider_val[1], end_of_month=True) if slider_val else None

    df_all = _get_transformed_gaps()
    # Apply lifespan + non-date filters to full dataset (for prior period / heatmap)
    df_all_filtered = _filter_gaps(df_all, machines, filter_rules, slider_val=None)

    df = _filter_gaps(df_all, machines, filter_rules, slider_val)

    # Table gets the full filtered df; KPIs/charts may be further filtered by grid column filters
    df_for_table = df
    triggered_by_grid = (
        ctx.triggered_id == f"{PAGE_ID}-table-filter-rows"
    )
    if grid_filter_rows is not None and isinstance(grid_filter_rows, list) and len(grid_filter_rows) > 0:
        # The table is built from df sorted desc by date, head 500.
        # _row_idx in the grid corresponds to position in that sorted/sliced result.
        # We need to map those indices back to df rows.
        tdf = df.sort_values("DowntimeDate", ascending=False).head(500)
        grid_idx_set = set(grid_filter_rows)
        # Select only the rows at those positions in tdf
        selected_positions = [i for i in range(len(tdf)) if i in grid_idx_set]
        if selected_positions:
            df = tdf.iloc[selected_positions]

    # --- KPIs ---
    holidays = _get_holidays_set()

    gap_rows = df[df["RowType"].isin(["Gap", "StartOfDay", "EndOfDay"])] if not df.empty else pd.DataFrame()
    fullday_rows = df[df["RowType"] == "FullDay"] if not df.empty else pd.DataFrame()
    # Deduplicated to one row per event — uses cached pre-dedup when possible.
    # Keep gap_rows (patient-level) for reroute_count, courses_interrupted, and patient sparklines.
    gap_rows_evt, fd_rows_evt = _get_deduped_events(df) if not df.empty else (pd.DataFrame(), pd.DataFrame())
    # gap_rows_evt and fd_rows_evt already have interpolated GapMinutes from cache

    # Exclude weekends and holidays — no treatments expected, not real outages
    if not fullday_rows.empty:
        _wd = fullday_rows["DowntimeDate"].dt.dayofweek
        _is_workday = (_wd < 5) & (~fullday_rows["DowntimeDate"].dt.normalize().isin(holidays))
        fullday_rows = fullday_rows[_is_workday]

    gap_hours = gap_rows_evt["GapMinutes"].sum() / 60 if not gap_rows_evt.empty else 0
    fullday_hours = fd_rows_evt["GapMinutes"].sum() / 60 if not fd_rows_evt.empty else 0
    fullday_count = fullday_rows.groupby(["Machine", "DowntimeDate"]).ngroups if not fullday_rows.empty else 0

    # Availability — use actual treatment operating windows from Treatment-Detail.
    # FullDay outage days are estimated from each machine's median daily window.
    # Falls back to workday count × 10 hrs if Treatment-Detail is unavailable.
    availability, fullday_est_hours = _compute_true_availability(df, start, end, machines, holidays)
    if availability is None:
        n_machines = df["Machine"].nunique() if not df.empty else len(machines or ACTIVE_MACHINES)
        all_bdays = pd.bdate_range(start, end) if start and end else []
        if holidays and len(all_bdays):
            all_bdays = all_bdays[~all_bdays.isin(holidays)]
        op_hours = len(all_bdays) * 10 * n_machines if len(all_bdays) > 0 else 1
        fullday_est_hours = fullday_hours
        availability = max(0, (1 - (gap_hours + fullday_est_hours) / op_hours)) * 100

    total_hours = gap_hours + (fullday_est_hours if fullday_est_hours is not None else fullday_hours)

    event_count = len(gap_rows_evt)
    # Include cancellations from full-day outages — those rows carry CancelledInGap too
    cancelled_total = (
        (int(gap_rows_evt["CancelledInGap"].sum()) if not gap_rows_evt.empty else 0)
        + (int(fd_rows_evt["CancelledInGap"].sum()) if not fd_rows_evt.empty else 0)
    )
    reroute_count = int((gap_rows["RerouteMachine"].notna() & (gap_rows["RerouteMachine"] != "")).sum()) if not gap_rows.empty else 0
    # Count courses interrupted (cancellations not undone by reroute)
    _ci_gaps = df[
        (df["RowType"].isin(["Gap", "StartOfDay", "EndOfDay"])) & (df["CancelledInGap"] > 0) & (df["PatientOutcome"] != "Rerouted")
    ] if not df.empty else pd.DataFrame()
    if not _ci_gaps.empty and "PatientId" in _ci_gaps.columns and "CourseName" in _ci_gaps.columns:
        _ci_valid = _ci_gaps[_ci_gaps["PatientId"].notna() & _ci_gaps["CourseName"].notna()]
        courses_interrupted = _ci_valid.groupby(["PatientId", "CourseName"]).ngroups if not _ci_valid.empty else 0
    else:
        courses_interrupted = 0

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
    prior_gap_rows = pd.DataFrame()
    prior_fullday_rows = pd.DataFrame()
    if date_preset and date_preset in _PRIOR_MAP and start is not None and end is not None:
        trend_label, prior_fn = _PRIOR_MAP[date_preset]
        prior_start, prior_end = prior_fn(start, end)
        if not df_all_filtered.empty and "DowntimeDate" in df_all_filtered.columns:
            prior_df = df_all_filtered[
                (df_all_filtered["DowntimeDate"] >= prior_start)
                & (df_all_filtered["DowntimeDate"] <= prior_end)
            ]
            prior_gap_rows = prior_df[prior_df["RowType"].isin(["Gap", "StartOfDay", "EndOfDay"])] if not prior_df.empty else pd.DataFrame()
            prior_fullday_rows = prior_df[prior_df["RowType"] == "FullDay"] if not prior_df.empty else pd.DataFrame()
            if not prior_fullday_rows.empty:
                _pwd = prior_fullday_rows["DowntimeDate"].dt.dayofweek
                prior_fullday_rows = prior_fullday_rows[
                    (_pwd < 5) & (~prior_fullday_rows["DowntimeDate"].dt.normalize().isin(holidays))
                ]

    # Compute prior-period values and trends
    _t_hours = (None, None)
    _t_avail = (None, None)
    _t_events = (None, None)
    _t_cancelled = (None, None)
    _t_reroute = (None, None)
    _t_courses = (None, None)

    if trend_label and (not prior_gap_rows.empty or not prior_fullday_rows.empty):
        prior_gap_rows_evt, p_fd_evt = _get_deduped_events(
            pd.concat([prior_gap_rows, prior_fullday_rows]) if not prior_gap_rows.empty or not prior_fullday_rows.empty else pd.DataFrame()
        )
        # Prior period deduped events already have interpolated minutes from cache
        p_gap_hours = prior_gap_rows_evt["GapMinutes"].sum() / 60 if not prior_gap_rows_evt.empty else 0
        p_fd_hours = p_fd_evt["GapMinutes"].sum() / 60 if not p_fd_evt.empty else 0
        p_fullday_count = prior_fullday_rows.groupby(["Machine", "DowntimeDate"]).ngroups if not prior_fullday_rows.empty else 0
        p_total_hours = p_gap_hours + p_fd_hours
        _t_hours = _trend(total_hours, p_total_hours, invert=True)

        # Prior availability
        p_df = pd.concat([prior_gap_rows, prior_fullday_rows]) if not prior_gap_rows.empty or not prior_fullday_rows.empty else pd.DataFrame()
        if not p_df.empty:
            p_workdays = p_df["DowntimeDate"].dt.normalize().nunique()
            p_n_machines = p_df["Machine"].nunique()
            p_op_hours = p_workdays * 10 * p_n_machines if p_n_machines > 0 else 1
            p_availability = max(0, (1 - p_total_hours / p_op_hours)) * 100
        else:
            p_availability = 100.0
        _t_avail = _trend(availability, p_availability)

        p_event_count = len(prior_gap_rows_evt)
        _t_events = _trend(event_count, p_event_count, invert=True)

        _t_fullday = _trend(fullday_count, p_fullday_count, invert=True)

        p_cancelled = (
            (int(prior_gap_rows_evt["CancelledInGap"].sum()) if not prior_gap_rows_evt.empty else 0)
            + (int(p_fd_evt["CancelledInGap"].sum()) if not p_fd_evt.empty else 0)
        )
        _t_cancelled = _trend(cancelled_total, p_cancelled, invert=True)

        p_reroute = int((prior_gap_rows["RerouteMachine"].notna() & (prior_gap_rows["RerouteMachine"] != "")).sum()) if not prior_gap_rows.empty else 0
        _t_reroute = _trend(reroute_count, p_reroute, invert=True)

        # Prior courses interrupted
        prior_df_for_courses = df_all_filtered[
            (df_all_filtered["DowntimeDate"] >= prior_start)
            & (df_all_filtered["DowntimeDate"] <= prior_end)
        ] if not df_all_filtered.empty else pd.DataFrame()
        _pci = prior_df_for_courses[
            (prior_df_for_courses["RowType"].isin(["Gap", "StartOfDay", "EndOfDay"]))
            & (prior_df_for_courses["CancelledInGap"] > 0)
            & (prior_df_for_courses["PatientOutcome"] != "Rerouted")
        ] if not prior_df_for_courses.empty else pd.DataFrame()
        if not _pci.empty and "PatientId" in _pci.columns and "CourseName" in _pci.columns:
            _pci_v = _pci[_pci["PatientId"].notna() & _pci["CourseName"].notna()]
            p_courses = _pci_v.groupby(["PatientId", "CourseName"]).ngroups if not _pci_v.empty else 0
        else:
            p_courses = 0
        _t_courses = _trend(courses_interrupted, p_courses, invert=True)

    # ------------------------------------------------------------------
    # Sparkline data — all 6 KPIs
    # ------------------------------------------------------------------
    sparkline_data = {}
    if not gap_rows.empty:
        def _grp_col(sub, date_col="DowntimeDate", _min_points=4):
            """Group by month; fall back to weekly if fewer than _min_points distinct months."""
            monthly = sub[date_col].dt.to_period("M").dt.to_timestamp()
            if monthly.nunique() >= _min_points:
                return monthly
            return sub[date_col].dt.to_period("W").dt.to_timestamp()

        # 1. Total downtime hours (event-level dedup — GapMinutes is per-event)
        grp = gap_rows_evt.copy()
        grp["_sp"] = _grp_col(grp)
        monthly_hrs = grp.groupby("_sp")["GapMinutes"].sum() / 60
        sparkline_data["hours"] = {
            "labels": [d.isoformat() for d in monthly_hrs.index],
            "values": [round(v, 1) for v in monthly_hrs.values.tolist()],
            "color": CHART_COLORWAY[2],
        }

        # 2. Availability (per period) — use pre-deduped event data
        if not gap_rows_evt.empty or not fullday_rows.empty:
            # Combine deduped gap events + fullday rows for availability calc
            _avail_gap = gap_rows_evt[["DowntimeDate", "GapMinutes", "Machine", "RowType"]].copy() if not gap_rows_evt.empty else pd.DataFrame()
            _avail_fd = fullday_rows[["DowntimeDate", "Machine", "RowType"]].copy() if not fullday_rows.empty else pd.DataFrame()
            all_rows = pd.concat([_avail_gap, _avail_fd], ignore_index=True) if not _avail_gap.empty or not _avail_fd.empty else pd.DataFrame()
            if not all_rows.empty:
                all_rows["_sp"] = _grp_col(all_rows)
                # Aggregate gap hours per period (already deduped)
                gap_part = all_rows[all_rows["RowType"].isin(["Gap", "StartOfDay", "EndOfDay"])]
                gap_hrs_per_sp = gap_part.groupby("_sp")["GapMinutes"].sum() / 60 if not gap_part.empty else pd.Series(dtype=float)
                fd_part = all_rows[all_rows["RowType"] == "FullDay"]
                fd_count_per_sp = fd_part.groupby("_sp").size() if not fd_part.empty else pd.Series(dtype=int)
                wd_per_sp = all_rows.groupby("_sp")["DowntimeDate"].apply(lambda x: x.dt.normalize().nunique())
                nm_per_sp = all_rows.groupby("_sp")["Machine"].nunique()

                periods = sorted(all_rows["_sp"].unique())
                avail_vals = []
                avail_labels = []
                for p in periods:
                    p_hrs = gap_hrs_per_sp.get(p, 0) + fd_count_per_sp.get(p, 0) * 10
                    p_op = wd_per_sp.get(p, 1) * 10 * nm_per_sp.get(p, 1)
                    avail_vals.append(round(max(0, (1 - p_hrs / max(p_op, 1))) * 100, 1))
                    avail_labels.append(p.isoformat())
                if len(avail_vals) > 2:
                    sparkline_data["availability"] = {
                        "labels": avail_labels,
                        "values": avail_vals,
                        "color": SEMANTIC_COLORS["success"],
                        "hover_fmt": "%{x|%b %Y}: %{y:.1f}%<extra></extra>",
                    }

        # 3. Events count
        events_grp = gap_rows_evt.copy()
        events_grp["_sp"] = _grp_col(events_grp)
        monthly_events = events_grp.groupby("_sp").size()
        sparkline_data["events"] = {
            "labels": [d.isoformat() for d in monthly_events.index],
            "values": monthly_events.values.tolist(),
            "color": CHART_COLORWAY[0],
        }

        # 4. Courses interrupted — unique (PatientId, CourseName) with non-rerouted cancellations per period
        interrupted_gaps = gap_rows[
            (gap_rows["CancelledInGap"] > 0)
            & (gap_rows["PatientOutcome"] != "Rerouted")
            & gap_rows["PatientId"].notna()
            & gap_rows["CourseName"].notna()
        ].copy()
        if not interrupted_gaps.empty:
            interrupted_gaps["_sp"] = _grp_col(interrupted_gaps)
            per_period = []
            for sp, grp in interrupted_gaps.groupby("_sp"):
                n_courses = grp.groupby(["PatientId", "CourseName"]).ngroups
                per_period.append((sp, n_courses))
            if len(per_period) > 1:
                sparkline_data["courses"] = {
                    "labels": [p[0].isoformat() for p in per_period],
                    "values": [p[1] for p in per_period],
                    "color": CHART_COLORWAY[3],
                }

        # 5. Cancelled appointments — include both gap and full-day outage cancellations
        _cancel_parts = [gap_rows_evt[["DowntimeDate", "CancelledInGap"]]]
        if not fullday_rows.empty:
            _cancel_parts.append(fd_rows_evt[["DowntimeDate", "CancelledInGap"]])
        cancel_rows = pd.concat(_cancel_parts)
        cancel_rows = cancel_rows[cancel_rows["CancelledInGap"] > 0].copy()
        if not cancel_rows.empty:
            cancel_rows["_sp"] = _grp_col(cancel_rows)
            monthly_cancel = cancel_rows.groupby("_sp")["CancelledInGap"].sum().astype(int)
            if len(monthly_cancel) > 1:
                sparkline_data["cancelled"] = {
                    "labels": [d.isoformat() for d in monthly_cancel.index],
                    "values": monthly_cancel.values.tolist(),
                    "color": SEMANTIC_COLORS["error"],
                }

        # 6. Rerouted patients
        reroute_rows = gap_rows[gap_rows["RerouteMachine"].notna() & (gap_rows["RerouteMachine"] != "")].copy()
        if not reroute_rows.empty:
            reroute_rows["_sp"] = _grp_col(reroute_rows)
            monthly_reroute = reroute_rows.groupby("_sp").size()
            if len(monthly_reroute) > 1:
                sparkline_data["rerouted"] = {
                    "labels": [d.isoformat() for d in monthly_reroute.index],
                    "values": monthly_reroute.values.tolist(),
                    "color": CHART_COLORWAY[4],
                }

    kpi_children = [
        dmc.GridCol(kpi_card(
            "Total Downtime", f"{total_hours:,.1f} hrs",
            accent_color=CHART_COLORWAY[2],
            sparkline_id=f"{PAGE_ID}-spark-hours",
            trend_text=f"{_t_hours[0]} {trend_label}" if _t_hours[0] else None,
            trend_direction=_t_hours[1],
        ), span={"base": 12, "sm": 6, "md": 2}),
        dmc.GridCol(kpi_card(
            "Availability", f"{availability:.1f}%",
            accent_color=SEMANTIC_COLORS["success"],
            sparkline_id=f"{PAGE_ID}-spark-availability",
            trend_text=f"{_t_avail[0]} {trend_label}" if _t_avail[0] else None,
            trend_direction=_t_avail[1],
        ), span={"base": 12, "sm": 6, "md": 2}),
        dmc.GridCol(kpi_card(
            "Downtime Events", f"{event_count:,}",
            accent_color=CHART_COLORWAY[0],
            sparkline_id=f"{PAGE_ID}-spark-events",
            trend_text=f"{_t_events[0]} {trend_label}" if _t_events[0] else None,
            trend_direction=_t_events[1],
        ), span={"base": 12, "sm": 6, "md": 2}),
        dmc.GridCol(kpi_card(
            "Cancelled Appts", f"{cancelled_total:,}",
            accent_color=SEMANTIC_COLORS["error"],
            sparkline_id=f"{PAGE_ID}-spark-cancelled",
            trend_text=f"{_t_cancelled[0]} {trend_label}" if _t_cancelled[0] else None,
            trend_direction=_t_cancelled[1],
        ), span={"base": 12, "sm": 6, "md": 2}),
        dmc.GridCol(kpi_card(
            "Patients Rerouted", f"{reroute_count:,}",
            accent_color=CHART_COLORWAY[4],
            sparkline_id=f"{PAGE_ID}-spark-rerouted",
            trend_text=f"{_t_reroute[0]} {trend_label}" if _t_reroute[0] else None,
            trend_direction=_t_reroute[1],
        ), span={"base": 12, "sm": 6, "md": 2}),
        dmc.GridCol(kpi_card(
            "Courses Interrupted", f"{courses_interrupted:,}",
            accent_color=CHART_COLORWAY[3],
            sparkline_id=f"{PAGE_ID}-spark-courses",
            trend_text=f"{_t_courses[0]} {trend_label}" if _t_courses[0] else None,
            trend_direction=_t_courses[1],
        ), span={"base": 12, "sm": 6, "md": 2}),
    ]

    # --- Pre-aggregated data for drill-down (yearly only — daily is lazy-loaded) ---
    gaps_agg = {
        "yearly": _build_yearly_summary(df_all_filtered),
    }

    trend_data = _build_trend_data(df)
    patient_impact_data = _build_patient_impact_data(df)
    detail_records = _build_detail_table(df_for_table) if not triggered_by_grid else no_update

    # --- Narrative summary ---
    if start is not None and end is not None and not df.empty:
        date_fmt = "%b %d, %Y"
        courses_affected = courses_interrupted
        parts = [
            f"From {start.strftime(date_fmt)} to {end.strftime(date_fmt)},",
            f"there were {event_count:,} downtime events totaling {total_hours:,.1f} hours",
            f"across {df['Machine'].nunique()} machines.",
        ]
        if fullday_count:
            parts.append(f"{fullday_count:,} of those were full-day outages.")
        if cancelled_total or reroute_count:
            cancel_parts = []
            if cancelled_total:
                cancel_parts.append(f"{cancelled_total:,} appointments were cancelled")
            if reroute_count:
                cancel_parts.append(f"{reroute_count:,} patients were rerouted to other machines")
            parts.append(f"{', and '.join(cancel_parts)}.")
        if courses_affected:
            parts.append(f"{courses_affected:,} patient courses were interrupted.")
        narrative = " ".join(parts)
    else:
        narrative = ""

    detail_col_defs = apply_phi_grid_rules([
        {"field": "Date", "headerName": "Date", "maxWidth": 130, "sort": "desc"},
        {"field": "Patient", "headerName": "Patient", "maxWidth": 160},
        {"field": "Machine", "headerName": "Machine", "maxWidth": 145},
        {"field": "Start", "headerName": "Start", "maxWidth": 95},
        {"field": "End", "headerName": "End", "maxWidth": 95},
        {"field": "Minutes", "headerName": "Duration", "maxWidth": 120, "type": "numericColumn"},
        {"field": "Type", "headerName": "Type"},
        {"field": "Classification", "headerName": "Classification"},
        {"field": "Cancellations", "headerName": "Cancelled", "maxWidth": 125, "type": "numericColumn"},
        {"field": "Errors", "headerName": "Errors", "maxWidth": 100},
        {"field": "Reroute", "headerName": "Reroute", "maxWidth": 110},
        {"field": "Outcome", "headerName": "Outcome", "maxWidth": 115},
        {"field": "CourseName", "headerName": "Course"},
        {"field": "DowntimeNote", "headerName": "Downtime Note"},
        {"field": "AppointmentNote", "headerName": "Appointment Note", "minWidth": 500},
    ])

    return (
        kpi_children,
        narrative,
        gaps_agg,
        trend_data,
        patient_impact_data,
        detail_col_defs if not triggered_by_grid else no_update,
        detail_records,
        sparkline_data,
    )


# ---------------------------------------------------------------------------
# Date controls sync (preset ↔ slider ↔ datepicker)
# ---------------------------------------------------------------------------

# A) Preset → Slider + DatePicker
@callback(
    Output(f"{PAGE_ID}-date-slider", "value"),
    Output(f"{PAGE_ID}-filter-daterange", "start_date", allow_duplicate=True),
    Output(f"{PAGE_ID}-filter-daterange", "end_date", allow_duplicate=True),
    Input(f"{PAGE_ID}-filter-date-preset", "value"),
    prevent_initial_call=True,
)
def sync_preset(preset):
    if not preset or preset == "custom":
        return (no_update,) * 3
    sv = preset_to_slider_val(preset, MAX_IDX)
    s, e = preset_to_exact_dates(preset)
    return sv, s, e

# B) Slider → DatePicker + Label (clientside)
clientside_callback(
    ClientsideFunction(namespace="machinesDateSlider", function_name="syncSlider"),
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
def sync_picker_to_slider(start, end, current_slider):
    if not start or not end:
        return no_update
    s = pd.Timestamp(start)
    e = pd.Timestamp(end)
    new_val = [month_idx(s.year, s.month), month_idx(e.year, e.month)]
    if new_val == current_slider:
        return no_update
    return new_val

# D) Slider → auto-clear preset to "custom"
@callback(
    Output(f"{PAGE_ID}-filter-date-preset", "value", allow_duplicate=True),
    Input(f"{PAGE_ID}-date-slider", "value"),
    State(f"{PAGE_ID}-filter-date-preset", "value"),
    prevent_initial_call=True,
)
def maybe_clear_preset(slider_val, current_preset):
    if not current_preset or current_preset == "custom":
        return no_update
    expected = preset_to_slider_val(current_preset, MAX_IDX)
    if slider_val == expected:
        return no_update
    return "custom"


# ---------------------------------------------------------------------------
# Drill-down click handlers
# ---------------------------------------------------------------------------

@callback(
    Output(f"{PAGE_ID}-store-drill", "data"),
    Input(f"{PAGE_ID}-store-year-click", "data"),
    Input(f"{PAGE_ID}-store-day-click", "data"),
    Input(f"{PAGE_ID}-timeline-prev", "n_clicks"),
    Input(f"{PAGE_ID}-timeline-next", "n_clicks"),
    State(f"{PAGE_ID}-store-drill", "data"),
    State(f"{PAGE_ID}-store-gaps-agg", "data"),
    prevent_initial_call=True,
)
def handle_drill_clicks(year_click, day_click, prev_click, next_click, drill, agg):
    ctx = dash.callback_context
    if not ctx.triggered:
        return no_update

    trigger = ctx.triggered[0]["prop_id"].split(".")[0]

    if trigger == f"{PAGE_ID}-store-year-click" and year_click:
        return {"level": 2, "year": int(year_click), "month": None, "day": None}

    elif trigger == f"{PAGE_ID}-store-day-click" and day_click:
        dt = pd.Timestamp(day_click)
        return {"level": 3, "year": dt.year, "month": dt.month, "day": dt.day}

    elif trigger == f"{PAGE_ID}-timeline-prev" and drill and drill.get("level") == 3:
        current = pd.Timestamp(drill["year"], drill["month"], drill["day"])
        prev_day = current - pd.Timedelta(days=1)
        # Skip weekends
        while prev_day.dayofweek >= 5:
            prev_day -= pd.Timedelta(days=1)
        return {"level": 3, "year": prev_day.year, "month": prev_day.month, "day": prev_day.day}

    elif trigger == f"{PAGE_ID}-timeline-next" and drill and drill.get("level") == 3:
        current = pd.Timestamp(drill["year"], drill["month"], drill["day"])
        next_day = current + pd.Timedelta(days=1)
        while next_day.dayofweek >= 5:
            next_day += pd.Timedelta(days=1)
        return {"level": 3, "year": next_day.year, "month": next_day.month, "day": next_day.day}

    return no_update


# Breadcrumb navigation is handled clientside via set_props in toggleDrillLevel


# ---------------------------------------------------------------------------
# Drill level visibility + breadcrumb (clientside)
# ---------------------------------------------------------------------------

clientside_callback(
    ClientsideFunction("machinesDowntime", "toggleDrillLevel"),
    Output(f"{PAGE_ID}-level1-container", "style"),
    Output(f"{PAGE_ID}-level2-container", "style"),
    Output(f"{PAGE_ID}-level3-container", "style"),
    Output(f"{PAGE_ID}-breadcrumb", "children"),
    Output(f"{PAGE_ID}-timeline-date-label", "children"),
    Input(f"{PAGE_ID}-store-drill", "data"),
)


# ---------------------------------------------------------------------------
# Year cards renderer (clientside)
# ---------------------------------------------------------------------------

clientside_callback(
    ClientsideFunction("machinesDowntime", "renderYearCards"),
    Output(f"{PAGE_ID}-year-cards-container", "children"),
    Input(f"{PAGE_ID}-store-gaps-agg", "data"),
)


# ---------------------------------------------------------------------------
# Month heatmap renderer (clientside)
# ---------------------------------------------------------------------------

clientside_callback(
    ClientsideFunction("machinesDowntime", "renderMonthHeatmap"),
    Output(f"{PAGE_ID}-month-heatmap-container", "children"),
    Input(f"{PAGE_ID}-store-gaps-daily", "data"),
    Input(f"{PAGE_ID}-store-drill", "data"),
)


# ---------------------------------------------------------------------------
# Lazy-load daily summary on drill to Level 2
# ---------------------------------------------------------------------------

# Clear daily store immediately when drill changes (shows skeleton)
clientside_callback(
    """function(drill) {
        if (!drill || drill.level !== 2) return window.dash_clientside.no_update;
        return null;
    }""",
    Output(f"{PAGE_ID}-store-gaps-daily", "data"),
    Input(f"{PAGE_ID}-store-drill", "data"),
    prevent_initial_call=True,
)


@callback(
    Output(f"{PAGE_ID}-store-gaps-daily", "data", allow_duplicate=True),
    Input(f"{PAGE_ID}-store-drill", "data"),
    Input(f"{PAGE_ID}-filter-machine", "value"),
    Input(f"{PAGE_ID}-store-filter-rules", "data"),
    prevent_initial_call=True,
)
def load_daily_on_drill(drill, machines, filter_rules):
    if not drill or drill.get("level") != 2:
        return no_update
    df_all = _get_transformed_gaps()
    df_filtered = _filter_gaps(df_all, machines, filter_rules, slider_val=None)
    return _build_daily_summary(df_filtered)


# ---------------------------------------------------------------------------
# Level 3 timeline data callback
# ---------------------------------------------------------------------------

@callback(
    Output(f"{PAGE_ID}-store-timeline", "data"),
    Input(f"{PAGE_ID}-store-drill", "data"),
    Input(f"{PAGE_ID}-filter-machine", "value"),
    Input(f"{PAGE_ID}-store-filter-rules", "data"),
    prevent_initial_call=True,
)
def load_timeline_data(drill, machines, filter_rules):
    if not drill or drill.get("level") != 3:
        return no_update

    year, month, day = drill["year"], drill["month"], drill["day"]
    if not all([year, month, day]):
        return no_update

    target_date = pd.Timestamp(year, month, day)

    # Load ALL gaps for this day — we show all gaps in the timeline,
    # with matched (filtered) gaps in red and unmatched in faded gray.
    from data.loader import load_downtime_fields_for_date
    gaps = _apply_lifespan_filter(_get_transformed_gaps().copy())
    day_gaps_all = gaps[gaps["DowntimeDate"].dt.normalize() == target_date]
    if machines:
        day_gaps_all = day_gaps_all[day_gaps_all["Machine"].isin(machines)]
    # Determine which gaps match the filter rules
    if filter_rules and filter_rules.get("groups"):
        filter_mask = _evaluate_filter_rules(day_gaps_all, filter_rules)
    else:
        filter_mask = pd.Series(True, index=day_gaps_all.index)
    day_gaps_all = day_gaps_all.copy()
    day_gaps_all["_matched"] = filter_mask
    gap_rows = day_gaps_all

    # Load fields for this day
    fields = load_downtime_fields_for_date(target_date)
    if machines and not fields.empty:
        fields = fields[fields["Machine"].isin(machines)]

    # Serialize gaps — aggregate rows that share the same gap window
    # (multiple rows per gap = one per affected patient)
    gap_list = []
    if not gap_rows.empty:
        gr = gap_rows.copy()
        gr["_start_str"] = gr["GapStartTime"].apply(lambda v: str(v)[:8] if pd.notna(v) else "")
        gr["_end_str"] = gr["GapEndTime"].apply(lambda v: str(v)[:8] if pd.notna(v) else "")
        group_cols = ["Machine", "RowType", "_start_str", "_end_str"]
        for (machine, row_type, start_s, end_s), grp in gr.groupby(group_cols, sort=False):
            is_fullday = row_type == "FullDay"
            first = grp.iloc[0]
            # CancelledInGap is a per-gap value duplicated across patient rows — take max, not sum
            cancelled = int(grp["CancelledInGap"].max()) if grp["CancelledInGap"].notna().any() else 0
            # Collect unique non-empty patient outcomes
            outcomes = grp["PatientOutcome"].dropna()
            outcomes = outcomes[outcomes != ""]
            outcome_counts = outcomes.value_counts().to_dict() if not outcomes.empty else {}
            # Collect unique downtime note match reasons
            notes = grp["DowntimeNoteMatch"].dropna()
            notes = notes[notes.astype(str).str.strip() != ""]
            note_reasons = sorted(notes.unique().tolist()) if not notes.empty else []
            # A gap is "matched" if any row in the group matched the filter
            matched = bool(grp["_matched"].any())
            gap_list.append({
                "machine": machine,
                "start": "" if is_fullday else start_s,
                "end": "" if is_fullday else end_s,
                "minutes": int(first["GapMinutes"]) if pd.notna(first.get("GapMinutes")) else (600 if is_fullday else 0),
                "fullDay": is_fullday,
                "confidence": first.get("LocalConfidence") or first.get("DowntimeConfidence", "Low"),
                "matched": matched,
                "cancelled": cancelled,
                "errors": int(first["MachineErrorsNearGap"]) if pd.notna(first.get("MachineErrorsNearGap")) else 0,
                "prevPatient": str(first.get("PrevPatientName", "")) if pd.notna(first.get("PrevPatientName")) else "",
                "nextPatient": str(first.get("NextPatientName", "")) if pd.notna(first.get("NextPatientName")) else "",
                "reroute": str(first["RerouteMachine"]) if pd.notna(first.get("RerouteMachine")) else "",
                "outcomes": outcome_counts,
                "notes": note_reasons,
            })

    # Serialize fields — skip ImagePI records (duplicates of PortFilm at same time)
    if not fields.empty and "ImageType" in fields.columns:
        fields = fields[~(fields["ImageType"].fillna("").eq("ImagePI"))]
    field_list = []
    for _, r in fields.iterrows():
        field_list.append({
            "machine": r["Machine"],
            "start": str(r["StartTime"])[:8] if pd.notna(r.get("StartTime")) else "",
            "end": str(r["EndTime"])[:8] if pd.notna(r.get("EndTime")) else "",
            "status": r.get("TerminationStatus", "NORMAL"),
            "type": r.get("RecordType", "Treatment"),
            "patient": str(r.get("PatientName", "")) if pd.notna(r.get("PatientName")) else "",
            "fieldId": str(r.get("FieldId", "")) if pd.notna(r.get("FieldId")) else "",
            "category": r.get("FieldCategory", ""),
            "imageType": str(r.get("ImageType", "")) if pd.notna(r.get("ImageType")) else "",
        })

    active_machines = sorted(set(
        [g["machine"] for g in gap_list] +
        [f["machine"] for f in field_list]
    ))

    return {
        "date": target_date.strftime("%Y-%m-%d"),
        "gaps": gap_list,
        "fields": field_list,
        "machines": active_machines,
    }


# Show loading spinner immediately when data inputs change
clientside_callback(
    ClientsideFunction("machinesDowntime", "showTimelineLoading"),
    Output(f"{PAGE_ID}-timeline-svg-container", "className"),
    Input(f"{PAGE_ID}-store-drill", "data"),
    Input(f"{PAGE_ID}-filter-machine", "value"),
    Input(f"{PAGE_ID}-store-filter-rules", "data"),
    prevent_initial_call=True,
)

# Timeline strip renderer (clientside)
clientside_callback(
    ClientsideFunction("machinesDowntime", "renderTimelineStrip"),
    Output(f"{PAGE_ID}-timeline-svg-container", "children"),
    Input(f"{PAGE_ID}-store-timeline", "data"),
    Input(f"{PAGE_ID}-timeline-show-unmatched", "checked"),
)



# ---------------------------------------------------------------------------
# Trend chart (clientside)
# ---------------------------------------------------------------------------

clientside_callback(
    ClientsideFunction("machinesDowntime", "renderTrend"),
    Output(f"{PAGE_ID}-chart-trend", "figure"),
    Input(f"{PAGE_ID}-chart-trend-store", "data"),
    Input(f"{PAGE_ID}-chart-trend-settings-smooth", "value"),
    Input(f"{PAGE_ID}-chart-trend-settings-type", "value"),
    Input(f"{PAGE_ID}-trend-agg", "value"),
    Input(f"{PAGE_ID}-chart-trend-settings-stack", "value"),
    Input(f"{PAGE_ID}-trend-metric", "value"),
    State(f"{PAGE_ID}-chart-trend", "figure"),
)


# ---------------------------------------------------------------------------
# Patient Impact chart (clientside)
# ---------------------------------------------------------------------------

clientside_callback(
    ClientsideFunction("machinesDowntime", "renderPatientImpact"),
    Output(f"{PAGE_ID}-chart-patient-impact", "figure"),
    Input(f"{PAGE_ID}-chart-patient-impact-store", "data"),
    Input(f"{PAGE_ID}-chart-patient-impact-settings-smooth", "value"),
    Input(f"{PAGE_ID}-chart-patient-impact-settings-type", "value"),
    Input(f"{PAGE_ID}-patient-impact-agg", "value"),
    Input(f"{PAGE_ID}-patient-impact-mode", "value"),
    Input(f"{PAGE_ID}-chart-patient-impact-settings-stack", "value"),
    State(f"{PAGE_ID}-chart-patient-impact", "figure"),
)

# Hide stacked/grouped toggle when single-series (Course mode)
clientside_callback(
    """function(mode, chartType) {
        if (mode === "course" || chartType === "line") return {"display": "none"};
        return {"display": ""};
    }""",
    Output(f"{PAGE_ID}-chart-patient-impact-settings-stack-wrap", "style"),
    Input(f"{PAGE_ID}-patient-impact-mode", "value"),
    Input(f"{PAGE_ID}-chart-patient-impact-settings-type", "value"),
)


# ---------------------------------------------------------------------------
# KPI sparklines (clientside) — generic updateFromStore pattern
# ---------------------------------------------------------------------------

_MACHINES_SPARKLINE_IDS = [
    f"{PAGE_ID}-spark-hours",
    f"{PAGE_ID}-spark-availability",
    f"{PAGE_ID}-spark-events",
    f"{PAGE_ID}-spark-cancelled",
    f"{PAGE_ID}-spark-rerouted",
    f"{PAGE_ID}-spark-courses",
]

for _spark_id in _MACHINES_SPARKLINE_IDS:
    clientside_callback(
        ClientsideFunction(namespace="sparklines", function_name="updateFromStore"),
        Output(_spark_id, "figure"),
        Input(f"{PAGE_ID}-store-kpi-sparklines", "data"),
        Input(_spark_id, "id"),
    )


# ---------------------------------------------------------------------------
# Continuous Strip — server callback
# ---------------------------------------------------------------------------

@callback(
    Output(f"{PAGE_ID}-store-strip", "data"),
    Input(f"{PAGE_ID}-strip-range", "value"),
    Input(f"{PAGE_ID}-filter-machine", "value"),
    Input(f"{PAGE_ID}-store-filter-rules", "data"),
    Input(f"{PAGE_ID}-interval", "n_intervals"),
    Input(f"{PAGE_ID}-store-drill", "data"),
)
def update_strip_data(strip_range, machines, filter_rules, _n, drill):
    from data.loader import load_treatment_detail

    td = load_treatment_detail()
    if td.empty:
        return {"machines": [], "colors": {}, "data": {}}

    last_date = td["ScheduledDateTime"].dt.normalize().max()

    # When drilled into a year or deeper, override the strip range
    drill_level = drill.get("level", 1) if drill else 1
    if drill_level >= 2 and drill and drill.get("year"):
        year = drill["year"]
        start_date = pd.Timestamp(year, 1, 1)
        end_date = pd.Timestamp(year, 12, 31)
        # Clamp to available data
        end_date = min(end_date, last_date)
    else:
        range_map = {
            "3mo": timedelta(days=90),
            "6mo": timedelta(days=182),
            "1yr": timedelta(days=365),
            "3yr": timedelta(days=365 * 3),
        }
        start_date = last_date - range_map.get(strip_range, timedelta(days=365 * 25))
        end_date = last_date

    # Load and filter gaps for overlay
    gaps_df = _get_transformed_gaps()
    if not gaps_df.empty:
        gaps_df = _filter_gaps(gaps_df, machines, filter_rules, slider_val=None)
        gaps_df = gaps_df[(gaps_df["DowntimeDate"] >= start_date) & (gaps_df["DowntimeDate"] <= end_date)]

    return _build_strip_data(gaps_df, machines, start_date, end_date)


# Disable strip range selector when drilled into a year
clientside_callback(
    """function(drill) {
        if (drill && drill.level >= 2) return true;
        return false;
    }""",
    Output(f"{PAGE_ID}-strip-range", "disabled"),
    Input(f"{PAGE_ID}-store-drill", "data"),
)

# Continuous Strip — clientside renderer
clientside_callback(
    ClientsideFunction("machinesDowntime", "renderStrip"),
    Output(f"{PAGE_ID}-strip-svg-container", "children"),
    Input(f"{PAGE_ID}-store-strip", "data"),
)


# Strip click → drill to Level 3
@callback(
    Output(f"{PAGE_ID}-store-drill", "data", allow_duplicate=True),
    Input(f"{PAGE_ID}-strip-svg-container", "n_clicks"),
    State(f"{PAGE_ID}-store-strip", "data"),
    prevent_initial_call=True,
)
def handle_strip_click(_n, strip_data):
    # The actual click target detection happens via a JS click handler
    # that stores the clicked date in a data attribute — handled in renderStrip
    return no_update


# ---------------------------------------------------------------------------
# Table column filter → page data feedback
# ---------------------------------------------------------------------------

# Track which rows are visible after grid column filters
clientside_callback(
    """function(virtual, rowData, prev) {
        var nu = window.dash_clientside.no_update;
        var hidden = {"position": "absolute", "top": -4, "right": 8, "zIndex": 10, "display": "none", "cursor": "pointer"};
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
        var base = {"position": "absolute", "top": -4, "right": 8, "zIndex": 10, "cursor": "pointer"};
        return [idxs, base, {}];
    }""",
    Output(f"{PAGE_ID}-table-filter-rows", "data"),
    Output(f"{PAGE_ID}-grid-filter-badge", "style"),
    Output(f"{PAGE_ID}-table-clear-filters", "style"),
    Input(f"{PAGE_ID}-detail-table", "virtualRowData"),
    State(f"{PAGE_ID}-detail-table", "rowData"),
    State(f"{PAGE_ID}-table-filter-rows", "data"),
    prevent_initial_call=True,
)

# Clear Filters button → reset grid filterModel
clientside_callback(
    """function(n) {
        if (!n) return window.dash_clientside.no_update;
        return {};
    }""",
    Output(f"{PAGE_ID}-detail-table", "filterModel"),
    Input(f"{PAGE_ID}-table-clear-filters", "n_clicks"),
    prevent_initial_call=True,
)

# Badge click → scroll to the detail table
clientside_callback(
    """function(n) {
        if (!n) return window.dash_clientside.no_update;
        var el = document.getElementById('""" + f"{PAGE_ID}-detail-table" + """');
        if (el) el.scrollIntoView({behavior: 'smooth', block: 'start'});
        return window.dash_clientside.no_update;
    }""",
    Output(f"{PAGE_ID}-grid-filter-badge", "n_clicks"),
    Input(f"{PAGE_ID}-grid-filter-badge", "n_clicks"),
    prevent_initial_call=True,
)
