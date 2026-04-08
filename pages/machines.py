"""Machine Downtime page — multi-level drill-down analysis of linac downtime,
patient impact, and course-level disruption across all treatment machines."""

import dash
import dash_mantine_components as dmc
import dash_ag_grid as dag
from dash import callback, clientside_callback, ClientsideFunction, Input, Output, State, dcc, html, no_update
from dash_iconify import DashIconify
import plotly.graph_objects as go
import pandas as pd
import numpy as np
from datetime import timedelta

from config.settings import (
    DEPARTMENT_COLORS, CHART_COLORWAY, PRIMARY, MACHINE_DEPT,
    DEFAULT_LAYOUT, FONT_FAMILY, NEUTRAL, SEMANTIC_COLORS,
    DEFAULT_COLUMN_DEFS, DEFAULT_GRID_OPTIONS, DEFAULT_GRID_STYLE, DEFAULT_GRID_CLASS,
)
from components.kpi_card import kpi_card
from components.chart_card import chart_card, register_chart_callbacks
from utils.charts import apply_default_layout, empty_figure
from utils.date_slider import (
    month_idx, idx_to_date, MAX_IDX, SLIDER_MARKS, DEFAULT_SLIDER,
    preset_to_slider_val,
)

dash.register_page(__name__, path="/machines", name="Machine Downtime", order=8)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ALL_MACHINES = ["TrueBeamNorth", "21EX", "21iX_CEN", "21iX_AB", "6EX"]
ACTIVE_MACHINES = ["TrueBeamNorth", "21EX", "21iX_CEN", "21iX_AB"]

MACHINE_COLORS = {m: DEPARTMENT_COLORS.get(d, CHART_COLORWAY[0])
                  for m, d in MACHINE_DEPT.items()}

CONFIDENCE_COLORS = {"High": "#D32F2F", "Medium": "#FF9800", "Low": "#FFC107"}

PAGE_ID = "machines"


