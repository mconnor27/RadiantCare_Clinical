"""Tasks page — physician task workload, SLA compliance, after-hours tracking."""

import dash
import dash_mantine_components as dmc
from dash import callback, Input, Output, dcc, clientside_callback, ClientsideFunction
import dash_ag_grid as dag
import plotly.graph_objects as go
import pandas as pd
from datetime import timedelta

from config.settings import (
    PHYSICIANS, CHART_COLORWAY, PRIMARY, FONT_FAMILY,
    SEMANTIC_COLORS, NEUTRAL, DEFAULT_LAYOUT,
)
from components.filter_bar import filter_bar, date_presets, physician_select
from components.kpi_card import kpi_card
from components.chart_settings import chart_settings_popover
from utils.charts import apply_default_layout, empty_figure, color_for_index

dash.register_page(__name__, path="/tasks", name="Tasks", order=5)


def _chart_card(chart_id: str, title: str, with_settings: bool = False):
    """Build a chart card with optional settings popover and loading overlay."""
    header_children = [
        dmc.Text(title, size="sm", fw=500, c=NEUTRAL["text_secondary"]),
    ]
    if with_settings:
        header_children.append(chart_settings_popover(chart_id))

    return dmc.Paper(
        children=[
            dmc.Group(header_children, justify="space-between", mb="sm"),
            dmc.Box(
                pos="relative",
                children=[
                    dmc.LoadingOverlay(
                        id=f"{chart_id}-loading",
                        visible=False,
                        loaderProps={"type": "dots", "color": PRIMARY},
                    ),
                    dcc.Graph(
                        id=chart_id,
                        config={"displayModeBar": False},
                        style={"height": "320px"},
                    ),
                ],
            ),
        ],
        p="md", radius="md", shadow="xs", withBorder=True,
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
                dmc.Title("Tasks", order=2, className="page-title"),
                filter_bar("tasks", children=[
                    date_presets("tasks"),
                    physician_select("tasks"),
                    dmc.SegmentedControl(
                        id="tasks-filter-type",
                        data=[
                            {"value": "all", "label": "All"},
                            {"value": "draw", "label": "Draw Volumes"},
                            {"value": "review", "label": "Review Plan"},
                        ],
                        value="all", size="sm",
                    ),
                    dmc.SegmentedControl(
                        id="tasks-filter-status",
                        data=[
                            {"value": "all", "label": "All"},
                            {"value": "open", "label": "Open"},
                            {"value": "done", "label": "Completed"},
                        ],
                        value="all", size="sm",
                    ),
                ]),
            ],
        ),

        # KPI row
        dmc.Grid(id="tasks-kpi-row", gutter="md", children=[
            dmc.GridCol(id="tasks-kpi-open", span={"base": 6, "md": 2.4}),
            dmc.GridCol(id="tasks-kpi-completed", span={"base": 6, "md": 2.4}),
            dmc.GridCol(id="tasks-kpi-time", span={"base": 6, "md": 2.4}),
            dmc.GridCol(id="tasks-kpi-sla", span={"base": 6, "md": 2.4}),
            dmc.GridCol(id="tasks-kpi-afterhrs", span={"base": 6, "md": 2.4}),
        ]),

        # Charts row 1: Volume trend + Time to Complete
        dmc.Grid(gutter="md", children=[
            dmc.GridCol(_chart_card("tasks-chart-volume", "Task Volume Trend", with_settings=True),
                        span={"base": 12, "md": 6}),
            dmc.GridCol(_chart_card("tasks-chart-histogram", "Time to Complete (minutes)"),
                        span={"base": 12, "md": 6}),
        ]),

        # Charts row 2: Physician comparison + SLA trend
        dmc.Grid(gutter="md", children=[
            dmc.GridCol(_chart_card("tasks-chart-physician", "Physician Comparison (median min)"),
                        span={"base": 12, "md": 6}),
            dmc.GridCol(_chart_card("tasks-chart-sla", "SLA Compliance Trend", with_settings=True),
                        span={"base": 12, "md": 6}),
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
        dcc.Store(id="tasks-store-sla"),
        dcc.Store(id="tasks-store-kpi-sparklines"),

        dcc.Interval(id="tasks-interval", interval=300_000, n_intervals=0),
    ],
)


