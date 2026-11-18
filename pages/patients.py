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
from utils.diagnosis_categories import (
    CATEGORIES as DX_CATEGORIES,
    build_code_to_category,
    primary_category,
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
    prepare_patient_point_data,
    trigger_patient_address_geocode,
    patient_geocode_progress,
)
from utils.address_match import reference_available as address_reference_available


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
                    dmc.Tooltip(
                        label="Seen: last appointment in the date range. "
                              "Upcoming: patients with a scheduled consult "
                              "(NextConsult), regardless of the date range. "
                              "All: both.",
                        position="bottom",
                        multiline=True,
                        w=260,
                        children=dmc.SegmentedControl(
                            id="patients-filter-status",
                            data=[
                                {"value": "seen", "label": "Seen"},
                                {"value": "all", "label": "All"},
                                {"value": "upcoming", "label": "Upcoming"},
                            ],
                            value="seen",
                            size="xs",
                        ),
                    ),
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

    for col in ["FirstAppointment", "LastAppointment", "DateOfBirth", "NextConsult"]:
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
                                dmc.Tooltip(
                                    label="Address: one dot per home (matched locally to county address points / parcels). "
                                          "ZIP: one dot per ZIP centroid.",
                                    position="bottom",
                                    multiline=True,
                                    w=220,
                                    children=dmc.SegmentedControl(
                                        id="patients-map-precision",
                                        data=[
                                            {"label": "Address", "value": "exact"},
                                            {"label": "ZIP", "value": "zip"},
                                        ],
                                        value="exact",
                                        size="xs",
                                        persistence=True,
                                        persistence_type="local",
                                    ),
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
                dmc.Alert(
                    id="patients-addr-geocode-status",
                    children="",
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

        # Age by diagnosis: trend over time (full history) + distribution
        # for the page date range. The New / All toggle drives both.
        dmc.Grid(
            gutter=16,
            children=[
                dmc.GridCol(
                    span={"base": 12, "md": 6},
                    children=chart_card(
                        "patients-chart-age-dx",
                        "Age at Treatment by Diagnosis",
                        chart_types=[
                            {"value": "line", "label": "Line"},
                            {"value": "bar", "label": "Bar"},
                        ],
                        chart_type_default="line",
                        show_smooth=False,
                        show_grouping=False,
                        settings_id="patients-age-dx",
                        extra_controls=[
                            dmc.Tooltip(
                                label="New: each patient once per diagnosis, at their "
                                      "first course for it. All: every patient treated "
                                      "in the period, including retreatment. Applies to "
                                      "both age-by-diagnosis charts.",
                                position="bottom", multiline=True, w=260,
                                children=dmc.SegmentedControl(
                                    id="patients-age-dx-basis",
                                    data=[
                                        {"value": "new", "label": "New"},
                                        {"value": "all", "label": "All"},
                                    ],
                                    value="new",
                                    size="xs",
                                ),
                            ),
                        ],
                        extra_settings=[
                            dmc.MultiSelect(
                                id="patients-age-dx-diagnoses",
                                label="Diagnoses",
                                data=[{"value": c, "label": c} for c in DX_CATEGORIES],
                                value=[],
                                placeholder="Top 5 by volume",
                                clearable=True,
                                searchable=True,
                                size="xs",
                                maxValues=8,
                                comboboxProps={"withinPortal": False},
                                mb="xs",
                            ),
                            dmc.Text("Statistic", size="xs", fw=500, mb=4),
                            dmc.SegmentedControl(
                                id="patients-age-dx-stat",
                                data=[
                                    {"value": "median", "label": "Median"},
                                    {"value": "mean", "label": "Mean"},
                                ],
                                value="median",
                                size="xs",
                                fullWidth=True,
                                mb="xs",
                            ),
                            dmc.Text("Period", size="xs", fw=500, mb=4),
                            dmc.SegmentedControl(
                                id="patients-age-dx-period",
                                data=[
                                    {"value": "Y", "label": "Year"},
                                    {"value": "Q", "label": "Quarter"},
                                ],
                                value="Q",
                                size="xs",
                                fullWidth=True,
                                mb="xs",
                            ),
                        ],
                    ),
                ),
                dmc.GridCol(
                    span={"base": 12, "md": 6},
                    children=chart_card(
                        "patients-chart-age-dxdist",
                        "Age Distribution by Diagnosis",
                        chart_types=None,
                        show_smooth=False,
                        show_grouping=False,
                        show_settings=True,
                        settings_id="patients-age-dxdist",
                    ),
                ),
            ],
        ),

        # Stores
        dcc.Store(id="patients-store-age-dx", data=None),
        dcc.Store(id="patients-store-geo", data=None),
        dcc.Store(id="patients-store-points", data=None),
        dcc.Store(id="patients-addr-geocode-tick", data=0),
        dcc.Store(id="patients-store-age-dist", data=None),
        dcc.Store(id="patients-map-selection", data=None),

        # Intervals
        dcc.Interval(id="patients-interval", interval=300_000, n_intervals=0, max_intervals=0),  # fires once on mount; no background refresh (daily data + global refresh button)
        dcc.Interval(
            id="patients-geocode-check", interval=5_000,
            n_intervals=0, max_intervals=120,
        ),
        # Polls the background patient-address geocode; enabled only while
        # it is running (see update_patients / _poll_addr_geocode).
        dcc.Interval(
            id="patients-addr-geocode-check", interval=5_000,
            n_intervals=0, disabled=True,
        ),
    ],
)