def _machine_color(machine):
    return MACHINE_COLORS.get(machine, CHART_COLORWAY[0])


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
                dmc.Title("Machine Downtime", order=2, className="page-title"),
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
                                # Signal filters — custom panel (chip_dropdown.js wires the toggle)
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
                                            className="wf-chip-dropdown",
                                            style={"display": "none", "minWidth": "320px"},
                                            children=[
                                                # Event Type
                                                dmc.Text("Event Type", size="xs", fw=600, c="#6B7280"),
                                                dmc.ChipGroup(
                                                    id=f"{PAGE_ID}-filter-rowtype",
                                                    value=["Gap", "StartOfDay", "EndOfDay", "FullDay"],
                                                    multiple=True,
                                                    children=[
                                                        dmc.Chip("Intraday Gap", value="Gap", size="xs"),
                                                        dmc.Chip("Start of Day", value="StartOfDay", size="xs"),
                                                        dmc.Chip("End of Day", value="EndOfDay", size="xs"),
                                                        dmc.Chip("Full Day Down", value="FullDay", size="xs"),
                                                    ],
                                                ),
                                                dmc.Divider(my="sm"),
                                                # Min Gap Duration
                                                dmc.Text("Min Gap Duration", size="xs", fw=600, c="#6B7280"),
                                                dmc.Box(
                                                    dmc.Slider(
                                                        id=f"{PAGE_ID}-filter-gap-threshold",
                                                        min=0, max=60, step=5, value=15,
                                                        size="sm",
                                                        marks=[
                                                            {"value": 0, "label": "0m"},
                                                            {"value": 15, "label": "15m"},
                                                            {"value": 30, "label": "30m"},
                                                            {"value": 60, "label": "60m"},
                                                        ],
                                                        styles={"markLabel": {"fontSize": "10px"}},
                                                    ),
                                                    mt=4, mb=20, style={"width": "100%"},
                                                ),
                                                dmc.Divider(my="sm"),
                                                # Min Cancellations
                                                dmc.Text("Min Cancellations", size="xs", fw=600, c="#6B7280"),
                                                dmc.Box(
                                                    dmc.Slider(
                                                        id=f"{PAGE_ID}-filter-min-cancellations",
                                                        min=0, max=10, step=1, value=0,
                                                        size="sm",
                                                        marks=[
                                                            {"value": 0, "label": "Any"},
                                                            {"value": 1, "label": "1+"},
                                                            {"value": 5, "label": "5+"},
                                                            {"value": 10, "label": "10+"},
                                                        ],
                                                        styles={"markLabel": {"fontSize": "10px"}},
                                                    ),
                                                    mt=4, mb=20, style={"width": "100%"},
                                                ),
                                                dmc.Divider(my="sm"),
                                                # Require Signals
                                                dmc.Text("Require", size="xs", fw=600, c="#6B7280"),
                                                dmc.Stack(gap=4, mt=4, children=[
                                                    dmc.Switch(
                                                        id=f"{PAGE_ID}-filter-require-note",
                                                        label="Has downtime note",
                                                        size="xs",
                                                        checked=False,
                                                    ),
                                                    dmc.Switch(
                                                        id=f"{PAGE_ID}-filter-require-termination",
                                                        label="Machine termination signal",
                                                        size="xs",
                                                        checked=False,
                                                    ),
                                                ]),
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
        dmc.Grid(id=f"{PAGE_ID}-kpi-row", gutter=16, children=[]),

        # --- Narrative summary ---
        dmc.Paper(
            dmc.Text(id=f"{PAGE_ID}-narrative", size="sm", c=NEUTRAL["text_primary"],
                     style={"lineHeight": 1.7}),
            p="md", radius="md", shadow="xs", withBorder=True,
            style={"borderLeft": f"4px solid {PRIMARY}"},
        ),

        # --- Breadcrumb navigation ---
        html.Div("All Years", id=f"{PAGE_ID}-breadcrumb", className="machines-breadcrumb"),

        # --- Drill-down containers ---
        # Level 1: Year overview cards (SVG rendered by clientside)
        dmc.Box(id=f"{PAGE_ID}-level1-container", children=[
            html.Div(id=f"{PAGE_ID}-year-cards-container"),
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
                html.Div(id=f"{PAGE_ID}-strip-svg-container", className="machines-strip-container"),
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
                    smooth_max=40, smooth_default=10, store_data=True,
                    extra_controls=[
                        dmc.SegmentedControl(
                            id=f"{PAGE_ID}-trend-agg",
                            data=[
                                {"value": "D", "label": "Daily"},
                                {"value": "W", "label": "Weekly"},
                                {"value": "M", "label": "Monthly"},
                            ],
                            value="W", size="xs",
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
                    smooth_max=30, smooth_default=5, store_data=True,
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
                            value="W", size="xs",
                        ),
                    ],
                ),
                span={"base": 12, "md": 6},
            ),
        ]),

        # --- Detail table ---
        dmc.Paper(
            children=[
                dmc.Group(justify="space-between", mb="sm", children=[
                    dmc.Text("Downtime Gap Detail", size="sm", fw=500, c=NEUTRAL["text_secondary"]),
                ]),
                dag.AgGrid(
                    id=f"{PAGE_ID}-detail-table",
                    rowData=[],
                    columnDefs=[
                        {"field": "Date", "headerName": "Date", "width": 110},
                        {"field": "Machine", "headerName": "Machine", "width": 120},
                        {"field": "Site", "headerName": "Site", "width": 100},
                        {"field": "Start", "headerName": "Start", "width": 90},
                        {"field": "End", "headerName": "End", "width": 90},
                        {"field": "Minutes", "headerName": "Duration", "width": 90, "type": "numericColumn"},
                        {"field": "Type", "headerName": "Type", "width": 130},
                        {"field": "Confidence", "headerName": "Confidence", "width": 110},
                        {"field": "Cancellations", "headerName": "Cancelled", "width": 95, "type": "numericColumn"},
                        {"field": "Errors", "headerName": "Errors", "width": 80, "type": "numericColumn"},
                        {"field": "Reroute", "headerName": "Reroute To", "width": 110},
                        {"field": "PrevPatient", "headerName": "Prev Patient", "width": 140},
                        {"field": "NextPatient", "headerName": "Next Patient", "width": 140},
                    ],
                    defaultColDef={**DEFAULT_COLUMN_DEFS, "sortable": True, "filter": True},
                    columnSize="autoSize",
                    dashGridOptions={**DEFAULT_GRID_OPTIONS, "paginationPageSize": 25},
                    style=DEFAULT_GRID_STYLE,
                    className=DEFAULT_GRID_CLASS,
                ),
            ],
            p="sm", radius="md", shadow="xs", withBorder=True,
        ),

        # --- Stores ---
        dcc.Store(id=f"{PAGE_ID}-store-drill", data={"level": 1, "year": None, "month": None, "day": None}),
        dcc.Store(id=f"{PAGE_ID}-store-gaps-agg", data={}),
        dcc.Store(id=f"{PAGE_ID}-store-timeline", data={}),
        dcc.Store(id=f"{PAGE_ID}-store-strip", data={}),
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
    f"{PAGE_ID}-chart-trend",
    f"{PAGE_ID}-chart-patient-impact",
])


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


