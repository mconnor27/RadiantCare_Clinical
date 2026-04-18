"""CPT Audit page — 2026 CPT coding compliance tracking with review workflow."""

import dash
import dash_mantine_components as dmc
from dash import callback, Input, Output, State, dcc, html, no_update, ctx
import dash_ag_grid as dag
import plotly.graph_objects as go
import pandas as pd

from dash_iconify import DashIconify

from config.settings import (
    PRIMARY, NEUTRAL, SEMANTIC_COLORS,
    DEFAULT_COLUMN_DEFS, DEFAULT_GRID_OPTIONS, DEFAULT_GRID_STYLE, DEFAULT_GRID_CLASS,
)
from components.filter_bar import department_chips
from utils.charts import apply_default_layout, empty_figure
from utils.date_slider import month_idx, idx_to_date, MAX_IDX, preset_to_slider_val, preset_to_exact_dates

_DEFAULT_DATE_PRESET = "ytd"

# Scope slider to CPT data range (2026-01 to current month)
_CPT_MIN_IDX = month_idx(2026, 1)
_CPT_MARKS = [
    {"value": month_idx(2026, m), "label": pd.Timestamp(2026, m, 1).strftime("%b")}
    for m in range(1, 13)
    if month_idx(2026, m) <= MAX_IDX
]

dash.register_page(__name__, path="/cpt-audit", name="CPT Audit", order=12)

# ---------------------------------------------------------------------------
# Column definitions (needed by layout)
# ---------------------------------------------------------------------------
_COL_DEFS = [
    {"field": "TreatmentDate", "headerName": "Date", "sort": "desc", "flex": 1.1},
    {"field": "_patient_display", "headerName": "Patient"},
    {"field": "PatientMRN", "headerName": "MRN", "flex": 1.2},
    {"field": "Department", "headerName": "Dept"},
    {"field": "Machine", "headerName": "Machine", "flex": 1.3},
    {"field": "CourseName", "headerName": "Course", "flex": 1.2},
    {"field": "RxTechnique_Day", "headerName": "Tech"},
    {"field": "UniqueIsocenters", "headerName": "Iso", "flex": 0.6},
    {"field": "FieldGating", "headerName": "Gate"},
    {"field": "CPT_Correct", "headerName": "Correct"},
    {"field": "_billed_display", "headerName": "Billed"},
    {"field": "AuditResult", "headerName": "Result",
     "filter": False, "sortable": False,
     "cellStyle": {"styleConditions": [
         {"condition": "params.value === 'PASS'", "style": {"color": SEMANTIC_COLORS["success"], "fontWeight": "600"}},
         {"condition": "params.value === 'FAIL'", "style": {"color": SEMANTIC_COLORS["error"], "fontWeight": "600"}},
     ]}},
    {"field": "ReviewStatus", "headerName": "Review", "flex": 2.3, "minWidth": 180,
     "cellRenderer": "CptReviewButtons", "sortable": False, "filter": False},
]

# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------
layout = dmc.Stack(
    gap=16,
    className="page-content",
    children=[
        # Sticky header with title and single-row filter bar
        dmc.Box(
            className="page-sticky-header",
            children=[
                dmc.Title("CPT Audit", order=2, className="page-title"),
                dmc.Paper(
                    dmc.Group([
                        department_chips("cpt"),
                        dmc.Select(
                            id="cpt-filter-date-preset",
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
                            size="xs", w=140, allowDeselect=False,
                            leftSection=DashIconify(icon="mdi:clock-outline", width=14),
                            comboboxProps={"zIndex": 500, "offset": 2},
                        ),
                        dmc.Paper(
                            dcc.DatePickerRange(
                                id="cpt-filter-daterange",
                                display_format="MMM D, YYYY",
                                start_date_placeholder_text="Start",
                                end_date_placeholder_text="End",
                                clearable=True,
                                number_of_months_shown=2,
                                minimum_nights=0,
                                min_date_allowed="2026-01-01",
                                start_date=idx_to_date(preset_to_slider_val(_DEFAULT_DATE_PRESET, MAX_IDX)[0]).strftime("%Y-%m-%d"),
                                end_date=idx_to_date(preset_to_slider_val(_DEFAULT_DATE_PRESET, MAX_IDX)[1], end_of_month=True).strftime("%Y-%m-%d"),
                                className="wf-date-picker-range",
                            ),
                            px="xs", py=4, radius="sm", withBorder=True,
                            className="wf-datepicker-wrapper",
                        ),
                        dmc.Box(
                            children=[
                                html.Div(id="cpt-date-range-label", style={"display": "none"}),
                                dmc.RangeSlider(
                                    id="cpt-date-slider",
                                    min=_CPT_MIN_IDX, max=MAX_IDX, step=1,
                                    value=preset_to_slider_val(_DEFAULT_DATE_PRESET, MAX_IDX),
                                    marks=_CPT_MARKS,
                                    color="violet", size="sm", minRange=0,
                                ),
                            ],
                            style={"flex": "1", "minWidth": "200px"},
                        ),
                    ], gap="md", align="center", wrap="wrap"),
                    p="sm", px="md", radius="md", shadow="xs", withBorder=True,
                ),
            ],
        ),

        # Compliance trend chart
        dmc.Paper(
            children=[
                dmc.Group([
                    dmc.Text("Compliance Trend", size="sm", fw=500, c=NEUTRAL["text_secondary"]),
                    dmc.Group([
                        dmc.SegmentedControl(
                            id="cpt-chart-agg",
                            data=[
                                {"value": "D", "label": "Daily"},
                                {"value": "W", "label": "Weekly"},
                                {"value": "M", "label": "Monthly"},
                            ],
                            value="W", size="xs",
                        ),
                        dmc.SegmentedControl(
                            id="cpt-chart-mode",
                            data=[
                                {"value": "line", "label": "Line"},
                                {"value": "area", "label": "Area"},
                                {"value": "bar", "label": "Bar"},
                            ],
                            value="area", size="xs",
                        ),
                    ], gap="xs"),
                ], justify="space-between", mb="xs"),
                dmc.Box(
                    pos="relative",
                    children=[
                        dmc.LoadingOverlay(id="cpt-trend-loading", visible=False, loaderProps={"type": "dots", "color": PRIMARY}),
                        dcc.Graph(id="cpt-chart-trend", config={"displayModeBar": False}, style={"height": "180px"}),
                    ],
                ),
            ],
            pt="md", px="md", pb=4, radius="md", shadow="xs", withBorder=True,
        ),

        # Detail table with review workflow
        dmc.Paper(
            children=[
                dmc.Group([
                    dmc.Group([
                        dmc.Text("CPT Audit Detail", size="sm", fw=500, c=NEUTRAL["text_secondary"]),
                        dmc.SegmentedControl(
                            id="cpt-filter-review-status",
                            data=[
                                {"value": "all", "label": "All"},
                                {"value": "unreviewed", "label": "Unreviewed"},
                                {"value": "reviewed", "label": "Reviewed"},
                            ],
                            value="all", size="xs",
                        ),
                        dmc.SegmentedControl(
                            id="cpt-filter-audit-result",
                            data=[
                                {"value": "all", "label": "All"},
                                {"value": "fail", "label": "Failed"},
                                {"value": "pass", "label": "Passed"},
                            ],
                            value="all", size="xs",
                        ),
                        dmc.SegmentedControl(
                            id="cpt-filter-table-date",
                            data=[
                                {"value": "all", "label": "All"},
                                {"value": "yesterday", "label": "Yesterday"},
                                {"value": "week", "label": "This Week"},
                                {"value": "month", "label": "This Month"},
                                {"value": "ytd", "label": "YTD"},
                            ],
                            value="all", size="xs",
                        ),
                    ], gap="sm", align="center"),
                    dmc.Group([
                        dmc.Button(id="cpt-bulk-ok-all",
                                   size="compact-xs", variant="light", color="teal", children="OK All"),
                        dmc.Button("Undo All", id="cpt-bulk-undo-all",
                                   size="compact-xs", variant="light", color="gray"),
                        dmc.Text(id="cpt-table-page-info", size="xs", c=NEUTRAL["text_muted"]),
                        dmc.Text(id="cpt-review-count", size="xs", c=NEUTRAL["text_muted"]),
                        dmc.Button("Export CSV", id="cpt-table-export",
                                   size="compact-xs", variant="light"),
                    ], gap="sm", align="center"),
                ], justify="space-between", mb="sm", wrap="wrap"),
                dmc.Text(id="cpt-table-empty", children="No CPT audit data available",
                         c=NEUTRAL["text_muted"], ta="center", py="xl"),
                dag.AgGrid(
                    id="cpt-detail-grid",
                    rowData=[],
                    columnDefs=_COL_DEFS,
                    defaultColDef={**DEFAULT_COLUMN_DEFS, "flex": 1},
                    columnSize=None,
                    dashGridOptions=DEFAULT_GRID_OPTIONS,
                    className=DEFAULT_GRID_CLASS,
                    style=DEFAULT_GRID_STYLE,
                ),
            ],
            p="md", radius="md", shadow="xs", withBorder=True,
        ),

        # Confirmation modal for bulk actions
        dmc.Modal(
            id="cpt-bulk-confirm-modal",
            title="Confirm Bulk Action",
            centered=True, size="sm",
            children=[
                dmc.Text(id="cpt-bulk-confirm-text", size="sm", mb="md"),
                dmc.Group([
                    dmc.Button("Cancel", id="cpt-bulk-cancel", variant="subtle", color="gray"),
                    dmc.Button("Confirm", id="cpt-bulk-confirm", color="violet"),
                ], justify="flex-end", gap="sm"),
            ],
        ),

        # Stores
        dcc.Store(id="cpt-store-reviews", data={}),
        dcc.Store(id="cpt-store-table-data", data=[]),
        dcc.Store(id="cpt-store-chart-data", data=[]),
        dcc.Store(id="cpt-store-course-reviews", data={}),
        dcc.Store(id="cpt-store-filtered-sids", data=[]),
        dcc.Store(id="cpt-store-pending-bulk", data=None),
        dcc.Store(id="cpt-store-review-action", data=None),
        dcc.Interval(id="cpt-interval", interval=300_000, n_intervals=0),
    ],
)



