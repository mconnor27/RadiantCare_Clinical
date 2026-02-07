"""Patients page — geographic visualization of patient origins with ZIP-centroid geocoding."""

import dash
import dash_mantine_components as dmc
import dash_ag_grid as dag
from dash import callback, ctx, Input, Output, State, dcc, no_update
import plotly.graph_objects as go
import pandas as pd
import numpy as np
from datetime import timedelta

from config.settings import (
    PHYSICIANS, DEPARTMENTS, DEPARTMENT_COLORS, CHART_COLORWAY, PRIMARY,
    DEFAULT_LAYOUT, FONT_FAMILY, SEMANTIC_COLORS, NEUTRAL,
    DEFAULT_COLUMN_DEFS, DEFAULT_GRID_OPTIONS,
    MAPBOX_TOKEN, MAPBOX_CENTER, MAPBOX_ZOOM, MAPBOX_STYLE,
)
from components.filter_bar import filter_bar, date_presets, department_chips
from components.kpi_card import kpi_card
from utils.charts import apply_default_layout, empty_figure, dept_color
from utils.geocoding import (
    prepare_patient_geo_data,
    get_department_patient_flows,
    bezier_arc,
    trigger_background_geocode,
    is_geocoding_complete,
    normalize_zip,
    DEPT_COORDS,
)


dash.register_page(__name__, path="/patients", name="Patients", order=11)


# ---------------------------------------------------------------------------
# Data prep
# ---------------------------------------------------------------------------

def _load_and_prepare():
    """Load patients data and clean/parse dates."""
    from data.loader import load_patients

    df = load_patients()
    if df.empty:
        return df

    if "Department" in df.columns:
        df["Department"] = (
            df["Department"].str.replace("*", "", regex=False).str.strip()
        )

    for col in ["FirstAppointment", "LastAppointment", "DateOfBirth"]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], format="%m/%d/%Y", errors="coerce")

    return df


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
                dmc.Title("Patients", order=2, className="page-title"),
                dmc.Paper(
                    children=[
                        dmc.Group(
                            children=[
                                date_presets("patients"),
                                department_chips("patients"),
                            ],
                            gap="lg",
                            wrap="wrap",
                        ),
                    ],
                    p="sm", px="md", radius="md", shadow="xs", withBorder=True,
                ),
            ],
        ),

        # KPI row
        dmc.Grid(id="patients-kpi-row", gutter=16, children=[]),

        # Map card with inline controls
        dmc.Paper(
            children=[
                # Row 1: title + department toggle
                dmc.Group(
                    justify="space-between",
                    mb="xs",
                    children=[
                        dmc.Text(
                            "Patient Origin Map",
                            size="sm", fw=500, c="#6B7280",
                        ),
                        dmc.SegmentedControl(
                            id="patients-map-flow-depts",
                            data=["All"] + list(DEPARTMENTS),
                            value="All",
                            size="xs",
                        ),
                    ],
                ),
                # Row 2: flow controls
                dmc.Group(
                    gap="lg",
                    mb="sm",
                    children=[
                        dmc.Switch(
                            id="patients-flow-toggle",
                            label="Flow lines",
                            size="xs",
                            checked=True,
                        ),
                        dmc.SegmentedControl(
                            id="patients-region-toggle",
                            data=[
                                {"label": "PNW", "value": "pnw"},
                                {"label": "All US", "value": "all"},
                            ],
                            value="pnw",
                            size="xs",
                        ),
                        dmc.Group(
                            gap="xs",
                            children=[
                                dmc.Text("Min patients:", size="xs", c="#9CA3AF"),
                                dmc.Slider(
                                    id="patients-min-slider",
                                    min=1, max=20, value=1, step=1,
                                    marks=[
                                        {"value": 1, "label": "1"},
                                        {"value": 5, "label": "5"},
                                        {"value": 10, "label": "10"},
                                        {"value": 20, "label": "20"},
                                    ],
                                    size="xs",
                                    w=160,
                                ),
                            ],
                        ),
                    ],
                ),
                # Geocoding status banner (hidden when cache is ready)
                dmc.Alert(
                    id="patients-geocode-status",
                    children="Geocoding ZIP codes for the first time. Map will appear when complete...",
                    color="violet",
                    variant="light",
                    style={"display": "none"},
                ),
                dcc.Graph(
                    id="patients-map",
                    config={"displayModeBar": False, "scrollZoom": True},
                    style={"height": "500px"},
                ),
            ],
            p="sm", radius="md", shadow="xs", withBorder=True,
        ),

        # Charts row: Department donut + Top Cities bar
        dmc.Grid(
            id="patients-charts-row",
            gutter=16,
            children=[],
        ),

        # Geographic summary table
        dmc.Stack(id="patients-table-container", gap=0, children=[]),

        # Stores
        dcc.Store(id="patients-store-geo", data=None),
        dcc.Store(id="patients-store-table", data=None),
        dcc.Store(id="patients-map-selection", data=None),

        # Intervals
        dcc.Interval(id="patients-interval", interval=300_000, n_intervals=0),
        dcc.Interval(
            id="patients-geocode-check", interval=5_000,
            n_intervals=0, max_intervals=120,
        ),
    ],
)


