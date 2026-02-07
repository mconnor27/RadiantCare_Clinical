"""Physicians page — manpower, assignments, after-hours work, cross-coverage."""

import dash
import dash_mantine_components as dmc
from dash import callback, clientside_callback, ClientsideFunction, Input, Output, State, dcc
import dash_ag_grid as dag
import plotly.graph_objects as go
import pandas as pd
from datetime import timedelta

from config.settings import (
    PHYSICIANS, DEPARTMENTS, DEPARTMENT_COLORS, PRIMARY, NEUTRAL,
    SEMANTIC_COLORS, CHART_COLORWAY,
)
from components.filter_bar import filter_bar, physician_select
from components.chart_settings import chart_settings_popover
from components.kpi_card import kpi_card
from utils.charts import apply_default_layout, empty_figure, color_for_index

dash.register_page(__name__, path="/physicians", name="Physicians", order=10)

# Statuses that indicate a physician is on duty (includes site assignments)
_ON_DUTY = {"ON", "ON CALL", "WEEKEND CALL", "CENTRALIA", "ABERDEEN"}

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
                dmc.Title("Physicians", order=2, className="page-title"),
                filter_bar("phys", children=[
                    dmc.SegmentedControl(
                        id="phys-filter-date-preset",
                        data=[
                            {"value": "1mo", "label": "1 mo"},
                            {"value": "3mo", "label": "3 mo"},
                            {"value": "6mo", "label": "6 mo"},
                            {"value": "12mo", "label": "12 mo"},
                            {"value": "all", "label": "All"},
                        ],
                        value="12mo",
                        size="sm",
                    ),
                    physician_select("phys"),
                ]),
            ],
        ),

        # KPI row
        dmc.Grid(id="phys-kpi-row", gutter="md", children=[
            dmc.GridCol(id="phys-kpi-coverage", span={"base": 6, "md": 2.4}),
            dmc.GridCol(id="phys-kpi-afterhours", span={"base": 6, "md": 2.4}),
            dmc.GridCol(id="phys-kpi-crosscoverage", span={"base": 6, "md": 2.4}),
            dmc.GridCol(id="phys-kpi-vacation", span={"base": 6, "md": 2.4}),
            dmc.GridCol(id="phys-kpi-weekend", span={"base": 6, "md": 2.4}),
        ]),

        # Charts row 1: Manpower over time + Site assignments
        dmc.Grid(gutter="md", children=[
            dmc.GridCol(
                dmc.Paper(
                    children=[
                        dmc.Group(
                            justify="space-between", mb="sm",
                            children=[
                                dmc.Text("Manpower Over Time", size="sm", fw=500, c=NEUTRAL["text_secondary"]),
                                chart_settings_popover(
                                    "phys-manpower",
                                    chart_types=[
                                        {"value": "area", "label": "Area"},
                                        {"value": "line", "label": "Line"},
                                        {"value": "bar", "label": "Bar"},
                                    ],
                                    show_smooth=True,
                                    smooth_max=50,
                                    smooth_default=15,
                                ),
                            ],
                        ),
                        dmc.Box(
                            pos="relative",
                            children=[
                                dmc.LoadingOverlay(id="phys-manpower-loading", visible=False, loaderProps={"type": "dots", "color": PRIMARY}),
                                dcc.Graph(id="phys-chart-manpower", config={"displayModeBar": False}, style={"height": "320px"}),
                            ],
                        ),
                    ],
                    p="md", radius="md", shadow="xs", withBorder=True,
                ),
                span={"base": 12, "md": 6},
            ),
            dmc.GridCol(
                dmc.Paper(
                    children=[
                        dmc.Text("Site Assignments", size="sm", fw=500, c=NEUTRAL["text_secondary"], mb="sm"),
                        dmc.Box(
                            pos="relative",
                            children=[
                                dmc.LoadingOverlay(id="phys-sites-loading", visible=False, loaderProps={"type": "dots", "color": PRIMARY}),
                                dcc.Graph(id="phys-chart-sites", config={"displayModeBar": False}, style={"height": "320px"}),
                            ],
                        ),
                    ],
                    p="md", radius="md", shadow="xs", withBorder=True,
                ),
                span={"base": 12, "md": 6},
            ),
        ]),

        # Charts row 2: After-hours work + Cross-coverage
        dmc.Grid(gutter="md", children=[
            dmc.GridCol(
                dmc.Paper(
                    children=[
                        dmc.Text("After-Hours Task Completions", size="sm", fw=500, c=NEUTRAL["text_secondary"], mb="sm"),
                        dmc.Box(
                            pos="relative",
                            children=[
                                dmc.LoadingOverlay(id="phys-afterhours-loading", visible=False, loaderProps={"type": "dots", "color": PRIMARY}),
                                dcc.Graph(id="phys-chart-afterhours", config={"displayModeBar": False}, style={"height": "320px"}),
                            ],
                        ),
                    ],
                    p="md", radius="md", shadow="xs", withBorder=True,
                ),
                span={"base": 12, "md": 6},
            ),
            dmc.GridCol(
                dmc.Paper(
                    children=[
                        dmc.Text("Cross-Coverage (Tasks for Other MDs' Patients)", size="sm", fw=500, c=NEUTRAL["text_secondary"], mb="sm"),
                        dmc.Box(
                            pos="relative",
                            children=[
                                dmc.LoadingOverlay(id="phys-crosscov-loading", visible=False, loaderProps={"type": "dots", "color": PRIMARY}),
                                dcc.Graph(id="phys-chart-crosscoverage", config={"displayModeBar": False}, style={"height": "320px"}),
                            ],
                        ),
                    ],
                    p="md", radius="md", shadow="xs", withBorder=True,
                ),
                span={"base": 12, "md": 6},
            ),
        ]),

        # Schedule calendar heatmap (full width)
        dmc.Paper(
            children=[
                dmc.Text("Physician Schedule Calendar", size="sm", fw=500, c=NEUTRAL["text_secondary"], mb="sm"),
                dmc.Box(
                    pos="relative",
                    children=[
                        dmc.LoadingOverlay(id="phys-calendar-loading", visible=False, loaderProps={"type": "dots", "color": PRIMARY}),
                        dcc.Graph(id="phys-chart-calendar", config={"displayModeBar": False}, style={"height": "400px"}),
                    ],
                ),
            ],
            p="md", radius="md", shadow="xs", withBorder=True,
        ),

        # Schedule detail table
        dmc.Paper(
            children=[
                dmc.Text("Schedule Detail", size="sm", fw=500, c=NEUTRAL["text_secondary"], mb="sm"),
                dmc.Box(id="phys-table-container"),
            ],
            p="md", radius="md", shadow="xs", withBorder=True,
        ),

        dcc.Store(id="phys-store-manpower"),
        dcc.Interval(id="phys-interval", interval=300_000, n_intervals=0),
    ],
)


