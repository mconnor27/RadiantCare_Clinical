"""Workflow page — Flow-Gantt pipeline, stage duration violins, pipeline trend."""

import dash
import dash_mantine_components as dmc
from dash import callback, Input, Output, State, dcc, html, clientside_callback, ClientsideFunction
from dash_iconify import DashIconify
import dash_ag_grid as dag
import pandas as pd
import numpy as np
from datetime import timedelta

from config.settings import CHART_COLORWAY, DEFAULT_GRAPH_CONFIG, DEFAULT_LAYOUT, FONT_FAMILY, PRIMARY, PHYSICIANS
from utils.diagnosis_categories import build_code_to_category, get_categories_for_codes
from components.filter_bar import department_chips
from components.chart_card import register_chart_callbacks
from components.chart_settings import chart_settings_popover
from components.detail_table import detail_table

dash.register_page(__name__, path="/workflow", name="Workflow", order=2)

# Stage definitions (canonical order, excluding ContourReview by default)
STAGES = ["Exam", "Simulation", "Draw", "Isodose", "ReviewPlan", "Treatment"]
STAGE_LABELS = {
    "Exam": "Consult",
    "Simulation": "Simulation",
    "Draw": "Contour",
    "Isodose": "Plan",
    "ReviewPlan": "Review",
    "Treatment": "Treatment",
}
INTER_STAGE_LABELS = [
    "Consult→Sim", "Sim→Contour", "Contour→Plan", "Plan→Review", "Review→Tx",
]

# Outlier-cap defaults (max days per inter-stage gap)
OUTLIER_DEFAULTS = [21, 8, 8, 5, 8]
OUTLIER_SLIDER_MAX = 120


# ---------------------------------------------------------------------------
# Date Slider Helpers (shared via utils.date_slider)
# ---------------------------------------------------------------------------

from utils.date_slider import (
    BASE_YEAR as _BASE_YEAR,
    month_idx as _month_idx,
    idx_to_date as _idx_to_date,
    MAX_IDX as _MAX_IDX,
    DEFAULT_SLIDER as _DEFAULT_SLIDER,
    SLIDER_MARKS as _SLIDER_MARKS,
    preset_to_slider_val as _preset_to_slider_val,
)

_DEFAULT_DATE_PRESET = "ytd" if pd.Timestamp.now().month > 1 else "3mo"

# ---------------------------------------------------------------------------
# Business-Day Helpers
# ---------------------------------------------------------------------------

_CALL_STATUSES = frozenset({"ON CALL", "WEEKEND CALL"})

from utils.holidays import get_holidays as _get_holidays


_BH_START = 8   # business hours start (8 AM)
_BH_END = 17    # business hours end (5 PM)
_BH_PER_DAY = _BH_END - _BH_START  # 9 hours per business day


def _business_days_between(start_dates, end_dates):
    """Vectorised business-hour duration between two Series of timestamps.

    Counts only hours within 8 AM – 5 PM on business days (excludes
    weekends and holidays).  Returns a float Series expressed in
    business days where 1.0 = 9 business hours.
    """
    holidays = _get_holidays()

    start = pd.Series(start_dates, copy=False)
    end = pd.Series(end_dates, copy=False)
    orig_index = start.index

    if holidays:
        hol_arr = np.array(sorted(holidays), dtype="datetime64[D]")
    else:
        hol_arr = np.array([], dtype="datetime64[D]")

    start_ts = pd.Series(start.values)
    end_ts = pd.Series(end.values)

    valid = pd.notna(start_ts) & pd.notna(end_ts)
    result = pd.Series(np.nan, index=orig_index, dtype=float)

    if valid.any():
        s = start_ts[valid].reset_index(drop=True)
        e = end_ts[valid].reset_index(drop=True)

        s_date = s.dt.normalize()
        e_date = e.dt.normalize()
        same_day = (s_date == e_date).values

        sd_arr = s_date.values.astype("datetime64[D]")
        ed_arr = e_date.values.astype("datetime64[D]")
        s_is_bd = np.is_busday(sd_arr, holidays=hol_arr)
        e_is_bd = np.is_busday(ed_arr, holidays=hol_arr)

        # Clamp start/end times to business hours window
        s_hour = s.dt.hour + s.dt.minute / 60 + s.dt.second / 3600
        e_hour = e.dt.hour + e.dt.minute / 60 + e.dt.second / 3600
        s_clamped = np.clip(s_hour.values, _BH_START, _BH_END)
        e_clamped = np.clip(e_hour.values, _BH_START, _BH_END)

        # Same-day: hours between clamped start and end (if business day)
        same_hours = np.where(
            same_day & s_is_bd,
            np.maximum(e_clamped - s_clamped, 0.0),
            0.0,
        )

        # Different-day: partial start day + interior days + partial end day
        start_day_hours = np.where(s_is_bd, _BH_END - s_clamped, 0.0)
        end_day_hours = np.where(e_is_bd, e_clamped - _BH_START, 0.0)

        next_day = sd_arr + np.timedelta64(1, "D")
        interior = np.maximum(
            np.busday_count(next_day, ed_arr, holidays=hol_arr).astype(float), 0.0
        )
        diff_hours = start_day_hours + (interior * _BH_PER_DAY) + end_day_hours

        total_hours = np.where(same_day, same_hours, diff_hours)
        # Express as business days (9 hours = 1 day)
        combined = total_hours / _BH_PER_DAY

        result.iloc[valid.values] = combined

    return result


def _duration_days(start_series, end_series, use_business_days=False):
    """Compute duration in days between two datetime Series.

    When use_business_days is True, counts only business days (excludes
    weekends and holidays).  Otherwise uses calendar days.
    """
    if use_business_days:
        return _business_days_between(start_series, end_series)
    else:
        return (end_series - start_series).dt.total_seconds() / 86400


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------

# ID mapping: dataset A preserves legacy IDs, dataset B uses consistent prefix.
# The _id() helper resolves this.
_A_ID_MAP = {
    "filter-department": "workflow-filter-department",
    "filter-physician": "workflow-filter-physician",
    "filter-technique": "workflow-filter-technique",
    "filter-body-system": "workflow-filter-body-system",
    "filter-date-preset": "workflow-filter-date-preset",
    "filter-daterange": "workflow-filter-daterange",
    "loopback-switch": "wf-sankey-loopback-switch",
}


def _id(prefix, suffix):
    """Resolve a component ID given a dataset prefix and logical suffix."""
    if prefix == "wf":
        return _A_ID_MAP.get(suffix, f"wf-{suffix}")
    return f"{prefix}-{suffix}"


_DATASET_COLORS = {"A": "#2196F3", "B": "#FF9800"}


