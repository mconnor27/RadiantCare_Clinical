"""Patients page — geographic visualization of patient origins with ZIP-centroid geocoding."""

import dash
import dash_mantine_components as dmc
from dash import callback, clientside_callback, ClientsideFunction, ctx, Input, Output, State, dcc, html, no_update
import plotly.graph_objects as go
import pandas as pd
import numpy as np
from datetime import timedelta
from dash_iconify import DashIconify

from config.settings import (
    DEPARTMENTS, DEPARTMENT_COLORS, CHART_COLORWAY, PRIMARY,
    DEFAULT_LAYOUT, FONT_FAMILY, SEMANTIC_COLORS, NEUTRAL,
    MAPBOX_TOKEN, MAPBOX_CENTER, MAPBOX_ZOOM, MAPBOX_STYLE,
    PHI_MODE,
)
from components.filter_bar import department_chips
from components.chart_card import chart_card, register_chart_callbacks
from components.kpi_card import kpi_card, kpi_placeholder
from utils.charts import apply_default_layout, empty_figure, dept_color
from utils.date_slider import (
    month_idx, idx_to_date, MAX_IDX, SLIDER_MARKS,
    preset_to_slider_val, preset_to_exact_dates,
)
from utils.geocoding import (
    prepare_patient_geo_data,
    get_department_patient_flows,
    bezier_arc,
    trigger_background_geocode,
    is_geocoding_complete,
    normalize_zip,
    build_zip3_geojson,
    DEPT_COORDS,
)


dash.register_page(__name__, path="/patients", name="Patients", order=11)

_DEFAULT_DATE_PRESET = "12mo"
_AGE_MIN = 0
_AGE_MAX = 110
_AGE_MARKS = [
    {"value": 0, "label": "0"},
    {"value": 20, "label": "20"},
    {"value": 40, "label": "40"},
    {"value": 60, "label": "60"},
    {"value": 80, "label": "80"},
    {"value": 100, "label": "100"},
]


# ---------------------------------------------------------------------------
# Filter bar
# ---------------------------------------------------------------------------

