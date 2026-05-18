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
    CHART_COLORWAY, PRIMARY,
    SEMANTIC_COLORS, NEUTRAL,
    CHART_PAPER_HEIGHT_SM, PRIOR_PERIOD_COLORS,
    DEFAULT_COLUMN_DEFS, DEFAULT_GRID_OPTIONS, DEFAULT_GRID_STYLE, DEFAULT_GRID_CLASS,
    OUTLIER_CAPS, OUTLIER_SLIDER_MAX,
)
from components.chart_card import chart_card, register_chart_callbacks
from components.detail_table import detail_table
from components.kpi_card import kpi_card, kpi_placeholder
from components.phi import apply_phi_grid_rules
from utils.charts import apply_default_layout, empty_figure, color_for_index
from utils.tables import sanitize_for_grid
from utils.date_slider import (
    month_idx, idx_to_date, MAX_IDX, SLIDER_MARKS,
    preset_to_slider_val, preset_to_exact_dates,
)
from components.diagnosis_filter import diagnosis_accordion, register_diagnosis_callbacks
from components.outlier_panel import outlier_panel, register_outlier_callbacks
from utils.diagnosis_categories import (
    build_code_to_category,
    get_categories_for_codes,
    primary_category,
)

dash.register_page(__name__, path="/tasks", name="Tasks", order=5)

PAGE_ID = "tasks"

_DEFAULT_DATE_PRESET = "ytd" if pd.Timestamp.now().month > 1 else "3mo"