# ---------------------------------------------------------------------------
# Server-side callback: compute data and output to stores
# ---------------------------------------------------------------------------
@callback(
    Output("tasks-kpi-open", "children"),
    Output("tasks-kpi-completed", "children"),
    Output("tasks-kpi-time", "children"),
    Output("tasks-kpi-sla", "children"),
    Output("tasks-kpi-afterhrs", "children"),
    Output("tasks-chart-histogram", "figure"),
    Output("tasks-chart-physician", "figure"),
    Output("tasks-table-container", "children"),
    Output("tasks-store-volume", "data"),
    Output("tasks-store-sla", "data"),
    Output("tasks-store-kpi-sparklines", "data"),
    Output("tasks-chart-volume-loading", "visible"),
    Output("tasks-chart-histogram-loading", "visible"),
    Output("tasks-chart-physician-loading", "visible"),
    Output("tasks-chart-sla-loading", "visible"),
    Input("tasks-interval", "n_intervals"),
    Input("tasks-filter-date-preset", "value"),
    Input("tasks-filter-physician", "value"),
    Input("tasks-filter-type", "value"),
    Input("tasks-filter-status", "value"),
)
def update_tasks(_n, date_preset, physicians, task_type, status):
    from data.loader import load_tasks

    try:
        tasks = load_tasks()
    except Exception:
        empty = empty_figure("Tasks data unavailable")
        na = kpi_card("—", "N/A")
        return (na, na, na, na, na, empty, empty, [], None, None, None,
                False, False, False, False)

    # Data-relative date filtering
    if "StartDateTime" in tasks.columns:
        last_date = tasks["StartDateTime"].dt.normalize().max()
    else:
        last_date = pd.Timestamp.now().normalize()

    if date_preset == "ytd":
        start = pd.Timestamp(last_date.year, 1, 1)
    elif date_preset == "12mo":
        start = last_date - timedelta(days=365)
    else:
        start = pd.Timestamp("2020-01-01")

    spark_start = last_date - timedelta(days=90)
    prior_start = start - (last_date - start)

    # Apply filters
    df = tasks.copy()
    if "StartDateTime" in df.columns:
        df = df[df["StartDateTime"] >= start]

    if physicians and "AssignedMD" in df.columns:
        df = df[df["AssignedMD"].isin(physicians)]

    if task_type == "draw" and "ActivityName" in df.columns:
        df = df[df["ActivityName"].str.contains("Draw", case=False, na=False)]
    elif task_type == "review" and "ActivityName" in df.columns:
        df = df[df["ActivityName"].str.contains("Review", case=False, na=False)]

    is_completed = df["CompletedDateTime"].notna() if "CompletedDateTime" in df.columns else pd.Series(False, index=df.index)

    if status == "open":
        df = df[~is_completed]
        is_completed = pd.Series(False, index=df.index)
    elif status == "done":
        df = df[is_completed]
        is_completed = pd.Series(True, index=df.index)

    # Prior period for trends
    df_prior = tasks.copy()
    if "StartDateTime" in df_prior.columns:
        df_prior = df_prior[(df_prior["StartDateTime"] >= prior_start) & (df_prior["StartDateTime"] < start)]
    if physicians and "AssignedMD" in df_prior.columns:
        df_prior = df_prior[df_prior["AssignedMD"].isin(physicians)]
    if task_type == "draw" and "ActivityName" in df_prior.columns:
        df_prior = df_prior[df_prior["ActivityName"].str.contains("Draw", case=False, na=False)]
    elif task_type == "review" and "ActivityName" in df_prior.columns:
        df_prior = df_prior[df_prior["ActivityName"].str.contains("Review", case=False, na=False)]

    is_completed_prior = df_prior["CompletedDateTime"].notna() if "CompletedDateTime" in df_prior.columns else pd.Series(False, index=df_prior.index)

    # --- KPIs with sparklines ---
    open_count = int((~is_completed).sum()) if status != "done" else 0
    completed_count = int(is_completed.sum()) if status != "open" else len(df)
    prior_completed = int(is_completed_prior.sum()) if len(df_prior) > 0 else 0

    # Completed trend
    comp_trend_dir = None
    comp_trend_txt = None
    if prior_completed > 0 and completed_count > 0:
        pct_chg = ((completed_count - prior_completed) / prior_completed) * 100
        comp_trend_dir = "up" if pct_chg > 0 else "down" if pct_chg < 0 else None
        comp_trend_txt = f"{abs(pct_chg):.1f}% vs prior"

    # Median time
    if "MinutesToComplete" in df.columns:
        mins = pd.to_numeric(df.loc[is_completed, "MinutesToComplete"], errors="coerce").dropna()
        median_min = f"{mins.median():.0f}" if len(mins) > 0 else "N/A"
    else:
        median_min = "N/A"
        mins = pd.Series(dtype=float)

    # SLA compliance
    sla_pct = None
    prior_sla_pct = None
    sla_text = "N/A"
    if "MinutesToComplete" in df.columns and "MinutesAllowed" in df.columns:
        completed_df = df[is_completed].copy()
        completed_df["MinutesToComplete"] = pd.to_numeric(completed_df["MinutesToComplete"], errors="coerce")
        completed_df["MinutesAllowed"] = pd.to_numeric(completed_df["MinutesAllowed"], errors="coerce")
        valid = completed_df.dropna(subset=["MinutesToComplete", "MinutesAllowed"])
        if len(valid) > 0:
            sla_pct = (valid["MinutesToComplete"] <= valid["MinutesAllowed"]).mean() * 100
            sla_text = f"{sla_pct:.1f}%"

        # Prior SLA
        if "MinutesToComplete" in df_prior.columns and "MinutesAllowed" in df_prior.columns:
            completed_prior_df = df_prior[is_completed_prior].copy()
            completed_prior_df["MinutesToComplete"] = pd.to_numeric(completed_prior_df["MinutesToComplete"], errors="coerce")
            completed_prior_df["MinutesAllowed"] = pd.to_numeric(completed_prior_df["MinutesAllowed"], errors="coerce")
            valid_prior = completed_prior_df.dropna(subset=["MinutesToComplete", "MinutesAllowed"])
            if len(valid_prior) > 0:
                prior_sla_pct = (valid_prior["MinutesToComplete"] <= valid_prior["MinutesAllowed"]).mean() * 100

    sla_trend_dir = None
    sla_trend_txt = None
    if sla_pct is not None and prior_sla_pct is not None:
        sla_diff = sla_pct - prior_sla_pct
        sla_trend_dir = "up" if sla_diff > 0 else "down" if sla_diff < 0 else None
        sla_trend_txt = f"{abs(sla_diff):.1f}pp vs prior"

    # After-hours count
    after_hrs_count = 0
    if "CompletedDateTime" in df.columns:
        completed_times = df.loc[is_completed, "CompletedDateTime"]
        hours = completed_times.dt.hour
        after_hrs_count = int(((hours < 8) | (hours >= 17)).sum())

    # Build sparkline data for KPIs
    sparkline_data = _build_kpi_sparklines(tasks, spark_start, last_date, physicians, task_type)

    kpi_open = kpi_card(
        "Open Tasks", str(open_count),
        accent_color=SEMANTIC_COLORS["warning"],
        sparkline_id="tasks-spark-open",
    )
    kpi_done = kpi_card(
        "Completed", f"{completed_count:,}",
        trend_text=comp_trend_txt, trend_direction=comp_trend_dir,
        sparkline_id="tasks-spark-completed",
    )
    kpi_time = kpi_card(
        "Median Time", f"{median_min} min",
        sparkline_id="tasks-spark-time",
    )
    kpi_sla = kpi_card(
        "SLA Compliance", sla_text,
        trend_text=sla_trend_txt, trend_direction=sla_trend_dir,
        accent_color=PRIMARY,
        sparkline_id="tasks-spark-sla",
    )
    kpi_after = kpi_card(
        "After-Hours", str(after_hrs_count),
        sparkline_id="tasks-spark-afterhours",
    )

    # --- Build store data for clientside charts ---
    volume_store = _build_volume_store(df)
    sla_store = _build_sla_store(df, is_completed)

    # --- Server-rendered charts ---
    fig_hist = _build_histogram(df, is_completed)
    fig_physician = _build_physician_comparison(df, is_completed)

    # --- Detail table ---
    table = _build_table(df, is_completed)

    return (
        kpi_open, kpi_done, kpi_time, kpi_sla, kpi_after,
        fig_hist, fig_physician, table,
        volume_store, sla_store, sparkline_data,
        False, False, False, False,
    )