# ---------------------------------------------------------------------------
# Date filtering
# ---------------------------------------------------------------------------

def _apply_date_filter(df, date_preset):
    """Filter by date preset using LastAppointment."""
    if "LastAppointment" not in df.columns:
        return df

    # Cap at today so far-future scheduled appointments don't skew the window
    today = pd.Timestamp.now().normalize()
    last_date = df["LastAppointment"].dt.normalize().clip(upper=today).max()
    if pd.isna(last_date):
        return df

    if date_preset == "ytd":
        start = pd.Timestamp(last_date.year, 1, 1)
    elif date_preset == "12mo":
        start = last_date - timedelta(days=365)
    elif date_preset == "all":
        return df
    else:
        start = last_date - timedelta(days=365)

    return df[df["LastAppointment"] >= start]


# ---------------------------------------------------------------------------
# KPI cards
# ---------------------------------------------------------------------------

def _build_kpis(df, geo_df):
    """Build 5 KPI cards from filtered patient data."""
    total_patients = (
        df["PatientId"].nunique() if "PatientId" in df.columns else len(df)
    )

    unique_cities = 0
    if "City" in df.columns:
        unique_cities = (
            df["City"].dropna().str.strip()
            .replace("", pd.NA).dropna().nunique()
        )

    unique_counties = 0
    if "County" in df.columns:
        unique_counties = (
            df["County"].dropna().str.strip()
            .replace("", pd.NA).dropna().nunique()
        )

    top_city = "N/A"
    if "City" in df.columns:
        city_counts = (
            df["City"].dropna().str.strip()
            .replace("", pd.NA).dropna().str.title().value_counts()
        )
        if not city_counts.empty:
            top_city = city_counts.index[0]

    # Geocode coverage
    geocoded_pct = 0
    if not geo_df.empty and "patient_count" in geo_df.columns:
        geocoded_patients = geo_df["patient_count"].sum()
        geocoded_pct = round(geocoded_patients / max(total_patients, 1) * 100)

    return [
        dmc.GridCol(
            span={"base": 12, "sm": 6, "md": 2.4},
            children=kpi_card(
                "Total Patients", f"{total_patients:,}",
                accent_color=PRIMARY,
            ),
        ),
        dmc.GridCol(
            span={"base": 12, "sm": 6, "md": 2.4},
            children=kpi_card(
                "Unique Cities", f"{unique_cities:,}",
                accent_color=CHART_COLORWAY[1],
            ),
        ),
        dmc.GridCol(
            span={"base": 12, "sm": 6, "md": 2.4},
            children=kpi_card(
                "Unique Counties", f"{unique_counties:,}",
                accent_color=CHART_COLORWAY[2],
            ),
        ),
        dmc.GridCol(
            span={"base": 12, "sm": 6, "md": 2.4},
            children=kpi_card(
                "Top City", top_city,
                accent_color=CHART_COLORWAY[3],
            ),
        ),
        dmc.GridCol(
            span={"base": 12, "sm": 6, "md": 2.4},
            children=kpi_card(
                "Geocode Coverage", f"{geocoded_pct}%",
                accent_color=SEMANTIC_COLORS["success"],
            ),
        ),
    ]


