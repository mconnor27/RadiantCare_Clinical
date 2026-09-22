"""EOT Audit page — end-of-treatment documentation compliance.

One row per patient-course from EndOfTreatment_Documentation.sql: did the
treatment summary get written, who wrote it, and how long did it take.
The note is due @GraceDays (30) after the last fraction, so every lag and
overdue metric on this page runs on the same clock (DaysAfterLastTx /
DaysUndocumented, both anchored on the last fraction).
"""

import dash
import dash_mantine_components as dmc
from dash import callback, Input, Output, State, dcc, html, clientside_callback, ClientsideFunction
from dash_iconify import DashIconify
import plotly.graph_objects as go
import pandas as pd

from config.settings import (
    DEPARTMENTS, DEPARTMENT_COLORS, PRIMARY, NEUTRAL, PHI_MODE,
    SEMANTIC_COLORS, CHART_COLORWAY, CHART_PAPER_HEIGHT,
)
from components.filter_bar import department_chips, physician_short_name
from components.kpi_card import kpi_card, kpi_placeholder
from components.chart_card import chart_card, register_chart_callbacks
from components.detail_table import detail_table
from components.phi import apply_phi_grid_rules
from utils.charts import apply_default_layout, empty_figure, full_period_range
from utils.tables import sanitize_for_grid
from utils.date_slider import (
    month_idx, idx_to_date, MAX_IDX,
    preset_to_slider_val, preset_to_exact_dates,
)

dash.register_page(__name__, path="/eot-audit", name="EOT Audit", order=12)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
import datetime as _dt

_DEFAULT_DATE_PRESET = "12mo"
_GRACE_DAYS = 30

# The warehouse's first End of Treatment note is dated 2021-08-01, so the
# timeline floors there — a slider reaching back to 2004 would be 17 years
# of guaranteed emptiness. The feed's single July-2021 course (last fraction
# 07/14, completed after the floor) is deliberately clipped with it: one
# course makes a meaningless 0% trend point.
_EOT_MIN_IDX = month_idx(2021, 8)
_EOT_SLIDER_MARKS = (
    [{"value": _EOT_MIN_IDX, "label": "'21"}]
    + [{"value": month_idx(y, 1), "label": f"'{y % 100:02d}"}
       for y in range(2022, _dt.date.today().year + 1)]
)


def _clamp_slider(val):
    """Clamp a [start, end] slider value to the EOT floor."""
    if not val or len(val) != 2:
        return val
    return [max(_EOT_MIN_IDX, val[0]), max(_EOT_MIN_IDX, val[1])]

_STATUS_COLORS = {
    "Documented": SEMANTIC_COLORS["success"],
    "Pending": SEMANTIC_COLORS["warning"],
    "Missing": SEMANTIC_COLORS["error"],
    "Reopened": "#1976D2",
    "Waived": "#9E9E9E",
}

# Local overrides (reviews_db.eot_overrides) rewrite DocStatus before any
# metric sees it: an open course can be Waived (excluded from open sets AND
# from compliance denominators — "no note needed"), a documented one can be
# Reopened (back in the open sets, counts as not-done). If the feed later
# resolves the underlying course (e.g. a waived MISSING gets its note), the
# override no longer matches its precondition and is ignored.
_OPEN_STATUSES = ("Missing", "Pending", "Reopened")

# Site-level placeholder treating physicians (loader renders ARIA's
# "Physician, Centralia" as "Centralia MD"). The Generic-MD toggle can
# resolve these to the oncologist of record or the note's author.
_GENERIC_MDS = ("Centralia MD", "Aberdeen MD", "Lacey MD")


def _resolve_generic_mds(df, mode):
    """Replace generic 'X MD' treating physicians with a real name.

    mode 'author' resolves via the documenting MD (AuthorName — who signed
    the treatment summary), falling back to PrimaryOncologist for the rare
    note-less generic row; together those attribute every placeholder in
    the current data. A value is only used when it's a real 'Last, First'
    name — '(none on file)' or another site generic keeps the original.
    (ConsultPhysician from Courses.csv was tried and rejected: it carries
    the same site placeholder for these courses — same billing root cause
    that made the SQL's treating cascade go generic.)
    """
    if mode in (None, "keep") or "TreatingPhysician" not in df.columns:
        return df
    generic = df["TreatingPhysician"].isin(_GENERIC_MDS)
    if not generic.any():
        return df

    def _valid(src):
        return (src.str.contains(", ", regex=False)
                & ~src.str.startswith("(")
                & ~src.isin(_GENERIC_MDS))

    df = df.copy()
    remaining = generic
    for col in ("AuthorName", "PrimaryOncologist"):
        if not remaining.any():
            break
        if col not in df.columns:
            continue
        src = df[col].fillna("")
        mask = remaining & _valid(src)
        df.loc[mask, "TreatingPhysician"] = src[mask]
        remaining = remaining & ~mask
    return df

_AGING_BUCKETS = ["0–30", "31–60", "61–90", "90+"]
_AGING_COLORS = {
    "0–30": SEMANTIC_COLORS["warning"],
    "31–60": "#FB8C00",
    "61–90": SEMANTIC_COLORS["error"],
    "90+": "#7B1FA2",
}


# ---------------------------------------------------------------------------
# Filter Bar
# ---------------------------------------------------------------------------