def _build_filter_bar(prefix, label=None):
    """Build the complete workflow filter bar for a dataset.

    prefix: "wf" for dataset A (preserves legacy IDs), "wf-b" for dataset B.
    label:  Optional badge label ("A" or "B").
    """
    badge_color = _DATASET_COLORS.get(label, "#6B7280")
    bar_class = f"wf-filter-bar-{label.lower()}" if label else ""

    badge = (
        html.Span(
            label,
            className=f"wf-dataset-badge wf-dataset-badge-{label.lower()}",
        )
        if label
        else None
    )

    return dmc.Paper(
        children=[
            # Row 1: data filters
            dmc.Group(
                children=[
                    *([] if badge is None else [badge]),
                    department_chips("workflow" if prefix == "wf" else prefix),
                    # Physician
                    html.Div(
                        children=[
                            html.Div(
                                children=[
                                    dmc.Button(
                                        "Physician",
                                        id=_id(prefix, "physician-trigger"),
                                        variant="default",
                                        size="sm",
                                        rightSection=DashIconify(icon="mdi:chevron-down", width=14),
                                    ),
                                    dmc.ActionIcon(
                                        DashIconify(icon="mdi:close-circle", width=18),
                                        id=_id(prefix, "physician-clear"),
                                        variant="subtle",
                                        color="gray",
                                        size="sm",
                                        className="wf-filter-clear-btn",
                                    ),
                                ],
                                style={"position": "relative", "display": "inline-block"},
                            ),
                            dmc.Paper(
                                id=_id(prefix, "physician-panel"),
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
                                        id=_id(prefix, "filter-physician"),
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
                    # Technique
                    html.Div(
                        children=[
                            html.Div(
                                children=[
                                    dmc.Button(
                                        "Technique",
                                        id=_id(prefix, "technique-trigger"),
                                        variant="default",
                                        size="sm",
                                        rightSection=DashIconify(icon="mdi:chevron-down", width=14),
                                    ),
                                    dmc.ActionIcon(
                                        DashIconify(icon="mdi:close-circle", width=18),
                                        id=_id(prefix, "technique-clear"),
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
                                        dmc.Chip(t, value=t, size="xs", variant="filled")
                                        for t in ["Electron", "3D", "IMRT", "VMAT", "SBRT", "SRS"]
                                    ],
                                    id=_id(prefix, "filter-technique"),
                                    multiple=True,
                                    value=[],
                                ),
                                id=_id(prefix, "technique-panel"),
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
                    # Body System
                    html.Div(
                        children=[
                            html.Div(
                                children=[
                                    dmc.Button(
                                        "Body System",
                                        id=_id(prefix, "body-system-trigger"),
                                        variant="default",
                                        size="sm",
                                        rightSection=DashIconify(icon="mdi:chevron-down", width=14),
                                    ),
                                    dmc.ActionIcon(
                                        DashIconify(icon="mdi:close-circle", width=18),
                                        id=_id(prefix, "body-system-clear"),
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
                                        for bs in [
                                            "Breast", "Central Nervous System",
                                            "Digestive System", "Endocrine",
                                            "Genitourinary", "Gynecological",
                                            "Head & Neck", "Hematology", "Lymphomas",
                                            "Misc.", "Musculoskeletal", "Opthalmic",
                                            "Skin", "Thoracic",
                                        ]
                                    ],
                                    id=_id(prefix, "filter-body-system"),
                                    multiple=True,
                                    value=[],
                                ),
                                id=_id(prefix, "body-system-panel"),
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
                    dmc.SegmentedControl(
                        id=_id(prefix, "agg-toggle"),
                        data=[
                            {"value": "median", "label": "Median"},
                            {"value": "mean", "label": "Mean"},
                        ],
                        value="median",
                        size="xs",
                    ),
                    dmc.Switch(
                        id=_id(prefix, "business-days-switch"),
                        label="Business Days",
                        size="xs",
                        checked=False,
                    ),
                    dmc.Switch(
                        id=_id(prefix, "loopback-switch"),
                        label="Loopbacks",
                        size="xs",
                        checked=False,
                    ),
                    *(
                        [
                            dmc.Switch(
                                id=_id(prefix, "inpatient-switch"),
                                label="Inpatient",
                                size="xs",
                                checked=False,
                            ),
                        ]
                        if prefix == "wf"
                        else [
                            dmc.Switch(
                                id=_id(prefix, "inpatient-switch"),
                                label="Inpatient",
                                size="xs",
                                checked=False,
                            ),
                        ]
                    ),
                    # Outlier Caps
                    html.Div(
                        children=[
                            dmc.Button(
                                "Outliers: Default",
                                id=_id(prefix, "outlier-trigger"),
                                variant="default",
                                size="sm",
                                rightSection=DashIconify(icon="mdi:chevron-down", width=14),
                            ),
                            dmc.Paper(
                                children=[
                                    dmc.Group(gap="xs", mb="sm", children=[
                                        dmc.Button(
                                            "None", id=_id(prefix, "outlier-preset-none"),
                                            size="compact-xs", variant="light",
                                        ),
                                        dmc.Button(
                                            "Default", id=_id(prefix, "outlier-preset-default"),
                                            size="compact-xs", variant="light",
                                            color="violet",
                                        ),
                                    ]),
                                    html.Div(
                                        id=_id(prefix, "outlier-sliders"),
                                        className="wf-outlier-sliders",
                                        children=[
                                            dmc.Box(
                                                children=[
                                                    dmc.Group(
                                                        justify="space-between",
                                                        children=[
                                                            dmc.Text(lbl, size="xs", c="#6B7280"),
                                                            dmc.Text(
                                                                f"{default}d",
                                                                id=_id(prefix, f"outlier-val-{i}"),
                                                                size="xs", fw=600, c="#7C2A83",
                                                            ),
                                                        ],
                                                    ),
                                                    dmc.Slider(
                                                        id=_id(prefix, f"outlier-cap-{i}"),
                                                        min=1,
                                                        max=OUTLIER_SLIDER_MAX,
                                                        step=1,
                                                        value=default,
                                                        size="xs",
                                                        color="violet",
                                                        showLabelOnHover=True,
                                                    ),
                                                ],
                                                mb="xs",
                                            )
                                            for i, (lbl, default) in enumerate([
                                                ("Consult \u2192 Sim", OUTLIER_DEFAULTS[0]),
                                                ("Sim \u2192 Contour", OUTLIER_DEFAULTS[1]),
                                                ("Contour \u2192 Plan", OUTLIER_DEFAULTS[2]),
                                                ("Plan \u2192 Review", OUTLIER_DEFAULTS[3]),
                                                ("Review \u2192 Tx", OUTLIER_DEFAULTS[4]),
                                            ])
                                        ],
                                    ),
                                ],
                                id=_id(prefix, "outlier-panel"),
                                p="sm",
                                shadow="md",
                                withBorder=True,
                                radius="md",
                                className="wf-chip-dropdown",
                                style={"display": "none", "minWidth": "260px"},
                            ),
                        ],
                        style={"position": "relative", "display": "inline-block"},
                    ),
                    *(
                        [
                            dmc.Box(style={"flex": "1"}),  # spacer
                            dmc.Tooltip(
                                dmc.Button(
                                    "Compare",
                                    id="wf-compare-toggle",
                                    variant="light",
                                    color="gray",
                                    size="compact-sm",
                                    leftSection=DashIconify(icon="mdi:compare-horizontal", width=16),
                                ),
                                label="Compare two filter sets side by side",
                                withArrow=True,
                                position="bottom",
                            ),
                        ]
                        if prefix == "wf"
                        else []
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
                        id=_id(prefix, "filter-date-preset"),
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
                            id=_id(prefix, "filter-daterange"),
                            display_format="MMM D, YYYY",
                            start_date_placeholder_text="Start",
                            end_date_placeholder_text="End",
                            clearable=True,
                            number_of_months_shown=2,
                            minimum_nights=0,
                            start_date=_idx_to_date(_preset_to_slider_val(_DEFAULT_DATE_PRESET, _MAX_IDX)[0]).strftime("%Y-%m-%d"),
                            end_date=_idx_to_date(_preset_to_slider_val(_DEFAULT_DATE_PRESET, _MAX_IDX)[1], end_of_month=True).strftime("%Y-%m-%d"),
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
                            html.Div(id=_id(prefix, "date-range-label"), style={"display": "none"}),
                            dmc.RangeSlider(
                                id=_id(prefix, "date-slider"),
                                min=0,
                                max=_MAX_IDX,
                                step=1,
                                value=_preset_to_slider_val(_DEFAULT_DATE_PRESET, _MAX_IDX),
                                marks=_SLIDER_MARKS,
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
        className=bar_class,
    )


layout = dmc.Stack(
    gap=16,
    className="page-content",
    children=[
        # Sticky header with title and filter bars
        dmc.Box(
            className="page-sticky-header",
            children=[
                dmc.Title("Workflow", order=2, className="page-title", style={"margin": 0, "textAlign": "center"}),
                # Dataset A filter bar
                html.Div(
                    id="wf-a-filter-container",
                    children=[_build_filter_bar("wf", "A")],
                ),
                # Dataset B filter bar (hidden by default)
                html.Div(
                    id="wf-b-filter-container",
                    children=[_build_filter_bar("wf-b", "B")],
                    style={"display": "none"},
                ),
            ],
        ),

        # Flow-Gantt — full width
        dmc.Paper(
            children=[
                dmc.Group(
                    justify="space-between", mb="sm",
                    children=[
                        dmc.Text("Patient Treatment Pipeline", size="sm", fw=500, c="#6B7280"),
                        dmc.Group(gap="sm", children=[]),
                    ],
                ),
                dmc.Box(
                    pos="relative",
                    children=[
                        dmc.LoadingOverlay(
                            id="wf-sankey-loading",
                            visible=False,
                            loaderProps={"type": "dots", "color": "#7C2A83"},
                            overlayProps={"radius": "sm", "blur": 2},
                            zIndex=100,
                        ),
                        html.Div(
                            id="wf-flow-gantt",
                            style={
                                "width": "100%",
                                "aspectRatio": "2.45 / 1",
                                "minHeight": "340px",
                                "maxHeight": "480px",
                            },
                        ),
                    ],
                ),
            ],
            p="md", radius="md", shadow="xs", withBorder=True,
        ),

        # Distribution + Trend side by side (driven by flow selection)
        dmc.Grid(gutter="md", align="stretch", children=[
            dmc.GridCol(
                dmc.Paper(
                    children=[
                        dmc.Group(
                            justify="space-between", mb="sm",
                            children=[
                                dmc.Text("Stage Duration (days)", id="wf-dist-title", size="sm", fw=500, c="#6B7280"),
                                dmc.Group(gap="sm", children=[
                                    dmc.Tooltip(
                                        dmc.Switch(
                                            id="wf-dist-km-switch",
                                            label="KM Adjusted",
                                            size="xs",
                                            checked=False,
                                        ),
                                        label="Kaplan-Meier survival estimate: adjusts the median for patients still in progress (censored), reducing bias from incomplete recent data.",
                                        multiline=True,
                                        w=280,
                                        withArrow=True,
                                        position="bottom",
                                    ),
                                    dmc.SegmentedControl(
                                        id="wf-dist-type",
                                        data=[
                                            {"value": "histogram", "label": "Histogram"},
                                            {"value": "density", "label": "Density"},
                                        ],
                                        value="histogram",
                                        size="xs",
                                    ),
                                ]),
                            ],
                        ),
                        dmc.Box(
                            pos="relative",
                            style={"flex": "1 1 auto", "minHeight": "360px"},
                            children=[
                                dmc.LoadingOverlay(
                                    id="wf-dist-loading",
                                    visible=False,
                                    loaderProps={"type": "dots", "color": "#7C2A83"},
                                    overlayProps={"radius": "sm", "blur": 2},
                            zIndex=100,
                                ),
                                dcc.Graph(id="wf-chart-dist", config={**DEFAULT_GRAPH_CONFIG, "responsive": True}, style={"height": "100%"}),
                            ],
                        ),
                    ],
                    p="md", radius="md", shadow="xs", withBorder=True, h="100%",
                    style={"display": "flex", "flexDirection": "column"},
                ),
                span={"base": 12, "md": 6},
            ),
            dmc.GridCol(
                dmc.Paper(
                    children=[
                        dmc.Group(
                            justify="space-between", mb="sm",
                            children=[
                                dmc.Text("Pipeline Trend (monthly median)", id="wf-trend-title", size="sm", fw=500, c="#6B7280"),
                                dmc.Group(gap="sm", children=[
                                    dmc.Tooltip(
                                        dmc.Switch(
                                            id="wf-trend-km-switch",
                                            label="KM Adjusted",
                                            size="xs",
                                            checked=False,
                                        ),
                                        label="Kaplan-Meier survival estimate: corrects median/mean for patients still in progress (censored), reducing bias from incomplete recent data.",
                                        multiline=True,
                                        w=280,
                                        withArrow=True,
                                        position="bottom",
                                    ),
                                    dmc.SegmentedControl(
                                        id="wf-trend-agg",
                                        data=[
                                            {"value": "D", "label": "Daily"},
                                            {"value": "W", "label": "Weekly"},
                                            {"value": "M", "label": "Monthly"},
                                        ],
                                        value="W",
                                        size="xs",
                                    ),
                                    chart_settings_popover(
                                        "wf-trend",
                                        chart_types=[
                                            {"value": "line", "label": "Line"},
                                            {"value": "area", "label": "Area"},
                                            {"value": "bar", "label": "Bar"},
                                        ],
                                        show_smooth=True,
                                        smooth_max=50,
                                        smooth_default=3,
                                    ),
                                ]),
                            ],
                        ),
                        dmc.Group(
                            justify="flex-end",
                            style={"position": "relative", "zIndex": 10},
                            children=[
                                dmc.Tooltip(
                                    html.Div(
                                        id="wf-trend-maturity-legend",
                                        children=[
                                            html.Span("\u25cf", style={"fontWeight": "bold"}),
                                            " \u226550% complete   ",
                                            html.Span("\u25cb", style={"fontWeight": "bold"}),
                                            " <50% complete",
                                        ],
                                        style={
                                            "fontSize": "11px",
                                            "color": "#6B7280",
                                            "display": "none",
                                            "cursor": "help",
                                        },
                                    ),
                                    label="Open circles mark periods where fewer than half of patients have completed this step. The value may shift as more patients finish treatment.",
                                    multiline=True,
                                    w=280,
                                    withArrow=True,
                                    position="bottom-end",
                                ),
                            ],
                        ),
                        dmc.Box(
                            pos="relative",
                            style={"flex": "1 1 auto", "minHeight": "360px"},
                            children=[
                                dmc.LoadingOverlay(
                                    id="wf-trend-loading",
                                    visible=False,
                                    loaderProps={"type": "dots", "color": "#7C2A83"},
                                    overlayProps={"radius": "sm", "blur": 2},
                            zIndex=100,
                                ),
                                dcc.Graph(id="wf-chart-trend", config={**DEFAULT_GRAPH_CONFIG, "responsive": True}, style={"height": "100%"}),
                            ],
                        ),
                    ],
                    p="md", radius="md", shadow="xs", withBorder=True, h="100%",
                    style={"display": "flex", "flexDirection": "column"},
                ),
                span={"base": 12, "md": 6},
            ),
        ]),

        # Detail table (hidden in compare mode)
        html.Div(
            id="wf-table-container",
            children=[
                detail_table("wf-detail-grid", title="Patient Pipeline Detail", export_id="wf-table-export"),
            ],
        ),

        dcc.Interval(id="wf-interval", interval=300_000, n_intervals=0),

        # Stores for clientside rendering — Dataset A
        dcc.Store(id="wf-store-sankey"),
        dcc.Store(id="wf-flow-gantt-trigger"),
        dcc.Store(id="wf-store-trend"),
        dcc.Store(id="wf-store-flow-details"),
        dcc.Store(id="wf-store-selected-flow"),
        dcc.Store(id="wf-outlier-enabled", data=True),
        dcc.Store(id="wf-filter-options"),
        html.Div(id="wf-filter-options-applier", style={"display": "none"}),

        # Compare mode
        dcc.Store(id="wf-compare-mode", data=False),

        # Stores for clientside rendering — Dataset B
        dcc.Store(id="wf-b-store-sankey"),
        dcc.Store(id="wf-b-store-flow-details"),
        dcc.Store(id="wf-b-store-trend"),
        dcc.Store(id="wf-b-store-selected-flow"),
        dcc.Store(id="wf-b-outlier-enabled", data=True),
        dcc.Store(id="wf-b-filter-options"),
        html.Div(id="wf-b-filter-options-applier", style={"display": "none"}),
    ],
)


# ---------------------------------------------------------------------------
# Data Processing Helpers
# ---------------------------------------------------------------------------

def _get_date_range(slider_val, daterange, first_date, last_date):
    """Calculate start/end based on slider or explicit daterange override."""
    if daterange and len(daterange) == 2 and daterange[0] and daterange[1]:
        return pd.Timestamp(daterange[0]), pd.Timestamp(daterange[1])
    if slider_val and len(slider_val) == 2:
        start = _idx_to_date(slider_val[0])
        end = _idx_to_date(slider_val[1], end_of_month=True)
        return max(start, first_date), min(end, last_date)
    return first_date, last_date


def _forward_fill_exam_info(wf):
    """Propagate Department, Physician, Diagnosis from Exam rows to all stages."""
    fill_cols = ["Department", "TreatingPhysician", "AppointmentPhysician",
                 "DiagnosisDescriptions", "ModalityType"]
    existing = [c for c in fill_cols if c in wf.columns]
    if not existing:
        return wf

    # Extract info from Exam rows
    exam_rows = wf[wf["StageName"] == "Exam"].copy()
    if exam_rows.empty:
        return wf

    # Prefer DimCourseID for grouping; fall back to PatientId
    if "DimCourseID" in wf.columns and exam_rows["DimCourseID"].notna().any():
        # Build lookup from Exam rows keyed on DimCourseID
        exam_info = (exam_rows[exam_rows["DimCourseID"].notna()]
                     .sort_values("StageDateTime")
                     .drop_duplicates(subset=["DimCourseID"], keep="first")
                     [["DimCourseID"] + existing])
        wf = wf.merge(exam_info, on="DimCourseID", how="left", suffixes=("", "_exam"))
        for col in existing:
            ecol = f"{col}_exam"
            if ecol in wf.columns:
                wf[col] = wf[col].fillna(wf[ecol])
                wf.drop(columns=[ecol], inplace=True)

    # Fill remaining nulls via PatientId fallback
    still_null = wf[existing].isna().any(axis=1)
    if still_null.any() and "PatientId" in wf.columns:
        patient_info = (exam_rows
                        .sort_values("StageDateTime")
                        .drop_duplicates(subset=["PatientId"], keep="last")
                        [["PatientId"] + existing])
        wf = wf.merge(patient_info, on="PatientId", how="left", suffixes=("", "_pat"))
        for col in existing:
            pcol = f"{col}_pat"
            if pcol in wf.columns:
                wf[col] = wf[col].fillna(wf[pcol])
                wf.drop(columns=[pcol], inplace=True)

    return wf


def _pivot_to_courses(wf):
    """Convert tall stage-based data to one row per workflow chain.

    Groups by UniqueRowID (the workflow chain key — shared across all stages
    of one exam-to-treatment pipeline). For each chain, takes the first
    occurrence of each stage to build the primary flow path.

    Returns a DataFrame with columns: UniqueRowID, PatientId, PatientName,
    Department, TreatingPhysician, DiagnosisDescriptions, ModalityType,
    Exam, Simulation, Draw, Isodose, ReviewPlan, Treatment
    """
    if "UniqueRowID" not in wf.columns:
        return pd.DataFrame()

    # Filter out cancelled/deleted stages; keep first occurrence per stage
    active = wf[~wf["StageStatus"].isin(["Cancelled", "Deleted"])].copy()
    if "StageOccurrence" in active.columns:
        active = active[active["StageOccurrence"].fillna(1) == 1]

    # Only keep our 6 target stages
    active = active[active["StageName"].isin(STAGES)]
    if active.empty:
        return pd.DataFrame()

    # For each chain/stage, keep the earliest StageDateTime
    active = active.sort_values("StageDateTime")
    deduped = active.drop_duplicates(subset=["UniqueRowID", "StageName"], keep="first")

    # Pivot: one row per chain, columns = stage names, values = StageDateTime
    pivot = deduped.pivot_table(
        index="UniqueRowID",
        columns="StageName",
        values="StageDateTime",
        aggfunc="first",
    )

    # Attach patient/exam info from the Exam row (or first available row)
    info_cols = ["UniqueRowID", "PatientId", "PatientName", "Department",
                 "TreatingPhysician", "DiagnosisDescriptions", "ModalityType",
                 "StageActivityName"]
    info_cols = [c for c in info_cols if c in deduped.columns]
    info = deduped.drop_duplicates(subset=["UniqueRowID"], keep="first")[info_cols]
    info = info.set_index("UniqueRowID")

    result = pivot.join(info, how="left")
    return result.reset_index()


def _enrich_pivot_with_baselines(pivot, wf_full):
    """Add {stage}_baseline columns to pivot from wf_full BaselineDateTime.

    ARIA pre-computes BaselineDateTime as the prior-step completion time for
    each stage.  For stages with a hidden intermediate step (e.g. ContourReview
    between Draw and Isodose), the baseline correctly reflects when the actual
    predecessor finished — not the displayed predecessor.  Using these baselines
    ensures 'actual' durations are measured over the same window as 'allotted'.
    """
    if "BaselineDateTime" not in wf_full.columns or "UniqueRowID" not in pivot.columns:
        return pivot
    result = pivot.copy()
    active = wf_full[~wf_full["StageStatus"].isin(["Cancelled", "Deleted"])]
    for stage in STAGES:
        col = f"{stage}_baseline"
        rows = active[
            (active["StageName"] == stage)
            & active["BaselineDateTime"].notna()
        ][["UniqueRowID", "BaselineDateTime"]].drop_duplicates("UniqueRowID", keep="first")
        rows = rows.rename(columns={"BaselineDateTime": col})
        result = result.merge(rows, on="UniqueRowID", how="left")
    return result


def _compute_flow_data(pivot, wf_full, use_business_days=False, agg_func="median"):
    """Compute Flow-Gantt data structure for clientside rendering."""
    stages = [s for s in STAGES if s in pivot.columns]
    if len(stages) < 2:
        return None

    total = len(pivot)
    if total == 0:
        return None

    _cancelled_statuses = frozenset(
        ["Cancelled", "Cancelled - Patient No-Show", "Deleted"]
    )

    stage_counts = []
    flow_values = []
    dropoffs = []
    pending_counts = []
    cancelled_counts = []
    median_days = []
    mean_days = []
    allotted_days = []
    on_time_pcts = []

    for i, stage in enumerate(stages):
        count = int(pivot[stage].notna().sum())
        stage_counts.append(count)

        if i < len(stages) - 1:
            next_stage = stages[i + 1]
            reached_current = pivot[stage].notna()
            reached_next = pivot[next_stage].notna()
            progressed = int((reached_current & reached_next).sum())
            dropped = int((reached_current & ~reached_next).sum())
            flow_values.append(progressed)
            dropoffs.append(dropped)

            # Split dropoffs: "pending" = next stage exists as Open/Scheduled/InProgress
            # "cancelled/unscheduled" = everything else (cancelled, or no further activity)
            stopped_mask = reached_current & ~reached_next
            if ("UniqueRowID" in pivot.columns
                    and "StageStatus" in wf_full.columns
                    and stopped_mask.any()):
                stopped_ids = set(pivot.loc[stopped_mask, "UniqueRowID"].dropna())
                chain_data = wf_full[wf_full["UniqueRowID"].isin(stopped_ids)]
                # Truly pending: chain has an Open/Scheduled/InProgress stage
                # for a LATER stage (beyond current)
                _active_statuses = frozenset(["Open", "Scheduled", "In Progress"])
                pending_ids = set(
                    chain_data[
                        chain_data["StageStatus"].isin(_active_statuses)
                    ]["UniqueRowID"].unique()
                )
                n_pending = len(stopped_ids & pending_ids)
                n_unscheduled = len(stopped_ids) - n_pending
            else:
                n_pending = 0
                n_unscheduled = dropped

            pending_counts.append(n_pending)
            cancelled_counts.append(n_unscheduled)

            # Median inter-stage duration (use BaselineDateTime when available)
            baseline_col = f"{next_stage}_baseline"
            both_mask = reached_current & reached_next
            if baseline_col in pivot.columns:
                days = _duration_days(
                    pivot.loc[both_mask, baseline_col].fillna(pivot.loc[both_mask, stage]),
                    pivot.loc[both_mask, next_stage],
                    use_business_days,
                )
            else:
                days = _duration_days(
                    pivot.loc[both_mask, stage],
                    pivot.loc[both_mask, next_stage],
                    use_business_days,
                )
            days = days[(days >= 0) & (days < 365)]
            median_days.append(round(float(days.median()), 1) if len(days) > 0 else 0)
            mean_days.append(round(float(days.mean()), 1) if len(days) > 0 else 0)

            # Median allotted time (StageDueDateTime - BaselineDateTime) for next stage
            if ("StageDueDateTime" in wf_full.columns
                    and "BaselineDateTime" in wf_full.columns):
                next_rows = wf_full[
                    (wf_full["StageName"] == next_stage)
                    & wf_full["StageDueDateTime"].notna()
                    & wf_full["BaselineDateTime"].notna()
                ]
                if not next_rows.empty:
                    allotted = _duration_days(
                        next_rows["BaselineDateTime"],
                        next_rows["StageDueDateTime"],
                        use_business_days,
                    )
                    allotted = allotted[(allotted >= 0) & (allotted < 365)]
                    allotted_median = (
                        round(float(allotted.median()), 1) if len(allotted) > 0 else None
                    )
                else:
                    allotted_median = None
            else:
                allotted_median = None
            allotted_days.append(allotted_median)

            # On-time %: did the patient complete before the due date?
            # This is always a calendar comparison (timestamp <= due),
            # independent of the business-day toggle.
            on_time_pct = None
            if "StageDueDateTime" in wf_full.columns:
                next_due = wf_full[
                    (wf_full["StageName"] == next_stage)
                    & wf_full["StageDueDateTime"].notna()
                ][["UniqueRowID", "StageDueDateTime"]].copy()
                if not next_due.empty:
                    next_due = next_due.drop_duplicates("UniqueRowID", keep="first")
                    if "UniqueRowID" in pivot.columns:
                        prog = pivot.loc[
                            reached_current & reached_next,
                            ["UniqueRowID", next_stage],
                        ].copy()
                        merged = prog.merge(
                            next_due[["UniqueRowID", "StageDueDateTime"]],
                            on="UniqueRowID", how="inner",
                        )
                        if len(merged) > 0:
                            n_on_time = int(
                                (merged[next_stage] <= merged["StageDueDateTime"]).sum()
                            )
                            on_time_pct = round(
                                n_on_time / len(merged) * 100, 0
                            )
            on_time_pcts.append(on_time_pct)

    # Compute x-positions: guarantee minimum spacing + proportional bonus
    display_days = mean_days if agg_func == "mean" else median_days
    n_gaps = len(display_days)
    min_gap = 0.07  # minimum spacing between consecutive stages
    total_min = min_gap * n_gaps
    remaining = max(1.0 - total_min, 0.0)
    total_duration = sum(display_days) if display_days else 1
    if total_duration <= 0:
        total_duration = 1

    x_positions = [0.0]
    cumulative = 0.0
    for d in display_days:
        bonus = (d / total_duration) * remaining
        cumulative += min_gap + bonus
        x_positions.append(min(cumulative, 1.0))
    x_positions[-1] = 1.0

    # Per-stage loopback totals (for hover tooltips)
    loopbacks = []
    if "StageOccurrence" in wf_full.columns:
        for stage in stages:
            lb = wf_full[(wf_full["StageName"] == stage) & (wf_full["StageOccurrence"] > 1)]
            loopbacks.append(int(len(lb)))
    else:
        loopbacks = [0] * len(stages)

    # Actual loopback source→target pairs from stage sequence data
    loopback_pairs = []
    if ("StageOccurrence" in wf_full.columns
            and "StageDateTime" in wf_full.columns):
        stage_to_idx = {s: i for i, s in enumerate(stages)}
        sorted_wf = wf_full.sort_values(["UniqueRowID", "StageDateTime"])
        prev_stages = sorted_wf.groupby("UniqueRowID")["StageName"].shift(1)
        mask = (
            (sorted_wf["StageOccurrence"] > 1)
            & sorted_wf["StageName"].isin(stages)
            & prev_stages.isin(stages)
            & (sorted_wf["StageName"] != prev_stages)
        )
        if mask.any():
            pairs = pd.DataFrame({
                "from_stage": prev_stages[mask],
                "to_stage": sorted_wf.loc[mask, "StageName"],
            })
            pair_counts = (pairs.groupby(["from_stage", "to_stage"])
                           .size().reset_index(name="count"))
            pair_counts = pair_counts.sort_values("count", ascending=False).head(10)
            for _, row in pair_counts.iterrows():
                fi = stage_to_idx.get(row["from_stage"])
                ti = stage_to_idx.get(row["to_stage"])
                if fi is not None and ti is not None and fi > ti:
                    loopback_pairs.append({
                        "fromIdx": int(fi),
                        "toIdx": int(ti),
                        "count": int(row["count"]),
                    })

    colors = [CHART_COLORWAY[i % len(CHART_COLORWAY)] for i in range(len(stages))]
    labels = [STAGE_LABELS.get(s, s) for s in stages]

    return {
        "stages": labels,
        "stageKeys": stages,
        "stageCounts": stage_counts,
        "flowValues": flow_values,
        "dropoffs": dropoffs,
        "pendingCounts": pending_counts,
        "cancelledCounts": cancelled_counts,
        "medianDays": median_days,
        "meanDays": mean_days,
        "aggFunc": agg_func,
        "allottedDays": allotted_days,
        "onTimePcts": on_time_pcts,
        "xPositions": x_positions,
        "colors": colors,
        "loopbacks": loopbacks,
        "loopbackPairs": loopback_pairs,
        "totalPatients": total,
        "height": 600,
    }


# ---------------------------------------------------------------------------
# Parameterized filter callback registration
# ---------------------------------------------------------------------------


def _register_filter_callbacks(prefix):
    """Register all filter-sync callbacks for a given dataset prefix.

    prefix: "wf" for dataset A (uses legacy IDs), "wf-b" for dataset B.
    """

    # A) Preset → Slider + DatePicker
    @callback(
        Output(_id(prefix, "date-slider"), "value"),
        Output(_id(prefix, "filter-daterange"), "start_date", allow_duplicate=True),
        Output(_id(prefix, "filter-daterange"), "end_date", allow_duplicate=True),
        Input(_id(prefix, "filter-date-preset"), "value"),
        prevent_initial_call=True,
    )
    def _sync_preset(preset):
        if not preset or preset == "custom":
            return (dash.no_update,) * 3
        sv = _preset_to_slider_val(preset, _MAX_IDX)
        s = _idx_to_date(sv[0]).strftime("%Y-%m-%d")
        e = _idx_to_date(sv[1], end_of_month=True).strftime("%Y-%m-%d")
        return sv, s, e

    # B) Slider → DatePicker + Label (clientside for speed)
    clientside_callback(
        ClientsideFunction(namespace="dateSlider", function_name="syncSlider"),
        Output(_id(prefix, "filter-daterange"), "start_date", allow_duplicate=True),
        Output(_id(prefix, "filter-daterange"), "end_date", allow_duplicate=True),
        Output(_id(prefix, "date-range-label"), "children"),
        Input(_id(prefix, "date-slider"), "value"),
        State(_id(prefix, "filter-daterange"), "start_date"),
        State(_id(prefix, "filter-daterange"), "end_date"),
        prevent_initial_call=True,
    )

    # C) DatePicker → Slider
    @callback(
        Output(_id(prefix, "date-slider"), "value", allow_duplicate=True),
        Input(_id(prefix, "filter-daterange"), "start_date"),
        Input(_id(prefix, "filter-daterange"), "end_date"),
        State(_id(prefix, "date-slider"), "value"),
        prevent_initial_call=True,
    )
    def _sync_picker_to_slider(start, end, current_slider):
        if not start or not end:
            return dash.no_update
        s = pd.Timestamp(start)
        e = pd.Timestamp(end)
        new_val = [_month_idx(s.year, s.month), _month_idx(e.year, e.month)]
        if new_val == current_slider:
            return dash.no_update
        return new_val

    # D) Slider → auto-set preset to "Custom" when it doesn't match
    @callback(
        Output(_id(prefix, "filter-date-preset"), "value", allow_duplicate=True),
        Input(_id(prefix, "date-slider"), "value"),
        State(_id(prefix, "filter-date-preset"), "value"),
        prevent_initial_call=True,
    )
    def _maybe_clear_preset(slider_val, current_preset):
        if not current_preset or current_preset == "custom":
            return dash.no_update
        expected = _preset_to_slider_val(current_preset, _MAX_IDX)
        if slider_val == expected:
            return dash.no_update
        return "custom"

    # --- Trigger labels ---
    clientside_callback(
        """function(val) {
            if (!val) return "Physician";
            return val.split(", ")[0];
        }""",
        Output(_id(prefix, "physician-trigger"), "children"),
        Input(_id(prefix, "filter-physician"), "value"),
    )
    clientside_callback(
        """function(vals) {
            if (!vals || vals.length === 0) return "Technique";
            if (vals.length === 1) return vals[0];
            return vals.length + " selected";
        }""",
        Output(_id(prefix, "technique-trigger"), "children"),
        Input(_id(prefix, "filter-technique"), "value"),
    )
    clientside_callback(
        """function(vals) {
            if (!vals || vals.length === 0) return "Body System";
            if (vals.length === 1) return vals[0];
            return vals.length + " selected";
        }""",
        Output(_id(prefix, "body-system-trigger"), "children"),
        Input(_id(prefix, "filter-body-system"), "value"),
    )

    # --- Clear-button visibility ---
    clientside_callback(
        """function(val) { return val ? {"display": "inline-flex"} : {"display": "none"}; }""",
        Output(_id(prefix, "physician-clear"), "style"),
        Input(_id(prefix, "filter-physician"), "value"),
    )
    clientside_callback(
        """function(vals) { return vals && vals.length > 0 ? {"display": "inline-flex"} : {"display": "none"}; }""",
        Output(_id(prefix, "technique-clear"), "style"),
        Input(_id(prefix, "filter-technique"), "value"),
    )
    clientside_callback(
        """function(vals) { return vals && vals.length > 0 ? {"display": "inline-flex"} : {"display": "none"}; }""",
        Output(_id(prefix, "body-system-clear"), "style"),
        Input(_id(prefix, "filter-body-system"), "value"),
    )

    # --- Clear-button actions ---
    clientside_callback(
        """function(n) { return null; }""",
        Output(_id(prefix, "filter-physician"), "value", allow_duplicate=True),
        Input(_id(prefix, "physician-clear"), "n_clicks"),
        prevent_initial_call=True,
    )
    clientside_callback(
        """function(n) { return []; }""",
        Output(_id(prefix, "filter-technique"), "value", allow_duplicate=True),
        Input(_id(prefix, "technique-clear"), "n_clicks"),
        prevent_initial_call=True,
    )
    clientside_callback(
        """function(n) { return []; }""",
        Output(_id(prefix, "filter-body-system"), "value", allow_duplicate=True),
        Input(_id(prefix, "body-system-clear"), "n_clicks"),
        prevent_initial_call=True,
    )

    # --- Outlier caps ---
    outlier_enabled_id = _id(prefix, "outlier-enabled") if prefix != "wf" else "wf-outlier-enabled"

    # "None" preset → disable outlier filtering
    clientside_callback(
        """function(n) { return false; }""",
        Output(outlier_enabled_id, "data", allow_duplicate=True),
        Input(_id(prefix, "outlier-preset-none"), "n_clicks"),
        prevent_initial_call=True,
    )

    # "Default" preset → enable + reset sliders to defaults
    clientside_callback(
        """function(n) { return [true, 21, 8, 8, 5, 8]; }""",
        Output(outlier_enabled_id, "data", allow_duplicate=True),
        Output(_id(prefix, "outlier-cap-0"), "value", allow_duplicate=True),
        Output(_id(prefix, "outlier-cap-1"), "value", allow_duplicate=True),
        Output(_id(prefix, "outlier-cap-2"), "value", allow_duplicate=True),
        Output(_id(prefix, "outlier-cap-3"), "value", allow_duplicate=True),
        Output(_id(prefix, "outlier-cap-4"), "value", allow_duplicate=True),
        Input(_id(prefix, "outlier-preset-default"), "n_clicks"),
        prevent_initial_call=True,
    )

    # Any slider change → auto-enable outlier filtering
    clientside_callback(
        """function() { return true; }""",
        Output(outlier_enabled_id, "data", allow_duplicate=True),
        Input(_id(prefix, "outlier-cap-0"), "value"),
        Input(_id(prefix, "outlier-cap-1"), "value"),
        Input(_id(prefix, "outlier-cap-2"), "value"),
        Input(_id(prefix, "outlier-cap-3"), "value"),
        Input(_id(prefix, "outlier-cap-4"), "value"),
        prevent_initial_call=True,
    )

    # Slider value labels
    for i in range(5):
        clientside_callback(
            """function(v) { return v + "d"; }""",
            Output(_id(prefix, f"outlier-val-{i}"), "children"),
            Input(_id(prefix, f"outlier-cap-{i}"), "value"),
        )

    # Trigger button summary label
    clientside_callback(
        """function(enabled, v0, v1, v2, v3, v4) {
            if (!enabled) return "Outliers: Off";
            var defaults = [21, 8, 8, 5, 8];
            var vals = [v0, v1, v2, v3, v4];
            var isDefault = true;
            for (var i = 0; i < 5; i++) {
                if (vals[i] !== defaults[i]) { isDefault = false; break; }
            }
            if (isDefault) return "Outliers: Default";
            return "Outliers: " + vals.join("/");
        }""",
        Output(_id(prefix, "outlier-trigger"), "children"),
        Input(outlier_enabled_id, "data"),
        Input(_id(prefix, "outlier-cap-0"), "value"),
        Input(_id(prefix, "outlier-cap-1"), "value"),
        Input(_id(prefix, "outlier-cap-2"), "value"),
        Input(_id(prefix, "outlier-cap-3"), "value"),
        Input(_id(prefix, "outlier-cap-4"), "value"),
    )

    # Dim sliders when outlier caps are disabled
    clientside_callback(
        """function(enabled) {
            return enabled ? "wf-outlier-sliders" : "wf-outlier-sliders is-disabled";
        }""",
        Output(_id(prefix, "outlier-sliders"), "className"),
        Input(outlier_enabled_id, "data"),
    )



# Register filter callbacks for both datasets
_register_filter_callbacks("wf")
_register_filter_callbacks("wf-b")

# ---------------------------------------------------------------------------
# Cross-filter: compute available options for each filter dimension
# ---------------------------------------------------------------------------

def _apply_dimension_filter(wf, departments, physician, techniques, body_systems,
                            courses_df, diag_lookup, skip=None):
    """Apply all dimension filters EXCEPT the one named by `skip`."""
    d = wf
    if skip != "department" and departments and "Department" in d.columns:
        d = d[d["Department"].isin(departments)]
    if skip != "physician" and physician and "TreatingPhysician" in d.columns and "UniqueRowID" in d.columns:
        ep = d[(d["StageName"] == "Exam") & (d["TreatingPhysician"] == physician)]["UniqueRowID"].unique()
        d = d[d["UniqueRowID"].isin(ep)]
    if skip != "technique" and techniques and "DimCourseID" in d.columns and courses_df is not None:
        tc = "TreatmentTechniques"
        if tc in courses_df.columns:
            tm = courses_df[["UniqueRowID", tc]].dropna(subset=[tc])
            ts = set(techniques)
            m = tm[tc].apply(lambda s: bool(ts & {t.strip() for t in str(s).split(",")}))
            d = d[d["DimCourseID"].isin(set(tm.loc[m, "UniqueRowID"]))]
    if skip != "body_system" and body_systems and "DiagnosisCodes" in d.columns and diag_lookup is not None:
        c2c = build_code_to_category(diag_lookup)
        if c2c:
            bs = set(body_systems)
            cd = (d[["UniqueRowID", "DiagnosisCodes"]]
                  .dropna(subset=["DiagnosisCodes"])
                  .drop_duplicates("UniqueRowID"))
            mm = cd["DiagnosisCodes"].apply(
                lambda s: bool(bs & get_categories_for_codes(s, c2c))
            )
            d = d[d["UniqueRowID"].isin(set(cd.loc[mm, "UniqueRowID"]))]
    return d


def _compute_available_options(wf_base, departments, physician, techniques, body_systems,
                               courses_df, diag_lookup):
    """Cross-filter: for each dimension, apply all OTHER filters and return available values."""
    # Department options
    wf_nd = _apply_dimension_filter(wf_base, departments, physician, techniques, body_systems,
                                    courses_df, diag_lookup, skip="department")
    dept_opts = sorted(wf_nd["Department"].dropna().unique().tolist()) if "Department" in wf_nd.columns else []

    # Physician options (from Exam rows only)
    wf_np = _apply_dimension_filter(wf_base, departments, physician, techniques, body_systems,
                                    courses_df, diag_lookup, skip="physician")
    if "StageName" in wf_np.columns:
        phys_src = wf_np[wf_np["StageName"] == "Exam"]
    else:
        phys_src = wf_np
    phys_opts = sorted(phys_src["TreatingPhysician"].dropna().unique().tolist()) if "TreatingPhysician" in phys_src.columns else []

    # Technique options
    tech_opts = []
    wf_nt = _apply_dimension_filter(wf_base, departments, physician, techniques, body_systems,
                                    courses_df, diag_lookup, skip="technique")
    if courses_df is not None and "DimCourseID" in wf_nt.columns:
        tc = "TreatmentTechniques"
        if tc in courses_df.columns:
            avail_cids = set(wf_nt["DimCourseID"].dropna())
            rel = courses_df[courses_df["UniqueRowID"].isin(avail_cids)]
            all_t = set()
            for val in rel[tc].dropna():
                all_t.update(t.strip() for t in str(val).split(","))
            tech_opts = sorted(all_t)

    # Body system options
    bs_opts = []
    wf_nb = _apply_dimension_filter(wf_base, departments, physician, techniques, body_systems,
                                    courses_df, diag_lookup, skip="body_system")
    if diag_lookup is not None and "DiagnosisCodes" in wf_nb.columns:
        c2c = build_code_to_category(diag_lookup)
        if c2c:
            cd = (wf_nb[["UniqueRowID", "DiagnosisCodes"]]
                  .dropna(subset=["DiagnosisCodes"])
                  .drop_duplicates("UniqueRowID"))
            all_bs = set()
            for val in cd["DiagnosisCodes"].dropna():
                all_bs.update(get_categories_for_codes(val, c2c))
            bs_opts = sorted(all_bs)

    return {
        "departments": dept_opts,
        "physicians": phys_opts,
        "techniques": tech_opts,
        "bodySystems": bs_opts,
    }


# ---------------------------------------------------------------------------
# Callbacks — main
# ---------------------------------------------------------------------------


@callback(
    Output("wf-store-sankey", "data"),
    Output("wf-store-flow-details", "data"),
    Output("wf-store-trend", "data"),
    Output("wf-detail-grid", "rowData"),
    Output("wf-detail-grid", "columnDefs"),
    Output("wf-store-selected-flow", "data"),
    Output("wf-filter-options", "data"),
    Input("wf-interval", "n_intervals"),
    Input("workflow-filter-department", "value"),
    Input("wf-date-slider", "value"),
    Input("workflow-filter-physician", "value"),
    Input("workflow-filter-technique", "value"),
    Input("workflow-filter-body-system", "value"),
    Input("wf-sankey-loopback-switch", "checked"),
    Input("wf-business-days-switch", "checked"),
    Input("wf-inpatient-switch", "checked"),
    Input("wf-agg-toggle", "value"),
    Input("wf-outlier-enabled", "data"),
    Input("wf-outlier-cap-0", "value"),
    Input("wf-outlier-cap-1", "value"),
    Input("wf-outlier-cap-2", "value"),
    Input("wf-outlier-cap-3", "value"),
    Input("wf-outlier-cap-4", "value"),
    running=[
        (Output("wf-sankey-loading", "visible"), True, False),
        (Output("wf-dist-loading", "visible"), True, False),
        (Output("wf-trend-loading", "visible"), True, False),
    ],
)
def update_workflow(_n, departments, slider_val, physician, techniques, body_systems, show_loopbacks, use_business_days, inpatient_only, agg_func, outlier_enabled, cap0, cap1, cap2, cap3, cap4):
    return _process_workflow_dataset(
        departments, slider_val, physician, techniques, body_systems,
        show_loopbacks, use_business_days, inpatient_only, agg_func,
        outlier_enabled, [cap0, cap1, cap2, cap3, cap4],
    )


def _process_workflow_dataset(
    departments, slider_val, physician, techniques, body_systems,
    show_loopbacks, use_business_days, inpatient_only, agg_func,
    outlier_enabled, caps,
):
    """Process workflow data for a single filter configuration.

    Returns: (sankey_data, flow_details, trend_data,
              row_data, col_defs, selected_flow, filter_options)
    """
    from data.loader import load_workflow, load_courses, load_diagnosis, load_clinic_visits

    empty = (None, None, None, [], [], None, None)

    try:
        wf = load_workflow()
    except Exception:
        return empty

    if wf.empty:
        return empty

    # Forward-fill exam info (Department, Physician, etc.)
    wf = _forward_fill_exam_info(wf)

    # Deduplicate overlapping chains: keep only the primary exam per sim
    # (SimVisitRank=1) and chains with no completed sim yet (NULL).
    # Rank > 1 means an older exam claimed the same sim — drop those.
    if "SimVisitRank" in wf.columns:
        wf = wf[wf["SimVisitRank"].isna() | (wf["SimVisitRank"] == 1)]

    # Exclude non-EBRT modalities (Brachytherapy, Pluvicto/radiopharmaceuticals)
    _EXCLUDED_MODALITIES = {"Brachytherapy", "Pluvicto"}
    if "ModalityType" in wf.columns:
        wf = wf[~wf["ModalityType"].str.strip().str.upper().isin(
            {m.upper() for m in _EXCLUDED_MODALITIES}
        ) | wf["ModalityType"].isna()]

    # Exclude future-dated open/scheduled appointments (tomorrow's schedule, etc.)
    _today = pd.Timestamp.now().normalize()
    if "StageDateTime" in wf.columns and "StageStatus" in wf.columns:
        wf = wf[~((wf["StageDateTime"] > _today) & (wf["StageStatus"] == "Open"))]

    # Get date range from Exam rows
    exam_dates = wf.loc[wf["StageName"] == "Exam", "StageDateTime"].dropna()
    last_date = exam_dates.max() if not exam_dates.empty else pd.Timestamp.now().normalize()
    # Modern 6-stage ARIA workflow (with Isodose/ReviewPlan) began Dec 2013.
    # Data before that reflects a fundamentally different pipeline config.
    first_date = pd.Timestamp("2014-01-01")
    start, end = _get_date_range(slider_val, None, first_date, last_date)

    # Inpatient filter: keep only workflows whose Exam patient had an
    # inpatient clinic visit on the same date (joined by PatientId + date)
    if inpatient_only:
        try:
            cv = load_clinic_visits()
            inpt = cv[cv["InPatientFlag"] == "Yes"]
            if not inpt.empty and "PatientId" in wf.columns:
                inpt_keys = set(
                    zip(
                        inpt["PatientId"].astype(str),
                        inpt["ScheduledDateTime"].dt.normalize(),
                    )
                )
                exams = wf[wf["StageName"] == "Exam"].copy()
                exam_keys = list(
                    zip(
                        exams["PatientId"].astype(str),
                        exams["StageDateTime"].dt.normalize(),
                    )
                )
                match_mask = [k in inpt_keys for k in exam_keys]
                inpt_chains = set(exams.loc[exams.index[match_mask], "UniqueRowID"])
                wf = wf[wf["UniqueRowID"].isin(inpt_chains)]
        except Exception:
            pass  # clinic visits unavailable — skip filter

    # Load lookup tables once (needed for cross-filtering and dimension filters)
    try:
        courses_df = load_courses()
    except Exception:
        courses_df = None
    try:
        diag_df = load_diagnosis()
    except Exception:
        diag_df = None

    # --- Date filter first (base filter for cross-filtering) ---
    # Date filter: apply to Exam rows and then keep all stages for matching patients
    if "StageDateTime" in wf.columns:
        exam_in_range = wf[
            (wf["StageName"] == "Exam") &
            (wf["StageDateTime"] >= start) &
            (wf["StageDateTime"] <= end)
        ]
        if "DimCourseID" in wf.columns and exam_in_range["DimCourseID"].notna().any():
            course_ids = exam_in_range["DimCourseID"].dropna().unique()
            patient_ids = exam_in_range["PatientId"].dropna().unique()
            wf = wf[
                wf["DimCourseID"].isin(course_ids) |
                (wf["DimCourseID"].isna() & wf["PatientId"].isin(patient_ids))
            ]
        elif "PatientId" in wf.columns:
            patient_ids = exam_in_range["PatientId"].dropna().unique()
            wf = wf[wf["PatientId"].isin(patient_ids)]

    if wf.empty:
        return empty

    # --- Cross-filter: compute available options for each dimension ---
    filter_options = _compute_available_options(
        wf, departments, physician, techniques, body_systems,
        courses_df, diag_df,
    )

    # --- Apply dimension filters ---
    wf = _apply_dimension_filter(
        wf, departments, physician, techniques, body_systems,
        courses_df, diag_df,
    )

    if wf.empty:
        return (None, None, None, [], [], None, filter_options)

    # Keep filtered data (respects date/dept/physician/etc.) for loopback counts
    wf_full = wf

    # Filter to pure workflows (no repeats) when loopbacks switch is off
    if not show_loopbacks and "StageOccurrence" in wf.columns and "UniqueRowID" in wf.columns:
        chains_with_loopbacks = wf.loc[
            wf["StageOccurrence"].fillna(1) > 1, "UniqueRowID"
        ].unique()
        wf = wf[~wf["UniqueRowID"].isin(chains_with_loopbacks)]
        if wf.empty:
            return (None, None, None, [], [], None, filter_options)

    # Pivot to course-level — ensure clean integer index for column arithmetic
    pivot = _pivot_to_courses(wf).reset_index(drop=True)

    if pivot.empty:
        return (None, None, None, [], [], None, filter_options)

    # Enforce date range on pivoted Exam dates — prevents old courses from
    # leaking through the PatientId fallback when DimCourseID is null
    if "Exam" in pivot.columns:
        pivot = pivot[(pivot["Exam"] >= start) & (pivot["Exam"] <= end)]
        pivot = pivot.reset_index(drop=True)
        if pivot.empty:
            return (None, None, None, [], [], None, filter_options)

    # Drop dead-end follow-ups: Exam is a follow-up AND no Simulation was
    # ever scheduled for the chain (not even cancelled/deleted — check raw
    # wf_full, which includes all statuses).
    if "StageActivityName" in pivot.columns and "UniqueRowID" in pivot.columns:
        chains_with_sim = set(
            wf_full.loc[wf_full["StageName"] == "Simulation", "UniqueRowID"]
        )
        is_followup = pivot["StageActivityName"].str.contains(
            "Follow", case=False, na=False,
        )
        has_no_sim = ~pivot["UniqueRowID"].isin(chains_with_sim)
        pivot = pivot[~(is_followup & has_no_sim)].reset_index(drop=True)
        if pivot.empty:
            return (None, None, None, [], [], None, filter_options)

    # Remove chains with stage gaps (e.g., has Treatment but skipped Isodose).
    # Pre-2014 ARIA didn't have Isodose/ReviewPlan stages, so legacy chains
    # would otherwise distort the funnel with false "cancelled" exits.
    stage_cols = [s for s in STAGES if s in pivot.columns]
    if len(stage_cols) >= 2:
        _present = pivot[stage_cols].notna()
        _has_gap = pd.Series(False, index=pivot.index)
        _seen_null = pd.Series(False, index=pivot.index)
        for _col in stage_cols:
            _has_gap |= (_seen_null & _present[_col])
            _seen_null |= ~_present[_col]
        pivot = pivot[~_has_gap].reset_index(drop=True)
        if pivot.empty:
            return (None, None, None, [], [], None, filter_options)

    # Enrich pivot with per-stage BaselineDateTime from ARIA (handles hidden
    # intermediate stages like ContourReview between Draw and Isodose)
    pivot = _enrich_pivot_with_baselines(pivot, wf_full)

    bdays = bool(use_business_days)

    # --- Outlier exclusion ---
    cap0, cap1, cap2, cap3, cap4 = caps
    if outlier_enabled:
        outlier_caps = [cap0, cap1, cap2, cap3, cap4]
        _stage_pairs = [
            ("Exam", "Simulation"),
            ("Simulation", "Draw"),
            ("Draw", "Isodose"),
            ("Isodose", "ReviewPlan"),
            ("ReviewPlan", "Treatment"),
        ]
        keep_mask = pd.Series(True, index=pivot.index)
        for (col_from, col_to), cap in zip(_stage_pairs, outlier_caps):
            if (col_from not in pivot.columns or col_to not in pivot.columns
                    or cap is None or cap >= OUTLIER_SLIDER_MAX):
                continue
            both = pivot[col_from].notna() & pivot[col_to].notna()
            baseline_col = f"{col_to}_baseline"
            if baseline_col in pivot.columns:
                _start = pivot[baseline_col].fillna(pivot[col_from])
            else:
                _start = pivot[col_from]
            dur = _duration_days(_start, pivot[col_to], bdays)
            keep_mask &= ~(both & (dur > cap))
        pivot = pivot[keep_mask].reset_index(drop=True)
        if pivot.empty:
            return (None, None, None, [], [], None, filter_options)

    agg = agg_func or "median"

    # --- Flow-Gantt data ---
    sankey_data = _compute_flow_data(pivot, wf_full, bdays, agg)

    # --- Flow details (for distribution + trend charts) ---
    flow_details = _compute_flow_details(pivot, wf_full, bdays, agg)

    # --- Trend data ---
    trend_data = _prepare_trend_data(pivot, bdays, agg)

    # --- Detail table ---
    row_data, col_defs = _build_table_data(pivot, bdays)

    return (sankey_data, flow_details, trend_data,
            row_data, col_defs, None, filter_options)


# ---------------------------------------------------------------------------
# Compare mode toggle
# ---------------------------------------------------------------------------

@callback(
    Output("wf-compare-mode", "data"),
    Input("wf-compare-toggle", "n_clicks"),
    State("wf-compare-mode", "data"),
    prevent_initial_call=True,
)
def _toggle_compare(n, current):
    return not current


# Compare mode visibility — toggle B filter bar, gantt height, table, button color
clientside_callback(
    """function(compareMode) {
        if (compareMode) {
            return [
                {"display": "block", "marginTop": "8px"},
                {"width": "100%", "minHeight": "800px", "maxHeight": "1100px"},
                {"display": "none"},
                "violet"
            ];
        }
        return [
            {"display": "none"},
            {"width": "100%", "aspectRatio": "2.45 / 1", "minHeight": "340px", "maxHeight": "480px"},
            {},
            "gray"
        ];
    }""",
    Output("wf-b-filter-container", "style"),
    Output("wf-flow-gantt", "style"),
    Output("wf-table-container", "style"),
    Output("wf-compare-toggle", "color"),
    Input("wf-compare-mode", "data"),
)

# Hide "A" badge when compare mode is off (no need to label single dataset)
clientside_callback(
    """function(compareMode) {
        var badges = document.querySelectorAll('.wf-dataset-badge-a');
        for (var i = 0; i < badges.length; i++) {
            badges[i].style.display = compareMode ? '' : 'none';
        }
        return window.dash_clientside.no_update;
    }""",
    Output("wf-a-filter-container", "className"),
    Input("wf-compare-mode", "data"),
)


# ---------------------------------------------------------------------------
# Dataset B server callback
# ---------------------------------------------------------------------------

@callback(
    Output("wf-b-store-sankey", "data"),
    Output("wf-b-store-flow-details", "data"),
    Output("wf-b-store-trend", "data"),
    Output("wf-b-store-selected-flow", "data"),
    Output("wf-b-filter-options", "data"),
    Input("wf-compare-mode", "data"),
    Input("wf-interval", "n_intervals"),
    Input("wf-b-filter-department", "value"),
    Input(_id("wf-b", "date-slider"), "value"),
    Input("wf-b-filter-physician", "value"),
    Input("wf-b-filter-technique", "value"),
    Input("wf-b-filter-body-system", "value"),
    Input(_id("wf-b", "loopback-switch"), "checked"),
    Input(_id("wf-b", "business-days-switch"), "checked"),
    Input(_id("wf-b", "inpatient-switch"), "checked"),
    Input(_id("wf-b", "agg-toggle"), "value"),
    Input("wf-b-outlier-enabled", "data"),
    Input(_id("wf-b", "outlier-cap-0"), "value"),
    Input(_id("wf-b", "outlier-cap-1"), "value"),
    Input(_id("wf-b", "outlier-cap-2"), "value"),
    Input(_id("wf-b", "outlier-cap-3"), "value"),
    Input(_id("wf-b", "outlier-cap-4"), "value"),
    running=[
        (Output("wf-sankey-loading", "visible"), True, False),
    ],
)
def update_workflow_b(compare_mode, _n, departments, slider_val, physician,
                      techniques, body_systems, show_loopbacks,
                      use_business_days, inpatient_only, agg_func,
                      outlier_enabled, cap0, cap1, cap2, cap3, cap4):
    if not compare_mode:
        return (None,) * 5
    result = _process_workflow_dataset(
        departments, slider_val, physician, techniques, body_systems,
        show_loopbacks, use_business_days, inpatient_only, agg_func,
        outlier_enabled, [cap0, cap1, cap2, cap3, cap4],
    )
    # result is (sankey, flow_details, trend, row_data, col_defs, selected_flow, filter_options)
    # We only need: sankey, flow_details, trend, selected_flow, filter_options
    return (result[0], result[1], result[2], result[5], result[6])


# ---------------------------------------------------------------------------
# Clientside callbacks for charts (compare-aware)
# ---------------------------------------------------------------------------

# Flow-Gantt — passes both A and B data + compare mode
clientside_callback(
    ClientsideFunction(namespace="flowGantt", function_name="renderFlowGantt"),
    Output("wf-flow-gantt-trigger", "data"),
    Input("wf-store-sankey", "data"),
    Input("wf-sankey-loopback-switch", "checked"),
    Input("wf-b-store-sankey", "data"),
    Input(_id("wf-b", "loopback-switch"), "checked"),
    Input("wf-compare-mode", "data"),
)

# Distribution chart — compare-aware
# A/B agg toggles passed directly so median↔mean switches are instant (no server round-trip)
clientside_callback(
    ClientsideFunction(namespace="flowGantt", function_name="renderFlowDistribution"),
    Output("wf-chart-dist", "figure"),
    Output("wf-dist-title", "children"),
    Input("wf-store-flow-details", "data"),
    Input("wf-store-selected-flow", "data"),
    Input("wf-dist-type", "value"),
    Input("wf-dist-km-switch", "checked"),
    Input("wf-b-store-flow-details", "data"),
    Input("wf-compare-mode", "data"),
    Input("wf-agg-toggle", "value"),
    Input(_id("wf-b", "agg-toggle"), "value"),
)

# Trend chart — compare-aware
clientside_callback(
    ClientsideFunction(namespace="flowGantt", function_name="renderFlowTrend"),
    Output("wf-chart-trend", "figure"),
    Output("wf-trend-title", "children"),
    Output("wf-trend-maturity-legend", "style"),
    Input("wf-store-flow-details", "data"),
    Input("wf-store-selected-flow", "data"),
    Input("wf-store-trend", "data"),
    Input("wf-trend-settings-smooth", "value"),
    Input("wf-trend-settings-type", "value"),
    Input("wf-trend-agg", "value"),
    Input("wf-trend-km-switch", "checked"),
    Input("wf-b-store-flow-details", "data"),
    Input("wf-b-store-trend", "data"),
    Input("wf-compare-mode", "data"),
    Input("wf-agg-toggle", "value"),
    Input(_id("wf-b", "agg-toggle"), "value"),
)


# ---------------------------------------------------------------------------
# Chart builders
# ---------------------------------------------------------------------------

def _simple_kde(values, n_points=100):
    """Simple Gaussian KDE without scipy dependency."""
    values = np.asarray(values, dtype=float)
    n = len(values)
    if n < 2:
        return [], []
    std = float(values.std())
    iqr = float(np.percentile(values, 75) - np.percentile(values, 25))
    bw = 0.9 * min(std, iqr / 1.34) * n ** (-0.2) if iqr > 0 else std * 0.5
    if bw <= 0:
        bw = 1.0
    x_min = max(0, float(values.min()) - bw * 3)
    x_max = float(values.max()) + bw * 3
    x = np.linspace(x_min, x_max, n_points)
    diff = x[:, np.newaxis] - values[np.newaxis, :]
    y = np.sum(np.exp(-0.5 * (diff / bw) ** 2), axis=1)
    y /= (n * bw * np.sqrt(2 * np.pi))
    return [round(float(v), 2) for v in x], [round(float(v), 6) for v in y]


def _kaplan_meier_median(durations, events):
    """Estimate median duration using Kaplan-Meier survival analysis.

    Args:
        durations: array of observed times (completed or censored).
        events: boolean array — True = completed, False = censored (in-progress).

    Returns:
        Estimated median (float) or None if survival never crosses 0.5.
    """
    durations = np.asarray(durations, dtype=float)
    events = np.asarray(events, dtype=bool)
    valid = np.isfinite(durations) & (durations >= 0)
    durations, events = durations[valid], events[valid]
    if len(durations) == 0 or not events.any():
        return None

    order = np.argsort(durations, kind="mergesort")
    t = durations[order]
    e = events[order]

    n = len(t)
    at_risk = n
    survival = 1.0
    i = 0
    while i < n:
        ti = t[i]
        d_i = 0   # completions at this time
        c_i = 0   # censored at this time
        while i < n and t[i] == ti:
            if e[i]:
                d_i += 1
            else:
                c_i += 1
            i += 1
        if d_i > 0 and at_risk > 0:
            survival *= (1.0 - d_i / at_risk)
            if survival <= 0.5:
                return float(ti)
        at_risk -= (d_i + c_i)

    return None


def _compute_flow_details(pivot, wf_full=None, use_business_days=False, agg_func="median"):
    """Compute per-transition detail data for clientside distribution & trend."""
    pairs = [
        ("Exam", "Simulation", "Consult → Sim"),
        ("Simulation", "Draw", "Sim → Contour"),
        ("Draw", "Isodose", "Contour → Plan"),
        ("Isodose", "ReviewPlan", "Plan → Review"),
        ("ReviewPlan", "Treatment", "Review → Tx"),
    ]
    transitions = []
    for idx, (col_from, col_to, label) in enumerate(pairs):
        if col_from not in pivot.columns or col_to not in pivot.columns:
            transitions.append(None)
            continue
        mask = pivot[col_from].notna() & pivot[col_to].notna()
        if mask.sum() == 0:
            transitions.append(None)
            continue
        sub = pivot.loc[mask].copy()
        # Use BaselineDateTime of col_to when available (handles hidden stages)
        baseline_col = f"{col_to}_baseline"
        if baseline_col in sub.columns:
            start = sub[baseline_col].fillna(sub[col_from])
        else:
            start = sub[col_from]
        days = _duration_days(start, sub[col_to], use_business_days)
        days = days[(days >= 0) & (days < 365)].dropna()
        if len(days) == 0:
            transitions.append(None)
            continue

        days_arr = days.values
        kde_x, kde_y = _simple_kde(days_arr)

        # All courses that reached col_from (for completion rate + KM)
        all_reached = pivot[pivot[col_from].notna()].copy()
        _ref_date = pd.Timestamp.now().normalize()

        # Build combined completed + censored observations for KM
        completed_obs = all_reached[all_reached[col_to].notna()].copy()
        if baseline_col in completed_obs.columns:
            c_start = completed_obs[baseline_col].fillna(completed_obs[col_from])
        else:
            c_start = completed_obs[col_from]
        completed_obs["_obs_days"] = _duration_days(
            c_start, completed_obs[col_to], use_business_days,
        )
        completed_obs["_event"] = True
        censored_obs = all_reached[all_reached[col_to].isna()].copy()
        censored_obs["_obs_days"] = _duration_days(
            censored_obs[col_from],
            pd.Series(_ref_date, index=censored_obs.index),
            use_business_days,
        )
        censored_obs["_event"] = False
        km_obs = pd.concat([completed_obs, censored_obs], ignore_index=True)
        km_obs = km_obs[(km_obs["_obs_days"] >= 0) & (km_obs["_obs_days"] < 365)]

        # Trend data at daily/weekly/monthly aggregation levels
        ref_col = "Exam" if "Exam" in sub.columns else col_from
        ref_col_all = "Exam" if "Exam" in all_reached.columns else col_from
        temp = sub.loc[days.index].copy()
        temp["_days"] = days
        trend_by_agg = {}
        for _agg_key in ("D", "W", "M"):
            if _agg_key == "D":
                temp["_period"] = temp[ref_col].dt.normalize()
                all_reached["_period"] = all_reached[ref_col_all].dt.normalize()
                km_obs["_period"] = km_obs[ref_col_all].dt.normalize()
            else:
                temp["_period"] = temp[ref_col].dt.to_period(_agg_key).dt.to_timestamp()
                all_reached["_period"] = all_reached[ref_col_all].dt.to_period(_agg_key).dt.to_timestamp()
                km_obs["_period"] = km_obs[ref_col_all].dt.to_period(_agg_key).dt.to_timestamp()
            grouped_median = temp.groupby("_period")["_days"].median()
            grouped_mean = temp.groupby("_period")["_days"].mean()
            completed_n = temp.groupby("_period")["_days"].size()
            started_n = all_reached.groupby("_period").size()
            rates = (completed_n / started_n.reindex(completed_n.index).fillna(1)).clip(0, 1).fillna(0)

            # KM median per period
            km_medians = {}
            for period, grp in km_obs.groupby("_period"):
                km_med = _kaplan_meier_median(grp["_obs_days"].values, grp["_event"].values)
                if km_med is not None:
                    km_medians[period] = round(km_med, 1)

            # Use all periods that have either raw or KM data
            all_periods = sorted(set(grouped_median.index) | set(km_medians.keys()))
            trend_by_agg[_agg_key] = {
                "dates": [d.isoformat() for d in all_periods],
                "medians": [round(float(grouped_median[d]), 1) if d in grouped_median.index else None for d in all_periods],
                "means": [round(float(grouped_mean[d]), 1) if d in grouped_mean.index else None for d in all_periods],
                "kmMedians": [km_medians.get(d) for d in all_periods],
                "counts": [int(completed_n.get(d, 0)) for d in all_periods],
                "completionRates": [round(float(rates.get(d, 0)), 2) for d in all_periods],
            }

        # Overall KM median for the distribution chart
        km_median_overall = _kaplan_meier_median(
            km_obs["_obs_days"].values, km_obs["_event"].values,
        )
        if km_median_overall is not None:
            km_median_overall = round(km_median_overall, 1)

        transitions.append({
            "label": label,
            "color": CHART_COLORWAY[idx % len(CHART_COLORWAY)],
            "days": [round(float(d), 3) for d in days_arr],
            "density": {"x": kde_x, "y": kde_y},
            "trendByAgg": trend_by_agg,
            "n": int(len(days_arr)),
            "nCensored": int(len(censored_obs)),
            "median": round(float(np.median(days_arr)), 3),
            "mean": round(float(np.mean(days_arr)), 3),
            "kmMedian": km_median_overall,
            "p25": round(float(np.percentile(days_arr, 25)), 3),
            "p75": round(float(np.percentile(days_arr, 75)), 3),
        })
    # Total pipeline (Exam → Treatment)
    total_data = None
    if "Exam" in pivot.columns and "Treatment" in pivot.columns:
        tmask = pivot["Exam"].notna() & pivot["Treatment"].notna()
        if tmask.sum() > 0:
            tsub = pivot.loc[tmask].copy()
            tdays = _duration_days(tsub["Exam"], tsub["Treatment"], use_business_days)
            tdays = tdays[(tdays >= 0) & (tdays < 365)].dropna()
            if len(tdays) > 0:
                tdays_arr = tdays.values
                tkde_x, tkde_y = _simple_kde(tdays_arr)
                ttemp = tsub.loc[tdays.index].copy()
                ttemp["_days"] = tdays
                # All courses with Exam (for completion rate + KM)
                tall_reached = pivot[pivot["Exam"].notna()].copy()
                _tref_date = pd.Timestamp.now().normalize()

                # Build completed + censored observations for KM
                t_completed = tall_reached[tall_reached["Treatment"].notna()].copy()
                t_completed["_obs_days"] = _duration_days(
                    t_completed["Exam"], t_completed["Treatment"], use_business_days,
                )
                t_completed["_event"] = True
                t_censored = tall_reached[tall_reached["Treatment"].isna()].copy()
                t_censored["_obs_days"] = _duration_days(
                    t_censored["Exam"],
                    pd.Series(_tref_date, index=t_censored.index),
                    use_business_days,
                )
                t_censored["_event"] = False
                tkm_obs = pd.concat([t_completed, t_censored], ignore_index=True)
                tkm_obs = tkm_obs[(tkm_obs["_obs_days"] >= 0) & (tkm_obs["_obs_days"] < 365)]

                ttba = {}
                for _agg_key in ("D", "W", "M"):
                    if _agg_key == "D":
                        ttemp["_period"] = ttemp["Exam"].dt.normalize()
                        tall_reached["_period"] = tall_reached["Exam"].dt.normalize()
                        tkm_obs["_period"] = tkm_obs["Exam"].dt.normalize()
                    else:
                        ttemp["_period"] = ttemp["Exam"].dt.to_period(_agg_key).dt.to_timestamp()
                        tall_reached["_period"] = tall_reached["Exam"].dt.to_period(_agg_key).dt.to_timestamp()
                        tkm_obs["_period"] = tkm_obs["Exam"].dt.to_period(_agg_key).dt.to_timestamp()
                    tgrouped_median = ttemp.groupby("_period")["_days"].median()
                    tgrouped_mean = ttemp.groupby("_period")["_days"].mean()
                    tcompleted_n = ttemp.groupby("_period")["_days"].size()
                    tstarted_n = tall_reached.groupby("_period").size()
                    trates = (tcompleted_n / tstarted_n.reindex(tcompleted_n.index).fillna(1)).clip(0, 1).fillna(0)

                    # KM median per period
                    tkm_medians = {}
                    for period, grp in tkm_obs.groupby("_period"):
                        km_med = _kaplan_meier_median(grp["_obs_days"].values, grp["_event"].values)
                        if km_med is not None:
                            tkm_medians[period] = round(km_med, 1)

                    tall_periods = sorted(set(tgrouped_median.index) | set(tkm_medians.keys()))
                    ttba[_agg_key] = {
                        "dates": [d.isoformat() for d in tall_periods],
                        "medians": [round(float(tgrouped_median[d]), 1) if d in tgrouped_median.index else None for d in tall_periods],
                        "means": [round(float(tgrouped_mean[d]), 1) if d in tgrouped_mean.index else None for d in tall_periods],
                        "kmMedians": [tkm_medians.get(d) for d in tall_periods],
                        "counts": [int(tcompleted_n.get(d, 0)) for d in tall_periods],
                        "completionRates": [round(float(trates.get(d, 0)), 2) for d in tall_periods],
                    }
                tkm_median_overall = _kaplan_meier_median(
                    tkm_obs["_obs_days"].values, tkm_obs["_event"].values,
                )
                if tkm_median_overall is not None:
                    tkm_median_overall = round(tkm_median_overall, 1)
                total_data = {
                    "label": "Total Pipeline",
                    "color": PRIMARY,
                    "days": [round(float(d), 3) for d in tdays_arr],
                    "density": {"x": tkde_x, "y": tkde_y},
                    "trendByAgg": ttba,
                    "n": int(len(tdays_arr)),
                    "nCensored": int(len(t_censored)),
                    "median": round(float(np.median(tdays_arr)), 3),
                    "mean": round(float(np.mean(tdays_arr)), 3),
                    "kmMedian": tkm_median_overall,
                    "p25": round(float(np.percentile(tdays_arr, 25)), 3),
                    "p75": round(float(np.percentile(tdays_arr, 75)), 3),
                }

    return {"transitions": transitions, "total": total_data, "aggFunc": agg_func}


def _prepare_trend_data(pivot, use_business_days=False, agg_func="median"):
    """Prepare trend data for clientside rendering."""
    if "Exam" not in pivot.columns or "Treatment" not in pivot.columns:
        return None

    temp = pivot[["Exam", "Treatment"]].reset_index(drop=True).copy()
    temp["total_days"] = _duration_days(temp["Exam"], temp["Treatment"], use_business_days)
    temp = temp[(temp["total_days"] >= 0) & (temp["total_days"] < 365)].dropna(subset=["total_days", "Exam"])

    if temp.empty:
        return None

    temp["month"] = temp["Exam"].dt.to_period("M").dt.to_timestamp()
    monthly = temp.groupby("month")["total_days"].median()
    dates = [d.isoformat() for d in monthly.index]

    series = [{
        "name": "Total Pipeline",
        "values": monthly.tolist(),
        "color": CHART_COLORWAY[0],
    }]

    # Add individual stage medians
    for col_from, col_to, label, color_idx in [
        ("Exam", "Simulation", "Consult→Sim", 1),
        ("ReviewPlan", "Treatment", "Review→Tx", 2),
    ]:
        if col_from in pivot.columns and col_to in pivot.columns:
            cols_needed = list(set(["Exam", col_from, col_to]))
            stage_temp = pivot[cols_needed].reset_index(drop=True).copy()
            stage_temp["_days"] = _duration_days(stage_temp[col_from], stage_temp[col_to], use_business_days)
            stage_temp = stage_temp[(stage_temp["_days"] >= 0) & (stage_temp["_days"] < 365)]
            stage_temp = stage_temp.dropna(subset=["_days", "Exam"])
            if not stage_temp.empty:
                stage_temp["month"] = stage_temp["Exam"].dt.to_period("M").dt.to_timestamp()
                stage_monthly = stage_temp.groupby("month")["_days"].median()
                series.append({
                    "name": label,
                    "values": stage_monthly.reindex(monthly.index, fill_value=0).tolist(),
                    "color": CHART_COLORWAY[color_idx],
                })

    return {
        "dates": dates,
        "series": series,
        "height": 350,
        "yTitle": "Median Days",
    }


def _build_table_data(pivot, use_business_days=False):
    """Build table row data and column definitions from pivoted course data."""
    col_map = {
        "PatientName": "Patient",
        "Department": "Dept",
        "TreatingPhysician": "Physician",
        "Exam": "Consult",
        "Simulation": "Sim",
        "days_to_sim": "Days to Sim",
        "Draw": "Draw",
        "Isodose": "Isodose",
        "ReviewPlan": "Review",
        "Treatment": "First Tx",
        "total_days": "Total Days",
        "status": "Status",
    }

    table = pivot.copy()

    # Compute derived columns
    if "Exam" in table.columns and "Simulation" in table.columns:
        table["days_to_sim"] = _duration_days(
            table["Exam"], table["Simulation"], use_business_days,
        ).round(1)
    if "Exam" in table.columns and "Treatment" in table.columns:
        table["total_days"] = _duration_days(
            table["Exam"], table["Treatment"], use_business_days,
        ).round(0)
    if "Treatment" in table.columns:
        table["status"] = table["Treatment"].apply(
            lambda x: "Complete" if pd.notna(x) else "In Progress"
        )

    # Select available columns
    available = [c for c in col_map if c in table.columns]
    if not available:
        return [], []

    table = table[available].head(200).copy()
    for c in table.select_dtypes(include=["datetime64", "datetime64[ns]"]).columns:
        table[c] = table[c].dt.strftime("%m/%d/%Y")
    table = table.fillna("—")

    col_defs = [{"field": c, "headerName": col_map.get(c, c)} for c in available]
    return table.to_dict("records"), col_defs


# ---------------------------------------------------------------------------
# Settings toggle + PNG export (shared framework)
# ---------------------------------------------------------------------------

register_chart_callbacks([("wf-trend", "wf-chart-trend")])

clientside_callback(
    """function(n) {
        if (!n) return window.dash_clientside.no_update;
        var gridApi = window.dash_ag_grid && window.dash_ag_grid['wf-detail-grid'];
        if (gridApi && gridApi.api) gridApi.api.exportDataAsCsv({fileName: 'pipeline_detail.csv'});
        return window.dash_clientside.no_update;
    }""",
    Output("wf-table-export", "n_clicks"),
    Input("wf-table-export", "n_clicks"),
    prevent_initial_call=True,
)