# ---------------------------------------------------------------------------
# Charts: Department donut + Top cities bar
# ---------------------------------------------------------------------------

def _build_dept_donut(df):
    """Department distribution donut chart."""
    if "Department" not in df.columns or df.empty:
        return empty_figure("No department data available")

    dept_counts = (
        df.groupby("Department")["PatientId"]
        .nunique()
        .reset_index(name="PatientCount")
    )
    dept_counts = dept_counts.sort_values("PatientCount", ascending=False)

    if dept_counts.empty:
        return empty_figure("No department data available")

    colors = [
        DEPARTMENT_COLORS.get(d, CHART_COLORWAY[0])
        for d in dept_counts["Department"]
    ]

    fig = go.Figure(data=[go.Pie(
        labels=dept_counts["Department"],
        values=dept_counts["PatientCount"],
        hole=0.5,
        marker=dict(colors=colors),
        textinfo="label+percent",
        textposition="outside",
        hovertemplate="%{label}<br>%{value:,} patients (%{percent})<extra></extra>",
    )])

    fig.update_layout(
        height=380,
        font=dict(family=FONT_FAMILY, size=13),
        plot_bgcolor="#FFFFFF",
        paper_bgcolor="#FFFFFF",
        margin=dict(l=8, r=8, t=8, b=8),
        showlegend=False,
    )

    return fig


def _build_top_cities_bar(df, top_n=20):
    """Horizontal bar of top cities, stacked by department."""
    if "City" not in df.columns or "PatientId" not in df.columns or df.empty:
        return empty_figure("No city data available")

    work = df.copy()
    work["City"] = work["City"].str.strip().str.title().replace("", pd.NA)
    work = work.dropna(subset=["City"])

    if work.empty:
        return empty_figure("No city data available")

    has_dept = "Department" in work.columns

    if has_dept:
        city_dept = (
            work.groupby(["City", "Department"])["PatientId"]
            .nunique()
            .reset_index(name="PatientCount")
        )
        city_totals = city_dept.groupby("City")["PatientCount"].sum().nlargest(top_n)
        top_cities = city_totals.index.tolist()
        city_dept = city_dept[city_dept["City"].isin(top_cities)]
        city_order = city_totals.sort_values(ascending=True).index.tolist()

        fig = go.Figure()
        for dept in DEPARTMENTS:
            dept_data = city_dept[city_dept["Department"] == dept]
            if dept_data.empty:
                continue
            dept_series = (
                dept_data.set_index("City")["PatientCount"]
                .reindex(city_order, fill_value=0)
            )
            fig.add_trace(go.Bar(
                y=dept_series.index,
                x=dept_series.values,
                name=dept,
                orientation="h",
                marker_color=DEPARTMENT_COLORS.get(dept, CHART_COLORWAY[0]),
                hovertemplate="%{y}<br>%{x:,} patients<extra>" + dept + "</extra>",
            ))
        fig.update_layout(barmode="stack")
    else:
        city_counts = (
            work.groupby("City")["PatientId"]
            .nunique().nlargest(top_n).sort_values(ascending=True)
        )
        fig = go.Figure(data=[go.Bar(
            y=city_counts.index,
            x=city_counts.values,
            orientation="h",
            marker_color=PRIMARY,
            hovertemplate="%{y}<br>%{x:,} patients<extra></extra>",
        )])

    fig = apply_default_layout(fig, height=380)
    fig.update_layout(
        margin=dict(l=120, r=16, t=8, b=32),
        xaxis_title="Patient Count",
        yaxis=dict(autorange=True, showgrid=False),
    )
    return fig


# ---------------------------------------------------------------------------
# Map builder
# ---------------------------------------------------------------------------