def _build_patients_filter_bar():
    """Single-row filter bar: date preset, date picker, date slider, departments, age."""
    return dmc.Paper(
        children=[
            dmc.Group(
                children=[
                    dmc.Select(
                        id="patients-filter-date-preset",
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
                        w=140,
                        allowDeselect=False,
                        leftSection=DashIconify(icon="mdi:clock-outline", width=14),
                        comboboxProps={"zIndex": 500, "offset": 2},
                        maxDropdownHeight=400,
                    ),
                    dmc.Paper(
                        dcc.DatePickerRange(
                            id="patients-filter-daterange",
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
                            html.Div(id="patients-date-range-label", style={"display": "none"}),
                            dmc.RangeSlider(
                                id="patients-date-slider",
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
                        style={"flex": "1", "minWidth": "200px"},
                    ),
                    department_chips("patients"),
                    dmc.Group(
                        gap="xs",
                        align="center",
                        children=[
                            dmc.Text(
                                "Age" if PHI_MODE else "Age at",
                                size="xs", c="#9CA3AF",
                            ),
                            # In PHI_MODE DOB is dropped and `AgeAtLoad` is the
                            # only age signal — the First/Last Appt toggle is
                            # meaningless, so hide it via a wrapper (keeping the
                            # SegmentedControl in the tree so the existing
                            # Input("patients-age-ref", "value") resolves).
                            html.Div(
                                dmc.SegmentedControl(
                                    id="patients-age-ref",
                                    data=[
                                        {"value": "first", "label": "First Appt"},
                                        {"value": "last", "label": "Last Appt"},
                                    ],
                                    value="first",
                                    size="xs",
                                ),
                                style={"display": "none"} if PHI_MODE else None,
                            ),
                            dmc.RangeSlider(
                                id="patients-filter-age",
                                min=_AGE_MIN,
                                max=_AGE_MAX,
                                value=[_AGE_MIN, _AGE_MAX],
                                step=1,
                                marks=_AGE_MARKS,
                                color="violet",
                                size="xs",
                                w=180,
                                minRange=0,
                                styles={
                                    "markLabel": {
                                        "fontSize": "10px",
                                        "marginTop": "0px",
                                    },
                                },
                            ),
                        ],
                    ),
                ],
                gap="md",
                align="center",
                wrap="wrap",
            ),
        ],
        p="sm",
        px="md",
        radius="md",
        shadow="xs",
        withBorder=True,
    )


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

    if "AgeAtLoad" in df.columns:
        df["AgeAtLoad"] = pd.to_numeric(df["AgeAtLoad"], errors="coerce")

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
                _build_patients_filter_bar(),
            ],
        ),

        # KPI row
        dmc.Grid(id="patients-kpi-row", gutter=16, children=[
            dmc.GridCol(kpi_placeholder(), span={"base": 12, "sm": 6, "md": 2.4}) for _ in range(5)
        ]),

        # Map card with inline controls.
        # In PHI_MODE the ZIP3 choropleth doesn't carry useful signal at the
        # resolution it renders, so hide the entire card. Components stay in
        # the tree (just display:none) so their Input/Output callback wiring
        # still resolves without needing conditional callbacks.
        dmc.Paper(
            style={"display": "none"} if PHI_MODE else None,
            children=[
                    dmc.Group(
                    justify="space-between",
                    mb="xs",
                    children=[
                        dmc.Text(
                            "Patient Origin Map",
                            size="sm", fw=500, c="#6B7280",
                        ),
                        dmc.Group(
                            gap="md",
                            align="center",
                            children=[
                                dmc.Switch(
                                    id="patients-flow-toggle",
                                    label="Flow lines",
                                    size="xs",
                                    checked=True,
                                ),
                                dmc.Group(
                                    gap="xs",
                                    align="center",
                                    children=[
                                        dmc.Text("Min:", size="xs", c="#9CA3AF"),
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
                                            w=140,
                                            styles={
                                                "markLabel": {
                                                    "fontSize": "9px",
                                                    "marginTop": "-2px",
                                                },
                                            },
                                        ),
                                    ],
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
                                dmc.SegmentedControl(
                                    id="patients-map-flow-depts",
                                    data=["All"] + list(DEPARTMENTS),
                                    value="All",
                                    size="xs",
                                ),
                                dmc.Tooltip(
                                    label="Reset map view",
                                    position="bottom",
                                    children=dmc.ActionIcon(
                                        DashIconify(icon="mdi:fit-to-screen-outline", width=16),
                                        id="patients-map-reset",
                                        variant="subtle",
                                        color="gray",
                                        size="sm",
                                    ),
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
                    style={"height": "700px"},
                ),
            ],
            p="sm", radius="md", shadow="xs", withBorder=True,
        ),

        # Charts row: Top Cities bar + Age distribution
        dmc.Grid(
            gutter=16,
            children=[
                dmc.GridCol(
                    span={"base": 12, "md": 6},
                    children=chart_card(
                        "patients-chart-top-cities",
                        "Top Cities by Patient Count",
                        chart_types=None,
                        show_smooth=False,
                        show_settings=False,
                    ),
                ),
                dmc.GridCol(
                    span={"base": 12, "md": 6},
                    children=chart_card(
                        "patients-chart-age-dist",
                        "Demographics",
                        chart_types=None,
                        show_smooth=True,
                        smooth_max=100,
                        smooth_default=50,
                        show_grouping=False,
                        settings_id="patients-age",
                        extra_controls_left=[
                            dmc.SegmentedControl(
                                id="patients-demog-metric",
                                data=[
                                    {"value": "age", "label": "Age"},
                                    {"value": "gender", "label": "Gender"},
                                ],
                                value="age",
                                size="xs",
                            ),
                            dmc.SegmentedControl(
                                id="patients-age-dist-group",
                                data=[
                                    {"value": "all", "label": "All"},
                                    {"value": "site", "label": "Per Site"},
                                ],
                                value="all",
                                size="xs",
                            ),
                        ],
                        extra_controls=[
                            # Histogram/Density — shown in Age mode only.
                            html.Div(
                                id="patients-age-dist-mode-wrap",
                                children=dmc.SegmentedControl(
                                    id="patients-age-dist-mode",
                                    data=[
                                        {"value": "histogram", "label": "Histogram"},
                                        {"value": "density", "label": "Density"},
                                    ],
                                    value="density",
                                    size="xs",
                                ),
                            ),
                            # Count/Percent — shown in Gender mode only.
                            html.Div(
                                id="patients-gender-scale-wrap",
                                style={"display": "none"},
                                children=dmc.SegmentedControl(
                                    id="patients-gender-scale",
                                    data=[
                                        {"value": "count", "label": "Count"},
                                        {"value": "pct",   "label": "Percent"},
                                    ],
                                    value="count",
                                    size="xs",
                                ),
                            ),
                        ],
                    ),
                ),
            ],
        ),

        # Stores
        dcc.Store(id="patients-store-geo", data=None),
        dcc.Store(id="patients-store-age-dist", data=None),
        dcc.Store(id="patients-map-selection", data=None),

        # Intervals
        dcc.Interval(id="patients-interval", interval=300_000, n_intervals=0, max_intervals=0),  # fires once on mount; no background refresh (daily data + global refresh button)
        dcc.Interval(
            id="patients-geocode-check", interval=5_000,
            n_intervals=0, max_intervals=120,
        ),
    ],
)

register_chart_callbacks([("patients-age", "patients-chart-age-dist")])


# Hide Histogram/Density + smoothing when the user switches to Gender.
# Inline (not namespaced) because the logic is trivial and only applies here.
clientside_callback(
    """
    function(metric) {
        const hidden = {display: "none"};
        const shown = {};
        if (metric === "gender") {
            return [hidden, hidden, shown];
        }
        return [shown, shown, hidden];
    }
    """,
    Output("patients-age-dist-mode-wrap", "style"),
    Output("patients-age-settings-smooth-wrap", "style", allow_duplicate=True),
    Output("patients-gender-scale-wrap", "style"),
    Input("patients-demog-metric", "value"),
    prevent_initial_call=True,
)


# ---------------------------------------------------------------------------
# Date slider sync callbacks
# ---------------------------------------------------------------------------

# A) Preset -> Slider + DatePicker
@callback(
    Output("patients-date-slider", "value", allow_duplicate=True),
    Output("patients-filter-daterange", "start_date", allow_duplicate=True),
    Output("patients-filter-daterange", "end_date", allow_duplicate=True),
    Input("patients-filter-date-preset", "value"),
    prevent_initial_call=True,
)
def _sync_preset(preset):
    if not preset or preset == "custom":
        return (dash.no_update,) * 3
    sv = preset_to_slider_val(preset, MAX_IDX)
    s, e = preset_to_exact_dates(preset)
    return sv, s, e


# B) Slider -> DatePicker + Label (clientside)
clientside_callback(
    ClientsideFunction(namespace="patientsDateSlider", function_name="syncSlider"),
    Output("patients-filter-daterange", "start_date", allow_duplicate=True),
    Output("patients-filter-daterange", "end_date", allow_duplicate=True),
    Output("patients-date-range-label", "children"),
    Input("patients-date-slider", "value"),
    State("patients-filter-daterange", "start_date"),
    State("patients-filter-daterange", "end_date"),
    prevent_initial_call=True,
)


# C) DatePicker -> Slider
@callback(
    Output("patients-date-slider", "value", allow_duplicate=True),
    Input("patients-filter-daterange", "start_date"),
    Input("patients-filter-daterange", "end_date"),
    State("patients-date-slider", "value"),
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
    Output("patients-filter-date-preset", "value", allow_duplicate=True),
    Input("patients-date-slider", "value"),
    State("patients-filter-date-preset", "value"),
    prevent_initial_call=True,
)
def _maybe_clear_preset(slider_val, current_preset):
    if not current_preset or current_preset == "custom":
        return dash.no_update
    expected = preset_to_slider_val(current_preset, MAX_IDX)
    if slider_val == expected:
        return dash.no_update
    return "custom"


# ---------------------------------------------------------------------------
# Date / age filtering helpers
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


def _apply_date_filter(df, slider_val, daterange):
    """Filter by date range using LastAppointment."""
    if "LastAppointment" not in df.columns:
        return df
    start, end = _get_date_range(slider_val, daterange)
    return df[(df["LastAppointment"] >= start) & (df["LastAppointment"] <= end)]


def _compute_age(df, ref="last"):
    """Compute age at first or last appointment.

    Args:
        ref: "last" (default) or "first" — which appointment date to use.

    In PHI_MODE the DOB is dropped at build time and replaced by a single
    pre-computed `AgeAtLoad` column (integer years, capped at 90). The ref
    toggle has no effect in that case.
    """
    if "DateOfBirth" not in df.columns:
        if "AgeAtLoad" in df.columns:
            return pd.to_numeric(df["AgeAtLoad"], errors="coerce").astype("float64")
        return pd.Series(dtype="float64", index=df.index)

    if ref == "first" and "FirstAppointment" in df.columns:
        ref_date = df["FirstAppointment"]
    else:
        ref_date = df.get("LastAppointment", df.get("FirstAppointment"))

    if ref_date is None:
        ref_date = pd.Timestamp.now()

    age = (ref_date - df["DateOfBirth"]).dt.days / 365.25
    return age.clip(lower=0)


def _apply_age_filter(df, age_range, age_ref="last"):
    """Filter by age range."""
    if not age_range or len(age_range) != 2:
        return df
    if "DateOfBirth" not in df.columns and "AgeAtLoad" not in df.columns:
        return df
    age = _compute_age(df, ref=age_ref)
    return df[(age >= age_range[0]) & (age <= age_range[1])]


# ---------------------------------------------------------------------------
# KPI cards
# ---------------------------------------------------------------------------

def _build_kpis(df, geo_df):
    """Build KPI cards: totals + per-department patient counts."""
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

    # Per-department counts
    dept_counts = {}
    if "Department" in df.columns and "PatientId" in df.columns:
        dept_counts = (
            df.groupby("Department", observed=True)["PatientId"].nunique().to_dict()
        )

    cards = [
        dmc.GridCol(
            span={"base": 12, "sm": 6, "md": 2},
            children=kpi_card(
                "Total Patients", f"{total_patients:,}",
                accent_color=PRIMARY,
            ),
        ),
        dmc.GridCol(
            span={"base": 12, "sm": 6, "md": 2},
            children=kpi_card(
                "Unique Cities", f"{unique_cities:,}",
                accent_color=CHART_COLORWAY[1],
            ),
        ),
        dmc.GridCol(
            span={"base": 12, "sm": 6, "md": 2},
            children=kpi_card(
                "Top City", top_city,
                accent_color=CHART_COLORWAY[3],
            ),
        ),
    ]

    # Department cards with percentage
    for dept in DEPARTMENTS:
        count = dept_counts.get(dept, 0)
        pct = round(count / max(total_patients, 1) * 100) if total_patients else 0
        cards.append(
            dmc.GridCol(
                span={"base": 12, "sm": 6, "md": 2},
                children=kpi_card(
                    dept, f"{count:,}",
                    value_detail=f"({pct}%)",
                    accent_color=DEPARTMENT_COLORS.get(dept, CHART_COLORWAY[0]),
                ),
            ),
        )

    return cards


# ---------------------------------------------------------------------------
# Charts: Top cities bar
# ---------------------------------------------------------------------------

def _build_top_cities_bar(df, top_n=12):
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

        # Add total labels at end of each stacked bar.
        # #4B5563 is registered with 02_theme.js's annotation-neutral remap:
        # stays mid-gray in light, swaps to #FFFFFF in dark.
        for city in city_order:
            total = int(city_totals[city])
            fig.add_annotation(
                x=total, y=city,
                text=f" {total:,}",
                showarrow=False,
                xanchor="left",
                font=dict(size=11, color="#4B5563"),
            )
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
            text=[f"{v:,}" for v in city_counts.values],
            textposition="outside",
            hovertemplate="%{y}<br>%{x:,} patients<extra></extra>",
        )])

    fig = apply_default_layout(fig, height=380)
    fig.update_layout(
        margin=dict(l=100, r=32, t=8, b=6),
        xaxis_title="Patient Count",
        yaxis=dict(autorange=True, showgrid=False),
    )
    return fig