register_chart_callbacks([
    ("patients-age", "patients-chart-age-dist"),
    {"sid": "patients-age-dx", "gid": "patients-chart-age-dx", "store_id": None,
     "show_smooth": False, "show_grouping": False},
    {"sid": "patients-age-dxdist", "gid": "patients-chart-age-dxdist", "store_id": None,
     "show_smooth": False, "show_grouping": False},
])


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


def _apply_status_filter(df, slider_val, status):
    """Seen / Upcoming / All patient selection.

    seen     — LastAppointment within the date range (the original behavior)
    upcoming — any patient with a scheduled NextConsult; the date range is
               ignored (it only spans past months)
    all      — union of the two
    """
    status = status or "seen"
    has_next = (df["NextConsult"].notna() if "NextConsult" in df.columns
                else pd.Series(False, index=df.index))
    if status == "upcoming":
        return df[has_next]
    seen = _apply_date_filter(df, slider_val, None)
    if status == "all":
        return df[df.index.isin(seen.index) | has_next]
    return seen


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
    # New patients with only a scheduled consult have no appointment dates
    # yet — use the consult date so they keep an age.
    if "NextConsult" in df.columns:
        ref_date = ref_date.fillna(df["NextConsult"])

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

def _build_kpis(df, geo_df, status="seen"):
    """Build KPI cards: totals + per-department patient counts."""
    total_patients = (
        df["PatientId"].nunique() if "PatientId" in df.columns else len(df)
    )
    total_detail = None
    if status == "all" and "NextConsult" in df.columns:
        n_up = df.loc[df["NextConsult"].notna(), "PatientId"].nunique()
        total_detail = f"({n_up:,} upcoming)"

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
                "Upcoming Consults" if status == "upcoming" else "Total Patients",
                f"{total_patients:,}",
                value_detail=total_detail,
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

def _vector_arcs(from_lat, from_lon, to_lat, to_lon, n=6, curvature=0.2):
    """Quadratic-bezier arcs from many origins to one destination.

    Vectorized twin of utils.geocoding.bezier_arc. Returns flat (lats, lons)
    lists with None separators between arcs, rounded to 5 decimals (~1 m) to
    keep the figure JSON small.
    """
    mid_lat = (from_lat + to_lat) / 2
    mid_lon = (from_lon + to_lon) / 2
    dlat = to_lat - from_lat
    dlon = to_lon - from_lon
    cos_lat = np.cos(np.radians(mid_lat))
    perp_lat = -dlon * cos_lat
    perp_lon = dlat / cos_lat
    plen = np.sqrt(perp_lat ** 2 + perp_lon ** 2)
    plen[plen == 0] = 1.0
    dist = np.sqrt(dlat ** 2 + (dlon * cos_lat) ** 2)
    ctrl_lat = mid_lat + perp_lat / plen * curvature * dist
    ctrl_lon = mid_lon + perp_lon / plen * curvature * dist
    t = np.linspace(0, 1, n)[None, :]
    lat = (1 - t) ** 2 * from_lat[:, None] + 2 * (1 - t) * t * ctrl_lat[:, None] + t ** 2 * to_lat
    lon = (1 - t) ** 2 * from_lon[:, None] + 2 * (1 - t) * t * ctrl_lon[:, None] + t ** 2 * to_lon
    sep = np.full((lat.shape[0], 1), np.nan)
    lat = np.hstack([np.round(lat, 5), sep]).ravel()
    lon = np.hstack([np.round(lon, 5), sep]).ravel()
    to_list = lambda a: [None if np.isnan(v) else float(v) for v in a]
    return to_list(lat), to_list(lon)


