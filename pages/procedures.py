"""Procedures page -- ancillary procedure tracking by category with tabbed detail views."""

import math
import dash
import dash_mantine_components as dmc
import dash_ag_grid as dag
from dash import callback, Input, Output, State, dcc, html, clientside_callback, ClientsideFunction
from dash_iconify import DashIconify
import plotly.graph_objects as go
import pandas as pd
import numpy as np

from config.settings import (
    PHYSICIANS, DEPARTMENTS, DEPARTMENT_COLORS, CHART_COLORWAY, PRIMARY,
    DEFAULT_LAYOUT, FONT_FAMILY, SEMANTIC_COLORS, NEUTRAL,
    DEFAULT_COLUMN_DEFS, DEFAULT_GRID_OPTIONS, CHART_PAPER_HEIGHT,
)
from components.filter_bar import department_chips
from components.kpi_card import kpi_card
from components.chart_card import chart_card, register_chart_callbacks
from components.detail_table import detail_table
from utils.charts import apply_default_layout, empty_figure, dept_color
from utils.date_slider import (
    month_idx, idx_to_date, MAX_IDX, DEFAULT_SLIDER, SLIDER_MARKS,
    preset_to_slider_val,
)

dash.register_page(__name__, path="/procedures", name="Procedures", order=10)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
PAGE_ID = "proc"
_DEFAULT_DATE_PRESET = "12mo"

PROCEDURE_CATEGORIES = [
    "Pluvicto", "Rectal Spacer", "Lupron", "Prostate LDR", "Volume Study", "Gold Seeds",
]

_TAB_KEYS = {
    "Lupron": "lupron",
    "Prostate LDR": "ldr",
    "Rectal Spacer": "spacer",
    "Gold Seeds": "seeds",
    "Volume Study": "volstudy",
    "Pluvicto": "pluvicto",
}

_CAT_TAB_PAIRS = list(_TAB_KEYS.items())  # ordered list of (cat_name, key)

_CATEGORY_COLORS = {
    "Lupron": CHART_COLORWAY[0],       # purple
    "Prostate LDR": CHART_COLORWAY[1],  # blue
    "Rectal Spacer": CHART_COLORWAY[2], # red
    "Gold Seeds": CHART_COLORWAY[3],    # green
    "Volume Study": CHART_COLORWAY[4],  # orange
    "Pluvicto": CHART_COLORWAY[5],      # cyan
}


# ---------------------------------------------------------------------------
# Filter Bar
# ---------------------------------------------------------------------------

