"""Referrals page — referring physician patterns, specialties, volume trends, and institution analysis."""

import dash
import dash_mantine_components as dmc
import dash_ag_grid as dag
from dash import callback, Input, Output, dcc
import plotly.graph_objects as go
import pandas as pd
import numpy as np
from datetime import timedelta

from config.settings import (
    PHYSICIANS, DEPARTMENTS, DEPARTMENT_COLORS, CHART_COLORWAY, PRIMARY,
    DEFAULT_LAYOUT, FONT_FAMILY, SEMANTIC_COLORS, NEUTRAL,
    DEFAULT_COLUMN_DEFS, DEFAULT_GRID_OPTIONS,
)
from components.filter_bar import filter_bar, date_presets, department_chips
from components.kpi_card import kpi_card
from utils.charts import apply_default_layout, empty_figure, dept_color, color_for_index

dash.register_page(__name__, path="/referrals", name="Referrals", order=12)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _preset_start(last_date, preset):
    """Return the start date for a given date preset, relative to data."""
    if preset == "ytd":
        return pd.Timestamp(last_date.year, 1, 1)
    elif preset == "12mo":
        return last_date - timedelta(days=365)
    else:  # "all"
        return pd.Timestamp("1970-01-01")


def _prior_range(last_date, preset):
    """Return (start, end) for the comparison period."""
    if preset == "ytd":
        try:
            pe = pd.Timestamp(last_date.year - 1, last_date.month, last_date.day)
        except ValueError:
            pe = pd.Timestamp(last_date.year - 1, last_date.month, 28)
        return pd.Timestamp(last_date.year - 1, 1, 1), pe
    elif preset == "12mo":
        return last_date - timedelta(days=730), last_date - timedelta(days=366)
    else:  # "all" -- no comparison
        return None, None


def _trend(curr, prior, invert=False):
    """Return (pct_text, direction, prior_value) for trend display."""
    if prior is None or prior == 0:
        return None, None, None
    pct = (curr - prior) / prior * 100
    direction = ("down" if pct > 0 else "up") if invert else ("up" if pct > 0 else "down")
    return f"{abs(pct):.0f}%", direction, prior


def _resolve_physician_name(row):
    """Get the best available referring physician name from merged data."""
    for col in ("DoctorFullName", "ReferringPhysician"):
        val = row.get(col)
        if pd.notna(val) and str(val).strip():
            return str(val).strip()
    return "Unknown"


def _resolve_specialty(row):
    """Get the best available specialty from merged data."""
    for col in ("DoctorSpecialty", "ReferringPhysicianSpecialty"):
        val = row.get(col)
        if pd.notna(val) and str(val).strip():
            return str(val).strip()
    return "Unknown"


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
                dmc.Title("Referrals", order=2, className="page-title"),
                dmc.Paper(
                    children=[
                        dmc.Group(
                            children=[
                                date_presets("referrals"),
                                department_chips("referrals"),
                            ],
                            gap="lg",
                            wrap="wrap",
                        ),
                    ],
                    p="sm", px="md", radius="md", shadow="xs", withBorder=True,
                ),
            ],
        ),

        # KPI row -- 5 cards
        dmc.Grid(
            id="referrals-kpi-row",
            gutter=16,
            children=[
                dmc.GridCol(span={"base": 12, "sm": 6, "md": 2.4}),
                dmc.GridCol(span={"base": 12, "sm": 6, "md": 2.4}),
                dmc.GridCol(span={"base": 12, "sm": 6, "md": 2.4}),
                dmc.GridCol(span={"base": 12, "sm": 6, "md": 2.4}),
                dmc.GridCol(span={"base": 12, "sm": 6, "md": 2.4}),
            ],
        ),

        # Charts container -- dynamically populated by callback
        dmc.Stack(id="referrals-charts", gap=16),

        # Detail table container
        dmc.Box(id="referrals-table-container"),

        # Interval for periodic refresh
        dcc.Interval(id="referrals-interval", interval=300_000, n_intervals=0),
    ],
)


# ---------------------------------------------------------------------------
# Chart Builders
# ---------------------------------------------------------------------------