def _build_kpi_sparklines(df, start, end, physicians, task_type):
    """Build sparkline data for KPI cards (weekly buckets over 90 days)."""
    data = {}

    # Filter base data
    fdf = df.copy()
    if "StartDateTime" in fdf.columns:
        fdf = fdf[(fdf["StartDateTime"] >= start) & (fdf["StartDateTime"] <= end)]
    if physicians and "AssignedMD" in fdf.columns:
        fdf = fdf[fdf["AssignedMD"].isin(physicians)]
    if task_type == "draw" and "ActivityName" in fdf.columns:
        fdf = fdf[fdf["ActivityName"].str.contains("Draw", case=False, na=False)]
    elif task_type == "review" and "ActivityName" in fdf.columns:
        fdf = fdf[fdf["ActivityName"].str.contains("Review", case=False, na=False)]

    if fdf.empty or "StartDateTime" not in fdf.columns:
        return data

    fdf = fdf.copy()
    fdf["week"] = fdf["StartDateTime"].dt.to_period("W").dt.start_time
    is_completed = fdf["CompletedDateTime"].notna() if "CompletedDateTime" in fdf.columns else pd.Series(False, index=fdf.index)

    # Open tasks by week (count where not completed)
    open_by_week = fdf[~is_completed].groupby("week").size().reset_index(name="count")
    if not open_by_week.empty:
        data["open"] = {
            "x": open_by_week["week"].dt.strftime("%Y-%m-%d").tolist(),
            "y": open_by_week["count"].tolist(),
        }

    # Completed by week
    comp_by_week = fdf[is_completed].groupby("week").size().reset_index(name="count")
    if not comp_by_week.empty:
        data["completed"] = {
            "x": comp_by_week["week"].dt.strftime("%Y-%m-%d").tolist(),
            "y": comp_by_week["count"].tolist(),
        }

    # Median time by week
    if "MinutesToComplete" in fdf.columns:
        fdf["MinutesToComplete"] = pd.to_numeric(fdf["MinutesToComplete"], errors="coerce")
        time_by_week = fdf[is_completed].groupby("week")["MinutesToComplete"].median().reset_index(name="median")
        time_by_week = time_by_week.dropna()
        if not time_by_week.empty:
            data["time"] = {
                "x": time_by_week["week"].dt.strftime("%Y-%m-%d").tolist(),
                "y": time_by_week["median"].tolist(),
            }

    # SLA compliance by week
    if "MinutesToComplete" in fdf.columns and "MinutesAllowed" in fdf.columns:
        fdf["MinutesAllowed"] = pd.to_numeric(fdf["MinutesAllowed"], errors="coerce")
        completed_fdf = fdf[is_completed].dropna(subset=["MinutesToComplete", "MinutesAllowed"])
        completed_fdf = completed_fdf.copy()
        completed_fdf["on_time"] = completed_fdf["MinutesToComplete"] <= completed_fdf["MinutesAllowed"]
        sla_by_week = completed_fdf.groupby("week")["on_time"].mean().reset_index(name="pct")
        sla_by_week["pct"] *= 100
        if not sla_by_week.empty:
            data["sla"] = {
                "x": sla_by_week["week"].dt.strftime("%Y-%m-%d").tolist(),
                "y": sla_by_week["pct"].tolist(),
            }

    # After-hours by week
    if "CompletedDateTime" in fdf.columns:
        completed_tasks = fdf[is_completed].copy()
        completed_tasks["hour"] = completed_tasks["CompletedDateTime"].dt.hour
        completed_tasks["after_hours"] = (completed_tasks["hour"] < 8) | (completed_tasks["hour"] >= 17)
        ah_by_week = completed_tasks.groupby("week")["after_hours"].sum().reset_index(name="count")
        if not ah_by_week.empty:
            data["afterhours"] = {
                "x": ah_by_week["week"].dt.strftime("%Y-%m-%d").tolist(),
                "y": ah_by_week["count"].tolist(),
            }

    return data


