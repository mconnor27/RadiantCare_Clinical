"""Workflow page — Flow-Gantt pipeline, stage duration violins, pipeline trend."""

import dash
import dash_mantine_components as dmc
from dash import callback, Input, Output, State, dcc, clientside_callback, ClientsideFunction
from dash_iconify import DashIconify
import dash_ag_grid as dag
import plotly.graph_objects as go
import pandas as pd
import numpy as np
from datetime import timedelta

from config.settings import CHART_COLORWAY, DEFAULT_LAYOUT, FONT_FAMILY, PRIMARY
from components.filter_bar import (
    filter_bar, date_presets, department_chips, physician_select, date_range_picker,
)
from components.kpi_card import kpi_card
from components.chart_settings import chart_settings_popover
from utils.charts import apply_default_layout, empty_figure

dash.register_page(__name__, path="/workflow", name="Workflow", order=2)

# Stage definitions (canonical order, excluding ContourReview by default)
STAGES = ["Exam", "Simulation", "Draw", "Isodose", "ReviewPlan", "Treatment"]
STAGE_LABELS = {
    "Exam": "Consult",
    "Simulation": "Simulation",
    "Draw": "Draw Volumes",
    "Isodose": "Isodose Plan",
    "ReviewPlan": "Review Plan",
    "Treatment": "First Treatment",
}
INTER_STAGE_LABELS = [
    "Consult→Sim", "Sim→Draw", "Draw→Isodose", "Isodose→Review", "Review→Tx",
]


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
                dmc.Title("Workflow", order=2, className="page-title"),
                filter_bar("workflow", children=[
                    date_presets("workflow"),
                    date_range_picker("workflow"),
                    department_chips("workflow"),
                    physician_select("workflow"),
                    dmc.MultiSelect(
                        id="workflow-filter-diagnosis",
                        placeholder="Diagnosis",
                        data=[],
                        clearable=True,
                        size="sm",
                        w=200,
                    ),
                    dmc.MultiSelect(
                        id="workflow-filter-modality",
                        placeholder="Modality",
                        data=[
                            {"value": "EBRT", "label": "EBRT"},
                            {"value": "Brachytherapy", "label": "Brachy"},
                            {"value": "Undetermined", "label": "Undet."},
                        ],
                        clearable=True,
                        size="sm",
                        w=160,
                    ),
                ]),
            ],
        ),

        # KPI row — 4 cards with sparklines
        dmc.Grid(id="wf-kpi-row", gutter="md", children=[
            dmc.GridCol(id="wf-kpi-consult-sim", span={"base": 6, "md": 3}),
            dmc.GridCol(id="wf-kpi-review-tx", span={"base": 6, "md": 3}),
            dmc.GridCol(id="wf-kpi-total", span={"base": 6, "md": 3}),
            dmc.GridCol(id="wf-kpi-pipeline", span={"base": 6, "md": 3}),
        ]),

        # Flow-Gantt — full width
        dmc.Paper(
            children=[
                dmc.Group(
                    justify="space-between", mb="sm",
                    children=[
                        dmc.Text("Patient Treatment Pipeline", size="sm", fw=500, c="#6B7280"),
                        dmc.Group(gap="sm", children=[
                            dmc.Switch(
                                id="wf-sankey-loopback-switch",
                                label="Loopbacks",
                                size="xs",
                                checked=False,
                            ),
                        ]),
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
                        ),
                        dcc.Graph(
                            id="wf-chart-sankey",
                            config={"displayModeBar": False},
                            style={"height": "600px"},
                        ),
                    ],
                ),
            ],
            p="md", radius="md", shadow="xs", withBorder=True,
        ),

        # Violin + Trend side by side
        dmc.Grid(gutter="md", children=[
            dmc.GridCol(
                dmc.Paper(
                    children=[
                        dmc.Text("Stage Duration (days)", size="sm", fw=500, c="#6B7280", mb="sm"),
                        dmc.Box(
                            pos="relative",
                            children=[
                                dmc.LoadingOverlay(
                                    id="wf-violin-loading",
                                    visible=False,
                                    loaderProps={"type": "dots", "color": "#7C2A83"},
                                    overlayProps={"radius": "sm", "blur": 2},
                                ),
                                dcc.Graph(id="wf-chart-violin", config={"displayModeBar": False}),
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
                        dmc.Group(
                            justify="space-between", mb="sm",
                            children=[
                                dmc.Text("Pipeline Trend (monthly median)", size="sm", fw=500, c="#6B7280"),
                                chart_settings_popover(
                                    "wf-trend",
                                    chart_types=[
                                        {"value": "line", "label": "Line"},
                                        {"value": "area", "label": "Area"},
                                    ],
                                    show_smooth=True,
                                    smooth_max=12,
                                    smooth_default=3,
                                ),
                            ],
                        ),
                        dmc.Box(
                            pos="relative",
                            children=[
                                dmc.LoadingOverlay(
                                    id="wf-trend-loading",
                                    visible=False,
                                    loaderProps={"type": "dots", "color": "#7C2A83"},
                                    overlayProps={"radius": "sm", "blur": 2},
                                ),
                                dcc.Graph(id="wf-chart-trend", config={"displayModeBar": False}),
                            ],
                        ),
                    ],
                    p="md", radius="md", shadow="xs", withBorder=True,
                ),
                span={"base": 12, "md": 6},
            ),
        ]),

        # Detail table
        dmc.Paper(
            children=[
                dmc.Group(justify="space-between", mb="sm", children=[
                    dmc.Text("Patient Pipeline Detail", size="sm", fw=500, c="#6B7280"),
                    dmc.Button(
                        "Export CSV",
                        id="wf-table-export",
                        size="compact-xs",
                        variant="light",
                    ),
                ]),
                dag.AgGrid(
                    id="wf-detail-grid",
                    columnDefs=[],
                    rowData=[],
                    defaultColDef={"sortable": True, "filter": True, "resizable": True},
                    dashGridOptions={"pagination": True, "paginationPageSize": 25},
                    style={"height": 400},
                    className="ag-theme-quartz",
                ),
            ],
            p="md", radius="md", shadow="xs", withBorder=True,
        ),

        dcc.Interval(id="wf-interval", interval=300_000, n_intervals=0),

        # Stores for clientside rendering
        dcc.Store(id="wf-store-sankey"),
        dcc.Store(id="wf-store-trend"),
        dcc.Store(id="wf-store-kpi-sparklines"),
    ],
)


