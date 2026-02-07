"""Billing page — billing activity, CPT audit compliance, and payor mix analysis."""

import dash
import dash_mantine_components as dmc
import dash_ag_grid as dag
from dash import callback, Input, Output, State, dcc, clientside_callback, ClientsideFunction
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
import numpy as np
from datetime import timedelta

from config.settings import (
    PHYSICIANS, DEPARTMENTS, DEPARTMENT_COLORS, CHART_COLORWAY, PRIMARY,
    DEFAULT_LAYOUT, FONT_FAMILY, SEMANTIC_COLORS, NEUTRAL,
    DEFAULT_COLUMN_DEFS, DEFAULT_GRID_OPTIONS,
)
from components.filter_bar import filter_bar, date_presets, department_chips, physician_select, date_range_picker
from components.kpi_card import kpi_card
from components.chart_settings import chart_settings_popover
from utils.charts import apply_default_layout, empty_figure, dept_color, color_for_index

dash.register_page(__name__, path="/billing", name="Billing", order=7)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _preset_start(last_date, preset, earliest_date):
    """Calculate start date from a date preset, relative to data."""
    if preset == "ytd":
        return pd.Timestamp(last_date.year, 1, 1)
    lookbacks = {"12mo": 365, "all": None}
    days = lookbacks.get(preset)
    if days is None:
        return earliest_date
    return last_date - timedelta(days=days)


def _filter_by_date(df, date_col, preset, daterange):
    """Apply date filtering using preset or explicit range.

    Uses data-relative dates (not pd.Timestamp.now()).
    """
    if date_col not in df.columns or df.empty:
        return df

    last_date = df[date_col].dt.normalize().max()
    earliest_date = df[date_col].dt.normalize().min()

    # Explicit date range takes precedence
    if daterange and len(daterange) == 2 and daterange[0] and daterange[1]:
        start = pd.Timestamp(daterange[0])
        end = pd.Timestamp(daterange[1])
        return df[(df[date_col] >= start) & (df[date_col] <= end)]

    start = _preset_start(last_date, preset or "12mo", earliest_date)
    return df[(df[date_col] >= start) & (df[date_col] <= last_date)]


def _filter_departments(df, departments):
    """Filter by departments if provided."""
    if departments and "Department" in df.columns:
        return df[df["Department"].isin(departments)]
    return df


def _filter_physician(df, physicians):
    """Filter by physician if provided. Checks SupervisingPhysician and AttendingPhysician."""
    if not physicians:
        return df
    mask = pd.Series(False, index=df.index)
    for col in ["SupervisingPhysician", "AttendingPhysician"]:
        if col in df.columns:
            mask = mask | df[col].isin(physicians)
    return df[mask] if mask.any() else df


def _top_n_with_other(series, n=10):
    """Return top N values from a Series, grouping the rest as 'Other'."""
    vc = series.value_counts()
    top = vc.head(n)
    other_count = vc.iloc[n:].sum() if len(vc) > n else 0
    if other_count > 0:
        top = pd.concat([top, pd.Series({"Other": other_count})])
    return top


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
                dmc.Title("Billing", order=2, className="page-title"),
                filter_bar("billing", children=[
                    date_presets("billing"),
                    date_range_picker("billing"),
                    department_chips("billing"),
                    physician_select("billing"),
                    dmc.SegmentedControl(
                        id="billing-filter-view",
                        data=[
                            {"value": "activity", "label": "Billing Activity"},
                            {"value": "audit", "label": "CPT Audit"},
                            {"value": "payor", "label": "Payor Mix"},
                        ],
                        value="activity",
                        size="sm",
                    ),
                ]),
            ],
        ),

        # KPI row
        dmc.Grid(
            id="billing-kpi-row",
            gutter=16,
            children=[
                dmc.GridCol(id="billing-kpi-total-events", span={"base": 12, "sm": 6, "md": 2.4}),
                dmc.GridCol(id="billing-kpi-unique-cpts", span={"base": 12, "sm": 6, "md": 2.4}),
                dmc.GridCol(id="billing-kpi-audit-pass", span={"base": 12, "sm": 6, "md": 2.4}),
                dmc.GridCol(id="billing-kpi-audit-fail", span={"base": 12, "sm": 6, "md": 2.4}),
                dmc.GridCol(id="billing-kpi-top-cpt", span={"base": 12, "sm": 6, "md": 2.4}),
            ],
        ),

        # Dynamic content area (changes based on view toggle)
        dmc.Box(id="billing-content"),

        # Interval for periodic refresh
        dcc.Interval(id="billing-interval", interval=300_000, n_intervals=0),
    ],
)