def _filter_gaps(df, machines, row_types, gap_threshold, slider_val,
                 min_cancellations=0, require_note=False,
                 require_termination=False):
    """Apply all filters to gaps dataframe."""
    if df.empty:
        return df

    df = _apply_lifespan_filter(df.copy())

    # Machine filter
    if machines:
        df = df[df["Machine"].isin(machines)]

    # Row type filter
    if row_types:
        df = df[df["RowType"].isin(row_types)]

    # Require machine termination prior to gap
    if require_termination and "LastFieldTerminationStatus" in df.columns:
        df = df[df["LastFieldTerminationStatus"] == "MACHINE"]

    # Min cancellations — require at least N cancellations in the gap window
    if min_cancellations and min_cancellations > 0 and "CancelledInGap" in df.columns:
        df = df[df["CancelledInGap"].fillna(0) >= min_cancellations]

    # Require downtime note (only meaningful when min_cancellations > 0)
    if require_note and min_cancellations and min_cancellations > 0:
        note_col = "EventNote" if "EventNote" in df.columns else "DowntimeNoteMatch"
        df = df[df[note_col].notna() & (df[note_col] != "")]

    # Gap threshold (only for Gap rows, not FullDay/EndOfDay/StartOfDay)
    if gap_threshold and gap_threshold > 0:
        gap_mask = df["RowType"] == "Gap"
        threshold_mask = ~gap_mask | (df["GapMinutes"] >= gap_threshold)
        df = df[threshold_mask]

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
    df["Year"] = df["DowntimeDate"].dt.year

    yearly = []
    for year, grp in df.groupby("Year"):
        gap_rows = grp[grp["RowType"].isin(["Gap", "StartOfDay", "EndOfDay"])]
        gap_rows_evt = _dedup_events(gap_rows)  # one row per event for GapMinutes / counts
        fullday_rows = grp[grp["RowType"] == "FullDay"]
        # Exclude weekends/holidays
        if not fullday_rows.empty:
            _wd = fullday_rows["DowntimeDate"].dt.dayofweek
            fullday_rows = fullday_rows[(_wd < 5) & (~fullday_rows["DowntimeDate"].dt.normalize().isin(holidays))]

        total_gap_hours = gap_rows_evt["GapMinutes"].sum() / 60 if not gap_rows_evt.empty else 0
        fullday_count = fullday_rows.groupby(["Machine", "DowntimeDate"]).ngroups if not fullday_rows.empty else 0
        total_hours = total_gap_hours + fullday_count * 10

        # Operating hours: ~250 workdays * 10 hrs * machines active that year
        machines_active = grp["Machine"].nunique()
        workdays = grp["DowntimeDate"].dt.normalize().nunique()
        operating_hours = workdays * 10 * machines_active if machines_active > 0 else 1
        availability = max(0, (1 - total_hours / operating_hours)) * 100

        # Monthly breakdown
        monthly = [0.0] * 12
        for m, mg in gap_rows_evt.groupby(gap_rows_evt["DowntimeDate"].dt.month):
            monthly[int(m) - 1] = mg["GapMinutes"].sum() / 60

        yearly.append({
            "year": int(year),
            "hours": round(float(total_hours), 1),
            "availability": round(float(availability), 1),
            "gapCount": int(len(gap_rows_evt)),
            "fullDayCount": int(fullday_count),
            "monthly": [round(float(v), 1) for v in monthly],
        })

    return sorted(yearly, key=lambda x: x["year"], reverse=True)