def _build_volume_store(df):
    """Prepare volume trend data for clientside rendering."""
    if "StartDateTime" not in df.columns:
        return None

    df = df.copy()
    df["month"] = df["StartDateTime"].dt.to_period("M").dt.to_timestamp()

    traces = []
    if "ActivityName" in df.columns:
        for i, ttype in enumerate(df["ActivityName"].unique()):
            tdata = df[df["ActivityName"] == ttype].groupby("month").size().reset_index(name="count")
            traces.append({
                "x": tdata["month"].dt.strftime("%Y-%m-%d").tolist(),
                "y": tdata["count"].tolist(),
                "name": ttype,
                "color": color_for_index(i),
            })
    else:
        monthly = df.groupby("month").size().reset_index(name="count")
        traces.append({
            "x": monthly["month"].dt.strftime("%Y-%m-%d").tolist(),
            "y": monthly["count"].tolist(),
            "name": "Tasks",
            "color": PRIMARY,
        })

    return {"traces": traces, "chartType": "bar"}


def _build_sla_store(df, is_completed):
    """Prepare SLA trend data for clientside rendering."""
    if "MinutesToComplete" not in df.columns or "MinutesAllowed" not in df.columns or "StartDateTime" not in df.columns:
        return None

    completed = df[is_completed].copy()
    completed["MinutesToComplete"] = pd.to_numeric(completed["MinutesToComplete"], errors="coerce")
    completed["MinutesAllowed"] = pd.to_numeric(completed["MinutesAllowed"], errors="coerce")
    completed = completed.dropna(subset=["MinutesToComplete", "MinutesAllowed"])

    if completed.empty:
        return None

    completed["month"] = completed["StartDateTime"].dt.to_period("M").dt.to_timestamp()
    completed["on_time"] = completed["MinutesToComplete"] <= completed["MinutesAllowed"]

    traces = []

    # Overall
    monthly = completed.groupby("month")["on_time"].mean().reset_index()
    monthly["on_time"] *= 100
    traces.append({
        "x": monthly["month"].dt.strftime("%Y-%m-%d").tolist(),
        "y": monthly["on_time"].tolist(),
        "name": "Overall",
        "color": PRIMARY,
    })

    # Per physician
    if "AssignedMD" in completed.columns:
        for i, md in enumerate(completed["AssignedMD"].unique()[:4]):
            md_data = completed[completed["AssignedMD"] == md]
            md_monthly = md_data.groupby("month")["on_time"].mean().reset_index()
            md_monthly["on_time"] *= 100
            traces.append({
                "x": md_monthly["month"].dt.strftime("%Y-%m-%d").tolist(),
                "y": md_monthly["on_time"].tolist(),
                "name": md.split(",")[0] if "," in md else md,
                "color": color_for_index(i + 1),
                "dash": "dash",
            })

    return {"traces": traces, "chartType": "line", "yRange": [50, 105]}