# ---------------------------------------------------------------------------
# Data Processing Helpers
# ---------------------------------------------------------------------------

def _get_date_range(date_preset, daterange, last_date):
    """Calculate start/end based on preset or explicit range."""
    if daterange and len(daterange) == 2 and daterange[0] and daterange[1]:
        return pd.Timestamp(daterange[0]), pd.Timestamp(daterange[1])
    elif date_preset == "ytd":
        return pd.Timestamp(last_date.year, 1, 1), last_date
    elif date_preset == "12mo":
        return last_date - timedelta(days=365), last_date
    else:
        return pd.Timestamp("2020-01-01"), last_date


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
                 "TreatingPhysician", "DiagnosisDescriptions", "ModalityType"]
    info_cols = [c for c in info_cols if c in deduped.columns]
    info = deduped.drop_duplicates(subset=["UniqueRowID"], keep="first")[info_cols]
    info = info.set_index("UniqueRowID")

    result = pivot.join(info, how="left")
    return result.reset_index()


def _compute_flow_data(pivot, wf_full):
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

            # Median inter-stage duration
            delta = (pivot.loc[reached_current & reached_next, next_stage]
                     - pivot.loc[reached_current & reached_next, stage])
            days = delta.dt.total_seconds() / 86400
            days = days[(days >= 0) & (days < 365)]
            median_days.append(round(float(days.median()), 1) if len(days) > 0 else 0)

    # Compute x-positions: guarantee minimum spacing + proportional bonus
    n_gaps = len(median_days)
    min_gap = 0.07  # minimum spacing between consecutive stages
    total_min = min_gap * n_gaps
    remaining = max(1.0 - total_min, 0.0)
    total_duration = sum(median_days) if median_days else 1
    if total_duration <= 0:
        total_duration = 1

    x_positions = [0.0]
    cumulative = 0.0
    for d in median_days:
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
                if fi is not None and ti is not None:
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
        "xPositions": x_positions,
        "colors": colors,
        "loopbacks": loopbacks,
        "loopbackPairs": loopback_pairs,
        "totalPatients": total,
        "height": 600,
    }