# ---------------------------------------------------------------------------
# Main Callback
# ---------------------------------------------------------------------------

@callback(
    Output("billing-kpi-row", "children"),
    Output("billing-content", "children"),
    Input("billing-interval", "n_intervals"),
    Input("billing-filter-date-preset", "value"),
    Input("billing-filter-daterange", "value"),
    Input("billing-filter-department", "value"),
    Input("billing-filter-physician", "value"),
    Input("billing-filter-view", "value"),
)
def update_billing(_n, date_preset, daterange, departments, physicians, view):
    """Master callback: compute KPIs and build view-specific content."""
    from data.loader import load_billing, load_cpt_audit, load_patients, load_clinic_visits, load_courses

    # Fallback KPI row
    na_kpi = kpi_card("--", "N/A")
    kpi_children = [
        dmc.GridCol(na_kpi, span={"base": 12, "sm": 6, "md": 2.4}),
    ] * 5

    empty_content = dmc.Paper(
        dmc.Text("No billing data for the selected filters.", c=NEUTRAL["text_muted"], ta="center", py="xl"),
        p="xl", radius="md", shadow="xs", withBorder=True,
    )

    # ------------------------------------------------------------------
    # Load data
    # ------------------------------------------------------------------
    try:
        billing = load_billing()
    except Exception:
        billing = pd.DataFrame()

    try:
        audit = load_cpt_audit()
    except Exception:
        audit = pd.DataFrame()

    # ------------------------------------------------------------------
    # Apply filters to billing data
    # ------------------------------------------------------------------
    bf = billing.copy() if not billing.empty else pd.DataFrame()
    if not bf.empty:
        bf = _filter_by_date(bf, "DateOfService", date_preset, daterange)
        bf = _filter_departments(bf, departments)
        bf = _filter_physician(bf, physicians)

    # Apply filters to audit data
    af = audit.copy() if not audit.empty else pd.DataFrame()
    if not af.empty:
        af = _filter_by_date(af, "TreatmentDate", date_preset, daterange)
        af = _filter_departments(af, departments)

    # ------------------------------------------------------------------
    # KPIs (always visible regardless of view)
    # ------------------------------------------------------------------
    # 1. Total Billing Events
    total_events = len(bf) if not bf.empty else 0
    kpi_total = kpi_card(
        "Total Billing Events",
        f"{total_events:,}",
        accent_color=PRIMARY,
    )

    # 2. Unique CPT Codes
    unique_cpts = bf["ProcedureCode"].nunique() if not bf.empty and "ProcedureCode" in bf.columns else 0
    kpi_cpts = kpi_card(
        "Unique CPT Codes",
        f"{unique_cpts:,}",
        accent_color=CHART_COLORWAY[1],
    )

    # 3. Audit Pass Rate
    if not af.empty and "AuditResult" in af.columns:
        total_audited = len(af)
        pass_count = (af["AuditResult"] == "PASS").sum()
        pass_rate = (pass_count / total_audited * 100) if total_audited > 0 else 0
        pass_color = SEMANTIC_COLORS["success"] if pass_rate >= 95 else SEMANTIC_COLORS["warning"]
        kpi_pass = kpi_card(
            "Audit Pass Rate",
            f"{pass_rate:.1f}%",
            accent_color=pass_color,
        )
    else:
        kpi_pass = kpi_card("Audit Pass Rate", "N/A")

    # 4. Audit Failures
    if not af.empty and "AuditResult" in af.columns:
        fail_count = (af["AuditResult"] == "FAIL").sum()
        fail_color = SEMANTIC_COLORS["error"] if fail_count > 0 else NEUTRAL["text_muted"]
        kpi_fail = kpi_card(
            "Audit Failures",
            f"{fail_count:,}",
            accent_color=fail_color,
        )
    else:
        kpi_fail = kpi_card("Audit Failures", "N/A")

    # 5. Top CPT Code
    if not bf.empty and "ProcedureCode" in bf.columns:
        top_cpt = bf["ProcedureCode"].value_counts().index[0] if len(bf) > 0 else "--"
        # Get description if available
        top_desc = ""
        if "ProcedureCodeDescription" in bf.columns:
            match = bf.loc[bf["ProcedureCode"] == top_cpt, "ProcedureCodeDescription"]
            if not match.empty:
                top_desc = str(match.iloc[0])
                if len(top_desc) > 30:
                    top_desc = top_desc[:27] + "..."
        kpi_top = kpi_card(
            "Top CPT Code",
            str(top_cpt),
            value_detail=top_desc if top_desc else None,
            accent_color=CHART_COLORWAY[4],
        )
    else:
        kpi_top = kpi_card("Top CPT Code", "N/A")

    kpi_children = [
        dmc.GridCol(kpi_total, span={"base": 12, "sm": 6, "md": 2.4}),
        dmc.GridCol(kpi_cpts, span={"base": 12, "sm": 6, "md": 2.4}),
        dmc.GridCol(kpi_pass, span={"base": 12, "sm": 6, "md": 2.4}),
        dmc.GridCol(kpi_fail, span={"base": 12, "sm": 6, "md": 2.4}),
        dmc.GridCol(kpi_top, span={"base": 12, "sm": 6, "md": 2.4}),
    ]

    # ------------------------------------------------------------------
    # Build view-specific content
    # ------------------------------------------------------------------
    if view == "activity":
        content = _build_activity_view(bf)
    elif view == "audit":
        content = _build_audit_view(af)
    elif view == "payor":
        try:
            patients = load_patients()
        except Exception:
            patients = pd.DataFrame()
        content = _build_payor_view(bf, patients, departments)
    else:
        content = empty_content

    return kpi_children, content