def _build_eot_filter_bar():
    """Two-row filter bar matching the OTV Audit page pattern."""
    return dmc.Paper(
        children=[
            # Row 1: dimension filters
            dmc.Group(
                children=[
                    department_chips("eot"),
                    # Treating physician chip dropdown
                    html.Div(
                        children=[
                            html.Div(
                                children=[
                                    dmc.Button(
                                        "Physician",
                                        id="eot-physician-trigger",
                                        variant="default",
                                        size="sm",
                                        rightSection=DashIconify(icon="mdi:chevron-down", width=14),
                                    ),
                                    dmc.ActionIcon(
                                        DashIconify(icon="mdi:close-circle", width=18),
                                        id="eot-physician-clear",
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
                                        id="eot-filter-physician",
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
                    # Resolve site-placeholder treating MDs to a real name
                    dmc.Group(
                        children=[
                            dmc.Text("Generic MD", size="xs", c="#6B7280", fw=500),
                            dmc.SegmentedControl(
                                id="eot-generic-md",
                                data=[
                                    {"value": "keep", "label": "Keep"},
                                    {"value": "author", "label": "Documenting"},
                                ],
                                value="keep",
                                size="xs",
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
            # Row 2: date controls (filter on last treatment date)
            dmc.Group(
                children=[
                    dmc.Select(
                        id="eot-filter-date-preset",
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
                            id="eot-filter-daterange",
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
                            html.Div(id="eot-date-range-label", style={"display": "none"}),
                            dmc.RangeSlider(
                                id="eot-date-slider",
                                min=_EOT_MIN_IDX,
                                max=MAX_IDX,
                                step=1,
                                value=preset_to_slider_val(_DEFAULT_DATE_PRESET, MAX_IDX),
                                marks=_EOT_SLIDER_MARKS,
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
        dmc.Box(
            className="page-sticky-header",
            children=[
                dmc.Title("EOT Audit", order=2, className="page-title",
                          style={"margin": 0, "textAlign": "center"}),
                html.Div(
                    style={"position": "relative"},
                    children=[
                        _build_eot_filter_bar(),
                        html.Div(
                            id="eot-grid-filter-badge",
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

        # KPI row
        dmc.Grid(gutter="md", children=[
            dmc.GridCol(kpi_placeholder(), id="eot-kpi-completed", span={"base": 6, "md": 2.4}),
            dmc.GridCol(kpi_placeholder(), id="eot-kpi-open", span={"base": 6, "md": 2.4}),
            dmc.GridCol(kpi_placeholder(), id="eot-kpi-documented", span={"base": 6, "md": 2.4}),
            dmc.GridCol(kpi_placeholder(), id="eot-kpi-ontime", span={"base": 6, "md": 2.4}),
            dmc.GridCol(kpi_placeholder(), id="eot-kpi-median", span={"base": 6, "md": 2.4}),
        ]),

        # Charts row 1: compliance trend + physician breakdown
        dmc.Grid(gutter="md", children=[
            dmc.GridCol(
                chart_card(
                    "eot-chart-trend",
                    "Documentation Compliance Trend",
                    chart_types=[
                        {"value": "line", "label": "Line"},
                        {"value": "area", "label": "Area"},
                        {"value": "bar", "label": "Bar"},
                    ],
                    show_smooth=True,
                    smooth_max=12,
                    smooth_default=0,
                    show_grouping=False,
                    settings_id="eot-trend",
                    extra_controls=[
                        dmc.SegmentedControl(
                            id="eot-trend-metric",
                            data=[
                                {"value": "ontime", "label": "On-Time %"},
                                {"value": "done", "label": "Documented %"},
                                {"value": "lag", "label": "Median Days"},
                            ],
                            value="ontime",
                            size="xs",
                        ),
                        dmc.SegmentedControl(
                            id="eot-trend-agg",
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
                span={"base": 12, "md": 6},
            ),
            dmc.GridCol(
                chart_card(
                    "eot-chart-physician",
                    "By Treating Physician",
                    chart_types=None,
                    show_smooth=False,
                    settings_id="eot-phys",
                    extra_controls=[
                        dmc.SegmentedControl(
                            id="eot-phys-mode",
                            data=[
                                {"value": "open", "label": "Open Tasks"},
                                {"value": "done", "label": "Documented %"},
                                {"value": "ontime", "label": "On-Time %"},
                                {"value": "lag", "label": "Median Days"},
                            ],
                            value="open",
                            size="xs",
                        ),
                    ],
                ),
                span={"base": 12, "md": 6},
            ),
        ]),

        # Charts row 2: lag distribution + open-task aging
        dmc.Grid(gutter="md", children=[
            dmc.GridCol(
                chart_card(
                    "eot-chart-lagdist",
                    "Days From Last Fraction to Note",
                    chart_types=None,
                    show_smooth=False,
                    settings_id="eot-lagdist",
                    extra_controls=[
                        dmc.SegmentedControl(
                            id="eot-lagdist-mode",
                            data=[
                                {"value": "all", "label": "All"},
                                {"value": "treating", "label": "Treating MD"},
                                {"value": "author", "label": "Author MD"},
                            ],
                            value="all",
                            size="xs",
                        ),
                    ],
                ),
                span={"base": 12, "md": 6},
            ),
            dmc.GridCol(
                chart_card(
                    "eot-chart-aging",
                    "Open-Task Aging",
                    chart_types=None,
                    show_smooth=False,
                    settings_id="eot-aging",
                    extra_controls=[
                        dmc.SegmentedControl(
                            id="eot-aging-slice",
                            data=[
                                {"value": "physician", "label": "MD"},
                                {"value": "department", "label": "Dept"},
                            ],
                            value="physician",
                            size="xs",
                        ),
                    ],
                ),
                span={"base": 12, "md": 6},
            ),
        ]),

        # Worklist table
        detail_table(
            "eot-detail-grid",
            title="Documentation Worklist",
            export_id="eot-table-export",
            extra_controls=[
                dmc.SegmentedControl(
                    id="eot-table-status",
                    data=[
                        {"value": "open", "label": "All Open"},
                        {"value": "Missing", "label": "Missing"},
                        {"value": "Pending", "label": "Pending"},
                        {"value": "Documented", "label": "Documented"},
                        {"value": "Waived", "label": "Waived"},
                        {"value": "all", "label": "All Items"},
                    ],
                    value="open",
                    size="xs",
                ),
                dmc.Select(
                    id="eot-table-md",
                    data=[],
                    placeholder="Per MD…",
                    clearable=True,
                    searchable=True,
                    size="xs",
                    w=130,
                    comboboxProps={"zIndex": 500},
                ),
                dmc.Button(
                    "Clear Filters",
                    id="eot-table-clear-filters",
                    size="compact-xs",
                    variant="light",
                    color="red",
                    leftSection=DashIconify(icon="mdi:filter-remove", width=14),
                    style={"display": "none"},
                ),
            ],
        ),

        # Stores
        dcc.Store(id="eot-store-kpi-sparklines"),
        dcc.Store(id="eot-store-filtered-dff"),
        dcc.Store(id="eot-store-prior-dff"),
        dcc.Store(id="eot-store-meta"),
        dcc.Store(id="eot-table-filter-rows"),
        dcc.Store(id="eot-store-overrides"),        # {CourseKey: waived|reopened}
        dcc.Store(id="eot-store-override-action"),  # set by EotOverrideButtons JS
        dcc.Interval(id="eot-interval", interval=300_000, n_intervals=0, max_intervals=0),  # fires once on mount; no background refresh (daily data + global refresh button)
    ],
)

# Register gear-icon toggle + PNG export for chart cards
register_chart_callbacks([
    ("eot-trend", "eot-chart-trend"),
    ("eot-phys", "eot-chart-physician"),
    ("eot-lagdist", "eot-chart-lagdist"),
    ("eot-aging", "eot-chart-aging"),
])


# ---------------------------------------------------------------------------
# Date Filter Sync Callbacks
# ---------------------------------------------------------------------------

# A) Preset -> Slider + DatePicker
@callback(
    Output("eot-date-slider", "value", allow_duplicate=True),
    Output("eot-filter-daterange", "start_date", allow_duplicate=True),
    Output("eot-filter-daterange", "end_date", allow_duplicate=True),
    Input("eot-filter-date-preset", "value"),
    prevent_initial_call=True,
)
def _sync_preset(preset):
    if not preset or preset == "custom":
        return (dash.no_update,) * 3
    sv = _clamp_slider(preset_to_slider_val(preset, MAX_IDX))
    s, e = preset_to_exact_dates(preset)
    if preset == "all":
        # "All Time" floors at the first EOT note, not 2004
        s = idx_to_date(_EOT_MIN_IDX).strftime("%Y-%m-%d")
    return sv, s, e


# B) Slider -> DatePicker + Label (clientside)
clientside_callback(
    ClientsideFunction(namespace="eotDateSlider", function_name="syncSlider"),
    Output("eot-filter-daterange", "start_date", allow_duplicate=True),
    Output("eot-filter-daterange", "end_date", allow_duplicate=True),
    Output("eot-date-range-label", "children"),
    Input("eot-date-slider", "value"),
    State("eot-filter-daterange", "start_date"),
    State("eot-filter-daterange", "end_date"),
    prevent_initial_call=True,
)


# C) DatePicker -> Slider
@callback(
    Output("eot-date-slider", "value", allow_duplicate=True),
    Input("eot-filter-daterange", "start_date"),
    Input("eot-filter-daterange", "end_date"),
    State("eot-date-slider", "value"),
    prevent_initial_call=True,
)
def _sync_picker_to_slider(start, end, current_slider):
    if not start or not end:
        return dash.no_update
    s = pd.Timestamp(start)
    e = pd.Timestamp(end)
    new_val = _clamp_slider([month_idx(s.year, s.month), month_idx(e.year, e.month)])
    if new_val == current_slider:
        return dash.no_update
    return new_val


# D) Slider -> auto-clear preset
@callback(
    Output("eot-filter-date-preset", "value", allow_duplicate=True),
    Input("eot-date-slider", "value"),
    State("eot-filter-date-preset", "value"),
    prevent_initial_call=True,
)
def _maybe_clear_preset(slider_val, current_preset):
    if not current_preset or current_preset == "custom":
        return dash.no_update
    expected = _clamp_slider(preset_to_slider_val(current_preset, MAX_IDX))
    if slider_val == expected:
        return dash.no_update
    return "custom"


# ---------------------------------------------------------------------------
# Physician Filter — UI callbacks
# ---------------------------------------------------------------------------

clientside_callback(
    """function(val) {
        if (!val) return "Physician";
        return val.split(", ")[0];
    }""",
    Output("eot-physician-trigger", "children"),
    Input("eot-filter-physician", "value"),
)

clientside_callback(
    """function(val) { return val ? {"display": "inline-flex"} : {"display": "none"}; }""",
    Output("eot-physician-clear", "style"),
    Input("eot-filter-physician", "value"),
)

clientside_callback(
    """function(n) { return null; }""",
    Output("eot-filter-physician", "value", allow_duplicate=True),
    Input("eot-physician-clear", "n_clicks"),
    prevent_initial_call=True,
)


@callback(
    Output("eot-filter-physician", "children"),
    Output("eot-filter-physician", "value"),
    Input("eot-interval", "n_intervals"),
    Input("eot-date-slider", "value"),
    Input("eot-filter-department", "value"),
    Input("eot-generic-md", "value"),
    State("eot-filter-physician", "value"),
)
def _populate_physician_chips(_n, slider_val, departments, generic_md, current_val):
    from data.loader import load_eot

    try:
        df = load_eot()
    except Exception:
        return [], None
    if df.empty or "TreatingPhysician" not in df.columns:
        return [], None

    if "DocStatus" in df.columns:
        df = df[df["DocStatus"] != "Active"]
    df = _resolve_generic_mds(df, generic_md)

    if "LastTxDate" in df.columns:
        start, end = _get_date_range(slider_val, None)
        df = df[df["LastTxDate"].notna() & (df["LastTxDate"] >= start) & (df["LastTxDate"] <= end)]

    all_depts = set(DEPARTMENTS)
    if departments and "Department" in df.columns and set(departments) != all_depts:
        df = df[df["Department"].isin(departments)]

    mds = sorted(df["TreatingPhysician"].dropna().unique())
    chips = [
        dmc.Chip(physician_short_name(md), value=md, size="xs", variant="filled")
        for md in mds
    ]

    clear_val = dash.no_update
    if current_val and current_val not in mds:
        clear_val = None

    return chips, clear_val


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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


def _apply_grid_row_filter(dff, grid_rows):
    """Filter dff to only rows matching the grid's visible row indices."""
    if grid_rows is None or dff is None or dff.empty:
        return dff
    idx_set = set(int(i) for i in grid_rows)
    return dff.loc[dff.index.isin(idx_set)]


def _trend(curr, prior, invert=False):
    """Compute trend % and direction."""
    if prior is None or prior == 0:
        return None, None
    pct = (curr - prior) / abs(prior) * 100
    direction = ("down" if pct > 0 else "up") if invert else ("up" if pct > 0 else "down")
    return f"{abs(pct):.0f}%", direction


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

_DATE_COLS = ("LastTxDate", "FirstTxDate", "DueDate", "CompletionDate", "EOTNoteDateTime")

# Columns shipped to the client store — everything the KPIs, charts and
# worklist read. Keeps the store payload light.
_STORE_COLS = [
    "CourseKey", "PatientId", "PatientFullName", "PatientCode", "CourseName",
    "Modality", "Department", "TreatingPhysician", "PrimaryOncologist",
    "DocumentationStatus", "DocStatus", "IsOpenTask", "DueDate",
    "FirstTxDate", "LastTxDate", "DeliveredFractions", "FractionsPrescribed",
    "ClinicalStatus", "CompletionDate", "CompletionBasis", "EOTNoteDateTime",
    "EOTNoteCount", "AuthorName", "AuthorIsPrimaryOnc",
    "AuthorIsTreatingPhysician", "DaysAfterLastTx", "DaysUndocumented",
    "ElapsedDays",
]


def _records_to_df(records):
    """Reconstruct a DataFrame from store records, parsing date columns."""
    if not records:
        return pd.DataFrame()
    df = pd.DataFrame.from_records(records)
    for col in _DATE_COLS:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")
    return df


def _ontime_mask(df):
    """Documented within the 30-day grace window (last fraction -> note)."""
    if "DocStatus" not in df.columns or "DaysAfterLastTx" not in df.columns:
        return pd.Series(False, index=df.index)
    lag = pd.to_numeric(df["DaysAfterLastTx"], errors="coerce")
    return (df["DocStatus"] == "Documented") & (lag <= _GRACE_DAYS)


def _resolved_mask(df):
    """Courses with a final verdict — Documented, Missing, or Reopened
    (a reopened note counts as not-done). Pending is still inside its
    writing window and can't be judged yet; Waived is excluded entirely."""
    if "DocStatus" not in df.columns:
        return pd.Series(False, index=df.index)
    return df["DocStatus"].isin(["Documented", "Missing", "Reopened"])


# ---------------------------------------------------------------------------
# Overrides — load on mount, persist button actions (reviews_db.eot_overrides)
# ---------------------------------------------------------------------------
@callback(
    Output("eot-store-overrides", "data"),
    Input("eot-interval", "n_intervals"),
)
def _load_overrides(_n):
    from data.reviews_db import get_all_eot_overrides
    try:
        return get_all_eot_overrides()
    except Exception:
        return {}


@callback(
    Output("eot-store-overrides", "data", allow_duplicate=True),
    Input("eot-store-override-action", "data"),
    State("eot-store-overrides", "data"),
    prevent_initial_call=True,
)
def _handle_override(action, overrides):
    from data.reviews_db import set_eot_override, remove_eot_override

    if not action or action.get("CourseKey") is None:
        return dash.no_update
    key = str(action["CourseKey"])
    act = action.get("_action")
    overrides = dict(overrides or {})
    if act == "waive":
        set_eot_override(key, "waived")
        overrides[key] = "waived"
    elif act == "reopen":
        set_eot_override(key, "reopened")
        overrides[key] = "reopened"
    elif act == "undo":
        remove_eot_override(key)
        overrides.pop(key, None)
    else:
        return dash.no_update
    return overrides


def _apply_overrides(df, overrides):
    """Rewrite DocStatus per local overrides; see _OPEN_STATUSES note."""
    if not overrides or "CourseKey" not in df.columns:
        return df
    ov = df["CourseKey"].astype(str).map(overrides)
    waive_mask = ov.eq("waived") & df["DocStatus"].isin(["Missing", "Pending"])
    reopen_mask = ov.eq("reopened") & df["DocStatus"].eq("Documented")
    if not waive_mask.any() and not reopen_mask.any():
        return df
    df = df.copy()
    df.loc[waive_mask, "DocStatus"] = "Waived"
    df.loc[reopen_mask, "DocStatus"] = "Reopened"
    # A reopened course is open again — restart its open-gap clock so the
    # worklist sort and aging buckets have a value to work with.
    if reopen_mask.any() and "LastTxDate" in df.columns:
        today = pd.Timestamp.now().normalize()
        df.loc[reopen_mask, "DaysUndocumented"] = (
            today - df.loc[reopen_mask, "LastTxDate"]).dt.days
    return df


# ---------------------------------------------------------------------------
# Data Prep Callback — runs only when a true data filter changes
# ---------------------------------------------------------------------------
@callback(
    Output("eot-store-filtered-dff", "data"),
    Output("eot-store-prior-dff", "data"),
    Output("eot-store-meta", "data"),
    Input("eot-interval", "n_intervals"),
    Input("eot-date-slider", "value"),
    Input("eot-filter-date-preset", "value"),
    Input("eot-filter-department", "value"),
    Input("eot-filter-physician", "value"),
    Input("eot-store-overrides", "data"),
    Input("eot-generic-md", "value"),
    running=[
        (Output("eot-chart-trend-loading", "visible"), True, False),
        (Output("eot-chart-physician-loading", "visible"), True, False),
        (Output("eot-chart-lagdist-loading", "visible"), True, False),
        (Output("eot-chart-aging-loading", "visible"), True, False),
    ],
)
def _prep_data(_n, slider_val, date_preset, departments, physician, overrides, generic_md):
    from data.loader import load_eot

    empty_meta = {"date_preset": date_preset, "trend_label": None}
    _empty_return = ([], [], empty_meta)

    try:
        df = load_eot()
    except Exception:
        return _empty_return
    if df.empty:
        return _empty_return

    # Active courses carry no verdict — excluded from every compliance view
    # (the daily feed ships with @IncludeActiveParam = 'No' anyway).
    if "DocStatus" in df.columns:
        df = df[df["DocStatus"] != "Active"]

    df = _apply_overrides(df, overrides)
    df = _resolve_generic_mds(df, generic_md)

    if physician and "TreatingPhysician" in df.columns:
        df = df[df["TreatingPhysician"] == physician]

    all_depts = set(DEPARTMENTS)
    dept_filtered = departments and "Department" in df.columns and set(departments) != all_depts
    if dept_filtered:
        df = df[df["Department"].isin(departments)]

    base = df  # date-unfiltered, for the prior-period comparison

    start, end = _get_date_range(slider_val, None)
    if "LastTxDate" in df.columns:
        df = df[df["LastTxDate"].notna() & (df["LastTxDate"] >= start) & (df["LastTxDate"] <= end)]

    keep = [c for c in _STORE_COLS if c in df.columns]
    df = df[keep].reset_index(drop=True)

    # Prior period
    df_prior = pd.DataFrame()
    trend_label = None
    if date_preset and date_preset in _PRIOR_MAP and "LastTxDate" in base.columns:
        trend_label, prior_fn = _PRIOR_MAP[date_preset]
        prior_start, prior_end = prior_fn(start, end)
        df_prior = base[base["LastTxDate"].notna()]
        df_prior = df_prior[(df_prior["LastTxDate"] >= prior_start) & (df_prior["LastTxDate"] <= prior_end)]
        df_prior = df_prior[[c for c in _STORE_COLS if c in df_prior.columns]].reset_index(drop=True)

    meta = {
        "date_preset": date_preset,
        "trend_label": trend_label,
        "start": start.isoformat() if not df.empty else None,
        "end": end.isoformat() if not df.empty else None,
    }

    return (
        df.to_dict("records") if not df.empty else [],
        df_prior.to_dict("records") if not df_prior.empty else [],
        meta,
    )


# ---------------------------------------------------------------------------
# KPIs + sparklines
# ---------------------------------------------------------------------------
@callback(
    Output("eot-kpi-completed", "children"),
    Output("eot-kpi-open", "children"),
    Output("eot-kpi-documented", "children"),
    Output("eot-kpi-ontime", "children"),
    Output("eot-kpi-median", "children"),
    Output("eot-store-kpi-sparklines", "data"),
    Input("eot-store-filtered-dff", "data"),
    Input("eot-store-prior-dff", "data"),
    Input("eot-store-meta", "data"),
    Input("eot-table-filter-rows", "data"),
)
def _update_kpis(dff_records, prior_records, meta, grid_rows):
    na_kpi = kpi_card("--", "N/A")
    if not dff_records:
        return (na_kpi,) * 5 + (None,)

    df = _records_to_df(dff_records)
    if df.empty:
        return (na_kpi,) * 5 + (None,)

    dff = _apply_grid_row_filter(df, grid_rows)
    if dff.empty:
        return (na_kpi,) * 5 + (None,)

    df_prior = _records_to_df(prior_records or [])
    meta = meta or {}
    trend_label = meta.get("trend_label")
    start_iso = meta.get("start")
    end_iso = meta.get("end")

    def _stats(frame):
        total = len(frame)
        missing = (frame["DocStatus"] == "Missing").sum()
        pending = (frame["DocStatus"] == "Pending").sum()
        reopened = (frame["DocStatus"] == "Reopened").sum()
        open_ct = missing + pending + reopened
        documented = (frame["DocStatus"] == "Documented").sum()
        resolved = _resolved_mask(frame).sum()
        # "Did it get done at all" — any lag counts; Pending (still inside
        # its 30-day writing window) is excluded from the denominator.
        documented_rate = (documented / resolved * 100) if resolved > 0 else None
        ontime = _ontime_mask(frame).sum()
        ontime_rate = (ontime / resolved * 100) if resolved > 0 else None
        doc_lag = pd.to_numeric(
            frame.loc[frame["DocStatus"] == "Documented", "DaysAfterLastTx"],
            errors="coerce").dropna()
        median_days = doc_lag.median() if not doc_lag.empty else None
        return (total, missing, pending, reopened, open_ct,
                documented_rate, ontime_rate, median_days)

    (total, missing, pending, reopened, open_ct,
     documented_rate, ontime_rate, median_days) = _stats(dff)

    _t_total = (None, None)
    _t_open = (None, None)
    _t_documented = (None, None)
    _t_ontime = (None, None)
    _t_median = (None, None)
    if trend_label and not df_prior.empty:
        (p_total, _pm, _pp, _pr, p_open,
         p_documented, p_ontime, p_median) = _stats(df_prior)
        _t_total = _trend(total, p_total)
        _t_open = _trend(open_ct, p_open, invert=True)
        if documented_rate is not None and p_documented:
            _t_documented = _trend(documented_rate, p_documented)
        if ontime_rate is not None and p_ontime:
            _t_ontime = _trend(ontime_rate, p_ontime)
        if median_days is not None and p_median:
            _t_median = _trend(median_days, p_median, invert=True)

    kpi_completed = kpi_card(
        "Courses Completed", f"{total:,}",
        accent_color=PRIMARY,
        sparkline_id="eot-spark-completed",
        trend_text=f"{_t_total[0]} {trend_label}" if _t_total[0] else None,
        trend_direction=_t_total[1],
    )
    _open_detail = f"({missing:,} missing · {pending:,} pending"
    _open_detail += f" · {reopened:,} reopened)" if reopened else ")"
    kpi_open = kpi_card(
        "Open Tasks", f"{open_ct:,}",
        value_detail=_open_detail,
        accent_color=SEMANTIC_COLORS["error"] if missing else SEMANTIC_COLORS["warning"],
        sparkline_id="eot-spark-open",
        trend_text=f"{_t_open[0]} {trend_label}" if _t_open[0] else None,
        trend_direction=_t_open[1],
    )
    kpi_documented = kpi_card(
        "Documented Rate", f"{documented_rate:.1f}%" if documented_rate is not None else "--",
        value_detail="(any lag)",
        accent_color=SEMANTIC_COLORS["success"] if (documented_rate or 0) >= 95 else SEMANTIC_COLORS["warning"],
        sparkline_id="eot-spark-documented",
        trend_text=f"{_t_documented[0]} {trend_label}" if _t_documented[0] else None,
        trend_direction=_t_documented[1],
    )
    kpi_ontime = kpi_card(
        "On-Time Rate", f"{ontime_rate:.1f}%" if ontime_rate is not None else "--",
        accent_color=SEMANTIC_COLORS["success"] if (ontime_rate or 0) >= 90 else SEMANTIC_COLORS["warning"],
        sparkline_id="eot-spark-ontime",
        trend_text=f"{_t_ontime[0]} {trend_label}" if _t_ontime[0] else None,
        trend_direction=_t_ontime[1],
    )
    kpi_median = kpi_card(
        "Median Days to Note", f"{median_days:.0f}" if median_days is not None else "--",
        value_detail=f"(due {_GRACE_DAYS})",
        accent_color=SEMANTIC_COLORS["success"] if (median_days or 99) <= _GRACE_DAYS else SEMANTIC_COLORS["error"],
        sparkline_id="eot-spark-median",
        trend_text=f"{_t_median[0]} {trend_label}" if _t_median[0] else None,
        trend_direction=_t_median[1],
    )

    # --- Sparklines (grouped on the last-fraction date) ---
    sparkline_data = {}
    start = pd.Timestamp(start_iso) if start_iso else dff["LastTxDate"].min()
    end = pd.Timestamp(end_iso) if end_iso else dff["LastTxDate"].max()
    if pd.notna(start) and pd.notna(end):
        range_months = (end.year - start.year) * 12 + (end.month - start.month) + 1
    else:
        range_months = 12
    _spark_period = "D" if range_months <= 3 else "W"

    temp = dff[dff["LastTxDate"].notna()].copy()
    if not temp.empty:
        if _spark_period == "D":
            temp["_sp"] = temp["LastTxDate"].dt.normalize()
        else:
            temp["_sp"] = temp["LastTxDate"].dt.to_period("W").dt.to_timestamp()

        grp_total = temp.groupby("_sp").size()
        if len(grp_total) > 2:
            sparkline_data["completed"] = {
                "labels": [d.isoformat() for d in grp_total.index],
                "values": grp_total.tolist(),
                "color": PRIMARY,
            }

        open_temp = temp[temp["DocStatus"].isin(_OPEN_STATUSES)]
        if not open_temp.empty:
            grp_open = open_temp.groupby("_sp").size().reindex(grp_total.index, fill_value=0)
            if len(grp_open) > 2:
                sparkline_data["open"] = {
                    "labels": [d.isoformat() for d in grp_open.index],
                    "values": grp_open.tolist(),
                    "color": SEMANTIC_COLORS["error"],
                }

        res_temp = temp[_resolved_mask(temp)]
        if not res_temp.empty:
            res_totals = res_temp.groupby("_sp").size()
            ontime_flags = _ontime_mask(res_temp)
            grp_rate = ontime_flags.groupby(res_temp["_sp"]).sum() / res_totals * 100
            if len(grp_rate) > 2:
                sparkline_data["ontime"] = {
                    "labels": [d.isoformat() for d in grp_rate.index],
                    "values": [round(v, 1) for v in grp_rate.tolist()],
                    "color": SEMANTIC_COLORS["success"],
                    "hover_fmt": "%{x|%b %d}: %{customdata:.1f}%<extra></extra>",
                }
            done_flags = res_temp["DocStatus"] == "Documented"
            grp_done = done_flags.groupby(res_temp["_sp"]).sum() / res_totals * 100
            if len(grp_done) > 2:
                sparkline_data["documented"] = {
                    "labels": [d.isoformat() for d in grp_done.index],
                    "values": [round(v, 1) for v in grp_done.tolist()],
                    "color": PRIMARY,
                    "hover_fmt": "%{x|%b %d}: %{customdata:.1f}%<extra></extra>",
                }

        doc_temp = temp[temp["DocStatus"] == "Documented"].copy()
        if not doc_temp.empty:
            doc_temp["_lag"] = pd.to_numeric(doc_temp["DaysAfterLastTx"], errors="coerce")
            grp_med = doc_temp.groupby("_sp")["_lag"].median().dropna()
            if len(grp_med) > 2:
                sparkline_data["median"] = {
                    "labels": [d.isoformat() for d in grp_med.index],
                    "values": [round(v, 1) for v in grp_med.tolist()],
                    "color": CHART_COLORWAY[4],
                    "hover_fmt": "%{x|%b %d}: %{customdata:.0f} days<extra></extra>",
                }

    return kpi_completed, kpi_open, kpi_documented, kpi_ontime, kpi_median, sparkline_data


# ---------------------------------------------------------------------------
# Per-chart callbacks
# ---------------------------------------------------------------------------
@callback(
    Output("eot-chart-trend", "figure"),
    Input("eot-store-filtered-dff", "data"),
    Input("eot-table-filter-rows", "data"),
    Input("eot-trend-settings-type", "value"),
    Input("eot-trend-metric", "value"),
    Input("eot-trend-agg", "value"),
    Input("eot-trend-settings-smooth", "value"),
    running=[(Output("eot-chart-trend-loading", "visible"), True, False)],
)
def _update_trend_chart(dff_records, grid_rows, chart_type, metric, agg, smooth):
    df = _records_to_df(dff_records)
    if df.empty:
        return empty_figure("No data")
    df = _apply_grid_row_filter(df, grid_rows)
    return _build_trend_chart(df, metric or "ontime", chart_type or "line", agg or "M", smooth or 0)


@callback(
    Output("eot-chart-physician", "figure"),
    Input("eot-store-filtered-dff", "data"),
    Input("eot-table-filter-rows", "data"),
    Input("eot-phys-mode", "value"),
    Input("eot-phys-settings-stack", "value"),
    running=[(Output("eot-chart-physician-loading", "visible"), True, False)],
)
def _update_physician_chart(dff_records, grid_rows, mode, stack_mode):
    df = _records_to_df(dff_records)
    if df.empty:
        return empty_figure("No data")
    df = _apply_grid_row_filter(df, grid_rows)
    return _build_physician_chart(df, mode or "open", stack_mode or "stacked")


@callback(
    Output("eot-chart-lagdist", "figure"),
    Input("eot-store-filtered-dff", "data"),
    Input("eot-table-filter-rows", "data"),
    Input("eot-lagdist-mode", "value"),
    Input("eot-lagdist-settings-stack", "value"),
    running=[(Output("eot-chart-lagdist-loading", "visible"), True, False)],
)
def _update_lagdist_chart(dff_records, grid_rows, mode, stack_mode):
    df = _records_to_df(dff_records)
    if df.empty:
        return empty_figure("No data")
    df = _apply_grid_row_filter(df, grid_rows)
    return _build_lagdist_chart(df, mode or "all", stack_mode or "stacked")


@callback(
    Output("eot-chart-aging", "figure"),
    Input("eot-store-filtered-dff", "data"),
    Input("eot-table-filter-rows", "data"),
    Input("eot-aging-slice", "value"),
    Input("eot-aging-settings-stack", "value"),
    running=[(Output("eot-chart-aging-loading", "visible"), True, False)],
)
def _update_aging_chart(dff_records, grid_rows, slice_by, stack_mode):
    df = _records_to_df(dff_records)
    if df.empty:
        return empty_figure("No data")
    df = _apply_grid_row_filter(df, grid_rows)
    return _build_aging_chart(df, slice_by or "physician", stack_mode or "stacked")


# ---------------------------------------------------------------------------
# Worklist table — ignores grid-row filter so the table isn't trimmed by its
# own column filters.
# ---------------------------------------------------------------------------
@callback(
    Output("eot-detail-grid", "rowData"),
    Output("eot-detail-grid", "columnDefs"),
    Input("eot-store-filtered-dff", "data"),
    Input("eot-table-status", "value"),
    Input("eot-table-md", "value"),
)
def _update_table_cb(dff_records, status_filter, md):
    df = _records_to_df(dff_records)
    if df.empty:
        return [], []
    return _build_table(df, status_filter or "open", md)


@callback(
    Output("eot-table-md", "data"),
    Input("eot-store-filtered-dff", "data"),
)
def _populate_table_md_options(dff_records):
    df = _records_to_df(dff_records)
    if df.empty or "TreatingPhysician" not in df.columns:
        return []
    mds = sorted(df["TreatingPhysician"].dropna().unique())
    return [{"value": md, "label": physician_short_name(md)} for md in mds]


# ---------------------------------------------------------------------------
# KPI Sparkline clientside callbacks
# ---------------------------------------------------------------------------

_EOT_SPARKLINE_IDS = [
    "eot-spark-completed",
    "eot-spark-open",
    "eot-spark-documented",
    "eot-spark-ontime",
    "eot-spark-median",
]

for _spark_id in _EOT_SPARKLINE_IDS:
    clientside_callback(f"""function() {{
        var fig = window.dash_clientside.sparklines.updateFromStore.apply(null, arguments);
        return window.dash_clientside.chartDeferred.wrap("{_spark_id}", fig);
    }}""",
        Output(_spark_id, "figure"),
        Input("eot-store-kpi-sparklines", "data"),
        Input(_spark_id, "id"),
        prevent_initial_call=True,
    )


# ---------------------------------------------------------------------------
# Grid filter → chart sync
# ---------------------------------------------------------------------------

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
    Output("eot-table-filter-rows", "data"),
    Output("eot-grid-filter-badge", "style"),
    Output("eot-table-clear-filters", "style"),
    Input("eot-detail-grid", "virtualRowData"),
    State("eot-detail-grid", "rowData"),
    State("eot-table-filter-rows", "data"),
    prevent_initial_call=True,
)

clientside_callback(
    """function(n) {
        if (!n) return window.dash_clientside.no_update;
        return {};
    }""",
    Output("eot-detail-grid", "filterModel"),
    Input("eot-table-clear-filters", "n_clicks"),
    prevent_initial_call=True,
)

clientside_callback(
    """function(n) {
        if (!n) return window.dash_clientside.no_update;
        var el = document.getElementById('eot-detail-grid');
        if (el) el.scrollIntoView({behavior: 'smooth', block: 'start'});
        return window.dash_clientside.no_update;
    }""",
    Output("eot-grid-filter-badge", "n_clicks"),
    Input("eot-grid-filter-badge", "n_clicks"),
    prevent_initial_call=True,
)

# Export CSV
clientside_callback(
    """function(n) {
        if (!n) return window.dash_clientside.no_update;
        gridExportCsv('eot-detail-grid', 'eot_worklist.csv');
        return window.dash_clientside.no_update;
    }""",
    Output("eot-table-export", "n_clicks"),
    Input("eot-table-export", "n_clicks"),
    prevent_initial_call=True,
)


# ---------------------------------------------------------------------------
# Chart Builders
# ---------------------------------------------------------------------------

def _build_trend_chart(df, metric="ontime", chart_type="line", agg="M", smooth=0):
    """On-time documentation rate (or median lag) over time by last fraction."""
    if "LastTxDate" not in df.columns or "DocStatus" not in df.columns:
        return empty_figure("No trend data")

    df = df[df["LastTxDate"].notna()].copy()
    if df.empty:
        return empty_figure("No trend data")
    df["_period"] = df["LastTxDate"].dt.to_period(agg).dt.to_timestamp()

    all_periods = full_period_range(df["_period"], agg)

    if metric == "lag":
        doc = df[df["DocStatus"] == "Documented"].copy()
        if doc.empty:
            return empty_figure("No documented courses in range")
        doc["_lag"] = pd.to_numeric(doc["DaysAfterLastTx"], errors="coerce")
        series = doc.groupby("_period")["_lag"].median().reindex(all_periods)
        y_title = "Median Days to Note"
        hover = "%{x|%b %Y}: %{y:.0f} days<extra></extra>"
        y_range = None
    else:
        # Both rate metrics share the resolved denominator (Documented +
        # Missing) — Pending courses are still inside their 30-day writing
        # window and can't be judged either way yet.
        resolved = df[_resolved_mask(df)]
        if resolved.empty:
            return empty_figure("No resolved courses in range")
        total = resolved.groupby("_period").size().reindex(all_periods, fill_value=0)
        if metric == "done":
            # Documented at all — any lag counts
            flags = resolved["DocStatus"] == "Documented"
            y_title = "Documented %"
        else:
            flags = _ontime_mask(resolved)
            y_title = "On-Time %"
        numer = flags.groupby(resolved["_period"]).sum().reindex(all_periods, fill_value=0)
        series = (numer / total * 100).where(total > 0)
        hover = "%{x|%b %Y}: %{y:.1f}%<extra></extra>"
        y_range = [0, 105]

    y = [None if pd.isna(v) else v for v in series.tolist()]
    if smooth and smooth > 0 and len(y) > 3:
        window = min(int(smooth), len(y) - 1)
        if window >= 2:
            s = pd.Series(y, dtype="float64")
            smoothed = s.rolling(window, min_periods=1, center=True).mean().tolist()
            y = [None if orig is None or pd.isna(sv) else sv
                 for orig, sv in zip(y, smoothed)]

    x_vals = list(all_periods)

    fig = go.Figure()
    if chart_type == "bar":
        fig.add_trace(go.Bar(x=x_vals, y=y, marker_color=PRIMARY, hovertemplate=hover))
    elif chart_type == "area":
        fig.add_trace(go.Scatter(
            x=x_vals, y=y, mode="lines", fill="tozeroy",
            line=dict(color=PRIMARY, width=2),
            fillcolor="rgba(124, 42, 131, 0.15)",
            hovertemplate=hover,
        ))
    else:
        fig.add_trace(go.Scatter(
            x=x_vals, y=y, mode="lines+markers",
            line=dict(color=PRIMARY, width=2), marker=dict(size=5),
            hovertemplate=hover,
        ))

    if metric == "lag":
        fig.add_hline(y=_GRACE_DAYS, line_dash="dash",
                      line_color=SEMANTIC_COLORS["error"], line_width=1,
                      annotation_text=f"Due ({_GRACE_DAYS}d)",
                      annotation_position="top left",
                      annotation_font_size=10,
                      annotation_font_color=SEMANTIC_COLORS["error"])

    apply_default_layout(fig)
    fig.update_layout(
        yaxis_title=y_title,
        margin=dict(l=48, r=16, t=12, b=20),
        hovermode="x unified",
        hoverdistance=-1,
    )
    if y_range:
        fig.update_layout(yaxis_range=y_range)
    return fig


def _build_physician_chart(df, mode="open", stack_mode="stacked"):
    """Per-physician bars: open tasks (missing/pending, stacked or grouped via
    the gear toggle), on-time %, or median lag."""
    if "TreatingPhysician" not in df.columns or "DocStatus" not in df.columns:
        return empty_figure("No physician data")

    df = df[df["TreatingPhysician"].notna()].copy()
    if df.empty:
        return empty_figure("No physician data")
    df["_md"] = df["TreatingPhysician"].map(physician_short_name)

    fig = go.Figure()

    if mode == "open":
        open_df = df[df["DocStatus"].isin(_OPEN_STATUSES)]
        if open_df.empty:
            return empty_figure("No open tasks — all summaries written")
        pivot = (open_df.groupby(["_md", "DocStatus"]).size()
                 .unstack(fill_value=0)
                 .reindex(columns=list(_OPEN_STATUSES), fill_value=0))
        pivot["_total"] = pivot.sum(axis=1)
        pivot = pivot.sort_values("_total", ascending=True)
        for status in _OPEN_STATUSES:
            if status == "Reopened" and pivot[status].sum() == 0:
                continue
            fig.add_trace(go.Bar(
                y=pivot.index, x=pivot[status], name=status,
                orientation="h", marker_color=_STATUS_COLORS[status],
                hovertemplate="%{y} — " + status + ": %{x}<extra></extra>",
            ))
        fig.update_layout(
            barmode="group" if stack_mode == "grouped" else "stack",
            xaxis_title="Open Tasks",
        )
    elif mode in ("ontime", "done"):
        resolved = df[_resolved_mask(df)].copy()
        if resolved.empty:
            return empty_figure("No resolved courses")
        if mode == "done":
            resolved["_flag"] = resolved["DocStatus"] == "Documented"
            x_title, threshold, hover_word = "Documented %", 95, "documented"
        else:
            resolved["_flag"] = _ontime_mask(resolved)
            x_title, threshold, hover_word = "On-Time %", 90, "on time"
        grp = resolved.groupby("_md").agg(rate=("_flag", "mean"), n=("_flag", "size"))
        grp = grp[grp["n"] >= 3]
        if grp.empty:
            return empty_figure("Not enough courses per physician")
        grp["rate"] *= 100
        grp = grp.sort_values("rate", ascending=True)
        fig.add_trace(go.Bar(
            y=grp.index, x=grp["rate"], orientation="h",
            marker_color=[SEMANTIC_COLORS["success"] if v >= threshold else SEMANTIC_COLORS["warning"]
                          for v in grp["rate"]],
            customdata=grp["n"],
            hovertemplate="%{y}: %{x:.1f}% " + hover_word + " (%{customdata} courses)<extra></extra>",
        ))
        fig.update_layout(xaxis_title=x_title, xaxis_range=[0, 105])
    else:  # lag
        doc = df[df["DocStatus"] == "Documented"].copy()
        if doc.empty:
            return empty_figure("No documented courses")
        doc["_lag"] = pd.to_numeric(doc["DaysAfterLastTx"], errors="coerce")
        grp = doc.groupby("_md").agg(med=("_lag", "median"), n=("_lag", "size"))
        grp = grp[grp["n"] >= 3].dropna()
        if grp.empty:
            return empty_figure("Not enough courses per physician")
        grp = grp.sort_values("med", ascending=True)
        fig.add_trace(go.Bar(
            y=grp.index, x=grp["med"], orientation="h",
            marker_color=[SEMANTIC_COLORS["success"] if v <= _GRACE_DAYS else SEMANTIC_COLORS["error"]
                          for v in grp["med"]],
            customdata=grp["n"],
            hovertemplate="%{y}: %{x:.0f} days median (%{customdata} courses)<extra></extra>",
        ))
        fig.add_vline(x=_GRACE_DAYS, line_dash="dash",
                      line_color=SEMANTIC_COLORS["error"], line_width=1)
        fig.update_layout(xaxis_title="Median Days to Note")

    apply_default_layout(fig)
    fig.update_layout(margin=dict(l=90, r=16, t=12, b=32))
    return fig


def _build_lagdist_chart(df, mode="all", stack_mode="stacked"):
    """Histogram of days from last fraction to note, with the 30-day due line.

    mode "all" colors bins green/red around the due line; "treating" /
    "author" breaks each bin out by that physician attribution instead —
    TreatingPhysician is the course-scoped treating MD, AuthorName is who
    actually signed the note (they differ on ~9% of notes). stack_mode
    (gear toggle) switches the per-MD bars between stacked and grouped.
    """
    if "DocStatus" not in df.columns or "DaysAfterLastTx" not in df.columns:
        return empty_figure("No lag data")
    doc = df[df["DocStatus"] == "Documented"].copy()
    if doc.empty:
        return empty_figure("No documented courses in range")

    doc["_lag"] = pd.to_numeric(doc["DaysAfterLastTx"], errors="coerce")
    doc = doc[doc["_lag"].notna()]
    if doc.empty:
        return empty_figure("No lag data")

    # 5-day bins, everything past 120 pooled into a single overflow bin
    edges = list(range(0, 125, 5))
    doc["_bin"] = pd.cut(doc["_lag"].clip(upper=120), bins=edges,
                         right=False, include_lowest=True)
    bin_index = doc["_bin"].cat.categories
    labels = [f"{int(iv.left)}–{int(iv.right) - 1}" for iv in bin_index]
    labels[-1] = "120+"

    md_col = {"treating": "TreatingPhysician", "author": "AuthorName"}.get(mode)
    if md_col and md_col in doc.columns:
        doc["_md"] = doc[md_col].map(physician_short_name).fillna("Unknown")
        # Cap the legend: top 8 by volume, the rest pooled as Other
        top = doc["_md"].value_counts().head(8).index
        doc.loc[~doc["_md"].isin(top), "_md"] = "Other"
        pivot = (doc.groupby(["_bin", "_md"], observed=False).size()
                 .unstack(fill_value=0)
                 .reindex(bin_index, fill_value=0))
        # Column order: descending total, Other last
        order = pivot.sum().sort_values(ascending=False).index.tolist()
        if "Other" in order:
            order.remove("Other")
            order.append("Other")
        color_map = {md: CHART_COLORWAY[i % len(CHART_COLORWAY)]
                     for i, md in enumerate(order)}
        fig = go.Figure()
        for md in order:
            fig.add_trace(go.Bar(
                x=labels, y=pivot[md].values, name=str(md),
                marker_color=color_map[md],
                hovertemplate=str(md) + " — %{x} days: %{y}<extra></extra>",
            ))
        fig.update_layout(barmode="group" if stack_mode == "grouped" else "stack")
    else:
        counts = doc.groupby("_bin", observed=False).size().reindex(bin_index, fill_value=0)
        colors = [SEMANTIC_COLORS["success"] if iv.left < _GRACE_DAYS
                  else SEMANTIC_COLORS["error"] for iv in bin_index]
        fig = go.Figure(go.Bar(
            x=labels, y=counts.values, marker_color=colors,
            hovertemplate="%{x} days: %{y} courses<extra></extra>",
        ))
    # Due boundary sits between the 25–29 and 30–34 bins. Label drawn as a
    # separate annotation inside the plot area — the vline's own "top"
    # annotation lands outside it, colliding with the legend row.
    fig.add_vline(x=5.5, line_dash="dash",
                  line_color=NEUTRAL["text_secondary"], line_width=1)
    fig.add_annotation(
        x=5.5, xanchor="left", xshift=6,
        y=0.94, yref="y domain",
        text=f"Due ({_GRACE_DAYS}d)", showarrow=False,
        font=dict(size=10, color=NEUTRAL["text_secondary"]),
    )

    apply_default_layout(fig)
    fig.update_layout(
        xaxis_title="Days From Last Fraction to Note",
        xaxis_tickangle=-45,
        yaxis_title="Courses",
        margin=dict(l=48, r=16, t=24, b=36),
        bargap=0.1,
    )
    return fig


def _build_aging_chart(df, slice_by="physician", stack_mode="stacked"):
    """Bars of open tasks by overdue-age bucket, stacked or grouped (gear)."""
    if "DocStatus" not in df.columns or "DaysUndocumented" not in df.columns:
        return empty_figure("No aging data")
    open_df = df[df["DocStatus"].isin(_OPEN_STATUSES)].copy()
    if open_df.empty:
        return empty_figure("No open tasks — all summaries written")

    days = pd.to_numeric(open_df["DaysUndocumented"], errors="coerce").fillna(0)
    open_df["_bucket"] = pd.cut(
        days, bins=[-1, 30, 60, 90, float("inf")], labels=_AGING_BUCKETS)

    if slice_by == "department" and "Department" in open_df.columns:
        open_df["_slice"] = open_df["Department"]
        color_map = DEPARTMENT_COLORS
    else:
        open_df["_slice"] = open_df["TreatingPhysician"].map(physician_short_name)
        slices = open_df["_slice"].dropna().unique()
        color_map = {s: CHART_COLORWAY[i % len(CHART_COLORWAY)]
                     for i, s in enumerate(sorted(slices))}

    pivot = (open_df.groupby(["_bucket", "_slice"], observed=False).size()
             .unstack(fill_value=0)
             .reindex(_AGING_BUCKETS, fill_value=0))

    fig = go.Figure()
    for col in pivot.columns:
        fig.add_trace(go.Bar(
            x=pivot.index.astype(str), y=pivot[col], name=str(col),
            marker_color=color_map.get(col, PRIMARY),
            hovertemplate=str(col) + " — %{x} days: %{y}<extra></extra>",
        ))

    apply_default_layout(fig)
    fig.update_layout(
        barmode="group" if stack_mode == "grouped" else "stack",
        xaxis_title="Days Since Last Fraction",
        yaxis_title="Open Tasks",
        margin=dict(l=48, r=16, t=12, b=36),
    )
    return fig


# ---------------------------------------------------------------------------
# Table Builder
# ---------------------------------------------------------------------------

def _build_table(df, status_filter="open", md=None):
    """Return (rowData, columnDefs) for the documentation worklist.

    status_filter: "open" (Missing + Pending + Reopened), a specific
    DocStatus, or "all" (everything, Waived included). md narrows to one
    treating physician. Open views sort most-overdue first; documented /
    all views sort by last fraction descending.
    """
    if md and "TreatingPhysician" in df.columns:
        df = df[df["TreatingPhysician"] == md]
    if status_filter == "open":
        df = df[df["DocStatus"].isin(_OPEN_STATUSES)]
    elif status_filter != "all":
        df = df[df["DocStatus"] == status_filter]
    if df.empty:
        return [], []

    df = df.copy()
    open_view = status_filter == "open" or status_filter in _OPEN_STATUSES
    if open_view:
        df["_sort"] = pd.to_numeric(df["DaysUndocumented"], errors="coerce")
        df = df.sort_values("_sort", ascending=False)
    else:
        df = df.sort_values("LastTxDate", ascending=False)
    df = df.drop(columns=["_sort"], errors="ignore")

    show_note_cols = status_filter in ("Documented", "all")
    display_cols = [
        {"field": "DocStatus", "headerName": "Status", "width": 110, "cellStyle": {
            "styleConditions": [
                {"condition": "params.value === 'Missing'", "style": {"color": SEMANTIC_COLORS["error"], "fontWeight": "600"}},
                {"condition": "params.value === 'Pending'", "style": {"color": SEMANTIC_COLORS["warning"], "fontWeight": "600"}},
                {"condition": "params.value === 'Documented'", "style": {"color": SEMANTIC_COLORS["success"], "fontWeight": "600"}},
                {"condition": "params.value === 'Reopened'", "style": {"color": _STATUS_COLORS["Reopened"], "fontWeight": "600"}},
                {"condition": "params.value === 'Waived'", "style": {"color": _STATUS_COLORS["Waived"], "fontWeight": "600"}},
            ],
        }},
        # Local override buttons (Waive / Reopen / Undo) — persisted in
        # reviews_db.eot_overrides via the eot-store-override-action store.
        {"field": "_override", "headerName": "Override", "width": 120,
         "cellRenderer": "EotOverrideButtons", "sortable": False, "filter": False},
        {"field": "PatientFullName", "headerName": "Patient"},
        {"field": "PatientId", "headerName": "MRN"},
        *([{"field": "PatientCode", "headerName": "Code", "width": 90}] if PHI_MODE else []),
        {"field": "CourseName", "headerName": "Course"},
        {"field": "Modality", "headerName": "Modality", "width": 100},
        {"field": "Department", "headerName": "Dept", "width": 110},
        {"field": "TreatingPhysician", "headerName": "Treating MD"},
        {"field": "LastTxDate", "headerName": "Last Tx", "width": 110},
        {"field": "DueDate", "headerName": "Note Due", "width": 110},
        {"field": "DaysUndocumented", "headerName": "Days Open", "width": 110,
         "type": "numericColumn"},
        *([
            {"field": "EOTNoteDateTime", "headerName": "Note Date", "width": 110},
            {"field": "AuthorName", "headerName": "Author"},
            {"field": "DaysAfterLastTx", "headerName": "Days to Note", "width": 110,
             "type": "numericColumn"},
        ] if show_note_cols else []),
        {"field": "DeliveredFractions", "headerName": "Fx", "width": 80,
         "type": "numericColumn"},
        {"field": "FractionsPrescribed", "headerName": "Rx Fx", "width": 90,
         "type": "numericColumn"},
        {"field": "CompletionBasis", "headerName": "Completion Basis"},
    ]

    existing_cols = [c for c in display_cols
                     if c["field"] in df.columns or c["field"] == "_override"]
    existing_cols = apply_phi_grid_rules(existing_cols)

    table_df = df.head(500).copy()
    # _row_idx must be the store df's positional index so the grid-filter →
    # chart sync maps back onto the full filtered population.
    table_df["_row_idx"] = table_df.index
    keep = [c["field"] for c in existing_cols if c["field"] in table_df.columns]
    # CourseKey rides along (not a column) — the override buttons key on it
    table_df = table_df[keep + ["CourseKey", "_row_idx"]]
    for c in ["LastTxDate", "DueDate", "EOTNoteDateTime"]:
        if c in table_df.columns and pd.api.types.is_datetime64_any_dtype(table_df[c]):
            table_df[c] = table_df[c].dt.strftime("%m/%d/%Y")
    # Keep numeric columns numeric so AG Grid sorts them correctly
    for c in ["DaysUndocumented", "DaysAfterLastTx", "DeliveredFractions", "FractionsPrescribed"]:
        if c in table_df.columns:
            table_df[c] = pd.to_numeric(table_df[c], errors="coerce").round().astype("Int64")
    table_df = sanitize_for_grid(table_df)

    return table_df.to_dict("records"), existing_cols