# ---------------------------------------------------------------------------
# Callbacks
# ---------------------------------------------------------------------------

@callback(
    Output("workflow-filter-diagnosis", "data"),
    Input("wf-interval", "n_intervals"),
)
def populate_diagnosis_options(_n):
    """Populate diagnosis filter with unique values from workflow data."""
    try:
        from data.loader import load_workflow
        wf = load_workflow()
        if "DiagnosisDescriptions" in wf.columns:
            diags = sorted(wf["DiagnosisDescriptions"].dropna().unique().tolist())
            return [{"value": d, "label": d} for d in diags[:100]]
    except Exception:
        pass
    return []


@callback(
    Output("wf-kpi-consult-sim", "children"),
    Output("wf-kpi-review-tx", "children"),
    Output("wf-kpi-total", "children"),
    Output("wf-kpi-pipeline", "children"),
    Output("wf-store-sankey", "data"),
    Output("wf-chart-violin", "figure"),
    Output("wf-store-trend", "data"),
    Output("wf-detail-grid", "rowData"),
    Output("wf-detail-grid", "columnDefs"),
    Output("wf-store-kpi-sparklines", "data"),
    Input("wf-interval", "n_intervals"),
    Input("workflow-filter-department", "value"),
    Input("workflow-filter-date-preset", "value"),
    Input("workflow-filter-daterange", "value"),
    Input("workflow-filter-physician", "value"),
    Input("workflow-filter-diagnosis", "value"),
    Input("workflow-filter-modality", "value"),
    running=[
        (Output("wf-sankey-loading", "visible"), True, False),
        (Output("wf-violin-loading", "visible"), True, False),
        (Output("wf-trend-loading", "visible"), True, False),
    ],
)
def update_workflow(_n, departments, date_preset, daterange, physicians, diagnosis, modality):
    from data.loader import load_workflow

    try:
        wf = load_workflow()
    except Exception:
        empty = empty_figure("Workflow data unavailable")
        na = kpi_card("—", "N/A")
        return na, na, na, na, None, empty, None, [], [], {}

    if wf.empty:
        empty = empty_figure("No workflow data")
        na = kpi_card("—", "N/A")
        return na, na, na, na, None, empty, None, [], [], {}

    # Forward-fill exam info (Department, Physician, etc.)
    wf = _forward_fill_exam_info(wf)

    # Keep full data for loopback counts before filtering
    wf_full = wf

    # Get date range from Exam rows
    exam_dates = wf.loc[wf["StageName"] == "Exam", "StageDateTime"].dropna()
    last_date = exam_dates.max() if not exam_dates.empty else pd.Timestamp.now().normalize()
    start, end = _get_date_range(date_preset, daterange, last_date)

    # Apply filters
    if departments and "Department" in wf.columns:
        wf = wf[wf["Department"].isin(departments)]

    if physicians:
        phys_col = next((c for c in ["TreatingPhysician", "AppointmentPhysician"] if c in wf.columns), None)
        if phys_col:
            wf = wf[wf[phys_col].isin(physicians)]

    if diagnosis and "DiagnosisDescriptions" in wf.columns:
        wf = wf[wf["DiagnosisDescriptions"].isin(diagnosis)]

    if modality and "ModalityType" in wf.columns:
        wf = wf[wf["ModalityType"].isin(modality)]

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
        empty = empty_figure("No data for selected filters")
        na = kpi_card("—", "N/A")
        return na, na, na, na, None, empty, None, [], [], {}

    # Pivot to course-level — ensure clean integer index for column arithmetic
    pivot = _pivot_to_courses(wf).reset_index(drop=True)

    if pivot.empty:
        empty = empty_figure("No course data")
        na = kpi_card("—", "N/A")
        return na, na, na, na, None, empty, None, [], [], {}

    # --- KPIs ---
    sparkline_data = {}

    def compute_duration(col_from, col_to):
        """Compute inter-stage duration in days."""
        if col_from in pivot.columns and col_to in pivot.columns:
            days = (pivot[col_to] - pivot[col_from]).dt.total_seconds() / 86400
            days = days[(days >= 0) & (days < 365)].dropna()
            return days
        return pd.Series(dtype=float)

    def build_monthly_sparkline(col_from, col_to, color):
        """Build monthly median sparkline for an inter-stage duration."""
        if col_from not in pivot.columns or col_to not in pivot.columns:
            return None
        if "Exam" not in pivot.columns:
            return None
        cols = list(set([col_from, col_to, "Exam"]))
        temp = pivot[cols].reset_index(drop=True).copy()
        temp["_days"] = (temp[col_to] - temp[col_from]).dt.total_seconds() / 86400
        temp = temp[(temp["_days"] >= 0) & (temp["_days"] < 365)].dropna(subset=["_days", "Exam"])
        if temp.empty:
            return None
        temp["_month"] = temp["Exam"].dt.to_period("M").dt.to_timestamp()
        monthly = temp.groupby("_month")["_days"].median()
        return {
            "labels": [d.isoformat() for d in monthly.index],
            "values": monthly.tolist(),
            "color": color,
        }

    # KPI 1: Exam → Sim
    cs_days = compute_duration("Exam", "Simulation")
    cs_median = cs_days.median() if len(cs_days) > 0 else None
    cs_spark = build_monthly_sparkline("Exam", "Simulation", CHART_COLORWAY[0])
    if cs_spark:
        sparkline_data["consult_sim"] = cs_spark
    kpi_cs = kpi_card(
        "Consult→Sim (median days)",
        f"{cs_median:.0f}" if cs_median is not None else "N/A",
        accent_color=CHART_COLORWAY[0],
        sparkline_id="wf-spark-consult-sim",
    )

    # KPI 2: Review → Treatment
    rt_days = compute_duration("ReviewPlan", "Treatment")
    rt_median = rt_days.median() if len(rt_days) > 0 else None
    rt_spark = build_monthly_sparkline("ReviewPlan", "Treatment", CHART_COLORWAY[1])
    if rt_spark:
        sparkline_data["review_tx"] = rt_spark
    kpi_rt = kpi_card(
        "Review→Tx (median days)",
        f"{rt_median:.0f}" if rt_median is not None else "N/A",
        accent_color=CHART_COLORWAY[1],
        sparkline_id="wf-spark-review-tx",
    )

    # KPI 3: Total Pipeline
    total_days = compute_duration("Exam", "Treatment")
    total_median = total_days.median() if len(total_days) > 0 else None
    total_spark = build_monthly_sparkline("Exam", "Treatment", CHART_COLORWAY[2])
    if total_spark:
        sparkline_data["total"] = total_spark
    kpi_total = kpi_card(
        "Total Pipeline (median days)",
        f"{total_median:.0f}" if total_median is not None else "N/A",
        accent_color=CHART_COLORWAY[2],
        sparkline_id="wf-spark-total",
    )

    # KPI 4: In Pipeline (recent Exam but no Treatment, within 90 days)
    if "Exam" in pivot.columns and "Treatment" in pivot.columns:
        recent_cutoff = last_date - timedelta(days=90)
        recent = pivot[(pivot["Exam"].notna()) & (pivot["Exam"] >= recent_cutoff)]
        pipeline_count = int(recent["Treatment"].isna().sum())
    else:
        pipeline_count = 0
    kpi_pipe = kpi_card("In Pipeline", str(pipeline_count), accent_color=PRIMARY)

    # --- Flow-Gantt data ---
    sankey_data = _compute_flow_data(pivot, wf_full)

    # --- Violin chart ---
    fig_violin = _build_violin(pivot)

    # --- Trend data ---
    trend_data = _prepare_trend_data(pivot)

    # --- Detail table ---
    row_data, col_defs = _build_table_data(pivot)

    return (kpi_cs, kpi_rt, kpi_total, kpi_pipe,
            sankey_data, fig_violin, trend_data,
            row_data, col_defs, sparkline_data)