def _build_top_physicians_chart(df, n=20):
    """Horizontal bar chart of top N referring physicians by consult count."""
    if df.empty:
        return empty_figure("No referral data available")

    df = df.copy()
    df["_physician"] = df.apply(_resolve_physician_name, axis=1)
    df["_specialty"] = df.apply(_resolve_specialty, axis=1)

    # Count consults per physician
    counts = df.groupby(["_physician", "_specialty"]).size().reset_index(name="count")
    counts = counts.sort_values("count", ascending=False).head(n)
    counts = counts.sort_values("count", ascending=True)  # Reverse for horizontal bar

    if counts.empty:
        return empty_figure("No referral data available")

    # Assign colors by specialty
    specialties = counts["_specialty"].unique().tolist()
    spec_colors = {s: color_for_index(i) for i, s in enumerate(specialties)}

    fig = go.Figure()

    # Group by specialty for legend
    for spec in specialties:
        spec_data = counts[counts["_specialty"] == spec]
        fig.add_trace(go.Bar(
            y=spec_data["_physician"],
            x=spec_data["count"],
            orientation="h",
            name=spec if len(spec) <= 30 else spec[:27] + "...",
            marker_color=spec_colors[spec],
            hovertemplate="%{y}<br>%{x} consults<br>" + spec + "<extra></extra>",
        ))

    fig = apply_default_layout(fig,
        height=380,
        barmode="stack",
        margin=dict(l=160, r=16, t=8, b=32),
        legend=dict(
            orientation="h", yanchor="bottom", y=1.02,
            xanchor="left", x=0, font=dict(size=10),
        ),
        yaxis=dict(
            showgrid=False, linecolor="#E0E0E0", gridcolor="#F0F0F0",
            tickfont=dict(size=11),
        ),
        xaxis=dict(
            showgrid=True, gridcolor="#F0F0F0", linecolor="#E0E0E0",
            title="Consults",
        ),
    )
    return fig


def _build_specialty_donut(df):
    """Donut chart of consult count by specialty (top 10 + Other)."""
    if df.empty:
        return empty_figure("No referral data available")

    df = df.copy()
    df["_specialty"] = df.apply(_resolve_specialty, axis=1)

    counts = df.groupby("_specialty").size().reset_index(name="count")
    counts = counts.sort_values("count", ascending=False)

    # Top 10 + Other
    if len(counts) > 10:
        top10 = counts.head(10)
        other_count = counts.iloc[10:]["count"].sum()
        other_row = pd.DataFrame([{"_specialty": "Other", "count": other_count}])
        counts = pd.concat([top10, other_row], ignore_index=True)

    colors = [color_for_index(i) for i in range(len(counts))]

    fig = go.Figure(data=[go.Pie(
        labels=counts["_specialty"],
        values=counts["count"],
        hole=0.45,
        marker=dict(colors=colors),
        textinfo="percent+label",
        textposition="outside",
        textfont=dict(size=10),
        hovertemplate="%{label}<br>%{value} consults (%{percent})<extra></extra>",
        sort=False,
    )])

    fig = apply_default_layout(fig,
        height=380,
        margin=dict(l=16, r=16, t=16, b=16),
        showlegend=False,
    )
    return fig


def _build_volume_trend(df):
    """Line chart of referral volume by month."""
    if df.empty or "ScheduledDateTime" not in df.columns:
        return empty_figure("No referral data available")

    df = df.copy()
    df["_month"] = df["ScheduledDateTime"].dt.to_period("M").dt.to_timestamp()

    monthly = df.groupby("_month").size().reset_index(name="count")
    monthly = monthly.sort_values("_month")

    if monthly.empty:
        return empty_figure("No referral data available")

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=monthly["_month"],
        y=monthly["count"],
        mode="lines+markers",
        line=dict(color=PRIMARY, width=2),
        marker=dict(size=5, color=PRIMARY),
        hovertemplate="%{x|%b %Y}: %{y} consults<extra></extra>",
        name="Referrals",
    ))

    # Add trend line (simple linear regression)
    if len(monthly) >= 3:
        x_num = np.arange(len(monthly))
        z = np.polyfit(x_num, monthly["count"].values, 1)
        p = np.poly1d(z)
        fig.add_trace(go.Scatter(
            x=monthly["_month"],
            y=p(x_num),
            mode="lines",
            line=dict(color=NEUTRAL["text_muted"], width=1.5, dash="dash"),
            hoverinfo="skip",
            name="Trend",
        ))

    fig = apply_default_layout(fig,
        height=380,
        margin=dict(l=48, r=16, t=8, b=48),
        xaxis=dict(
            showgrid=False, linecolor="#E0E0E0", gridcolor="#F0F0F0",
            dtick="M3", tickformat="%b %Y",
        ),
        yaxis=dict(
            showgrid=True, gridcolor="#F0F0F0", linecolor="#E0E0E0",
            title="Consults",
        ),
        legend=dict(
            orientation="h", yanchor="bottom", y=1.02,
            xanchor="left", x=0, font=dict(size=11),
        ),
    )
    return fig