# ---------------------------------------------------------------------------
# Billing Activity View
# ---------------------------------------------------------------------------

def _build_activity_view(df):
    """Build Billing Activity view: CPT distribution bar + volume trend."""
    if df.empty:
        return dmc.Paper(
            dmc.Text("No billing data for selected filters.", c=NEUTRAL["text_muted"], ta="center", py="xl"),
            p="xl", radius="md", shadow="xs", withBorder=True,
        )

    return dmc.Grid(
        gutter=16,
        children=[
            # Left: CPT Code Distribution (horizontal bar)
            dmc.GridCol(
                span={"base": 12, "md": 6},
                children=dmc.Paper(
                    children=[
                        dmc.Text(
                            "CPT Code Distribution (Top 15)",
                            size="sm", fw=500, c=NEUTRAL["text_secondary"], mb="sm",
                        ),
                        dcc.Graph(
                            id="billing-chart-cpt-dist",
                            figure=_fig_cpt_distribution(df),
                            config={"displayModeBar": False},
                        ),
                    ],
                    p="sm", radius="md", shadow="xs", withBorder=True,
                ),
            ),
            # Right: Billing Volume Trend
            dmc.GridCol(
                span={"base": 12, "md": 6},
                children=dmc.Paper(
                    children=[
                        dmc.Text(
                            "Billing Volume Trend",
                            size="sm", fw=500, c=NEUTRAL["text_secondary"], mb="sm",
                        ),
                        dcc.Graph(
                            id="billing-chart-volume-trend",
                            figure=_fig_volume_trend(df),
                            config={"displayModeBar": False},
                        ),
                    ],
                    p="sm", radius="md", shadow="xs", withBorder=True,
                ),
            ),
        ],
    )