# ---------------------------------------------------------------------------
# Clientside callbacks for sparklines
# ---------------------------------------------------------------------------

clientside_callback(
    """function(data, _trigger) {
        if (!data || !data.consult_sim) return window.dash_clientside.no_update;
        var spark = data.consult_sim;
        return {
            data: [{x: spark.labels, y: spark.values, mode: "lines", line: {color: spark.color, width: 1.5}}],
            layout: {margin: {l: 0, r: 0, t: 0, b: 0}, height: 34, plot_bgcolor: "rgba(0,0,0,0)", paper_bgcolor: "rgba(0,0,0,0)", xaxis: {visible: false}, yaxis: {visible: false}, showlegend: false, hovermode: "x"}
        };
    }""",
    Output("wf-spark-consult-sim", "figure"),
    Input("wf-store-kpi-sparklines", "data"),
    Input("workflow-filter-date-preset", "value"),
)

clientside_callback(
    """function(data, _trigger) {
        if (!data || !data.review_tx) return window.dash_clientside.no_update;
        var spark = data.review_tx;
        return {
            data: [{x: spark.labels, y: spark.values, mode: "lines", line: {color: spark.color, width: 1.5}}],
            layout: {margin: {l: 0, r: 0, t: 0, b: 0}, height: 34, plot_bgcolor: "rgba(0,0,0,0)", paper_bgcolor: "rgba(0,0,0,0)", xaxis: {visible: false}, yaxis: {visible: false}, showlegend: false, hovermode: "x"}
        };
    }""",
    Output("wf-spark-review-tx", "figure"),
    Input("wf-store-kpi-sparklines", "data"),
    Input("workflow-filter-date-preset", "value"),
)