# ---------------------------------------------------------------------------
# Date preset → slider sync
# ---------------------------------------------------------------------------
@callback(
    Output("cpt-date-slider", "value"),
    Output("cpt-filter-daterange", "start_date", allow_duplicate=True),
    Output("cpt-filter-daterange", "end_date", allow_duplicate=True),
    Input("cpt-filter-date-preset", "value"),
    prevent_initial_call=True,
)
def sync_preset_to_slider(preset):
    if not preset or preset == "custom":
        return (no_update,) * 3
    val = preset_to_slider_val(preset, MAX_IDX)
    # Clamp to CPT data range
    val[0] = max(val[0], _CPT_MIN_IDX)
    s, e = preset_to_exact_dates(preset)
    return val, s, e


@callback(
    Output("cpt-filter-daterange", "start_date"),
    Output("cpt-filter-daterange", "end_date"),
    Input("cpt-date-slider", "value"),
    prevent_initial_call=True,
)
def sync_slider_to_daterange(slider_val):
    if not slider_val:
        return no_update, no_update
    s = idx_to_date(slider_val[0])
    e = idx_to_date(slider_val[1], end_of_month=True)
    return s.strftime("%Y-%m-%d"), e.strftime("%Y-%m-%d")


# D) Slider → auto-set preset to "Custom" when it doesn't match
@callback(
    Output("cpt-filter-date-preset", "value", allow_duplicate=True),
    Input("cpt-date-slider", "value"),
    State("cpt-filter-date-preset", "value"),
    prevent_initial_call=True,
)
def _maybe_clear_preset(slider_val, current_preset):
    if not current_preset or current_preset == "custom":
        return no_update
    expected = preset_to_slider_val(current_preset, MAX_IDX)
    if slider_val == expected:
        return no_update
    return "custom"