def _build_patient_map(
    geo_df, departments_filter, selected_dept=None,
    show_flows=True, region="pnw", min_patients=1,
    uirevision="patients-map",
    map_style=None,
    point_df=None,
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
        Minimum patient count at an origin to display it. In address mode
        this applies to the point's ZIP total (per department), so the
        slider still hides sparse areas rather than every single household.
    point_df : DataFrame or None
        Per-address points (local mode, Address precision). When given, dots
        are drawn at home coordinates, with per-home flow lines.
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

    # --- Per-address patient points (Address precision) ----------------------
    point_frames = {}   # dept -> plotted points, reused for per-home flow lines
    if (not phi_choropleth and render_depts and point_df is not None
            and not point_df.empty):
        zip_counts = {}
        if {"zip5", "Department", "patient_count"}.issubset(geo_df.columns):
            zip_counts = {
                (z, d): c for z, d, c in
                zip(geo_df["zip5"], geo_df["Department"], geo_df["patient_count"])
            }
        for dept in render_depts:
            pts = point_df[point_df["Department"] == dept]
            pts = pts[
                (pts["lat"].between(*lat_bounds))
                & (pts["lon"].between(*lon_bounds))
            ]
            if min_patients and min_patients > 1:
                keep = [
                    zip_counts.get((z, dept), 0) >= min_patients
                    for z in pts["zip5"]
                ]
                pts = pts[keep]
            if pts.empty:
                continue
            point_frames[dept] = pts
            color = DEPARTMENT_COLORS.get(dept, CHART_COLORWAY[0])
            for precise, sub in pts.groupby("precise"):
                hover = [
                    f"{city or 'Unknown'} ({z})<br>{dept}: {n:,} "
                    f"patient{'s' if n != 1 else ''}"
                    + ("" if precise else "<br><i>ZIP-level location</i>")
                    for city, z, n in zip(sub["primary_city"], sub["zip5"], sub["patient_count"])
                ]
                fig.add_trace(go.Scattermapbox(
                    lat=sub["lat"],
                    lon=sub["lon"],
                    mode="markers",
                    marker=dict(
                        size=[min(5 + 2 * (n - 1), 12) for n in sub["patient_count"]]
                        if precise else 7,
                        color=color,
                        opacity=0.65 if precise else 0.35,
                    ),
                    customdata=sub[["zip5", "primary_city"]].values.tolist(),
                    text=hover,
                    hoverinfo="text",
                    showlegend=False,
                ))

    # --- Patient bubbles (one trace per department) --------------------------
    if (not phi_choropleth and render_depts and not geo_df.empty and "lat" in geo_df.columns
            and (point_df is None or point_df.empty)):
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

    # --- Per-home flow lines (Address precision) -----------------------------
    # One faint, slightly curved line from every plotted home to its site.
    # Thousands of lines, so: few points per arc, rounded coords, one trace
    # per department, and no hover.
    if show_flows and point_frames:
        for dept, pts in point_frames.items():
            dept_coord = DEPT_COORDS.get(dept)
            if not dept_coord:
                continue
            far = (
                ((pts["lat"] - dept_coord[0]).abs() >= 0.01)
                | ((pts["lon"] - dept_coord[1]).abs() >= 0.01)
            )
            pts = pts[far]
            if pts.empty:
                continue
            lats, lons = _vector_arcs(
                pts["lat"].to_numpy(), pts["lon"].to_numpy(),
                dept_coord[0], dept_coord[1],
            )
            fig.add_trace(go.Scattermapbox(
                lat=lats, lon=lons, mode="lines",
                line=dict(width=0.7, color=DEPARTMENT_COLORS.get(dept, CHART_COLORWAY[0])),
                opacity=0.18,
                hoverinfo="skip",
                showlegend=False,
            ))

    # --- Curved flow lines (bundled arcs scaled by relative volume) ----------
    elif show_flows and render_depts and not geo_df.empty and "Department" in geo_df.columns:
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
    Output("patients-store-points", "data"),
    Output("patients-addr-geocode-status", "children"),
    Output("patients-addr-geocode-status", "style"),
    Output("patients-addr-geocode-check", "disabled"),
    Input("patients-interval", "n_intervals"),
    Input("patients-date-slider", "value"),
    Input("patients-filter-date-preset", "value"),
    Input("patients-filter-department", "value"),
    Input("patients-filter-age", "value"),
    Input("patients-age-ref", "value"),
    Input("patients-filter-status", "value"),
    Input("patients-map-precision", "value"),
    Input("patients-addr-geocode-tick", "data"),
    running=[
        (Output("patients-chart-top-cities-loading", "visible"), True, False),
        (Output("patients-chart-age-dist-loading", "visible"), True, False),
    ],
)
def update_patients(_n_interval, slider_val, date_preset,
                    departments, age_range, age_ref, status, precision, _geo_tick):
    """Update all Patients page components based on filters."""
    base = _update_patients_core(slider_val, departments, age_range, age_ref, status)
    *outs, df = base
    points, banner_text, banner_style, poll_disabled = _patient_points_payload(df, precision)
    # Address-geocode progress ticks only need the map points refreshed.
    if ctx.triggered_id in ("patients-addr-geocode-tick", "patients-map-precision"):
        outs = [no_update] * len(outs)
    return (*outs, points, banner_text, banner_style, poll_disabled)