def _build_patient_map(
    geo_df, departments_filter, selected_dept=None,
    show_flows=True, region="pnw", min_patients=1,
):
    """Build Scattermapbox with patient origin bubbles, dept markers, and flow lines.

    Parameters
    ----------
    selected_dept : str or None
        "All" shows every department; a single name shows only that dept.
    show_flows : bool
        Whether to render curved flow-line bundles.
    region : str
        "pnw" restricts to Pacific NW bounding box; "all" shows continental US.
    min_patients : int
        Minimum patient count at an origin to display it.
    """
    fig = go.Figure()

    # Bounding boxes ----------------------------------------------------------
    _PNW_LAT = (42.0, 50.0)
    _PNW_LON = (-126.0, -116.0)
    _US_LAT = (24.0, 50.0)
    _US_LON = (-126.0, -66.0)

    if region == "pnw":
        lat_bounds, lon_bounds = _PNW_LAT, _PNW_LON
    else:
        lat_bounds, lon_bounds = _US_LAT, _US_LON

    active_depts = departments_filter if departments_filter else list(DEPARTMENTS)

    # Determine which departments to render -----------------------------------
    if selected_dept == "All":
        render_depts = list(active_depts)
    elif selected_dept in active_depts:
        render_depts = [selected_dept]
    else:
        render_depts = []

    # --- Patient bubbles (one trace per department) --------------------------
    if render_depts and not geo_df.empty and "lat" in geo_df.columns:
        for dept in render_depts:
            dept_data = (
                geo_df[geo_df["Department"] == dept]
                if "Department" in geo_df.columns
                else geo_df
            )
            # Region filter
            dept_data = dept_data[
                (dept_data["lat"].between(*lat_bounds))
                & (dept_data["lon"].between(*lon_bounds))
            ]
            # Min-patients filter
            if "patient_count" in dept_data.columns:
                dept_data = dept_data[dept_data["patient_count"] >= min_patients]

            if dept_data.empty:
                continue

            color = DEPARTMENT_COLORS.get(dept, CHART_COLORWAY[0])
            fig.add_trace(go.Scattermapbox(
                lat=dept_data["lat"],
                lon=dept_data["lon"],
                mode="markers",
                marker=dict(size=8, color=color, opacity=0.7),
                customdata=dept_data[["zip5", "primary_city"]].values.tolist(),
                text=dept_data.apply(
                    lambda r, d=dept: (
                        f"{r['primary_city']} ({r['zip5']})<br>"
                        f"{d}: {r['patient_count']:,} "
                        f"patient{'s' if r['patient_count'] != 1 else ''}"
                    ),
                    axis=1,
                ),
                hoverinfo="text",
                showlegend=False,
            ))

    # --- Department location markers -----------------------------------------
    for dept in render_depts:
        coords = DEPT_COORDS.get(dept)
        if coords:
            color = DEPARTMENT_COLORS.get(dept, PRIMARY)
            fig.add_trace(go.Scattermapbox(
                lat=[coords[0]],
                lon=[coords[1]],
                mode="markers+text",
                marker=dict(size=16, color=color, symbol="hospital"),
                text=[dept],
                textposition="top center",
                textfont=dict(size=12, color=color),
                hovertext=f"{dept} Department",
                hoverinfo="text",
                showlegend=False,
            ))

    # --- Curved flow lines (bundled arcs scaled by relative volume) ----------
    if show_flows and render_depts and not geo_df.empty and "Department" in geo_df.columns:
        all_flows = get_department_patient_flows(geo_df, min_patients=min_patients)

        for dept in render_depts:
            dept_flows = [
                f for f in all_flows
                if f["dept"] == dept
                and lat_bounds[0] <= f["from_lat"] <= lat_bounds[1]
                and lon_bounds[0] <= f["from_lon"] <= lon_bounds[1]
            ]
            if not dept_flows:
                continue

            # Scale bundles relative to the largest flow in the current view
            max_flow = max(f["count"] for f in dept_flows)

            all_lats: list = []
            all_lons: list = []
            all_text: list = []
            all_cd: list = []
            for flow in dept_flows:
                count = flow["count"]
                ratio = count / max(max_flow, 1)
                # 1–6 arcs scaled by ratio to the largest flow
                n_arcs = max(1, min(6, 1 + int(ratio * 5)))
                if n_arcs == 1:
                    curvatures = [0.25]
                else:
                    curvatures = np.linspace(0.15, 0.35, n_arcs).tolist()

                hover = (
                    f"{flow['city_label']} \u2192 {dept}: "
                    f"{count:,} patient{'s' if count != 1 else ''}"
                )
                cd = [flow["zip5"], flow["city_label"]]
                for curv in curvatures:
                    arc_lats, arc_lons = bezier_arc(
                        flow["from_lat"], flow["from_lon"],
                        flow["to_lat"], flow["to_lon"],
                        num_points=20, curvature=curv,
                    )
                    all_lats.extend(arc_lats + [None])
                    all_lons.extend(arc_lons + [None])
                    all_text.extend([hover] * len(arc_lats) + [None])
                    all_cd.extend([cd] * len(arc_lats) + [None])

            color = DEPARTMENT_COLORS.get(dept, CHART_COLORWAY[0])
            fig.add_trace(go.Scattermapbox(
                lat=all_lats,
                lon=all_lons,
                mode="lines",
                line=dict(width=2.5, color=color),
                opacity=0.4,
                customdata=all_cd,
                text=all_text,
                hoverinfo="text",
                showlegend=False,
            ))

    fig.update_layout(
        mapbox=dict(
            accesstoken=MAPBOX_TOKEN,
            style=MAPBOX_STYLE,
            center=MAPBOX_CENTER,
            zoom=MAPBOX_ZOOM,
        ),
        height=500,
        margin=dict(l=0, r=0, t=0, b=0),
        font=dict(family=FONT_FAMILY, size=13),
        paper_bgcolor="#FFFFFF",
        showlegend=False,
        uirevision="patients-map",
    )

    return fig