def _fig_cpt_distribution(df):
    """Horizontal bar chart of top 15 CPT codes, colored by CodeType."""
    if "ProcedureCode" not in df.columns:
        return empty_figure("No procedure code data")

    # Build label from code + description
    df = df.copy()
    if "ProcedureCodeDescription" in df.columns:
        df["_label"] = df["ProcedureCode"].astype(str) + " - " + df["ProcedureCodeDescription"].fillna("").astype(str)
        # Truncate long descriptions
        df["_label"] = df["_label"].str[:50]
    else:
        df["_label"] = df["ProcedureCode"].astype(str)

    # Get top 15 codes
    top_codes = df["ProcedureCode"].value_counts().head(15).index.tolist()
    sub = df[df["ProcedureCode"].isin(top_codes)]

    fig = go.Figure()

    # Color by CodeType if available
    if "CodeType" in sub.columns:
        code_types = sub["CodeType"].dropna().unique()
        type_colors = {
            "Global": CHART_COLORWAY[0],
            "Technical": CHART_COLORWAY[1],
            "Professional": CHART_COLORWAY[2],
        }
        # Determine consistent y-axis ordering across all traces
        overall_order = sub.groupby("_label").size().sort_values(ascending=True).index.tolist()
        for ct in sorted(code_types):
            ct_data = sub[sub["CodeType"] == ct]
            counts = ct_data.groupby("_label").size().reindex(overall_order).fillna(0)
            fig.add_trace(go.Bar(
                y=counts.index,
                x=counts.values,
                name=str(ct),
                orientation="h",
                marker_color=type_colors.get(str(ct), color_for_index(len(type_colors))),
            ))
        fig.update_layout(barmode="stack")
    else:
        counts = sub.groupby("_label").size().sort_values(ascending=True)
        fig.add_trace(go.Bar(
            y=counts.index,
            x=counts.values,
            orientation="h",
            marker_color=PRIMARY,
        ))

    apply_default_layout(fig, height=380)
    fig.update_layout(
        xaxis_title="Count",
        margin=dict(l=200, r=16, t=8, b=40),
    )
    return fig


def _fig_volume_trend(df):
    """Line/area chart of billing volume by month, series by CodeType."""
    if "DateOfService" not in df.columns:
        return empty_figure("No date data")

    df = df.copy()
    df["Month"] = df["DateOfService"].dt.to_period("M").dt.to_timestamp()

    fig = go.Figure()

    if "CodeType" in df.columns:
        code_types = sorted(df["CodeType"].dropna().unique())
        type_colors = {
            "Global": CHART_COLORWAY[0],
            "Technical": CHART_COLORWAY[1],
            "Professional": CHART_COLORWAY[2],
        }
        for ct in code_types:
            ct_data = df[df["CodeType"] == ct]
            monthly = ct_data.groupby("Month").size().sort_index()
            fig.add_trace(go.Scatter(
                x=monthly.index,
                y=monthly.values,
                name=str(ct),
                mode="lines",
                fill="tozeroy",
                line=dict(color=type_colors.get(str(ct), color_for_index(len(type_colors))), width=2),
            ))
    else:
        monthly = df.groupby("Month").size().sort_index()
        fig.add_trace(go.Scatter(
            x=monthly.index,
            y=monthly.values,
            mode="lines",
            fill="tozeroy",
            line=dict(color=PRIMARY, width=2),
        ))

    apply_default_layout(fig, height=380)
    fig.update_layout(
        yaxis_title="Billing Events",
        margin=dict(l=48, r=16, t=8, b=40),
    )
    return fig


# ---------------------------------------------------------------------------
# CPT Audit View
# ---------------------------------------------------------------------------