def _build_daily_summary(df):
    """Aggregate gaps + full-day outages by date for Level 2 heatmap."""
    if df.empty:
        return []

    gap_rows = df[df["RowType"].isin(["Gap", "StartOfDay", "EndOfDay"])]
    fd_rows = df[df["RowType"] == "FullDay"]
    if gap_rows.empty and fd_rows.empty:
        return []

    records = []
    if not gap_rows.empty:
        gap_rows_evt = _dedup_events(gap_rows)  # one row per event for event-level columns
        daily = gap_rows_evt.groupby(gap_rows_evt["DowntimeDate"].dt.normalize()).agg(
            minutes=("GapMinutes", "sum"),
            gapCount=("RowKey", "count"),
            machines=("Machine", lambda x: list(x.unique())),
            cancelled=("CancelledInGap", "sum"),
            errors=("MachineErrorsNearGap", "sum"),
        ).reset_index()
        for _, row in daily.iterrows():
            records.append({
                "date": row["DowntimeDate"].strftime("%Y-%m-%d"),
                "minutes": round(float(row["minutes"]), 1),
                "gapCount": int(row["gapCount"]),
                "machines": list(row["machines"]),
                "cancelled": int(row["cancelled"]),
                "errors": int(row["errors"]),
                "fullDay": False,
            })

    # Add full-day outage days (10 hrs = 600 min per machine)
    if not fd_rows.empty:
        fd_rows_evt = _dedup_events(fd_rows)  # dedup before summing event-level columns
        fd_daily = fd_rows_evt.groupby(fd_rows_evt["DowntimeDate"].dt.normalize()).agg(
            machines=("Machine", lambda x: list(x.unique())),
            cancelled=("CancelledInGap", "sum"),
            errors=("MachineErrorsNearGap", "sum"),
        ).reset_index()
        existing_dates = {r["date"] for r in records}
        for _, row in fd_daily.iterrows():
            dstr = row["DowntimeDate"].strftime("%Y-%m-%d")
            n_machines = len(row["machines"])
            if dstr in existing_dates:
                # Merge into existing record
                for rec in records:
                    if rec["date"] == dstr:
                        rec["minutes"] += 600 * n_machines
                        rec["machines"] = list(set(rec["machines"] + row["machines"]))
                        rec["cancelled"] += int(row["cancelled"])
                        rec["fullDay"] = True
                        break
            else:
                records.append({
                    "date": dstr,
                    "minutes": 600.0 * n_machines,
                    "gapCount": n_machines,
                    "machines": list(row["machines"]),
                    "cancelled": int(row["cancelled"]),
                    "errors": int(row["errors"]),
                    "fullDay": True,
                })

    return [r for r in sorted(records, key=lambda x: x["date"])
    ]



def _build_trend_data(df):
    """Compute daily downtime data — clientside JS handles D/W/M aggregation."""
    if df.empty:
        return {"dates": [], "series": []}

    gap_rows = df[df["RowType"].isin(["Gap", "StartOfDay", "EndOfDay"])].copy()
    if gap_rows.empty:
        return {"dates": [], "series": []}

    gap_rows = _dedup_events(gap_rows)  # one row per event — GapMinutes is event-level
    gap_rows["Date"] = gap_rows["DowntimeDate"].dt.normalize()
    machines = sorted(gap_rows["Machine"].unique())
    all_dates = sorted(gap_rows["Date"].unique())
    date_labels = [d.strftime("%Y-%m-%d") for d in all_dates]

    series = []
    for machine in machines:
        mdf = gap_rows[gap_rows["Machine"] == machine]
        daily = mdf.groupby("Date")["GapMinutes"].sum() / 60
        values = [round(float(daily.get(d, 0)), 2) for d in all_dates]
        dept = MACHINE_DEPT.get(machine, "Unknown")
        series.append({
            "name": machine,
            "values": values,
            "color": DEPARTMENT_COLORS.get(dept, CHART_COLORWAY[0]),
        })

    return {
        "dates": date_labels,
        "series": series,
    }