# ---------------------------------------------------------------------------
# Geographic summary table
# ---------------------------------------------------------------------------

def _build_geo_table(df):
    """AG Grid table of geographic summary by City."""
    if df.empty or "City" not in df.columns:
        return dmc.Text(
            "No geographic data available",
            c="#9CA3AF", ta="center", py="xl",
        )

    work = df.copy()
    work["City"] = work["City"].str.strip().str.title().replace("", pd.NA)
    work = work.dropna(subset=["City"])
    if "County" in work.columns:
        work["County"] = work["County"].fillna("").str.strip().str.title()

    if work.empty:
        return dmc.Text(
            "No geographic data available",
            c="#9CA3AF", ta="center", py="xl",
        )

    has_dept = "Department" in work.columns
    has_county = "County" in work.columns

    group_cols = ["City"]
    if has_county:
        group_cols.append("County")
    if has_dept:
        group_cols.append("Department")

    geo_summary = (
        work.groupby(group_cols)["PatientId"]
        .nunique()
        .reset_index(name="PatientCount")
    )

    total_patients = geo_summary["PatientCount"].sum()
    geo_summary["PctOfTotal"] = (
        geo_summary["PatientCount"] / total_patients * 100
    ).round(1)
    geo_summary = geo_summary.sort_values("PatientCount", ascending=False)

    if "Zip" in work.columns:
        zip_map = (
            work.groupby("City")["Zip"]
            .agg(lambda x: x.mode().iloc[0] if not x.mode().empty else "")
            .reset_index()
        )
        geo_summary = geo_summary.merge(zip_map, on="City", how="left")

    column_defs = [
        {"field": "City", "headerName": "City", "minWidth": 140, "filter": "agTextColumnFilter"},
    ]
    if has_county:
        column_defs.append(
            {"field": "County", "headerName": "County", "minWidth": 120, "filter": "agTextColumnFilter"}
        )
    if "Zip" in geo_summary.columns:
        column_defs.append(
            {"field": "Zip", "headerName": "Zip", "minWidth": 80, "filter": "agTextColumnFilter"}
        )
    if has_dept:
        column_defs.append(
            {"field": "Department", "headerName": "Department", "minWidth": 110, "filter": "agTextColumnFilter"}
        )
    column_defs.extend([
        {
            "field": "PatientCount", "headerName": "Patient Count",
            "minWidth": 120, "type": "numericColumn",
            "filter": "agNumberColumnFilter",
            "valueFormatter": {"function": "d3.format(',')(params.value)"},
        },
        {
            "field": "PctOfTotal", "headerName": "% of Total",
            "minWidth": 100, "type": "numericColumn",
            "filter": "agNumberColumnFilter",
            "valueFormatter": {"function": "params.value + '%'"},
        },
    ])

    records = geo_summary.head(500).to_dict("records")
    for rec in records:
        for k, v in rec.items():
            if pd.isna(v):
                rec[k] = ""

    grid = dag.AgGrid(
        id="patients-geo-grid",
        rowData=records,
        columnDefs=column_defs,
        defaultColDef={**DEFAULT_COLUMN_DEFS, "flex": 1},
        dashGridOptions={**DEFAULT_GRID_OPTIONS, "paginationPageSize": 25},
        style={"height": "500px"},
        className="ag-theme-alpine",
    )

    return dmc.Paper(
        children=[
            dmc.Group(
                justify="space-between", mb="sm",
                children=[
                    dmc.Text("Geographic Summary", size="sm", fw=500, c="#6B7280"),
                    dmc.Text(f"{len(geo_summary):,} rows", size="xs", c="#9CA3AF"),
                ],
            ),
            grid,
        ],
        p="sm", radius="md", shadow="xs", withBorder=True,
    )