# ---------------------------------------------------------------------------
# Callbacks
# ---------------------------------------------------------------------------
@callback(
    Output("phys-kpi-coverage", "children"),
    Output("phys-kpi-afterhours", "children"),
    Output("phys-kpi-crosscoverage", "children"),
    Output("phys-kpi-vacation", "children"),
    Output("phys-kpi-weekend", "children"),
    Output("phys-store-manpower", "data"),
    Output("phys-chart-sites", "figure"),
    Output("phys-chart-afterhours", "figure"),
    Output("phys-chart-crosscoverage", "figure"),
    Output("phys-chart-calendar", "figure"),
    Output("phys-table-container", "children"),
    Output("phys-manpower-loading", "visible"),
    Output("phys-sites-loading", "visible"),
    Output("phys-afterhours-loading", "visible"),
    Output("phys-crosscov-loading", "visible"),
    Output("phys-calendar-loading", "visible"),
    Input("phys-interval", "n_intervals"),
    Input("phys-filter-date-preset", "value"),
    Input("phys-filter-physician", "value"),
)
def update_physicians(_n, date_preset, physicians):
    from data.loader import load_physician_schedule, load_tasks

    # Initialize empty outputs
    empty = empty_figure("Data unavailable")
    na_kpi = kpi_card("—", "N/A")
    loading_off = False

    try:
        schedule = load_physician_schedule()
    except Exception:
        return (na_kpi,) * 5 + (None,) + (empty,) * 4 + ([],) + (loading_off,) * 5

    try:
        tasks = load_tasks()
    except Exception:
        tasks = pd.DataFrame()

    # Date filtering — schedule extends into the future so clamp to today
    if "Date" in schedule.columns:
        schedule["Date"] = pd.to_datetime(schedule["Date"], errors="coerce")
    today = pd.Timestamp.now().normalize()

    preset_days = {"1mo": 30, "3mo": 90, "6mo": 180, "12mo": 365}
    if date_preset == "all":
        start = None
    else:
        start = today - timedelta(days=preset_days.get(date_preset, 365))

    # Filter schedule
    df = schedule.copy()
    if start is not None and "Date" in df.columns:
        df = df[df["Date"] >= start]

    if physicians and "Physician" in df.columns:
        df = df[df["Physician"].isin(physicians)]

    # Filter tasks
    task_df = tasks.copy()
    if start is not None and not task_df.empty and "StartDateTime" in task_df.columns:
        task_df = task_df[task_df["StartDateTime"] >= start]
    if physicians and not task_df.empty and "CompletingMD" in task_df.columns:
        task_df = task_df[task_df["CompletingMD"].isin(physicians)]

    # --- KPIs ---
    kpi_cov = _kpi_coverage(df)
    kpi_ah = _kpi_afterhours(task_df)
    kpi_cc = _kpi_crosscoverage(task_df)
    kpi_vac = _kpi_vacation_days(df)
    kpi_wknd = _kpi_weekend_calls(df)

    # --- Charts ---
    manpower_data = _build_manpower_data(df)
    fig_sites = _build_site_assignments(df)
    fig_afterhours = _build_afterhours_chart(task_df, df)
    fig_crosscov = _build_crosscoverage_chart(task_df)
    fig_calendar = _build_calendar_heatmap(df)

    # --- Table ---
    table = _build_schedule_table(df)

    return (
        kpi_cov, kpi_ah, kpi_cc, kpi_vac, kpi_wknd,
        manpower_data, fig_sites, fig_afterhours, fig_crosscov, fig_calendar,
        table,
        False, False, False, False, False,
    )