# ---------------------------------------------------------------------------
# Main callback — chart + raw table data (filter-driven)
# ---------------------------------------------------------------------------
@callback(
    Output("cpt-store-chart-data", "data"),
    Output("cpt-store-table-data", "data"),
    Output("cpt-trend-loading", "visible"),
    Input("cpt-interval", "n_intervals"),
    Input("cpt-filter-daterange", "start_date"),
    Input("cpt-filter-daterange", "end_date"),
    Input("cpt-filter-department", "value"),
)
def update_cpt_audit(_n, start_date, end_date, departments):
    from data.loader import load_cpt_audit

    try:
        cpt = load_cpt_audit()
    except Exception:
        return [], [], False

    # --- Date filtering ---
    if "TreatmentDate" in cpt.columns:
        cpt["TreatmentDate"] = pd.to_datetime(cpt["TreatmentDate"], errors="coerce")
        last_date = cpt["TreatmentDate"].max()
    else:
        last_date = pd.Timestamp.now().normalize()

    if start_date and end_date:
        start = pd.Timestamp(start_date)
        end = pd.Timestamp(end_date)
    else:
        end = last_date
        start = pd.Timestamp(last_date.year, 1, 1)

    df = cpt.copy()
    if "TreatmentDate" in df.columns:
        df = df[(df["TreatmentDate"] >= start) & (df["TreatmentDate"] <= end)]

    if departments and "Department" in df.columns:
        df = df[df["Department"].isin(departments)]

    if df.empty:
        return [], [], False

    # --- Chart data: per-day pass/total for flexible aggregation ---
    chart_df = df[["TreatmentDate", "AuditResult"]].copy() if "AuditResult" in df.columns else pd.DataFrame()
    if not chart_df.empty:
        chart_df["date"] = chart_df["TreatmentDate"].dt.strftime("%Y-%m-%d")
        daily = chart_df.groupby("date")["AuditResult"].agg(
            total="count", passed=lambda x: (x == "PASS").sum()
        ).reset_index()
        chart_data = daily.to_dict("records")
    else:
        chart_data = []

    # --- Serialize table rows ---
    table_cols = [
        "SessionUniqueID", "TreatmentDate", "PatientName", "PatientFullName",
        "PatientMRN", "Department", "Machine", "CourseName",
        "RxTechnique_Day", "UniqueIsocenters", "FieldGating",
        "CPT_Correct", "CPT_Billed", "AuditResult",
    ]
    keep = [c for c in table_cols if c in df.columns]
    table_df = df[keep].copy()
    if "TreatmentDate" in table_df.columns and pd.api.types.is_datetime64_any_dtype(table_df["TreatmentDate"]):
        sort_cols = ["TreatmentDate"]
        asc = [False]
        if "SessionUniqueID" in table_df.columns:
            sort_cols.append("SessionUniqueID")
            asc.append(True)
        table_df = table_df.sort_values(sort_cols, ascending=asc).reset_index(drop=True)
        # _sort_key: integer index locked to date-desc order from server
        table_df["_sort_key"] = range(len(table_df))
        table_df["TreatmentDate"] = table_df["TreatmentDate"].dt.strftime("%m/%d/%y")
    else:
        table_df["_sort_key"] = range(len(table_df))
    table_records = table_df.fillna("").to_dict("records")

    return chart_data, table_records, False


# ---------------------------------------------------------------------------
# Load reviews from SQLite on page load / interval
# ---------------------------------------------------------------------------
@callback(
    Output("cpt-store-reviews", "data"),
    Output("cpt-store-course-reviews", "data"),
    Input("cpt-interval", "n_intervals"),
)
def load_reviews_from_db(_n):
    from data.reviews_db import get_all_reviews, get_all_course_reviews
    return get_all_reviews(), get_all_course_reviews()