# ---------------------------------------------------------------------------
# Callback: main data update
# ---------------------------------------------------------------------------

@callback(
    Output("patients-kpi-row", "children"),
    Output("patients-store-geo", "data"),
    Output("patients-store-table", "data"),
    Output("patients-charts-row", "children"),
    Output("patients-geocode-status", "style"),
    Output("patients-map-selection", "data"),
    Input("patients-interval", "n_intervals"),
    Input("patients-geocode-check", "n_intervals"),
    Input("patients-filter-date-preset", "value"),
    Input("patients-filter-department", "value"),
)
def update_patients(_n_interval, _n_geocode, date_preset, departments):
    """Update all Patients page components based on filters."""
    df = _load_and_prepare()

    # --- Empty data ---
    if df.empty:
        empty_kpis = [
            dmc.GridCol(
                span={"base": 12, "sm": 6, "md": 2.4},
                children=kpi_card(label, "N/A"),
            )
            for label in ["Total Patients", "Unique Cities", "Unique Counties", "Top City", "Geocode Coverage"]
        ]
        return empty_kpis, None, None, [], {"display": "none"}, None

    # --- Apply filters ---
    df = _apply_date_filter(df, date_preset)
    if departments and "Department" in df.columns:
        df = df[df["Department"].isin(departments)]

    if df.empty:
        zero_kpis = [
            dmc.GridCol(
                span={"base": 12, "sm": 6, "md": 2.4},
                children=kpi_card(label, "0" if label != "Top City" else "N/A"),
            )
            for label in ["Total Patients", "Unique Cities", "Unique Counties", "Top City", "Geocode Coverage"]
        ]
        return zero_kpis, None, None, [], {"display": "none"}, None

    # --- Trigger background geocoding on first visit ---
    if "Zip" in df.columns:
        unique_zips = df["Zip"].apply(normalize_zip).dropna().unique().tolist()
        trigger_background_geocode(unique_zips)

    # --- Prepare geo data ---
    geo_df = prepare_patient_geo_data(df)

    # Geocoding status
    geocode_done = is_geocoding_complete()
    status_style = {"display": "none"} if geocode_done or not geo_df.empty else {}

    # Serialize geo data to store (no PII — only aggregated ZIP-level data)
    geo_store = geo_df.to_dict("records") if not geo_df.empty else None

    # --- Table data store (non-PII columns only) ---
    table_cols = [c for c in ["City", "County", "Department", "Zip", "PatientId"] if c in df.columns]
    table_store = df[table_cols].to_dict("records") if table_cols else None

    # --- KPIs ---
    kpis = _build_kpis(df, geo_df)

    # --- Charts row ---
    dept_donut = _build_dept_donut(df)
    top_cities = _build_top_cities_bar(df)

    charts_row = [
        dmc.GridCol(
            span={"base": 12, "md": 6},
            children=dmc.Paper(
                children=[
                    dmc.Text("Department Distribution", size="sm", fw=500, c="#6B7280", mb="sm"),
                    dcc.Graph(figure=dept_donut, config={"displayModeBar": False}),
                ],
                p="sm", radius="md", shadow="xs", withBorder=True,
            ),
        ),
        dmc.GridCol(
            span={"base": 12, "md": 6},
            children=dmc.Paper(
                children=[
                    dmc.Text("Top Cities by Patient Count", size="sm", fw=500, c="#6B7280", mb="sm"),
                    dcc.Graph(figure=top_cities, config={"displayModeBar": False}),
                ],
                p="sm", radius="md", shadow="xs", withBorder=True,
            ),
        ),
    ]

    # Only clear map selection when the user changes a filter, not on interval ticks
    clear_selection = (
        None if ctx.triggered_id in (
            "patients-filter-date-preset", "patients-filter-department",
        )
        else no_update
    )
    return kpis, geo_store, table_store, charts_row, status_style, clear_selection