def _build_institution_chart(df, n=15):
    """Horizontal bar chart of top N institutions by consult count."""
    if df.empty:
        return empty_figure("No referral data available")

    inst_col = "DoctorInstitution"
    if inst_col not in df.columns:
        return empty_figure("Institution data not available")

    df = df.copy()
    df["_institution"] = df[inst_col].fillna("Unknown").astype(str).str.strip()
    df.loc[df["_institution"] == "", "_institution"] = "Unknown"

    counts = df.groupby("_institution").size().reset_index(name="count")
    counts = counts.sort_values("count", ascending=False).head(n)
    counts = counts.sort_values("count", ascending=True)  # Reverse for horizontal bar

    if counts.empty:
        return empty_figure("No institution data available")

    # Truncate long names for display
    counts["_display"] = counts["_institution"].apply(
        lambda x: x if len(x) <= 35 else x[:32] + "..."
    )

    fig = go.Figure()
    fig.add_trace(go.Bar(
        y=counts["_display"],
        x=counts["count"],
        orientation="h",
        marker_color=CHART_COLORWAY[1],
        hovertemplate="%{y}<br>%{x} consults<extra></extra>",
        showlegend=False,
    ))

    fig = apply_default_layout(fig,
        height=380,
        margin=dict(l=200, r=16, t=8, b=32),
        yaxis=dict(
            showgrid=False, linecolor="#E0E0E0", gridcolor="#F0F0F0",
            tickfont=dict(size=11),
        ),
        xaxis=dict(
            showgrid=True, gridcolor="#F0F0F0", linecolor="#E0E0E0",
            title="Consults",
        ),
    )
    return fig


def _build_new_referrer_trend(df):
    """Bar chart of new referrers by month (first referral month per physician)."""
    if df.empty or "ScheduledDateTime" not in df.columns:
        return empty_figure("No referral data available")

    ref_col = "ReferringPhysicianDimDoctorID"
    if ref_col not in df.columns:
        return empty_figure("Referring physician ID not available")

    df = df.copy()
    df_with_ref = df[df[ref_col].notna()]

    if df_with_ref.empty:
        return empty_figure("No referring physician data available")

    # Find each referring MD's first referral date
    first_referral = (
        df_with_ref
        .groupby(ref_col)["ScheduledDateTime"]
        .min()
        .reset_index()
    )
    first_referral.columns = [ref_col, "FirstReferralDate"]
    first_referral["_month"] = first_referral["FirstReferralDate"].dt.to_period("M").dt.to_timestamp()

    monthly_new = first_referral.groupby("_month").size().reset_index(name="count")
    monthly_new = monthly_new.sort_values("_month")

    if monthly_new.empty:
        return empty_figure("No new referrer data available")

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=monthly_new["_month"],
        y=monthly_new["count"],
        marker_color=CHART_COLORWAY[4],
        hovertemplate="%{x|%b %Y}: %{y} new referrers<extra></extra>",
        showlegend=False,
    ))

    fig = apply_default_layout(fig,
        height=380,
        margin=dict(l=48, r=16, t=8, b=48),
        xaxis=dict(
            showgrid=False, linecolor="#E0E0E0", gridcolor="#F0F0F0",
            dtick="M3", tickformat="%b %Y",
        ),
        yaxis=dict(
            showgrid=True, gridcolor="#F0F0F0", linecolor="#E0E0E0",
            title="New Referring MDs",
        ),
    )
    return fig