def _kpi_coverage(df):
    """Average MDs on duty per day."""
    if df.empty or "Date" not in df.columns or "Status" not in df.columns:
        return kpi_card("Avg Daily Coverage", "N/A")
    on_duty = df[df["Status"].str.upper().isin(_ON_DUTY)]
    if on_duty.empty:
        return kpi_card("Avg Daily Coverage", "0")
    avg = on_duty.groupby("Date").size().mean()
    return kpi_card("Avg Daily Coverage", f"{avg:.1f} MDs", accent_color=PRIMARY)


def _kpi_afterhours(task_df):
    """Tasks completed after hours (5pm-8am or weekends)."""
    if task_df.empty or "CompletedDateTime" not in task_df.columns:
        return kpi_card("After-Hours Tasks", "N/A")
    completed = task_df[task_df["CompletedDateTime"].notna()].copy()
    if completed.empty:
        return kpi_card("After-Hours Tasks", "0")
    completed["hour"] = completed["CompletedDateTime"].dt.hour
    completed["dow"] = completed["CompletedDateTime"].dt.dayofweek
    after_hours = completed[
        (completed["hour"] < 8) | (completed["hour"] >= 17) | (completed["dow"] >= 5)
    ]
    return kpi_card("After-Hours Tasks", f"{len(after_hours):,}", accent_color=SEMANTIC_COLORS["warning"])


def _kpi_crosscoverage(task_df):
    """Tasks where CompletingMD != TreatingPhysician."""
    if task_df.empty or "CompletingMD" not in task_df.columns or "TreatingPhysician" not in task_df.columns:
        return kpi_card("Cross-Coverage Tasks", "N/A")
    completed = task_df[task_df["CompletedDateTime"].notna()].copy()
    cross = completed[completed["CompletingMD"] != completed["TreatingPhysician"]]
    pct = (len(cross) / len(completed) * 100) if len(completed) > 0 else 0
    return kpi_card("Cross-Coverage", f"{len(cross):,}", value_detail=f"({pct:.1f}%)")


def _kpi_vacation_days(df):
    """Total vacation/sick days in period."""
    if df.empty or "Status" not in df.columns:
        return kpi_card("Vacation/Sick Days", "N/A")
    vac = df[df["Status"].str.upper().isin(["VACATION", "SICK", "OFF"])]
    return kpi_card("Off/Vacation Days", f"{len(vac):,}")