def _build_audit_view(df):
    """Build CPT Audit view: results by machine, by technique, and failure detail table."""
    if df.empty:
        return dmc.Paper(
            dmc.Text("No CPT audit data for selected filters.", c=NEUTRAL["text_muted"], ta="center", py="xl"),
            p="xl", radius="md", shadow="xs", withBorder=True,
        )

    children = [
        # Row 1: By Machine + By Technique
        dmc.Grid(
            gutter=16,
            children=[
                dmc.GridCol(
                    span={"base": 12, "md": 6},
                    children=dmc.Paper(
                        children=[
                            dmc.Text(
                                "Audit Results by Machine",
                                size="sm", fw=500, c=NEUTRAL["text_secondary"], mb="sm",
                            ),
                            dcc.Graph(
                                id="billing-chart-audit-machine",
                                figure=_fig_audit_by_machine(df),
                                config={"displayModeBar": False},
                            ),
                        ],
                        p="sm", radius="md", shadow="xs", withBorder=True,
                    ),
                ),
                dmc.GridCol(
                    span={"base": 12, "md": 6},
                    children=dmc.Paper(
                        children=[
                            dmc.Text(
                                "Audit Results by Technique",
                                size="sm", fw=500, c=NEUTRAL["text_secondary"], mb="sm",
                            ),
                            dcc.Graph(
                                id="billing-chart-audit-technique",
                                figure=_fig_audit_by_technique(df),
                                config={"displayModeBar": False},
                            ),
                        ],
                        p="sm", radius="md", shadow="xs", withBorder=True,
                    ),
                ),
            ],
        ),
    ]

    # Row 2: Failure detail table (only if there are failures)
    fail_df = df[df["AuditResult"] == "FAIL"] if "AuditResult" in df.columns else pd.DataFrame()
    if not fail_df.empty:
        children.append(
            dmc.Paper(
                children=[
                    dmc.Text(
                        "Audit Failure Detail",
                        size="sm", fw=500, c=NEUTRAL["text_secondary"], mb="sm",
                    ),
                    _build_audit_failure_table(fail_df),
                ],
                p="sm", radius="md", shadow="xs", withBorder=True,
            )
        )

    return dmc.Stack(gap=16, children=children)


def _fig_audit_by_machine(df):
    """Grouped bar chart of PASS vs FAIL by Machine."""
    if "Machine" not in df.columns or "AuditResult" not in df.columns:
        return empty_figure("No machine data available")

    pivot = df.groupby(["Machine", "AuditResult"]).size().unstack(fill_value=0)

    fig = go.Figure()
    result_colors = {
        "PASS": SEMANTIC_COLORS["success"],
        "FAIL": SEMANTIC_COLORS["error"],
    }

    for result in ["PASS", "FAIL"]:
        if result in pivot.columns:
            fig.add_trace(go.Bar(
                x=pivot.index,
                y=pivot[result],
                name=result,
                marker_color=result_colors.get(result, NEUTRAL["text_muted"]),
            ))

    apply_default_layout(fig, barmode="group", height=380)
    fig.update_layout(
        yaxis_title="Sessions",
        margin=dict(l=48, r=16, t=8, b=40),
    )
    return fig


def _fig_audit_by_technique(df):
    """Grouped bar chart of PASS vs FAIL by RxTechnique_Course."""
    col = "RxTechnique_Course"
    if col not in df.columns or "AuditResult" not in df.columns:
        return empty_figure("No technique data available")

    pivot = df.groupby([col, "AuditResult"]).size().unstack(fill_value=0)

    fig = go.Figure()
    result_colors = {
        "PASS": SEMANTIC_COLORS["success"],
        "FAIL": SEMANTIC_COLORS["error"],
    }

    for result in ["PASS", "FAIL"]:
        if result in pivot.columns:
            fig.add_trace(go.Bar(
                x=pivot.index,
                y=pivot[result],
                name=result,
                marker_color=result_colors.get(result, NEUTRAL["text_muted"]),
            ))

    apply_default_layout(fig, barmode="group", height=380)
    fig.update_layout(
        yaxis_title="Sessions",
        margin=dict(l=48, r=16, t=8, b=40),
    )
    return fig


def _build_audit_failure_table(df):
    """AG Grid table of audit FAIL rows."""
    display_cols = [
        {"field": "TreatmentDate", "headerName": "Treatment Date", "flex": 1},
        {"field": "PatientName", "headerName": "Patient", "flex": 1.5},
        {"field": "Machine", "headerName": "Machine", "flex": 1},
        {"field": "RxTechnique_Course", "headerName": "Technique", "flex": 1},
        {"field": "CPT_Correct", "headerName": "Correct CPT", "flex": 1},
        {"field": "CPT_Billed", "headerName": "Billed CPT", "flex": 1},
        {"field": "AuditResult", "headerName": "Result", "flex": 0.7,
         "cellStyle": {
             "styleConditions": [
                 {"condition": "params.value === 'FAIL'",
                  "style": {"color": SEMANTIC_COLORS["error"], "fontWeight": "600"}},
             ],
         }},
    ]

    # Only include columns that exist in the data
    existing_cols = [c for c in display_cols if c["field"] in df.columns]

    table_df = df.copy()
    # Format dates for display
    if "TreatmentDate" in table_df.columns and pd.api.types.is_datetime64_any_dtype(table_df["TreatmentDate"]):
        table_df["TreatmentDate"] = table_df["TreatmentDate"].dt.strftime("%m/%d/%Y")
    table_df = table_df.fillna("--")

    return dag.AgGrid(
        id="billing-audit-detail-table",
        rowData=table_df.to_dict("records"),
        columnDefs=existing_cols,
        defaultColDef=DEFAULT_COLUMN_DEFS,
        dashGridOptions={**DEFAULT_GRID_OPTIONS, "paginationPageSize": 25},
        style={"height": "500px"},
        className="ag-theme-alpine",
    )