_HIDDEN = {"display": "none"}


def _patient_points_payload(df, precision):
    """Per-address points for the map store + geocode banner state.

    Local (non-PHI) mode only. Points carry coordinates, ZIP, city, department
    and a count — no names, IDs, or street text.
    """
    if PHI_MODE or precision != "exact" or df is None or df.empty:
        return None, "", _HIDDEN, True
    pts, pending = prepare_patient_point_data(df)
    if pending:
        trigger_patient_address_geocode(pending)
    prog = patient_geocode_progress()
    store = pts.to_dict("records") if not pts.empty else None
    if prog["running"]:
        done, total = prog["done"], max(prog["total"], 1)
        text = (
            f"Matching {total:,} patient addresses to local county address "
            f"data. Homes show at their ZIP centroid until it finishes "
            f"(usually under a minute)."
        )
        return store, text, {}, False
    if pending and not address_reference_available():
        return store, ("Local address reference not built: showing ZIP centroids. "
                       "Run scripts/build_address_reference.py."), {}, True
    return store, "", _HIDDEN, True


def _update_patients_core(slider_val, departments, age_range, age_ref, status="seen"):
    df = _load_and_prepare()

    _empty = [kpi_card("—", "N/A")]
    _no_age = (_AGE_MIN, _AGE_MAX, _AGE_MARKS)

    # --- Empty data ---
    if df.empty:
        return _empty, None, None, empty_figure("No city data available"), {"display": "none"}, None, *_no_age, None

    # --- Apply date + department filters (before computing age range) ---
    df = _apply_status_filter(df, slider_val, status)
    if departments and "Department" in df.columns:
        df = df[df["Department"].isin(departments)]

    if df.empty:
        return _empty, None, None, empty_figure("No city data available"), {"display": "none"}, None, *_no_age, None

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
        return _empty, None, None, empty_figure("No city data available"), {"display": "none"}, None, age_lo, age_hi, age_marks, None

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
    kpis = _build_kpis(df, geo_df, status=status or "seen")

    # --- Top cities chart ---
    top_cities = _build_top_cities_bar(df)

    # Only clear map selection when the user changes a filter, not on interval ticks
    clear_selection = (
        None if ctx.triggered_id in (
            "patients-date-slider", "patients-filter-date-preset",
            "patients-filter-department", "patients-filter-age",
            "patients-age-ref", "patients-filter-status",
        )
        else no_update
    )
    return kpis, geo_store, age_dist_data, top_cities, status_style, clear_selection, age_lo, age_hi, age_marks, df


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