# ---------------------------------------------------------------------------
# Review via AG Grid cellRendererData (no pattern matching!)
# ---------------------------------------------------------------------------
@callback(
    Output("cpt-store-reviews", "data", allow_duplicate=True),
    Output("cpt-store-course-reviews", "data", allow_duplicate=True),
    Input("cpt-store-review-action", "data"),
    State("cpt-store-reviews", "data"),
    State("cpt-store-course-reviews", "data"),
    prevent_initial_call=True,
)
def handle_review(action_data, reviews, course_reviews):
    from data.reviews_db import set_review, remove_review, set_course_review, remove_course_review

    if not action_data:
        return no_update, no_update

    row = action_data
    action = row.get("_action", "")
    sid = str(row.get("SessionUniqueID", ""))
    mrn = str(row.get("PatientMRN", ""))
    course = str(row.get("CourseName", ""))
    course_key = f"{mrn}|{course}"

    reviews = dict(reviews or {})
    course_reviews = dict(course_reviews or {})
    course_updated = False

    if action == "OK" or action == "Fixed":
        set_review(sid, action)
        reviews[sid] = action
    elif action == "undo":
        remove_review(sid)
        reviews.pop(sid, None)
        # Also clear course review if present
        if course_key in course_reviews:
            remove_course_review(mrn, course)
            course_reviews.pop(course_key, None)
            course_updated = True
    elif action == "Course OK":
        set_course_review(mrn, course, "OK")
        course_reviews[course_key] = "OK"
        course_updated = True
    elif action == "undo_course":
        remove_course_review(mrn, course)
        course_reviews.pop(course_key, None)
        course_updated = True

    return reviews, course_reviews if course_updated else no_update


# ---------------------------------------------------------------------------
# Bulk actions — open confirmation modal
# ---------------------------------------------------------------------------
@callback(
    Output("cpt-bulk-confirm-modal", "opened"),
    Output("cpt-bulk-confirm-text", "children"),
    Output("cpt-store-pending-bulk", "data"),
    Input("cpt-bulk-ok-all", "n_clicks"),
    Input("cpt-bulk-undo-all", "n_clicks"),
    Input("cpt-bulk-cancel", "n_clicks"),
    State("cpt-store-filtered-sids", "data"),
    State("cpt-store-reviews", "data"),
    prevent_initial_call=True,
)
def open_bulk_confirm(ok_all, undo_all, cancel, filtered_sids, reviews):
    triggered = ctx.triggered_id
    if triggered == "cpt-bulk-cancel":
        return False, "", None

    if triggered == "cpt-bulk-ok-all":
        count = len(filtered_sids or [])
        return True, f"Mark all {count} unreviewed filtered rows as OK?", {"action": "ok_all"}
    elif triggered == "cpt-bulk-undo-all":
        session_count = len(reviews or {})
        return True, f"Clear all {session_count} session reviews and all course approvals?", {"action": "undo_all"}

    return False, "", None


@callback(
    Output("cpt-store-reviews", "data", allow_duplicate=True),
    Output("cpt-store-course-reviews", "data", allow_duplicate=True),
    Output("cpt-bulk-confirm-modal", "opened", allow_duplicate=True),
    Input("cpt-bulk-confirm", "n_clicks"),
    State("cpt-store-pending-bulk", "data"),
    State("cpt-store-filtered-sids", "data"),
    State("cpt-store-reviews", "data"),
    State("cpt-store-course-reviews", "data"),
    prevent_initial_call=True,
)
def execute_bulk(n, pending, filtered_sids, reviews, course_reviews):
    from data.reviews_db import set_review, remove_review, remove_course_review

    if not pending:
        return no_update, no_update, False

    action = pending.get("action")
    reviews = dict(reviews or {})
    course_updated = False

    if action == "ok_all":
        for sid in (filtered_sids or []):
            set_review(sid, "OK")
            reviews[sid] = "OK"
    elif action == "undo_all":
        # Clear all session reviews
        for sid in list(reviews.keys()):
            remove_review(sid)
        reviews = {}
        # Clear all course reviews
        for key in list((course_reviews or {}).keys()):
            parts = key.split("|", 1)
            if len(parts) == 2:
                remove_course_review(parts[0], parts[1])
        course_reviews = {}
        course_updated = True

    return reviews, course_reviews if course_updated else no_update, False