def _build_detail_table(df):
    """AG Grid detail table of referral consult records."""
    if df.empty:
        return dmc.Text(
            "No referral data to display.",
            c="#9CA3AF", ta="center", py="xl",
        )

    df = df.copy()
    df["RefPhysician"] = df.apply(_resolve_physician_name, axis=1)
    df["Specialty"] = df.apply(_resolve_specialty, axis=1)

    # Format the scheduled date
    if "ScheduledDateTime" in df.columns:
        df["Date"] = df["ScheduledDateTime"].dt.strftime("%m/%d/%Y %I:%M %p")
    else:
        df["Date"] = ""

    # Select and order columns for display
    col_map = {
        "Date": "Consult Date",
        "PatientFullName": "Patient",
        "Department": "Department",
        "RefPhysician": "Referring Physician",
        "Specialty": "Specialty",
    }
    if "DoctorInstitution" in df.columns:
        col_map["DoctorInstitution"] = "Institution"
    if "DiagnosisDescriptions" in df.columns:
        col_map["DiagnosisDescriptions"] = "Diagnosis"

    available_cols = [c for c in col_map.keys() if c in df.columns]
    table_df = df[available_cols].rename(columns=col_map)

    # Sort by date descending
    if "Consult Date" in table_df.columns:
        table_df = table_df.sort_values("Consult Date", ascending=False)

    column_defs = []
    for col in table_df.columns:
        col_def = {"field": col, "headerName": col, **DEFAULT_COLUMN_DEFS}
        if col == "Consult Date":
            col_def["width"] = 170
        elif col == "Patient":
            col_def["width"] = 160
        elif col == "Department":
            col_def["width"] = 110
        elif col == "Referring Physician":
            col_def["width"] = 180
        elif col == "Specialty":
            col_def["width"] = 160
        elif col == "Institution":
            col_def["width"] = 200
        elif col == "Diagnosis":
            col_def["flex"] = 1
            col_def["minWidth"] = 200
        column_defs.append(col_def)

    return dmc.Paper(
        children=[
            dmc.Group(
                justify="space-between", mb="sm",
                children=[
                    dmc.Text("Referral Detail", size="sm", fw=500, c="#6B7280"),
                    dmc.Text(
                        f"{len(table_df):,} records",
                        size="xs", c="#9CA3AF",
                    ),
                ],
            ),
            dag.AgGrid(
                id="referrals-detail-grid",
                rowData=table_df.to_dict("records"),
                columnDefs=column_defs,
                defaultColDef=DEFAULT_COLUMN_DEFS,
                dashGridOptions={
                    **DEFAULT_GRID_OPTIONS,
                    "paginationPageSize": 25,
                },
                style={"height": "500px"},
                className="ag-theme-alpine",
            ),
        ],
        p="sm", radius="md", shadow="xs", withBorder=True,
    )


# ---------------------------------------------------------------------------
# Chart wrapper helper
# ---------------------------------------------------------------------------

def _chart_paper(title, figure):
    """Wrap a Plotly figure in a titled Paper card."""
    return dmc.Paper(
        children=[
            dmc.Text(title, size="sm", fw=500, c="#6B7280", mb="sm"),
            dcc.Graph(
                figure=figure,
                config={"displayModeBar": False},
            ),
        ],
        p="sm", radius="md", shadow="xs", withBorder=True,
    )


# ---------------------------------------------------------------------------
# Main Callback
# ---------------------------------------------------------------------------