def _build_patient_impact_data(df):
    """Build daily cancelled/rerouted + course impact data — clientside JS handles D/W/M aggregation."""
    empty = {"dates": [], "cancelled": [], "rerouted": [], "courses": []}
    if df.empty:
        return empty

    gap_rows = df[df["RowType"].isin(["Gap", "StartOfDay", "EndOfDay"])].copy()
    if gap_rows.empty:
        return empty

    gap_rows["Date"] = gap_rows["DowntimeDate"].dt.normalize()
    gap_rows_evt = _dedup_events(gap_rows)  # event-level dedup for CancelledInGap
    all_dates = sorted(gap_rows["Date"].unique())
    date_labels = [d.strftime("%Y-%m-%d") for d in all_dates]

    cancelled = []
    rerouted = []
    for d in all_dates:
        dg_evt = gap_rows_evt[gap_rows_evt["Date"] == d]
        dg = gap_rows[gap_rows["Date"] == d]
        cancelled.append(int(dg_evt["CancelledInGap"].sum()))
        rerouted.append(int(dg["RerouteMachine"].notna().sum()))

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
    for _, row in tdf.iterrows():
        records.append({
            "Date": row["DowntimeDate"].strftime("%Y-%m-%d") if pd.notna(row["DowntimeDate"]) else "",
            "Machine": row.get("Machine", ""),
            "Site": row.get("Site", ""),
            "Start": str(row.get("GapStartTime", ""))[:8] if pd.notna(row.get("GapStartTime")) else "",
            "End": str(row.get("GapEndTime", ""))[:8] if pd.notna(row.get("GapEndTime")) else "",
            "Minutes": int(row["GapMinutes"]) if pd.notna(row.get("GapMinutes")) else None,
            "Type": row.get("DowntimeType") or row.get("GapClassification", ""),
            "Confidence": row.get("LocalConfidence") or row.get("DowntimeConfidence", ""),
            "Cancellations": int(row["CancelledInGap"]) if pd.notna(row.get("CancelledInGap")) else 0,
            "Errors": int(row["MachineErrorsNearGap"]) if pd.notna(row.get("MachineErrorsNearGap")) else 0,
            "Reroute": str(row["RerouteMachine"]) if pd.notna(row.get("RerouteMachine")) else "",
            "PrevPatient": str(row.get("PrevPatientName", "")) if pd.notna(row.get("PrevPatientName")) else "",
            "NextPatient": str(row.get("NextPatientName", "")) if pd.notna(row.get("NextPatientName")) else "",
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

    deduped = df.drop_duplicates(subset=keys).copy()

    # Propagate best DowntimeNoteMatch from A-branch rows
    if "DowntimeNoteMatch" in df.columns:
        note_best = (
            df[df["DowntimeNoteMatch"].notna()]
            .drop_duplicates(subset=keys)[keys + ["DowntimeNoteMatch"]]
        )
        if not note_best.empty:
            deduped = deduped.drop(columns=["DowntimeNoteMatch"])
            deduped = deduped.merge(note_best, on=keys, how="left")

    # Propagate highest LocalConfidence from any row in the event group
    if "LocalConfidence" in df.columns:
        conf_best = (
            df.assign(_co=df["LocalConfidence"].map(_CONFIDENCE_ORDER).fillna(0))
            .sort_values("_co", ascending=False)
            .drop_duplicates(subset=keys)[keys + ["LocalConfidence"]]
        )
        deduped = deduped.drop(columns=["LocalConfidence"], errors="ignore")
        deduped = deduped.merge(conf_best, on=keys, how="left")

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
    fd_rows = df_events[df_events["RowType"] == "FullDay"] if not df_events.empty else pd.DataFrame()
    if not fd_rows.empty:
        fd_evt = _dedup_events(fd_rows).copy()
        fd_evt["_med"] = fd_evt["Machine"].map(machine_median_min).fillna(600)
        fullday_est_min = float(fd_evt["_med"].sum())
        total_op_min += fullday_est_min

    if total_op_min <= 0:
        return 100.0, 0.0

    gap_rows = df_events[df_events["RowType"].isin(["Gap", "StartOfDay", "EndOfDay"])] if not df_events.empty else pd.DataFrame()
    gap_min = float(_dedup_events(gap_rows)["GapMinutes"].sum()) if not gap_rows.empty else 0.0

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

    def _score(row):
        if row.get("RowType") == "FullDay":
            if pd.notna(row.get("DowntimeNoteMatch")):
                return "High"
            if (row.get("CancelledInGap") or 0) > 0:
                return "Medium"
            return "Low"
        # Gap / StartOfDay / EndOfDay
        if pd.notna(row.get("DowntimeNoteMatch")):
            return "High"
        if row.get("LastFieldTerminationStatus") == "MACHINE":
            return "Medium"
        return "Low"

    df["LocalConfidence"] = df.apply(_score, axis=1)
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
        gap_rows = gaps_df[gaps_df["RowType"].isin(["Gap", "EndOfDay", "StartOfDay"])].copy()
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
    Output(f"{PAGE_ID}-detail-table", "rowData"),
    Output(f"{PAGE_ID}-store-kpi-sparklines", "data"),
    Input(f"{PAGE_ID}-interval", "n_intervals"),
    Input(f"{PAGE_ID}-filter-machine", "value"),
    Input(f"{PAGE_ID}-filter-rowtype", "value"),
    Input(f"{PAGE_ID}-filter-gap-threshold", "value"),
    Input(f"{PAGE_ID}-date-slider", "value"),
    Input(f"{PAGE_ID}-filter-date-preset", "value"),
    Input(f"{PAGE_ID}-filter-min-cancellations", "value"),
    Input(f"{PAGE_ID}-filter-require-note", "checked"),
    Input(f"{PAGE_ID}-filter-require-termination", "checked"),
)
def update_main_data(_n, machines, row_types, gap_threshold, slider_val, date_preset,
                     min_cancel, req_note, req_term):
    from data.loader import load_downtime_gaps

    # Resolve date range early — needed for availability and prior-period calcs
    start = idx_to_date(slider_val[0]) if slider_val else None
    end = idx_to_date(slider_val[1], end_of_month=True) if slider_val else None

    df_all = _compute_downtime_type(_compute_local_confidence(_propagate_event_note(load_downtime_gaps())))
    # Apply lifespan + non-date filters to full dataset (for prior period / heatmap)
    df_all_filtered = _filter_gaps(df_all, machines, row_types, gap_threshold, slider_val=None,
                                   min_cancellations=min_cancel, require_note=req_note,
                                   require_termination=req_term)

    df = _filter_gaps(df_all, machines, row_types, gap_threshold, slider_val,
                      min_cancellations=min_cancel, require_note=req_note,
                      require_termination=req_term)

    # --- KPIs ---
    holidays = _get_holidays_set()

    gap_rows = df[df["RowType"].isin(["Gap", "StartOfDay", "EndOfDay"])] if not df.empty else pd.DataFrame()
    # Deduplicated to one row per event — for event-level columns (GapMinutes, CancelledInGap, etc.)
    # Keep gap_rows (patient-level) for reroute_count, courses_interrupted, and patient sparklines.
    gap_rows_evt = _dedup_events(gap_rows) if not gap_rows.empty else gap_rows
    fullday_rows = df[df["RowType"] == "FullDay"] if not df.empty else pd.DataFrame()
    # Exclude weekends and holidays — no treatments expected, not real outages
    if not fullday_rows.empty:
        _wd = fullday_rows["DowntimeDate"].dt.dayofweek
        _is_workday = (_wd < 5) & (~fullday_rows["DowntimeDate"].dt.normalize().isin(holidays))
        fullday_rows = fullday_rows[_is_workday]

    gap_hours = gap_rows_evt["GapMinutes"].sum() / 60 if not gap_rows_evt.empty else 0
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
        fullday_est_hours = fullday_count * 10
        availability = max(0, (1 - (gap_hours + fullday_est_hours) / op_hours)) * 100

    total_hours = gap_hours + (fullday_est_hours if fullday_est_hours is not None else fullday_count * 10)

    event_count = len(gap_rows_evt)
    # Include cancellations from full-day outages — those rows carry CancelledInGap too
    fd_rows_evt = _dedup_events(fullday_rows) if not fullday_rows.empty else fullday_rows
    cancelled_total = (
        (int(gap_rows_evt["CancelledInGap"].sum()) if not gap_rows_evt.empty else 0)
        + (int(fd_rows_evt["CancelledInGap"].sum()) if not fd_rows_evt.empty else 0)
    )
    reroute_count = int(gap_rows["RerouteMachine"].notna().sum()) if not gap_rows.empty else 0
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
        prior_gap_rows_evt = _dedup_events(prior_gap_rows) if not prior_gap_rows.empty else prior_gap_rows
        p_gap_hours = prior_gap_rows_evt["GapMinutes"].sum() / 60 if not prior_gap_rows_evt.empty else 0
        p_fullday_count = prior_fullday_rows.groupby(["Machine", "DowntimeDate"]).ngroups if not prior_fullday_rows.empty else 0
        p_total_hours = p_gap_hours + p_fullday_count * 10
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

        p_fd_evt = _dedup_events(prior_fullday_rows) if not prior_fullday_rows.empty else prior_fullday_rows
        p_cancelled = (
            (int(prior_gap_rows_evt["CancelledInGap"].sum()) if not prior_gap_rows_evt.empty else 0)
            + (int(p_fd_evt["CancelledInGap"].sum()) if not p_fd_evt.empty else 0)
        )
        _t_cancelled = _trend(cancelled_total, p_cancelled, invert=True)

        p_reroute = int(prior_gap_rows["RerouteMachine"].notna().sum()) if not prior_gap_rows.empty else 0
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

        # 2. Availability (per period)
        all_rows = df[df["RowType"].isin(["Gap", "FullDay"])].copy() if not df.empty else pd.DataFrame()
        if not all_rows.empty:
            all_rows["_sp"] = _grp_col(all_rows)
            periods = sorted(all_rows["_sp"].unique())
            avail_vals = []
            avail_labels = []
            for p in periods:
                p_sub = all_rows[all_rows["_sp"] == p]
                p_gap = _dedup_events(p_sub[p_sub["RowType"].isin(["Gap", "StartOfDay", "EndOfDay"])])
                p_fd = p_sub[p_sub["RowType"] == "FullDay"]
                p_hrs = (p_gap["GapMinutes"].sum() / 60 if not p_gap.empty else 0) + len(p_fd) * 10
                p_wd = p_sub["DowntimeDate"].dt.normalize().nunique()
                p_nm = p_sub["Machine"].nunique()
                p_op = p_wd * 10 * p_nm if p_nm > 0 else 1
                avail_vals.append(round(max(0, (1 - p_hrs / p_op)) * 100, 1))
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
            _cancel_parts.append(_dedup_events(fullday_rows)[["DowntimeDate", "CancelledInGap"]])
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
        reroute_rows = gap_rows[gap_rows["RerouteMachine"].notna()].copy()
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

    # --- Pre-aggregated data for drill-down ---
    gaps_agg = {
        "yearly": _build_yearly_summary(df_all_filtered),
        "daily": _build_daily_summary(df_all_filtered),
    }

    trend_data = _build_trend_data(df)
    patient_impact_data = _build_patient_impact_data(df)
    detail_records = _build_detail_table(df)

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

    return (
        kpi_children,
        narrative,
        gaps_agg,
        trend_data,
        patient_impact_data,
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
    s = idx_to_date(sv[0]).strftime("%Y-%m-%d")
    e_ts = idx_to_date(sv[1], end_of_month=True)
    today = pd.Timestamp.now().normalize()
    if e_ts > today:
        e_ts = today
    e = e_ts.strftime("%Y-%m-%d")
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
    Input(f"{PAGE_ID}-store-gaps-agg", "data"),
    Input(f"{PAGE_ID}-store-drill", "data"),
)


# ---------------------------------------------------------------------------
# Filter panel — disable note switch when min cancellations = 0,
# and update button label with active filter summary
# ---------------------------------------------------------------------------

clientside_callback(
    """function(minCancel) {
        return minCancel < 1;
    }""",
    Output(f"{PAGE_ID}-filter-require-note", "disabled"),
    Input(f"{PAGE_ID}-filter-min-cancellations", "value"),
)

clientside_callback(
    """function(rowTypes, gapThreshold, minCancel, reqNote, reqTerm) {
        var parts = [];
        // Row types: show only if not all 4 selected
        if (rowTypes && rowTypes.length < 4) {
            var labels = {Gap: "Intraday", StartOfDay: "SOD", EndOfDay: "EOD", FullDay: "Full Day"};
            parts.push(rowTypes.map(function(r) { return labels[r] || r; }).join("+"));
        }
        if (gapThreshold && gapThreshold > 0) parts.push("≥" + gapThreshold + "m");
        if (minCancel && minCancel > 0) parts.push(minCancel + "+ cancels");
        if (reqNote) parts.push("noted");
        if (reqTerm) parts.push("terminated");
        if (parts.length === 0) return "Filters";
        return "Filters: " + parts.join(" · ");
    }""",
    Output(f"{PAGE_ID}-filter-trigger-label", "children"),
    Input(f"{PAGE_ID}-filter-rowtype", "value"),
    Input(f"{PAGE_ID}-filter-gap-threshold", "value"),
    Input(f"{PAGE_ID}-filter-min-cancellations", "value"),
    Input(f"{PAGE_ID}-filter-require-note", "checked"),
    Input(f"{PAGE_ID}-filter-require-termination", "checked"),
)


# ---------------------------------------------------------------------------
# Level 3 timeline data callback
# ---------------------------------------------------------------------------

@callback(
    Output(f"{PAGE_ID}-store-timeline", "data"),
    Input(f"{PAGE_ID}-store-drill", "data"),
    Input(f"{PAGE_ID}-filter-machine", "value"),
    Input(f"{PAGE_ID}-filter-rowtype", "value"),
    Input(f"{PAGE_ID}-filter-gap-threshold", "value"),
    Input(f"{PAGE_ID}-filter-min-cancellations", "value"),
    Input(f"{PAGE_ID}-filter-require-note", "checked"),
    Input(f"{PAGE_ID}-filter-require-termination", "checked"),
    prevent_initial_call=True,
)
def load_timeline_data(drill, machines, row_types, gap_threshold, min_cancel, req_note, req_term):
    if not drill or drill.get("level") != 3:
        return no_update

    year, month, day = drill["year"], drill["month"], drill["day"]
    if not all([year, month, day]):
        return no_update

    target_date = pd.Timestamp(year, month, day)

    # Load gaps for this day (with lifespan filter to exclude pre-commission FullDay rows)
    from data.loader import load_downtime_gaps, load_downtime_fields_for_date
    gaps = _compute_downtime_type(_compute_local_confidence(_propagate_event_note(load_downtime_gaps())))
    day_gaps = gaps[gaps["DowntimeDate"].dt.normalize() == target_date]
    day_gaps = _filter_gaps(
        day_gaps, machines, row_types, gap_threshold or 0,
        slider_val=None,
        min_cancellations=min_cancel, require_note=req_note,
        require_termination=req_term,
    )
    gap_rows = day_gaps

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
            gap_list.append({
                "machine": machine,
                "start": "" if is_fullday else start_s,
                "end": "" if is_fullday else end_s,
                "minutes": int(first["GapMinutes"]) if pd.notna(first.get("GapMinutes")) else (600 if is_fullday else 0),
                "fullDay": is_fullday,
                "confidence": first.get("LocalConfidence") or first.get("DowntimeConfidence", "Low"),
                "cancelled": cancelled,
                "errors": int(first["MachineErrorsNearGap"]) if pd.notna(first.get("MachineErrorsNearGap")) else 0,
                "prevPatient": str(first.get("PrevPatientName", "")) if pd.notna(first.get("PrevPatientName")) else "",
                "nextPatient": str(first.get("NextPatientName", "")) if pd.notna(first.get("NextPatientName")) else "",
                "reroute": str(first["RerouteMachine"]) if pd.notna(first.get("RerouteMachine")) else "",
                "outcomes": outcome_counts,
                "notes": note_reasons,
            })

    # Serialize fields
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
    Input(f"{PAGE_ID}-filter-gap-threshold", "value"),
    prevent_initial_call=True,
)