# ---------------------------------------------------------------------------
# Table callback — updates rowData in-place (grid lives in layout)
# ---------------------------------------------------------------------------
@callback(
    Output("cpt-detail-grid", "rowData"),
    Output("cpt-table-empty", "style"),
    Output("cpt-review-count", "children"),
    Output("cpt-table-page-info", "children"),
    Output("cpt-store-filtered-sids", "data"),
    Output("cpt-bulk-ok-all", "children"),
    Input("cpt-store-table-data", "data"),
    Input("cpt-filter-review-status", "value"),
    Input("cpt-filter-audit-result", "value"),
    Input("cpt-filter-table-date", "value"),
    Input("cpt-store-reviews", "data"),
    Input("cpt-store-course-reviews", "data"),
)
def update_table(table_records, review_filter, result_filter, table_date, reviews, course_reviews):
    reviews = reviews or {}
    course_reviews = course_reviews or {}
    if not table_records:
        return [], {"display": "block"}, "", "", [], "OK All"

    # Merge review status: session-level first, then course-level fallback
    for row in table_records:
        sid = str(row.get("SessionUniqueID", ""))
        session_status = reviews.get(sid, "")
        if session_status:
            row["ReviewStatus"] = session_status
            row["ReviewSource"] = "session"
        else:
            mrn = str(row.get("PatientMRN", ""))
            course = str(row.get("CourseName", ""))
            course_key = f"{mrn}|{course}"
            course_status = course_reviews.get(course_key, "")
            if course_status:
                row["ReviewStatus"] = course_status
                row["ReviewSource"] = "course"
            else:
                row["ReviewStatus"] = ""
                row["ReviewSource"] = ""

    # Table-local date filter
    if table_date and table_date != "all":
        today = pd.Timestamp.now().normalize()
        for row in table_records:
            try:
                row["_parsed_date"] = pd.Timestamp(row.get("TreatmentDate", ""))
            except Exception:
                row["_parsed_date"] = None

        cutoffs = {
            "yesterday": today - pd.Timedelta(days=1),
            "week": today - pd.Timedelta(days=today.weekday()),
            "month": today.replace(day=1),
            "ytd": pd.Timestamp(today.year, 1, 1),
        }
        cutoff = cutoffs.get(table_date)
        if cutoff:
            if table_date == "yesterday":
                table_records = [r for r in table_records if r.get("_parsed_date") is not None and r["_parsed_date"].normalize() == cutoff]
            else:
                table_records = [r for r in table_records if r.get("_parsed_date") is not None and r["_parsed_date"].normalize() >= cutoff]

    # Review status filter
    if review_filter == "unreviewed":
        table_records = [r for r in table_records if not r["ReviewStatus"]]
    elif review_filter == "reviewed":
        table_records = [r for r in table_records if r["ReviewStatus"]]

    # Audit result filter
    if result_filter == "fail":
        table_records = [r for r in table_records if r.get("AuditResult") == "FAIL"]
    elif result_filter == "pass":
        table_records = [r for r in table_records if r.get("AuditResult") == "PASS"]

    # Patient name + billed display
    for row in table_records:
        raw = str(row.get("PatientName", "") or row.get("PatientFullName", "") or "")
        if raw and "," in raw:
            parts = raw.split(",", 1)
            last = parts[0].strip().title()
            first_init = parts[1].strip()[0].upper() + "." if len(parts[1].strip()) > 0 else ""
            row["_patient_display"] = f"{last}, {first_init}"
        else:
            row["_patient_display"] = raw or "—"
        gate = row.get("FieldGating", "")
        if gate in (1, "1", 1.0, True):
            row["FieldGating"] = "Yes"
        elif gate in (0, "0", 0.0, False):
            row["FieldGating"] = "No"
        row["_billed_display"] = _strip_igrt(row.get("CPT_Billed", ""))

    # Sort by server key (date desc, stable)
    table_records = sorted(table_records, key=lambda r: r.get("_sort_key", 0))

    total = len(table_records)
    reviewed_count = sum(1 for v in reviews.values() if v)
    review_text = f"{reviewed_count} reviewed" if reviewed_count else ""
    info_text = f"{total:,} records"

    filtered_sids = [str(r.get("SessionUniqueID", "")) for r in table_records if not r.get("ReviewStatus")]
    unreviewed_count = len(filtered_sids)
    ok_all_label = f"OK All ({unreviewed_count:,})" if unreviewed_count else "OK All"

    empty_style = {"display": "none"} if table_records else {"display": "block"}

    return table_records, empty_style, review_text, info_text, filtered_sids, ok_all_label


