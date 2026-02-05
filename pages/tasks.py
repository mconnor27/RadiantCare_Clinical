"""Tasks page — physician task workload, SLA compliance, after-hours tracking."""

import dash
import dash_mantine_components as dmc
from dash import callback, Input, Output, dcc
import dash_ag_grid as dag
import plotly.graph_objects as go
import pandas as pd
import numpy as np
from datetime import timedelta

from config.settings import (
    PHYSICIANS, CHART_COLORWAY, PRIMARY, FONT_FAMILY,
    SEMANTIC_COLORS,
)
from components.filter_bar import filter_bar, date_presets, physician_select
from components.kpi_card import kpi_card
from utils.charts import apply_default_layout, empty_figure, color_for_index

dash.register_page(__name__, path="/tasks", name="Tasks", order=5)

# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------
layout = dmc.Stack(
    gap="md",
    children=[
        dmc.Title("Tasks", order=2, c="#7C2A83", ta="center", fw=700, py="sm"),
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

        # KPI row
        dmc.Grid(id="tasks-kpi-row", gutter="md", children=[
            dmc.GridCol(id="tasks-kpi-open", span={"base": 6, "md": 2}),
            dmc.GridCol(id="tasks-kpi-completed", span={"base": 6, "md": 2}),
            dmc.GridCol(id="tasks-kpi-time", span={"base": 6, "md": 3}),
            dmc.GridCol(id="tasks-kpi-sla", span={"base": 6, "md": 2}),
            dmc.GridCol(id="tasks-kpi-afterhrs", span={"base": 6, "md": 3}),
        ]),

        # Charts row 1: Volume trend + Time to Complete
        dmc.Grid(gutter="md", children=[
            dmc.GridCol(
                dmc.Paper(
                    children=[
                        dmc.Text("Task Volume Trend", size="sm", fw=500, c="#6B7280", mb="sm"),
                        dcc.Graph(id="tasks-chart-volume", config={"displayModeBar": False}),
                    ],
                    p="md", radius="md", shadow="xs", withBorder=True,
                ),
                span={"base": 12, "md": 6},
            ),
            dmc.GridCol(
                dmc.Paper(
                    children=[
                        dmc.Text("Time to Complete (minutes)", size="sm", fw=500, c="#6B7280", mb="sm"),
                        dcc.Graph(id="tasks-chart-histogram", config={"displayModeBar": False}),
                    ],
                    p="md", radius="md", shadow="xs", withBorder=True,
                ),
                span={"base": 12, "md": 6},
            ),
        ]),

        # Charts row 2: Physician comparison + SLA trend
        dmc.Grid(gutter="md", children=[
            dmc.GridCol(
                dmc.Paper(
                    children=[
                        dmc.Text("Physician Comparison (median min)", size="sm", fw=500, c="#6B7280", mb="sm"),
                        dcc.Graph(id="tasks-chart-physician", config={"displayModeBar": False}),
                    ],
                    p="md", radius="md", shadow="xs", withBorder=True,
                ),
                span={"base": 12, "md": 6},
            ),
            dmc.GridCol(
                dmc.Paper(
                    children=[
                        dmc.Text("SLA Compliance Trend", size="sm", fw=500, c="#6B7280", mb="sm"),
                        dcc.Graph(id="tasks-chart-sla", config={"displayModeBar": False}),
                    ],
                    p="md", radius="md", shadow="xs", withBorder=True,
                ),
                span={"base": 12, "md": 6},
            ),
        ]),

        # Detail table
        dmc.Paper(
            children=[
                dmc.Text("Task Detail", size="sm", fw=500, c="#6B7280", mb="sm"),
                dmc.Box(id="tasks-table-container"),
            ],
            p="md", radius="md", shadow="xs", withBorder=True,
        ),

        dcc.Interval(id="tasks-interval", interval=300_000, n_intervals=0),
    ],
)


# ---------------------------------------------------------------------------
# Callbacks
# ---------------------------------------------------------------------------

