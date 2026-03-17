"""Tasks page — physician task workload, SLA compliance, after-hours tracking."""

import dash
import dash_mantine_components as dmc
from dash import callback, Input, Output, State, dcc, html, clientside_callback, ClientsideFunction
import dash_ag_grid as dag
from dash_iconify import DashIconify
import plotly.graph_objects as go
import pandas as pd
import numpy as np
from config.settings import (
    PHYSICIANS, CHART_COLORWAY, PRIMARY,
    SEMANTIC_COLORS, NEUTRAL,
    CHART_PAPER_HEIGHT_SM,
)
from components.chart_card import chart_card, register_chart_callbacks
from components.kpi_card import kpi_card
from utils.charts import apply_default_layout, empty_figure, color_for_index
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

dash.register_page(__name__, path="/tasks", name="Tasks", order=5)

PAGE_ID = "tasks"

_DEFAULT_DATE_PRESET = "ytd" if pd.Timestamp.now().month > 1 else "3mo"


# ---------------------------------------------------------------------------
# Task type consolidation — raw ARIA ActivityNames → display groups
# ---------------------------------------------------------------------------
_TASK_TYPE_GROUPS = {
    "Draw Volumes": [
        "Draw Volumes",
        "Draw Volumes / Add Rx",
        "Draw Volumes/MLCs",
        "Draw Blocks",
    ],
    "Draw Volumes (SRS)": [
        "Draw Volumes SRS / Add Rx",
    ],
    "Contour Review": [
        "Contour Review",
    ],
    "Review Plan": [
        "Review Plan/Chart Rounds",
        "Review Plan/Rounds",
    ],
}

# Reverse lookup: raw ActivityName → group label
_TASK_TYPE_TO_GROUP = {}
for _grp, _raws in _TASK_TYPE_GROUPS.items():
    for _raw in _raws:
        _TASK_TYPE_TO_GROUP[_raw] = _grp

_TASK_GROUP_NAMES = list(_TASK_TYPE_GROUPS.keys())

# KPI card groups — each shows completed / open / median time
_KPI_GROUPS = [
    {"name": "Draw Volumes", "key": "draw", "task_groups": ["Draw Volumes"],
     "color": CHART_COLORWAY[0]},
    {"name": "Draw Volumes (SRS)", "key": "srs", "task_groups": ["Draw Volumes (SRS)"],
     "color": CHART_COLORWAY[4]},
    {"name": "Contour Review", "key": "contour", "task_groups": ["Contour Review"],
     "color": CHART_COLORWAY[1]},
    {"name": "Review Plan", "key": "review", "task_groups": ["Review Plan"],
     "color": CHART_COLORWAY[2]},
]
for _kg in _KPI_GROUPS:
    _kg["raw_types"] = []
    for _g in _kg["task_groups"]:
        _kg["raw_types"].extend(_TASK_TYPE_GROUPS.get(_g, [_g]))


# ---------------------------------------------------------------------------
# Filter Bar (sim-style two-row layout)
# ---------------------------------------------------------------------------