clientside_callback(
    """function(data, _trigger) {
        if (!data || !data.total) return window.dash_clientside.no_update;
        var spark = data.total;
        return {
            data: [{x: spark.labels, y: spark.values, mode: "lines", line: {color: spark.color, width: 1.5}}],
            layout: {margin: {l: 0, r: 0, t: 0, b: 0}, height: 34, plot_bgcolor: "rgba(0,0,0,0)", paper_bgcolor: "rgba(0,0,0,0)", xaxis: {visible: false}, yaxis: {visible: false}, showlegend: false, hovermode: "x"}
        };
    }""",
    Output("wf-spark-total", "figure"),
    Input("wf-store-kpi-sparklines", "data"),
    Input("workflow-filter-date-preset", "value"),
)


# ---------------------------------------------------------------------------
# Clientside callback for Flow-Gantt
# ---------------------------------------------------------------------------

clientside_callback(
    ClientsideFunction(namespace="flowGantt", function_name="renderFlowGantt"),
    Output("wf-chart-sankey", "figure"),
    Input("wf-store-sankey", "data"),
    Input("wf-sankey-loopback-switch", "checked"),
)


# ---------------------------------------------------------------------------
# Clientside callback for trend chart
# ---------------------------------------------------------------------------

clientside_callback(
    ClientsideFunction(namespace="census", function_name="smoothChartWithType"),
    Output("wf-chart-trend", "figure"),
    Input("wf-store-trend", "data"),
    Input("wf-trend-settings-smooth", "value"),
    Input("wf-trend-settings-type", "value"),
    State("wf-chart-trend", "figure"),
)