# ---------------------------------------------------------------------------
# Age distribution data prep
# ---------------------------------------------------------------------------

def _prepare_demog_data(df, age_ref="last"):
    """Prepare demographics (age + gender) data for the chart store.

    Returns a single payload covering both metrics; the chart callback
    picks the relevant section based on the user's Age/Gender toggle.
    """
    if df.empty:
        return None

    result: dict = {}

    # --- Age ----------------------------------------------------------------
    if "DateOfBirth" in df.columns or "AgeAtLoad" in df.columns:
        ages = _compute_age(df, ref=age_ref).dropna()
        ages = ages[(ages >= 0) & (ages <= 120)]
        if not ages.empty:
            arr = ages.values
            try:
                from scipy.stats import gaussian_kde
                kde = gaussian_kde(arr, bw_method="silverman")
                x_min = max(0, float(arr.min()) - 2)
                x_max = float(arr.max()) + 2
                x_grid = np.linspace(x_min, x_max, 200)
                kde_y_raw = kde(x_grid)
                kde_x = [round(float(v), 2) for v in x_grid]
                kde_y = [round(float(v), 6) for v in kde_y_raw]
            except Exception:
                kde_x, kde_y = [], []

            result.update({
                "values": [round(float(v), 1) for v in arr],
                "median": round(float(np.median(arr)), 1),
                "mean": round(float(np.mean(arr)), 1),
                "p25": round(float(np.percentile(arr, 25)), 1),
                "p75": round(float(np.percentile(arr, 75)), 1),
                "n": int(len(arr)),
                "kde_x": kde_x,
                "kde_y": kde_y,
            })

            if "Department" in df.columns:
                by_dept = {}
                for dept in DEPARTMENTS:
                    dept_ages = ages[df.loc[ages.index, "Department"] == dept]
                    if dept_ages.empty:
                        continue
                    by_dept[dept] = [round(float(v), 1) for v in dept_ages.values]
                result["by_dept"] = by_dept

    # --- Gender -------------------------------------------------------------
    if "Gender" in df.columns and "PatientId" in df.columns:
        gdf = df[["PatientId", "Gender"]].copy()
        gdf["Gender"] = (
            gdf["Gender"].astype("object").where(gdf["Gender"].notna(), "Unknown")
        )
        gdf["Gender"] = gdf["Gender"].replace({"": "Unknown"}).fillna("Unknown")
        # Dedup to one row per patient so gender counts match Total Patients.
        gdf = gdf.drop_duplicates("PatientId")

        total = gdf["Gender"].value_counts().to_dict()
        gender_payload: dict = {"total": {k: int(v) for k, v in total.items()}}

        if "Department" in df.columns:
            ddf = df[["PatientId", "Gender", "Department"]].copy()
            ddf["Gender"] = (
                ddf["Gender"].astype("object").where(ddf["Gender"].notna(), "Unknown")
            )
            ddf["Gender"] = ddf["Gender"].replace({"": "Unknown"}).fillna("Unknown")
            ddf = ddf.drop_duplicates(["PatientId", "Department"])
            by_dept_gender: dict = {}
            for dept in DEPARTMENTS:
                sub = ddf[ddf["Department"] == dept]
                if sub.empty:
                    continue
                by_dept_gender[dept] = {
                    k: int(v) for k, v in sub["Gender"].value_counts().to_dict().items()
                }
            gender_payload["by_dept"] = by_dept_gender

        result["gender"] = gender_payload

    return result or None