@callback(
    Output("patients-addr-geocode-tick", "data"),
    Input("patients-addr-geocode-check", "n_intervals"),
    State("patients-addr-geocode-tick", "data"),
    prevent_initial_call=True,
)
def _poll_addr_geocode(n, tick):
    """Refresh map points every ~30 s while geocoding, and once at the end."""
    prog = patient_geocode_progress()
    if not prog["running"] or (n or 0) % 6 == 0:
        return (tick or 0) + 1
    return no_update


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
    Input("patients-store-points", "data"),
    Input("patients-map-precision", "value"),
)
def update_map(geo_data, selected_dept, departments, show_flows, region, min_patients, _reset, theme,
               points_data, precision):
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
    _preserve = {"patients-store-geo", "patients-flow-toggle", "global-theme-store",
                 "patients-store-points", "patients-map-precision"}
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
    point_df = (
        pd.DataFrame(points_data)
        if precision == "exact" and points_data else None
    )
    return _build_patient_map(
        geo_df, departments,
        point_df=point_df,
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


# ---------------------------------------------------------------------------
# Age at treatment by diagnosis over time
#
# One row per (patient, diagnosis category, period): a patient treated for
# the same diagnosis twice in a period counts once, at their first course.
# Age is at the course's first treatment date (falls back to course start).
# Spans full history — the page date filter (which keys on appointment
# dates in the patient lookup) does not apply; the department filter does.
# ---------------------------------------------------------------------------

_AGE_DX_MIN_N = 5          # suppress period points with fewer patients
_AGE_DX_TOP_N = 5          # default selection when none is chosen
_AGE_DX_MIN_COVERAGE = 0.8  # min share of courses with a diagnosis code per period
_AGE_DX_WASHOUT_MONTHS = 12  # New-diagnosis view starts this long after coding begins


def _age_dx_colors():
    """Same per-category colors as the Diagnosis page."""
    from pages.diagnosis import _DIAG_COLORS
    return {c: _DIAG_COLORS[i % len(_DIAG_COLORS)] for i, c in enumerate(DX_CATEGORIES)}


_AGE_DX_BASE_MEMO = {"key": None, "val": None}


def _age_dx_base():
    """Coded courses with Age + Category, all sites, plus derived helpers.

    Returns dict(c, first, coverage, washout_start) or None. Memoized on the
    identity of the (TTL-cached) loader frames so slider drags don't redo the
    1 s+ join / categorization.
    """
    from data.loader import load_courses, load_diagnosis, load_patients

    try:
        courses = load_courses()
        raw_pts = load_patients()
    except Exception:
        return None
    key = (id(courses), id(raw_pts))
    if _AGE_DX_BASE_MEMO["key"] == key:
        return _AGE_DX_BASE_MEMO["val"]
    val = _build_age_dx_base(courses, load_diagnosis)
    _AGE_DX_BASE_MEMO.update(key=key, val=val)
    return val


def _build_age_dx_base(courses, load_diagnosis):
    pts = _load_and_prepare()
    if courses is None or courses.empty or pts.empty:
        return None

    cols = [c for c in ("PatientId", "CourseId", "CourseStartDate", "FirstTreatmentDate",
                        "DiagnosisCodes", "Department") if c in courses.columns]
    c = courses[cols].copy()
    # Department filter is applied after first-course detection (below), so a
    # patient's first course at another site still marks later ones as repeats.
    tx = c["FirstTreatmentDate"] if "FirstTreatmentDate" in c.columns else pd.Series(pd.NaT, index=c.index)
    c["TxDate"] = pd.to_datetime(tx, errors="coerce").fillna(
        pd.to_datetime(c.get("CourseStartDate"), errors="coerce")
    )
    c = c.dropna(subset=["TxDate"])
    # Diagnosis codes only populate courses from mid-2021 on (plus a partial
    # 2004 migration batch). Keep periods where >= 80% of courses carry a
    # code so sparse legacy periods don't plot as misleading lone points.
    has_dx = c["DiagnosisCodes"].notna()
    coverage = {
        per: has_dx.groupby(c["TxDate"].dt.to_period(per)).mean()
        for per in ("Y", "Q")
    }
    c = c[has_dx]
    if c.empty:
        return None

    # Age at treatment
    if "DateOfBirth" in pts.columns:
        dob = pts.drop_duplicates("PatientId").set_index("PatientId")["DateOfBirth"]
        c["Age"] = (c["TxDate"] - c["PatientId"].map(dob)).dt.days / 365.25
    elif "AgeAtLoad" in pts.columns:
        # PHI_MODE: DOB is dropped at build time. AgeAtLoad is integer age as
        # of the latest LastAppointment in the file (see sanitize rules), so
        # back-date it to the treatment date. ±0.5 yr; 90+ is capped at 90.
        ref = pts["LastAppointment"].max() if "LastAppointment" in pts.columns else pd.Timestamp.now()
        age_now = pts.drop_duplicates("PatientId").set_index("PatientId")["AgeAtLoad"]
        c["Age"] = (c["PatientId"].map(age_now) + 0.5) - (ref - c["TxDate"]).dt.days / 365.25
    else:
        return None
    c = c[c["Age"].between(0, 110)]

    try:
        diag_df = load_diagnosis()
    except Exception:
        diag_df = None
    c2c = build_code_to_category(diag_df)
    uniq = c["DiagnosisCodes"].unique()
    cat_map = {v: primary_category(v, c2c) for v in uniq}
    c["Category"] = c["DiagnosisCodes"].map(cat_map)
    c = c[c["Category"].isin(DX_CATEGORIES)]
    if c.empty:
        return None

    c = c.sort_values("TxDate")

    # "New": each patient once per diagnosis category, at their first coded
    # course for it (across all sites). A later second cancer of a different
    # category still counts; a retreatment of the same category does not.
    first = c.drop_duplicates(["PatientId", "Category"], keep="first")
    # Washout: codes start ~Q4 2021, so a retreatment of a pre-coding cancer
    # would look new. Begin the New view 12 months after coding coverage starts.
    good_q = coverage["Q"][coverage["Q"] >= _AGE_DX_MIN_COVERAGE].index
    washout_start = (
        good_q.min().start_time + pd.DateOffset(months=_AGE_DX_WASHOUT_MONTHS)
        if len(good_q) else None
    )
    return {"c": c, "first": first, "coverage": coverage, "washout_start": washout_start}


def _prepare_age_dx_data(departments):
    """Aggregate age-at-treatment stats per (period, category). Returns dict."""
    base = _age_dx_base()
    if not base:
        return None
    c, first = base["c"], base["first"]
    coverage, washout_start = base["coverage"], base["washout_start"]
    out = {"rows": [], "top": []}

    def _dept(frame):
        if departments and "Department" in frame.columns:
            return frame[frame["Department"].isin(departments)]
        return frame

    sources = (("all", _dept(c)), ("new", _dept(first)))
    for basis, src, period in [(b, f, per) for b, f in sources for per in ("Y", "Q")]:
        pr = src["TxDate"].dt.to_period(period)
        good = set(coverage[period][coverage[period] >= _AGE_DX_MIN_COVERAGE].index)
        work = src.assign(Period=pr)
        work = work[work["Period"].isin(good)]
        if basis == "new" and washout_start is not None:
            work = work[work["Period"].map(lambda p_: p_.start_time >= washout_start)]
        if work.empty:
            continue
        per_cat = work.drop_duplicates(["PatientId", "Category", "Period"])
        overall = work.drop_duplicates(["PatientId", "Period"]).assign(Category="All Diagnoses")
        for frame in (per_cat, overall):
            g = frame.groupby(["Period", "Category"])["Age"]
            agg = pd.DataFrame({
                "median": g.median(), "mean": g.mean(),
                "q1": g.quantile(0.25), "q3": g.quantile(0.75), "n": g.size(),
            }).reset_index()
            for r in agg.itertuples(index=False):
                label = str(r.Period.year) if period == "Y" else f"{r.Period.year} Q{r.Period.quarter}"
                out["rows"].append({
                    "basis": basis,
                    "period": period,
                    "x": r.Period.start_time.strftime("%Y-%m-%d"),
                    "label": label,
                    "cat": r.Category,
                    "median": round(float(r.median), 1),
                    "mean": round(float(r.mean), 1),
                    "q1": round(float(r.q1), 1),
                    "q3": round(float(r.q3), 1),
                    "n": int(r.n),
                })
    out["top"] = _dept(first)["Category"].value_counts().head(_AGE_DX_TOP_N).index.tolist()
    return out


@callback(
    Output("patients-store-age-dx", "data"),
    Input("patients-interval", "n_intervals"),
    Input("patients-filter-department", "value"),
)
def _update_age_dx_store(_n, departments):
    return _prepare_age_dx_data(departments)


@callback(
    Output("patients-chart-age-dx", "figure"),
    Input("patients-store-age-dx", "data"),
    Input("patients-age-dx-diagnoses", "value"),
    Input("patients-age-dx-stat", "value"),
    Input("patients-age-dx-period", "value"),
    Input("patients-age-dx-basis", "value"),
    Input("patients-age-dx-settings-type", "value"),
)
def _update_age_dx_chart(data, selected, stat, period, basis, chart_type):
    if not data or not data.get("rows"):
        return empty_figure("No diagnosis data for selected filters")
    return _build_age_dx_fig(data, selected, stat or "median", period or "Q",
                             basis or "new", chart_type or "line")


def _build_age_dx_fig(data, selected, stat, period, basis="new", chart_type="line"):
    df = pd.DataFrame(data["rows"])
    df = df[(df["basis"] == basis) & (df["period"] == period) & (df["n"] >= _AGE_DX_MIN_N)]
    n_label = "New patients" if basis == "new" else "Patients"
    cats = list(selected) if selected else list(data.get("top", []))
    if df.empty or not cats:
        return empty_figure("No diagnosis data for selected filters")

    colors = _age_dx_colors()
    stat_label = "Median" if stat == "median" else "Mean"
    if chart_type == "bar":
        return _build_age_dx_bar(df, cats, stat, stat_label, n_label, colors)
    fig = go.Figure()

    # Reference: all diagnoses combined
    ref = df[df["cat"] == "All Diagnoses"].sort_values("x")
    if not ref.empty:
        fig.add_trace(go.Scatter(
            x=ref["x"], y=ref[stat], mode="lines", name="All Diagnoses",
            line=dict(color="#9CA3AF", width=2, dash="dash"),
            customdata=ref[["label", "n", "q1", "q3"]].values.tolist(),
            hovertemplate=(
                "All Diagnoses, %{customdata[0]}<br>"
                + stat_label + " age: %{y:.1f}<br>"
                "IQR: %{customdata[2]:.0f}–%{customdata[3]:.0f}<br>"
                + n_label + ": %{customdata[1]:,}<extra></extra>"
            ),
        ))

    for cat in cats:
        d = df[df["cat"] == cat].sort_values("x")
        if d.empty:
            continue
        color = colors.get(cat, PRIMARY)
        if len(cats) == 1:
            # Single diagnosis: show the interquartile band
            fig.add_trace(go.Scatter(
                x=list(d["x"]) + list(d["x"])[::-1],
                y=list(d["q3"]) + list(d["q1"])[::-1],
                fill="toself", fillcolor=_hex_rgba(color, 0.15),
                line=dict(width=0), hoverinfo="skip", showlegend=True,
                name="Middle 50% of ages",
            ))
        fig.add_trace(go.Scatter(
            x=d["x"], y=d[stat], mode="lines+markers", name=cat,
            line=dict(color=color, width=2.5),
            marker=dict(size=5, color=color),
            customdata=d[["label", "n", "q1", "q3"]].values.tolist(),
            hovertemplate=(
                cat + ", %{customdata[0]}<br>"
                + stat_label + " age: %{y:.1f}<br>"
                "IQR: %{customdata[2]:.0f}–%{customdata[3]:.0f}<br>"
                + n_label + ": %{customdata[1]:,}<extra></extra>"
            ),
        ))

    apply_default_layout(
        fig,
        yaxis=dict(title=f"{stat_label} Age at Treatment"),
        xaxis=dict(title=None),
        hovermode="closest",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
    )
    return fig


def _age_dx_hover(name, stat_label, n_label):
    return (
        name + ", %{customdata[0]}<br>"
        + stat_label + " age: %{y:.1f}<br>"
        "IQR: %{customdata[2]:.0f}–%{customdata[3]:.0f}<br>"
        + n_label + ": %{customdata[1]:,}<extra></extra>"
    )


def _build_age_dx_bar(df, cats, stat, stat_label, n_label, colors):
    """Grouped bars per period (zero baseline — ages differ by a few years,
    so value labels carry the comparison when bars are few enough)."""
    order = (
        df[["x", "label"]].drop_duplicates().sort_values("x")["label"].tolist()
    )
    fig = go.Figure()
    plotted = [c for c in cats if not df[df["cat"] == c].empty]
    n_bars = sum(len(df[df["cat"] == c]) for c in plotted)
    show_text = n_bars <= 40
    for cat in plotted:
        d = df[df["cat"] == cat].sort_values("x")
        color = colors.get(cat, PRIMARY)
        fig.add_trace(go.Bar(
            x=d["label"], y=d[stat], name=cat,
            marker_color=color,
            text=[f"{v:.0f}" for v in d[stat]] if show_text else None,
            textposition="outside", textfont=dict(size=10), cliponaxis=False,
            customdata=d[["label", "n", "q1", "q3"]].values.tolist(),
            hovertemplate=_age_dx_hover(cat, stat_label, n_label),
        ))
    ref = df[df["cat"] == "All Diagnoses"].sort_values("x")
    if not ref.empty:
        fig.add_trace(go.Scatter(
            x=ref["label"], y=ref[stat], mode="lines+markers", name="All Diagnoses",
            line=dict(color="#9CA3AF", width=2, dash="dash"),
            marker=dict(size=5, color="#9CA3AF"),
            customdata=ref[["label", "n", "q1", "q3"]].values.tolist(),
            hovertemplate=_age_dx_hover("All Diagnoses", stat_label, n_label),
        ))
    ymax = df[df["cat"].isin(plotted + ["All Diagnoses"])][stat].max()
    apply_default_layout(
        fig,
        barmode="group",
        bargap=0.25,
        yaxis=dict(title=f"{stat_label} Age at Treatment", range=[0, ymax * 1.12]),
        xaxis=dict(title=None, type="category", categoryorder="array", categoryarray=order),
        hovermode="closest",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
    )
    return fig


# ---------------------------------------------------------------------------
# Age distribution by diagnosis (page date range)
# ---------------------------------------------------------------------------

@callback(
    Output("patients-chart-age-dxdist", "figure"),
    Input("patients-interval", "n_intervals"),
    Input("patients-date-slider", "value"),
    Input("patients-filter-department", "value"),
    Input("patients-age-dx-basis", "value"),
)
def _update_age_dxdist(_n, slider_val, departments, basis):
    base = _age_dx_base()
    if not base:
        return empty_figure("No diagnosis data available")
    groups = _age_dxdist_groups(base, slider_val, departments, basis or "new")
    if not groups:
        return empty_figure("No diagnosis data for selected filters")
    return _build_age_box(groups, basis or "new")


def _age_dxdist_groups(base, slider_val, departments, basis):
    """[(category, ages ndarray)] for the date range, sorted by median age
    ascending, with "All Diagnoses" last. Each patient counts once per
    diagnosis (New: at their first course for it; All: their first course
    for it inside the range)."""
    start, end = _get_date_range(slider_val, None)
    src = base["first"] if basis == "new" else base["c"]
    if departments and "Department" in src.columns:
        src = src[src["Department"].isin(departments)]
    src = src[(src["TxDate"] >= start) & (src["TxDate"] <= end)]
    if basis == "new" and base["washout_start"] is not None:
        src = src[src["TxDate"] >= base["washout_start"]]
    if src.empty:
        return []
    per_cat = src.drop_duplicates(["PatientId", "Category"])
    groups = []
    for cat, g in per_cat.groupby("Category"):
        if len(g) >= _AGE_DX_MIN_N:
            groups.append((cat, g["Age"].to_numpy()))
    if not groups:
        return []
    groups.sort(key=lambda t: np.median(t[1]))
    groups.append(("All Diagnoses", src.drop_duplicates("PatientId")["Age"].to_numpy()))
    return groups


def _age_dx_group_label(cat, ages):
    return f"{cat} ({len(ages):,})"


def _build_age_box(groups, basis):
    colors = _age_dx_colors()
    n_label = "New patients" if basis == "new" else "Patients"
    fig = go.Figure()
    for cat, ages in groups:
        color = colors.get(cat, "#9CA3AF")
        q1, med, q3 = np.percentile(ages, [25, 50, 75])
        fig.add_trace(go.Box(
            x=ages, name=_age_dx_group_label(cat, ages), orientation="h",
            marker_color=color, line=dict(width=1.5),
            fillcolor=_hex_rgba(color, 0.35),
            boxpoints=False,
            hoverinfo="skip",
        ))
        # Invisible median point carries a readable hover
        fig.add_trace(go.Scatter(
            x=[med], y=[_age_dx_group_label(cat, ages)], mode="markers",
            marker=dict(size=14, color="rgba(0,0,0,0)"),
            hovertemplate=(
                f"{cat}<br>Median age: {med:.1f}<br>"
                f"Middle 50%: {q1:.0f}–{q3:.0f}<br>"
                f"{n_label}: {len(ages):,}<extra></extra>"
            ),
            showlegend=False,
        ))
    apply_default_layout(
        fig,
        showlegend=False,
        xaxis=dict(title="Age at Treatment", range=[0, 100]),
        yaxis=dict(title=None, automargin=True),
        hovermode="closest",
        margin=dict(l=10, r=10, t=10, b=40),
    )
    return fig


def _hex_rgba(hex_color, alpha):
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return f"rgba({r},{g},{b},{alpha})"