# ---------------------------------------------------------------------------
# Callback: map figure (reads from store + inline controls)
# ---------------------------------------------------------------------------

@callback(
    Output("patients-map", "figure"),
    Input("patients-store-geo", "data"),
    Input("patients-map-flow-depts", "value"),
    Input("patients-filter-department", "value"),
    Input("patients-flow-toggle", "checked"),
    Input("patients-region-toggle", "value"),
    Input("patients-min-slider", "value"),
)
def update_map(geo_data, selected_dept, departments, show_flows, region, min_patients):
    """Build the Mapbox map from geocoded data in the store."""
    if not geo_data:
        fig = go.Figure()
        fig.update_layout(
            mapbox=dict(
                accesstoken=MAPBOX_TOKEN, style=MAPBOX_STYLE,
                center=MAPBOX_CENTER, zoom=MAPBOX_ZOOM,
            ),
            height=500,
            margin=dict(l=0, r=0, t=0, b=0),
            paper_bgcolor="#FFFFFF",
            showlegend=False,
            uirevision="patients-map",
        )
        return fig

    geo_df = pd.DataFrame(geo_data)
    return _build_patient_map(
        geo_df, departments,
        selected_dept=selected_dept,
        show_flows=show_flows,
        region=region,
        min_patients=min_patients or 1,
    )


# ---------------------------------------------------------------------------
# Callback: map click → toggle selection
# ---------------------------------------------------------------------------

@callback(
    Output("patients-map-selection", "data", allow_duplicate=True),
    Input("patients-map", "clickData"),
    State("patients-map-selection", "data"),
    prevent_initial_call=True,
)
def toggle_map_selection(click_data, current):
    """Click a bubble/flow to filter the table; click same one again to clear."""
    if not click_data or not click_data.get("points"):
        return no_update

    point = click_data["points"][0]
    cd = point.get("customdata")
    if not cd or not isinstance(cd, list) or len(cd) < 2:
        return None  # clicked dept marker or empty area → clear

    zip5, city = cd[0], cd[1]

    # Toggle: clicking the same ZIP deselects
    if current and current.get("zip5") == zip5:
        return None

    return {"zip5": zip5, "city": city}


# ---------------------------------------------------------------------------
# Callback: table (reacts to data store + map selection)
# ---------------------------------------------------------------------------

@callback(
    Output("patients-table-container", "children"),
    Input("patients-store-table", "data"),
    Input("patients-map-selection", "data"),
)
def update_table(table_data, selection):
    """Build the geographic summary table, optionally filtered by map selection."""
    if not table_data:
        return [dmc.Text("No patient data available", c="#9CA3AF", ta="center", py="xl")]

    df = pd.DataFrame(table_data)

    # --- Selection banner ---
    banner = None
    if selection and selection.get("zip5"):
        zip5 = selection["zip5"]
        city = selection.get("city", "")
        label = f"{city} ({zip5})" if city else zip5

        # Filter by normalized ZIP
        if "Zip" in df.columns:
            df["_zip5"] = df["Zip"].apply(normalize_zip)
            df = df[df["_zip5"] == zip5].drop(columns=["_zip5"])

        banner = dmc.Alert(
            children=dmc.Group(
                gap="xs",
                children=[
                    dmc.Text(
                        f"Filtered to {label}  —  click the same bubble to clear",
                        size="sm",
                    ),
                ],
            ),
            color="blue",
            variant="light",
            mb="sm",
            py="xs",
        )

    table = _build_geo_table(df)
    children = []
    if banner:
        children.append(banner)
    children.append(table)
    return children