def _build_histogram(df, is_completed):
    if "MinutesToComplete" not in df.columns:
        return empty_figure("No completion time data")

    vals = pd.to_numeric(df.loc[is_completed, "MinutesToComplete"], errors="coerce").dropna()
    if len(vals) == 0:
        return empty_figure()

    fig = go.Figure(go.Histogram(
        x=vals, nbinsx=30,
        marker_color=PRIMARY, opacity=0.8,
    ))

    # SLA threshold line
    if "MinutesAllowed" in df.columns:
        sla = pd.to_numeric(df["MinutesAllowed"], errors="coerce").dropna()
        if len(sla) > 0:
            sla_val = sla.mode().iloc[0] if len(sla.mode()) > 0 else sla.median()
            fig.add_vline(x=sla_val, line_dash="dash", line_color=SEMANTIC_COLORS["error"],
                          annotation_text=f"SLA: {sla_val:.0f}m")

    apply_default_layout(fig, height=320)
    fig.update_layout(xaxis_title="Minutes", yaxis_title="Count", margin=dict(l=48, r=16, t=16, b=48))
    return fig


def _build_physician_comparison(df, is_completed):
    if "AssignedMD" not in df.columns or "MinutesToComplete" not in df.columns:
        return empty_figure()

    completed = df[is_completed].copy()
    completed["MinutesToComplete"] = pd.to_numeric(completed["MinutesToComplete"], errors="coerce")

    if "ActivityName" in completed.columns:
        types = completed["ActivityName"].unique()
        fig = go.Figure()
        for i, ttype in enumerate(types):
            tdata = completed[completed["ActivityName"] == ttype]
            md_median = tdata.groupby("AssignedMD")["MinutesToComplete"].median().reset_index()
            fig.add_trace(go.Bar(
                x=md_median["AssignedMD"].str.split(",").str[0],
                y=md_median["MinutesToComplete"],
                name=ttype, marker_color=color_for_index(i),
            ))
        apply_default_layout(fig, barmode="group", height=320)
    else:
        md_median = completed.groupby("AssignedMD")["MinutesToComplete"].median().reset_index()
        fig = go.Figure(go.Bar(
            x=md_median["AssignedMD"].str.split(",").str[0],
            y=md_median["MinutesToComplete"],
            marker_color=PRIMARY,
        ))
        apply_default_layout(fig, height=320)

    fig.update_layout(yaxis_title="Median Minutes", margin=dict(l=48, r=16, t=16, b=48))
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
    table_df = table_df.fillna("—")

    return dag.AgGrid(
        id="tasks-detail-grid",
        rowData=table_df.to_dict("records"),
        columnDefs=display_cols,
        defaultColDef={"sortable": True, "filter": True, "resizable": True},
        dashGridOptions={"pagination": True, "paginationPageSize": 25, "domLayout": "autoHeight"},
        className="ag-theme-alpine",
    )