@callback(
    Output("tasks-kpi-open", "children"),
    Output("tasks-kpi-completed", "children"),
    Output("tasks-kpi-time", "children"),
    Output("tasks-kpi-sla", "children"),
    Output("tasks-kpi-afterhrs", "children"),
    Output("tasks-chart-volume", "figure"),
    Output("tasks-chart-histogram", "figure"),
    Output("tasks-chart-physician", "figure"),
    Output("tasks-chart-sla", "figure"),
    Output("tasks-table-container", "children"),
    Input("tasks-interval", "n_intervals"),
    Input("tasks-filter-date-preset", "value"),
    Input("tasks-filter-physician", "value"),
    Input("tasks-filter-type", "value"),
    Input("tasks-filter-status", "value"),
)
def update_tasks(_n, date_preset, physicians, task_type, status):
    from data.loader import load_tasks, load_physician_schedule

    try:
        tasks = load_tasks()
    except Exception:
        empty = empty_figure("Tasks data unavailable")
        na = kpi_card("—", "N/A")
        return na, na, na, na, na, empty, empty, empty, empty, []

    today = pd.Timestamp.now().normalize()
    if date_preset == "ytd":
        start = pd.Timestamp(today.year, 1, 1)
    elif date_preset == "12mo":
        start = today - timedelta(days=365)
    else:
        start = pd.Timestamp("2020-01-01")

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
    elif status == "done":
        df = df[is_completed]

    # --- KPIs ---
    open_count = (~is_completed).sum() if status != "done" else 0
    completed_count = is_completed.sum() if status != "open" else len(df)

    if "MinutesToComplete" in df.columns:
        mins = pd.to_numeric(df.loc[is_completed, "MinutesToComplete"], errors="coerce").dropna()
        median_min = f"{mins.median():.0f}" if len(mins) > 0 else "N/A"
    else:
        median_min = "N/A"
        mins = pd.Series(dtype=float)

    if "MinutesToComplete" in df.columns and "MinutesAllowed" in df.columns:
        completed_df = df[is_completed].copy()
        completed_df["MinutesToComplete"] = pd.to_numeric(completed_df["MinutesToComplete"], errors="coerce")
        completed_df["MinutesAllowed"] = pd.to_numeric(completed_df["MinutesAllowed"], errors="coerce")
        valid = completed_df.dropna(subset=["MinutesToComplete", "MinutesAllowed"])
        if len(valid) > 0:
            sla_pct = (valid["MinutesToComplete"] <= valid["MinutesAllowed"]).mean() * 100
            sla_text = f"{sla_pct:.1f}%"
        else:
            sla_text = "N/A"
    else:
        sla_text = "N/A"

    # After-hours: rough check — completed outside 8am-5pm
    after_hrs_count = 0
    if "CompletedDateTime" in df.columns:
        completed_times = df.loc[is_completed, "CompletedDateTime"]
        hours = completed_times.dt.hour
        after_hrs_count = int(((hours < 8) | (hours >= 17)).sum())

    kpi_open = kpi_card("Open Tasks", str(int(open_count)), accent_color=SEMANTIC_COLORS["warning"])
    kpi_done = kpi_card("Completed", f"{int(completed_count):,}")
    kpi_time = kpi_card("Median Time to Complete", f"{median_min} min")
    kpi_sla = kpi_card("SLA Compliance", sla_text, accent_color=PRIMARY)
    kpi_after = kpi_card("After-Hours Completions", str(after_hrs_count))

    # --- Charts ---
    fig_volume = _build_volume_trend(df, is_completed)
    fig_hist = _build_histogram(df, is_completed)
    fig_physician = _build_physician_comparison(df, is_completed)
    fig_sla = _build_sla_trend(df, is_completed)

    # --- Detail table ---
    table = _build_table(df, is_completed)

    return kpi_open, kpi_done, kpi_time, kpi_sla, kpi_after, fig_volume, fig_hist, fig_physician, fig_sla, table


def _build_volume_trend(df, is_completed):
    if "StartDateTime" not in df.columns:
        return empty_figure()

    df = df.copy()
    df["month"] = df["StartDateTime"].dt.to_period("M").dt.to_timestamp()

    fig = go.Figure()

    if "ActivityName" in df.columns:
        for i, ttype in enumerate(df["ActivityName"].unique()):
            tdata = df[df["ActivityName"] == ttype].groupby("month").size().reset_index(name="count")
            fig.add_trace(go.Bar(
                x=tdata["month"], y=tdata["count"],
                name=ttype, marker_color=color_for_index(i),
            ))
    else:
        monthly = df.groupby("month").size().reset_index(name="count")
        fig.add_trace(go.Bar(x=monthly["month"], y=monthly["count"], marker_color=PRIMARY))

    apply_default_layout(fig, barmode="stack", height=320)
    fig.update_layout(yaxis_title="Tasks", margin=dict(l=48, r=16, t=16, b=48))
    return fig


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


def _build_sla_trend(df, is_completed):
    if "MinutesToComplete" not in df.columns or "MinutesAllowed" not in df.columns or "StartDateTime" not in df.columns:
        return empty_figure()

    completed = df[is_completed].copy()
    completed["MinutesToComplete"] = pd.to_numeric(completed["MinutesToComplete"], errors="coerce")
    completed["MinutesAllowed"] = pd.to_numeric(completed["MinutesAllowed"], errors="coerce")
    completed = completed.dropna(subset=["MinutesToComplete", "MinutesAllowed"])

    if completed.empty:
        return empty_figure()

    completed["month"] = completed["StartDateTime"].dt.to_period("M").dt.to_timestamp()
    completed["on_time"] = completed["MinutesToComplete"] <= completed["MinutesAllowed"]

    monthly = completed.groupby("month")["on_time"].mean().reset_index()
    monthly["on_time"] *= 100

    fig = go.Figure(go.Scatter(
        x=monthly["month"], y=monthly["on_time"],
        mode="lines+markers",
        line=dict(color=PRIMARY, width=2),
        marker=dict(size=5),
        name="Overall",
    ))

    # Per physician if available
    if "AssignedMD" in completed.columns:
        for i, md in enumerate(completed["AssignedMD"].unique()[:4]):
            md_data = completed[completed["AssignedMD"] == md]
            md_monthly = md_data.groupby("month")["on_time"].mean().reset_index()
            md_monthly["on_time"] *= 100
            fig.add_trace(go.Scatter(
                x=md_monthly["month"], y=md_monthly["on_time"],
                mode="lines", name=md.split(",")[0],
                line=dict(color=color_for_index(i + 1), width=1.5, dash="dash"),
            ))

    apply_default_layout(fig, height=320)
    fig.update_layout(
        yaxis_title="SLA Compliance %", yaxis_range=[50, 105],
        margin=dict(l=48, r=16, t=16, b=48),
    )
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
        return dmc.Text("No task data available", c="#9CA3AF", ta="center", py="xl")

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