# ---------------------------------------------------------------------------
# Payor Mix View
# ---------------------------------------------------------------------------

def _build_payor_view(billing_df, patients_df, departments):
    """Build Payor Mix view: per-patient donut, per-event bar, payor trend."""
    if billing_df.empty:
        return dmc.Paper(
            dmc.Text("No billing data for selected filters.", c=NEUTRAL["text_muted"], ta="center", py="xl"),
            p="xl", radius="md", shadow="xs", withBorder=True,
        )

    # Join billing with patients to get PrimaryInsurance
    if not patients_df.empty and "PatientId" in billing_df.columns and "PatientId" in patients_df.columns:
        df_with_payor = billing_df.merge(
            patients_df[["PatientId", "PrimaryInsurance"]].drop_duplicates("PatientId"),
            on="PatientId",
            how="left",
        )
    else:
        df_with_payor = billing_df.copy()
        if "PrimaryInsurance" not in df_with_payor.columns:
            df_with_payor["PrimaryInsurance"] = "Unknown"

    # Fill missing insurance
    df_with_payor["PrimaryInsurance"] = df_with_payor["PrimaryInsurance"].fillna("Unknown")

    # Filter patients by department if applicable
    if departments and not patients_df.empty and "Department" in patients_df.columns:
        dept_patients = patients_df[patients_df["Department"].isin(departments)]
    elif not patients_df.empty:
        dept_patients = patients_df
    else:
        dept_patients = pd.DataFrame()

    # Prepare patient-level insurance data for the donut
    if not dept_patients.empty and "PrimaryInsurance" in dept_patients.columns:
        patient_insurance = dept_patients
    elif not dept_patients.empty and not patients_df.empty and "PrimaryInsurance" in patients_df.columns:
        patient_insurance = dept_patients.merge(
            patients_df[["PatientId", "PrimaryInsurance"]].drop_duplicates("PatientId"),
            on="PatientId",
            how="left",
        )
        patient_insurance["PrimaryInsurance"] = patient_insurance["PrimaryInsurance"].fillna("Unknown")
    else:
        patient_insurance = pd.DataFrame()

    return dmc.Stack(
        gap=16,
        children=[
            # Row 1: Per-Patient donut + Per-Event horizontal bar
            dmc.Grid(
                gutter=16,
                children=[
                    dmc.GridCol(
                        span={"base": 12, "md": 6},
                        children=dmc.Paper(
                            children=[
                                dmc.Text(
                                    "Insurance Distribution (Per Patient)",
                                    size="sm", fw=500, c=NEUTRAL["text_secondary"], mb="sm",
                                ),
                                dcc.Graph(
                                    id="billing-chart-payor-patient",
                                    figure=_fig_payor_donut(patient_insurance),
                                    config={"displayModeBar": False},
                                ),
                            ],
                            p="sm", radius="md", shadow="xs", withBorder=True,
                        ),
                    ),
                    dmc.GridCol(
                        span={"base": 12, "md": 6},
                        children=dmc.Paper(
                            children=[
                                dmc.Text(
                                    "Insurance Distribution (Per Billing Event)",
                                    size="sm", fw=500, c=NEUTRAL["text_secondary"], mb="sm",
                                ),
                                dcc.Graph(
                                    id="billing-chart-payor-event",
                                    figure=_fig_payor_bar(df_with_payor),
                                    config={"displayModeBar": False},
                                ),
                            ],
                            p="sm", radius="md", shadow="xs", withBorder=True,
                        ),
                    ),
                ],
            ),
            # Row 2: Payor trend (full width)
            dmc.Paper(
                children=[
                    dmc.Text(
                        "Payor Mix Trend",
                        size="sm", fw=500, c=NEUTRAL["text_secondary"], mb="sm",
                    ),
                    dcc.Graph(
                        id="billing-chart-payor-trend",
                        figure=_fig_payor_trend(df_with_payor),
                        config={"displayModeBar": False},
                    ),
                ],
                p="sm", radius="md", shadow="xs", withBorder=True,
            ),
        ],
    )