def _kpi_weekend_calls(df):
    """Weekend call shifts."""
    if df.empty or "Status" not in df.columns:
        return kpi_card("Weekend Calls", "N/A")
    wknd = df[df["Status"].str.upper() == "WEEKEND CALL"]
    return kpi_card("Weekend Calls", f"{len(wknd):,}")


def _build_manpower_data(df):
    """Build raw manpower data dict for clientside smoothing."""
    if df.empty or "Date" not in df.columns or "Status" not in df.columns:
        return None

    on_duty = df[df["Status"].str.upper().isin(_ON_DUTY)].copy()
    if on_duty.empty:
        return None

    daily = on_duty.groupby("Date").size().reset_index(name="count")
    # Keep only weekdays with >1 MD (excludes weekends / lone on-call days)
    daily = daily[(daily["Date"].dt.dayofweek < 5) & (daily["count"] > 1)]
    if daily.empty:
        return None

    return {
        "dates": [d.isoformat() for d in daily["Date"]],
        "series": [{
            "name": "MDs On Duty",
            "values": daily["count"].tolist(),
            "color": PRIMARY,
        }],
        "height": 320,
        "yTitle": "MDs On Duty",
    }


def _build_site_assignments(df):
    """Grouped bar chart of site assignment days per physician."""
    if df.empty or "Department" not in df.columns or "Physician" not in df.columns:
        return empty_figure("No department data")

    assigned = df[df["Department"].notna()]
    if assigned.empty:
        return empty_figure("No site assignment data")

    counts = assigned.groupby(["Physician", "Department"]).size().reset_index(name="count")
    counts["short_name"] = counts["Physician"].str.split(",").str[0]

    fig = go.Figure()
    for dept in sorted(counts["Department"].unique()):
        dept_data = counts[counts["Department"] == dept]
        fig.add_trace(go.Bar(
            x=dept_data["short_name"],
            y=dept_data["count"],
            name=dept,
            marker_color=DEPARTMENT_COLORS.get(dept, PRIMARY),
        ))

    apply_default_layout(fig, height=320)
    fig.update_layout(
        yaxis_title="Assignment Days",
        barmode="group",
        margin=dict(l=48, r=16, t=16, b=48),
    )
    return fig


def _build_afterhours_chart(task_df, schedule_df):
    """Bar chart of after-hours tasks by physician."""
    if task_df.empty or "CompletedDateTime" not in task_df.columns or "CompletingMD" not in task_df.columns:
        return empty_figure("No task data")

    completed = task_df[task_df["CompletedDateTime"].notna()].copy()
    if completed.empty:
        return empty_figure("No completed tasks")

    completed["hour"] = completed["CompletedDateTime"].dt.hour
    completed["dow"] = completed["CompletedDateTime"].dt.dayofweek
    completed["after_hours"] = (
        (completed["hour"] < 8) | (completed["hour"] >= 17) | (completed["dow"] >= 5)
    )

    ah_by_md = completed[completed["after_hours"]].groupby("CompletingMD").size().reset_index(name="count")
    ah_by_md = ah_by_md.sort_values("count", ascending=True)
    ah_by_md["short_name"] = ah_by_md["CompletingMD"].str.split(",").str[0]

    fig = go.Figure(go.Bar(
        x=ah_by_md["count"],
        y=ah_by_md["short_name"],
        orientation="h",
        marker_color=SEMANTIC_COLORS["warning"],
    ))

    apply_default_layout(fig, height=320)
    fig.update_layout(xaxis_title="After-Hours Tasks", margin=dict(l=100, r=16, t=16, b=48))
    return fig


def _build_crosscoverage_chart(task_df):
    """Bar chart showing cross-coverage by physician."""
    if task_df.empty or "CompletingMD" not in task_df.columns or "TreatingPhysician" not in task_df.columns:
        return empty_figure("No task data")

    completed = task_df[task_df["CompletedDateTime"].notna()].copy()
    cross = completed[completed["CompletingMD"] != completed["TreatingPhysician"]]

    if cross.empty:
        return empty_figure("No cross-coverage tasks")

    cc_by_md = cross.groupby("CompletingMD").size().reset_index(name="count")
    cc_by_md = cc_by_md.sort_values("count", ascending=True)
    cc_by_md["short_name"] = cc_by_md["CompletingMD"].str.split(",").str[0]

    fig = go.Figure(go.Bar(
        x=cc_by_md["count"],
        y=cc_by_md["short_name"],
        orientation="h",
        marker_color=CHART_COLORWAY[1],
    ))

    apply_default_layout(fig, height=320)
    fig.update_layout(xaxis_title="Cross-Coverage Tasks", margin=dict(l=100, r=16, t=16, b=48))
    return fig