# ---------------------------------------------------------------------------
# Clientside callbacks for charts with smoothing
# ---------------------------------------------------------------------------
clientside_callback(
    ClientsideFunction(namespace="census", function_name="smoothChartWithType"),
    Output("tasks-chart-volume", "figure"),
    Input("tasks-store-volume", "data"),
    Input("tasks-chart-volume-settings-type", "value"),
    Input("tasks-chart-volume-settings-smooth", "checked"),
)

clientside_callback(
    ClientsideFunction(namespace="census", function_name="smoothChartWithType"),
    Output("tasks-chart-sla", "figure"),
    Input("tasks-store-sla", "data"),
    Input("tasks-chart-sla-settings-type", "value"),
    Input("tasks-chart-sla-settings-smooth", "checked"),
)

# ---------------------------------------------------------------------------
# Clientside callbacks for KPI sparklines
# ---------------------------------------------------------------------------
clientside_callback(
    ClientsideFunction(namespace="sparklines", function_name="updateFromStore"),
    Output("tasks-spark-open", "figure"),
    Input("tasks-store-kpi-sparklines", "data"),
    Input("tasks-spark-open", "id"),
)

clientside_callback(
    ClientsideFunction(namespace="sparklines", function_name="updateFromStore"),
    Output("tasks-spark-completed", "figure"),
    Input("tasks-store-kpi-sparklines", "data"),
    Input("tasks-spark-completed", "id"),
)

clientside_callback(
    ClientsideFunction(namespace="sparklines", function_name="updateFromStore"),
    Output("tasks-spark-time", "figure"),
    Input("tasks-store-kpi-sparklines", "data"),
    Input("tasks-spark-time", "id"),
)

clientside_callback(
    ClientsideFunction(namespace="sparklines", function_name="updateFromStore"),
    Output("tasks-spark-sla", "figure"),
    Input("tasks-store-kpi-sparklines", "data"),
    Input("tasks-spark-sla", "id"),
)

clientside_callback(
    ClientsideFunction(namespace="sparklines", function_name="updateFromStore"),
    Output("tasks-spark-afterhours", "figure"),
    Input("tasks-store-kpi-sparklines", "data"),
    Input("tasks-spark-afterhours", "id"),
)