# Back-compat alias — callers elsewhere in the module still reference the old
# name. Remove once no references remain.
_prepare_age_dist_data = _prepare_demog_data


# ---------------------------------------------------------------------------
# Map builder
# ---------------------------------------------------------------------------

def _build_patient_map(
    geo_df, departments_filter, selected_dept=None,
    show_flows=True, region="pnw", min_patients=1,
    uirevision="patients-map",
    map_style=None,
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

    # --- PHI-mode choropleth (ZIP3 polygons) --------------------------------
    phi_choropleth = PHI_MODE and render_depts and not geo_df.empty and "zip5" in geo_df.columns
    if phi_choropleth:
        if "Department" in geo_df.columns:
            cho = geo_df[geo_df["Department"].isin(render_depts)]
        else:
            cho = geo_df
        cho = cho[cho["patient_count"] >= min_patients]
        cho = cho[
            (cho["lat"].between(*lat_bounds))
            & (cho["lon"].between(*lon_bounds))
        ]

        if not cho.empty:
            totals = (
                cho.groupby("zip5", as_index=False)
                .agg(patient_count=("patient_count", "sum"),
                     primary_city=("primary_city", "first"))
            )

            single_dept = render_depts[0] if len(render_depts) == 1 else None
            if single_dept:
                base = DEPARTMENT_COLORS.get(single_dept, PRIMARY)
                colorscale = [[0.0, "rgba(255,255,255,0.2)"], [1.0, base]]
            else:
                colorscale = "Viridis"

            hover = [
                f"ZIP3 {row.zip5}xx<br>{int(row.patient_count):,} patients"
                for row in totals.itertuples()
            ]
            fig.add_trace(go.Choroplethmapbox(
                geojson=build_zip3_geojson(),
                locations=totals["zip5"].tolist(),
                z=totals["patient_count"].tolist(),
                customdata=[[z, c] for z, c in zip(totals["zip5"], totals["primary_city"])],
                colorscale=colorscale,
                marker=dict(line=dict(width=0.5, color="rgba(60,60,60,0.6)"), opacity=0.55),
                showscale=True,
                colorbar=dict(
                    title=dict(text="Patients", side="right"),
                    thickness=10, len=0.6, x=0.99, xanchor="right",
                ),
                text=hover,
                hoverinfo="text",
            ))
            # Invisible scatter to seed autofit with ZIP3 centroids
            fig.add_trace(go.Scattermapbox(
                lat=cho["lat"].tolist(),
                lon=cho["lon"].tolist(),
                mode="markers",
                marker=dict(size=1, opacity=0),
                hoverinfo="skip",
                showlegend=False,
            ))

    # --- Patient bubbles (one trace per department) --------------------------
    if not phi_choropleth and render_depts and not geo_df.empty and "lat" in geo_df.columns:
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

    # Auto-fit: compute center and zoom from trace coordinates
    import math
    all_lat, all_lon = [], []
    for trace in fig.data:
        lats = trace.lat if hasattr(trace, "lat") else []
        lons = trace.lon if hasattr(trace, "lon") else []
        if lats is not None:
            all_lat.extend(v for v in lats if v is not None)
        if lons is not None:
            all_lon.extend(v for v in lons if v is not None)

    if all_lat and all_lon:
        center = dict(
            lat=(min(all_lat) + max(all_lat)) / 2,
            lon=(min(all_lon) + max(all_lon)) / 2,
        )
        lat_span = max(max(all_lat) - min(all_lat), 0.1) * 1.2
        lon_span = max(max(all_lon) - min(all_lon), 0.1) * 1.2
        z_lat = 8.4 - math.log2(lat_span)   # calibrated for ~700px height
        z_lon = 10.0 - math.log2(lon_span)  # calibrated for full-width card (~2000px+)
        zoom = max(2.0, min(12.0, min(z_lat, z_lon)))
    else:
        center = MAPBOX_CENTER
        zoom = MAPBOX_ZOOM

    fig.update_layout(
        mapbox=dict(
            accesstoken=MAPBOX_TOKEN,
            style=map_style or MAPBOX_STYLE,
            center=center,
            zoom=zoom,
        ),
        height=700,
        margin=dict(l=0, r=0, t=0, b=0),
        font=dict(family=FONT_FAMILY, size=13),
        paper_bgcolor="rgba(0,0,0,0)",
        showlegend=False,
        uirevision=uirevision,
    )

    return fig



# ---------------------------------------------------------------------------
# Callback: main data update
# ---------------------------------------------------------------------------

@callback(
    Output("patients-kpi-row", "children"),
    Output("patients-store-geo", "data"),
    Output("patients-store-age-dist", "data"),
    Output("patients-chart-top-cities", "figure"),
    Output("patients-geocode-status", "style"),
    Output("patients-map-selection", "data"),
    Output("patients-filter-age", "min"),
    Output("patients-filter-age", "max"),
    Output("patients-filter-age", "marks"),
    Input("patients-interval", "n_intervals"),
    Input("patients-date-slider", "value"),
    Input("patients-filter-date-preset", "value"),
    Input("patients-filter-department", "value"),
    Input("patients-filter-age", "value"),
    Input("patients-age-ref", "value"),
    running=[
        (Output("patients-chart-top-cities-loading", "visible"), True, False),
        (Output("patients-chart-age-dist-loading", "visible"), True, False),
    ],
)
def update_patients(_n_interval, slider_val, date_preset,
                    departments, age_range, age_ref):
    """Update all Patients page components based on filters."""
    df = _load_and_prepare()

    _empty = [kpi_card("—", "N/A")]
    _no_age = (_AGE_MIN, _AGE_MAX, _AGE_MARKS)

    # --- Empty data ---
    if df.empty:
        return _empty, None, None, empty_figure("No city data available"), {"display": "none"}, None, *_no_age

    # --- Apply date + department filters (before computing age range) ---
    df = _apply_date_filter(df, slider_val, None)
    if departments and "Department" in df.columns:
        df = df[df["Department"].isin(departments)]

    if df.empty:
        return _empty, None, None, empty_figure("No city data available"), {"display": "none"}, None, *_no_age

    # --- Compute dynamic age range from date+dept filtered data ---
    age_ref = age_ref or "last"
    ages = _compute_age(df, ref=age_ref).dropna()
    if not ages.empty:
        age_lo = int(ages.min())
        age_hi = min(int(ages.max()) + 1, 120)
        # Only show min, max, and ~3 evenly spaced round marks to avoid overlap
        span = age_hi - age_lo
        if span <= 20:
            step = 5
        elif span <= 50:
            step = 10
        else:
            step = 20
        first_mark = age_lo + (step - age_lo % step) if age_lo % step else age_lo
        inner = [v for v in range(first_mark, age_hi, step) if v != age_lo and v != age_hi]
        age_marks = [{"value": age_lo, "label": str(age_lo)}]
        age_marks += [{"value": v, "label": str(v)} for v in inner]
        age_marks.append({"value": age_hi, "label": str(age_hi)})
    else:
        age_lo, age_hi, age_marks = _AGE_MIN, _AGE_MAX, _AGE_MARKS

    # --- Apply age filter ---
    df = _apply_age_filter(df, age_range, age_ref=age_ref)

    if df.empty:
        return _empty, None, None, empty_figure("No city data available"), {"display": "none"}, None, age_lo, age_hi, age_marks

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

    # --- Age distribution data ---
    age_dist_data = _prepare_age_dist_data(df, age_ref=age_ref)

    # --- KPIs ---
    kpis = _build_kpis(df, geo_df)

    # --- Top cities chart ---
    top_cities = _build_top_cities_bar(df)

    # Only clear map selection when the user changes a filter, not on interval ticks
    clear_selection = (
        None if ctx.triggered_id in (
            "patients-date-slider", "patients-filter-date-preset",
            "patients-filter-department", "patients-filter-age",
            "patients-age-ref",
        )
        else no_update
    )
    return kpis, geo_store, age_dist_data, top_cities, status_style, clear_selection, age_lo, age_hi, age_marks


# ---------------------------------------------------------------------------
# Callback: geocode progress poll
#
# Runs only until the geocode cache finishes warming. Updates the status
# banner and disables itself — crucially, this is NOT wired into the main
# update_patients callback, so it doesn't cause the whole page to re-render
# (and the charts to flash) every 5 seconds.
# ---------------------------------------------------------------------------

@callback(
    Output("patients-geocode-status", "style", allow_duplicate=True),
    Output("patients-geocode-check", "disabled"),
    Input("patients-geocode-check", "n_intervals"),
    prevent_initial_call=True,
)
def _poll_geocode_status(_n):
    if is_geocoding_complete():
        return {"display": "none"}, True
    return no_update, no_update


# ---------------------------------------------------------------------------
# Gender distribution helper (used when metric toggle is set to Gender)
# ---------------------------------------------------------------------------

# Ordering used by both the overall bar and the per-site stacks.
_GENDER_ORDER = ["Female", "Male", "Unknown"]
_GENDER_COLORS = {
    "Female": "#A88FFF",   # lavender — complements brand purple
    "Male": "#4C8DFF",     # steel blue
    "Unknown": "#9CA3AF",  # neutral gray
}


def _build_gender_fig(data, group="all", scale="count"):
    """Build the gender distribution figure.

    "all"  -> horizontal bar of totals.
    "site" -> grouped bars per department, one series per gender.

    scale="count" shows raw counts; "pct" shows percent-of-group (percent of
    the whole in "all" mode, percent of that site's total in "site" mode).
    """
    gender = (data or {}).get("gender") if data else None
    if not gender or not gender.get("total"):
        fig = empty_figure("No gender data available")
        fig.update_layout(height=380)
        return fig

    fig = go.Figure()
    as_pct = (scale == "pct")

    if group == "site" and gender.get("by_dept"):
        by_dept = gender["by_dept"]
        dept_order = [d for d in DEPARTMENTS if d in by_dept]
        site_totals = {d: sum(by_dept.get(d, {}).values()) or 1 for d in dept_order}

        for g in _GENDER_ORDER:
            counts = [by_dept.get(d, {}).get(g, 0) for d in dept_order]
            if not any(counts):
                continue
            if as_pct:
                vals = [c / site_totals[d] * 100 for c, d in zip(counts, dept_order)]
                text = [f"{v:.0f}%" if v else "" for v in vals]
                hover = (
                    f"{g}<br>%{{x}}: %{{y:.1f}}%  "
                    f"(%{{customdata:,}} patients)<extra></extra>"
                )
                fig.add_trace(go.Bar(
                    x=dept_order, y=vals, name=g,
                    customdata=counts,
                    marker_color=_GENDER_COLORS[g],
                    hovertemplate=hover,
                    text=text, textposition="outside",
                    textfont=dict(size=11, color="#4B5563"),
                ))
            else:
                fig.add_trace(go.Bar(
                    x=dept_order, y=counts, name=g,
                    marker_color=_GENDER_COLORS[g],
                    hovertemplate=f"{g}<br>%{{x}}: %{{y:,}} patients<extra></extra>",
                    text=[f"{v:,}" if v else "" for v in counts],
                    textposition="outside",
                    textfont=dict(size=11, color="#4B5563"),
                ))
        fig.update_layout(barmode="group")
        xaxis_title = "Department"
        yaxis_title = "Share of site" if as_pct else "Patients"
    else:
        total = gender["total"]
        cats = [g for g in _GENDER_ORDER if total.get(g, 0) > 0]
        counts = [total[g] for g in cats]
        grand = sum(counts) or 1
        if as_pct:
            pcts = [c / grand * 100 for c in counts]
            fig.add_trace(go.Bar(
                y=cats, x=pcts,
                orientation="h",
                marker_color=[_GENDER_COLORS[g] for g in cats],
                customdata=counts,
                text=[f"{p:.1f}%" for p in pcts],
                textposition="outside",
                textfont=dict(size=11, color="#4B5563"),
                hovertemplate=(
                    "%{y}<br>%{x:.1f}%  (%{customdata:,} patients)<extra></extra>"
                ),
            ))
            xaxis_title = "Share of patients (%)"
        else:
            fig.add_trace(go.Bar(
                y=cats, x=counts,
                orientation="h",
                marker_color=[_GENDER_COLORS[g] for g in cats],
                text=[f"{v:,} ({v/grand:.0%})" for v in counts],
                textposition="outside",
                textfont=dict(size=11, color="#4B5563"),
                hovertemplate="%{y}<br>%{x:,} patients<extra></extra>",
            ))
            xaxis_title = "Patient Count"
        yaxis_title = None

    apply_default_layout(fig)
    n_total = sum(gender["total"].values())
    # Matches the top-cities chart margins so the x-axis baselines align.
    fig.update_layout(
        height=380,
        xaxis_title=f"{xaxis_title}  (n={n_total:,})",
        yaxis_title=yaxis_title,
        margin=dict(l=80, r=32, t=8, b=6),
        showlegend=(group == "site"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02,
                    xanchor="left", x=0),
    )
    # Outside-bar labels need headroom on the right so they aren't clipped.
    if group != "site":
        if as_pct:
            fig.update_xaxes(range=[0, 110])
        else:
            grand = sum(gender["total"].values()) or 1
            fig.update_xaxes(range=[0, grand * 1.18])
    return fig


# ---------------------------------------------------------------------------
# Callback: age distribution chart (reads from store + toggle)
# ---------------------------------------------------------------------------

@callback(
    Output("patients-chart-age-dist", "figure"),
    Input("patients-store-age-dist", "data"),
    Input("patients-demog-metric", "value"),
    Input("patients-age-dist-mode", "value"),
    Input("patients-age-dist-group", "value"),
    Input("patients-age-settings-smooth", "value"),
    Input("patients-gender-scale", "value"),
    running=[
        (Output("patients-chart-age-dist-loading", "visible"), True, False),
    ],
)
def _update_age_dist(data, metric, mode, group, bandwidth_pct, gender_scale):
    metric = metric or "age"

    if metric == "gender":
        return _build_gender_fig(
            data, group=group or "all", scale=gender_scale or "count",
        )

    if not data or "values" not in data:
        fig = empty_figure("No age data available")
        fig.update_layout(height=380)
        return fig

    mode = mode or "density"
    group = group or "all"
    bw_pct = bandwidth_pct if bandwidth_pct is not None else 50
    bw_factor = max(0.1, 0.1 + (bw_pct / 100) * 2.9)

    fig = go.Figure()
    by_dept = data.get("by_dept", {})
    per_site = group == "site" and bool(by_dept)

    def _hex_to_rgba(hex_color, alpha):
        r, g, b = int(hex_color[1:3], 16), int(hex_color[3:5], 16), int(hex_color[5:7], 16)
        return f"rgba({r},{g},{b},{alpha})"

    if mode == "density":
        from scipy.stats import gaussian_kde

        if per_site:
            for dept, dept_vals in by_dept.items():
                vals = np.array(dept_vals)
                if len(vals) < 2:
                    continue
                color = DEPARTMENT_COLORS.get(dept, CHART_COLORWAY[0])
                try:
                    kde = gaussian_kde(vals, bw_method="silverman")
                    kde.set_bandwidth(kde.factor * bw_factor)
                    x_grid = np.linspace(max(0, vals.min() - 2), vals.max() + 2, 200)
                    fig.add_trace(go.Scatter(
                        x=x_grid, y=kde(x_grid),
                        mode="lines", fill="tozeroy", name=dept,
                        line=dict(color=color, width=2),
                        fillcolor=_hex_to_rgba(color, 0.15),
                        hovertemplate=f"{dept}<br>Age: %{{x:.0f}}<br>Density: %{{y:.4f}}<extra></extra>",
                    ))
                except Exception:
                    pass
        else:
            vals = np.array(data["values"])
            try:
                kde = gaussian_kde(vals, bw_method="silverman")
                kde.set_bandwidth(kde.factor * bw_factor)
                x_grid = np.linspace(max(0, vals.min() - 2), vals.max() + 2, 200)
                fig.add_trace(go.Scatter(
                    x=x_grid, y=kde(x_grid),
                    mode="lines", fill="tozeroy",
                    line=dict(color=PRIMARY, width=2),
                    fillcolor="rgba(124, 42, 131, 0.15)",
                    hovertemplate="Age: %{x:.0f}<br>Density: %{y:.4f}<extra></extra>",
                ))
            except Exception:
                if data.get("kde_x"):
                    fig.add_trace(go.Scatter(
                        x=data["kde_x"], y=data["kde_y"],
                        mode="lines", fill="tozeroy",
                        line=dict(color=PRIMARY, width=2),
                        fillcolor="rgba(124, 42, 131, 0.15)",
                        hovertemplate="Age: %{x:.0f}<br>Density: %{y:.4f}<extra></extra>",
                    ))
        y_title = "Density"
    else:
        bin_width = max(1, min(10, round(1 + (bw_pct / 100) * 9)))
        if per_site:
            for dept, dept_vals in by_dept.items():
                color = DEPARTMENT_COLORS.get(dept, CHART_COLORWAY[0])
                fig.add_trace(go.Histogram(
                    x=dept_vals, name=dept,
                    xbins=dict(start=0, end=110, size=bin_width),
                    marker_color=color, opacity=0.7,
                    hovertemplate=f"{dept}<br>Age: %{{x}}<br>Count: %{{y}}<extra></extra>",
                ))
            fig.update_layout(barmode="overlay")
        else:
            fig.add_trace(go.Histogram(
                x=data["values"],
                xbins=dict(start=0, end=110, size=bin_width),
                marker_color=PRIMARY,
                hovertemplate="Age: %{x}<br>Count: %{y}<extra></extra>",
            ))
        y_title = "Patients"

    # Median vertical line. Annotation sits INSIDE the plot area (just below
    # the top) so the chart can use the same tight top margin as top-cities /
    # gender and their x-axis baselines stay aligned across the row.
    # PRIMARY is registered with 02_theme.js's brand-color remap: stays
    # #7C2A83 in light, swaps to #CD8AD0 (bumped) in dark.
    med = data["median"]
    fig.add_vline(x=med, line_dash="dash", line_color=PRIMARY)
    fig.add_annotation(
        x=med, y=1.06, yref="paper",
        text=f"Median: {med:.0f}", showarrow=False,
        font=dict(size=11, color=PRIMARY),
        yanchor="top", xanchor="center",
    )

    apply_default_layout(fig)
    xaxis_title = (
        f"Age (years)  (n={data['n']:,}  Mean: {data['mean']:.0f}  "
        f"IQR: {data['p25']:.0f}\u2013{data['p75']:.0f})"
    )
    if PHI_MODE:
        xaxis_title += "   \u2014 ages 90+ reported as 90"
    fig.update_layout(
        height=380,
        xaxis_title=xaxis_title,
        yaxis_title=y_title,
        # Matches top-cities + gender margins so all three x-axis baselines
        # align along the row. Extra top room for the "Median: N" annotation.
        margin=dict(l=48, r=16, t=22, b=6),
        showlegend=per_site,
        legend=dict(
            orientation="h", yanchor="bottom", y=1.02,
            xanchor="left", x=0,
        ),
    )
    return fig


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
    Input("patients-map-reset", "n_clicks"),
    Input("global-theme-store", "data"),
)
def update_map(geo_data, selected_dept, departments, show_flows, region, min_patients, _reset, theme):
    """Build the Mapbox map from geocoded data in the store."""
    # In PHI mode the map card is hidden via CSS, but the dcc.Graph still
    # exists in the DOM. Building a Mapbox figure here triggers a Plotly +
    # Mapbox-GL race ("Style is not done loading") that the React error
    # boundary catches, freezing the page. Return a bare empty figure (no
    # mapbox layer) so the Graph stays inert.
    if PHI_MODE:
        return go.Figure()
    map_style = "dark" if theme == "dark" else MAPBOX_STYLE
    # Re-fit when view controls change; preserve zoom on data refresh / flow toggle
    _preserve = {"patients-store-geo", "patients-flow-toggle", "global-theme-store"}
    triggered = ctx.triggered_id
    if triggered and triggered not in _preserve:
        reset_rev = f"{region}-{selected_dept}-{departments}-{min_patients}-{_reset}"
    else:
        reset_rev = "patients-map"

    if not geo_data:
        fig = go.Figure()
        fig.update_layout(
            mapbox=dict(
                accesstoken=MAPBOX_TOKEN, style=map_style,
                center=MAPBOX_CENTER, zoom=MAPBOX_ZOOM,
            ),
            height=700,
            margin=dict(l=0, r=0, t=0, b=0),
            paper_bgcolor="rgba(0,0,0,0)",
            showlegend=False,
            uirevision=reset_rev,
        )
        return fig

    geo_df = pd.DataFrame(geo_data)
    return _build_patient_map(
        geo_df, departments,
        selected_dept=selected_dept,
        show_flows=show_flows,
        region=region,
        min_patients=min_patients or 1,
        uirevision=reset_rev,
        map_style=map_style,
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