# ---------------------------------------------------------------------------
# Settings panel toggle
# ---------------------------------------------------------------------------

@callback(
    Output("wf-trend-settings-panel", "style"),
    Input("wf-trend-settings-btn", "n_clicks"),
    State("wf-trend-settings-panel", "style"),
    prevent_initial_call=True,
)
def toggle_trend_settings(n, style):
    if not n:
        return style
    current = style or {}
    is_hidden = current.get("display") == "none"
    return {"display": "block"} if is_hidden else {"display": "none"}


# ---------------------------------------------------------------------------
# Chart builders
# ---------------------------------------------------------------------------

def _build_violin(pivot):
    """Violin plots of inter-stage durations from pivoted course data."""
    fig = go.Figure()

    pairs = [
        ("Exam", "Simulation", "Consult→Sim"),
        ("Simulation", "Draw", "Sim→Draw"),
        ("Draw", "Isodose", "Draw→Isodose"),
        ("Isodose", "ReviewPlan", "Isodose→Review"),
        ("ReviewPlan", "Treatment", "Review→Tx"),
    ]

    for col_from, col_to, label in pairs:
        if col_from in pivot.columns and col_to in pivot.columns:
            days = (pivot[col_to] - pivot[col_from]).dt.total_seconds() / 86400
            days = days[(days >= 0) & (days < 365)].dropna()
            if len(days) > 0:
                fig.add_trace(go.Violin(
                    y=days, name=label,
                    box_visible=True, meanline_visible=True,
                    points="outliers",
                    fillcolor=CHART_COLORWAY[len(fig.data) % len(CHART_COLORWAY)],
                    opacity=0.7, line_color="#1A1A2E",
                ))

    apply_default_layout(fig, height=350)
    fig.update_layout(yaxis_title="Days", margin=dict(l=48, r=16, t=16, b=48), showlegend=False)
    return fig


def _prepare_trend_data(pivot):
    """Prepare trend data for clientside rendering."""
    if "Exam" not in pivot.columns or "Treatment" not in pivot.columns:
        return None

    temp = pivot[["Exam", "Treatment"]].reset_index(drop=True).copy()
    temp["total_days"] = (temp["Treatment"] - temp["Exam"]).dt.total_seconds() / 86400
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
            stage_temp["_days"] = (stage_temp[col_to] - stage_temp[col_from]).dt.total_seconds() / 86400
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


def _build_table_data(pivot):
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
        table["days_to_sim"] = (
            (table["Simulation"] - table["Exam"]).dt.total_seconds() / 86400
        ).round(1)
    if "Exam" in table.columns and "Treatment" in table.columns:
        table["total_days"] = (
            (table["Treatment"] - table["Exam"]).dt.total_seconds() / 86400
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
# PNG Export
# ---------------------------------------------------------------------------

clientside_callback(
    """function(n) {
        if (!n) return window.dash_clientside.no_update;
        var wrapper = document.getElementById('wf-chart-trend');
        var graphEl = wrapper ? wrapper.querySelector('.js-plotly-plot') : null;
        if (graphEl) Plotly.downloadImage(graphEl, {format: 'png', width: 1200, height: 600, filename: 'pipeline_trend'});
        return window.dash_clientside.no_update;
    }""",
    Output("wf-trend-settings-export", "n_clicks"),
    Input("wf-trend-settings-export", "n_clicks"),
    prevent_initial_call=True,
)

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