def _build_filter_bar():
    """Build the two-row filter bar for procedures page."""
    return dmc.Paper(
        children=[
            # Row 1: dimension filters
            dmc.Group(
                children=[
                    department_chips(PAGE_ID),
                    # Physician dropdown
                    html.Div(
                        children=[
                            html.Div(
                                children=[
                                    dmc.Button(
                                        "Physician",
                                        id=f"{PAGE_ID}-physician-trigger",
                                        variant="default",
                                        size="sm",
                                        rightSection=DashIconify(icon="mdi:chevron-down", width=14),
                                    ),
                                    dmc.ActionIcon(
                                        DashIconify(icon="mdi:close-circle", width=18),
                                        id=f"{PAGE_ID}-physician-clear",
                                        variant="subtle",
                                        color="gray",
                                        size="sm",
                                        className="wf-filter-clear-btn",
                                    ),
                                ],
                                style={"position": "relative", "display": "inline-block"},
                            ),
                            dmc.Paper(
                                id=f"{PAGE_ID}-physician-panel",
                                children=[
                                    dmc.ChipGroup(
                                        children=[],
                                        id=f"{PAGE_ID}-filter-physician",
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
                    # Status filter
                    dmc.SegmentedControl(
                        id=f"{PAGE_ID}-filter-status",
                        data=[
                            {"value": "all", "label": "All"},
                            {"value": "open", "label": "Open"},
                            {"value": "completed", "label": "Completed"},
                        ],
                        value="all",
                        size="xs",
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
# Tab Panels — each tab gets trend + cumulative charts + detail grid
# ---------------------------------------------------------------------------

def _tab_panel(cat_key):
    """Build a tab panel for a procedure category."""
    children = [
        dmc.Grid(gutter="md", children=[
            dmc.GridCol(
                chart_card(
                    f"{PAGE_ID}-tab-chart-trend-{cat_key}",
                    "Volume Trend",
                    show_settings=False,
                    show_smooth=False,
                    paper_height="360px",
                    paper_padding="md",
                ),
                span={"base": 12, "md": 6},
            ),
            dmc.GridCol(
                chart_card(
                    f"{PAGE_ID}-tab-chart-cumul-{cat_key}",
                    "Cumulative Volume",
                    show_settings=False,
                    show_smooth=False,
                    paper_height="360px",
                    paper_padding="md",
                ),
                span={"base": 12, "md": 6},
            ),
        ]),
        detail_table(
            f"{PAGE_ID}-tab-grid-{cat_key}",
            title="Detail Records",
            export_id=f"{PAGE_ID}-tab-export-{cat_key}",
            height=400,
        ),
    ]
    return children


def _pluvicto_panel():
    """Build the Pluvicto tab panel with patient queue grid + charts."""
    children = [
        # Patient queue — slim inline table with status toggle
        dmc.Paper(
            children=[
                dmc.Group(
                    justify="space-between", align="center", mb=6,
                    children=[
                        dmc.Text("Pluvicto Patient Queue", size="sm", fw=500, c=NEUTRAL["text_secondary"]),
                        dmc.SegmentedControl(
                            id=f"{PAGE_ID}-pluvicto-queue-filter",
                            data=[
                                {"value": "all", "label": "All"},
                                {"value": "in_progress", "label": "In Progress"},
                                {"value": "completed", "label": "Completed"},
                            ],
                            value="all",
                            size="xs",
                        ),
                    ],
                ),
                html.Div(id=f"{PAGE_ID}-pluvicto-queue"),
            ],
            p="md",
            radius="md",
            shadow="xs",
            withBorder=True,
        ),
        # Charts
        dmc.Grid(gutter="md", children=[
            dmc.GridCol(
                chart_card(
                    f"{PAGE_ID}-tab-chart-trend-pluvicto",
                    "Volume Trend",
                    show_settings=False,
                    show_smooth=False,
                    paper_height="360px",
                    paper_padding="md",
                ),
                span={"base": 12, "md": 6},
            ),
            dmc.GridCol(
                chart_card(
                    f"{PAGE_ID}-tab-chart-cumul-pluvicto",
                    "Cumulative Volume",
                    show_settings=False,
                    show_smooth=False,
                    paper_height="360px",
                    paper_padding="md",
                ),
                span={"base": 12, "md": 6},
            ),
        ]),
        detail_table(
            f"{PAGE_ID}-tab-grid-pluvicto",
            title="Detail Records",
            export_id=f"{PAGE_ID}-tab-export-pluvicto",
            height=400,
        ),
    ]
    return children


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
                dmc.Title("Procedures", order=2, className="page-title",
                          style={"margin": 0, "textAlign": "center"}),
                _build_filter_bar(),
            ],
        ),

        # KPI row — 5 cards
        dmc.Grid(id=f"{PAGE_ID}-kpi-row", gutter="md", children=[
            dmc.GridCol(id=f"{PAGE_ID}-kpi-pluvicto", span={"base": 12, "sm": 6, "md": 2.4}),
            dmc.GridCol(id=f"{PAGE_ID}-kpi-upcoming-pluv", span={"base": 12, "sm": 6, "md": 2.4}),
            dmc.GridCol(id=f"{PAGE_ID}-kpi-spacer", span={"base": 12, "sm": 6, "md": 2.4}),
            dmc.GridCol(id=f"{PAGE_ID}-kpi-upcoming-spacer", span={"base": 12, "sm": 6, "md": 2.4}),
            dmc.GridCol(id=f"{PAGE_ID}-kpi-lead-time", span={"base": 12, "sm": 6, "md": 2.4}),
        ]),

        # Category tabs
        dmc.Tabs(
            id=f"{PAGE_ID}-tabs",
            value="pluvicto",
            variant="outline",
            color="violet",
            children=[
                dmc.TabsList([
                    dmc.TabsTab("Pluvicto", value="pluvicto"),
                    dmc.TabsTab("Rectal Spacer", value="spacer"),
                    dmc.TabsTab("Lupron", value="lupron"),
                    dmc.TabsTab("Prostate LDR", value="ldr"),
                    dmc.TabsTab("Volume Study", value="volstudy"),
                    dmc.TabsTab("Gold Seeds", value="seeds"),
                ]),
                dmc.TabsPanel(dmc.Stack(gap=16, children=_pluvicto_panel(), mt="md"), value="pluvicto"),
                dmc.TabsPanel(dmc.Stack(gap=16, children=_tab_panel("spacer"), mt="md"), value="spacer"),
                dmc.TabsPanel(dmc.Stack(gap=16, children=_tab_panel("lupron"), mt="md"), value="lupron"),
                dmc.TabsPanel(dmc.Stack(gap=16, children=_tab_panel("ldr"), mt="md"), value="ldr"),
                dmc.TabsPanel(dmc.Stack(gap=16, children=_tab_panel("volstudy"), mt="md"), value="volstudy"),
                dmc.TabsPanel(dmc.Stack(gap=16, children=_tab_panel("seeds"), mt="md"), value="seeds"),
            ],
        ),

        # Interval for periodic refresh
        dcc.Interval(id=f"{PAGE_ID}-interval", interval=300_000, n_intervals=0),
    ],
)


# ---------------------------------------------------------------------------
# Filter Callbacks
# ---------------------------------------------------------------------------

def _register_filter_callbacks():
    """Register all filter-sync callbacks."""

    # A) Preset -> Slider + DatePicker
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

    # B) Slider -> DatePicker + Label (clientside)
    clientside_callback(
        ClientsideFunction(namespace="proceduresDateSlider", function_name="syncSlider"),
        Output(f"{PAGE_ID}-filter-daterange", "start_date", allow_duplicate=True),
        Output(f"{PAGE_ID}-filter-daterange", "end_date", allow_duplicate=True),
        Output(f"{PAGE_ID}-date-range-label", "children"),
        Input(f"{PAGE_ID}-date-slider", "value"),
        State(f"{PAGE_ID}-filter-daterange", "start_date"),
        State(f"{PAGE_ID}-filter-daterange", "end_date"),
        prevent_initial_call=True,
    )

    # C) DatePicker -> Slider
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

    # D) Slider -> auto-clear preset
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
            if (!val) return "Physician";
            return val.split(", ")[0];
        }""",
        Output(f"{PAGE_ID}-physician-trigger", "children"),
        Input(f"{PAGE_ID}-filter-physician", "value"),
    )

    # --- Clear-button visibility ---
    clientside_callback(
        """function(val) { return val ? {"display": "inline-flex"} : {"display": "none"}; }""",
        Output(f"{PAGE_ID}-physician-clear", "style"),
        Input(f"{PAGE_ID}-filter-physician", "value"),
    )

    # --- Clear-button actions ---
    clientside_callback(
        """function(n) { return null; }""",
        Output(f"{PAGE_ID}-filter-physician", "value", allow_duplicate=True),
        Input(f"{PAGE_ID}-physician-clear", "n_clicks"),
        prevent_initial_call=True,
    )


_register_filter_callbacks()


# ---------------------------------------------------------------------------
# Dynamic physician chip population
# ---------------------------------------------------------------------------
@callback(
    Output(f"{PAGE_ID}-filter-physician", "children"),
    Input(f"{PAGE_ID}-interval", "n_intervals"),
    Input(f"{PAGE_ID}-filter-daterange", "start_date"),
    Input(f"{PAGE_ID}-filter-daterange", "end_date"),
    Input(f"{PAGE_ID}-filter-department", "value"),
    Input(f"{PAGE_ID}-filter-status", "value"),
    Input(f"{PAGE_ID}-date-slider", "value"),
)
def _populate_physician_chips(_n, range_start, range_end, dept_filter, status_filter, slider_val):
    from data.loader import load_procedures
    try:
        df = load_procedures()
    except Exception:
        return []
    if df.empty or "AppointmentPhysician" not in df.columns:
        return []
    start, end = _get_date_range(slider_val, [range_start, range_end])
    dff = _filter_data(df, start, end, dept_filter, None, status_filter)
    mds = sorted(dff["AppointmentPhysician"].dropna().unique())
    return [
        dmc.Chip(md.split(", ")[0], value=md, size="xs", variant="filled")
        for md in mds
    ]


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


def _filter_data(df, start, end, dept_filter, physician_filter, status_filter):
    """Apply common filters to procedures DataFrame."""
    dff = df.copy()
    if "ScheduledDateTime" in dff.columns:
        dff = dff[dff["ScheduledDateTime"].notna()]
        dff = dff[(dff["ScheduledDateTime"] >= start) & (dff["ScheduledDateTime"] <= end)]
    if dept_filter and "Department" in dff.columns:
        dff = dff[dff["Department"].isin(dept_filter)]
    if physician_filter and "AppointmentPhysician" in dff.columns:
        dff = dff[dff["AppointmentPhysician"] == physician_filter]
    if status_filter and status_filter != "all" and "ActivityStatus" in dff.columns:
        if status_filter == "open":
            dff = dff[dff["ActivityStatus"] == "Open"]
        elif status_filter == "completed":
            dff = dff[dff["ActivityStatus"] == "Manually Completed"]
    return dff


# ---------------------------------------------------------------------------
# KPI helpers
# ---------------------------------------------------------------------------

def _build_upcoming_card(df_all, cat_name, accent_color, n=3):
    """Build an 'upcoming' KPI card showing next N scheduled with date + MD."""
    if df_all.empty or "ProcedureCategory" not in df_all.columns:
        return kpi_card(f"Upcoming {cat_name}", "0", accent_color=accent_color)

    cat_df = df_all[df_all["ProcedureCategory"] == cat_name]
    if "ActivityStatus" in cat_df.columns:
        upcoming = cat_df[cat_df["ActivityStatus"] == "Open"].copy()
    else:
        upcoming = pd.DataFrame()

    count = len(upcoming)
    if upcoming.empty:
        return kpi_card(f"Upcoming {cat_name}", "0", accent_color=accent_color)

    # Sort by date, take next N
    if "ScheduledDateTime" in upcoming.columns:
        upcoming = upcoming.sort_values("ScheduledDateTime").head(n)

    # Build detail lines
    lines = []
    for _, row in upcoming.iterrows():
        dt = row.get("ScheduledDateTime")
        md = row.get("AppointmentPhysician", "")
        dt_str = dt.strftime("%m/%d") if pd.notna(dt) else ""
        md_short = md.split(", ")[0] if md and pd.notna(md) else ""
        line = f"{dt_str} — {md_short}" if md_short else dt_str
        lines.append(line)

    detail_text = " | ".join(lines) if lines else ""

    return kpi_card(
        f"Upcoming {cat_name}",
        f"{count:,}",
        value_detail=detail_text if detail_text else None,
        accent_color=accent_color,
    )


def _build_sparkline_kpi(dff, cat_name, accent_color):
    """Build a KPI card with sparkline for a category."""
    if "ProcedureCategory" not in dff.columns:
        return kpi_card(cat_name, "0", accent_color=accent_color)

    sub = dff[dff["ProcedureCategory"] == cat_name]
    count = len(sub)

    spark_vals, spark_labels = None, None
    if not sub.empty and "ScheduledDateTime" in sub.columns:
        weekly = sub.set_index("ScheduledDateTime").resample("W").size()
        if len(weekly) > 1:
            spark_vals = weekly.tolist()
            spark_labels = [pd.Timestamp(d) for d in weekly.index]

    return kpi_card(
        cat_name, f"{count:,}",
        sparkline_past=spark_vals,
        sparkline_past_labels=spark_labels,
        accent_color=accent_color,
    )


def _build_lead_time_kpi(dff, categories):
    """Build avg lead time KPI for specific categories."""
    if dff.empty or "ProcedureCategory" not in dff.columns or "DaysFromCreatedToAppt" not in dff.columns:
        return kpi_card("Avg Lead Time", "N/A", accent_color=PRIMARY)

    sub = dff[dff["ProcedureCategory"].isin(categories)]
    vals = sub["DaysFromCreatedToAppt"].dropna()
    if vals.empty:
        return kpi_card("Avg Lead Time", "N/A", accent_color=PRIMARY)

    avg = round(vals.mean(), 1)

    # Sparkline of weekly avg lead time
    t = sub[sub["DaysFromCreatedToAppt"].notna()].copy()
    spark_vals, spark_labels = None, None
    if not t.empty and "ScheduledDateTime" in t.columns:
        weekly = t.set_index("ScheduledDateTime")["DaysFromCreatedToAppt"].resample("W").mean()
        fv, fl = [], []
        for v, d in zip(weekly, weekly.index):
            if pd.notna(v):
                fv.append(round(v, 1))
                fl.append(pd.Timestamp(d))
        if len(fv) > 1:
            spark_vals = fv
            spark_labels = fl

    return kpi_card(
        "Avg Lead Time", f"{avg} days",
        sparkline_past=spark_vals,
        sparkline_past_labels=spark_labels,
        sparkline_hover_fmt="%{x|%b %d}: %{y:.1f} days<extra></extra>",
        accent_color=PRIMARY,
    )


# ---------------------------------------------------------------------------
# Tab chart builders
# ---------------------------------------------------------------------------

def _build_tab_trend_figure(dff, cat_name):
    """Build a monthly trend bar chart for a category."""
    if dff.empty or "ScheduledDateTime" not in dff.columns:
        return empty_figure(f"No {cat_name} data")

    t = dff.copy()
    t["period"] = t["ScheduledDateTime"].dt.to_period("M").dt.to_timestamp()
    counts = t.groupby("period").size()

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=counts.index, y=counts.values,
        marker_color=_CATEGORY_COLORS.get(cat_name, PRIMARY),
        hovertemplate="%{x|%b %Y}: %{y}<extra></extra>",
    ))
    apply_default_layout(fig)
    fig.update_layout(
        height=300, yaxis_title="Count",
        margin=dict(l=50, r=16, t=16, b=40), showlegend=False,
    )
    return fig


def _build_tab_cumulative_figure(dff, cat_name):
    """Build a cumulative volume line chart for a category, comparing years."""
    if dff.empty or "ScheduledDateTime" not in dff.columns:
        return empty_figure(f"No {cat_name} data")

    t = dff.copy()
    t["_date"] = t["ScheduledDateTime"].dt.normalize()
    years = sorted(t["_date"].dt.year.unique(), reverse=True)

    fig = go.Figure()
    color = _CATEGORY_COLORS.get(cat_name, PRIMARY)

    for i, yr in enumerate(years[:4]):
        sub = t[t["_date"].dt.year == yr].copy()
        sub["_doy"] = sub["_date"].dt.dayofyear
        daily = sub.groupby("_doy").size().sort_index()
        cum = daily.cumsum()
        is_current = (i == 0)
        fig.add_trace(go.Scatter(
            x=cum.index, y=cum.values,
            mode="lines", name=str(yr),
            line=dict(
                color=color if is_current else NEUTRAL["text_muted"],
                width=2.5 if is_current else 1.5,
                dash="solid" if is_current else "dot",
            ),
            hovertemplate=f"Day %{{x}}: %{{y:,.0f}}<extra>{yr}</extra>",
        ))

    apply_default_layout(fig)
    fig.update_layout(
        height=300, yaxis_title="Cumulative",
        xaxis_title="Day of Year",
        margin=dict(l=50, r=16, t=16, b=40),
        legend=dict(orientation="h", y=1.08),
    )
    return fig


def _build_tab_grid_data(dff):
    """Build AG Grid column defs and row data for a category tab."""
    cols = [
        {"field": "PatientFullName", "headerName": "Patient", "minWidth": 160},
        {"field": "ScheduledDateTime", "headerName": "Date", "minWidth": 120,
         "valueFormatter": {"function": "d3.timeFormat('%m/%d/%Y')(new Date(params.value))"}},
        {"field": "AppointmentPhysician", "headerName": "Physician", "minWidth": 130},
        {"field": "DaysFromCreatedToAppt", "headerName": "Lead (days)", "minWidth": 90, "type": "numericColumn"},
        {"field": "DurationMinutes", "headerName": "Duration (min)", "minWidth": 100, "type": "numericColumn"},
        {"field": "ActivityStatus", "headerName": "Status", "minWidth": 110},
        {"field": "Department", "headerName": "Dept", "minWidth": 90},
        {"field": "ReferringPhysician", "headerName": "Referring MD", "minWidth": 130},
    ]
    if dff.empty:
        return cols, []
    display_cols = [c["field"] for c in cols if c["field"] in dff.columns]
    rows = dff[display_cols].copy()
    if "ScheduledDateTime" in rows.columns:
        rows["ScheduledDateTime"] = rows["ScheduledDateTime"].dt.strftime("%Y-%m-%dT%H:%M:%S")
    return cols, rows.to_dict("records")


# ---------------------------------------------------------------------------
# Pluvicto Queue
# ---------------------------------------------------------------------------

def _build_pluvicto_queue(status_filter="all"):
    """Build the Pluvicto patient queue as a slim DMC table.

    status_filter: "all", "in_progress", or "completed"
    """
    from data.loader import load_procedures, load_pluvicto_workflow

    try:
        procs = load_procedures()
        wf = load_pluvicto_workflow()
    except Exception:
        return dmc.Text("No data available", size="sm", c=NEUTRAL["text_muted"])

    plv_procs = procs[procs["ProcedureCategory"] == "Pluvicto"] if "ProcedureCategory" in procs.columns else pd.DataFrame()
    patients = {}

    # From workflow: consult date and stage
    if not wf.empty and "PatientId" in wf.columns:
        for pid in wf["PatientId"].unique():
            pw = wf[wf["PatientId"] == pid].sort_values("StageOrder" if "StageOrder" in wf.columns else "StageDateTime")
            exam_row = pw[pw["StageName"] == "Exam"] if "StageName" in pw.columns else pd.DataFrame()
            consult_date = exam_row["StageDateTime"].min() if not exam_row.empty and "StageDateTime" in exam_row.columns else None
            latest_stage = pw.iloc[-1]["StageName"] if "StageName" in pw.columns and len(pw) > 0 else "Unknown"
            patient_name = pw.iloc[0].get("PatientName", pw.iloc[0].get("PatientFullName", "Unknown"))
            patients[pid] = {
                "Patient": patient_name,
                "Consult": consult_date.strftime("%m/%d/%y") if pd.notna(consult_date) else "",
                "Stage": latest_stage,
                "Physician": "",
                "tx_dates": [],
            }

    # From procedures: treatment dates
    if not plv_procs.empty and "PatientId" in plv_procs.columns:
        for pid in plv_procs["PatientId"].unique():
            pp = plv_procs[plv_procs["PatientId"] == pid].sort_values("ScheduledDateTime")
            if pid not in patients:
                patients[pid] = {
                    "Patient": pp.iloc[0].get("PatientFullName", "Unknown"),
                    "Consult": "",
                    "Stage": "On Treatment",
                    "Physician": "",
                    "tx_dates": [],
                }
            rec = patients[pid]
            if "AppointmentPhysician" in pp.columns:
                phys = pp["AppointmentPhysician"].dropna()
                if not phys.empty:
                    rec["Physician"] = phys.iloc[0].split(", ")[0]
            for _, row in pp.head(6).iterrows():
                tx_date = row.get("ScheduledDateTime")
                md_name = row.get("AppointmentPhysician", "")
                # Build initials from "Last, First" -> "FL"
                md_init = ""
                if md_name and pd.notna(md_name):
                    parts = [p.strip() for p in str(md_name).split(",")]
                    if len(parts) >= 2:
                        md_init = parts[1][0] + parts[0][0]  # First initial + Last initial
                    elif parts:
                        md_init = parts[0][0]
                rec["tx_dates"].append((tx_date if pd.notna(tx_date) else None, md_init))

            # Determine patient status: completed (all 6 done) vs in_progress
            n_completed = len(pp[pp["ActivityStatus"] == "Manually Completed"]) if "ActivityStatus" in pp.columns else 0
            n_total = len(pp)
            if n_total >= 6 and n_completed >= 6:
                rec["_status"] = "completed"
            else:
                rec["_status"] = "in_progress"

    # Patients only in workflow (no procedures yet) are "in_progress"
    for rec in patients.values():
        if "_status" not in rec:
            rec["_status"] = "in_progress"

    # Apply status filter
    if status_filter and status_filter != "all":
        patients = {pid: rec for pid, rec in patients.items() if rec["_status"] == status_filter}

    if not patients:
        return dmc.Text("No Pluvicto patients in queue", size="sm", c=NEUTRAL["text_muted"])

    today = pd.Timestamp.now().normalize()
    col_w = "10%"  # even width across 10 columns

    # Build table header
    headers = ["Patient", "Consult", "Stage", "Treatment 1", "Treatment 2", "Treatment 3", "Treatment 4", "Treatment 5", "Treatment 6", "MD"]
    head = dmc.TableThead(dmc.TableTr([
        dmc.TableTh(h, style={"fontSize": "11px", "color": NEUTRAL["text_secondary"],
                              "fontWeight": 600, "textTransform": "uppercase",
                              "padding": "6px 8px", "whiteSpace": "nowrap",
                              "width": col_w})
        for h in headers
    ]))

    # Colors for past vs future
    _DONE_COLOR = SEMANTIC_COLORS["success"]   # green
    _FUTURE_COLOR = NEUTRAL["text_muted"]      # gray
    _EMPTY_COLOR = NEUTRAL["border_light"]

    def _tx_cell(tx_info):
        """Render a Tx cell with color-coded dot: green=past, gray=future, empty=not scheduled.

        tx_info: (datetime, md_initials) tuple or None
        """
        base = {"fontSize": "13px", "padding": "5px 8px", "whiteSpace": "nowrap", "width": col_w}
        if tx_info is None:
            return dmc.TableTd(
                dmc.Text("—", size="sm", c=_EMPTY_COLOR),
                style=base,
            )
        dt, md_init = tx_info
        if dt is None:
            return dmc.TableTd(
                dmc.Text("—", size="sm", c=_EMPTY_COLOR),
                style=base,
            )
        is_past = dt.normalize() <= today
        dot_color = _DONE_COLOR if is_past else _FUTURE_COLOR
        label = dt.strftime("%m/%d/%y")
        if md_init:
            label += f" ({md_init})"
        return dmc.TableTd(
            dmc.Group(
                gap=6, align="center", wrap="nowrap",
                children=[
                    html.Span(style={
                        "width": "7px", "height": "7px", "borderRadius": "50%",
                        "backgroundColor": dot_color, "display": "inline-block",
                        "flexShrink": 0,
                    }),
                    dmc.Text(label, size="sm",
                             c=NEUTRAL["text_primary"] if is_past else _FUTURE_COLOR),
                ],
            ),
            style=base,
        )

    cell_style = {"fontSize": "13px", "padding": "5px 8px", "whiteSpace": "nowrap", "width": col_w}

    body_rows = []
    for rec in patients.values():
        tx = rec["tx_dates"]
        cells = [
            dmc.TableTd(rec["Patient"], style={**cell_style, "fontWeight": 500}),
            dmc.TableTd(rec["Consult"], style=cell_style),
            dmc.TableTd(rec["Stage"], style=cell_style),
        ]
        for i in range(6):
            cells.append(_tx_cell(tx[i] if i < len(tx) else None))
        cells.append(dmc.TableTd(rec["Physician"], style=cell_style))
        body_rows.append(dmc.TableTr(cells))

    body = dmc.TableTbody(body_rows)

    return dmc.Table(
        [head, body],
        striped=True,
        highlightOnHover=True,
        withTableBorder=False,
        withColumnBorders=False,
        horizontalSpacing="xs",
        verticalSpacing=4,
        style={"tableLayout": "fixed", "width": "100%"},
    )


# ---------------------------------------------------------------------------
# Main Server Callback
# ---------------------------------------------------------------------------

# Build output list dynamically
_OUTPUTS = [
    # 5 KPIs
    Output(f"{PAGE_ID}-kpi-pluvicto", "children"),
    Output(f"{PAGE_ID}-kpi-upcoming-pluv", "children"),
    Output(f"{PAGE_ID}-kpi-spacer", "children"),
    Output(f"{PAGE_ID}-kpi-upcoming-spacer", "children"),
    Output(f"{PAGE_ID}-kpi-lead-time", "children"),
]
# Per-tab: trend chart, cumulative chart, grid columnDefs, grid rowData
for _cat_name, _cat_key in _CAT_TAB_PAIRS:
    _OUTPUTS.append(Output(f"{PAGE_ID}-tab-chart-trend-{_cat_key}", "figure"))
    _OUTPUTS.append(Output(f"{PAGE_ID}-tab-chart-cumul-{_cat_key}", "figure"))
    _OUTPUTS.append(Output(f"{PAGE_ID}-tab-grid-{_cat_key}", "columnDefs"))
    _OUTPUTS.append(Output(f"{PAGE_ID}-tab-grid-{_cat_key}", "rowData"))
# Pluvicto queue
_OUTPUTS.append(Output(f"{PAGE_ID}-pluvicto-queue", "children"))


@callback(
    *_OUTPUTS,
    Input(f"{PAGE_ID}-interval", "n_intervals"),
    Input(f"{PAGE_ID}-filter-daterange", "start_date"),
    Input(f"{PAGE_ID}-filter-daterange", "end_date"),
    Input(f"{PAGE_ID}-filter-department", "value"),
    Input(f"{PAGE_ID}-filter-physician", "value"),
    Input(f"{PAGE_ID}-filter-status", "value"),
    Input(f"{PAGE_ID}-date-slider", "value"),
    Input(f"{PAGE_ID}-pluvicto-queue-filter", "value"),
)
def _update_procedures(
    _n, range_start, range_end, dept_filter, physician_filter, status_filter, slider_val,
    queue_filter,
):
    from data.loader import load_procedures

    try:
        df = load_procedures()
    except Exception:
        empty = empty_figure("Data not available")
        return tuple([None] * 5 + [empty, empty, [], []] * len(_CAT_TAB_PAIRS) + [None])

    start, end = _get_date_range(slider_val, [range_start, range_end])
    dff = _filter_data(df, start, end, dept_filter, physician_filter, status_filter)

    # --- KPIs ---
    kpi_pluv = _build_sparkline_kpi(dff, "Pluvicto", _CATEGORY_COLORS["Pluvicto"])
    kpi_upcoming_pluv = _build_upcoming_card(df, "Pluvicto", _CATEGORY_COLORS["Pluvicto"])
    kpi_spacer = _build_sparkline_kpi(dff, "Rectal Spacer", _CATEGORY_COLORS["Rectal Spacer"])
    kpi_upcoming_spacer = _build_upcoming_card(df, "Rectal Spacer", _CATEGORY_COLORS["Rectal Spacer"])
    kpi_lead = _build_lead_time_kpi(dff, ["Pluvicto", "Rectal Spacer"])

    # --- Tab content ---
    tab_outputs = []
    for cat_name, cat_key in _CAT_TAB_PAIRS:
        cat_df = dff[dff["ProcedureCategory"] == cat_name] if "ProcedureCategory" in dff.columns else pd.DataFrame()
        tab_outputs.append(_build_tab_trend_figure(cat_df, cat_name))
        tab_outputs.append(_build_tab_cumulative_figure(cat_df, cat_name))
        cols, rows = _build_tab_grid_data(cat_df)
        tab_outputs.append(cols)
        tab_outputs.append(rows)

    # --- Pluvicto queue ---
    queue_table = _build_pluvicto_queue(queue_filter or "all")

    return (
        kpi_pluv, kpi_upcoming_pluv, kpi_spacer, kpi_upcoming_spacer, kpi_lead,
        *tab_outputs,
        queue_table,
    )


# ---------------------------------------------------------------------------
# CSV Export callbacks
# ---------------------------------------------------------------------------

def _register_export_callbacks():
    for cat_name, cat_key in _CAT_TAB_PAIRS:
        clientside_callback(
            """function(n) {
                if (!n) return window.dash_clientside.no_update;
                var grid = document.querySelector('#""" + f"{PAGE_ID}-tab-grid-{cat_key}" + """');
                if (grid && grid.gridApi) {
                    grid.gridApi.exportDataAsCsv({fileName: '""" + cat_name.replace(" ", "_") + """_procedures.csv'});
                }
                return window.dash_clientside.no_update;
            }""",
            Output(f"{PAGE_ID}-tab-export-{cat_key}", "n_clicks"),
            Input(f"{PAGE_ID}-tab-export-{cat_key}", "n_clicks"),
            prevent_initial_call=True,
        )


_register_export_callbacks()