def _build_tasks_filter_bar():
    """Build the sim-style two-row filter bar for tasks."""
    return dmc.Paper(
        children=[
            # Row 1: data filters
            dmc.Group(
                children=[
                    # Physician dropdown
                    html.Div(
                        children=[
                            html.Div(
                                children=[
                                    dmc.Button(
                                        "Physician",
                                        id="tasks-physician-trigger",
                                        variant="default",
                                        size="sm",
                                        rightSection=DashIconify(icon="mdi:chevron-down", width=14),
                                    ),
                                    dmc.ActionIcon(
                                        DashIconify(icon="mdi:close-circle", width=18),
                                        id="tasks-physician-clear",
                                        variant="subtle",
                                        color="gray",
                                        size="sm",
                                        className="wf-filter-clear-btn",
                                    ),
                                ],
                                style={"position": "relative", "display": "inline-block"},
                            ),
                            dmc.Paper(
                                id="tasks-physician-panel",
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
                                        id="tasks-filter-physician",
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
                                        id="tasks-diagnosis-trigger",
                                        variant="default",
                                        size="sm",
                                        rightSection=DashIconify(icon="mdi:chevron-down", width=14),
                                    ),
                                    dmc.ActionIcon(
                                        DashIconify(icon="mdi:close-circle", width=18),
                                        id="tasks-diagnosis-clear",
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
                                    id="tasks-filter-diagnosis",
                                    multiple=True,
                                    value=[],
                                ),
                                id="tasks-diagnosis-panel",
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
                    # Task Type dropdown
                    html.Div(
                        children=[
                            html.Div(
                                children=[
                                    dmc.Button(
                                        "Task Type",
                                        id="tasks-tasktype-trigger",
                                        variant="default",
                                        size="sm",
                                        rightSection=DashIconify(icon="mdi:chevron-down", width=14),
                                    ),
                                    dmc.ActionIcon(
                                        DashIconify(icon="mdi:close-circle", width=18),
                                        id="tasks-tasktype-clear",
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
                                        dmc.Chip(g, value=g, size="xs", variant="filled")
                                        for g in _TASK_GROUP_NAMES
                                    ],
                                    id="tasks-filter-type",
                                    multiple=True,
                                    value=[],
                                ),
                                id="tasks-tasktype-panel",
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
                    # Status: All / Open / Completed
                    dmc.SegmentedControl(
                        id="tasks-filter-status",
                        data=[
                            {"value": "all", "label": "All"},
                            {"value": "open", "label": "Open"},
                            {"value": "done", "label": "Completed"},
                        ],
                        value="all",
                        size="xs",
                    ),
                    # Smoothing
                    dmc.Group(
                        children=[
                            dmc.Text("Smoothing", size="xs", c="#6B7280", fw=500),
                            dmc.Slider(
                                id="tasks-smooth-slider",
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
                        id="tasks-filter-date-preset",
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
                            id="tasks-filter-daterange",
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
                            html.Div(id="tasks-date-range-label", style={"display": "none"}),
                            dmc.RangeSlider(
                                id="tasks-date-slider",
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
# KPI group card helpers
# ---------------------------------------------------------------------------

def _trend_el(text, direction):
    """Return a small trend badge or None."""
    if not text:
        return None
    tc = (SEMANTIC_COLORS["success"] if direction == "up"
          else SEMANTIC_COLORS["error"] if direction == "down"
          else NEUTRAL["text_muted"])
    icon = "\u25b2 " if direction == "up" else "\u25bc " if direction == "down" else ""
    return dmc.Text(f"{icon}{text}", size="xs", c=tc)


def _empty_sparkline():
    from components.kpi_card import create_sparkline
    return create_sparkline()


def _task_group_kpi_card(group_name, metrics, accent_color=None, key=""):
    """Build a task-group KPI card with two halves: completed+open | median time."""
    color = accent_color or PRIMARY

    left_children = [
        dmc.Group([
            dmc.Text("Completed", size="xs", c=NEUTRAL["text_secondary"], fw=500),
            dmc.Text(
                f"({metrics['open']} open)",
                size="xs", c=NEUTRAL["text_muted"],
            ),
        ], gap=4),
        dmc.Text(metrics["completed"], size="xl", fw=700,
                 c=NEUTRAL["text_primary"], lh=1.2),
    ]
    trend = _trend_el(metrics["comp_trend_text"], metrics["comp_trend_dir"])
    if trend is not None:
        left_children.append(trend)
    left_children.append(
        dcc.Graph(
            id=f"tasks-spark-{key}_comp",
            figure=_empty_sparkline(),
            config={"displayModeBar": False, "scrollZoom": False},
            style={"height": "44px", "marginTop": "2px"},
        )
    )

    time_label_parts = [
        dmc.Text("Median Time", size="xs", c=NEUTRAL["text_secondary"], fw=500),
    ]
    if metrics.get("pct_on_time_text"):
        time_label_parts.append(
            dmc.Text(metrics["pct_on_time_text"], size="xs",
                     c=NEUTRAL["text_muted"]),
        )

    right_children = [
        dmc.Group(time_label_parts, gap=4),
        dmc.Text(metrics["median_min"], size="xl", fw=700,
                 c=NEUTRAL["text_primary"], lh=1.2),
    ]
    trend_t = _trend_el(metrics["med_trend_text"], metrics["med_trend_dir"])
    if trend_t is not None:
        right_children.append(trend_t)
    right_children.append(
        dcc.Graph(
            id=f"tasks-spark-{key}_time",
            figure=_empty_sparkline(),
            config={"displayModeBar": False, "scrollZoom": False},
            style={"height": "44px", "marginTop": "2px"},
        )
    )

    return dmc.Paper(
        children=[
            dmc.Text(group_name, size="sm", fw=600,
                     c=accent_color or NEUTRAL["text_secondary"], mb=4),
            dmc.SimpleGrid(
                cols=2,
                spacing="md",
                children=[
                    dmc.Stack(left_children, gap=2),
                    dmc.Stack(right_children, gap=2),
                ],
            ),
        ],
        pt="sm",
        px="md",
        pb=4,
        radius="md",
        shadow="xs",
        withBorder=True,
        style={"borderLeft": f"4px solid {accent_color}" if accent_color else "none"},
    )


def _compute_group_metrics(df_base, df_prior_base, spark_base, raw_types,
                           spark_period="W"):
    """Compute KPI metrics and sparklines for one task-type group."""
    gdf = (df_base[df_base["ActivityName"].isin(raw_types)]
           if "ActivityName" in df_base.columns else df_base)
    gdf_prior = (df_prior_base[df_prior_base["ActivityName"].isin(raw_types)]
                 if "ActivityName" in df_prior_base.columns else df_prior_base)

    is_comp = (gdf["CompletedDateTime"].notna()
               if "CompletedDateTime" in gdf.columns
               else pd.Series(False, index=gdf.index))
    is_comp_prior = (gdf_prior["CompletedDateTime"].notna()
                     if "CompletedDateTime" in gdf_prior.columns
                     else pd.Series(False, index=gdf_prior.index))

    completed = int(is_comp.sum())
    open_count = int((~is_comp).sum())
    prior_completed = int(is_comp_prior.sum())

    comp_trend_dir = comp_trend_txt = None
    if prior_completed > 0 and completed > 0:
        pct_chg = ((completed - prior_completed) / prior_completed) * 100
        comp_trend_dir = "up" if pct_chg > 0 else "down" if pct_chg < 0 else None
        comp_trend_txt = f"{abs(pct_chg):.0f}% vs prior"

    median_min = "N/A"
    med_trend_dir = med_trend_txt = None
    if "MinutesToComplete" in gdf.columns:
        mins = pd.to_numeric(gdf.loc[is_comp, "MinutesToComplete"], errors="coerce").dropna()
        if len(mins) > 0:
            median_val = mins.median()
            if median_val >= 60:
                hrs = int(median_val // 60)
                rem = int(median_val % 60)
                median_min = f"{hrs}h {rem}m" if rem else f"{hrs}h"
            else:
                median_min = f"{median_val:.0f} min"

            if "MinutesToComplete" in gdf_prior.columns:
                prior_mins = pd.to_numeric(
                    gdf_prior.loc[is_comp_prior, "MinutesToComplete"], errors="coerce"
                ).dropna()
                if len(prior_mins) > 0:
                    prior_median = prior_mins.median()
                    pct_diff = (((median_val - prior_median) / prior_median) * 100
                                if prior_median else 0)
                    med_trend_dir = ("up" if pct_diff < 0
                                     else "down" if pct_diff > 0 else None)
                    med_trend_txt = f"{abs(pct_diff):.0f}% vs prior"

    pct_on_time_text = None
    if "MinutesToComplete" in gdf.columns and "MinutesAllowed" in gdf.columns:
        comp_df = gdf[is_comp].copy()
        comp_df["MinutesToComplete"] = pd.to_numeric(comp_df["MinutesToComplete"], errors="coerce")
        comp_df["MinutesAllowed"] = pd.to_numeric(comp_df["MinutesAllowed"], errors="coerce")
        valid = comp_df.dropna(subset=["MinutesToComplete", "MinutesAllowed"])
        if len(valid) > 0:
            pct_ot = (valid["MinutesToComplete"] <= valid["MinutesAllowed"]).mean() * 100
            pct_on_time_text = f"{pct_ot:.0f}% on time"

    spark_completed = spark_time = None
    spark_df = (spark_base[spark_base["ActivityName"].isin(raw_types)]
                if "ActivityName" in spark_base.columns else spark_base)

    if not spark_df.empty and "StartDateTime" in spark_df.columns:
        sdf = spark_df.copy()
        if spark_period == "D":
            sdf["_sp"] = sdf["StartDateTime"].dt.normalize()
        else:
            sdf["_sp"] = sdf["StartDateTime"].dt.to_period("W").dt.start_time
        spark_is_comp = (sdf["CompletedDateTime"].notna()
                         if "CompletedDateTime" in sdf.columns
                         else pd.Series(False, index=sdf.index))

        comp_by_sp = sdf[spark_is_comp].groupby("_sp").size().reset_index(name="count")
        if len(comp_by_sp) >= 3:
            spark_completed = {
                "labels": [d.isoformat() for d in comp_by_sp["_sp"]],
                "values": comp_by_sp["count"].tolist(),
            }

        if "MinutesToComplete" in sdf.columns:
            sdf["MinutesToComplete"] = pd.to_numeric(sdf["MinutesToComplete"], errors="coerce")
            time_by_sp = (sdf[spark_is_comp]
                          .groupby("_sp")["MinutesToComplete"].median()
                          .reset_index(name="median").dropna())
            if len(time_by_sp) >= 3:
                spark_time = {
                    "labels": [d.isoformat() for d in time_by_sp["_sp"]],
                    "values": time_by_sp["median"].tolist(),
                }

    return {
        "completed": f"{completed:,}",
        "open": str(open_count),
        "comp_trend_text": comp_trend_txt,
        "comp_trend_dir": comp_trend_dir,
        "median_min": median_min,
        "med_trend_text": med_trend_txt,
        "med_trend_dir": med_trend_dir,
        "pct_on_time_text": pct_on_time_text,
        "spark_completed": spark_completed,
        "spark_time": spark_time,
    }


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
                dmc.Title("Tasks", order=2, className="page-title", style={"margin": 0, "textAlign": "center"}),
                _build_tasks_filter_bar(),
            ],
        ),

        # KPI row — one group card per task type
        dmc.Grid(id="tasks-kpi-row", gutter="md", children=[
            dmc.GridCol(id="tasks-kpi-draw", span={"base": 12, "md": 3}),
            dmc.GridCol(id="tasks-kpi-srs", span={"base": 12, "md": 3}),
            dmc.GridCol(id="tasks-kpi-contour", span={"base": 12, "md": 3}),
            dmc.GridCol(id="tasks-kpi-review", span={"base": 12, "md": 3}),
        ]),

        # Row 1: Volume Trend + Cumulative
        dmc.Grid(gutter="md", children=[
            dmc.GridCol(
                chart_card(
                    "tasks-chart-volume",
                    "Task Volume Trend",
                    settings_id="tasks-volume",
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
                            id="tasks-volume-slice",
                            data=[
                                {"value": "", "label": "Total"},
                                {"value": "task", "label": "Task"},
                                {"value": "physician", "label": "MD"},
                                {"value": "bodysite", "label": "Dx"},
                            ],
                            value="",
                            size="xs",
                        ),
                    ],
                    extra_controls=[
                        dmc.SegmentedControl(
                            id="tasks-volume-agg",
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
                    "tasks-chart-cumulative",
                    "Cumulative Task Volume",
                    settings_id="tasks-cumulative",
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
                            id="tasks-cumulative-mode",
                            data=[
                                {"value": "prior", "label": "Prior Periods"},
                                {"value": "slice", "label": "Slice By"},
                            ],
                            value="prior",
                            size="xs",
                        ),
                        dmc.SegmentedControl(
                            id="tasks-cumulative-period-type",
                            data=[
                                {"value": "calendar", "label": "Calendar"},
                                {"value": "rolling", "label": "Rolling"},
                            ],
                            value="calendar",
                            size="xs",
                        ),
                        dmc.SegmentedControl(
                            id="tasks-cumulative-slice",
                            data=[
                                {"value": "task", "label": "Task"},
                                {"value": "physician", "label": "MD"},
                                {"value": "bodysite", "label": "Dx"},
                            ],
                            value="task",
                            size="xs",
                            style={"display": "none"},
                        ),
                    ],
                ),
                span={"base": 12, "md": 6},
            ),
        ]),

        # Row 2: Histogram + Time Trend + SLA Trend (3 across)
        dmc.Grid(gutter="md", children=[
            dmc.GridCol(
                chart_card(
                    "tasks-chart-histogram",
                    "Time Distribution",
                    settings_id="tasks-histogram",
                    chart_types=[
                        {"value": "histogram", "label": "Histogram"},
                        {"value": "density", "label": "Density"},
                    ],
                    show_smooth=False,
                    paper_padding="md",
                    paper_height=CHART_PAPER_HEIGHT_SM,
                    extra_controls_left=[
                        dmc.SegmentedControl(
                            id="tasks-hist-slice",
                            data=[
                                {"value": "", "label": "Total"},
                                {"value": "task", "label": "Task"},
                                {"value": "physician", "label": "MD"},
                                {"value": "bodysite", "label": "Dx"},
                            ],
                            value="",
                            size="xs",
                        ),
                    ],
                ),
                span={"base": 12, "md": 4},
            ),
            dmc.GridCol(
                chart_card(
                    "tasks-chart-time-trend",
                    "Time to Complete Trend",
                    settings_id="tasks-time-trend",
                    chart_types=[
                        {"value": "line", "label": "Line"},
                        {"value": "area", "label": "Area"},
                        {"value": "bar", "label": "Bar"},
                    ],
                    show_smooth=True,
                    smooth_max=12,
                    smooth_default=2,
                    paper_padding="md",
                    paper_height=CHART_PAPER_HEIGHT_SM,
                    extra_controls_left=[
                        dmc.SegmentedControl(
                            id="tasks-time-slice",
                            data=[
                                {"value": "", "label": "Total"},
                                {"value": "task", "label": "Task"},
                                {"value": "physician", "label": "MD"},
                                {"value": "bodysite", "label": "Dx"},
                            ],
                            value="",
                            size="xs",
                        ),
                    ],
                    extra_controls=[
                        dmc.SegmentedControl(
                            id="tasks-time-agg",
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
                span={"base": 12, "md": 4},
            ),
            dmc.GridCol(
                chart_card(
                    "tasks-chart-sla",
                    "SLA Compliance Trend",
                    settings_id="tasks-sla",
                    chart_types=[
                        {"value": "line", "label": "Line"},
                        {"value": "area", "label": "Area"},
                        {"value": "bar", "label": "Bar"},
                    ],
                    show_smooth=True,
                    smooth_max=12,
                    smooth_default=0,
                    paper_padding="md",
                    paper_height=CHART_PAPER_HEIGHT_SM,
                    extra_controls_left=[
                        dmc.SegmentedControl(
                            id="tasks-sla-slice",
                            data=[
                                {"value": "", "label": "Total"},
                                {"value": "task", "label": "Task"},
                                {"value": "physician", "label": "MD"},
                                {"value": "bodysite", "label": "Dx"},
                            ],
                            value="",
                            size="xs",
                        ),
                    ],
                    extra_controls=[
                        dmc.SegmentedControl(
                            id="tasks-sla-agg",
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
        ]),

        # Detail table
        dmc.Paper(
            children=[
                dmc.Group([
                    dmc.Text("Task Detail", size="sm", fw=500, c=NEUTRAL["text_secondary"]),
                    dmc.ActionIcon(
                        dmc.Text("CSV", size="xs", fw=600),
                        id="tasks-table-export",
                        variant="subtle", color="gray", size="sm",
                    ),
                ], justify="space-between", mb="sm"),
                dmc.Box(id="tasks-table-container"),
            ],
            p="md", radius="md", shadow="xs", withBorder=True,
        ),

        # Stores for clientside callbacks
        dcc.Store(id="tasks-store-volume"),
        dcc.Store(id="tasks-store-cumulative"),
        dcc.Store(id="tasks-store-time-trend"),
        dcc.Store(id="tasks-store-sla"),
        dcc.Store(id="tasks-store-kpi-sparklines"),

        dcc.Interval(id="tasks-interval", interval=300_000, n_intervals=0),
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

def _register_tasks_filter_callbacks():
    """Register all filter-sync callbacks for the tasks page."""

    # A) Preset → Slider + DatePicker
    @callback(
        Output("tasks-date-slider", "value"),
        Output("tasks-filter-daterange", "start_date", allow_duplicate=True),
        Output("tasks-filter-daterange", "end_date", allow_duplicate=True),
        Input("tasks-filter-date-preset", "value"),
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
        ClientsideFunction(namespace="tasksDateSlider", function_name="syncSlider"),
        Output("tasks-filter-daterange", "start_date", allow_duplicate=True),
        Output("tasks-filter-daterange", "end_date", allow_duplicate=True),
        Output("tasks-date-range-label", "children"),
        Input("tasks-date-slider", "value"),
        State("tasks-filter-daterange", "start_date"),
        State("tasks-filter-daterange", "end_date"),
        prevent_initial_call=True,
    )

    # C) DatePicker → Slider
    @callback(
        Output("tasks-date-slider", "value", allow_duplicate=True),
        Input("tasks-filter-daterange", "start_date"),
        Input("tasks-filter-daterange", "end_date"),
        State("tasks-date-slider", "value"),
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
        Output("tasks-filter-date-preset", "value", allow_duplicate=True),
        Input("tasks-date-slider", "value"),
        State("tasks-filter-date-preset", "value"),
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
        Output("tasks-physician-trigger", "children"),
        Input("tasks-filter-physician", "value"),
    )
    clientside_callback(
        "function(vals) {"
        "  if (!vals || vals.length === 0) return 'Diagnosis';"
        "  if (vals.length === 1) return vals[0];"
        "  return vals.length + ' selected';"
        "}",
        Output("tasks-diagnosis-trigger", "children"),
        Input("tasks-filter-diagnosis", "value"),
    )
    clientside_callback(
        "function(vals) {"
        "  if (!vals || vals.length === 0) return 'Task Type';"
        "  if (vals.length === 1) return vals[0];"
        "  return vals.length + ' selected';"
        "}",
        Output("tasks-tasktype-trigger", "children"),
        Input("tasks-filter-type", "value"),
    )

    # --- Clear-button visibility ---
    clientside_callback(
        """function(val) { return val ? {"display": "inline-flex"} : {"display": "none"}; }""",
        Output("tasks-physician-clear", "style"),
        Input("tasks-filter-physician", "value"),
    )
    clientside_callback(
        """function(vals) { return vals && vals.length > 0 ? {"display": "inline-flex"} : {"display": "none"}; }""",
        Output("tasks-diagnosis-clear", "style"),
        Input("tasks-filter-diagnosis", "value"),
    )
    clientside_callback(
        """function(vals) { return vals && vals.length > 0 ? {"display": "inline-flex"} : {"display": "none"}; }""",
        Output("tasks-tasktype-clear", "style"),
        Input("tasks-filter-type", "value"),
    )

    # --- Clear-button actions ---
    clientside_callback(
        """function(n) { return null; }""",
        Output("tasks-filter-physician", "value", allow_duplicate=True),
        Input("tasks-physician-clear", "n_clicks"),
        prevent_initial_call=True,
    )
    clientside_callback(
        """function(n) { return []; }""",
        Output("tasks-filter-diagnosis", "value", allow_duplicate=True),
        Input("tasks-diagnosis-clear", "n_clicks"),
        prevent_initial_call=True,
    )
    clientside_callback(
        """function(n) { return []; }""",
        Output("tasks-filter-type", "value", allow_duplicate=True),
        Input("tasks-tasktype-clear", "n_clicks"),
        prevent_initial_call=True,
    )


# Register filter callbacks
_register_tasks_filter_callbacks()


# ---------------------------------------------------------------------------
# Server-side callback: compute data and output to stores
# ---------------------------------------------------------------------------
@callback(
    Output("tasks-kpi-draw", "children"),
    Output("tasks-kpi-srs", "children"),
    Output("tasks-kpi-contour", "children"),
    Output("tasks-kpi-review", "children"),
    Output("tasks-chart-histogram", "figure"),
    Output("tasks-table-container", "children"),
    Output("tasks-store-volume", "data"),
    Output("tasks-store-cumulative", "data"),
    Output("tasks-store-time-trend", "data"),
    Output("tasks-store-sla", "data"),
    Output("tasks-store-kpi-sparklines", "data"),
    Input("tasks-interval", "n_intervals"),
    Input("tasks-filter-date-preset", "value"),
    Input("tasks-filter-physician", "value"),
    Input("tasks-filter-type", "value"),
    Input("tasks-filter-diagnosis", "value"),
    Input("tasks-filter-status", "value"),
    Input("tasks-date-slider", "value"),
    Input("tasks-volume-agg", "value"),
    Input("tasks-volume-slice", "value"),
    Input("tasks-cumulative-mode", "value"),
    Input("tasks-cumulative-period-type", "value"),
    Input("tasks-cumulative-slice", "value"),
    Input("tasks-hist-slice", "value"),
    Input("tasks-histogram-settings-type", "value"),
    Input("tasks-time-agg", "value"),
    Input("tasks-time-slice", "value"),
    Input("tasks-sla-agg", "value"),
    Input("tasks-sla-slice", "value"),
    running=[
        (Output("tasks-chart-volume-loading", "visible"), True, False),
        (Output("tasks-chart-cumulative-loading", "visible"), True, False),
        (Output("tasks-chart-histogram-loading", "visible"), True, False),
        (Output("tasks-chart-time-trend-loading", "visible"), True, False),
        (Output("tasks-chart-sla-loading", "visible"), True, False),
    ],
)
def update_tasks(_n, date_preset, physician, task_types,
                 diagnosis_cats, status, slider_val,
                 volume_agg, volume_slice,
                 cumul_mode, cumul_period_type, cumul_slice,
                 hist_slice, hist_type,
                 time_agg, time_slice,
                 sla_agg, sla_slice):
    from data.loader import load_tasks, load_diagnosis

    _empty_store = {"dates": [], "series": []}
    try:
        tasks = load_tasks()
    except Exception:
        empty = empty_figure("Tasks data unavailable")
        na_card = dmc.Text("\u2014", ta="center")
        return (na_card, na_card, na_card, na_card, empty, [],
                _empty_store, None, _empty_store, _empty_store, {})

    start, end = _get_date_range(slider_val)
    prior_start = start - (end - start)

    # Adaptive sparkline granularity
    range_months = (end.year - start.year) * 12 + (end.month - start.month) + 1
    _spark_period = "D" if range_months <= 3 else "W"

    # --- Base filtering (everything except task type) ---
    df_base = tasks.copy()
    if "StartDateTime" in df_base.columns:
        df_base = df_base[(df_base["StartDateTime"] >= start) & (df_base["StartDateTime"] <= end)]
    if physician and "AssignedMD" in df_base.columns:
        df_base = df_base[df_base["AssignedMD"] == physician]

    try:
        diag_df = load_diagnosis()
    except Exception:
        diag_df = None
    c2b = build_code_to_category(diag_df)

    if diagnosis_cats and "DiagnosisCodes" in df_base.columns and c2b:
        bs_set = set(diagnosis_cats)
        row_bs = df_base["DiagnosisCodes"].apply(
            lambda s: get_categories_for_codes(s, c2b) if pd.notna(s) else set()
        )
        df_base = df_base[row_bs.apply(lambda cats: bool(cats & bs_set))]

    # Status filter
    is_completed_base = (df_base["CompletedDateTime"].notna()
                         if "CompletedDateTime" in df_base.columns
                         else pd.Series(False, index=df_base.index))
    if status == "open":
        df_base = df_base[~is_completed_base]
    elif status == "done":
        df_base = df_base[is_completed_base]

    # --- Prior period (no status filter, no task-type filter) ---
    df_prior_base = tasks.copy()
    if "StartDateTime" in df_prior_base.columns:
        df_prior_base = df_prior_base[
            (df_prior_base["StartDateTime"] >= prior_start)
            & (df_prior_base["StartDateTime"] < start)
        ]
    if physician and "AssignedMD" in df_prior_base.columns:
        df_prior_base = df_prior_base[df_prior_base["AssignedMD"] == physician]
    if diagnosis_cats and "DiagnosisCodes" in df_prior_base.columns and c2b:
        bs_set = set(diagnosis_cats)
        row_bs_prior = df_prior_base["DiagnosisCodes"].apply(
            lambda s: get_categories_for_codes(s, c2b) if pd.notna(s) else set()
        )
        df_prior_base = df_prior_base[row_bs_prior.apply(lambda cats: bool(cats & bs_set))]

    # --- Build KPI group cards + sparkline store data ---
    group_cards = []
    sparkline_data = {}
    for kg in _KPI_GROUPS:
        metrics = _compute_group_metrics(
            df_base, df_prior_base, df_base, kg["raw_types"],
            spark_period=_spark_period,
        )
        group_cards.append(
            _task_group_kpi_card(kg["name"], metrics,
                                accent_color=kg["color"], key=kg["key"])
        )
        k = kg["key"]
        if metrics.get("spark_completed"):
            sparkline_data[f"{k}_comp"] = {
                **metrics["spark_completed"],
                "color": kg["color"],
                "hover_fmt": "%{x|%b %d}: %{customdata:,.0f}<extra></extra>",
            }
        if metrics.get("spark_time"):
            sparkline_data[f"{k}_time"] = {
                **metrics["spark_time"],
                "color": kg["color"],
                "hover_fmt": "%{x|%b %d}: %{customdata:,.0f} min<extra></extra>",
            }

    # --- Apply task-type filter for charts / table ---
    df = df_base.copy()
    if task_types and "ActivityName" in df.columns:
        raw_types = []
        for g in task_types:
            raw_types.extend(_TASK_TYPE_GROUPS.get(g, [g]))
        df = df[df["ActivityName"].isin(raw_types)]

    is_completed = (df["CompletedDateTime"].notna()
                    if "CompletedDateTime" in df.columns
                    else pd.Series(False, index=df.index))

    # Pre-date-filtered copy for cumulative prior periods
    df_all_dates = tasks.copy()
    if physician and "AssignedMD" in df_all_dates.columns:
        df_all_dates = df_all_dates[df_all_dates["AssignedMD"] == physician]
    if diagnosis_cats and "DiagnosisCodes" in df_all_dates.columns and c2b:
        bs_set = set(diagnosis_cats)
        row_bs_all = df_all_dates["DiagnosisCodes"].apply(
            lambda s: get_categories_for_codes(s, c2b) if pd.notna(s) else set()
        )
        df_all_dates = df_all_dates[row_bs_all.apply(lambda cats: bool(cats & bs_set))]
    if task_types and "ActivityName" in df_all_dates.columns:
        raw_types = []
        for g in task_types:
            raw_types.extend(_TASK_TYPE_GROUPS.get(g, [g]))
        df_all_dates = df_all_dates[df_all_dates["ActivityName"].isin(raw_types)]
    # Apply status filter to cumulative data too
    if "CompletedDateTime" in df_all_dates.columns:
        is_comp_all = df_all_dates["CompletedDateTime"].notna()
        if status == "open":
            df_all_dates = df_all_dates[~is_comp_all]
        elif status == "done":
            df_all_dates = df_all_dates[is_comp_all]

    # --- Build chart data ---
    volume_store = _prepare_volume_data(df, volume_agg or "W", volume_slice or "", c2b)
    cumulative_store = _prepare_cumulative_data(
        df_all_dates, start, end, date_preset,
        mode=cumul_mode or "prior",
        period_type=cumul_period_type or "calendar",
        slice_by=cumul_slice or "task",
        c2b=c2b,
    )
    time_trend_store = _prepare_time_trend_data(df, is_completed, time_agg or "M", time_slice or "", c2b)
    sla_store = _prepare_sla_data(df, is_completed, sla_agg or "W", sla_slice or "", c2b)
    fig_hist = _build_histogram(df, is_completed, hist_slice or "", hist_type or "histogram", c2b)
    table = _build_table(df, is_completed)

    return (
        *group_cards,
        fig_hist, table,
        volume_store, cumulative_store, time_trend_store, sla_store, sparkline_data,
    )


# ---------------------------------------------------------------------------
# Data preparation functions
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


def _task_group_label(activity_name):
    """Map raw ActivityName to display group label."""
    return _TASK_TYPE_TO_GROUP.get(activity_name, activity_name)


def _slice_series(df, slice_by, period_col, all_periods, c2b, agg_func="count", value_col=None):
    """Generic slicer — returns list of {name, values, color} series dicts.

    agg_func: "count" for counting rows, "median" for median of value_col.
    """
    series = []

    def _make_series(sub, name, color, idx):
        if agg_func == "count":
            vals = sub.groupby(period_col).size().reindex(all_periods, fill_value=0)
            return {"name": name, "values": _trim_edges(vals.tolist()), "color": color}
        else:
            medians = sub.groupby(period_col)[value_col].median().reindex(all_periods)
            vals = [v if pd.notna(v) else None for v in medians.tolist()]
            return {"name": name, "values": vals, "color": color}

    if not slice_by:
        if agg_func == "count":
            vals = df.groupby(period_col).size().reindex(all_periods, fill_value=0)
            series.append({"name": "Total", "values": _trim_edges(vals.tolist()), "color": PRIMARY})
        else:
            medians = df.groupby(period_col)[value_col].median().reindex(all_periods)
            vals = [v if pd.notna(v) else None for v in medians.tolist()]
            series.append({"name": "Total", "values": vals, "color": PRIMARY})

    elif slice_by == "task" and "ActivityName" in df.columns:
        df = df.copy()
        df["_TaskGroup"] = df["ActivityName"].map(_TASK_TYPE_TO_GROUP).fillna(df["ActivityName"])
        for i, grp in enumerate(sorted(df["_TaskGroup"].dropna().unique())):
            sub = df[df["_TaskGroup"] == grp]
            series.append(_make_series(sub, grp, CHART_COLORWAY[i % len(CHART_COLORWAY)], i))

    elif slice_by == "physician" and "AssignedMD" in df.columns:
        for i, md in enumerate(sorted(df["AssignedMD"].dropna().unique())):
            sub = df[df["AssignedMD"] == md]
            name = md.split(",")[0] if "," in md else md
            series.append(_make_series(sub, name, CHART_COLORWAY[i % len(CHART_COLORWAY)], i))

    elif slice_by == "bodysite" and "DiagnosisCodes" in df.columns and c2b:
        df = df.copy()
        df["_bs"] = df["DiagnosisCodes"].apply(lambda v: primary_category(v, c2b))
        for i, bs in enumerate(sorted(df["_bs"].dropna().unique())):
            if bs == "Unknown":
                continue
            sub = df[df["_bs"] == bs]
            series.append(_make_series(sub, bs, CHART_COLORWAY[i % len(CHART_COLORWAY)], i))

    return series


def _prepare_volume_data(df, agg, slice_by="", c2b=None):
    """Prepare volume trend data for clientside rendering."""
    if df.empty or "StartDateTime" not in df.columns:
        return None

    df = df.copy()
    period_code = "Y" if agg == "Y" else agg
    df["period"] = df["StartDateTime"].dt.to_period(period_code).dt.to_timestamp()
    all_periods = sorted(df["period"].unique())
    dates = [d.isoformat() for d in all_periods]

    series = _slice_series(df, slice_by, "period", all_periods, c2b)

    return {
        "dates": dates,
        "series": series,
        "height": 350,
        "yTitle": "Tasks",
        "hideLegend": len(series) <= 1,
    }


def _prepare_cumulative_data(df_all, start, end, date_preset,
                              mode="prior", period_type="calendar",
                              slice_by="task", c2b=None):
    """Prepare cumulative task volume data for overlay chart."""
    if df_all.empty or "StartDateTime" not in df_all.columns:
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

    def _cumulative_for_window(df, w_start, w_end):
        mask = (df["StartDateTime"] >= w_start) & (df["StartDateTime"] <= w_end)
        sub = df.loc[mask]
        if sub.empty:
            return []
        daily = sub.groupby(sub["StartDateTime"].dt.normalize()).size()
        idx = pd.date_range(w_start.normalize(), w_end.normalize(), freq="D")
        daily = daily.reindex(idx, fill_value=0)
        return daily.cumsum().tolist()

    def _slice_totals_for_window(df, w_start, w_end, sb):
        mask = (df["StartDateTime"] >= w_start) & (df["StartDateTime"] <= w_end)
        sub = df.loc[mask]
        if sub.empty:
            return {}
        if sb == "task" and "ActivityName" in sub.columns:
            sub_c = sub.copy()
            sub_c["_TaskGroup"] = sub_c["ActivityName"].map(_TASK_TYPE_TO_GROUP).fillna(sub_c["ActivityName"])
            return sub_c.groupby("_TaskGroup").size().to_dict()
        elif sb == "physician" and "AssignedMD" in sub.columns:
            counts = sub.groupby("AssignedMD").size()
            return {(k.split(",")[0] if "," in k else k): v for k, v in counts.items()}
        elif sb == "bodysite" and "DiagnosisCodes" in sub.columns and c2b:
            sub_bs = sub.copy()
            sub_bs["_bs"] = sub_bs["DiagnosisCodes"].apply(lambda v: primary_category(v, c2b))
            sub_bs = sub_bs[sub_bs["_bs"] != "Unknown"]
            return sub_bs.groupby("_bs").size().to_dict() if not sub_bs.empty else {}
        return {}

    n_days = period_days
    start_norm = start.normalize()
    day_indices = list(range(n_days))

    tick_positions, tick_labels = _build_day_index_ticks(start_norm, n_days)

    current_vals = _cumulative_for_window(dff_all, start, end)
    data_min = dff_all["StartDateTime"].min() if not dff_all.empty else start

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
            "yTitle": "Cumulative Tasks",
        }

    # Slice mode
    mask = (dff_all["StartDateTime"] >= start) & (dff_all["StartDateTime"] <= end)
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

    if slice_by == "task" and "ActivityName" in dff_period.columns:
        dff_period = dff_period.copy()
        dff_period["_TaskGroup"] = dff_period["ActivityName"].map(_TASK_TYPE_TO_GROUP).fillna(dff_period["ActivityName"])
        for i, grp in enumerate(sorted(dff_period["_TaskGroup"].dropna().unique())):
            sub = dff_period[dff_period["_TaskGroup"] == grp]
            daily = sub.groupby(sub["StartDateTime"].dt.normalize()).size()
            daily = daily.reindex(dates_range, fill_value=0)
            series.append({
                "name": grp,
                "values": _trimmed_cumsum(daily),
                "color": CHART_COLORWAY[i % len(CHART_COLORWAY)],
            })

    elif slice_by == "physician" and "AssignedMD" in dff_period.columns:
        for i, md in enumerate(sorted(dff_period["AssignedMD"].dropna().unique())):
            sub = dff_period[dff_period["AssignedMD"] == md]
            daily = sub.groupby(sub["StartDateTime"].dt.normalize()).size()
            daily = daily.reindex(dates_range, fill_value=0)
            series.append({
                "name": md.split(",")[0] if "," in md else md,
                "values": _trimmed_cumsum(daily),
                "color": CHART_COLORWAY[i % len(CHART_COLORWAY)],
            })

    elif slice_by == "bodysite" and "DiagnosisCodes" in dff_period.columns and c2b:
        dff_period = dff_period.copy()
        dff_period["_bs"] = dff_period["DiagnosisCodes"].apply(lambda v: primary_category(v, c2b))
        dff_period = dff_period[dff_period["_bs"] != "Unknown"]
        for i, bs in enumerate(sorted(dff_period["_bs"].dropna().unique())):
            sub = dff_period[dff_period["_bs"] == bs]
            daily = sub.groupby(sub["StartDateTime"].dt.normalize()).size()
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
        "yTitle": "Cumulative Tasks",
    }


def _prepare_time_trend_data(df, is_completed, agg="M", slice_by="", c2b=None):
    """Prepare median time-to-complete trend data for clientside rendering."""
    if "MinutesToComplete" not in df.columns or "StartDateTime" not in df.columns:
        return None

    completed = df[is_completed].copy()
    completed["MinutesToComplete"] = pd.to_numeric(completed["MinutesToComplete"], errors="coerce")
    completed = completed.dropna(subset=["MinutesToComplete"])
    if completed.empty:
        return None

    period_code = "Y" if agg == "Y" else agg
    completed["period"] = completed["StartDateTime"].dt.to_period(period_code).dt.to_timestamp()
    all_periods = sorted(completed["period"].unique())
    dates = [d.isoformat() for d in all_periods]

    series = _slice_series(completed, slice_by, "period", all_periods, c2b,
                           agg_func="median", value_col="MinutesToComplete")

    if not series:
        return None

    return {
        "dates": dates,
        "series": series,
        "height": 320,
        "yTitle": "Median Minutes",
        "hideLegend": len(series) <= 1,
    }


def _prepare_sla_data(df, is_completed, agg="W", slice_by="", c2b=None):
    """Prepare SLA compliance trend data for clientside rendering."""
    if ("MinutesToComplete" not in df.columns or "MinutesAllowed" not in df.columns
            or "StartDateTime" not in df.columns):
        return None

    completed = df[is_completed].copy()
    completed["MinutesToComplete"] = pd.to_numeric(completed["MinutesToComplete"], errors="coerce")
    completed["MinutesAllowed"] = pd.to_numeric(completed["MinutesAllowed"], errors="coerce")
    completed = completed.dropna(subset=["MinutesToComplete", "MinutesAllowed"])
    if completed.empty:
        return None

    period_code = "Y" if agg == "Y" else agg
    completed["period"] = completed["StartDateTime"].dt.to_period(period_code).dt.to_timestamp()
    completed["on_time"] = completed["MinutesToComplete"] <= completed["MinutesAllowed"]
    all_periods = sorted(completed["period"].unique())
    dates = [d.isoformat() for d in all_periods]

    series = []

    def _sla_for_subset(sub, name, color):
        totals = sub.groupby("period").size().reindex(all_periods, fill_value=0)
        on_time = sub[sub["on_time"]].groupby("period").size().reindex(all_periods, fill_value=0)
        rates = ((on_time / totals) * 100).fillna(0)
        return {"name": name, "values": _trim_edges(rates.tolist()), "color": color}

    if not slice_by:
        series.append(_sla_for_subset(completed, "Overall", PRIMARY))

    elif slice_by == "task" and "ActivityName" in completed.columns:
        completed = completed.copy()
        completed["_TaskGroup"] = completed["ActivityName"].map(_TASK_TYPE_TO_GROUP).fillna(completed["ActivityName"])
        for i, grp in enumerate(sorted(completed["_TaskGroup"].dropna().unique())):
            sub = completed[completed["_TaskGroup"] == grp]
            series.append(_sla_for_subset(sub, grp, CHART_COLORWAY[i % len(CHART_COLORWAY)]))

    elif slice_by == "physician" and "AssignedMD" in completed.columns:
        for i, md in enumerate(sorted(completed["AssignedMD"].dropna().unique())):
            sub = completed[completed["AssignedMD"] == md]
            name = md.split(",")[0] if "," in md else md
            series.append(_sla_for_subset(sub, name, CHART_COLORWAY[i % len(CHART_COLORWAY)]))

    elif slice_by == "bodysite" and "DiagnosisCodes" in completed.columns and c2b:
        completed = completed.copy()
        completed["_bs"] = completed["DiagnosisCodes"].apply(lambda v: primary_category(v, c2b))
        for i, bs in enumerate(sorted(completed["_bs"].dropna().unique())):
            if bs == "Unknown":
                continue
            sub = completed[completed["_bs"] == bs]
            series.append(_sla_for_subset(sub, bs, CHART_COLORWAY[i % len(CHART_COLORWAY)]))

    return {
        "dates": dates,
        "series": series,
        "stacked": False,
        "height": 320,
        "yTitle": "SLA Compliance %",
        "hideLegend": len(series) <= 1,
    }


def _build_histogram(df, is_completed, slice_by="", hist_type="histogram", c2b=None):
    """Build histogram or density plot of time to complete, optionally sliced."""
    if "MinutesToComplete" not in df.columns:
        return empty_figure("No completion time data")

    completed = df[is_completed].copy()
    completed["MinutesToComplete"] = pd.to_numeric(completed["MinutesToComplete"], errors="coerce")
    completed = completed.dropna(subset=["MinutesToComplete"])
    if completed.empty:
        return empty_figure()

    fig = go.Figure()

    def _add_hist_traces(sub, name, color, show_legend=True):
        vals = sub["MinutesToComplete"].values
        if hist_type == "density":
            try:
                from scipy.stats import gaussian_kde
                kde = gaussian_kde(vals)
                x_range = np.linspace(max(0, vals.min() - 5), vals.max() + 5, 200)
                y_vals = kde(x_range)
                fig.add_trace(go.Scatter(
                    x=x_range, y=y_vals, mode="lines",
                    fill="tozeroy", name=name,
                    line=dict(color=color, width=2),
                    fillcolor=color.replace(")", ", 0.15)").replace("rgb", "rgba") if "rgb" in color else color,
                    showlegend=show_legend,
                ))
            except Exception:
                fig.add_trace(go.Histogram(
                    x=vals, nbinsx=30,
                    marker_color=color, opacity=0.7,
                    name=name, showlegend=show_legend,
                ))
        else:
            fig.add_trace(go.Histogram(
                x=vals, nbinsx=30,
                marker_color=color, opacity=0.7,
                name=name, showlegend=show_legend,
            ))

    if not slice_by:
        _add_hist_traces(completed, "All Tasks", PRIMARY, show_legend=False)
    elif slice_by == "task" and "ActivityName" in completed.columns:
        completed["_TaskGroup"] = completed["ActivityName"].map(_TASK_TYPE_TO_GROUP).fillna(completed["ActivityName"])
        for i, grp in enumerate(sorted(completed["_TaskGroup"].dropna().unique())):
            sub = completed[completed["_TaskGroup"] == grp]
            _add_hist_traces(sub, grp, CHART_COLORWAY[i % len(CHART_COLORWAY)])
    elif slice_by == "physician" and "AssignedMD" in completed.columns:
        for i, md in enumerate(sorted(completed["AssignedMD"].dropna().unique())):
            sub = completed[completed["AssignedMD"] == md]
            name = md.split(",")[0] if "," in md else md
            _add_hist_traces(sub, name, CHART_COLORWAY[i % len(CHART_COLORWAY)])
    elif slice_by == "bodysite" and "DiagnosisCodes" in completed.columns and c2b:
        completed["_bs"] = completed["DiagnosisCodes"].apply(lambda v: primary_category(v, c2b))
        for i, bs in enumerate(sorted(completed["_bs"].dropna().unique())):
            if bs == "Unknown":
                continue
            sub = completed[completed["_bs"] == bs]
            _add_hist_traces(sub, bs, CHART_COLORWAY[i % len(CHART_COLORWAY)])

    # SLA threshold line
    if "MinutesAllowed" in df.columns:
        sla = pd.to_numeric(df["MinutesAllowed"], errors="coerce").dropna()
        if len(sla) > 0:
            sla_val = sla.mode().iloc[0] if len(sla.mode()) > 0 else sla.median()
            fig.add_vline(x=sla_val, line_dash="dash", line_color=SEMANTIC_COLORS["error"],
                          annotation_text=f"SLA: {sla_val:.0f}m")

    # Annotation: n, median, IQR
    all_vals = completed["MinutesToComplete"]
    n_total = len(all_vals)
    median_val = all_vals.median()
    q1, q3 = all_vals.quantile(0.25), all_vals.quantile(0.75)
    annotation = f"n={n_total:,}  Median: {median_val:.0f}m  (IQR: {q1:.0f}–{q3:.0f}m)"

    apply_default_layout(fig, barmode="overlay", height=300)
    fig.update_layout(
        xaxis_title="Minutes",
        yaxis_title="Density" if hist_type == "density" else "Count",
        margin=dict(l=48, r=16, t=16, b=56),
    )
    fig.add_annotation(
        text=annotation,
        xref="paper", yref="paper",
        x=0.5, y=-0.18, showarrow=False,
        font=dict(size=11, color=NEUTRAL["text_muted"]),
    )

    # Median line
    fig.add_vline(x=median_val, line_dash="dash", line_color=PRIMARY,
                  annotation_text=f"Median: {median_val:.0f}m",
                  annotation_position="top left")

    return fig


def _build_table(df, is_completed):
    display_cols = []
    col_map = {
        "StartDateTime": "Start",
        "DueDateTime": "Due",
        "CompletedDateTime": "Completed",
        "ActivityName": "Type",
        "AssignedMD": "Assigned",
        "CompletingMD": "Completed By",
        "MinutesToComplete": "Minutes",
        "MinutesAllowed": "SLA (min)",
        "PatientFullName": "Patient",
    }

    for col, header in col_map.items():
        if col in df.columns:
            display_cols.append({"field": col, "headerName": header})

    if not display_cols:
        return dmc.Text("No task data available", c=NEUTRAL["text_muted"], ta="center", py="xl")

    table_df = df.head(200).copy()
    for c in table_df.select_dtypes(include=["datetime64"]).columns:
        table_df[c] = table_df[c].dt.strftime("%m/%d/%Y %H:%M")
    table_df = table_df.fillna("\u2014")

    return dag.AgGrid(
        id="tasks-detail-grid",
        rowData=table_df.to_dict("records"),
        columnDefs=display_cols,
        defaultColDef={"sortable": True, "filter": True, "resizable": True},
        dashGridOptions={"pagination": True, "paginationPageSize": 25, "domLayout": "autoHeight"},
        className="ag-theme-alpine",
    )


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

    pos, lbl = [], []
    prev_year = None
    for i in range(n_days):
        d = start_norm + pd.Timedelta(days=i)
        if d.year != prev_year:
            pos.append(i)
            lbl.append(str(d.year))
            prev_year = d.year
    candidates.append((pos, lbl))

    for p, l in candidates:
        if len(p) <= max_ticks:
            return p, l
    return candidates[-1]


# ---------------------------------------------------------------------------
# Clientside callbacks for charts with smoothing
# ---------------------------------------------------------------------------
clientside_callback(
    ClientsideFunction(namespace="census", function_name="smoothChartWithType"),
    Output("tasks-chart-volume", "figure"),
    Input("tasks-store-volume", "data"),
    Input("tasks-volume-settings-smooth", "value"),
    Input("tasks-volume-settings-type", "value"),
    State("tasks-chart-volume", "figure"),
)

clientside_callback(
    ClientsideFunction(namespace="cumulative", function_name="renderCumulative"),
    Output("tasks-chart-cumulative", "figure"),
    Input("tasks-store-cumulative", "data"),
    Input("tasks-cumulative-settings-smooth", "value"),
    Input("tasks-cumulative-settings-type", "value"),
    State("tasks-chart-cumulative", "figure"),
)

clientside_callback(
    ClientsideFunction(namespace="census", function_name="smoothChartWithType"),
    Output("tasks-chart-time-trend", "figure"),
    Input("tasks-store-time-trend", "data"),
    Input("tasks-time-trend-settings-smooth", "value"),
    Input("tasks-time-trend-settings-type", "value"),
    State("tasks-chart-time-trend", "figure"),
)

clientside_callback(
    ClientsideFunction(namespace="census", function_name="smoothChartWithType"),
    Output("tasks-chart-sla", "figure"),
    Input("tasks-store-sla", "data"),
    Input("tasks-sla-settings-smooth", "value"),
    Input("tasks-sla-settings-type", "value"),
    State("tasks-chart-sla", "figure"),
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
    Output("tasks-cumulative-slice", "style"),
    Output("tasks-cumulative-period-type", "style"),
    Input("tasks-cumulative-mode", "value"),
)

# ---------------------------------------------------------------------------
# Clientside callbacks for KPI sparklines
# ---------------------------------------------------------------------------
for _kg in _KPI_GROUPS:
    for _suffix in ("comp", "time"):
        _spark_id = f"tasks-spark-{_kg['key']}_{_suffix}"
        clientside_callback(
            ClientsideFunction(namespace="sparklines", function_name="updateFromStore"),
            Output(_spark_id, "figure"),
            Input("tasks-store-kpi-sparklines", "data"),
            Input(_spark_id, "id"),
            Input("tasks-smooth-slider", "value"),
        )

# ---------------------------------------------------------------------------
# Register settings toggle + PNG export callbacks for charts with settings
# ---------------------------------------------------------------------------
register_chart_callbacks([
    ("tasks-volume", "tasks-chart-volume"),
    ("tasks-cumulative", "tasks-chart-cumulative"),
    ("tasks-histogram", "tasks-chart-histogram"),
    ("tasks-time-trend", "tasks-chart-time-trend"),
    ("tasks-sla", "tasks-chart-sla"),
])

# ---------------------------------------------------------------------------
# Slice-by dim styling
# ---------------------------------------------------------------------------
_SLICE_CLASS_JS = """function(val) {
    return val ? "slice-group-active" : "slice-total-active";
}"""

for _sid in ["tasks-volume-slice", "tasks-hist-slice", "tasks-time-slice", "tasks-sla-slice"]:
    clientside_callback(
        _SLICE_CLASS_JS,
        Output(_sid, "className"),
        Input(_sid, "value"),
    )