def _fig_payor_donut(df):
    """Donut chart of insurance distribution per unique patient (top 10 + Other)."""
    if df.empty or "PrimaryInsurance" not in df.columns:
        return empty_figure("No patient insurance data")

    # Get unique patients by insurance
    if "PatientId" in df.columns:
        patient_ins = df.drop_duplicates("PatientId")["PrimaryInsurance"]
    else:
        patient_ins = df["PrimaryInsurance"]

    dist = _top_n_with_other(patient_ins, n=10)

    colors = [color_for_index(i) for i in range(len(dist))]

    fig = go.Figure(go.Pie(
        labels=dist.index,
        values=dist.values,
        hole=0.45,
        marker=dict(colors=colors),
        textinfo="label+percent",
        textposition="outside",
        hovertemplate="%{label}: %{value:,} patients (%{percent})<extra></extra>",
    ))

    apply_default_layout(fig, height=380)
    fig.update_layout(
        showlegend=False,
        margin=dict(l=16, r=16, t=8, b=16),
    )
    return fig


def _fig_payor_bar(df):
    """Horizontal bar chart of insurance distribution per billing event."""
    if df.empty or "PrimaryInsurance" not in df.columns:
        return empty_figure("No payor data")

    dist = _top_n_with_other(df["PrimaryInsurance"], n=10)
    dist = dist.sort_values(ascending=True)

    colors = [color_for_index(i) for i in range(len(dist))]

    fig = go.Figure(go.Bar(
        y=dist.index,
        x=dist.values,
        orientation="h",
        marker_color=colors,
        hovertemplate="%{y}: %{x:,} events<extra></extra>",
    ))

    apply_default_layout(fig, height=380)
    fig.update_layout(
        xaxis_title="Billing Events",
        margin=dict(l=160, r=16, t=8, b=40),
    )
    return fig


def _fig_payor_trend(df):
    """Stacked area chart by month: top 5 insurers + Other."""
    if df.empty or "PrimaryInsurance" not in df.columns or "DateOfService" not in df.columns:
        return empty_figure("No payor trend data")

    df = df.copy()
    df["Month"] = df["DateOfService"].dt.to_period("M").dt.to_timestamp()

    # Identify top 5 insurers overall
    top5 = df["PrimaryInsurance"].value_counts().head(5).index.tolist()
    df["_payor_group"] = df["PrimaryInsurance"].where(df["PrimaryInsurance"].isin(top5), "Other")

    # Pivot by month and payor group
    monthly = df.groupby(["Month", "_payor_group"]).size().unstack(fill_value=0)

    # Ensure 'Other' is last, top payors in descending order
    ordered_cols = [c for c in top5 if c in monthly.columns]
    if "Other" in monthly.columns:
        ordered_cols.append("Other")
    monthly = monthly.reindex(columns=ordered_cols, fill_value=0)

    fig = go.Figure()
    for i, col in enumerate(monthly.columns):
        fig.add_trace(go.Scatter(
            x=monthly.index,
            y=monthly[col],
            name=str(col),
            mode="lines",
            stackgroup="one",
            line=dict(color=color_for_index(i), width=1),
            hovertemplate=f"{col}: " + "%{y:,}<extra></extra>",
        ))

    apply_default_layout(fig, height=380)
    fig.update_layout(
        yaxis_title="Billing Events",
        margin=dict(l=48, r=16, t=8, b=40),
    )
    return fig