def _build_calendar_heatmap(df):
    """Calendar heatmap showing physician schedules."""
    if df.empty or "Date" not in df.columns or "Physician" not in df.columns:
        return empty_figure("No schedule data")

    # Pivot to physician x date matrix
    pivot = df.pivot_table(
        index="Physician",
        columns="Date",
        values="Status",
        aggfunc="first",
    )

    if pivot.empty:
        return empty_figure("No schedule data")

    # Map status to numeric for heatmap
    status_map = {
        "ON": 3, "ON CALL": 3, "CENTRALIA": 3, "ABERDEEN": 3,
        "WEEKEND CALL": 2,
        "OFF": 0, "VACATION": -1, "SICK": -1,
    }

    z_data = pivot.applymap(lambda x: status_map.get(str(x).upper(), 1) if pd.notna(x) else 0)

    fig = go.Figure(go.Heatmap(
        z=z_data.values,
        x=z_data.columns,
        y=[p.split(",")[0] for p in z_data.index],
        colorscale=[
            [0, "#EF4444"],      # Vacation/Sick
            [0.25, "#F5F6F8"],   # Off
            [0.5, "#FCD34D"],    # Weekend call
            [1, "#10B981"],      # On duty
        ],
        showscale=False,
        hovertemplate="Date: %{x}<br>Physician: %{y}<extra></extra>",
    ))

    apply_default_layout(fig, height=400)
    fig.update_layout(
        margin=dict(l=100, r=16, t=16, b=48),
        xaxis=dict(tickformat="%b %d"),
    )
    return fig


def _build_schedule_table(df):
    """Build AG Grid table of schedule records."""
    if df.empty:
        return dmc.Text("No schedule data available", c=NEUTRAL["text_muted"], ta="center", py="xl")

    display_cols = []
    col_map = {
        "Date": "Date",
        "Physician": "Physician",
        "Status": "Status",
        "Department": "Department",
    }

    for col, header in col_map.items():
        if col in df.columns:
            display_cols.append({"field": col, "headerName": header})

    if not display_cols:
        return dmc.Text("No schedule data available", c=NEUTRAL["text_muted"], ta="center", py="xl")

    table_df = df.head(200).copy()
    if "Date" in table_df.columns:
        table_df["Date"] = table_df["Date"].dt.strftime("%Y-%m-%d")
    table_df = table_df.fillna("—")

    return dag.AgGrid(
        id="phys-detail-grid",
        rowData=table_df.to_dict("records"),
        columnDefs=display_cols,
        defaultColDef={"sortable": True, "filter": True, "resizable": True},
        dashGridOptions={"pagination": True, "paginationPageSize": 25, "domLayout": "autoHeight"},
        className="ag-theme-alpine",
    )


# ---------------------------------------------------------------------------
# Clientside callback — manpower chart smoothing / chart type
# ---------------------------------------------------------------------------
clientside_callback(
    ClientsideFunction(namespace="census", function_name="smoothChartWithType"),
    Output("phys-chart-manpower", "figure"),
    Input("phys-store-manpower", "data"),
    Input("phys-manpower-settings-smooth", "value"),
    Input("phys-manpower-settings-type", "value"),
    State("phys-chart-manpower", "figure"),
)


# ---------------------------------------------------------------------------
# Settings panel toggle
# ---------------------------------------------------------------------------
@callback(
    Output("phys-manpower-settings-panel", "style"),
    Input("phys-manpower-settings-btn", "n_clicks"),
    State("phys-manpower-settings-panel", "style"),
    prevent_initial_call=True,
)
def toggle_manpower_settings(n, style):
    if not n:
        return style
    current = style or {}
    is_hidden = current.get("display") == "none"
    return {"display": "block"} if is_hidden else {"display": "none"}