@callback(
    Output("referrals-kpi-row", "children"),
    Output("referrals-charts", "children"),
    Output("referrals-table-container", "children"),
    Input("referrals-interval", "n_intervals"),
    Input("referrals-filter-date-preset", "value"),
    Input("referrals-filter-department", "value"),
)
def update_referrals(_n, date_preset, departments):
    """Update all Referrals page components on filter change."""
    from data.loader import load_clinic_visits, load_referring

    PERIOD_LABELS = {"ytd": "YTD", "12mo": "12 Mo", "all": "All Time"}
    TREND_LABELS = {"ytd": "vs prior year", "12mo": "vs prior 12 mo", "all": ""}
    period_label = PERIOD_LABELS.get(date_preset, "12 Mo")
    trend_label = TREND_LABELS.get(date_preset, "")

    # -- Load and join data ------------------------------------------------
    try:
        cv = load_clinic_visits()
        ref = load_referring()
    except Exception:
        empty_kpis = [kpi_card("Total Referrals", "N/A")] * 5
        return empty_kpis, [], dmc.Text("Error loading data", c="#9CA3AF")

    if cv.empty or "ActivityName" not in cv.columns:
        empty_kpis = [kpi_card("Total Referrals", "N/A")] * 5
        return empty_kpis, [], dmc.Text("No clinic visit data", c="#9CA3AF")

    # Filter to consult activities
    consults = cv[cv["ActivityName"].str.contains("Consult", case=False, na=False)].copy()

    # Filter to completed
    if "Status" in consults.columns:
        consults = consults[
            consults["Status"].str.contains("Completed", case=False, na=False)
        ]

    if consults.empty:
        empty_kpis = [kpi_card("Total Referrals", "N/A")] * 5
        return empty_kpis, [], dmc.Text("No completed consult data", c="#9CA3AF")

    # Department filter
    if departments and "Department" in consults.columns:
        consults = consults[
            consults["Department"].isin(departments) | consults["Department"].isna()
        ]

    # Join to referring lookup
    if not ref.empty and "DimDoctorID" in ref.columns:
        merge_cols = ["DimDoctorID"]
        for col in [
            "DoctorFullName", "DoctorSpecialty",
            "DoctorInstitution", "PatientCount",
        ]:
            if col in ref.columns:
                merge_cols.append(col)
        ref_consults = consults.merge(
            ref[merge_cols],
            left_on="ReferringPhysicianDimDoctorID",
            right_on="DimDoctorID",
            how="left",
        )
    else:
        ref_consults = consults

    # -- Date filtering (data-relative) ------------------------------------
    if "ScheduledDateTime" not in ref_consults.columns or ref_consults.empty:
        empty_kpis = [kpi_card("Total Referrals", "N/A")] * 5
        return empty_kpis, [], dmc.Text("No data available", c="#9CA3AF")

    last_date = ref_consults["ScheduledDateTime"].dt.normalize().max()
    start_date = _preset_start(last_date, date_preset)

    # Full dataset for "new referrer" calculation (need all history)
    all_ref_consults = ref_consults.copy()

    # Filter to selected period
    period_data = ref_consults[
        ref_consults["ScheduledDateTime"] >= start_date
    ].copy()

    if period_data.empty:
        empty_kpis = [
            kpi_card(f"Total Referrals ({period_label})", "0")
        ] * 5
        return (
            empty_kpis, [],
            dmc.Text("No data for selected period", c="#9CA3AF"),
        )

    # -- KPI Calculations --------------------------------------------------
    ref_id_col = "ReferringPhysicianDimDoctorID"

    # 1. Total Referrals -- consults with a non-null referring physician
    has_ref = period_data[period_data[ref_id_col].notna()]
    total_referrals = len(has_ref)

    # Prior period comparison
    ps, pe = _prior_range(last_date, date_preset)
    if ps is not None and pe is not None:
        prior_data = ref_consults[
            (ref_consults["ScheduledDateTime"] >= ps)
            & (ref_consults["ScheduledDateTime"] <= pe)
        ]
        prior_referrals = len(prior_data[prior_data[ref_id_col].notna()])
    else:
        prior_data = pd.DataFrame()
        prior_referrals = None

    t_text, t_dir, t_prior = _trend(total_referrals, prior_referrals)
    kpi_total = kpi_card(
        f"Total Referrals ({period_label})",
        f"{total_referrals:,}",
        trend_text=(
            f"{t_text} {trend_label} ({t_prior:,.0f})" if t_text else None
        ),
        trend_direction=t_dir,
        accent_color=PRIMARY,
    )

    # 2. Unique Referring MDs
    unique_mds = has_ref[ref_id_col].nunique()
    if ps is not None and pe is not None and not prior_data.empty:
        prior_unique = (
            prior_data[prior_data[ref_id_col].notna()][ref_id_col].nunique()
        )
    else:
        prior_unique = None
    t_text2, t_dir2, t_prior2 = _trend(unique_mds, prior_unique)
    kpi_unique = kpi_card(
        f"Unique Referring MDs ({period_label})",
        f"{unique_mds:,}",
        trend_text=(
            f"{t_text2} {trend_label} ({t_prior2:,.0f})" if t_text2 else None
        ),
        trend_direction=t_dir2,
        accent_color=CHART_COLORWAY[1],
    )

    # 3. Top Referrer
    if not has_ref.empty:
        has_ref_named = has_ref.copy()
        has_ref_named["_physician"] = has_ref_named.apply(
            _resolve_physician_name, axis=1
        )
        physician_counts = (
            has_ref_named.groupby("_physician").size()
            .sort_values(ascending=False)
        )
        top_ref_name = physician_counts.index[0]
        top_ref_count = physician_counts.iloc[0]
        display_name = (
            top_ref_name
            if len(top_ref_name) <= 22
            else top_ref_name[:19] + "..."
        )
    else:
        display_name = "N/A"
        top_ref_count = 0

    kpi_top_ref = kpi_card(
        "Top Referrer",
        display_name,
        trend_text=(
            f"{top_ref_count:,} consults" if top_ref_count > 0 else None
        ),
        accent_color=CHART_COLORWAY[2],
    )

    # 4. Top Specialty
    if not has_ref.empty:
        has_ref_spec = has_ref.copy()
        has_ref_spec["_specialty"] = has_ref_spec.apply(
            _resolve_specialty, axis=1
        )
        spec_counts = (
            has_ref_spec.groupby("_specialty").size()
            .sort_values(ascending=False)
        )
        top_spec = spec_counts.index[0] if not spec_counts.empty else "N/A"
        top_spec_count = spec_counts.iloc[0] if not spec_counts.empty else 0
        display_spec = (
            top_spec if len(top_spec) <= 25 else top_spec[:22] + "..."
        )
    else:
        display_spec = "N/A"
        top_spec_count = 0

    kpi_top_spec = kpi_card(
        "Top Specialty",
        display_spec,
        trend_text=(
            f"{top_spec_count:,} consults" if top_spec_count > 0 else None
        ),
        accent_color=CHART_COLORWAY[3],
    )

    # 5. New Referrers -- MDs whose first-ever referral is within the period
    new_ref_count = 0
    prior_new_count = None
    if ref_id_col in all_ref_consults.columns:
        all_with_ref = all_ref_consults[all_ref_consults[ref_id_col].notna()]
        first_referral = (
            all_with_ref
            .groupby(ref_id_col)["ScheduledDateTime"]
            .min()
            .reset_index()
        )
        first_referral.columns = [ref_id_col, "FirstReferralDate"]
        new_referrers = first_referral[
            first_referral["FirstReferralDate"] >= start_date
        ]
        new_ref_count = len(new_referrers)

        if ps is not None and pe is not None:
            prior_new = first_referral[
                (first_referral["FirstReferralDate"] >= ps)
                & (first_referral["FirstReferralDate"] <= pe)
            ]
            prior_new_count = len(prior_new)

    t_text5, t_dir5, t_prior5 = _trend(new_ref_count, prior_new_count)
    kpi_new = kpi_card(
        f"New Referrers ({period_label})",
        f"{new_ref_count:,}",
        trend_text=(
            f"{t_text5} {trend_label} ({t_prior5:,.0f})" if t_text5 else None
        ),
        trend_direction=t_dir5,
        accent_color=CHART_COLORWAY[4],
    )

    kpis = [kpi_total, kpi_unique, kpi_top_ref, kpi_top_spec, kpi_new]

    # -- Charts ------------------------------------------------------------
    charts = []

    # Row 1: Top Physicians (half) + Specialty Donut (half)
    fig_physicians = _build_top_physicians_chart(period_data)
    fig_specialty = _build_specialty_donut(period_data)
    charts.append(
        dmc.Grid(
            gutter=16,
            children=[
                dmc.GridCol(
                    span={"base": 12, "md": 6},
                    children=_chart_paper(
                        "Top Referring Physicians", fig_physicians
                    ),
                ),
                dmc.GridCol(
                    span={"base": 12, "md": 6},
                    children=_chart_paper(
                        "Referrals by Specialty", fig_specialty
                    ),
                ),
            ],
        )
    )

    # Row 2: Volume Trend (half) + Institution Analysis (half)
    fig_trend = _build_volume_trend(all_ref_consults)
    fig_institution = _build_institution_chart(period_data)
    charts.append(
        dmc.Grid(
            gutter=16,
            children=[
                dmc.GridCol(
                    span={"base": 12, "md": 6},
                    children=_chart_paper(
                        "Referral Volume Trend", fig_trend
                    ),
                ),
                dmc.GridCol(
                    span={"base": 12, "md": 6},
                    children=_chart_paper(
                        "Institution Analysis", fig_institution
                    ),
                ),
            ],
        )
    )

    # Row 3: New Referrer Trend (half)
    fig_new = _build_new_referrer_trend(all_ref_consults)
    charts.append(
        dmc.Grid(
            gutter=16,
            children=[
                dmc.GridCol(
                    span={"base": 12, "md": 6},
                    children=_chart_paper(
                        "New Referrer Trend", fig_new
                    ),
                ),
            ],
        )
    )

    # -- Detail Table ------------------------------------------------------
    table = _build_detail_table(period_data)

    return kpis, charts, table