# Outlier caps per task group (days) — derived from shared config
_CAP_DRAW = OUTLIER_CAPS["sim_to_contour"]
_CAP_SRS = OUTLIER_CAPS["draw_srs"]
_CAP_CONTOUR = OUTLIER_CAPS["contour_to_plan"]
_CAP_ISODOSE = OUTLIER_CAPS["contour_to_plan"]
_CAP_REVIEW = OUTLIER_CAPS["plan_to_review"]


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
    "Create Isodose Plan": [
        "Create Isodose Plan",
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

# Workflow-ordered group names (clinical progression)
_TASK_GROUP_NAMES = list(_TASK_TYPE_GROUPS.keys())
_TASK_GROUP_ORDER = {name: i for i, name in enumerate(_TASK_GROUP_NAMES)}

# KPI card groups — each shows completed / open / median time
_KPI_GROUPS = [
    {"name": "Draw Volumes", "key": "draw", "task_groups": ["Draw Volumes"],
     "color": CHART_COLORWAY[0]},
    {"name": "Draw Volumes (SRS)", "key": "srs", "task_groups": ["Draw Volumes (SRS)"],
     "color": CHART_COLORWAY[4]},
    {"name": "Contour Review", "key": "contour", "task_groups": ["Contour Review"],
     "color": CHART_COLORWAY[1]},
    {"name": "Create Isodose Plan", "key": "isodose", "task_groups": ["Create Isodose Plan"],
     "color": CHART_COLORWAY[3]},
    {"name": "Review Plan", "key": "review", "task_groups": ["Review Plan"],
     "color": CHART_COLORWAY[2]},
]
for _kg in _KPI_GROUPS:
    _kg["raw_types"] = []
    for _g in _kg["task_groups"]:
        _kg["raw_types"].extend(_TASK_TYPE_GROUPS.get(_g, [_g]))

# Map task group display name → KPI card color (for consistent chart colors)
_TASK_GROUP_COLORS = {kg["name"]: kg["color"] for kg in _KPI_GROUPS}


# ---------------------------------------------------------------------------
# Business-hours computation (reuse workflow logic)
# ---------------------------------------------------------------------------

def _compute_business_minutes(df):
    """Replace MinutesToComplete with business-hours-only duration.

    Uses PriorStepBaseline (when the prior step completed) as the start
    timestamp if available, otherwise derives it from
    CompletedDateTime - MinutesToComplete (calendar minutes).

    Recalculates counting only 8am–5pm on business days.
    """
    if "CompletedDateTime" not in df.columns or "MinutesToComplete" not in df.columns:
        return df
    from pages.workflow import _business_days_between, _BH_PER_DAY
    df = df.copy()
    cal_mins = pd.to_numeric(df["MinutesToComplete"], errors="coerce")
    mask = df["CompletedDateTime"].notna() & cal_mins.notna()
    if not mask.any():
        return df
    # Use PriorStepBaseline directly when available; fall back to derived baseline
    if "PriorStepBaseline" in df.columns:
        baseline = df.loc[mask, "PriorStepBaseline"].copy()
        fallback = df.loc[mask, "CompletedDateTime"] - pd.to_timedelta(cal_mins[mask], unit="m")
        baseline = baseline.where(baseline.notna(), fallback)
    else:
        baseline = df.loc[mask, "CompletedDateTime"] - pd.to_timedelta(cal_mins[mask], unit="m")
    bdays = _business_days_between(baseline, df.loc[mask, "CompletedDateTime"])
    # _business_days_between returns float business-days (1.0 = 9 hours)
    df.loc[mask, "MinutesToComplete"] = bdays * _BH_PER_DAY * 60
    return df


# ---------------------------------------------------------------------------
# Physician resolution — CompletingMD → AssignedMD → TreatingPhysician
# Only accept names that appear in the Physician Schedule.
# ---------------------------------------------------------------------------

def _load_known_physicians():
    """Return set of physician names from Physician Schedule."""
    try:
        from data.loader import load_physician_schedule
        sched = load_physician_schedule()
        if "Physician" in sched.columns:
            return set(sched["Physician"].dropna().unique())
    except Exception:
        pass
    return set()


def _resolve_md(df, known_mds=None):
    """Add 'ResolvedMD' column: first MD-verified name from
    CompletingMD → AssignedMD → TreatingPhysician cascade.

    For 'Create Isodose Plan' tasks, uses CompletingUser (planner) instead.
    """
    if known_mds is None:
        known_mds = _load_known_physicians()

    candidates = [c for c in ("CompletingMD", "AssignedMD", "TreatingPhysician")
                  if c in df.columns]
    if not candidates:
        df["ResolvedMD"] = pd.NA
        return df

    def _pick(row):
        for col in candidates:
            val = row[col]
            if pd.notna(val) and val in known_mds:
                return val
        return pd.NA

    df = df.copy()
    df["ResolvedMD"] = df[candidates].apply(_pick, axis=1)

    # For Isodose Plan tasks, the completer is a planner, not an MD
    if "CompletingUser" in df.columns and "ActivityName" in df.columns:
        iso_mask = df["ActivityName"] == "Create Isodose Plan"
        user_vals = df.loc[iso_mask, "CompletingUser"]
        valid = user_vals.notna() & (user_vals.astype(str).str.strip() != "") & (user_vals.astype(str).str.upper() != "NA")
        df.loc[iso_mask & valid, "ResolvedMD"] = df.loc[iso_mask & valid, "CompletingUser"]

    return df


# ---------------------------------------------------------------------------
# Status helpers — use explicit TaskStatus + PriorStepComplete columns
# ---------------------------------------------------------------------------

def _task_is_completed(df):
    """Return boolean Series: True where task is completed.
    Prefers TaskStatus column; falls back to CompletedDateTime."""
    if "TaskStatus" in df.columns:
        return df["TaskStatus"] == "Completed"
    if "CompletedDateTime" in df.columns:
        return df["CompletedDateTime"].notna()
    return pd.Series(False, index=df.index)


def _prior_step_complete(df):
    """Return boolean Series: True where the prior workflow step is done.
    Tasks with PriorStepComplete=True are actionable."""
    if "PriorStepComplete" not in df.columns:
        # Fallback: assume all are actionable if column missing
        return pd.Series(True, index=df.index)
    return df["PriorStepComplete"].astype(str).str.strip().str.lower() == "true"


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
                        id="tasks-physician-wrap",
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
                                children=[
                                    dmc.ChipGroup(
                                        children=[],
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
                    # Planner dropdown (visible when Isodose tasks are in scope)
                    html.Div(
                        id="tasks-planner-wrap",
                        children=[
                            html.Div(
                                children=[
                                    dmc.Button(
                                        "Planner",
                                        id="tasks-planner-trigger",
                                        variant="default",
                                        size="sm",
                                        rightSection=DashIconify(icon="mdi:chevron-down", width=14),
                                    ),
                                    dmc.ActionIcon(
                                        DashIconify(icon="mdi:close-circle", width=18),
                                        id="tasks-planner-clear",
                                        variant="subtle",
                                        color="gray",
                                        size="sm",
                                        className="wf-filter-clear-btn",
                                    ),
                                ],
                                style={"position": "relative", "display": "inline-block"},
                            ),
                            dmc.Paper(
                                children=[
                                    dmc.ChipGroup(
                                        children=[],
                                        id="tasks-filter-planner",
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
                    diagnosis_accordion("tasks"),
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
                            {"value": "done", "label": "Completed"},
                        ],
                        value="all",
                        size="xs",
                    ),
                    dmc.Switch(
                        id="tasks-business-hours-switch",
                        label="Business Hours",
                        size="xs",
                        checked=False,
                    ),
                    # Outlier caps per task type
                    outlier_panel(PAGE_ID, transitions=[
                        ("Draw Volumes", _CAP_DRAW),
                        ("Draw Volumes (SRS)", _CAP_SRS),
                        ("Contour Review", _CAP_CONTOUR),
                        ("Create Isodose Plan", _CAP_ISODOSE),
                        ("Review Plan", _CAP_REVIEW),
                    ], slider_max=OUTLIER_SLIDER_MAX),
                    # Smoothing
                    dmc.Group(
                        children=[
                            dmc.Text("Smoothing", size="xs", c="#6B7280", fw=500),
                            dmc.Slider(
                                id="tasks-smooth-slider",
                                min=0,
                                max=1,
                                step=0.01,
                                value=0.55,
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
    left_children.append(trend if trend is not None else dmc.Text("\u00a0", size="xs"))
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
    right_children.append(trend_t if trend_t is not None else dmc.Text("\u00a0", size="xs"))
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
        className=f"tasks-kpi-paper tasks-kpi-paper-{key}",
        style={"borderLeft": f"4px solid {accent_color}" if accent_color else "none"},
    )


def _compute_group_metrics(df_base, df_prior_base, spark_base, raw_types,
                           spark_period="W", max_minutes=None, skip_sla=False):
    """Compute KPI metrics and sparklines for one task-type group."""
    gdf = (df_base[df_base["ActivityName"].isin(raw_types)]
           if "ActivityName" in df_base.columns else df_base)
    gdf_prior = (df_prior_base[df_prior_base["ActivityName"].isin(raw_types)]
                 if "ActivityName" in df_prior_base.columns else df_prior_base)

    is_comp = (_task_is_completed(gdf))
    is_comp_prior = (_task_is_completed(gdf_prior))

    completed = int(is_comp.sum())
    # "Open" = not completed AND prior step is done (actionable)
    open_count = int(((~is_comp) & _prior_step_complete(gdf)).sum())
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
        # Exclude zeros (instant sign-offs) and values above cap for time metrics
        mins = mins[(mins > 0)]
        if max_minutes:
            mins = mins[mins <= max_minutes]
        if len(mins) > 0:
            median_val = mins.median()
            if median_val >= 36 * 60:
                days = int(median_val // 1440)
                rem_hrs = int((median_val % 1440) // 60)
                median_min = f"{days}d {rem_hrs}h" if rem_hrs else f"{days}d"
            elif median_val >= 60:
                hrs = int(median_val // 60)
                rem = int(median_val % 60)
                median_min = f"{hrs}h {rem}m" if rem else f"{hrs}h"
            else:
                median_min = f"{median_val:.0f} min"

            if "MinutesToComplete" in gdf_prior.columns:
                prior_mins = pd.to_numeric(
                    gdf_prior.loc[is_comp_prior, "MinutesToComplete"], errors="coerce"
                ).dropna()
                prior_mins = prior_mins[prior_mins > 0]
                if max_minutes:
                    prior_mins = prior_mins[prior_mins <= max_minutes]
                if len(prior_mins) > 0:
                    prior_median = prior_mins.median()
                    pct_diff = (((median_val - prior_median) / prior_median) * 100
                                if prior_median else 0)
                    med_trend_dir = ("up" if pct_diff < 0
                                     else "down" if pct_diff > 0 else None)
                    med_trend_txt = f"{abs(pct_diff):.0f}% vs prior"

    pct_on_time_text = None
    if not skip_sla:
        comp_df = gdf[is_comp].copy()
        if "CompletedDateTime" in comp_df.columns and "DueDateTime" in comp_df.columns:
            valid = comp_df.dropna(subset=["CompletedDateTime", "DueDateTime"])
            if len(valid) > 0:
                pct_ot = (valid["CompletedDateTime"] <= valid["DueDateTime"]).mean() * 100
                pct_on_time_text = f"({pct_ot:.0f}% OT)"
        elif "MinutesToComplete" in comp_df.columns and "MinutesAllowed" in comp_df.columns:
            comp_df["MinutesToComplete"] = pd.to_numeric(comp_df["MinutesToComplete"], errors="coerce")
            comp_df["MinutesAllowed"] = pd.to_numeric(comp_df["MinutesAllowed"], errors="coerce")
            valid = comp_df.dropna(subset=["MinutesToComplete", "MinutesAllowed"])
            if len(valid) > 0:
                pct_ot = (valid["MinutesToComplete"] <= valid["MinutesAllowed"]).mean() * 100
                pct_on_time_text = f"({pct_ot:.0f}% OT)"

    spark_completed = spark_time = None
    spark_df = (spark_base[spark_base["ActivityName"].isin(raw_types)]
                if "ActivityName" in spark_base.columns else spark_base)

    if not spark_df.empty and "StartDateTime" in spark_df.columns:
        sdf = spark_df.copy()
        if spark_period == "D":
            sdf["_sp"] = sdf["StartDateTime"].dt.normalize()
        else:
            sdf["_sp"] = sdf["StartDateTime"].dt.to_period("W").dt.start_time
        spark_is_comp = _task_is_completed(sdf)

        comp_by_sp = sdf[spark_is_comp].groupby("_sp").size().reset_index(name="count")
        if len(comp_by_sp) >= 3:
            spark_completed = {
                "labels": [d.isoformat() for d in comp_by_sp["_sp"]],
                "values": comp_by_sp["count"].tolist(),
            }

        if "MinutesToComplete" in sdf.columns:
            sdf["MinutesToComplete"] = pd.to_numeric(sdf["MinutesToComplete"], errors="coerce")
            # Exclude zeros and values above cap for time sparklines
            time_mask = spark_is_comp & (sdf["MinutesToComplete"] > 0)
            if max_minutes:
                time_mask = time_mask & (sdf["MinutesToComplete"] <= max_minutes)
            time_by_sp = (sdf[time_mask]
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
                html.Div(
                    style={"position": "relative"},
                    children=[
                        _build_tasks_filter_bar(),
                        html.Div(
                            id="tasks-grid-filter-badge",
                            children=dmc.Tooltip(
                                label="Table column filters are active",
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

        # KPI row — one group card per task type (clickable to filter)
        dmc.SimpleGrid(cols={"base": 1, "sm": 2, "md": 5}, spacing="md", children=[
            html.Div(id="tasks-kpi-click-draw", n_clicks=0,
                     style={"cursor": "pointer"},
                     children=[html.Div(kpi_placeholder(), id="tasks-kpi-draw")]),
            html.Div(id="tasks-kpi-click-srs", n_clicks=0,
                     style={"cursor": "pointer"},
                     children=[html.Div(kpi_placeholder(), id="tasks-kpi-srs")]),
            html.Div(id="tasks-kpi-click-contour", n_clicks=0,
                     style={"cursor": "pointer"},
                     children=[html.Div(kpi_placeholder(), id="tasks-kpi-contour")]),
            html.Div(id="tasks-kpi-click-isodose", n_clicks=0,
                     style={"cursor": "pointer"},
                     children=[html.Div(kpi_placeholder(), id="tasks-kpi-isodose")]),
            html.Div(id="tasks-kpi-click-review", n_clicks=0,
                     style={"cursor": "pointer"},
                     children=[html.Div(kpi_placeholder(), id="tasks-kpi-review")]),
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
                        {"value": "line", "label": "Line"},
                        {"value": "area", "label": "Area"},
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
                                {"value": "planner", "label": "Planner"},
                                {"value": "bodysite", "label": "Dx"},
                            ],
                            value="task",
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
                                {"value": "planner", "label": "Planner"},
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

        # Row 2: Histogram + Actual vs Allowed
        dmc.Grid(gutter="md", children=[
            dmc.GridCol(
                chart_card(
                    "tasks-chart-histogram",
                    "Time Distribution",
                    settings_id="tasks-histogram",
                    chart_types=[],
                    show_smooth=False,
                    paper_padding="md",
                    extra_controls_left=[
                        dmc.SegmentedControl(
                            id="tasks-hist-slice",
                            data=[
                                {"value": "", "label": "Total"},
                                {"value": "task", "label": "Task"},
                                {"value": "physician", "label": "MD"},
                                {"value": "planner", "label": "Planner"},
                            ],
                            value="",
                            size="xs",
                        ),
                    ],
                    extra_controls=[
                        dmc.SegmentedControl(
                            id="tasks-histogram-settings-type",
                            data=[
                                {"value": "histogram", "label": "Histogram"},
                                {"value": "density", "label": "Density"},
                            ],
                            value="histogram",
                            size="xs",
                        ),
                    ],
                    extra_settings=[
                        html.Div(
                            id="tasks-hist-bw-wrap",
                            children=dmc.Stack(
                                gap=4,
                                children=[
                                    dmc.Text("Density Smoothing", size="xs", fw=500, c="#6B7280"),
                                    dmc.Slider(
                                        id="tasks-hist-bw",
                                        min=0.02,
                                        max=0.5,
                                        step=0.02,
                                        value=0.12,
                                        size="xs",
                                        showLabelOnHover=True,
                                        updatemode="drag",
                                    ),
                                ],
                            ),
                            style={"display": "none"},
                        ),
                    ],
                ),
                span={"base": 12, "md": 6},
            ),
            dmc.GridCol(
                chart_card(
                    "tasks-chart-time-compare",
                    "Actual vs Allowed Time",
                    settings_id="tasks-time-compare",
                    chart_types=[],
                    show_smooth=False,
                    paper_padding="md",
                    extra_controls_left=[
                        dmc.SegmentedControl(
                            id="tasks-time-compare-slice",
                            data=[
                                {"value": "", "label": "Total"},
                                {"value": "task", "label": "Task"},
                                {"value": "physician", "label": "MD"},
                                {"value": "planner", "label": "Planner"},
                                {"value": "bodysite", "label": "Dx"},
                            ],
                            value="",
                            size="xs",
                        ),
                    ],
                ),
                span={"base": 12, "md": 6},
            ),
        ]),

        # Row 3: Time Trend + On-Time Trend (half-width each)
        dmc.Grid(gutter="md", children=[
            dmc.GridCol(
                chart_card(
                    "tasks-chart-time-trend",
                    "Time to Complete Trend",
                    settings_id="tasks-time-trend",
                    chart_types=[
                        {"value": "area", "label": "Area"},
                        {"value": "line", "label": "Line"},
                        {"value": "bar", "label": "Bar"},
                    ],
                    show_smooth=True,
                    smooth_max=12,
                    smooth_default=2,
                    paper_padding="md",
                    extra_controls_left=[
                        dmc.SegmentedControl(
                            id="tasks-time-slice",
                            data=[
                                {"value": "", "label": "Total"},
                                {"value": "task", "label": "Task"},
                                {"value": "physician", "label": "MD"},
                                {"value": "planner", "label": "Planner"},
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
                            value="W",
                            size="xs",
                        ),
                    ],
                ),
                span={"base": 12, "md": 6},
            ),
            dmc.GridCol(
                chart_card(
                    "tasks-chart-sla",
                    "On-Time Trend",
                    settings_id="tasks-sla",
                    chart_types=[
                        {"value": "area", "label": "Area"},
                        {"value": "line", "label": "Line"},
                        {"value": "bar", "label": "Bar"},
                    ],
                    show_smooth=True,
                    smooth_max=12,
                    smooth_default=0,
                    paper_padding="md",
                    extra_controls_left=[
                        dmc.SegmentedControl(
                            id="tasks-sla-slice",
                            data=[
                                {"value": "", "label": "Total"},
                                {"value": "task", "label": "Task"},
                                {"value": "physician", "label": "MD"},
                                {"value": "planner", "label": "Planner"},
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
                span={"base": 12, "md": 6},
            ),
        ]),

        # Detail table
        detail_table(
            "tasks-detail-grid",
            title="Task Detail",
            export_id="tasks-table-export",
            accordion_id="tasks-detail-accordion",
            extra_controls=[
                dmc.Button(
                    "Clear Filters",
                    id="tasks-table-clear-filters",
                    size="compact-xs",
                    variant="light",
                    color="red",
                    leftSection=DashIconify(icon="mdi:filter-remove", width=14),
                    style={"display": "none"},
                ),
            ],
        ),

        # Stores for clientside callbacks
        dcc.Store(id="tasks-store-histogram"),
        dcc.Store(id="tasks-store-time-compare"),
        dcc.Store(id="tasks-store-volume"),
        dcc.Store(id="tasks-store-cumulative"),
        dcc.Store(id="tasks-store-time-trend"),
        dcc.Store(id="tasks-store-sla"),
        dcc.Store(id="tasks-store-kpi-sparklines"),

        dcc.Interval(id="tasks-interval", interval=300_000, n_intervals=0, max_intervals=0),  # fires once on mount; no background refresh (daily data + global refresh button)
    ],
)

# Register reusable diagnosis accordion callbacks
register_diagnosis_callbacks("tasks")


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
        s, e = preset_to_exact_dates(preset)
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
        """function(val) {
            if (!val) return "Planner";
            return val.split(", ")[0];
        }""",
        Output("tasks-planner-trigger", "children"),
        Input("tasks-filter-planner", "value"),
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
        """function(val) { return val ? {"display": "inline-flex"} : {"display": "none"}; }""",
        Output("tasks-planner-clear", "style"),
        Input("tasks-filter-planner", "value"),
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
        """function(n) { return null; }""",
        Output("tasks-filter-planner", "value", allow_duplicate=True),
        Input("tasks-planner-clear", "n_clicks"),
        prevent_initial_call=True,
    )
    clientside_callback(
        """function(n) { return []; }""",
        Output("tasks-filter-type", "value", allow_duplicate=True),
        Input("tasks-tasktype-clear", "n_clicks"),
        prevent_initial_call=True,
    )

    # --- Physician/Planner dropdown visibility based on task type filter ---
    # No filter: both visible. Isodose only: planner only. Non-Isodose only: physician only.
    _WRAP_VISIBLE = {"position": "relative", "display": "inline-block"}
    _WRAP_HIDDEN = {"position": "relative", "display": "none"}
    clientside_callback(
        """function(taskTypes) {
            var vis = {"position": "relative", "display": "inline-block"};
            var hid = {"position": "relative", "display": "none"};
            var none = !taskTypes || taskTypes.length === 0;
            var hasIso = none || (taskTypes.indexOf("Create Isodose Plan") >= 0);
            var isoOnly = taskTypes && taskTypes.length === 1 && taskTypes[0] === "Create Isodose Plan";
            var phys = isoOnly ? hid : vis;
            var plan = hasIso ? vis : hid;
            var clearPhys = isoOnly ? null : window.dash_clientside.no_update;
            var clearPlan = hasIso ? window.dash_clientside.no_update : null;
            return [phys, plan, clearPhys, clearPlan];
        }""",
        Output("tasks-physician-wrap", "style"),
        Output("tasks-planner-wrap", "style"),
        Output("tasks-filter-physician", "value", allow_duplicate=True),
        Output("tasks-filter-planner", "value", allow_duplicate=True),
        Input("tasks-filter-type", "value"),
        prevent_initial_call=True,
    )


# Register filter callbacks
_register_tasks_filter_callbacks()

# Register outlier panel callbacks
register_outlier_callbacks(PAGE_ID, n_transitions=5,
                           defaults=[_CAP_DRAW, _CAP_SRS, _CAP_CONTOUR, _CAP_ISODOSE, _CAP_REVIEW])

# KPI card click → toggle task type filter
clientside_callback(
    """function(n1, n2, n3, n4, n5, currentTypes) {
        const ctx = dash_clientside.callback_context;
        if (!ctx.triggered.length) return dash_clientside.no_update;
        const tid = ctx.triggered_id;
        const map = {
            "tasks-kpi-click-draw": "Draw Volumes",
            "tasks-kpi-click-srs": "Draw Volumes (SRS)",
            "tasks-kpi-click-contour": "Contour Review",
            "tasks-kpi-click-isodose": "Create Isodose Plan",
            "tasks-kpi-click-review": "Review Plan"
        };
        const group = map[tid];
        if (!group) return dash_clientside.no_update;
        const current = currentTypes || [];
        if (current.length === 1 && current[0] === group) {
            return [];
        }
        return [group];
    }""",
    Output("tasks-filter-type", "value", allow_duplicate=True),
    Input("tasks-kpi-click-draw", "n_clicks"),
    Input("tasks-kpi-click-srs", "n_clicks"),
    Input("tasks-kpi-click-contour", "n_clicks"),
    Input("tasks-kpi-click-isodose", "n_clicks"),
    Input("tasks-kpi-click-review", "n_clicks"),
    State("tasks-filter-type", "value"),
    prevent_initial_call=True,
)

# Instant KPI card highlight — outputs className on static wrapper divs
clientside_callback(
    """function(taskTypes) {
        const map = {
            "Draw Volumes": "draw",
            "Draw Volumes (SRS)": "srs",
            "Contour Review": "contour",
            "Create Isodose Plan": "isodose",
            "Review Plan": "review"
        };
        const keys = ["draw", "srs", "contour", "isodose", "review"];
        const selected = new Set();
        if (taskTypes && taskTypes.length > 0) {
            taskTypes.forEach(function(t) { if (map[t]) selected.add(map[t]); });
        }
        return keys.map(function(k) {
            return selected.has(k) ? "tasks-kpi-click tasks-kpi-active" : "tasks-kpi-click";
        });
    }""",
    Output("tasks-kpi-click-draw", "className"),
    Output("tasks-kpi-click-srs", "className"),
    Output("tasks-kpi-click-contour", "className"),
    Output("tasks-kpi-click-isodose", "className"),
    Output("tasks-kpi-click-review", "className"),
    Input("tasks-filter-type", "value"),
)


# ---------------------------------------------------------------------------
# Dynamic physician chip population
# ---------------------------------------------------------------------------
@callback(
    Output("tasks-filter-physician", "children"),
    Input("tasks-interval", "n_intervals"),
    Input("tasks-date-slider", "value"),
    Input("tasks-filter-type", "value"),
    Input("tasks-diag-store", "data"),
    Input("tasks-diag-mode", "data"),
    Input("tasks-filter-status", "value"),
)
def _populate_physician_chips(_n, slider_val, task_types, diagnosis_cats, diag_mode, status):
    """Populate physician filter with MDs that appear in the filtered data."""
    from data.loader import load_tasks, load_diagnosis

    try:
        tasks = load_tasks()
    except Exception:
        return []

    known_mds = _load_known_physicians()
    tasks = _resolve_md(tasks, known_mds)

    # Apply non-physician filters — strict date range for chip population
    # (no open_eligible broadening, avoids showing retired physicians)
    start, end = _get_date_range(slider_val)
    if "StartDateTime" in tasks.columns:
        tasks = tasks[(tasks["StartDateTime"] >= start) & (tasks["StartDateTime"] <= end)]

    if task_types and "ActivityName" in tasks.columns:
        raw_types = []
        for g in task_types:
            raw_types.extend(_TASK_TYPE_GROUPS.get(g, [g]))
        tasks = tasks[tasks["ActivityName"].isin(raw_types)]

    if diagnosis_cats and "DiagnosisCodes" in tasks.columns:
        try:
            diag_df = load_diagnosis()
        except Exception:
            diag_df = None
        c2b = build_code_to_category(diag_df)
        if c2b:
            from utils.diagnosis_categories import filter_by_diagnosis
            tasks = filter_by_diagnosis(tasks, diagnosis_cats, c2b, mode=diag_mode or "primary")

    is_comp = _task_is_completed(tasks)
    if status == "open":
        tasks = tasks[(~is_comp) & _prior_step_complete(tasks)]
    elif status == "done":
        tasks = tasks[is_comp]

    # Get unique resolved MDs in filtered data — always MDs only
    from components.filter_bar import physician_short_name
    mds = sorted(tasks["ResolvedMD"].dropna().unique())
    mds = [m for m in mds if m in known_mds]

    return [
        dmc.Chip(
            physician_short_name(md),
            value=md,
            size="xs",
            variant="filled",
        )
        for md in mds
    ]


# ---------------------------------------------------------------------------
# Dynamic planner chip population
# ---------------------------------------------------------------------------
@callback(
    Output("tasks-filter-planner", "children"),
    Input("tasks-interval", "n_intervals"),
    Input("tasks-date-slider", "value"),
    Input("tasks-filter-type", "value"),
    Input("tasks-diag-store", "data"),
    Input("tasks-diag-mode", "data"),
    Input("tasks-filter-status", "value"),
)
def _populate_planner_chips(_n, slider_val, task_types, diagnosis_cats, diag_mode, status):
    """Populate planner filter with CompletingUser names from Isodose tasks."""
    from data.loader import load_tasks, load_diagnosis

    try:
        tasks = load_tasks()
    except Exception:
        return []

    known_mds = _load_known_physicians()

    # Apply date filter
    start, end = _get_date_range(slider_val)
    if "StartDateTime" in tasks.columns:
        tasks = tasks[(tasks["StartDateTime"] >= start) & (tasks["StartDateTime"] <= end)]

    # Apply diagnosis filter
    if diagnosis_cats and "DiagnosisCodes" in tasks.columns:
        try:
            diag_df = load_diagnosis()
        except Exception:
            diag_df = None
        c2b = build_code_to_category(diag_df)
        if c2b:
            from utils.diagnosis_categories import filter_by_diagnosis
            tasks = filter_by_diagnosis(tasks, diagnosis_cats, c2b, mode=diag_mode or "primary")

    is_comp = _task_is_completed(tasks)
    if status == "open":
        tasks = tasks[(~is_comp) & _prior_step_complete(tasks)]
    elif status == "done":
        tasks = tasks[is_comp]

    # Get planners: CompletingUser from Isodose tasks, excluding MDs
    if "CompletingUser" not in tasks.columns or "ActivityName" not in tasks.columns:
        return []
    iso_types = _TASK_TYPE_GROUPS.get("Create Isodose Plan", [])
    iso_tasks = tasks[tasks["ActivityName"].isin(iso_types)]
    planners = iso_tasks["CompletingUser"].dropna().unique()
    planners = sorted([p for p in planners
                       if p.strip() and p.upper() != "NA" and p not in known_mds])

    return [
        dmc.Chip(p, value=p, size="xs", variant="filled")
        for p in planners
    ]


# ---------------------------------------------------------------------------
# Shared filter helper — load data, apply filters, return dict or None
# ---------------------------------------------------------------------------

def _load_and_filter_tasks(slider_val, physician, planner, task_types,
                           diagnosis_cats,
                           diag_mode, status, use_business_hours,
                           outlier_enabled, cap0, cap1, cap2, cap3, cap4,
                           date_preset):
    """Load tasks data, apply all dimension/date/status filters.

    Returns a dict with shared dataframes and metadata, or None if empty.
    """
    from data.loader import load_tasks, load_diagnosis

    try:
        tasks = load_tasks().copy()
    except Exception:
        return None
    if tasks.empty:
        return None

    # --- Recalculate elapsed time from PriorStepBaseline when available ---
    if ("PriorStepBaseline" in tasks.columns and "CompletedDateTime" in tasks.columns
            and "MinutesToComplete" in tasks.columns):
        _bl_mask = tasks["PriorStepBaseline"].notna() & tasks["CompletedDateTime"].notna()
        if _bl_mask.any():
            tasks.loc[_bl_mask, "MinutesToComplete"] = (
                (tasks.loc[_bl_mask, "CompletedDateTime"] - tasks.loc[_bl_mask, "PriorStepBaseline"])
                .dt.total_seconds() / 60
            )

    # --- Clean MinutesToComplete: exclude negatives always ---
    if "MinutesToComplete" in tasks.columns:
        mtc = pd.to_numeric(tasks["MinutesToComplete"], errors="coerce")
        tasks = tasks[mtc.fillna(0) >= 0]

    # Recalculate MinutesToComplete using business hours only
    if use_business_hours:
        tasks = _compute_business_minutes(tasks)

    # Resolve physician: CompletingMD → AssignedMD → TreatingPhysician
    known_mds = _load_known_physicians()
    tasks = _resolve_md(tasks, known_mds)

    start, end = _get_date_range(slider_val)
    prior_start = start - (end - start)

    # Per-task-group outlier caps (days → minutes)
    if outlier_enabled:
        _cap_minutes = {
            "Draw Volumes": (cap0 or _CAP_DRAW) * 24 * 60,
            "Draw Volumes (SRS)": (cap1 or _CAP_SRS) * 24 * 60,
            "Contour Review": (cap2 or _CAP_CONTOUR) * 24 * 60,
            "Create Isodose Plan": (cap3 or _CAP_ISODOSE) * 24 * 60,
            "Review Plan": (cap4 or _CAP_REVIEW) * 24 * 60,
        }
    else:
        _cap_minutes = {}  # no capping

    # Adaptive sparkline granularity
    range_months = (end.year - start.year) * 12 + (end.month - start.month) + 1
    _spark_period = "D" if range_months <= 3 else "W"

    # --- Base filtering (everything except task type) ---
    df_base = tasks.copy()
    if "StartDateTime" in df_base.columns:
        in_range = (df_base["StartDateTime"] >= start) & (df_base["StartDateTime"] <= end)
        is_open = ~_task_is_completed(df_base)
        open_eligible = is_open & (df_base["StartDateTime"].isna() | (df_base["StartDateTime"] <= end))
        df_base = df_base[in_range | open_eligible]
    if physician and "ResolvedMD" in df_base.columns:
        df_base = df_base[df_base["ResolvedMD"] == physician]
    if planner and "CompletingUser" in df_base.columns:
        df_base = df_base[df_base["CompletingUser"] == planner]

    try:
        diag_df = load_diagnosis()
    except Exception:
        diag_df = None
    c2b = build_code_to_category(diag_df)

    if diagnosis_cats:
        from utils.diagnosis_categories import filter_by_diagnosis
        df_base = filter_by_diagnosis(df_base, diagnosis_cats, c2b, mode=diag_mode or "primary")

    # Status filter — use TaskStatus column
    is_completed_base = _task_is_completed(df_base)
    if status == "open":
        df_base = df_base[(~is_completed_base) & _prior_step_complete(df_base)]
    elif status == "done":
        df_base = df_base[is_completed_base]

    # --- Prior period (no status filter, no task-type filter) ---
    df_prior_base = tasks.copy()
    if "StartDateTime" in df_prior_base.columns:
        df_prior_base = df_prior_base[
            (df_prior_base["StartDateTime"] >= prior_start)
            & (df_prior_base["StartDateTime"] < start)
        ]
    if physician and "ResolvedMD" in df_prior_base.columns:
        df_prior_base = df_prior_base[df_prior_base["ResolvedMD"] == physician]
    if planner and "CompletingUser" in df_prior_base.columns:
        df_prior_base = df_prior_base[df_prior_base["CompletingUser"] == planner]
    if diagnosis_cats:
        from utils.diagnosis_categories import filter_by_diagnosis
        df_prior_base = filter_by_diagnosis(df_prior_base, diagnosis_cats, c2b, mode=diag_mode or "primary")

    # --- Apply task-type filter for chart/table frames ---
    df = df_base.copy()
    if task_types and "ActivityName" in df.columns:
        raw_types = []
        for g in task_types:
            raw_types.extend(_TASK_TYPE_GROUPS.get(g, [g]))
        df = df[df["ActivityName"].isin(raw_types)]

    is_completed = _task_is_completed(df)

    # Strictly date-ranged frame for trend charts (no old open tasks)
    if "StartDateTime" in df.columns:
        df_in_range = df[(df["StartDateTime"] >= start) & (df["StartDateTime"] <= end)]
    else:
        df_in_range = df
    is_completed_in_range = _task_is_completed(df_in_range)

    # Time-valid mask: completed + non-zero + within per-group cap
    _mtc = (pd.to_numeric(df["MinutesToComplete"], errors="coerce")
            if "MinutesToComplete" in df.columns else pd.Series(dtype=float))
    if _cap_minutes and "ActivityName" in df.columns:
        _row_cap = df["ActivityName"].map(_TASK_TYPE_TO_GROUP).map(_cap_minutes)
        is_time_valid = is_completed & (_mtc > 0) & (_mtc <= _row_cap.fillna(np.inf))
    else:
        is_time_valid = is_completed & (_mtc > 0)

    _mtc_ir = (pd.to_numeric(df_in_range["MinutesToComplete"], errors="coerce")
               if "MinutesToComplete" in df_in_range.columns else pd.Series(dtype=float))
    if _cap_minutes and "ActivityName" in df_in_range.columns:
        _row_cap_ir = df_in_range["ActivityName"].map(_TASK_TYPE_TO_GROUP).map(_cap_minutes)
        is_time_valid_in_range = is_completed_in_range & (_mtc_ir > 0) & (_mtc_ir <= _row_cap_ir.fillna(np.inf))
    else:
        is_time_valid_in_range = is_completed_in_range & (_mtc_ir > 0)

    # Pre-date-filtered copy for cumulative prior periods
    df_all_dates = tasks.copy()
    if physician and "ResolvedMD" in df_all_dates.columns:
        df_all_dates = df_all_dates[df_all_dates["ResolvedMD"] == physician]
    if planner and "CompletingUser" in df_all_dates.columns:
        df_all_dates = df_all_dates[df_all_dates["CompletingUser"] == planner]
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
    is_comp_all = _task_is_completed(df_all_dates)
    if status == "open":
        df_all_dates = df_all_dates[(~is_comp_all) & _prior_step_complete(df_all_dates)]
    elif status == "done":
        df_all_dates = df_all_dates[is_comp_all]

    # Accent color: use KPI card color when exactly one task type selected
    _kpi_color_map = {kg["name"]: kg["color"] for kg in _KPI_GROUPS}
    _accent = (_kpi_color_map.get(task_types[0])
               if task_types and len(task_types) == 1 else None)

    return {
        "tasks": tasks,
        "df_base": df_base,
        "df_prior_base": df_prior_base,
        "df": df,
        "df_in_range": df_in_range,
        "df_all_dates": df_all_dates,
        "is_completed": is_completed,
        "is_completed_in_range": is_completed_in_range,
        "is_time_valid": is_time_valid,
        "is_time_valid_in_range": is_time_valid_in_range,
        "c2b": c2b,
        "start": start,
        "end": end,
        "date_preset": date_preset,
        "accent": _accent,
        "cap_minutes": _cap_minutes,
        "spark_period": _spark_period,
    }


# Common filter inputs shared by all split callbacks
_TASKS_FILTER_INPUTS = [
    Input("tasks-interval", "n_intervals"),
    Input("tasks-filter-date-preset", "value"),
    Input("tasks-filter-physician", "value"),
    Input("tasks-filter-type", "value"),
    Input("tasks-diag-store", "data"),
    Input("tasks-diag-mode", "data"),
    Input("tasks-filter-status", "value"),
    Input("tasks-date-slider", "value"),
    Input("tasks-business-hours-switch", "checked"),
    Input(f"{PAGE_ID}-outlier-enabled", "data"),
    Input(f"{PAGE_ID}-outlier-cap-0", "value"),
    Input(f"{PAGE_ID}-outlier-cap-1", "value"),
    Input(f"{PAGE_ID}-outlier-cap-2", "value"),
    Input(f"{PAGE_ID}-outlier-cap-3", "value"),
    Input(f"{PAGE_ID}-outlier-cap-4", "value"),
    Input("tasks-filter-planner", "value"),
]

_N_FILTER_INPUTS = len(_TASKS_FILTER_INPUTS)


def _unpack_tasks_filter_args(args):
    """Unpack the common filter args into kwargs for _load_and_filter_tasks."""
    (_n, date_preset, physician, task_types, diagnosis_cats, diag_mode,
     status, slider_val, use_business_hours,
     outlier_enabled, cap0, cap1, cap2, cap3, cap4, planner) = args[:_N_FILTER_INPUTS]
    return dict(
        slider_val=slider_val, physician=physician, planner=planner,
        task_types=task_types,
        diagnosis_cats=diagnosis_cats, diag_mode=diag_mode, status=status,
        use_business_hours=use_business_hours,
        outlier_enabled=outlier_enabled, cap0=cap0, cap1=cap1,
        cap2=cap2, cap3=cap3, cap4=cap4,
        date_preset=date_preset,
    )


# ---------------------------------------------------------------------------
# Callback 1: KPIs + Sparklines + Detail Table
# ---------------------------------------------------------------------------

@callback(
    Output("tasks-kpi-draw", "children"),
    Output("tasks-kpi-srs", "children"),
    Output("tasks-kpi-contour", "children"),
    Output("tasks-kpi-isodose", "children"),
    Output("tasks-kpi-review", "children"),
    Output("tasks-detail-grid", "rowData"),
    Output("tasks-detail-grid", "columnDefs"),
    Output("tasks-store-kpi-sparklines", "data"),
    *_TASKS_FILTER_INPUTS,
)
def _update_tasks_kpis(*args):
    ctx = _unpack_tasks_filter_args(args)
    data = _load_and_filter_tasks(**ctx)

    na_card = dmc.Text("\u2014", ta="center")
    if data is None:
        return na_card, na_card, na_card, na_card, na_card, [], [], {}

    df_base = data["df_base"]
    df_prior_base = data["df_prior_base"]
    df = data["df"]
    is_completed = data["is_completed"]
    _cap_minutes = data["cap_minutes"]
    _spark_period = data["spark_period"]

    # Build KPI group cards + sparkline store data
    group_cards = []
    sparkline_data = {}
    for kg in _KPI_GROUPS:
        group_cap = _cap_minutes.get(kg["name"]) if _cap_minutes else None
        metrics = _compute_group_metrics(
            df_base, df_prior_base, df_base, kg["raw_types"],
            spark_period=_spark_period,
            max_minutes=group_cap,
            skip_sla=(kg["key"] == "isodose"),
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

    row_data, col_defs = _build_table(df, is_completed)

    return (*group_cards, row_data, col_defs, sparkline_data)


# ---------------------------------------------------------------------------
# Callback 2: Volume Store
# ---------------------------------------------------------------------------

@callback(
    Output("tasks-store-volume", "data"),
    *_TASKS_FILTER_INPUTS,
    Input("tasks-volume-agg", "value"),
    Input("tasks-volume-slice", "value"),
    running=[(Output("tasks-chart-volume-loading", "visible"), True, False)],
)
def _update_tasks_volume(*args):
    ctx = _unpack_tasks_filter_args(args)
    agg, volume_slice = args[_N_FILTER_INPUTS], args[_N_FILTER_INPUTS + 1]
    data = _load_and_filter_tasks(**ctx)
    if data is None:
        return None
    return _prepare_volume_data(
        data["df_in_range"], agg or "W", volume_slice or "",
        data["c2b"], accent_color=data["accent"],
    )


# ---------------------------------------------------------------------------
# Callback 3: Cumulative Store
# ---------------------------------------------------------------------------

@callback(
    Output("tasks-store-cumulative", "data"),
    *_TASKS_FILTER_INPUTS,
    Input("tasks-cumulative-mode", "value"),
    Input("tasks-cumulative-period-type", "value"),
    Input("tasks-cumulative-slice", "value"),
    running=[(Output("tasks-chart-cumulative-loading", "visible"), True, False)],
)
def _update_tasks_cumulative(*args):
    ctx = _unpack_tasks_filter_args(args)
    cumul_mode, cumul_period_type, cumul_slice = args[_N_FILTER_INPUTS], args[_N_FILTER_INPUTS + 1], args[_N_FILTER_INPUTS + 2]
    data = _load_and_filter_tasks(**ctx)
    if data is None:
        return None
    return _prepare_cumulative_data(
        data["df_all_dates"], data["start"], data["end"], data["date_preset"],
        mode=cumul_mode or "prior",
        period_type=cumul_period_type or "calendar",
        slice_by=cumul_slice or "task",
        c2b=data["c2b"],
        accent_color=data["accent"],
        max_prior=10,
    )


# ---------------------------------------------------------------------------
# Callback 4: Time Trend Store
# ---------------------------------------------------------------------------

@callback(
    Output("tasks-store-time-trend", "data"),
    *_TASKS_FILTER_INPUTS,
    Input("tasks-time-agg", "value"),
    Input("tasks-time-slice", "value"),
    running=[(Output("tasks-chart-time-trend-loading", "visible"), True, False)],
)
def _update_tasks_time_trend(*args):
    ctx = _unpack_tasks_filter_args(args)
    time_agg, time_slice = args[_N_FILTER_INPUTS], args[_N_FILTER_INPUTS + 1]
    data = _load_and_filter_tasks(**ctx)
    if data is None:
        return None
    return _prepare_time_trend_data(
        data["df_in_range"], data["is_time_valid_in_range"],
        time_agg or "M", time_slice or "",
        data["c2b"], accent_color=data["accent"],
    )


# ---------------------------------------------------------------------------
# Callback 5: SLA Store
# ---------------------------------------------------------------------------

@callback(
    Output("tasks-store-sla", "data"),
    *_TASKS_FILTER_INPUTS,
    Input("tasks-sla-agg", "value"),
    Input("tasks-sla-slice", "value"),
    running=[(Output("tasks-chart-sla-loading", "visible"), True, False)],
)
def _update_tasks_sla(*args):
    ctx = _unpack_tasks_filter_args(args)
    sla_agg, sla_slice = args[_N_FILTER_INPUTS], args[_N_FILTER_INPUTS + 1]
    data = _load_and_filter_tasks(**ctx)
    if data is None:
        return None
    return _prepare_sla_data(
        data["df_in_range"], data["is_completed_in_range"],
        sla_agg or "W", sla_slice or "",
        data["c2b"], accent_color=data["accent"],
    )


# ---------------------------------------------------------------------------
# Callback 6: Histogram (server-rendered figure)
# ---------------------------------------------------------------------------

@callback(
    Output("tasks-store-histogram", "data"),
    *_TASKS_FILTER_INPUTS,
    Input("tasks-hist-slice", "value"),
    running=[(Output("tasks-chart-histogram-loading", "visible"), True, False)],
)
def _update_tasks_histogram(*args):
    ctx = _unpack_tasks_filter_args(args)
    hist_slice = args[_N_FILTER_INPUTS]
    data = _load_and_filter_tasks(**ctx)
    if data is None:
        return None
    return _prepare_histogram_data(
        data["df_in_range"], data["is_time_valid_in_range"],
        hist_slice or "", data["c2b"], accent_color=data["accent"],
    )


# ---------------------------------------------------------------------------
# Callback 7: Actual vs Allowed Time Comparison
# ---------------------------------------------------------------------------

@callback(
    Output("tasks-store-time-compare", "data"),
    *_TASKS_FILTER_INPUTS,
    Input("tasks-time-compare-slice", "value"),
    running=[(Output("tasks-chart-time-compare-loading", "visible"), True, False)],
)
def _update_tasks_time_compare(*args):
    ctx = _unpack_tasks_filter_args(args)
    tc_slice = args[_N_FILTER_INPUTS]
    data = _load_and_filter_tasks(**ctx)
    if data is None:
        return None
    return _prepare_time_compare_data(
        data["df"], data["is_time_valid"],
        tc_slice or "", data["c2b"], accent_color=data["accent"],
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


def _slice_series(df, slice_by, period_col, all_periods, c2b, agg_func="count", value_col=None, accent_color=None):
    """Generic slicer — returns list of {name, values, color} series dicts.

    agg_func: "count" for counting rows, "median" for median of value_col.
    accent_color: override for single-trace "Total" color (e.g. selected KPI card color).
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

    _total_color = accent_color or PRIMARY
    if not slice_by:
        if agg_func == "count":
            vals = df.groupby(period_col).size().reindex(all_periods, fill_value=0)
            series.append({"name": "Total", "values": _trim_edges(vals.tolist()), "color": _total_color})
        else:
            medians = df.groupby(period_col)[value_col].median().reindex(all_periods)
            vals = [v if pd.notna(v) else None for v in medians.tolist()]
            series.append({"name": "Total", "values": vals, "color": _total_color})

    elif slice_by == "task" and "ActivityName" in df.columns:
        df = df.copy()
        df["_TaskGroup"] = df["ActivityName"].map(_TASK_TYPE_TO_GROUP).fillna(df["ActivityName"])
        groups = sorted(df["_TaskGroup"].dropna().unique(),
                        key=lambda g: _TASK_GROUP_ORDER.get(g, 999))
        for i, grp in enumerate(groups):
            sub = df[df["_TaskGroup"] == grp]
            color = _TASK_GROUP_COLORS.get(grp, CHART_COLORWAY[i % len(CHART_COLORWAY)])
            series.append(_make_series(sub, grp, color, i))

    elif slice_by == "physician" and "ResolvedMD" in df.columns:
        known_mds = _load_known_physicians()
        for i, md in enumerate(sorted(m for m in df["ResolvedMD"].dropna().unique() if m in known_mds)):
            sub = df[df["ResolvedMD"] == md]
            name = md.split(",")[0] if "," in md else md
            series.append(_make_series(sub, name, CHART_COLORWAY[i % len(CHART_COLORWAY)], i))

    elif slice_by == "planner" and "CompletingUser" in df.columns:
        known_mds = _load_known_physicians()
        planners = sorted(p for p in df["CompletingUser"].dropna().unique()
                          if p.strip() and p.upper() != "NA" and p not in known_mds)
        for i, p in enumerate(planners):
            sub = df[df["CompletingUser"] == p]
            series.append(_make_series(sub, p, CHART_COLORWAY[i % len(CHART_COLORWAY)], i))

    elif slice_by == "bodysite" and "DiagnosisCodes" in df.columns and c2b:
        df = df.copy()
        df["_bs"] = df["DiagnosisCodes"].apply(lambda v: primary_category(v, c2b))
        for i, bs in enumerate(sorted(df["_bs"].dropna().unique())):
            if bs == "Unknown":
                continue
            sub = df[df["_bs"] == bs]
            series.append(_make_series(sub, bs, CHART_COLORWAY[i % len(CHART_COLORWAY)], i))

    # When only one series produced and we have an accent color, use it
    if len(series) == 1 and accent_color:
        series[0]["color"] = accent_color

    return series


def _prepare_volume_data(df, agg, slice_by="", c2b=None, accent_color=None):
    """Prepare volume trend data for clientside rendering."""
    if df.empty or "StartDateTime" not in df.columns:
        return None

    df = df.copy()
    period_code = "Y" if agg == "Y" else agg
    df["period"] = df["StartDateTime"].dt.to_period(period_code).dt.to_timestamp()
    all_periods = sorted(df["period"].unique())
    dates = [d.isoformat() for d in all_periods]

    series = _slice_series(df, slice_by, "period", all_periods, c2b, accent_color=accent_color)

    return {
        "dates": dates,
        "series": series,
        "stacked": len(series) > 1,
        "height": 350,
        "yTitle": "Tasks",
        "hideLegend": len(series) <= 1,
    }


def _prepare_cumulative_data(df_all, start, end, date_preset,
                              mode="prior", period_type="calendar",
                              slice_by="task", c2b=None, accent_color=None,
                              max_prior=10):
    """Prepare cumulative task volume data for overlay chart."""
    if df_all.empty or "StartDateTime" not in df_all.columns:
        return None

    from utils.cumulative_current_year import setup_current_year_range, apply_current_year_projection
    today = pd.Timestamp.now().normalize()
    start, end, _cy_last_actual = setup_current_year_range(date_preset, mode, start, end)
    if _cy_last_actual is None and end.normalize() > today:
        end = today

    period_days = (end - start).days + 1
    if period_days < 2:
        return None

    # Force rolling when period exceeds 1 year (calendar shifts would overlap)
    if period_days > 365 and period_type == "calendar":
        period_type = "rolling"

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
        if sb == "total":
            return {"Total": len(sub)}
        if sb == "task" and "ActivityName" in sub.columns:
            sub_c = sub.copy()
            sub_c["_TaskGroup"] = sub_c["ActivityName"].map(_TASK_TYPE_TO_GROUP).fillna(sub_c["ActivityName"])
            return sub_c.groupby("_TaskGroup").size().to_dict()
        elif sb == "physician" and "ResolvedMD" in sub.columns:
            known_mds = _load_known_physicians()
            counts = sub[sub["ResolvedMD"].isin(known_mds)].groupby("ResolvedMD").size()
            return {(k.split(",")[0] if "," in k else k): v for k, v in counts.items()}
        elif sb == "planner" and "CompletingUser" in sub.columns:
            known_mds = _load_known_physicians()
            psub = sub[sub["CompletingUser"].notna()
                       & ~sub["CompletingUser"].isin(known_mds)
                       & (sub["CompletingUser"].str.strip() != "")
                       & (sub["CompletingUser"].str.upper() != "NA")]
            return psub.groupby("CompletingUser").size().to_dict() if not psub.empty else {}
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
            prior.append({"label": label, "values": vals, "color": PRIOR_PERIOD_COLORS[min(pi, len(PRIOR_PERIOD_COLORS) - 1)]})
            last_prior_start = p_start

    # Metadata for client-side control updates
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

    slice_keys_sorted = sorted(all_slice_keys,
                               key=lambda g: _TASK_GROUP_ORDER.get(g, 999))
    slice_colors = {k: _TASK_GROUP_COLORS.get(k, CHART_COLORWAY[i % len(CHART_COLORWAY)])
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
                "color": accent_color or PRIMARY,
                "endpoint": current_vals[-1] if current_vals and current_vals[-1] is not None else (
                    next((v for v in reversed(current_vals) if v is not None), 0)
                ),
            },
            "prior": prior,
            "sliceBreakdown": slice_breakdown,
            "height": 350,
            "yTitle": "Cumulative Tasks",
            **_prior_meta,
        }
        if _cy_last_actual is not None:
            apply_current_year_projection(_result, _cy_last_actual, start)
        return _result

    # Slice mode
    mask = (dff_all["StartDateTime"] >= start) & (dff_all["StartDateTime"] <= end)
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

    if slice_by == "task" and "ActivityName" in dff_period.columns:
        dff_period = dff_period.copy()
        dff_period["_TaskGroup"] = dff_period["ActivityName"].map(_TASK_TYPE_TO_GROUP).fillna(dff_period["ActivityName"])
        for i, grp in enumerate(sorted(dff_period["_TaskGroup"].dropna().unique(),
                                       key=lambda g: _TASK_GROUP_ORDER.get(g, 999))):
            sub = dff_period[dff_period["_TaskGroup"] == grp]
            daily = sub.groupby(sub["StartDateTime"].dt.normalize()).size()
            daily = daily.reindex(dates_range, fill_value=0)
            series.append({
                "name": grp,
                "values": _trimmed_cumsum(daily),
                "color": _TASK_GROUP_COLORS.get(grp, CHART_COLORWAY[i % len(CHART_COLORWAY)]),
            })

    elif slice_by == "physician" and "ResolvedMD" in dff_period.columns:
        known_mds = _load_known_physicians()
        for i, md in enumerate(sorted(m for m in dff_period["ResolvedMD"].dropna().unique() if m in known_mds)):
            sub = dff_period[dff_period["ResolvedMD"] == md]
            daily = sub.groupby(sub["StartDateTime"].dt.normalize()).size()
            daily = daily.reindex(dates_range, fill_value=0)
            series.append({
                "name": md.split(",")[0] if "," in md else md,
                "values": _trimmed_cumsum(daily),
                "color": CHART_COLORWAY[i % len(CHART_COLORWAY)],
            })

    elif slice_by == "planner" and "CompletingUser" in dff_period.columns:
        known_mds = _load_known_physicians()
        planners = sorted(p for p in dff_period["CompletingUser"].dropna().unique()
                          if p.strip() and p.upper() != "NA" and p not in known_mds)
        for i, p in enumerate(planners):
            sub = dff_period[dff_period["CompletingUser"] == p]
            daily = sub.groupby(sub["StartDateTime"].dt.normalize()).size()
            daily = daily.reindex(dates_range, fill_value=0)
            series.append({
                "name": p,
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
        **_prior_meta,
    }


def _prepare_time_trend_data(df, is_completed, agg="M", slice_by="", c2b=None, accent_color=None):
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
                           agg_func="median", value_col="MinutesToComplete",
                           accent_color=accent_color)

    if not series:
        return None

    # Auto-detect display unit from the data values
    all_vals = [v for s in series for v in s["values"] if v is not None]
    min_val = min(all_vals) if all_vals else 0
    if min_val >= 1440:  # smallest value > 24h → show days
        scale, y_title, tick_suffix = 1 / 1440, "Median Time", "d"
    elif min_val >= 60 or (all_vals and max(all_vals) >= 120):
        scale, y_title, tick_suffix = 1 / 60, "Median Time", "h"
    else:
        scale, y_title, tick_suffix = 1, "Median Time", "m"

    if scale != 1:
        for s in series:
            s["values"] = [v * scale if v is not None else None for v in s["values"]]

    return {
        "dates": dates,
        "series": series,
        "stacked": len(series) > 1,
        "height": 350,
        "yTitle": y_title,
        "yTickSuffix": tick_suffix,
        "hideLegend": len(series) <= 1,
    }


def _prepare_sla_data(df, is_completed, agg="W", slice_by="", c2b=None, accent_color=None):
    """Prepare SLA compliance trend data for clientside rendering."""
    if ("MinutesToComplete" not in df.columns or "MinutesAllowed" not in df.columns
            or "StartDateTime" not in df.columns):
        return None

    completed = df[is_completed].copy()
    # Exclude Isodose tasks — ARIA SLA data for planning tasks is unreliable
    iso_only = False
    if "ActivityName" in completed.columns:
        iso_types = _TASK_TYPE_GROUPS.get("Create Isodose Plan", [])
        pre_exclude = len(completed)
        completed = completed[~completed["ActivityName"].isin(iso_types)]
        if pre_exclude > 0 and completed.empty:
            iso_only = True
    completed["MinutesToComplete"] = pd.to_numeric(completed["MinutesToComplete"], errors="coerce")
    completed["MinutesAllowed"] = pd.to_numeric(completed["MinutesAllowed"], errors="coerce")
    completed = completed.dropna(subset=["MinutesToComplete", "MinutesAllowed"])
    if completed.empty:
        if iso_only:
            return {"emptyMessage": "Allowed-time data not available for Isodose tasks\n(ARIA due-date data is unreliable)", "height": 320}
        return {"emptyMessage": "No allowed-time data available for this selection", "height": 320}

    period_code = "Y" if agg == "Y" else agg
    completed["period"] = completed["StartDateTime"].dt.to_period(period_code).dt.to_timestamp()
    # On-time is a calendar check: did the task finish before its due date?
    # Independent of business-hours toggle.
    if "CompletedDateTime" in completed.columns and "DueDateTime" in completed.columns:
        completed["on_time"] = completed["CompletedDateTime"] <= completed["DueDateTime"]
    else:
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
        series.append(_sla_for_subset(completed, "Overall", accent_color or PRIMARY))

    elif slice_by == "task" and "ActivityName" in completed.columns:
        completed = completed.copy()
        completed["_TaskGroup"] = completed["ActivityName"].map(_TASK_TYPE_TO_GROUP).fillna(completed["ActivityName"])
        for i, grp in enumerate(sorted(completed["_TaskGroup"].dropna().unique(),
                                        key=lambda g: _TASK_GROUP_ORDER.get(g, 999))):
            sub = completed[completed["_TaskGroup"] == grp]
            series.append(_sla_for_subset(sub, grp, _TASK_GROUP_COLORS.get(grp, CHART_COLORWAY[i % len(CHART_COLORWAY)])))

    elif slice_by == "physician" and "ResolvedMD" in completed.columns:
        known_mds = _load_known_physicians()
        for i, md in enumerate(sorted(m for m in completed["ResolvedMD"].dropna().unique() if m in known_mds)):
            sub = completed[completed["ResolvedMD"] == md]
            name = md.split(",")[0] if "," in md else md
            series.append(_sla_for_subset(sub, name, CHART_COLORWAY[i % len(CHART_COLORWAY)]))

    elif slice_by == "planner" and "CompletingUser" in completed.columns:
        known_mds = _load_known_physicians()
        planners = sorted(p for p in completed["CompletingUser"].dropna().unique()
                          if p.strip() and p.upper() != "NA" and p not in known_mds)
        for i, p in enumerate(planners):
            sub = completed[completed["CompletingUser"] == p]
            series.append(_sla_for_subset(sub, p, CHART_COLORWAY[i % len(CHART_COLORWAY)]))

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
        "yTitle": "On-Time %",
        "hideLegend": len(series) <= 1,
    }


def _prepare_histogram_data(df, is_completed, slice_by="", c2b=None, accent_color=None):
    """Prepare histogram data for clientside rendering.

    Returns a dict with series of raw values, stats, and display config.
    """
    if "MinutesToComplete" not in df.columns:
        return None

    completed = df[is_completed].copy()
    completed["MinutesToComplete"] = pd.to_numeric(completed["MinutesToComplete"], errors="coerce")
    completed = completed.dropna(subset=["MinutesToComplete"])
    if completed.empty:
        return None

    # --- Auto-detect display unit based on data range ---
    all_vals = completed["MinutesToComplete"]
    max_val = float(all_vals.max())
    if max_val > 3 * 1440:
        suffix, scale = "d", 1 / 1440
        tick_suffix, x_title = "d", "Days"
    elif max_val >= 60:
        suffix, scale = "h", 1 / 60
        tick_suffix, x_title = "hr", "Hours"
    else:
        suffix, scale = "m", 1
        tick_suffix, x_title = "m", "Minutes"

    completed["_display_val"] = completed["MinutesToComplete"] * scale

    # --- Stats ---
    disp = completed["_display_val"]
    stats = {
        "n": len(disp),
        "median": float(disp.median()),
        "mean": float(disp.mean()),
        "q1": float(disp.quantile(0.25)),
        "q3": float(disp.quantile(0.75)),
        "suffix": suffix,
        "tickSuffix": tick_suffix,
        "xTitle": x_title,
        "accentColor": accent_color or PRIMARY,
    }

    # --- Build series ---
    series = []

    def _add_series(sub, name, color):
        series.append({
            "name": name,
            "values": sub["_display_val"].tolist(),
            "color": color,
        })

    if not slice_by:
        _add_series(completed, "All Tasks", accent_color or PRIMARY)
    elif slice_by == "task" and "ActivityName" in completed.columns:
        completed["_TaskGroup"] = completed["ActivityName"].map(_TASK_TYPE_TO_GROUP).fillna(completed["ActivityName"])
        for i, grp in enumerate(sorted(completed["_TaskGroup"].dropna().unique(),
                                        key=lambda g: _TASK_GROUP_ORDER.get(g, 999))):
            _add_series(completed[completed["_TaskGroup"] == grp], grp,
                        _TASK_GROUP_COLORS.get(grp, CHART_COLORWAY[i % len(CHART_COLORWAY)]))
    elif slice_by == "physician" and "ResolvedMD" in completed.columns:
        known_mds = _load_known_physicians()
        for i, md in enumerate(sorted(m for m in completed["ResolvedMD"].dropna().unique() if m in known_mds)):
            name = md.split(",")[0] if "," in md else md
            _add_series(completed[completed["ResolvedMD"] == md], name,
                        CHART_COLORWAY[i % len(CHART_COLORWAY)])
    elif slice_by == "planner" and "CompletingUser" in completed.columns:
        known_mds = _load_known_physicians()
        planners = sorted(p for p in completed["CompletingUser"].dropna().unique()
                          if p.strip() and p.upper() != "NA" and p not in known_mds)
        for i, p in enumerate(planners):
            _add_series(completed[completed["CompletingUser"] == p], p,
                        CHART_COLORWAY[i % len(CHART_COLORWAY)])

    # When only one series and we have an accent color, use it
    if len(series) == 1 and accent_color:
        series[0]["color"] = accent_color
        stats["accentColor"] = accent_color

    return {"series": series, "stats": stats, "sliced": bool(slice_by)}


def _prepare_time_compare_data(df, is_time_valid, slice_by="", c2b=None, accent_color=None):
    """Prepare actual vs allowed time comparison data for horizontal bar chart.

    Returns rows with median actual and median allowed values, grouped by the
    selected dimension (task type, physician, or diagnosis).
    """
    if "MinutesToComplete" not in df.columns or "MinutesAllowed" not in df.columns:
        return None

    completed = df[is_time_valid].copy()
    completed["MinutesToComplete"] = pd.to_numeric(completed["MinutesToComplete"], errors="coerce")
    completed["MinutesAllowed"] = pd.to_numeric(completed["MinutesAllowed"], errors="coerce")
    completed = completed.dropna(subset=["MinutesToComplete"])
    if completed.empty:
        return None

    # Identify Isodose rows — ARIA SLA data is unreliable for planning tasks
    _iso_types = _TASK_TYPE_GROUPS.get("Create Isodose Plan", [])
    is_iso = (completed["ActivityName"].isin(_iso_types)
              if "ActivityName" in completed.columns
              else pd.Series(False, index=completed.index))

    # For non-Isodose rows, require valid allowed time
    has_allowed = completed["MinutesAllowed"].notna() & (completed["MinutesAllowed"] > 0) & ~is_iso

    # Auto-detect display unit from actual times (always present)
    # plus allowed times where valid
    max_actual = float(completed["MinutesToComplete"].max())
    max_allowed = float(completed.loc[has_allowed, "MinutesAllowed"].max()) if has_allowed.any() else 0
    max_val = max(max_actual, max_allowed)
    if max_val > 3 * 1440:
        scale, tick_suffix = 1 / 1440, "d"
    elif max_val >= 60:
        scale, tick_suffix = 1 / 60, "hr"
    else:
        scale, tick_suffix = 1, "m"

    rows = []

    def _add_row(sub, label, color):
        actual_med = float(sub["MinutesToComplete"].median()) * scale
        # Compute allowed only from non-Isodose rows with valid SLA
        sub_allowed = sub[sub.index.isin(completed.index[has_allowed])]
        if len(sub_allowed) > 0:
            allowed_med = round(float(sub_allowed["MinutesAllowed"].median()) * scale, 2)
        else:
            allowed_med = None
        rows.append({
            "label": label,
            "actual": round(actual_med, 2),
            "allowed": allowed_med,
            "color": color,
            "n": len(sub),
        })

    if not slice_by:
        _add_row(completed, "All Tasks", accent_color or PRIMARY)
    elif slice_by == "task" and "ActivityName" in completed.columns:
        completed["_TaskGroup"] = completed["ActivityName"].map(_TASK_TYPE_TO_GROUP).fillna(completed["ActivityName"])
        for i, grp in enumerate(sorted(completed["_TaskGroup"].dropna().unique(),
                                        key=lambda g: _TASK_GROUP_ORDER.get(g, 999))):
            sub = completed[completed["_TaskGroup"] == grp]
            color = _TASK_GROUP_COLORS.get(grp, CHART_COLORWAY[i % len(CHART_COLORWAY)])
            _add_row(sub, grp, color)
    elif slice_by == "physician" and "ResolvedMD" in completed.columns:
        known_mds = _load_known_physicians()
        for i, md in enumerate(sorted(m for m in completed["ResolvedMD"].dropna().unique() if m in known_mds)):
            sub = completed[completed["ResolvedMD"] == md]
            name = md.split(",")[0] if "," in md else md
            _add_row(sub, name, CHART_COLORWAY[i % len(CHART_COLORWAY)])
    elif slice_by == "planner" and "CompletingUser" in completed.columns:
        known_mds = _load_known_physicians()
        planners = sorted(p for p in completed["CompletingUser"].dropna().unique()
                          if p.strip() and p.upper() != "NA" and p not in known_mds)
        for i, p in enumerate(planners):
            sub = completed[completed["CompletingUser"] == p]
            _add_row(sub, p, CHART_COLORWAY[i % len(CHART_COLORWAY)])
    elif slice_by == "bodysite" and "DiagnosisCodes" in completed.columns and c2b:
        completed["_bs"] = completed["DiagnosisCodes"].apply(lambda v: primary_category(v, c2b))
        for i, bs in enumerate(sorted(completed["_bs"].dropna().unique())):
            if bs == "Unknown":
                continue
            sub = completed[completed["_bs"] == bs]
            _add_row(sub, bs, CHART_COLORWAY[i % len(CHART_COLORWAY)])

    if not rows:
        return None

    return {
        "rows": rows,
        "tickSuffix": tick_suffix,
        "accentColor": accent_color or PRIMARY,
    }


def _build_table(df, is_completed):
    display_cols = []

    # Include all completed tasks + open tasks only if prior step is done
    actionable = is_completed | _prior_step_complete(df)
    table_df = df[actionable].copy()

    if table_df.empty:
        return [], []

    # Check if filtered to Isodose-only (allowed time unreliable)
    iso_types = _TASK_TYPE_GROUPS.get("Create Isodose Plan", [])
    is_iso_only = ("ActivityName" in table_df.columns
                   and set(table_df["ActivityName"].dropna().unique()).issubset(set(iso_types)))

    col_map = [
        ("PriorStepBaseline", "Baseline"),
        ("CompletedDateTime", "Completed"),
        ("PatientFullName", "Patient"),
        ("ActivityName", "Type"),
        ("AssignedMD", "Assigned"),
        ("CompletingUser", "Completing"),
        ("MinutesToComplete", "Actual (min)"),
        ("MinutesAllowed", "Allowed (min)"),
        ("TaskStatus", "Status"),
    ]

    for col, header in col_map:
        if col not in table_df.columns:
            continue
        if col == "MinutesAllowed" and is_iso_only:
            continue
        col_def = {"field": col, "headerName": header}
        if col == "PriorStepBaseline":
            col_def["sort"] = "desc"
        display_cols.append(col_def)

    if not display_cols:
        return [], []

    # Fill null baselines with a far-future date so they sort to top in desc order
    _FAR_FUTURE = pd.Timestamp("2099-12-31")
    if "PriorStepBaseline" in table_df.columns:
        table_df["PriorStepBaseline"] = table_df["PriorStepBaseline"].fillna(_FAR_FUTURE)

    table_df = table_df.sort_values("PriorStepBaseline", ascending=False).head(200)

    # Blank out allowed time for Isodose rows (unreliable ARIA data)
    if "MinutesAllowed" in table_df.columns and "ActivityName" in table_df.columns:
        iso_mask = table_df["ActivityName"].isin(iso_types)
        table_df.loc[iso_mask, "MinutesAllowed"] = pd.NA

    for c in table_df.select_dtypes(include=["datetime64"]).columns:
        table_df[c] = table_df[c].dt.strftime("%m/%d/%Y %H:%M")
    # Replace the far-future placeholder with a visible label
    if "PriorStepBaseline" in table_df.columns:
        table_df["PriorStepBaseline"] = table_df["PriorStepBaseline"].replace(
            _FAR_FUTURE.strftime("%m/%d/%Y %H:%M"), "Pending"
        )
    table_df = sanitize_for_grid(table_df)

    return table_df.to_dict("records"), apply_phi_grid_rules(display_cols)


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
clientside_callback("""function() {
        return window.dash_clientside.census.smoothChartWithType.apply(null, arguments);
    }""",
    Output("tasks-chart-volume", "figure"),
    Input("tasks-store-volume", "data"),
    Input("tasks-volume-settings-smooth", "value"),
    Input("tasks-volume-settings-type", "value"),
    State("tasks-chart-volume", "figure"),
    prevent_initial_call=True,
)

clientside_callback("""function() {
        var fig = window.dash_clientside.cumulative.renderWithProjectToggle.apply(null, arguments);
        return window.dash_clientside.chartDeferred.wrap("tasks-chart-cumulative", fig, true);
    }""",
    Output("tasks-chart-cumulative", "figure"),
    Input("tasks-store-cumulative", "data"),
    Input("tasks-cumulative-settings-smooth", "value"),
    Input("tasks-cumulative-settings-type", "value"),
    Input("tasks-cumulative-settings-stack", "value"),
    Input("tasks-cumulative-settings-prior-periods", "value"),

    Input("tasks-cumulative-project", "checked"),
    State("tasks-chart-cumulative", "figure"),
    prevent_initial_call=True,
)

clientside_callback("""function() {
        return window.dash_clientside.census.smoothChartWithType.apply(null, arguments);
    }""",
    Output("tasks-chart-time-trend", "figure"),
    Input("tasks-store-time-trend", "data"),
    Input("tasks-time-trend-settings-smooth", "value"),
    Input("tasks-time-trend-settings-type", "value"),
    State("tasks-chart-time-trend", "figure"),
    prevent_initial_call=True,
)

clientside_callback("""function() {
        return window.dash_clientside.census.smoothChartWithType.apply(null, arguments);
    }""",
    Output("tasks-chart-sla", "figure"),
    Input("tasks-store-sla", "data"),
    Input("tasks-sla-settings-smooth", "value"),
    Input("tasks-sla-settings-type", "value"),
    State("tasks-chart-sla", "figure"),
    prevent_initial_call=True,
)

# Show/hide cumulative sub-controls based on mode + chart-type:
#   bar           → hide mode toggle, show period-type + slice together
#   prior + non-bar → show mode + period-type, hide slice
#   slice + non-bar → show mode + slice, hide period-type
clientside_callback(
    """function(mode, chartType) {
        if (chartType === "bar") {
            return [{"display": "none"}, {}, {}];
        }
        if (mode === "prior") {
            return [{}, {}, {"display": "none"}];
        }
        return [{}, {"display": "none"}, {}];
    }""",
    Output("tasks-cumulative-mode", "style"),
    Output("tasks-cumulative-period-type", "style"),
    Output("tasks-cumulative-slice", "style"),
    Input("tasks-cumulative-mode", "value"),
    Input("tasks-cumulative-settings-type", "value"),
)

# Disable Calendar when period > 1 year; cap prior-periods slider to available data
clientside_callback(
    """function(storeData, currentPtValue) {
        return window.dash_clientside.cumulative.updatePriorControls(storeData, currentPtValue);
    }""",
    Output("tasks-cumulative-period-type", "data"),
    Output("tasks-cumulative-period-type", "value", allow_duplicate=True),
    Output("tasks-cumulative-settings-prior-periods", "max"),
    Output("tasks-cumulative-settings-prior-periods", "marks"),
    Input("tasks-store-cumulative", "data"),
    State("tasks-cumulative-period-type", "value"),
    prevent_initial_call=True,
)

# Hide "Total" slice option in line/area mode; swap MD↔Planner for Isodose
clientside_callback(
    """function(chartType, taskTypes, sliceVal) {
        var none = !taskTypes || taskTypes.length === 0;
        var hasIso = none || taskTypes.indexOf("Create Isodose Plan") >= 0;
        var isoOnly = !none && taskTypes.length === 1 && taskTypes[0] === "Create Isodose Plan";
        var hasMD = !isoOnly;
        var hasPlanner = hasIso;
        var noUpdate = window.dash_clientside.no_update;

        var opts = [];
        if (chartType === "bar") opts.push({value: "total", label: "Total"});
        opts.push({value: "task", label: "Task"});
        if (hasMD) opts.push({value: "physician", label: "MD"});
        if (hasPlanner) opts.push({value: "planner", label: "Planner"});
        opts.push({value: "bodysite", label: "Dx"});

        var valid = false;
        for (var i = 0; i < opts.length; i++) {
            if (opts[i].value === sliceVal) { valid = true; break; }
        }
        return [opts, valid ? noUpdate : "task"];
    }""",
    Output("tasks-cumulative-slice", "data"),
    Output("tasks-cumulative-slice", "value", allow_duplicate=True),
    Input("tasks-cumulative-settings-type", "value"),
    Input("tasks-filter-type", "value"),
    State("tasks-cumulative-slice", "value"),
    prevent_initial_call=True,
)

# ---------------------------------------------------------------------------
# Clientside callbacks for KPI sparklines
# ---------------------------------------------------------------------------
for _kg in _KPI_GROUPS:
    for _suffix in ("comp", "time"):
        _spark_id = f"tasks-spark-{_kg['key']}_{_suffix}"
        clientside_callback(f"""function() {{
        var fig = window.dash_clientside.sparklines.updateFromStore.apply(null, arguments);
        return window.dash_clientside.chartDeferred.wrap("{_spark_id}", fig);
    }}""",
            Output(_spark_id, "figure"),
            Input("tasks-store-kpi-sparklines", "data"),
            Input(_spark_id, "id"),
            Input("tasks-smooth-slider", "value"),
            prevent_initial_call=True,
        )

# ---------------------------------------------------------------------------
# Register settings toggle + PNG export callbacks for charts with settings
# ---------------------------------------------------------------------------
register_chart_callbacks([
    ("tasks-volume", "tasks-chart-volume"),
    {"sid": "tasks-cumulative", "gid": "tasks-chart-cumulative", "store_id": "tasks-store-cumulative", "show_grouping": False},
    ("tasks-histogram", "tasks-chart-histogram"),
    ("tasks-time-compare", "tasks-chart-time-compare"),
    ("tasks-time-trend", "tasks-chart-time-trend"),
    ("tasks-sla", "tasks-chart-sla"),
])

# ---------------------------------------------------------------------------
# Slice-by dim styling
# ---------------------------------------------------------------------------
_SLICE_CLASS_JS = """function(val) {
    return (val && val !== "total") ? "slice-group-active" : "slice-total-active";
}"""

for _sid in ["tasks-volume-slice", "tasks-hist-slice", "tasks-time-compare-slice", "tasks-time-slice", "tasks-sla-slice", "tasks-cumulative-slice"]:
    clientside_callback(
        _SLICE_CLASS_JS,
        Output(_sid, "className"),
        Input(_sid, "value"),
    )

# Histogram: clientside rendering from store
clientside_callback("""function() {
        var fig = window.dash_clientside.histogram.render.apply(null, arguments);
        return window.dash_clientside.chartDeferred.wrap("tasks-chart-histogram", fig, true);
    }""",
    Output("tasks-chart-histogram", "figure"),
    Input("tasks-store-histogram", "data"),
    Input("tasks-histogram-settings-type", "value"),
    Input("tasks-hist-bw", "value"),
    State("tasks-chart-histogram", "figure"),
    prevent_initial_call=True,
)

# Time comparison: clientside rendering from store
clientside_callback("""function() {
        var fig = window.dash_clientside.timeCompare.render.apply(null, arguments);
        return window.dash_clientside.chartDeferred.wrap("tasks-chart-time-compare", fig, true);
    }""",
    Output("tasks-chart-time-compare", "figure"),
    Input("tasks-store-time-compare", "data"),
    State("tasks-chart-time-compare", "figure"),
    prevent_initial_call=True,
)

# Show kernel bandwidth slider only in density mode
clientside_callback(
    """function(chartType) {
        return chartType === "density" ? {} : {"display": "none"};
    }""",
    Output("tasks-hist-bw-wrap", "style"),
    Input("tasks-histogram-settings-type", "value"),
)

_HIDE_STACK_JS = """function(sliceVal, chartType) {
    var single = !sliceVal || sliceVal === "total" || sliceVal === "";
    var noStack = chartType === "line";
    return (single || noStack) ? {"display": "none"} : {};
}"""

for _slice_id, _settings_id in [
    ("tasks-volume-slice", "tasks-volume"),
    ("tasks-time-slice", "tasks-time-trend"),
    ("tasks-sla-slice", "tasks-sla"),
]:
    clientside_callback(
        _HIDE_STACK_JS,
        Output(f"{_settings_id}-settings-stack-wrap", "style", allow_duplicate=True),
        Input(_slice_id, "value"),
        Input(f"{_settings_id}-settings-type", "value"),
        prevent_initial_call="initial_duplicate",
    )

# Cumulative chart: also hide grouping in Prior Periods mode (single dimension)
clientside_callback(
    """function(mode, sliceVal, chartType) {
        var single = !sliceVal || sliceVal === "total" || sliceVal === "";
        if (single) return {"display": "none"};
        if (chartType === "bar") return {};
        var isPrior = mode === "prior";
        var noStack = chartType === "line";
        return (isPrior || noStack) ? {"display": "none"} : {};
    }""",
    Output("tasks-cumulative-settings-stack-wrap", "style"),
    Input("tasks-cumulative-mode", "value"),
    Input("tasks-cumulative-slice", "value"),
    Input("tasks-cumulative-settings-type", "value"),
)

# ---------------------------------------------------------------------------
# Dynamic MD / Planner slice options based on task type filter
# ---------------------------------------------------------------------------
clientside_callback(
    """function(taskTypes, volVal, histVal, tcVal, timeVal, slaVal) {
        var none = !taskTypes || taskTypes.length === 0;
        var hasIso = none || taskTypes.indexOf("Create Isodose Plan") >= 0;
        var isoOnly = !none && taskTypes.length === 1 && taskTypes[0] === "Create Isodose Plan";
        var hasMD = !isoOnly;
        var hasPlanner = hasIso;
        var singleTask = !none && taskTypes.length === 1;
        var noUpdate = window.dash_clientside.no_update;

        function buildOpts(includeTotal, includeDx) {
            var opts = [];
            if (includeTotal) opts.push({value: "", label: "Total"});
            opts.push({value: "task", label: "Task"});
            if (hasMD) opts.push({value: "physician", label: "MD"});
            if (hasPlanner) opts.push({value: "planner", label: "Planner"});
            if (includeDx) opts.push({value: "bodysite", label: "Dx"});
            return opts;
        }
        function validVal(opts, curVal) {
            for (var i = 0; i < opts.length; i++) {
                if (opts[i].value === curVal) return noUpdate;
            }
            return opts.length > 0 ? opts[0].value : "task";
        }
        var showTotal = !singleTask;
        var dxOpts   = buildOpts(showTotal, true);
        var noDxOpts = buildOpts(showTotal, false);
        return [
            dxOpts,   validVal(dxOpts, volVal),
            noDxOpts, validVal(noDxOpts, histVal),
            dxOpts,   validVal(dxOpts, tcVal),
            dxOpts,   validVal(dxOpts, timeVal),
            dxOpts,   validVal(dxOpts, slaVal)
        ];
    }""",
    Output("tasks-volume-slice", "data"),
    Output("tasks-volume-slice", "value"),
    Output("tasks-hist-slice", "data"),
    Output("tasks-hist-slice", "value"),
    Output("tasks-time-compare-slice", "data"),
    Output("tasks-time-compare-slice", "value"),
    Output("tasks-time-slice", "data"),
    Output("tasks-time-slice", "value"),
    Output("tasks-sla-slice", "data"),
    Output("tasks-sla-slice", "value"),
    Input("tasks-filter-type", "value"),
    State("tasks-volume-slice", "value"),
    State("tasks-hist-slice", "value"),
    State("tasks-time-compare-slice", "value"),
    State("tasks-time-slice", "value"),
    State("tasks-sla-slice", "value"),
)

# ---------------------------------------------------------------------------
# Table column filter: badge + clear button
# ---------------------------------------------------------------------------
clientside_callback(
    """function(virtual, rowData) {
        var base = {"position": "absolute", "top": -12, "right": 8, "zIndex": 10, "cursor": "pointer"};
        var hidden = Object.assign({}, base, {"display": "none"});
        var btnHide = {"display": "none"};
        if (!rowData || !rowData.length || !virtual) {
            return [hidden, btnHide];
        }
        if (virtual.length >= rowData.length) {
            return [hidden, btnHide];
        }
        return [base, {}];
    }""",
    Output("tasks-grid-filter-badge", "style"),
    Output("tasks-table-clear-filters", "style"),
    Input("tasks-detail-grid", "virtualRowData"),
    State("tasks-detail-grid", "rowData"),
)

# Clear filters button → reset filterModel
clientside_callback(
    """function(n) {
        if (!n) return window.dash_clientside.no_update;
        return {};
    }""",
    Output("tasks-detail-grid", "filterModel"),
    Input("tasks-table-clear-filters", "n_clicks"),
    prevent_initial_call=True,
)

# CSV export
clientside_callback(
    """function(n) {
        if (!n) return window.dash_clientside.no_update;
        gridExportCsv('tasks-detail-grid', 'tasks_detail.csv');
        return window.dash_clientside.no_update;
    }""",
    Output("tasks-table-export", "n_clicks"),
    Input("tasks-table-export", "n_clicks"),
    prevent_initial_call=True,
)

# Badge click → scroll to table
clientside_callback(
    """function(n) {
        if (!n) return window.dash_clientside.no_update;
        var el = document.getElementById('tasks-detail-accordion');
        if (el) el.scrollIntoView({behavior: 'smooth', block: 'start'});
        return window.dash_clientside.no_update;
    }""",
    Output("tasks-grid-filter-badge", "n_clicks"),
    Input("tasks-grid-filter-badge", "n_clicks"),
    prevent_initial_call=True,
)


# Project-to-year-end toggle visibility (shown only for current_year preset)
clientside_callback(
    """function(preset) {
        return preset === "current_year" ? {} : {"display": "none"};
    }""",
    Output("tasks-cumulative" + "-project-wrap", "style"),
    Input("tasks-filter-date-preset", "value"),
)