# ---------------------------------------------------------------------------
# Chart callback — rebuilds on data, aggregation, or mode changes
# ---------------------------------------------------------------------------
@callback(
    Output("cpt-chart-trend", "figure"),
    Input("cpt-store-table-data", "data"),
    Input("cpt-store-reviews", "data"),
    Input("cpt-store-course-reviews", "data"),
    Input("cpt-chart-agg", "value"),
    Input("cpt-chart-mode", "value"),
)
def build_trend_chart(table_data, reviews, course_reviews, agg, mode):
    if not table_data:
        return empty_figure("No trend data")

    reviews = reviews or {}
    course_reviews = course_reviews or {}

    # Build per-session frame with reviews factored in
    df = pd.DataFrame(table_data)
    if "TreatmentDate" not in df.columns or "AuditResult" not in df.columns:
        return empty_figure("No trend data")

    df["date"] = pd.to_datetime(df["TreatmentDate"], errors="coerce")
    df = df.dropna(subset=["date"])

    # A session counts as "passed" if it originally passed, OR has been reviewed OK/Fixed
    def is_passing(row):
        if row.get("AuditResult") == "PASS":
            return True
        sid = str(row.get("SessionUniqueID", ""))
        if reviews.get(sid) in ("OK", "Fixed"):
            return True
        mrn = str(row.get("PatientMRN", ""))
        course = str(row.get("CourseName", ""))
        if course_reviews.get(f"{mrn}|{course}"):
            return True
        return False

    df["_passing"] = df.apply(is_passing, axis=1)

    # Aggregate
    if agg == "D":
        grouped = df.groupby(df["date"].dt.normalize()).agg(
            total=("_passing", "count"), passed=("_passing", "sum")
        )
        grouped["pass_rate"] = grouped["passed"] / grouped["total"] * 100
    else:
        period = "W" if agg == "W" else "M"
        df["period"] = df["date"].dt.to_period(period).dt.start_time
        grouped = df.groupby("period").agg(total=("_passing", "count"), passed=("_passing", "sum")).reset_index()
        grouped["pass_rate"] = grouped["passed"] / grouped["total"] * 100
        grouped = grouped.rename(columns={"period": "date"}).set_index("date").sort_index()

    fig = go.Figure()

    # Drop zero-total rows for bar mode so empty days (weekends) don't show
    if mode == "bar":
        grouped = grouped[grouped["total"] > 0]

    x = grouped.index
    y = grouped["pass_rate"]
    hover = "%{x}: %{y:.1f}%<extra></extra>"

    if mode == "bar":
        x_labels = x.strftime("%b") if agg == "M" else x.strftime("%b %-d")
        fig.add_trace(go.Bar(
            x=x_labels, y=y,
            marker_color=PRIMARY,
            hovertemplate=hover,
        ))
    elif mode == "area":
        fig.add_trace(go.Scatter(
            x=x, y=y,
            mode="lines",
            fill="tozeroy",
            line=dict(color=PRIMARY, width=2),
            fillcolor="rgba(124, 42, 131, 0.15)",
            hovertemplate=hover,
        ))
    else:  # line
        fig.add_trace(go.Scatter(
            x=x, y=y,
            mode="lines+markers",
            line=dict(color=PRIMARY, width=2),
            marker=dict(size=4),
            hovertemplate=hover,
        ))

    apply_default_layout(fig, height=180)
    layout_kw = dict(
        yaxis_title="Pass Rate %",
        yaxis_range=[max(0, y.min() - 5) if len(y) else 0, 100],
        margin=dict(l=48, r=16, t=12, b=16),
    )
    if mode == "bar":
        layout_kw["xaxis_type"] = "category"
    fig.update_layout(**layout_kw)
    return fig


def _strip_igrt(val):
    """Remove 77387 (IGRT) from comma-separated CPT_Billed, show remaining code."""
    s = str(val or "—")
    parts = [p.strip() for p in s.split(",") if p.strip() != "77387"]
    return parts[0] if parts else s