# Timeline strip renderer (clientside)
clientside_callback(
    ClientsideFunction("machinesDowntime", "renderTimelineStrip"),
    Output(f"{PAGE_ID}-timeline-svg-container", "children"),
    Input(f"{PAGE_ID}-store-timeline", "data"),
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
    State(f"{PAGE_ID}-chart-patient-impact", "figure"),
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
    Input(f"{PAGE_ID}-filter-rowtype", "value"),
    Input(f"{PAGE_ID}-filter-gap-threshold", "value"),
    Input(f"{PAGE_ID}-interval", "n_intervals"),
    Input(f"{PAGE_ID}-filter-min-cancellations", "value"),
    Input(f"{PAGE_ID}-filter-require-note", "checked"),
    Input(f"{PAGE_ID}-filter-require-termination", "checked"),
)
def update_strip_data(strip_range, machines, row_types, gap_threshold, _n, min_cancel, req_note, req_term):
    from data.loader import load_downtime_gaps, load_treatment_detail

    td = load_treatment_detail()
    if td.empty:
        return {"machines": [], "colors": {}, "data": {}}

    last_date = td["ScheduledDateTime"].dt.normalize().max()
    range_map = {
        "3mo": timedelta(days=90),
        "6mo": timedelta(days=182),
        "1yr": timedelta(days=365),
        "3yr": timedelta(days=365 * 3),
    }
    start_date = last_date - range_map.get(strip_range, timedelta(days=365 * 25))
    end_date = last_date

    # Load and filter gaps for overlay
    gaps_df = _compute_downtime_type(_compute_local_confidence(_propagate_event_note(load_downtime_gaps())))
    if not gaps_df.empty:
        gaps_df = _filter_gaps(gaps_df, machines, row_types, gap_threshold, slider_val=None,
                               min_cancellations=min_cancel, require_note=req_note,
                               require_termination=req_term)
        gaps_df = gaps_df[(gaps_df["DowntimeDate"] >= start_date) & (gaps_df["DowntimeDate"] <= end_date)]

    return _build_strip_data(gaps_df, machines, start_date, end_date)


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
