"""Referrals page — conversion funnel, lead times, referring sources, and trends."""

import re
from pathlib import Path
import dash
import dash_mantine_components as dmc
import dash_ag_grid as dag
from dash import callback, Input, Output, State, dcc, html, clientside_callback, ClientsideFunction, ctx
from dash_iconify import DashIconify
import plotly.graph_objects as go
import pandas as pd
import numpy as np
from datetime import timedelta

from config.settings import (
    DEPARTMENTS, DEPARTMENT_COLORS, CHART_COLORWAY, PRIMARY,
    DEFAULT_LAYOUT, FONT_FAMILY, SEMANTIC_COLORS, NEUTRAL, CHART_PAPER_HEIGHT,
    DEFAULT_COLUMN_DEFS, DEFAULT_GRID_OPTIONS, DEFAULT_GRID_STYLE, DEFAULT_GRID_CLASS, ABMS_SPECIALTIES,
    PRIOR_PERIOD_COLORS,
    MAPBOX_TOKEN, MAPBOX_CENTER, MAPBOX_ZOOM, MAPBOX_STYLE,
)
from utils.geocoding import (
    normalize_zip, geocode_addresses, _addr_geocode_key,
    get_department_patient_flows, bezier_arc, DEPT_COORDS,
)
from components.ai_settings import ai_settings_panel, register_ai_settings_callbacks
from components.diagnosis_filter import diagnosis_accordion, register_diagnosis_callbacks
from components.filter_bar import department_chips
from components.kpi_card import kpi_card, kpi_placeholder, create_sparkline
from components.chart_card import chart_card, register_chart_callbacks
from components.chart_settings import chart_settings_popover
from components.detail_table import detail_table
from components.outlier_panel import outlier_panel, register_outlier_callbacks
from components.phi import apply_phi_grid_rules
from utils.charts import apply_default_layout, empty_figure, dept_color, color_for_index
from utils.tables import sanitize_for_grid
from utils.permissions import can_see_manager_modals
from utils.diagnosis_categories import (
    build_code_to_category, CATEGORIES as BODY_SYSTEMS,
    SUBCATEGORIES as DIAG_SUBCATEGORIES, ALL_SUBCATEGORIES,
    get_all_subcategory_entries,
)
from utils.date_slider import (
    month_idx, idx_to_date, MAX_IDX, DEFAULT_SLIDER, SLIDER_MARKS,
    preset_to_slider_val, preset_to_exact_dates,
)

dash.register_page(__name__, path="/referrals", name="Referrals", order=12)

PAGE_ID = "referrals"
_DEFAULT_DATE_PRESET = "12mo"

# Outlier caps for duration computations (days)
_CAP_CREATED_TO_SCHEDULED = 14   # > 2 weeks = outlier
_CAP_SCHEDULED_TO_VISIT = 28     # > 4 weeks = outlier
_CAP_TOTAL = _CAP_CREATED_TO_SCHEDULED + _CAP_SCHEDULED_TO_VISIT

# Dimension trend/comparison chart height
_DIM_RIDGE_HEIGHT = 720


# ---------------------------------------------------------------------------
# Diagnosis Categorisation
# ---------------------------------------------------------------------------
# Delegated to utils.diagnosis_categories.categorise_referral, which is
# shared with the Med-Onc Cross-Referrals page. Cascade:
#   1. ICD-10/ICD-9 code from "Diagnoses" → taxonomy lookup
#   2. Free-text regex on "Rfl Prim Dx"
#   3. Free-text regex on "Diagnoses"
#   4. Free-text regex on "Onc Dx"  (patient-level fallback)
#   5. "Other"
# Both pages stay symmetric — a given referral type lands in the same bucket
# whether it's to med-onc or rad-onc.

# ICD regexes (still used below for a separate analytic codepath that pulls
# every ICD code out of a row, not just the first one).
_ICD10_RE = re.compile(r"([A-Z]\d[0-9A-Z](?:\.[0-9A-Z]+)?)\s*\(ICD-10")
_ICD9_RE = re.compile(r"(\d{3}(?:\.\d+)?)\s*\(ICD-9")

from data.loader import load_diagnosis as _load_diag
from utils.diagnosis_categories import (
    categorise_referral as _categorise_referral,
    categorise_free_text as _categorise_text,
)
_DIAG_C2C: dict[str, str] = build_code_to_category(_load_diag())


def _categorise_diagnosis(diagnoses_text, prim_dx_text=None, onc_dx_text=None):
    """Thin wrapper — delegates to the shared cascade helper."""
    return _categorise_referral(
        diagnoses=diagnoses_text,
        rfl_prim_dx=prim_dx_text,
        onc_dx=onc_dx_text,
        c2c=_DIAG_C2C,
    )


# ---------------------------------------------------------------------------
# Department mapping from Referred-by Department
# ---------------------------------------------------------------------------

_DEPT_MAP_PATTERNS = [
    ("Lacey",     re.compile(r"LACEY", re.I)),
    ("Centralia", re.compile(r"CENTRALIA", re.I)),
    ("Aberdeen",  re.compile(r"ABERDEEN", re.I)),
]


def _map_to_our_dept(ref_dept):
    """Map a department string (typically 'Referred to Department') to our
    three sites — Lacey / Centralia / Aberdeen — or None if no match.

    Always map from 'Referred to Department' for site attribution: that column
    records WHICH RadiantCare site will see the patient (~100% mapping rate).
    'Referred by Department' is the EXTERNAL referring office and only
    coincidentally contains our site names (~30% mapping rate).
    """
    if pd.isna(ref_dept):
        return None
    s = str(ref_dept)
    for dept, pat in _DEPT_MAP_PATTERNS:
        if pat.search(s):
            return dept
    return None


# ---------------------------------------------------------------------------
# Payor helpers
# ---------------------------------------------------------------------------

_PAYOR_MODE_TOGGLE = [
    {"value": "actual", "label": "Actual"},
    {"value": "broad", "label": "Broad"},
    {"value": "phdsc", "label": "PHDSC"},
]

_BROAD_PAYOR_CATEGORIES = [
    "Medicare", "Medicaid", "Private", "Military/VA",
    "Workers Comp", "Tribal/IHS", "Self Pay", "Other/Unknown",
]

_PHDSC_PAYOR_CATEGORIES = [
    "1 - Medicare", "2 - Medicaid/CHIP", "3 - Other Govt",
    "4 - Corrections", "5 - Private", "6 - BCBS",
    "8 - No Payment", "9 - Other",
]

_PAYOR_ID_RE = re.compile(r"\s*\[\d+\]\s*$")


def _extract_primary_payor(val):
    """Extract the primary payor name from the raw `Payer` value.

    The Excel export packs multiple payors as newline-separated entries,
    each suffixed with a bracketed ID like ``[1078]``. The first line is
    the primary insurer.
    """
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    s = str(val).strip()
    if not s:
        return None
    first = s.split("\n")[0].strip()
    cleaned = _PAYOR_ID_RE.sub("", first).strip()
    return cleaned or None


def _broad_payor_fallback(name):
    """Map insurer name → broad category (used when no DB mapping exists)."""
    if not isinstance(name, str) or not name or name == "Unknown":
        return "Other/Unknown"
    nl = name.lower()
    if "medicare" in nl:
        return "Medicare"
    if any(kw in nl for kw in (
        "medicaid", "apple health", "dshs", "molina",
        "amerigroup medicaid", "coordinated care medicaid",
        "community hlth plan chpw medicaid",
        "wellpoint wa medicaid", "united healthcare medicaid",
    )):
        return "Medicaid"
    if any(kw in nl for kw in (
        "tricare", "champva", "veterans admin", "veteran",
        "us family healthplan",
    )):
        return "Military/VA"
    if any(kw in nl for kw in (
        "labor and ind", "dept of labor", "workers comp", " wc",
        "corvel", "sedgwick",
    )):
        return "Workers Comp"
    if any(kw in nl for kw in (
        "indian health", "quinault", "chehalis", "nisqually",
        "tongas",
    )):
        return "Tribal/IHS"
    if "self pay" in nl:
        return "Self Pay"
    if any(kw in nl for kw in (
        "correction", "mcneil island", "stafford creek",
        "thurston county jail",
    )):
        return "Other/Unknown"
    return "Private"


def _payor_mode_groups(series, mode, mapping):
    """Return Series mapping each payor name to its display group under *mode*."""
    s = series.fillna("Unknown")
    if mode == "broad":
        def _r(name):
            if name in mapping and mapping[name].get("broad_category"):
                return mapping[name]["broad_category"]
            return _broad_payor_fallback(name)
        return s.apply(_r)
    if mode == "phdsc":
        def _r(name):
            if name in mapping and mapping[name].get("phdsc_category"):
                cat = str(mapping[name]["phdsc_category"]).strip()
                # cat may be a bare digit ("1") or the full label ("1 - Medicare")
                digit = cat.split(" ")[0].split("-")[0].strip()
                for pc in _PHDSC_PAYOR_CATEGORIES:
                    if pc.split(" ")[0] == digit:
                        return pc
                return "9 - Other"
            return "9 - Other"
        return s.apply(_r)
    # actual — standardized payor name (fallback to raw)
    def _r(name):
        if name in mapping and mapping[name].get("standardized_payor"):
            return mapping[name]["standardized_payor"]
        return name
    return s.apply(_r)


def _get_payor_mapping():
    try:
        from data.reviews_db import get_payor_mapping_dict
        return get_payor_mapping_dict()
    except Exception:
        return {}


def _apply_payor_filter(df, selected, mode):
    """Filter df to rows whose primary payor falls in *selected* under *mode*."""
    if not selected or "Payer" not in df.columns:
        return df
    mapping = _get_payor_mapping()
    primary = df["Payer"].apply(_extract_primary_payor)
    grp = _payor_mode_groups(primary, mode or "broad", mapping)
    return df[grp.isin(selected)]


def _chip_dropdown(name, chip_id, multiple=True, children=None):
    """Reusable chip-dropdown: button + clear + floating panel."""
    return html.Div(
        children=[
            html.Div(
                children=[
                    dmc.Button(
                        name,
                        id=f"{PAGE_ID}-{chip_id}-trigger",
                        variant="default",
                        size="sm",
                        rightSection=DashIconify(icon="mdi:chevron-down", width=14),
                    ),
                    dmc.ActionIcon(
                        DashIconify(icon="mdi:close-circle", width=18),
                        id=f"{PAGE_ID}-{chip_id}-clear",
                        variant="subtle",
                        color="gray",
                        size="sm",
                        className="wf-filter-clear-btn",
                    ),
                ],
                style={"position": "relative", "display": "inline-block"},
            ),
            dmc.Paper(
                id=f"{PAGE_ID}-{chip_id}-panel",
                children=children or [],
                p="xs",
                shadow="md",
                withBorder=True,
                radius="md",
                className="wf-chip-dropdown",
                style={"display": "none"},
            ),
        ],
        style={"position": "relative", "display": "inline-block"},
    )


# ---------------------------------------------------------------------------
# Status grouping
# ---------------------------------------------------------------------------

_STATUS_GROUPS = {
    "Closed":                     "Closed",
    "Pending Review":             "Pending",
    "Authorized":                 "Authorized",
    "Authorization not Required": "Auth Not Req",
    "Canceled":                   "Canceled",
    "Denied":                     "Denied",
    "Open":                       "Open",
}


# ---------------------------------------------------------------------------
# Filter Bar
# ---------------------------------------------------------------------------

_STATUS_OPTIONS = [
    {"value": "Closed", "label": "Closed"},
    {"value": "Pending Review", "label": "Pending Review"},
    {"value": "Authorized", "label": "Authorized"},
    {"value": "Authorization not Required", "label": "Auth Not Req"},
    {"value": "Canceled", "label": "Canceled"},
    {"value": "Denied", "label": "Denied"},
    {"value": "Open", "label": "Open"},
]


def _build_filter_bar():
    """Two-row filter bar: dimension filters + date controls."""
    return dmc.Paper(
        children=[
            # Row 1: dimension filters
            dmc.Group(
                children=[
                    department_chips(PAGE_ID),
                    html.Div(
                        id=f"{PAGE_ID}-specialty-wrap",
                        className="rc-compact-multi-wrap",
                        style={"position": "relative",
                               "display": "inline-block",
                               "width": 220},
                        children=[
                            dmc.MultiSelect(
                                id=f"{PAGE_ID}-filter-specialty",
                                data=[],
                                placeholder="All Specialties",
                                clearable=True,
                                searchable=True,
                                hidePickedOptions=False,
                                size="sm",
                                # Specialty list is finite (~25 entries) so
                                # we make the dropdown tall enough to show
                                # all without scrolling.
                                maxDropdownHeight=800,
                                comboboxProps={"zIndex": 500},
                                styles={
                                    "pillsList": {
                                        "flexWrap": "nowrap",
                                        "overflow": "hidden",
                                        "alignItems": "center",
                                        "maxWidth": "100%",
                                    },
                                },
                            ),
                            html.Span(
                                id=f"{PAGE_ID}-specialty-count-badge",
                                className="rc-count-badge",
                                children="",
                                style={"display": "none"},
                            ),
                        ],
                    ),
                    html.Div(
                        id=f"{PAGE_ID}-institution-wrap",
                        className="rc-compact-multi-wrap",
                        style={"position": "relative",
                               "display": "inline-block",
                               "width": 240},
                        children=[
                            dmc.MultiSelect(
                                id=f"{PAGE_ID}-filter-institution",
                                data=[],
                                placeholder="All Institutions",
                                clearable=True,
                                searchable=True,
                                hidePickedOptions=False,
                                size="sm",
                                maxDropdownHeight=800,
                                comboboxProps={"zIndex": 500},
                                styles={
                                    "pillsList": {
                                        "flexWrap": "nowrap",
                                        "overflow": "hidden",
                                        "alignItems": "center",
                                        "maxWidth": "100%",
                                    },
                                },
                            ),
                            html.Span(
                                id=f"{PAGE_ID}-institution-count-badge",
                                className="rc-count-badge",
                                children="",
                                style={"display": "none"},
                            ),
                        ],
                    ),
                    html.Div(
                        id=f"{PAGE_ID}-provider-wrap",
                        className="rc-compact-multi-wrap",
                        style={"position": "relative",
                               "display": "inline-block",
                               "width": 260},
                        children=[
                            dmc.MultiSelect(
                                id=f"{PAGE_ID}-filter-provider",
                                data=[],  # populated by callback
                                placeholder="All Providers",
                                clearable=True,
                                searchable=True,
                                # Show picked options in dropdown so users
                                # can untick them; callback sorts selected
                                # providers to the top of the list.
                                hidePickedOptions=False,
                                size="sm",
                                maxDropdownHeight=800,
                                comboboxProps={"zIndex": 500},
                                # Mantine 7 MultiSelect: pills live inside
                                # the `pillsList` slot (a flex container).
                                # Forcing nowrap + clipping on THAT slot
                                # keeps everything on one row; targeting the
                                # outer `input` slot used to clip the lone
                                # pill out of view because pillsList sits
                                # inside it with its own padding.
                                styles={
                                    "pillsList": {
                                        "flexWrap": "nowrap",
                                        "overflow": "hidden",
                                        "alignItems": "center",
                                        "maxWidth": "100%",
                                    },
                                },
                            ),
                            # Badge appears only when >=2 providers picked;
                            # text + visibility driven by a clientside
                            # callback (see _provider_compact_callbacks).
                            html.Span(
                                id=f"{PAGE_ID}-provider-count-badge",
                                className="rc-count-badge",
                                children="",
                                style={"display": "none"},
                            ),
                        ],
                    ),
                    diagnosis_accordion(PAGE_ID),
                    _chip_dropdown("Payor", "payor-filter", children=[
                        dmc.SegmentedControl(
                            id=f"{PAGE_ID}-filter-payor-mode",
                            data=_PAYOR_MODE_TOGGLE,
                            value="broad",
                            size="xs",
                            fullWidth=True,
                            mb="xs",
                        ),
                        html.Div(
                            dmc.ChipGroup(
                                children=[],
                                id=f"{PAGE_ID}-filter-payor",
                                multiple=True,
                                value=[],
                            ),
                            style={"maxHeight": 280, "overflowY": "auto",
                                   "minWidth": 240},
                        ),
                    ]),
                    outlier_panel(PAGE_ID, transitions=[
                        ("Created \u2192 Scheduled", _CAP_CREATED_TO_SCHEDULED),
                        ("Scheduled \u2192 Visit", _CAP_SCHEDULED_TO_VISIT),
                    ], extra_children=[
                        dmc.Divider(my="xs"),
                        dmc.Box(children=[
                            dmc.Group(
                                justify="space-between",
                                children=[
                                    dmc.Text("Pipeline Window", size="xs", c="#6B7280"),
                                    dmc.Text(
                                        "90d",
                                        id=f"{PAGE_ID}-pipeline-window-val",
                                        size="xs", fw=600, c="#7C2A83",
                                    ),
                                ],
                            ),
                            dmc.Slider(
                                id=f"{PAGE_ID}-pipeline-window",
                                min=30, max=180, step=5,
                                value=90, size="xs", color="violet",
                                showLabelOnHover=True,
                            ),
                        ], mb="xs"),
                    ]),
                    dmc.Group(
                        children=[
                            dmc.Text("Smoothing", size="xs", c="#6B7280", fw=500),
                            dmc.Slider(
                                id=f"{PAGE_ID}-smooth-slider",
                                min=0, max=1, step=0.01, value=0.3,
                                size="xs", showLabelOnHover=False,
                                w=120, updatemode="drag",
                            ),
                        ],
                        gap=6, align="center",
                    ),
                ],
                gap="md", wrap="wrap", align="center",
            ),
            # Row 2: date controls
            dmc.Group(
                children=[
                    dmc.Select(
                        id=f"{PAGE_ID}-filter-date-preset",
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
                        size="xs", w=150, allowDeselect=False,
                        leftSection=DashIconify(icon="mdi:clock-outline", width=14),
                        comboboxProps={"zIndex": 500, "offset": 2},
                        maxDropdownHeight=400,
                    ),
                    dmc.Paper(
                        dcc.DatePickerRange(
                            id=f"{PAGE_ID}-filter-daterange",
                            display_format="MMM D, YYYY",
                            start_date_placeholder_text="Start",
                            end_date_placeholder_text="End",
                            clearable=True,
                            number_of_months_shown=2,
                            minimum_nights=0,
                            start_date=idx_to_date(
                                preset_to_slider_val(_DEFAULT_DATE_PRESET, MAX_IDX)[0]
                            ).strftime("%Y-%m-%d"),
                            end_date=idx_to_date(
                                preset_to_slider_val(_DEFAULT_DATE_PRESET, MAX_IDX)[1],
                                end_of_month=True,
                            ).strftime("%Y-%m-%d"),
                            className="wf-date-picker-range",
                        ),
                        px="xs", py=4, radius="sm", withBorder=True,
                        className="wf-datepicker-wrapper",
                    ),
                    dmc.Box(
                        children=[
                            html.Div(id=f"{PAGE_ID}-date-range-label", style={"display": "none"}),
                            dmc.RangeSlider(
                                id=f"{PAGE_ID}-date-slider",
                                min=0, max=MAX_IDX, step=1,
                                value=preset_to_slider_val(_DEFAULT_DATE_PRESET, MAX_IDX),
                                marks=SLIDER_MARKS,
                                color="violet", size="sm", minRange=0,
                            ),
                        ],
                        style={"flex": "1", "minWidth": "280px"},
                    ),
                ],
                gap="md", align="center", mt="xs",
            ),
        ],
        p="sm", px="md", radius="md", shadow="xs", withBorder=True,
    )


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------

layout = dmc.Stack(
    gap=16,
    className="page-content",
    children=[
        # Sticky header
        dmc.Box(
            className="page-sticky-header",
            children=[
                dmc.Group(
                    justify="center", align="center", gap="sm",
                    children=[
                        dmc.Title("Referrals", order=2, className="page-title"),
                        dmc.ActionIcon(
                            DashIconify(icon="tabler:address-book", width=20),
                            id=f"{PAGE_ID}-rpm-btn",
                            variant="subtle", color="violet", size="lg",
                        ),
                    ],
                ),
                html.Div(
                    style={"position": "relative"},
                    children=[
                        _build_filter_bar(),
                        html.Div(
                            id=f"{PAGE_ID}-grid-filter-badge",
                            children=dmc.Tooltip(
                                label="Table column filters are active — charts reflect the filtered subset",
                                position="left", withArrow=True, multiline=True, w=220,
                                children=dmc.Badge(
                                    "Table Filtered",
                                    color="red", variant="filled", size="md",
                                    leftSection=DashIconify(icon="mdi:filter", width=14),
                                ),
                            ),
                            style={
                                "position": "absolute", "top": -12, "right": 8,
                                "zIndex": 10, "display": "none", "cursor": "pointer",
                            },
                        ),
                    ],
                ),
            ],
        ),

        # KPI row — 6 cards, evenly spaced
        dmc.Group(
            id=f"{PAGE_ID}-kpi-row",
            gap="sm",
            grow=True,
            wrap="nowrap",
            style={"overflow": "hidden"},
            children=[kpi_placeholder() for _ in range(6)],
        ),

        # Flow Gantt — referral pathway
        dmc.Paper(
            children=[
                dmc.Text("Referral Pathway", size="sm", fw=500, c=NEUTRAL["text_secondary"], mb="sm"),
                dmc.Box(
                    pos="relative",
                    children=[
                        dmc.LoadingOverlay(
                            id=f"{PAGE_ID}-flow-gantt-loading",
                            visible=False,
                            loaderProps={"type": "dots", "color": PRIMARY},
                            overlayProps={"radius": "sm", "blur": 2},
                            zIndex=100,
                            transitionProps={"duration": 600, "exitDuration": 80},
                        ),
                        html.Div(
                            id=f"{PAGE_ID}-flow-gantt",
                            style={
                                "width": "100%",
                                "aspectRatio": "2.45 / 1",
                                "minHeight": "340px",
                                "maxHeight": "480px",
                            },
                        ),
                    ],
                ),
            ],
            p="md", radius="md", shadow="xs", withBorder=True,
        ),

        # Flow distribution + trend + conversion (driven by Gantt band selection)
        dmc.Grid(
            gutter="md",
            children=[
                dmc.GridCol(
                    span={"base": 12, "md": 4},
                    children=dmc.Paper(
                        children=[
                            dmc.Group(
                                justify="space-between", mb=8,
                                children=[
                                    dmc.Text(
                                        id=f"{PAGE_ID}-dist-title",
                                        children="Duration Distribution",
                                        size="sm", fw=500, c=NEUTRAL["text_secondary"],
                                    ),
                                    dmc.Group(
                                        gap="xs", align="center", wrap="nowrap",
                                        children=[
                                            dmc.SegmentedControl(
                                                id=f"{PAGE_ID}-dist-type",
                                                data=[
                                                    {"value": "density", "label": "Density"},
                                                    {"value": "histogram", "label": "Histogram"},
                                                ],
                                                value="density", size="xs",
                                            ),
                                            chart_settings_popover(
                                                f"{PAGE_ID}-dist",
                                                chart_types=None,
                                                show_smooth=True,
                                                smooth_min=0,
                                                smooth_max=10,
                                                smooth_step=0.5,
                                                smooth_default=1.5,
                                                slider_label="Bandwidth",
                                                show_grouping=False,
                                            ),
                                        ],
                                    ),
                                ],
                            ),
                            dmc.Box(
                                pos="relative",
                                style={"height": "340px"},
                                children=[
                                    dmc.LoadingOverlay(
                                        id=f"{PAGE_ID}-flow-dist-loading",
                                        visible=False,
                                        loaderProps={"type": "dots", "color": PRIMARY},
                                        overlayProps={"radius": "sm", "blur": 2},
                                        transitionProps={"duration": 600, "exitDuration": 80},
                                    ),
                                    dcc.Graph(
                                        id=f"{PAGE_ID}-flow-dist",
                                        config={"displayModeBar": False, "responsive": True},
                                        style={"height": "100%"},
                                    ),
                                ],
                            ),
                        ],
                        p="sm", radius="md", shadow="xs", withBorder=True,
                    ),
                ),
                dmc.GridCol(
                    span={"base": 12, "md": 4},
                    children=dmc.Paper(
                        children=[
                            dmc.Group(
                                justify="space-between", mb=8,
                                children=[
                                    dmc.Text(
                                        id=f"{PAGE_ID}-trend-title",
                                        children="Duration Trend",
                                        size="sm", fw=500, c=NEUTRAL["text_secondary"],
                                    ),
                                    dmc.Group(
                                        gap="xs", align="center", wrap="nowrap",
                                        children=[
                                            dmc.SegmentedControl(
                                                id=f"{PAGE_ID}-trend-agg",
                                                data=[
                                                    {"value": "W", "label": "Weekly"},
                                                    {"value": "M", "label": "Monthly"},
                                                    {"value": "Y", "label": "Yearly"},
                                                ],
                                                value="M", size="xs",
                                            ),
                                            chart_settings_popover(
                                                f"{PAGE_ID}-trend",
                                                chart_types=[
                                                    {"value": "line", "label": "Line"},
                                                    {"value": "area", "label": "Area"},
                                                    {"value": "bar", "label": "Bar"},
                                                ],
                                                chart_type_default="bar",
                                                show_smooth=True,
                                                smooth_max=12,
                                                smooth_default=2,
                                                slider_label="Smoothing",
                                                show_grouping=False,
                                            ),
                                        ],
                                    ),
                                ],
                            ),
                            dmc.Box(
                                pos="relative",
                                style={"height": "340px"},
                                children=[
                                    dmc.LoadingOverlay(
                                        id=f"{PAGE_ID}-flow-trend-loading",
                                        visible=False,
                                        loaderProps={"type": "dots", "color": PRIMARY},
                                        overlayProps={"radius": "sm", "blur": 2},
                                        transitionProps={"duration": 600, "exitDuration": 80},
                                    ),
                                    dcc.Graph(
                                        id=f"{PAGE_ID}-flow-trend",
                                        config={"displayModeBar": False, "responsive": True},
                                        style={"height": "100%"},
                                    ),
                                ],
                            ),
                        ],
                        p="sm", radius="md", shadow="xs", withBorder=True,
                    ),
                ),
                dmc.GridCol(
                    span={"base": 12, "md": 4},
                    children=dmc.Paper(
                        children=[
                            dmc.Group(
                                justify="space-between", mb=8,
                                children=[
                                    dmc.Text(
                                        id=f"{PAGE_ID}-conv-title",
                                        children="Conversion Rate Trend",
                                        size="sm", fw=500, c=NEUTRAL["text_secondary"],
                                    ),
                                    dmc.Group(
                                        gap="xs", align="center", wrap="nowrap",
                                        children=[
                                            dmc.SegmentedControl(
                                                id=f"{PAGE_ID}-conv-agg",
                                                data=[
                                                    {"value": "W", "label": "Weekly"},
                                                    {"value": "M", "label": "Monthly"},
                                                    {"value": "Y", "label": "Yearly"},
                                                ],
                                                value="M", size="xs",
                                            ),
                                            chart_settings_popover(
                                                f"{PAGE_ID}-conv",
                                                chart_types=[
                                                    {"value": "line", "label": "Line"},
                                                    {"value": "area", "label": "Area"},
                                                    {"value": "bar", "label": "Bar"},
                                                ],
                                                chart_type_default="line",
                                                show_smooth=True,
                                                smooth_max=12,
                                                smooth_default=0,
                                                slider_label="Smoothing",
                                                show_grouping=False,
                                            ),
                                        ],
                                    ),
                                ],
                            ),
                            dmc.Box(
                                pos="relative",
                                style={"height": "340px"},
                                children=[
                                    dmc.LoadingOverlay(
                                        id=f"{PAGE_ID}-flow-conv-loading",
                                        visible=False,
                                        loaderProps={"type": "dots", "color": PRIMARY},
                                        overlayProps={"radius": "sm", "blur": 2},
                                        transitionProps={"duration": 600, "exitDuration": 80},
                                    ),
                                    dcc.Graph(
                                        id=f"{PAGE_ID}-flow-conv",
                                        config={"displayModeBar": False, "responsive": True},
                                        style={"height": "100%"},
                                    ),
                                ],
                            ),
                        ],
                        p="sm", radius="md", shadow="xs", withBorder=True,
                    ),
                ),
            ],
        ),

        # Dimension Trend + Current vs Prior comparison
        dmc.Grid(
            gutter="md",
            children=[
                dmc.GridCol(
                    chart_card(
                        f"{PAGE_ID}-chart-dim-trend",
                        "Referral Trend",
                        chart_types=[
                            {"value": "area", "label": "Area"},
                            {"value": "line", "label": "Line"},
                            {"value": "bar", "label": "Bar"},
                        ],
                        show_grouping=False,
                        show_smooth=True,
                        smooth_max=30,
                        smooth_default=0,
                        graph_height="100%",
                        paper_height=f"{_DIM_RIDGE_HEIGHT + 60}px",
                        store_data=True,
                        extra_controls=[
                            dmc.SegmentedControl(
                                id=f"{PAGE_ID}-dim-trend-agg",
                                data=[
                                    {"value": "W", "label": "Weekly"},
                                    {"value": "M", "label": "Monthly"},
                                    {"value": "Y", "label": "Yearly"},
                                ],
                                value="M",
                                size="xs",
                            ),
                        ],
                        extra_controls_left=[
                            dmc.SegmentedControl(
                                id=f"{PAGE_ID}-dim-toggle",
                                data=[
                                    {"value": "provider", "label": "Referring MD"},
                                    {"value": "department", "label": "Referring Dept"},
                                    {"value": "institution", "label": "Institution"},
                                    {"value": "specialty", "label": "Specialty"},
                                    {"value": "diagnosis", "label": "Diagnosis"},
                                    {"value": "payor", "label": "Payor"},
                                ],
                                value="diagnosis",
                                size="xs",
                                color="violet",
                            ),
                        ],
                    ),
                    span=6,
                ),
                dmc.GridCol(
                    dmc.Paper(
                        children=[
                            dmc.Group(
                                justify="space-between",
                                mb=8,
                                children=[
                                    dmc.Text("Current vs Prior Period", size="sm", fw=500,
                                             c=NEUTRAL["text_secondary"],
                                             id=f"{PAGE_ID}-compare-title"),
                                    dmc.Group(
                                        gap="xs",
                                        children=[
                                            dmc.SegmentedControl(
                                                id=f"{PAGE_ID}-dim-compare-period",
                                                data=[
                                                    {"value": "calendar", "label": "Calendar"},
                                                    {"value": "rolling", "label": "Rolling"},
                                                ],
                                                value="calendar",
                                                size="xs",
                                            ),
                                            chart_settings_popover(
                                                f"{PAGE_ID}-dim-compare",
                                                chart_types=None,
                                                show_smooth=False,
                                                show_grouping=False,
                                                show_prior_periods=True,
                                                prior_periods_default=1,
                                            ),
                                        ],
                                    ),
                                ],
                            ),
                            dmc.Box(
                                pos="relative",
                                style={"flex": "1", "minHeight": 0},
                                children=[
                                    dmc.LoadingOverlay(
                                        id=f"{PAGE_ID}-chart-dim-comparison-loading",
                                        visible=False,
                                        loaderProps={"type": "dots", "color": PRIMARY},
                                        overlayProps={"radius": "sm", "blur": 2},
                                        transitionProps={"duration": 600, "exitDuration": 80},
                                    ),
                                    dmc.Box(
                                        style={"position": "absolute", "top": 0, "left": 0,
                                               "right": 0, "bottom": 0},
                                        children=[
                                            dcc.Graph(
                                                id=f"{PAGE_ID}-chart-dim-comparison",
                                                config={"displayModeBar": False},
                                                responsive=True,
                                                style={"height": "100%", "width": "100%"},
                                            ),
                                        ],
                                    ),
                                ],
                            ),
                        ],
                        p="sm", pb=8, radius="md", shadow="xs", withBorder=True,
                        h=f"{_DIM_RIDGE_HEIGHT + 60}px",
                        style={"display": "flex", "flexDirection": "column"},
                    ),
                    span=6,
                ),
            ],
        ),

        # Row: Referral Volume Trend + Cumulative Referral Volume
        dmc.Grid(gutter="md", children=[
            dmc.GridCol(
                chart_card(
                    f"{PAGE_ID}-chart-vol",
                    "Referral Volume",
                    settings_id=f"{PAGE_ID}-vol",
                    chart_types=[
                        {"value": "bar", "label": "Bar"},
                        {"value": "line", "label": "Line"},
                        {"value": "area", "label": "Area"},
                    ],
                    show_smooth=True,
                    smooth_max=12,
                    smooth_default=0,
                    paper_padding="md",
                    extra_controls_left=[
                        dmc.SegmentedControl(
                            id=f"{PAGE_ID}-vol-slice",
                            data=[
                                {"value": "", "label": "Total"},
                                {"value": "department", "label": "Ref Dept"},
                                {"value": "institution", "label": "Institution"},
                                {"value": "specialty", "label": "Specialty"},
                                {"value": "diagnosis", "label": "Dx"},
                                {"value": "site", "label": "Site"},
                                {"value": "payor", "label": "Payor"},
                            ],
                            value="",
                            size="xs",
                            color="violet",
                        ),
                    ],
                    extra_controls=[
                        dmc.SegmentedControl(
                            id=f"{PAGE_ID}-vol-agg",
                            data=[
                                {"value": "W", "label": "Weekly"},
                                {"value": "M", "label": "Monthly"},
                                {"value": "Y", "label": "Yearly"},
                            ],
                            value="M",
                            size="xs",
                        ),
                    ],
                ),
                span={"base": 12, "md": 6},
            ),
            dmc.GridCol(
                chart_card(
                    f"{PAGE_ID}-chart-cumulative",
                    "Cumulative Referral Volume",
                    settings_id=f"{PAGE_ID}-cumulative",
                    chart_types=[
                        {"value": "line", "label": "Line"},
                        {"value": "area", "label": "Area"},
                        {"value": "bar", "label": "Bar"},
                    ],
                    show_smooth=True,
                    show_prior_periods=True,
                    show_project_toggle=True,
                    smooth_min=0,
                    smooth_max=1,
                    smooth_step=0.05,
                    smooth_default=0.1,
                    prior_periods_default=3,
                    slider_label="Smoothing",
                    paper_padding="md",
                    extra_controls=[
                        dmc.SegmentedControl(
                            id=f"{PAGE_ID}-cumulative-mode",
                            data=[
                                {"value": "prior", "label": "Prior Periods"},
                                {"value": "slice", "label": "Slice By"},
                            ],
                            value="prior",
                            size="xs",
                        ),
                        dmc.SegmentedControl(
                            id=f"{PAGE_ID}-cumulative-period-type",
                            data=[
                                {"value": "calendar", "label": "Calendar"},
                                {"value": "rolling", "label": "Rolling"},
                            ],
                            value="calendar",
                            size="xs",
                        ),
                        dmc.SegmentedControl(
                            id=f"{PAGE_ID}-cumulative-slice",
                            data=[
                                {"value": "department", "label": "Ref Dept"},
                                {"value": "institution", "label": "Institution"},
                                {"value": "specialty", "label": "Specialty"},
                                {"value": "diagnosis", "label": "Dx"},
                                {"value": "site", "label": "Site"},
                            ],
                            value="department",
                            size="xs",
                            style={"display": "none"},
                        ),
                    ],
                ),
                span={"base": 12, "md": 6},
            ),
        ]),

        # Referring Provider Map
        dmc.Paper(
            children=[
                dmc.Group(
                    justify="space-between", mb="xs",
                    children=[
                        dmc.Text("Referring Provider Origins", size="sm", fw=500, c=NEUTRAL["text_secondary"]),
                        dmc.Group(
                            gap="md", align="center",
                            children=[
                                dmc.Switch(
                                    id=f"{PAGE_ID}-map-flow-toggle",
                                    label="Flow lines",
                                    size="xs",
                                    checked=True,
                                ),
                                dmc.Group(
                                    gap="xs", align="center",
                                    children=[
                                        dmc.Text("Min:", size="xs", c="#9CA3AF"),
                                        dmc.Slider(
                                            id=f"{PAGE_ID}-map-min-slider",
                                            min=1, max=20, value=3, step=1,
                                            marks=[
                                                {"value": 1, "label": "1"},
                                                {"value": 5, "label": "5"},
                                                {"value": 10, "label": "10"},
                                                {"value": 20, "label": "20"},
                                            ],
                                            size="xs", w=140,
                                            styles={"markLabel": {"fontSize": "9px", "marginTop": "-2px"}},
                                        ),
                                    ],
                                ),
                                dmc.SegmentedControl(
                                    id=f"{PAGE_ID}-map-region",
                                    data=[
                                        {"label": "PNW", "value": "pnw"},
                                        {"label": "All US", "value": "all"},
                                    ],
                                    value="pnw", size="xs",
                                ),
                                dmc.SegmentedControl(
                                    id=f"{PAGE_ID}-map-dept",
                                    data=["All"] + list(DEPARTMENTS),
                                    value="All", size="xs",
                                ),
                                dmc.Tooltip(
                                    label="Reset map view", position="bottom",
                                    children=dmc.ActionIcon(
                                        DashIconify(icon="mdi:fit-to-screen-outline", width=16),
                                        id=f"{PAGE_ID}-map-reset",
                                        variant="subtle", color="gray", size="sm",
                                    ),
                                ),
                            ],
                        ),
                    ],
                ),
                dmc.Box(
                    pos="relative",
                    style={"height": "700px"},
                    children=[
                        dmc.LoadingOverlay(
                            id=f"{PAGE_ID}-map-loading",
                            visible=False,
                            loaderProps={"type": "dots", "color": PRIMARY},
                            overlayProps={"radius": "sm", "blur": 2},
                            transitionProps={"duration": 600, "exitDuration": 80},
                        ),
                        dcc.Graph(
                            id=f"{PAGE_ID}-map",
                            config={"displayModeBar": False, "scrollZoom": True},
                            style={"height": "100%"},
                        ),
                    ],
                ),
            ],
            p="sm", radius="md", shadow="xs", withBorder=True,
        ),

        # Detail table (accordion)
        detail_table(
            f"{PAGE_ID}-detail-grid",
            title="Referral Detail",
            export_id=f"{PAGE_ID}-table-export",
            column_size="autoSize",
            extra_controls=[
                dmc.Button(
                    "Clear Filters",
                    id=f"{PAGE_ID}-table-clear-filters",
                    size="compact-xs",
                    variant="light",
                    color="red",
                    leftSection=DashIconify(icon="mdi:filter-remove", width=14),
                    style={"display": "none"},
                ),
            ],
        ),

        # ---------------------------------------------------------------
        # Referring Physician Manager Modal
        # ---------------------------------------------------------------
        # Instant-feedback overlay while the heavy DMC Modal renders.
        html.Div(
            id=f"{PAGE_ID}-rpm-overlay",
            className="heavy-modal-overlay hidden",
            children=[
                html.Div(
                    className="heavy-modal-overlay-card",
                    children=[
                        html.Div(className="heavy-modal-spinner"),
                        html.Div("Loading Referring Physician Manager…",
                                 className="heavy-modal-overlay-text"),
                    ],
                ),
            ],
        ),
        dcc.Interval(
            id=f"{PAGE_ID}-rpm-delay",
            interval=60,
            disabled=True,
            max_intervals=1,
            n_intervals=0,
        ),

        dmc.Modal(
            id=f"{PAGE_ID}-rpm-modal",
            opened=False,
            # keepMounted=False: modal internals are heavy; don't keep them in
            # the DOM on initial page load. First open re-mounts from scratch.
            keepMounted=False,
            transitionProps={"transition": "fade", "duration": 120},
            title=dmc.Group(
                children=[
                    DashIconify(icon="tabler:address-book", width=22, color=PRIMARY),
                    dmc.Text("Referring Physician Manager", fw=600, size="lg"),
                ],
                gap="xs",
            ),
            size="95%",
            centered=True,
            zIndex=1000,
            styles={
                "header": {"padding": "6px 16px"},
                "content": {"height": "95vh", "display": "flex", "flexDirection": "column"},
                "body": {"padding": "0px 16px 4px 16px", "flex": 1, "overflow": "hidden", "display": "flex", "flexDirection": "column"},
            },
            children=[
                html.Div(ai_settings_panel("ref", compact=True),
                         style={"marginBottom": "6px"}),
                dmc.Tabs(
                    id=f"{PAGE_ID}-rpm-tabs",
                    value="providers",
                    style={"flex": 1, "display": "flex", "flexDirection": "column", "overflow": "hidden"},
                    children=[
                        # Tab row: tabs left, buttons right (same line)
                        dmc.Group(
                            justify="space-between", align="center", mb=4,
                            style={"borderBottom": "1px solid #dee2e6"},
                            children=[
                                dmc.TabsList(
                                    style={"borderBottom": "none"},
                                    children=[
                                        dmc.TabsTab(
                                            dmc.Group(gap=6, children=[
                                                DashIconify(icon="tabler:stethoscope", width=16),
                                                "Providers",
                                                dmc.Badge(
                                                    id=f"{PAGE_ID}-rpm-prov-count", size="sm",
                                                    variant="light", color="violet",
                                                ),
                                            ]),
                                            value="providers",
                                        ),
                                        dmc.TabsTab(
                                            dmc.Group(gap=6, children=[
                                                DashIconify(icon="tabler:building-hospital", width=16),
                                                "Institutions",
                                                dmc.Badge(
                                                    id=f"{PAGE_ID}-rpm-inst-count", size="sm",
                                                    variant="light", color="violet",
                                                ),
                                            ]),
                                            value="institutions",
                                        ),
                                        dmc.TabsTab(
                                            dmc.Group(gap=6, children=[
                                                DashIconify(icon="tabler:dna", width=16),
                                                "Diagnoses",
                                                dmc.Badge(
                                                    id=f"{PAGE_ID}-rpm-diag-count", size="sm",
                                                    variant="light", color="violet",
                                                ),
                                            ]),
                                            value="diagnoses",
                                        ),
                                    ],
                                ),
                                # Buttons — visible only on Providers tab
                                dmc.Group(
                                    id=f"{PAGE_ID}-rpm-action-btns",
                                    gap="sm", mr="xs",
                                    children=[
                                        dmc.Text(id=f"{PAGE_ID}-rpm-stats", size="xs",
                                                 c=NEUTRAL["text_muted"]),
                                        dmc.Switch(
                                            id=f"{PAGE_ID}-rpm-unreviewed-toggle",
                                            label="Unreviewed only",
                                            size="xs",
                                            checked=False,
                                        ),
                                        dmc.Switch(
                                            id=f"{PAGE_ID}-rpm-dupes-toggle",
                                            label="Duplicate NPIs only",
                                            size="xs",
                                            checked=False,
                                            color="teal",
                                        ),
                                        dmc.Button(
                                            "Look Up Specialties (NPI)",
                                            id=f"{PAGE_ID}-rpm-npi-btn",
                                            leftSection=DashIconify(icon="tabler:search", width=14),
                                            variant="light", color="blue", size="xs",
                                        ),
                                        dmc.Button(
                                            "Research (AI)",
                                            id=f"{PAGE_ID}-rpm-ai-btn",
                                            leftSection=DashIconify(icon="tabler:brain", width=14),
                                            variant="light", color="grape", size="xs",
                                        ),
                                        dmc.Button(
                                            "Mark Reviewed",
                                            id=f"{PAGE_ID}-rpm-reviewed-btn",
                                            leftSection=DashIconify(icon="tabler:check", width=14),
                                            variant="light", color="green", size="xs",
                                        ),
                                        dmc.Button(
                                            "Add Address",
                                            id=f"{PAGE_ID}-rpm-add-addr-btn",
                                            leftSection=DashIconify(icon="tabler:map-pin-plus", width=14),
                                            variant="light", color="violet", size="xs",
                                        ),
                                        dmc.Button(
                                            "Merge Selected",
                                            id=f"{PAGE_ID}-rpm-merge-btn",
                                            leftSection=DashIconify(icon="tabler:arrows-join", width=14),
                                            variant="light", color="teal", size="xs",
                                        ),
                                        dmc.Button(
                                            "Delete Selected",
                                            id=f"{PAGE_ID}-rpm-delete-btn",
                                            leftSection=DashIconify(icon="tabler:trash", width=14),
                                            variant="light", color="red", size="xs",
                                        ),
                                        dmc.Button(
                                            "Export CSV",
                                            id=f"{PAGE_ID}-rpm-export-btn",
                                            leftSection=DashIconify(icon="tabler:download", width=14),
                                            variant="light", color="gray", size="xs",
                                        ),
                                    ],
                                ),
                            ],
                        ),

                        # ── Providers tab ──
                        dmc.TabsPanel(
                            value="providers",
                            pt=4,
                            style={"flex": 1, "display": "flex", "flexDirection": "column", "overflow": "hidden"},
                            children=[
                                # Progress bar
                                dmc.Progress(
                                    id=f"{PAGE_ID}-rpm-progress",
                                    value=0, size="sm", color="blue",
                                    style={"display": "none"}, mb=4,
                                ),
                                dmc.Text(
                                    id=f"{PAGE_ID}-rpm-progress-text", size="xs",
                                    c=NEUTRAL["text_muted"],
                                    style={"display": "none"}, mb=4,
                                ),
                                # NPI Lookup Review Panel (hidden until results ready)
                                dmc.Paper(
                                    id=f"{PAGE_ID}-rpm-npi-review",
                                    style={"display": "none"},
                                    p="sm", radius="md", withBorder=True, mb=6,
                                    children=[
                                        dmc.Group(
                                            justify="space-between", mb=6,
                                            children=[
                                                dmc.Text("NPI Lookup Results — Review before applying",
                                                         size="sm", fw=600, c=PRIMARY),
                                                dmc.Group(
                                                    gap="sm",
                                                    children=[
                                                        dmc.Button(
                                                            "Accept All",
                                                            id=f"{PAGE_ID}-rpm-npi-accept-all",
                                                            leftSection=DashIconify(icon="tabler:checks", width=14),
                                                            variant="light", color="green", size="xs",
                                                        ),
                                                        dmc.Button(
                                                            "Reject All",
                                                            id=f"{PAGE_ID}-rpm-npi-reject-all",
                                                            leftSection=DashIconify(icon="tabler:x", width=14),
                                                            variant="light", color="red", size="xs",
                                                        ),
                                                        dmc.Button(
                                                            "Apply Selected",
                                                            id=f"{PAGE_ID}-rpm-npi-apply",
                                                            leftSection=DashIconify(icon="tabler:check", width=14),
                                                            variant="filled", color="green", size="xs",
                                                        ),
                                                    ],
                                                ),
                                            ],
                                        ),
                                        dag.AgGrid(
                                            id=f"{PAGE_ID}-rpm-npi-review-grid",
                                            columnDefs=[
                                                {"field": "accept", "headerName": "Accept", "width": 70,
                                                 "cellDataType": "boolean", "editable": True},
                                                {"field": "npi", "headerName": "NPI", "flex": 0.7,
                                                 "cellRenderer": "NpiLink"},
                                                {"field": "name", "headerName": "Name", "flex": 1.4,
                                                 "cellRenderer": "NameSearchFull"},
                                                {"field": "current_specialty", "headerName": "Current", "flex": 1,
                                                 "cellStyle": {"color": NEUTRAL["text_muted"]}},
                                                {"field": "raw_taxonomy", "headerName": "NPI Taxonomy", "flex": 1.2,
                                                 "cellStyle": {"fontStyle": "italic"}},
                                                {"field": "mapped_specialty", "headerName": "Mapped To", "flex": 1,
                                                 "editable": True,
                                                 "cellEditor": "agSelectCellEditor",
                                                 "cellEditorParams": {"values": [""] + ABMS_SPECIALTIES},
                                                 "cellStyle": {"fontWeight": 600, "cursor": "pointer"}},
                                                {"field": "status", "headerName": "Status", "flex": 0.5},
                                                {"field": "referral_count", "headerName": "Referrals", "flex": 0.4,
                                                 "cellRenderer": "ReferralCountLink",
                                                 "type": "numericColumn"},
                                            ],
                                            defaultColDef={"sortable": True, "resizable": True, "valueFormatter": {"function": "params.value == null || params.value === '' ? '–' : params.value"}},
                                            dashGridOptions={
                                                "rowHeight": 32,
                                                "headerHeight": 32,
                                                "domLayout": "autoHeight",
                                                "pagination": True,
                                                "paginationPageSize": 15,
                                                "singleClickEdit": True,
                                            },
                                            style={"maxHeight": "300px"},
                                            className="ag-theme-alpine",
                                        ),
                                    ],
                                ),
                                # Providers grid
                                dag.AgGrid(
                                    id=f"{PAGE_ID}-rpm-grid",
                                    columnDefs=[
                                        {"field": "npi", "headerName": "NPI", "flex": 0.7,
                                         "cellRenderer": "NpiLink",
                                         "filter": "agTextColumnFilter", "floatingFilter": True},
                                        {"field": "name", "headerName": "Name", "flex": 1.2,
                                         "editable": True,
                                         "cellRenderer": "NameSearch",
                                         "filter": "agTextColumnFilter", "floatingFilter": True},
                                        {"field": "department", "headerName": "Department", "flex": 1.4,
                                         "filter": "agTextColumnFilter", "floatingFilter": True},
                                        {"field": "full_address", "headerName": "Address", "flex": 1.6,
                                         "editable": True,
                                         "cellEditor": "AddressAutocompleteEditor",
                                         "cellEditorPopup": True,
                                         "cellEditorPopupPosition": "under",
                                         "cellRenderer": "AddressCopy",
                                         "cellStyle": {"function": "params.data && params.data.address_source === 'manual' ? {fontStyle: 'italic', color: '#7C2A83'} : {}"},
                                         "filter": "agTextColumnFilter", "floatingFilter": True},
                                        {"field": "specialty", "headerName": "Specialty", "flex": 1.1,
                                         "editable": True,
                                         "cellEditor": "agSelectCellEditor",
                                         "cellEditorParams": {"values": [""] + ABMS_SPECIALTIES},
                                         "cellStyle": {"cursor": "pointer"},
                                         "filter": "agTextColumnFilter", "floatingFilter": True},
                                        {"field": "institution", "headerName": "Institution", "flex": 1.3,
                                         "editable": True,
                                         "cellRenderer": "InstitutionBadge",
                                         "cellEditor": "InstitutionEditor",
                                         "cellEditorPopup": True,
                                         "cellEditorPopupPosition": "under",
                                         "cellStyle": {"cursor": "pointer"},
                                         "filter": "agTextColumnFilter", "floatingFilter": True},
                                        {"field": "source", "headerName": "Source", "flex": 0.5,
                                         "filter": "agTextColumnFilter", "floatingFilter": True,
                                         "cellStyle": {"fontStyle": "italic", "color": NEUTRAL["text_muted"]}},
                                        {"field": "patient_count", "headerName": "Referrals", "flex": 0.4,
                                         "cellRenderer": "ReferralCountLink",
                                         "filter": "agNumberColumnFilter", "sort": "desc",
                                         "type": "numericColumn"},
                                        {"field": "first_referral", "headerName": "First", "flex": 0.5,
                                         "minWidth": 100,
                                         "filter": "agTextColumnFilter"},
                                        {"field": "last_referral", "headerName": "Last", "flex": 0.5,
                                         "minWidth": 100,
                                         "filter": "agTextColumnFilter"},
                                        {"field": "reviewed", "headerName": "Reviewed", "flex": 0.4,
                                         "cellDataType": "boolean",
                                         "editable": True,
                                         "cellStyle": {"textAlign": "center"}},
                                    ],
                                    defaultColDef={"sortable": True, "resizable": True, "valueFormatter": {"function": "params.value == null || params.value === '' ? '–' : params.value"}},
                                    dashGridOptions={
                                        "pagination": True,
                                        "paginationPageSize": 50,
                                        "animateRows": True,
                                        "undoRedoCellEditing": True,
                                        "singleClickEdit": True,
                                        "rowHeight": 36,
                                        "headerHeight": 36,
                                        "floatingFiltersHeight": 32,
                                        "rowSelection": {"mode": "multiRow", "selectAll": "filtered"},
                                        # Stable row identity lets AG Grid do diff-based updates
                                        # when rowData changes (instead of full re-render), so
                                        # scroll position is preserved after a save/review.
                                        "getRowId": {"function": "params.data.row_key"},
                                    },
                                    style={"flex": 1, "minHeight": 0},
                                    className="ag-theme-alpine",
                                ),
                                # Institution rename confirmation (modal rendered outside grid)
                                # Referral detail panel — shows when a provider row is clicked
                                dmc.Paper(
                                    id=f"{PAGE_ID}-rpm-detail-panel",
                                    style={"display": "none"},
                                    p="sm", radius="md", withBorder=True,
                                    children=[
                                        dmc.Group(
                                            justify="space-between", mb=4,
                                            children=[
                                                dmc.Text(
                                                    id=f"{PAGE_ID}-rpm-detail-title",
                                                    size="sm", fw=600, c=PRIMARY,
                                                ),
                                                dmc.ActionIcon(
                                                    DashIconify(icon="tabler:x", width=14),
                                                    id=f"{PAGE_ID}-rpm-detail-close",
                                                    variant="subtle", color="gray", size="sm",
                                                ),
                                            ],
                                        ),
                                        dag.AgGrid(
                                            id=f"{PAGE_ID}-rpm-detail-grid",
                                            columnDefs=apply_phi_grid_rules([
                                                {"field": "Created", "headerName": "Date", "flex": 0.6,
                                                 "sort": "desc"},
                                                {"field": "MRN", "headerName": "MRN", "flex": 0.5},
                                                {"field": "Patient Name", "headerName": "Patient", "flex": 1},
                                                {"field": "Rfl Prim Dx", "headerName": "Primary Dx", "flex": 1.2},
                                                {"field": "Diagnoses", "headerName": "Diagnoses", "flex": 1.5},
                                                {"field": "Status", "headerName": "Status", "flex": 0.6},
                                                {"field": "First Appt", "headerName": "First Appt", "flex": 0.6},
                                                {"field": "Days to First Appt", "headerName": "Days", "flex": 0.4,
                                                 "type": "numericColumn"},
                                            ]),
                                            defaultColDef={"sortable": True, "resizable": True,
                                                           "filter": True, "floatingFilter": True,
                                                           "valueFormatter": {"function": "params.value == null || params.value === '' ? '–' : params.value"}},
                                            dashGridOptions={
                                                "rowHeight": 30,
                                                "headerHeight": 30,
                                                "floatingFiltersHeight": 28,
                                                "pagination": True,
                                                "paginationPageSize": 10,
                                            },
                                            style={"height": "250px"},
                                            className="ag-theme-alpine",
                                        ),
                                    ],
                                ),
                            ],
                        ),

                        # ── Institutions tab ──
                        dmc.TabsPanel(
                            value="institutions",
                            pt=4,
                            style={"flex": 1, "display": "flex", "flexDirection": "column", "overflow": "hidden"},
                            children=[
                                dmc.Group(
                                    justify="space-between", mb=6,
                                    children=[
                                        dmc.Text(
                                            "Edit an institution name to rename it across all providers. "
                                            "Delete removes the assignment from all providers.",
                                            size="sm", c=NEUTRAL["text_secondary"],
                                        ),
                                        dmc.Button(
                                            "Export Institutions",
                                            id=f"{PAGE_ID}-rpm-inst-export-btn",
                                            leftSection=DashIconify(icon="tabler:download", width=16),
                                            variant="light", color="gray", size="sm",
                                        ),
                                    ],
                                ),
                                dag.AgGrid(
                                    id=f"{PAGE_ID}-rpm-inst-grid",
                                    columnDefs=[
                                        {"field": "name", "headerName": "Institution Name", "flex": 2,
                                         "editable": True, "cellEditor": "agTextCellEditor",
                                         "filter": "agTextColumnFilter", "floatingFilter": True},
                                        {"field": "physician_count", "headerName": "Providers",
                                         "flex": 0.5, "type": "numericColumn", "sort": "desc",
                                         "filter": "agNumberColumnFilter"},
                                        {"field": "delete", "headerName": "", "flex": 0.3,
                                         "cellRenderer": "InstitutionDelete",
                                         "cellStyle": {"textAlign": "center"}},
                                    ],
                                    defaultColDef={"sortable": True, "resizable": True, "valueFormatter": {"function": "params.value == null || params.value === '' ? '–' : params.value"}},
                                    dashGridOptions={
                                        "pagination": True,
                                        "paginationPageSize": 25,
                                        "rowHeight": 36,
                                        "headerHeight": 36,
                                        "floatingFiltersHeight": 32,
                                        "animateRows": True,
                                    },
                                    style={"flex": 1, "minHeight": 0},
                                    className="ag-theme-alpine",
                                ),
                            ],
                        ),
                        # ── Diagnoses tab ──
                        dmc.TabsPanel(
                            value="diagnoses",
                            pt=4,
                            style={"flex": 1, "display": "flex", "flexDirection": "column", "overflow": "hidden"},
                            children=[
                                dmc.Group(
                                    justify="space-between", mb=6,
                                    children=[
                                        dmc.Text(
                                            "ICD codes and free-text diagnoses from referrals not in the ARIA lookup. "
                                            "Classify these to improve referral diagnosis reporting.",
                                            size="sm", c=NEUTRAL["text_secondary"],
                                        ),
                                        dmc.Group(
                                            gap="sm",
                                            children=[
                                                dmc.Text(id=f"{PAGE_ID}-rpm-diag-stats", size="xs",
                                                         c=NEUTRAL["text_muted"]),
                                                dmc.Switch(
                                                    id=f"{PAGE_ID}-rpm-diag-unreviewed-toggle",
                                                    label="Unreviewed only",
                                                    size="xs",
                                                    checked=False,
                                                ),
                                                dmc.Button(
                                                    "Classify (AI)",
                                                    id=f"{PAGE_ID}-rpm-diag-ai-btn",
                                                    leftSection=DashIconify(icon="tabler:brain", width=14),
                                                    variant="light", color="grape", size="xs",
                                                ),
                                                dmc.Button(
                                                    "Mark Reviewed",
                                                    id=f"{PAGE_ID}-rpm-diag-reviewed-btn",
                                                    leftSection=DashIconify(icon="tabler:check", width=14),
                                                    variant="light", color="green", size="xs",
                                                ),
                                                dmc.Button(
                                                    "Export CSV",
                                                    id=f"{PAGE_ID}-rpm-diag-export-btn",
                                                    leftSection=DashIconify(icon="tabler:download", width=14),
                                                    variant="light", color="gray", size="xs",
                                                ),
                                            ],
                                        ),
                                    ],
                                ),
                                # AI progress
                                dmc.Progress(
                                    id=f"{PAGE_ID}-rpm-diag-ai-progress",
                                    value=0, size="sm", color="grape",
                                    style={"display": "none"}, mb=4,
                                ),
                                dmc.Text(
                                    id=f"{PAGE_ID}-rpm-diag-ai-progress-text", size="xs",
                                    c=NEUTRAL["text_muted"],
                                    style={"display": "none"}, mb=4,
                                ),
                                # AI Review Panel placeholder (modal rendered outside)
                                dag.AgGrid(
                                    id=f"{PAGE_ID}-rpm-diag-grid",
                                    columnDefs=[
                                        {"field": "icd_code", "headerName": "ICD Code", "flex": 0.6,
                                         "filter": "agTextColumnFilter", "floatingFilter": True},
                                        {"field": "description", "headerName": "Description", "flex": 1.8,
                                         "filter": "agTextColumnFilter", "floatingFilter": True},
                                        {"field": "category", "headerName": "Category", "flex": 1,
                                         "editable": True,
                                         "cellEditor": "agSelectCellEditor",
                                         "cellEditorParams": {"values": [""] + BODY_SYSTEMS + ["Unknown"]},
                                         "cellStyle": {"cursor": "pointer"},
                                         "filter": "agTextColumnFilter", "floatingFilter": True},
                                        {"field": "subcategory", "headerName": "Subcategory", "flex": 1,
                                         "editable": True,
                                         "cellEditor": "agSelectCellEditor",
                                         "cellEditorParams": {"function": "getSubcategoryValues(params)"},
                                         "cellStyle": {"cursor": "pointer"},
                                         "filter": "agTextColumnFilter", "floatingFilter": True},
                                        {"field": "patients", "headerName": "Referrals", "flex": 0.4,
                                         "cellRenderer": "DiagCountLink",
                                         "cellRendererParams": {"storeId": f"{PAGE_ID}-rpm-diag-detail-store"},
                                         "type": "numericColumn", "sort": "desc",
                                         "filter": "agNumberColumnFilter",
                                         "headerTooltip": "Total referrals (rad-onc + med-onc)"},
                                        {"field": "rad_onc_count", "headerName": "Rad-Onc", "flex": 0.35,
                                         "type": "numericColumn",
                                         "filter": "agNumberColumnFilter"},
                                        {"field": "medonc_count", "headerName": "Med-Onc", "flex": 0.35,
                                         "type": "numericColumn",
                                         "filter": "agNumberColumnFilter"},
                                        {"field": "origin", "headerName": "Origin", "flex": 0.4,
                                         "filter": "agTextColumnFilter", "floatingFilter": True,
                                         "cellStyle": {"function":
                                            "params.value === 'medonc' ? {color: '#9C27B0', fontWeight: 600} : "
                                            "params.value === 'both' ? {color: '#7C2A83', fontWeight: 600} : "
                                            "{color: '#6B7280'}"}},
                                        {"field": "source", "headerName": "Source", "flex": 0.4,
                                         "filter": "agTextColumnFilter", "floatingFilter": True,
                                         "cellStyle": {"fontStyle": "italic", "color": NEUTRAL["text_muted"]}},
                                        {"field": "reviewed", "headerName": "Reviewed", "flex": 0.3,
                                         "cellDataType": "boolean", "editable": True,
                                         "cellStyle": {"textAlign": "center"}},
                                    ],
                                    defaultColDef={"sortable": True, "resizable": True, "valueFormatter": {"function": "params.value == null || params.value === '' ? '–' : params.value"}},
                                    dashGridOptions={
                                        "pagination": True,
                                        "paginationPageSize": 50,
                                        "animateRows": True,
                                        "singleClickEdit": True,
                                        "rowHeight": 36,
                                        "headerHeight": 36,
                                        "floatingFiltersHeight": 32,
                                        "rowSelection": {"mode": "multiRow", "selectAll": "filtered"},
                                    },
                                    style={"flex": 1, "minHeight": 0},
                                    className="ag-theme-alpine",
                                ),
                                # Diagnosis detail panel
                                dmc.Paper(
                                    id=f"{PAGE_ID}-rpm-diag-detail-panel",
                                    style={"display": "none"},
                                    p="sm", radius="md", withBorder=True,
                                    children=[
                                        dmc.Group(
                                            justify="space-between", mb=4,
                                            children=[
                                                dmc.Text(id=f"{PAGE_ID}-rpm-diag-detail-title",
                                                         size="sm", fw=600, c=PRIMARY),
                                                dmc.ActionIcon(
                                                    DashIconify(icon="tabler:x", width=14),
                                                    id=f"{PAGE_ID}-rpm-diag-detail-close",
                                                    variant="subtle", color="gray", size="sm",
                                                ),
                                            ],
                                        ),
                                        dag.AgGrid(
                                            id=f"{PAGE_ID}-rpm-diag-detail-grid",
                                            columnDefs=apply_phi_grid_rules([
                                                {"field": "Created", "headerName": "Date", "flex": 0.6, "sort": "desc"},
                                                {"field": "Source", "headerName": "Source", "flex": 0.5,
                                                 "filter": "agTextColumnFilter",
                                                 "cellStyle": {"function":
                                                    "params.value === 'Med-Onc' ? {color: '#9C27B0', fontWeight: 600} : "
                                                    "{color: '#7C2A83', fontWeight: 600}"}},
                                                {"field": "MRN", "headerName": "MRN", "flex": 0.5},
                                                {"field": "Patient Name", "headerName": "Patient", "flex": 1},
                                                {"field": "Rfl Prim Dx", "headerName": "Primary Dx", "flex": 1.2},
                                                {"field": "Diagnoses", "headerName": "Diagnoses", "flex": 1.5},
                                                {"field": "Status", "headerName": "Status", "flex": 0.6},
                                            ]),
                                            defaultColDef={"sortable": True, "resizable": True,
                                                           "filter": True, "floatingFilter": True,
                                                           "valueFormatter": {"function": "params.value == null || params.value === '' ? '–' : params.value"}},
                                            dashGridOptions={
                                                "rowHeight": 30, "headerHeight": 30,
                                                "floatingFiltersHeight": 28,
                                                "pagination": True, "paginationPageSize": 10,
                                            },
                                            style={"height": "250px"},
                                            className="ag-theme-alpine",
                                        ),
                                    ],
                                ),
                            ],
                        ),
                    ],
                ),
                dcc.Download(id=f"{PAGE_ID}-rpm-inst-download"),
                dcc.Download(id=f"{PAGE_ID}-rpm-diag-download"),
                dcc.Store(id=f"{PAGE_ID}-rpm-diag-detail-store", data=None),
            ],
        ),
        # RPM stores and interval
        dcc.Store(id=f"{PAGE_ID}-rpm-grid-full-store", data=None),
        dcc.Store(id=f"{PAGE_ID}-rpm-inst-pending", data=None),
        dmc.Modal(
            id=f"{PAGE_ID}-rpm-inst-confirm",
            opened=False,
            title=dmc.Group(
                children=[
                    DashIconify(icon="tabler:building-hospital", width=20, color=PRIMARY),
                    dmc.Text("Rename Institution", fw=600, size="md"),
                ],
                gap="xs",
            ),
            centered=True,
            zIndex=2000,
            size="lg",
            children=[
                dmc.Text(id=f"{PAGE_ID}-rpm-inst-confirm-text", size="sm", mb="md"),
                dmc.Group(
                    justify="flex-end",
                    gap="sm",
                    children=[
                        dmc.Button(
                            "Cancel",
                            id=f"{PAGE_ID}-rpm-inst-confirm-cancel",
                            variant="subtle", color="gray", size="sm",
                        ),
                        dmc.Button(
                            "Just this provider",
                            id=f"{PAGE_ID}-rpm-inst-confirm-one",
                            variant="light", color="blue", size="sm",
                        ),
                        dmc.Button(
                            id=f"{PAGE_ID}-rpm-inst-confirm-all",
                            variant="filled", color="violet", size="sm",
                        ),
                    ],
                ),
            ],
        ),
        dcc.Store(id=f"{PAGE_ID}-rpm-merge-pending", data=None),
        dmc.Modal(
            id=f"{PAGE_ID}-rpm-merge-confirm",
            opened=False,
            title=dmc.Group(
                children=[
                    DashIconify(icon="tabler:arrows-join", width=20, color=PRIMARY),
                    dmc.Text("Merge Provider Rows", fw=600, size="md"),
                ],
                gap="xs",
            ),
            centered=True,
            zIndex=2000,
            size="lg",
            children=[
                dmc.Text(id=f"{PAGE_ID}-rpm-merge-confirm-text", size="sm", mb="sm"),
                dmc.Paper(
                    id=f"{PAGE_ID}-rpm-merge-confirm-detail",
                    p="sm", radius="sm", withBorder=True, mb="md",
                ),
                dmc.Group(
                    justify="flex-end",
                    gap="sm",
                    children=[
                        dmc.Button(
                            "Cancel",
                            id=f"{PAGE_ID}-rpm-merge-confirm-cancel",
                            variant="subtle", color="gray", size="sm",
                        ),
                        dmc.Button(
                            "Merge",
                            id=f"{PAGE_ID}-rpm-merge-confirm-apply",
                            leftSection=DashIconify(icon="tabler:arrows-join", width=14),
                            variant="filled", color="teal", size="sm",
                        ),
                    ],
                ),
            ],
        ),
        dcc.Store(id=f"{PAGE_ID}-rpm-diag-grid-full-store", data=None),
        dcc.Store(id=f"{PAGE_ID}-rpm-diag-ai-running", data=False),
        dmc.Modal(
            id=f"{PAGE_ID}-rpm-diag-ai-review",
            opened=False,
            title=dmc.Group(
                children=[
                    DashIconify(icon="tabler:brain", width=22, color="grape"),
                    dmc.Text("AI Classification Results — Review before applying", fw=600, size="lg"),
                ],
                gap="xs",
            ),
            size="90%",
            centered=True,
            zIndex=2000,
            styles={
                "content": {"height": "80vh", "display": "flex", "flexDirection": "column"},
                "body": {"flex": 1, "overflow": "hidden", "display": "flex", "flexDirection": "column"},
            },
            children=[
                dmc.Group(
                    justify="flex-end", mb=8,
                    children=[
                        dmc.Button(
                            "Accept All",
                            id=f"{PAGE_ID}-rpm-diag-ai-accept-all",
                            leftSection=DashIconify(icon="tabler:checks", width=14),
                            variant="light", color="green", size="sm",
                        ),
                        dmc.Button(
                            "Reject All",
                            id=f"{PAGE_ID}-rpm-diag-ai-reject-all",
                            leftSection=DashIconify(icon="tabler:x", width=14),
                            variant="light", color="red", size="sm",
                        ),
                        dmc.Button(
                            "Apply Selected",
                            id=f"{PAGE_ID}-rpm-diag-ai-apply",
                            leftSection=DashIconify(icon="tabler:check", width=14),
                            variant="filled", color="green", size="sm",
                        ),
                    ],
                ),
                dag.AgGrid(
                    id=f"{PAGE_ID}-rpm-diag-ai-review-grid",
                    columnDefs=[
                        {"field": "accept", "headerName": "Accept", "width": 80,
                         "cellDataType": "boolean", "editable": True},
                        {"field": "description", "headerName": "Description", "flex": 1.5},
                        {"field": "current_category", "headerName": "Current Cat", "flex": 0.8,
                         "cellStyle": {"color": NEUTRAL["text_muted"]}},
                        {"field": "current_subcategory", "headerName": "Current Sub", "flex": 0.8,
                         "cellStyle": {"color": NEUTRAL["text_muted"]}},
                        {"field": "ai_category", "headerName": "AI Category", "flex": 1,
                         "editable": True,
                         "cellEditor": "agSelectCellEditor",
                         "cellEditorParams": {"values": [""] + BODY_SYSTEMS + ["Unknown"]},
                         "cellStyle": {"fontWeight": 600, "cursor": "pointer"}},
                        {"field": "ai_subcategory", "headerName": "AI Subcategory", "flex": 1,
                         "editable": True,
                         "cellEditor": "agSelectCellEditor",
                         "cellEditorParams": {"function": "getSubcategoryValues(params)"},
                         "cellStyle": {"fontWeight": 600, "cursor": "pointer"}},
                        {"field": "patients", "headerName": "Pts", "flex": 0.3,
                         "type": "numericColumn"},
                    ],
                    defaultColDef={"sortable": True, "resizable": True, "valueFormatter": {"function": "params.value == null || params.value === '' ? '–' : params.value"}},
                    dashGridOptions={
                        "rowHeight": 36,
                        "headerHeight": 36,
                        "pagination": True,
                        "paginationPageSize": 25,
                        "singleClickEdit": True,
                    },
                    style={"flex": 1, "minHeight": 0},
                    className="ag-theme-alpine",
                ),
            ],
        ),
        dcc.Store(id=f"{PAGE_ID}-rpm-diag-ai-review-data", data=None),
        dcc.Interval(id=f"{PAGE_ID}-rpm-diag-ai-poll", interval=2000, disabled=True),
        # ---- Provider AI review modal (opt-in via the toggle) ----
        # Mirrors the diag/payor pattern: AI runs, results stash here for
        # editing instead of writing straight through. User edits cells,
        # checks Accept, and clicks Apply Selected to persist.
        dmc.Modal(
            id=f"{PAGE_ID}-rpm-ai-review",
            opened=False,
            title=dmc.Group(
                children=[
                    DashIconify(icon="tabler:brain", width=22, color="grape"),
                    dmc.Text("AI Provider Research — Review before applying",
                             fw=600, size="lg"),
                ],
                gap="xs",
            ),
            size="95%",
            centered=True,
            zIndex=2100,
            styles={
                "content": {"height": "85vh", "display": "flex", "flexDirection": "column"},
                "body": {"flex": 1, "overflow": "hidden",
                         "display": "flex", "flexDirection": "column"},
            },
            children=[
                dmc.Group(
                    justify="flex-end", mb=8,
                    children=[
                        dmc.Button(
                            "Accept All",
                            id=f"{PAGE_ID}-rpm-ai-accept-all",
                            leftSection=DashIconify(icon="tabler:checks", width=14),
                            variant="light", color="green", size="sm",
                        ),
                        dmc.Button(
                            "Reject All",
                            id=f"{PAGE_ID}-rpm-ai-reject-all",
                            leftSection=DashIconify(icon="tabler:x", width=14),
                            variant="light", color="red", size="sm",
                        ),
                        dmc.Button(
                            "Apply Selected",
                            id=f"{PAGE_ID}-rpm-ai-apply",
                            leftSection=DashIconify(icon="tabler:check", width=14),
                            variant="filled", color="green", size="sm",
                        ),
                    ],
                ),
                dag.AgGrid(
                    id=f"{PAGE_ID}-rpm-ai-review-grid",
                    columnDefs=[
                        {"field": "accept", "headerName": "Accept", "width": 80,
                         "cellDataType": "boolean", "editable": True},
                        {"field": "name", "headerName": "Name", "flex": 1,
                         "cellStyle": {"fontSize": "12px"}},
                        {"field": "npi", "headerName": "NPI", "flex": 0.6,
                         "cellStyle": {"fontSize": "11px",
                                       "color": NEUTRAL["text_muted"]}},
                        {"field": "current_institution", "headerName": "Current Inst",
                         "flex": 0.9,
                         "cellStyle": {"color": NEUTRAL["text_muted"], "fontSize": "11px"}},
                        {"field": "ai_institution", "headerName": "AI Institution",
                         "flex": 1, "editable": True,
                         "cellStyle": {"fontWeight": 600, "fontSize": "12px"}},
                        {"field": "current_specialty", "headerName": "Current Spec",
                         "flex": 0.7,
                         "cellStyle": {"color": NEUTRAL["text_muted"], "fontSize": "11px"}},
                        {"field": "ai_specialty", "headerName": "AI Specialty",
                         "flex": 0.8, "editable": True,
                         "cellEditor": "agSelectCellEditor",
                         "cellEditorParams": {"values": [""] + ABMS_SPECIALTIES},
                         "cellStyle": {"fontWeight": 600, "cursor": "pointer",
                                       "fontSize": "12px"}},
                        {"field": "current_address", "headerName": "Current Address",
                         "flex": 1.1, "wrapText": True, "autoHeight": True,
                         "cellStyle": {"color": NEUTRAL["text_muted"], "fontSize": "11px",
                                       "lineHeight": "1.3"}},
                        {"field": "ai_address", "headerName": "AI Address",
                         "flex": 1.2, "editable": True,
                         "wrapText": True, "autoHeight": True,
                         "cellStyle": {"fontWeight": 600, "fontSize": "12px",
                                       "lineHeight": "1.3"}},
                        {"field": "window", "headerName": "Window",
                         "flex": 0.5, "cellStyle": {"fontSize": "11px",
                                                    "color": NEUTRAL["text_muted"]}},
                    ],
                    defaultColDef={
                        "sortable": True, "resizable": True,
                        "valueFormatter": {"function":
                            "params.value == null || params.value === '' ? '–' : params.value"},
                    },
                    dashGridOptions={
                        "rowHeight": 56,
                        "headerHeight": 36,
                        "pagination": True,
                        "paginationPageSize": 25,
                        "singleClickEdit": True,
                    },
                    style={"flex": 1, "minHeight": 0},
                    className="ag-theme-alpine",
                ),
            ],
        ),
        dcc.Store(id=f"{PAGE_ID}-rpm-running", data=False),
        dcc.Store(id=f"{PAGE_ID}-rpm-npi-pending", data=None),
        dcc.Store(id=f"{PAGE_ID}-rpm-detail-store", data=None),
        dcc.Interval(id=f"{PAGE_ID}-rpm-poll", interval=2000, disabled=True),
        dcc.Download(id=f"{PAGE_ID}-rpm-download"),

        # Stores
        dcc.Store(id=f"{PAGE_ID}-store-flow-gantt"),
        dcc.Store(id=f"{PAGE_ID}-store-flow-details"),
        dcc.Store(id=f"{PAGE_ID}-store-selected-flow"),
        dcc.Store(id=f"{PAGE_ID}-flow-gantt-trigger"),
        # Dummy stores/inputs for clientside callback compatibility
        dcc.Store(id=f"{PAGE_ID}-store-flow-details-b"),
        dcc.Store(id=f"{PAGE_ID}-compare-mode", data=False),
        dcc.Store(id=f"{PAGE_ID}-agg-toggle", data="median"),
        dcc.Store(id=f"{PAGE_ID}-agg-toggle-b", data="median"),
        dcc.Store(id=f"{PAGE_ID}-dist-km-switch", data=False),
        dcc.Store(id=f"{PAGE_ID}-store-trend-legacy"),
        dcc.Store(id=f"{PAGE_ID}-store-trend-legacy-b"),
        dcc.Store(id=f"{PAGE_ID}-trend-km-switch", data=False),
        html.Div(id=f"{PAGE_ID}-trend-maturity", style={"display": "none"}),
        dcc.Store(id=f"{PAGE_ID}-store-funnel"),
        dcc.Store(id=f"{PAGE_ID}-store-leadtime"),
        dcc.Store(id=f"{PAGE_ID}-store-providers"),
        dcc.Store(id=f"{PAGE_ID}-store-departments"),
        dcc.Store(id=f"{PAGE_ID}-store-trend"),
        dcc.Store(id=f"{PAGE_ID}-store-ridge"),
        dcc.Store(id=f"{PAGE_ID}-store-conv-dept"),
        dcc.Store(id=f"{PAGE_ID}-store-new-referrers"),
        dcc.Store(id=f"{PAGE_ID}-store-vol"),
        dcc.Store(id=f"{PAGE_ID}-store-cumulative"),
        dcc.Store(id=f"{PAGE_ID}-store-kpi-sparklines"),
        dcc.Store(id=f"{PAGE_ID}-store-map-geo"),
        dcc.Store(id=f"{PAGE_ID}-store-dim-compare-figs"),

        dcc.Store(id=f"{PAGE_ID}-table-filter-rows"),
        dcc.Interval(id=f"{PAGE_ID}-interval", interval=300_000, n_intervals=0, max_intervals=0),  # fires once on mount; no background refresh (daily data + global refresh button)
    ],
)


# ---------------------------------------------------------------------------
# Date Slider Sync Callbacks
# ---------------------------------------------------------------------------

@callback(
    Output(f"{PAGE_ID}-date-slider", "value"),
    Output(f"{PAGE_ID}-filter-daterange", "start_date", allow_duplicate=True),
    Output(f"{PAGE_ID}-filter-daterange", "end_date", allow_duplicate=True),
    Input(f"{PAGE_ID}-filter-date-preset", "value"),
    prevent_initial_call=True,
)
def _preset_to_slider(preset):
    if preset == "custom":
        return (dash.no_update,) * 3
    slider_val = preset_to_slider_val(preset, MAX_IDX)
    s, e = preset_to_exact_dates(preset)
    return slider_val, s, e


clientside_callback(
    ClientsideFunction(namespace="referralsDateSlider", function_name="syncSlider"),
    Output(f"{PAGE_ID}-filter-daterange", "start_date"),
    Output(f"{PAGE_ID}-filter-daterange", "end_date"),
    Output(f"{PAGE_ID}-date-range-label", "children"),
    Input(f"{PAGE_ID}-date-slider", "value"),
    State(f"{PAGE_ID}-filter-daterange", "start_date"),
    State(f"{PAGE_ID}-filter-daterange", "end_date"),
)


# D) Slider → auto-set preset to "Custom" when it doesn't match
@callback(
    Output(f"{PAGE_ID}-filter-date-preset", "value", allow_duplicate=True),
    Input(f"{PAGE_ID}-date-slider", "value"),
    State(f"{PAGE_ID}-filter-date-preset", "value"),
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
# Grid filter → table-filter-rows store, badge, clear-filters button
# ---------------------------------------------------------------------------

clientside_callback(
    """function(virtual, rowData, prev) {
        var nu = window.dash_clientside.no_update;
        var base = {"position": "absolute", "top": -12, "right": 8, "zIndex": 10, "cursor": "pointer"};
        var hidden = Object.assign({}, base, {"display": "none"});
        var btnHide = {"display": "none"};
        if (!rowData || !rowData.length || !virtual) {
            return prev == null ? [nu, nu, nu] : [null, hidden, btnHide];
        }
        if (virtual.length >= rowData.length) {
            return prev == null ? [nu, nu, nu] : [null, hidden, btnHide];
        }
        var idxs = [];
        for (var i = 0; i < virtual.length; i++) {
            if (virtual[i]._row_idx != null) idxs.push(virtual[i]._row_idx);
        }
        idxs.sort(function(a, b) { return a - b; });
        if (!idxs.length) {
            return prev == null ? [nu, nu, nu] : [null, hidden, btnHide];
        }
        if (prev && prev.length === idxs.length) {
            var same = true;
            for (var j = 0; j < idxs.length; j++) {
                if (prev[j] !== idxs[j]) { same = false; break; }
            }
            if (same) return [nu, nu, nu];
        }
        return [idxs, base, {}];
    }""",
    Output(f"{PAGE_ID}-table-filter-rows", "data"),
    Output(f"{PAGE_ID}-grid-filter-badge", "style"),
    Output(f"{PAGE_ID}-table-clear-filters", "style"),
    Input(f"{PAGE_ID}-detail-grid", "virtualRowData"),
    State(f"{PAGE_ID}-detail-grid", "rowData"),
    State(f"{PAGE_ID}-table-filter-rows", "data"),
    prevent_initial_call=True,
)

# Clear filters → reset AG Grid filterModel
clientside_callback(
    """function(n) {
        if (!n) return window.dash_clientside.no_update;
        return {};
    }""",
    Output(f"{PAGE_ID}-detail-grid", "filterModel"),
    Input(f"{PAGE_ID}-table-clear-filters", "n_clicks"),
    prevent_initial_call=True,
)

# Badge click → scroll to the detail grid
clientside_callback(
    """function(n) {
        if (!n) return window.dash_clientside.no_update;
        var el = document.getElementById('""" + f"{PAGE_ID}-detail-grid" + """');
        if (el) el.scrollIntoView({behavior: 'smooth', block: 'start'});
        return window.dash_clientside.no_update;
    }""",
    Output(f"{PAGE_ID}-grid-filter-badge", "n_clicks"),
    Input(f"{PAGE_ID}-grid-filter-badge", "n_clicks"),
    prevent_initial_call=True,
)

# Export CSV
clientside_callback(
    """function(n) {
        if (!n) return window.dash_clientside.no_update;
        gridExportCsv('""" + f"{PAGE_ID}-detail-grid" + """', 'referrals_detail.csv');
        return window.dash_clientside.no_update;
    }""",
    Output(f"{PAGE_ID}-table-export", "n_clicks"),
    Input(f"{PAGE_ID}-table-export", "n_clicks"),
    prevent_initial_call=True,
)


# Flow Gantt renderer — reuses flow_gantt.js via referralFlowGantt wrapper
clientside_callback(
    ClientsideFunction(namespace="referralFlowGantt", function_name="render"),
    Output(f"{PAGE_ID}-flow-gantt-trigger", "data"),
    Input(f"{PAGE_ID}-store-flow-gantt", "data"),
)

# Distribution chart — reuses flowGantt.renderFlowDistribution
clientside_callback(f"""function() {{
        var fig = window.dash_clientside.flowGantt.renderFlowDistribution.apply(null, arguments);
        return window.dash_clientside.chartDeferred.wrap("{PAGE_ID}-flow-dist", fig);
    }}""",
    Output(f"{PAGE_ID}-flow-dist", "figure"),
    Output(f"{PAGE_ID}-dist-title", "children"),
    Input(f"{PAGE_ID}-store-flow-details", "data"),
    Input(f"{PAGE_ID}-store-selected-flow", "data"),
    Input(f"{PAGE_ID}-dist-type", "value"),
    Input(f"{PAGE_ID}-dist-km-switch", "data"),
    Input(f"{PAGE_ID}-store-flow-details-b", "data"),
    Input(f"{PAGE_ID}-compare-mode", "data"),
    Input(f"{PAGE_ID}-agg-toggle", "data"),
    Input(f"{PAGE_ID}-agg-toggle-b", "data"),
    Input(f"{PAGE_ID}-dist-settings-smooth", "value"),
    prevent_initial_call=True,
)

# Trend chart — reuses flowGantt.renderFlowTrend
clientside_callback(f"""function() {{
        var fig = window.dash_clientside.flowGantt.renderFlowTrend.apply(null, arguments);
        return window.dash_clientside.chartDeferred.wrap("{PAGE_ID}-flow-trend", fig);
    }}""",
    Output(f"{PAGE_ID}-flow-trend", "figure"),
    Output(f"{PAGE_ID}-trend-title", "children"),
    Output(f"{PAGE_ID}-trend-maturity", "style"),
    Input(f"{PAGE_ID}-store-flow-details", "data"),
    Input(f"{PAGE_ID}-store-selected-flow", "data"),
    Input(f"{PAGE_ID}-store-trend-legacy", "data"),
    Input(f"{PAGE_ID}-trend-settings-smooth", "value"),
    Input(f"{PAGE_ID}-trend-settings-type", "value"),
    Input(f"{PAGE_ID}-trend-agg", "value"),
    Input(f"{PAGE_ID}-trend-km-switch", "data"),
    Input(f"{PAGE_ID}-store-flow-details-b", "data"),
    Input(f"{PAGE_ID}-store-trend-legacy-b", "data"),
    Input(f"{PAGE_ID}-compare-mode", "data"),
    Input(f"{PAGE_ID}-agg-toggle", "data"),
    Input(f"{PAGE_ID}-agg-toggle-b", "data"),
    prevent_initial_call=True,
)

# Conversion rate trend — clientside from flow details store
clientside_callback(f"""function() {{
        var fig = window.dash_clientside.flowGantt.renderConversionTrend.apply(null, arguments);
        return window.dash_clientside.chartDeferred.wrap("{PAGE_ID}-flow-conv", fig);
    }}""",
    Output(f"{PAGE_ID}-flow-conv", "figure"),
    Output(f"{PAGE_ID}-conv-title", "children"),
    Input(f"{PAGE_ID}-store-flow-details", "data"),
    Input(f"{PAGE_ID}-store-selected-flow", "data"),
    Input(f"{PAGE_ID}-conv-agg", "value"),
    Input(f"{PAGE_ID}-conv-settings-type", "value"),
    Input(f"{PAGE_ID}-conv-settings-smooth", "value"),
    prevent_initial_call=True,
)


# Register outlier panel callbacks
register_outlier_callbacks(
    PAGE_ID, n_transitions=2,
    defaults=[_CAP_CREATED_TO_SCHEDULED, _CAP_SCHEDULED_TO_VISIT],
)

# Pipeline window slider value label
clientside_callback(
    """function(v) { return v + "d"; }""",
    Output(f"{PAGE_ID}-pipeline-window-val", "children"),
    Input(f"{PAGE_ID}-pipeline-window", "value"),
)

# Register gear-icon toggle + export callbacks for dimension trend chart
register_chart_callbacks([
    f"{PAGE_ID}-chart-dim-trend",
    f"{PAGE_ID}-dim-compare",
    (f"{PAGE_ID}-dist", f"{PAGE_ID}-flow-dist"),
    {"sid": f"{PAGE_ID}-trend", "gid": f"{PAGE_ID}-flow-trend",
     "store_id": True, "show_grouping": False},
    {"sid": f"{PAGE_ID}-conv", "gid": f"{PAGE_ID}-flow-conv",
     "store_id": True, "show_grouping": False},
    (f"{PAGE_ID}-vol", f"{PAGE_ID}-chart-vol", f"{PAGE_ID}-store-vol"),
    {"sid": f"{PAGE_ID}-cumulative", "gid": f"{PAGE_ID}-chart-cumulative",
     "store_id": f"{PAGE_ID}-store-cumulative", "show_grouping": False},
])
register_diagnosis_callbacks(PAGE_ID)

# ---------------------------------------------------------------------------
# Provider compact-multi: hide pills when 2+ picked, show a "N selected"
# badge in their place. Functions live in assets/compact_multi.js — the
# explicit-namespace pattern is more robust than inline string callbacks
# (which can hit anonymous-namespace lookup errors at dispatch time).
# ---------------------------------------------------------------------------
clientside_callback(
    ClientsideFunction(namespace="providerCompact", function_name="wrapClass"),
    Output(f"{PAGE_ID}-provider-wrap", "className"),
    Input(f"{PAGE_ID}-filter-provider", "value"),
)
clientside_callback(
    ClientsideFunction(namespace="providerCompact", function_name="badge"),
    Output(f"{PAGE_ID}-provider-count-badge", "children"),
    Output(f"{PAGE_ID}-provider-count-badge", "style"),
    Input(f"{PAGE_ID}-filter-provider", "value"),
)
# Same pattern applied to Specialty + Institution.
clientside_callback(
    ClientsideFunction(namespace="providerCompact", function_name="wrapClass"),
    Output(f"{PAGE_ID}-specialty-wrap", "className"),
    Input(f"{PAGE_ID}-filter-specialty", "value"),
)
clientside_callback(
    ClientsideFunction(namespace="providerCompact", function_name="badge"),
    Output(f"{PAGE_ID}-specialty-count-badge", "children"),
    Output(f"{PAGE_ID}-specialty-count-badge", "style"),
    Input(f"{PAGE_ID}-filter-specialty", "value"),
)
clientside_callback(
    ClientsideFunction(namespace="providerCompact", function_name="wrapClass"),
    Output(f"{PAGE_ID}-institution-wrap", "className"),
    Input(f"{PAGE_ID}-filter-institution", "value"),
)
clientside_callback(
    ClientsideFunction(namespace="providerCompact", function_name="badge"),
    Output(f"{PAGE_ID}-institution-count-badge", "children"),
    Output(f"{PAGE_ID}-institution-count-badge", "style"),
    Input(f"{PAGE_ID}-filter-institution", "value"),
)

# Clientside callbacks — KPI sparklines via store + smooth slider
_KPI_SPARK_IDS = [
    f"{PAGE_ID}-spark-total",
    f"{PAGE_ID}-spark-conv",
    f"{PAGE_ID}-spark-lead",
    f"{PAGE_ID}-spark-mds",
]

for _spark_id in _KPI_SPARK_IDS:
    clientside_callback(f"""function() {{
        var fig = window.dash_clientside.sparklines.updateFromStore.apply(null, arguments);
        return window.dash_clientside.chartDeferred.wrap("{_spark_id}", fig);
    }}""",
        Output(_spark_id, "figure"),
        Input(f"{PAGE_ID}-store-kpi-sparklines", "data"),
        Input(_spark_id, "id"),
        Input(f"{PAGE_ID}-smooth-slider", "value"),
        prevent_initial_call=True,
    )

# Clientside callback — renders dimension trend ridgeline from store + settings
clientside_callback(f"""function() {{
        var fig = window.dash_clientside.referralRidge.renderTrend.apply(null, arguments);
        return window.dash_clientside.chartDeferred.wrap("{PAGE_ID}-chart-dim-trend", fig, true);
    }}""",
    Output(f"{PAGE_ID}-chart-dim-trend", "figure"),
    Input(f"{PAGE_ID}-chart-dim-trend-store", "data"),
    Input(f"{PAGE_ID}-chart-dim-trend-settings-smooth", "value"),
    Input(f"{PAGE_ID}-chart-dim-trend-settings-type", "value"),
    Input(f"{PAGE_ID}-dim-trend-agg", "value"),
    prevent_initial_call=True,
)

# Clientside callback — pick comparison figure by prior periods slider (no server trip)
clientside_callback(
    """function(figs, nPrior) {
        if (!figs) return [window.dash_clientside.no_update, window.dash_clientside.no_update];
        var key = String(nPrior != null ? nPrior : 1);
        var fig = figs[key] || window.dash_clientside.no_update;
        var title = nPrior === 0 ? "Current Period" : "Current vs Prior Period";
        return [fig, title];
    }""",
    Output(f"{PAGE_ID}-chart-dim-comparison", "figure"),
    Output(f"{PAGE_ID}-compare-title", "children"),
    Input(f"{PAGE_ID}-store-dim-compare-figs", "data"),
    Input(f"{PAGE_ID}-dim-compare-settings-prior-periods", "value"),
    prevent_initial_call=True,
)


# ---------------------------------------------------------------------------
# Chart Builders
# ---------------------------------------------------------------------------

def _build_funnel(df):
    """Horizontal bar chart showing referral funnel stages including CV confirmation."""
    if df.empty:
        return empty_figure("No referral data")

    total = len(df)
    auth_ok = len(df[df["Status"].isin(["Closed", "Authorized", "Authorization not Required", "Open"])])
    with_appt = len(df[df["Appt Attached"] == "Yes"])
    confirmed = len(df[df["CVMatch"].isin(["Confirmed", "Rescheduled"])]) if "CVMatch" in df.columns else 0
    closed = len(df[df["Status"] == "Closed"])

    stages = ["Total Referrals", "Authorized / Auth Not Req", "Appt Attached",
              "Visit Confirmed (CV)", "Closed"]
    values = [total, auth_ok, with_appt, confirmed, closed]
    pcts = [100] + [v / total * 100 if total else 0 for v in values[1:]]

    colors = [CHART_COLORWAY[0], CHART_COLORWAY[1], CHART_COLORWAY[3],
              SEMANTIC_COLORS["success"], CHART_COLORWAY[5]]

    fig = go.Figure()
    for i, (stage, val, pct, clr) in enumerate(zip(stages, values, pcts, colors)):
        fig.add_trace(go.Bar(
            y=[stage], x=[val], orientation="h",
            marker_color=clr,
            text=f"{val:,} ({pct:.0f}%)",
            textposition="auto",
            textfont=dict(size=12, color="white"),
            hovertemplate=f"{stage}: %{{x:,}} ({pct:.1f}%)<extra></extra>",
            showlegend=False,
        ))

    fig = apply_default_layout(fig,
        height=380,
        margin=dict(l=180, r=16, t=8, b=32),
        yaxis=dict(showgrid=False, autorange="reversed", categoryorder="array",
                   categoryarray=stages),
        xaxis=dict(showgrid=True, gridcolor="#F0F0F0", title="Referrals"),
    )
    return fig


def _build_leadtime(df):
    """Box plots for lead time metrics."""
    if df.empty:
        return empty_figure("No referral data")

    metrics = [
        ("Days to Assign", "Assign"),
        ("Days to Auth", "Authorize"),
        ("Auth to Appt", "Auth to Appt"),
        ("Days to First Appt", "To First Appt"),
    ]

    fig = go.Figure()
    colors = [CHART_COLORWAY[0], CHART_COLORWAY[1], CHART_COLORWAY[3], CHART_COLORWAY[5]]
    for i, (col, label) in enumerate(metrics):
        if col not in df.columns:
            continue
        vals = df[col].dropna()
        # Cap outliers at 99th percentile for cleaner display
        if not vals.empty:
            cap = vals.quantile(0.99)
            vals = vals[vals <= cap]
        fig.add_trace(go.Box(
            y=vals, name=label,
            marker_color=colors[i % len(colors)],
            boxmean="sd",
            hovertemplate="%{y:.0f} days<extra></extra>",
        ))

    fig = apply_default_layout(fig,
        height=380,
        margin=dict(l=48, r=16, t=8, b=48),
        showlegend=False,
        yaxis=dict(showgrid=True, gridcolor="#F0F0F0", title="Days"),
        xaxis=dict(showgrid=False),
    )
    return fig



def _prepare_referral_geo_data(df):
    """Aggregate referral provider locations by address + our department for map.

    Uses city/state/zip geocoding (more precise than ZIP centroids) with
    persistent caching. Falls back to ZIP centroid if address geocoding fails.

    Returns a DataFrame with: addr_key, lat, lon, referral_count, primary_city,
    zip5, Department.
    """
    required = ["Referring Provider City", "Referring Provider State",
                 "Referring Provider Zip Code"]
    if df.empty or not all(c in df.columns for c in required):
        return pd.DataFrame()

    work = df.copy()
    # Use "Referred to Department" (always our 3 depts) for coloring
    if "Referred to Department" in work.columns:
        work["_our_dept"] = work["Referred to Department"].apply(_map_to_our_dept).fillna("Unknown")
    else:
        work["_our_dept"] = work["Referred by Department"].apply(_map_to_our_dept).fillna("Unknown")

    # Build address key for each row
    work["_addr_key"] = work.apply(
        lambda r: _addr_geocode_key(
            r.get("Referring Provider Address", ""),
            r.get("Referring Provider City", ""),
            r.get("Referring Provider State", ""),
            r.get("Referring Provider Zip Code", ""),
        ), axis=1,
    )
    work = work[work["_addr_key"].str.strip("|") != "|||"]

    if work.empty:
        return pd.DataFrame()

    # Build unique address records for geocoding
    unique_keys = work["_addr_key"].unique()
    addr_records = []
    for key in unique_keys:
        row = work[work["_addr_key"] == key].iloc[0]
        addr_records.append({
            "address": row.get("Referring Provider Address", ""),
            "city": row.get("Referring Provider City", ""),
            "state": row.get("Referring Provider State", ""),
            "zip_code": row.get("Referring Provider Zip Code", ""),
        })

    # Geocode
    geo = geocode_addresses(addr_records)
    if geo.empty:
        return pd.DataFrame()

    # Aggregate: count referrals per address + our department
    _inst_col = "DoctorInstitution" if "DoctorInstitution" in work.columns else None
    _inst_agg = {"institution": (_inst_col, lambda s: s.mode().iloc[0] if not s.mode().empty else "")} if _inst_col else {}
    has_dept = work["_our_dept"].notna().any()
    if has_dept:
        grp = work.groupby(["_addr_key", "_our_dept"]).agg(
            referral_count=("_addr_key", "size"),
            primary_city=("Referring Provider City",
                          lambda s: s.mode().iloc[0] if not s.mode().empty else ""),
            zip5=("Referring Provider Zip Code",
                  lambda s: normalize_zip(s.mode().iloc[0]) if not s.mode().empty else ""),
            **_inst_agg,
        ).reset_index().rename(columns={"_addr_key": "addr_key", "_our_dept": "Department"})
    else:
        grp = work.groupby("_addr_key").agg(
            referral_count=("_addr_key", "size"),
            primary_city=("Referring Provider City",
                          lambda s: s.mode().iloc[0] if not s.mode().empty else ""),
            zip5=("Referring Provider Zip Code",
                  lambda s: normalize_zip(s.mode().iloc[0]) if not s.mode().empty else ""),
            **_inst_agg,
        ).reset_index().rename(columns={"_addr_key": "addr_key"})
        grp["Department"] = "Unknown"

    # Merge coordinates
    result = grp.merge(geo[["addr_key", "lat", "lon"]], on="addr_key", how="inner")
    result = result[result["referral_count"] > 0]

    return result


def _format_addr_hover(addr_key, dept, count, arrow_to=None, institution=None):
    """Format addr_key (ADDRESS|CITY|STATE|ZIP) into readable hover text."""
    parts = addr_key.split("|") if addr_key else []
    address = parts[0].title() if len(parts) > 0 and parts[0] else ""
    city = parts[1].title() if len(parts) > 1 and parts[1] else ""
    state = parts[2].upper() if len(parts) > 2 and parts[2] else ""
    zipcode = parts[3] if len(parts) > 3 and parts[3] else ""
    lines = []
    if institution and str(institution) not in ("", "nan"):
        lines.append(f"<b>{institution}</b>")
    if address:
        lines.append(address)
    loc = ", ".join(filter(None, [city, state, zipcode]))
    if loc:
        lines.append(loc)
    suffix = "referral" if count == 1 else "referrals"
    if arrow_to:
        lines.append(f"\u2192 {arrow_to}: {count:,} {suffix}")
    else:
        lines.append(f"{dept}: {count:,} {suffix}")
    return "<br>".join(lines)


def _build_referral_map(geo_df, departments_filter, selected_dept="All",
                        show_flows=True, region="pnw", min_referrals=3,
                        uirevision="referrals-map", map_style=None):
    """Build Scattermapbox for referring provider origins."""
    fig = go.Figure()

    _PNW_LAT, _PNW_LON = (42.0, 50.0), (-126.0, -116.0)
    _US_LAT, _US_LON = (24.0, 50.0), (-126.0, -66.0)
    lat_bounds = _PNW_LAT if region == "pnw" else _US_LAT
    lon_bounds = _PNW_LON if region == "pnw" else _US_LON

    active_depts = departments_filter if departments_filter else list(DEPARTMENTS)
    if selected_dept == "All":
        render_depts = list(active_depts)
    elif selected_dept in active_depts:
        render_depts = [selected_dept]
    else:
        render_depts = []

    # Flow lines (rendered first = bottom layer)
    if show_flows and render_depts and not geo_df.empty and "Department" in geo_df.columns:
        # Adapt geo_df to the format get_department_patient_flows expects
        flow_df = geo_df.rename(columns={"referral_count": "patient_count"})
        if "zip5" not in flow_df.columns:
            flow_df["zip5"] = flow_df.get("addr_key", "")
        all_flows = get_department_patient_flows(flow_df, min_patients=min_referrals)

        for dept in render_depts:
            dept_flows = [
                f for f in all_flows
                if f["dept"] == dept
                and lat_bounds[0] <= f["from_lat"] <= lat_bounds[1]
                and lon_bounds[0] <= f["from_lon"] <= lon_bounds[1]
            ]
            if not dept_flows:
                continue

            max_flow = max(f["count"] for f in dept_flows)
            all_lats, all_lons, all_text, all_cd = [], [], [], []
            for flow in dept_flows:
                ratio = flow["count"] / max(max_flow, 1)
                n_arcs = max(1, min(6, 1 + int(ratio * 5)))
                curvatures = [0.25] if n_arcs == 1 else np.linspace(0.15, 0.35, n_arcs).tolist()
                hover = _format_addr_hover(
                    flow.get("addr_key", ""), dept, flow["count"],
                    arrow_to=dept, institution=flow.get("institution"),
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
                lat=all_lats, lon=all_lons,
                mode="lines", line=dict(width=2.5, color=color),
                opacity=0.4, customdata=all_cd,
                text=all_text, hoverinfo="text", showlegend=False,
            ))

    # Department location markers (middle layer)
    for dept in render_depts:
        coords = DEPT_COORDS.get(dept)
        if coords:
            color = DEPARTMENT_COLORS.get(dept, PRIMARY)
            fig.add_trace(go.Scattermapbox(
                lat=[coords[0]], lon=[coords[1]],
                mode="markers+text",
                marker=dict(size=16, color=color, symbol="hospital"),
                text=[dept], textposition="top center",
                textfont=dict(size=12, color=color),
                hovertext=f"{dept} Department", hoverinfo="text",
                showlegend=False,
            ))

    # Scatter markers (top layer — captures hover over flow lines)
    if render_depts and not geo_df.empty and "lat" in geo_df.columns:
        if "Department" in geo_df.columns:
            plot_df = geo_df[geo_df["Department"].isin(render_depts)]
        else:
            plot_df = geo_df
        plot_df = plot_df[
            plot_df["lat"].between(*lat_bounds) & plot_df["lon"].between(*lon_bounds)
        ]
        if "referral_count" in plot_df.columns:
            plot_df = plot_df[plot_df["referral_count"] >= min_referrals]

        for dept in render_depts:
            dept_data = plot_df[plot_df["Department"] == dept] if "Department" in plot_df.columns else plot_df
            if dept_data.empty:
                continue

            color = DEPARTMENT_COLORS.get(dept, "#9E9E9E")
            fig.add_trace(go.Scattermapbox(
                lat=dept_data["lat"], lon=dept_data["lon"],
                mode="markers",
                marker=dict(size=8, color=color, opacity=0.7),
                text=dept_data.apply(
                    lambda r, d=dept: (
                        _format_addr_hover(r.get("addr_key", ""), d, r["referral_count"],
                                          institution=r.get("institution"))
                    ), axis=1,
                ),
                hoverinfo="text", showlegend=False,
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
        # Zoom separately for lat (700px tall) and lon (~1100px wide),
        # take the more constrained axis. 20% padding on each.
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
            accesstoken=MAPBOX_TOKEN, style=map_style or MAPBOX_STYLE,
            center=center, zoom=zoom,
        ),
        height=700, margin=dict(l=0, r=0, t=0, b=0),
        font=dict(family=FONT_FAMILY, size=13),
        paper_bgcolor="rgba(0,0,0,0)", showlegend=False,
        uirevision=uirevision,
    )
    return fig


def _prepare_ref_volume_data(df, agg, slice_by="", payor_mode="broad"):
    """Census-format store data for referral volume trend.

    payor_mode is only consulted when slice_by == "payor".
    """
    if df.empty or "Created" not in df.columns:
        return None

    df = df.copy()
    period_code = "Y" if agg == "Y" else agg
    df["period"] = df["Created"].dt.to_period(period_code).dt.to_timestamp()
    all_periods = sorted(df["period"].unique())
    dates = [d.isoformat() for d in all_periods]

    series = []

    if not slice_by:
        counts = df.groupby("period").size().reindex(all_periods, fill_value=0)
        series.append({"name": "Total", "values": counts.tolist(), "color": PRIMARY})

    elif slice_by == "department":
        top = df["Referred by Department"].value_counts().head(10).index.tolist()
        for i, dept in enumerate(top):
            sub = df[df["Referred by Department"] == dept]
            counts = sub.groupby("period").size().reindex(all_periods, fill_value=0)
            series.append({"name": dept[:30], "values": counts.tolist(),
                           "color": CHART_COLORWAY[i % len(CHART_COLORWAY)]})

    elif slice_by == "institution":
        col = "DoctorInstitution"
        if col in df.columns:
            top = df[col].dropna().value_counts().head(10).index.tolist()
            for i, inst in enumerate(top):
                sub = df[df[col] == inst]
                counts = sub.groupby("period").size().reindex(all_periods, fill_value=0)
                series.append({"name": inst[:30], "values": counts.tolist(),
                               "color": CHART_COLORWAY[i % len(CHART_COLORWAY)]})

    elif slice_by == "specialty":
        col = "DeptSpecialty"
        if col in df.columns:
            top = df[col].dropna().value_counts().head(10).index.tolist()
            for i, spec in enumerate(top):
                sub = df[df[col] == spec]
                counts = sub.groupby("period").size().reindex(all_periods, fill_value=0)
                series.append({"name": spec[:30], "values": counts.tolist(),
                               "color": CHART_COLORWAY[i % len(CHART_COLORWAY)]})

    elif slice_by == "diagnosis":
        df["_dx"] = df.apply(
            lambda r: _categorise_diagnosis(
                r.get("Diagnoses"), r.get("Rfl Prim Dx"), r.get("Onc Dx")
            ), axis=1,
        )
        df_dx = df[~df["_dx"].isin(["Other", "Unknown"])]
        top = df_dx["_dx"].value_counts().head(10).index.tolist()
        for i, dx in enumerate(top):
            sub = df_dx[df_dx["_dx"] == dx]
            counts = sub.groupby("period").size().reindex(all_periods, fill_value=0)
            series.append({"name": dx, "values": counts.tolist(),
                           "color": CHART_COLORWAY[i % len(CHART_COLORWAY)]})

    elif slice_by == "site":
        # Our site (mapped from "Referred to Department" — where we see the patient)
        df["_our_dept"] = df["Referred to Department"].apply(_map_to_our_dept)
        for dept in DEPARTMENTS:
            sub = df[df["_our_dept"] == dept]
            if sub.empty:
                continue
            counts = sub.groupby("period").size().reindex(all_periods, fill_value=0)
            series.append({"name": dept, "values": counts.tolist(),
                           "color": DEPARTMENT_COLORS.get(dept, CHART_COLORWAY[0])})

    elif slice_by == "payor" and "Payer" in df.columns:
        mapping = _get_payor_mapping()
        primary = df["Payer"].apply(_extract_primary_payor)
        df["_payor_grp"] = _payor_mode_groups(primary, payor_mode or "broad", mapping)
        df_p = df[df["_payor_grp"].notna()]
        top = df_p["_payor_grp"].value_counts().head(10).index.tolist()
        for i, p in enumerate(top):
            sub = df_p[df_p["_payor_grp"] == p]
            counts = sub.groupby("period").size().reindex(all_periods, fill_value=0)
            series.append({"name": str(p)[:30], "values": counts.tolist(),
                           "color": CHART_COLORWAY[i % len(CHART_COLORWAY)]})

    if not series:
        return None

    return {
        "dates": dates,
        "series": series,
        "height": 380,
        "yTitle": "Referrals",
        "hideLegend": len(series) == 1,
    }


def _build_day_index_ticks_ref(start_norm, n_days, max_ticks=12):
    """Build tick positions and labels for day-indexed x-axis."""
    if n_days <= max_ticks:
        positions = list(range(n_days))
        labels = [(start_norm + pd.Timedelta(days=i)).strftime("%b %d") for i in positions]
        return positions, labels
    step = max(1, n_days // max_ticks)
    positions = list(range(0, n_days, step))
    labels = [(start_norm + pd.Timedelta(days=i)).strftime("%b %d") for i in positions]
    return positions, labels


def _prepare_ref_cumulative_data(df_all, start, end, mode="prior",
                                  period_type="calendar", slice_by="department",
                                  date_preset=None):
    """Prepare cumulative referral volume data for overlay chart.

    mode="prior": Current period cumulative + prior equivalent periods.
    mode="slice": Current period only, split by dimension.

    Returns (store_data, max_slider, marks).
    """
    _default_marks = [{"value": i, "label": str(i)} for i in range(0, 6)]

    if df_all.empty or "Created" not in df_all.columns:
        return None, 5, _default_marks

    from utils.cumulative_current_year import setup_current_year_range, apply_current_year_projection
    last_data = df_all["Created"].dt.normalize().max()
    start, end, _cy_last_actual = setup_current_year_range(date_preset, mode, start, end)
    if _cy_last_actual is not None:
        _cy_last_actual = min(_cy_last_actual, last_data)
    elif end.normalize() > last_data:
        end = last_data

    period_days = (end - start).days + 1
    if period_days < 2:
        return None, 5, _default_marks

    if period_days > 365 and period_type == "calendar":
        period_type = "rolling"

    def _cumulative_for_window(df, w_start, w_end):
        mask = (df["Created"] >= w_start) & (df["Created"] <= w_end)
        sub = df.loc[mask]
        if sub.empty:
            return []
        daily = sub.groupby(sub["Created"].dt.normalize()).size()
        idx = pd.date_range(w_start.normalize(), w_end.normalize(), freq="D")
        daily = daily.reindex(idx, fill_value=0)
        return daily.cumsum().tolist()

    n_days = period_days
    start_norm = start.normalize()
    day_indices = list(range(n_days))
    tick_positions, tick_labels = _build_day_index_ticks_ref(start_norm, n_days)

    current_vals = _cumulative_for_window(df_all, start, end) if not df_all.empty else [0] * n_days

    if df_all.empty:
        data_min = start
    else:
        data_min = df_all["Created"].min()

    def _period_label(p_start, p_end):
        same_year = p_start.year == p_end.year
        same_month = same_year and p_start.month == p_end.month
        if same_month:
            return p_start.strftime("%b %Y")
        if same_year:
            if p_start.month == 1 and p_end.month == 12:
                return str(p_start.year)
            return f"{p_start.strftime('%b')} – {p_end.strftime('%b %Y')}"
        fmt = "%b '%y"
        return f"{p_start.strftime(fmt)} – {p_end.strftime(fmt)}"

    _MAX_PRIOR = 10
    windows = []
    for i in range(1, _MAX_PRIOR + 1):
        if period_type == "calendar":
            try:
                p_start = start - pd.DateOffset(years=i)
                p_end = end - pd.DateOffset(years=i)
            except Exception:
                continue
        else:
            shift = pd.Timedelta(days=period_days * i)
            p_start = start - shift
            p_end = end - shift
        if p_end < data_min:
            break
        windows.append((_period_label(p_start, p_end), p_start, p_end))

    prior = []
    for pi, (label, p_start, p_end) in enumerate(windows):
        vals = _cumulative_for_window(df_all, p_start, p_end)
        if vals and any(v > 0 for v in vals):
            if len(vals) < n_days:
                vals = vals + [vals[-1] if vals else 0] * (n_days - len(vals))
            elif len(vals) > n_days:
                vals = vals[:n_days]
            prior.append({"label": label, "values": vals,
                          "color": PRIOR_PERIOD_COLORS[min(pi, len(PRIOR_PERIOD_COLORS) - 1)]})

    has_partial = False
    if prior and windows:
        last_prior_start = windows[len(prior) - 1][1]
        has_partial = last_prior_start.normalize() < data_min.normalize()

    _prior_meta = {
        "periodDays": period_days,
        "maxAvailablePriors": len(prior),
        "hasPartialPrior": has_partial,
    }

    current_label = _period_label(start, end)
    if len(current_vals) < n_days:
        current_vals = current_vals + [None] * (n_days - len(current_vals))

    # Per-slice-per-period breakdown for bar mode
    def _slice_totals_for_window(df, w_start, w_end, sb):
        mask = (df["Created"] >= w_start) & (df["Created"] <= w_end)
        sub = df.loc[mask]
        if sub.empty:
            return {}
        if sb == "total":
            return {"Total": len(sub)}
        if sb == "department" and "Referred by Department" in sub.columns:
            return sub.groupby("Referred by Department").size().to_dict()
        elif sb == "institution" and "DoctorInstitution" in sub.columns:
            return sub.groupby("DoctorInstitution").size().to_dict()
        elif sb == "specialty" and "DeptSpecialty" in sub.columns:
            return sub.groupby("DeptSpecialty").size().to_dict()
        elif sb == "diagnosis":
            sub = sub.copy()
            sub["_dx"] = sub.apply(
                lambda r: _categorise_diagnosis(
                    r.get("Diagnoses"), r.get("Rfl Prim Dx"), r.get("Onc Dx")
                ), axis=1,
            )
            sub = sub[~sub["_dx"].isin(["Other", "Unknown"])]
            return sub.groupby("_dx").size().to_dict()
        elif sb == "status" and "Status" in sub.columns:
            return sub.groupby("Status").size().to_dict()
        return {}

    all_windows_list = [(current_label, start, end)]
    for label, p_start, p_end in windows:
        all_windows_list.append((label, p_start, p_end))

    all_slice_totals = []
    all_slice_keys = set()
    for wlabel, ws, we in all_windows_list:
        totals = _slice_totals_for_window(df_all, ws, we, slice_by)
        all_slice_totals.append((wlabel, totals))
        all_slice_keys.update(totals.keys())

    slice_keys_sorted = sorted(all_slice_keys)
    slice_colors = {k: CHART_COLORWAY[i % len(CHART_COLORWAY)]
                   for i, k in enumerate(slice_keys_sorted)}

    breakdown_periods = [t[0] for t in reversed(all_slice_totals)]
    breakdown_slices = []
    for sk in slice_keys_sorted:
        vals = [t[1].get(sk, 0) for t in reversed(all_slice_totals)]
        breakdown_slices.append({"name": sk, "values": vals, "color": slice_colors[sk]})

    slice_breakdown = {"periods": breakdown_periods, "slices": breakdown_slices}

    avail_priors = max(len(prior), 1)
    slider_max = avail_priors
    slider_marks = [{"value": i, "label": str(i)} for i in range(0, slider_max + 1)]

    if mode == "prior":
        store_data = {
            "mode": "prior",
            "startDate": start_norm.isoformat(),
            "dayIndices": day_indices,
            "tickPositions": tick_positions,
            "tickLabels": tick_labels,
            "current": {
                "label": current_label,
                "values": current_vals,
                "color": PRIMARY,
                "endpoint": current_vals[-1] if current_vals and current_vals[-1] is not None else (
                    next((v for v in reversed(current_vals) if v is not None), 0)
                ),
            },
            "prior": prior,
            "sliceBreakdown": slice_breakdown,
            "height": 350,
            "yTitle": "Cumulative Referrals",
            **_prior_meta,
        }
        if _cy_last_actual is not None:
            apply_current_year_projection(store_data, _cy_last_actual, start)
        return store_data, slider_max, slider_marks

    else:  # mode == "slice"
        mask = (df_all["Created"] >= start) & (df_all["Created"] <= end)
        dff_period = df_all.loc[mask]

        dates_range = pd.date_range(start.normalize(), end.normalize(), freq="D")
        dates_iso = [d.isoformat() for d in dates_range]

        def _trimmed_cumsum(daily_counts):
            cumvals = daily_counts.cumsum().tolist()
            raw = daily_counts.tolist()
            first_idx = next((i for i, v in enumerate(raw) if v > 0), None)
            if first_idx is None:
                return [None] * len(cumvals)
            for i in range(first_idx):
                cumvals[i] = None
            last_idx = next((i for i in range(len(raw) - 1, -1, -1) if raw[i] > 0), first_idx)
            for i in range(last_idx + 1, len(cumvals)):
                cumvals[i] = cumvals[last_idx]
            return cumvals

        series = []

        if slice_by == "department" and "Referred by Department" in dff_period.columns:
            top = dff_period["Referred by Department"].dropna().value_counts().head(10).index.tolist()
            for i, dept in enumerate(top):
                sub = dff_period[dff_period["Referred by Department"] == dept]
                daily = sub.groupby(sub["Created"].dt.normalize()).size()
                daily = daily.reindex(dates_range, fill_value=0)
                series.append({
                    "name": dept[:30],
                    "values": _trimmed_cumsum(daily),
                    "color": CHART_COLORWAY[i % len(CHART_COLORWAY)],
                })

        elif slice_by == "institution" and "DoctorInstitution" in dff_period.columns:
            top = dff_period["DoctorInstitution"].dropna().value_counts().head(10).index.tolist()
            for i, inst in enumerate(top):
                sub = dff_period[dff_period["DoctorInstitution"] == inst]
                daily = sub.groupby(sub["Created"].dt.normalize()).size()
                daily = daily.reindex(dates_range, fill_value=0)
                series.append({
                    "name": inst[:30],
                    "values": _trimmed_cumsum(daily),
                    "color": CHART_COLORWAY[i % len(CHART_COLORWAY)],
                })

        elif slice_by == "specialty" and "DeptSpecialty" in dff_period.columns:
            top = dff_period["DeptSpecialty"].dropna().value_counts().head(10).index.tolist()
            for i, spec in enumerate(top):
                sub = dff_period[dff_period["DeptSpecialty"] == spec]
                daily = sub.groupby(sub["Created"].dt.normalize()).size()
                daily = daily.reindex(dates_range, fill_value=0)
                series.append({
                    "name": spec[:30],
                    "values": _trimmed_cumsum(daily),
                    "color": CHART_COLORWAY[i % len(CHART_COLORWAY)],
                })

        elif slice_by == "diagnosis":
            dff_p = dff_period.copy()
            dff_p["_dx"] = dff_p.apply(
                lambda r: _categorise_diagnosis(
                    r.get("Diagnoses"), r.get("Rfl Prim Dx"), r.get("Onc Dx")
                ), axis=1,
            )
            dff_dx = dff_p[~dff_p["_dx"].isin(["Other", "Unknown"])]
            top = dff_dx["_dx"].value_counts().head(8).index.tolist()
            for i, dx in enumerate(top):
                sub = dff_dx[dff_dx["_dx"] == dx]
                daily = sub.groupby(sub["Created"].dt.normalize()).size()
                daily = daily.reindex(dates_range, fill_value=0)
                series.append({
                    "name": dx,
                    "values": _trimmed_cumsum(daily),
                    "color": CHART_COLORWAY[i % len(CHART_COLORWAY)],
                })

        elif slice_by == "site":
            dff_period = dff_period.copy()
            dff_period["_our_dept"] = dff_period["Referred to Department"].apply(_map_to_our_dept)
            for dept in DEPARTMENTS:
                sub = dff_period[dff_period["_our_dept"] == dept]
                if sub.empty:
                    continue
                daily = sub.groupby(sub["Created"].dt.normalize()).size()
                daily = daily.reindex(dates_range, fill_value=0)
                series.append({
                    "name": dept,
                    "values": _trimmed_cumsum(daily),
                    "color": DEPARTMENT_COLORS.get(dept, CHART_COLORWAY[0]),
                })

        store_data = {
            "mode": "slice",
            "dates": dates_iso,
            "series": series,
            "sliceBreakdown": slice_breakdown,
            "height": 350,
            "yTitle": "Cumulative Referrals",
            **_prior_meta,
        }
        return store_data, slider_max, slider_marks


# ---------------------------------------------------------------------------
# Dimension-grouped Trend + Comparison (like Diagnosis page)
# ---------------------------------------------------------------------------

_DIM_TOP_N = 15  # max groups in trend/comparison

# Stable colorway for dimension groups
_DIM_COLORS = [
    "#7C2A83", "#2196F3", "#F44336", "#4CAF50", "#FF9800",
    "#00BCD4", "#9C27B0", "#795548", "#E91E63", "#3F51B5",
    "#8BC34A", "#FF5722", "#607D8B", "#009688", "#CDDC39",
]


def _assign_dimension_group(df, dimension, payor_mode="broad"):
    """Add _dim_group column based on the chosen dimension.

    dimension: "provider" | "department" | "institution" | "specialty" |
               "diagnosis" | "payor"
    payor_mode: "actual" | "broad" | "phdsc" — only used when dimension="payor"
    Returns df with _dim_group column (rows with None/_dim_group==None dropped).
    """
    df = df.copy()
    if dimension == "provider":
        col = "Referred by Provider"
        if col not in df.columns:
            df["_dim_group"] = None
        else:
            df["_dim_group"] = df[col]
    elif dimension == "department":
        col = "Referred by Department"
        if col not in df.columns:
            df["_dim_group"] = None
        else:
            df["_dim_group"] = df[col].apply(
                lambda v: v if len(str(v)) <= 40 else str(v)[:37] + "..."
                if pd.notna(v) else None
            )
    elif dimension == "institution":
        col = "DoctorInstitution"
        if col not in df.columns:
            df["_dim_group"] = None
        else:
            df["_dim_group"] = df[col].apply(
                lambda v: v if len(str(v)) <= 40 else str(v)[:37] + "..."
                if pd.notna(v) else None
            )
    elif dimension == "specialty":
        col = "DeptSpecialty"
        if col not in df.columns:
            df["_dim_group"] = None
        else:
            df["_dim_group"] = df[col]
    elif dimension == "diagnosis":
        df["_dim_group"] = df.apply(
            lambda r: _categorise_diagnosis(
                r.get("Diagnoses"), r.get("Rfl Prim Dx"), r.get("Onc Dx")
            ),
            axis=1,
        )
        # Drop "Other" from diagnosis grouping for cleaner charts
        df.loc[df["_dim_group"] == "Other", "_dim_group"] = None
    elif dimension == "payor":
        if "Payer" not in df.columns:
            df["_dim_group"] = None
        else:
            mapping = _get_payor_mapping()
            primary = df["Payer"].apply(_extract_primary_payor)
            df["_dim_group"] = _payor_mode_groups(
                primary, payor_mode or "broad", mapping,
            )
    else:
        df["_dim_group"] = None

    df = df[df["_dim_group"].notna()]
    return df


def _dim_color_map(groups):
    """Return {group_name: hex_color} for a list of group names."""
    return {g: _DIM_COLORS[i % len(_DIM_COLORS)] for i, g in enumerate(groups)}


def _prepare_ref_trend_store(df, dimension):
    """Build per-group time-series data for W/M/Y aggregation.

    Same JSON format as diagnosis page, consumed by referralRidge.renderTrend.
    """
    if df.empty or "_dim_group" not in df.columns or "Created" not in df.columns:
        return None

    tmp = df[["Created", "_dim_group"]].dropna(subset=["Created"]).copy()

    # Limit to top N groups by total count
    group_counts = tmp["_dim_group"].value_counts()
    top_groups = group_counts.head(_DIM_TOP_N).index.tolist()
    tmp = tmp[tmp["_dim_group"].isin(top_groups)]

    groups = list(reversed(
        tmp["_dim_group"].value_counts().index.tolist()
    ))  # ascending (bottom→top)
    if not groups:
        return None

    cmap = _dim_color_map(groups)

    combos = {}
    for agg in ("W", "M", "Y"):
        period_code = "Y" if agg == "Y" else agg
        t = tmp.copy()
        t["period"] = t["Created"].dt.to_period(period_code).dt.to_timestamp()
        all_periods = sorted(t["period"].unique())
        dates = [d.isoformat() for d in all_periods]

        series = []
        for grp in groups:
            sub = t[t["_dim_group"] == grp]
            counts = sub.groupby("period").size().reindex(all_periods, fill_value=0)
            series.append({
                "name": grp,
                "values": counts.tolist(),
                "color": cmap.get(grp, CHART_COLORWAY[0]),
            })

        combos[agg] = {"dates": dates, "series": series}

    return {"combos": combos, "groups": groups, "height": _DIM_RIDGE_HEIGHT}


def _period_label(start, end):
    """Smart period label for date ranges."""
    same_year = start.year == end.year
    same_month = same_year and start.month == end.month
    if same_month:
        return start.strftime("%b %Y")
    if same_year:
        if start.month == 1 and end.month == 12:
            return str(start.year)
        return f"{start.strftime('%b')} – {end.strftime('%b %Y')}"
    return f"{start.strftime('%b %y')} – {end.strftime('%b %y')}"


def _build_ref_comparison_bars(dff_curr, prior_windows, start, end):
    """Horizontal grouped bar chart: current vs N prior periods per dimension group.

    Args:
        dff_curr: Current period dataframe (with _dim_group column)
        prior_windows: list of (dff_prior, prior_start, prior_end) tuples
        start, end: Current period boundaries
    """
    if dff_curr.empty or "_dim_group" not in dff_curr.columns:
        fig = empty_figure("No data for selected filters")
        fig.update_layout(height=_DIM_RIDGE_HEIGHT)
        return fig

    curr_label = _period_label(start, end)
    curr_counts = dff_curr["_dim_group"].value_counts()

    # Build prior count series + labels
    prior_data = []  # list of (label, counts_series)
    for dff_p, ps, pe in prior_windows:
        label = _period_label(ps, pe)
        counts = (
            dff_p["_dim_group"].value_counts()
            if dff_p is not None and not dff_p.empty and "_dim_group" in dff_p.columns
            else pd.Series(dtype=int)
        )
        prior_data.append((label, counts))

    # Collect all groups across current + all priors
    all_group_set = set(curr_counts.index)
    for _, pc in prior_data:
        all_group_set.update(pc.index)

    # Sort by absolute change vs most recent prior (biggest movers first),
    # or by current count if no prior periods
    first_prior = prior_data[0][1] if prior_data else pd.Series(dtype=int)
    if prior_data:
        all_groups = sorted(
            all_group_set,
            key=lambda g: abs(curr_counts.get(g, 0) - first_prior.get(g, 0)),
            reverse=True,
        )
    else:
        all_groups = sorted(all_group_set, key=lambda g: curr_counts.get(g, 0), reverse=True)
    all_groups = all_groups[:_DIM_TOP_N]
    # Re-sort ascending by current count for horizontal bar display (largest at top)
    all_groups = sorted(all_groups, key=lambda g: curr_counts.get(g, 0))

    cmap = _dim_color_map(all_groups)
    curr_vals = [int(curr_counts.get(g, 0)) for g in all_groups]

    fig = go.Figure()

    # Prior bars (furthest back first, progressively lighter)
    gray_alphas = [0.45, 0.30, 0.18]
    for idx in range(len(prior_data) - 1, -1, -1):
        plabel, pcounts = prior_data[idx]
        pvals = [int(pcounts.get(g, 0)) for g in all_groups]
        alpha = gray_alphas[idx] if idx < len(gray_alphas) else 0.15
        fig.add_trace(go.Bar(
            x=pvals, y=all_groups, orientation="h",
            marker_color=f"rgba(156, 163, 175, {alpha})",
            name=plabel,
            text=[f"{v:,}" for v in pvals],
            # Always render labels outside the bar — keeps text readable on
            # the washed-out prior fills and on narrow current bars alike.
            textposition="outside",
            textangle=0,
            # #1F2937 (dark slate) is the annotation-strong pair: dark on
            # light bg, white on dark bg (swapped by 02_theme.js).
            # #4B5563 is the annotation-neutral pair: mid-gray in light,
            # white in dark (swapped by 02_theme.js). Outside the bar puts
            # the text on the page bg (high contrast) rather than the
            # washed-out prior fill (low contrast).
            textfont=dict(size=11, color="#4B5563"),
            cliponaxis=False,
            hovertemplate=[
                f"<b>{g}</b><br>{plabel}: {v:,}<extra></extra>"
                for g, v in zip(all_groups, pvals)
            ],
        ))

    # Current bars (front, colored per group)
    bar_colors = [cmap.get(g, CHART_COLORWAY[0]) for g in all_groups]
    fig.add_trace(go.Bar(
        x=curr_vals, y=all_groups, orientation="h",
        marker_color=bar_colors,
        name=curr_label,
        text=[f"{v:,}" for v in curr_vals],
        textposition="outside",
        textangle=0,
        textfont=dict(size=11, color="#1F2937"),
        cliponaxis=False,
        hovertemplate=[
            f"<b>{g}</b><br>{curr_label}: {v:,}<extra></extra>"
            for g, v in zip(all_groups, curr_vals)
        ],
    ))

    # Delta annotations: compare current vs most recent prior (skip if no priors)
    annotations = []
    if prior_data:
        first_prior_vals = [int(first_prior.get(g, 0)) for g in all_groups]
        all_vals = curr_vals + first_prior_vals
        for _, pc in prior_data:
            all_vals += [int(pc.get(g, 0)) for g in all_groups]
        max_val = max(all_vals) if all_vals else 0
        annot_x = max_val * 1.05 if max_val > 0 else 1

        for i, g in enumerate(all_groups):
            c, p = curr_vals[i], first_prior_vals[i]
            if p > 0:
                pct = (c - p) / p * 100
                if pct > 0:
                    txt, color = f"▲ {pct:.0f}%", "#10B981"
                elif pct < 0:
                    txt, color = f"▼ {abs(pct):.0f}%", "#EF4444"
                else:
                    txt, color = "—", "#9CA3AF"
            elif c > 0:
                txt, color = "● new", "#3B82F6"
            else:
                continue
            annotations.append(dict(
                x=annot_x, y=g, text=txt, showarrow=False,
                font=dict(size=12, color=color, family=FONT_FAMILY),
                xanchor="left", yanchor="middle",
            ))
    else:
        max_val = max(curr_vals) if curr_vals else 0
        annot_x = max_val * 1.05 if max_val > 0 else 1

    apply_default_layout(fig, barmode="group")
    fig.update_layout(
        height=_DIM_RIDGE_HEIGHT,
        xaxis_title="", yaxis_title="",
        xaxis=dict(visible=False, range=[0, annot_x * 1.15]),
        yaxis=dict(
            automargin="left+top+bottom", ticklabelstandoff=0,
            categoryorder="array", categoryarray=all_groups,
            tickfont=dict(size=11),
        ),
        margin=dict(l=0, r=60, t=24, b=12),
        showlegend=True,
        legend=dict(
            orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0,
            font=dict(size=11),
        ),
        bargroupgap=0.15,
        annotations=annotations,
    )
    return fig


def _build_detail_table(df):
    """Return (rowData, columnDefs) for the accordion AG Grid detail table."""
    if df.empty:
        return [], []

    df = df.copy()

    # Mapped diagnosis category
    df["Dx Category"] = df.apply(
        lambda r: _categorise_diagnosis(
            r.get("Diagnoses"), r.get("Rfl Prim Dx"), r.get("Onc Dx")
        ),
        axis=1,
    )

    # Full address: "Street, City, ST Zip"
    addr_parts = ["Referring Provider Address", "Referring Provider City",
                   "Referring Provider State", "Referring Provider Zip Code"]
    if any(c in df.columns for c in addr_parts):
        street = df.get("Referring Provider Address", pd.Series("", index=df.index)).fillna("")
        city = df.get("Referring Provider City", pd.Series("", index=df.index)).fillna("")
        state = df.get("Referring Provider State", pd.Series("", index=df.index)).fillna("")
        zipcode = df.get("Referring Provider Zip Code", pd.Series("", index=df.index)).fillna("").astype(str)
        city_st_zip = (city.str.strip() + ", " + state.str.strip() + " " + zipcode.str.strip()).str.strip(", ")
        df["Address"] = (street.str.strip() + ", " + city_st_zip).str.strip(", ")
        df.loc[df["Address"].str.strip() == "", "Address"] = pd.NA

    # Simplify "Referred to Department" → Lacey / Centralia / Aberdeen
    if "Referred to Department" in df.columns:
        df["Referred to Department"] = df["Referred to Department"].apply(_map_to_our_dept)

    # Date columns → ISO (YYYY-MM-DD) for proper sorting; valueFormatter handles display
    date_cols = ["Created", "First Appt", "Authorized On", "CVBookedDate"]
    for col in date_cols:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce").dt.strftime("%Y-%m-%d")

    # Column mapping: source → display name (order = display order)
    display_cols = {
        "Created": "Created",
        "Patient Name": "Patient",
        "MRN": "MRN",
        "Payer": "Payor",
        "Referred by Provider": "Referring Provider",
        "DoctorInstitution": "Institution",
        "Referred by Department": "Referring Dept",
        "Address": "Address",
        "Referred to Department": "Referred to Site",
        "Dx Category": "Dx Category",
        "Diagnoses": "Raw Diagnosis",
        "Rfl Prim Dx": "Primary Dx",
        "Authorized On": "Authorized",
        "CVBookedDate": "Scheduled",
        "First Appt": "First Appt",
        "Days to Assign": "Days to Assign",
        "Days to Auth": "Days to Auth",
        "Auth to Appt": "Auth to Appt",
        "Days to First Appt": "Days to Appt",
        "CVDaysBookedToAppt": "Booked to Appt",
        "CVMatch": "Visit Status",
    }
    available = {k: v for k, v in display_cols.items() if k in df.columns}
    table_df = df[list(available.keys())].rename(columns=available)
    table_df["_row_idx"] = table_df.index  # preserve original index for grid filter
    table_df = table_df.sort_values("Created", ascending=False, na_position="last")
    table_df = sanitize_for_grid(table_df)

    # Column definitions with explicit widths
    col_widths = {
        "Created": 120,
        "Patient": 160,
        "MRN": 90,
        "Payor": 140,
        "Referring Provider": 200,
        "Institution": 180,
        "Referring Dept": 180,
        "Address": 250,
        "Referred to Site": 130,
        "Dx Category": 130,
        "Raw Diagnosis": 200,
        "Primary Dx": 160,
        "Authorized": 120,
        "Scheduled": 120,
        "First Appt": 120,
        "Days to Assign": 120,
        "Days to Auth": 120,
        "Auth to Appt": 120,
        "Days to Appt": 120,
        "Booked to Appt": 125,
        "Visit Status": 120,
    }
    date_display_cols = {"Created", "First Appt", "Authorized", "Scheduled"}
    date_formatter = {
        "function": "params.value ? new Date(params.value + 'T00:00:00').toLocaleDateString('en-US', {month: '2-digit', day: '2-digit', year: 'numeric'}) : '\u2013'"
    }

    column_defs = []
    for col in table_df.columns:
        if col == "_row_idx":
            continue
        col_def = {"field": col, "headerName": col, **DEFAULT_COLUMN_DEFS}
        if col in col_widths:
            col_def["width"] = col_widths[col]
        if col in date_display_cols:
            col_def["valueFormatter"] = date_formatter
        if col == "Created":
            col_def["sort"] = "desc"
        column_defs.append(col_def)

    return table_df.to_dict("records"), column_defs


# ---------------------------------------------------------------------------
# Referral Flow-Gantt Data
# ---------------------------------------------------------------------------

_FLOW_STAGES = ["Created", "Scheduled", "Visit Completed"]
_FLOW_COLORS = ["#7C2A83", "#2196F3", "#4CAF50"]


def _compute_referral_flow_data(df, cap_0=_CAP_CREATED_TO_SCHEDULED, cap_1=_CAP_SCHEDULED_TO_VISIT):
    """Build the data dict consumed by the flow_gantt.js renderer.

    Three reality-based stages:
      Created -> Scheduled (MRN-matched to CV) -> Visit Completed

    Dropoff categories:
      Pending  = appointment is genuinely in the future (First Appt > today)
      Cancelled = referral Denied/Canceled, or CV status is Canceled/No-Show
    """
    if df.empty:
        return None

    stages = list(_FLOW_STAGES)
    n = len(stages)
    today = pd.Timestamp.now().normalize()

    # --- Stage boolean masks ---
    created = pd.Series(True, index=df.index)

    # Scheduled = found in CV OR has a future appointment OR referral says appt attached
    cv_matched = df["CVMatch"].isin([
        "Confirmed", "Rescheduled", "Canceled", "No Show",
    ]) if "CVMatch" in df.columns else created & False
    has_future_appt = (
        df["First Appt"].notna() & (df["First Appt"] >= today)
    ) if "First Appt" in df.columns else created & False
    appt_attached = (df["Appt Attached"] == "Yes") if "Appt Attached" in df.columns else created & False
    scheduled = cv_matched | has_future_appt | appt_attached

    # Visit Completed = CV-confirmed as actually happened
    completed = df["CVMatch"].isin([
        "Confirmed", "Rescheduled",
    ]) if "CVMatch" in df.columns else created & False

    masks = [created, scheduled, completed]
    stage_counts = [int(m.sum()) for m in masks]

    # --- Flow values ---
    flow_values = [
        int((created & scheduled).sum()),
        int((scheduled & completed).sum()),
    ]

    # --- Dropoffs ---
    dropoffs = [
        int((created & ~scheduled).sum()),
        int((scheduled & ~completed).sum()),
    ]

    # --- Pending vs Cancelled in dropoffs ---
    is_cancelled = df["Status"].isin(["Denied", "Canceled"])
    cv_cancelled = df["CVMatch"].isin(["Canceled", "No Show"]) if "CVMatch" in df.columns else created & False

    pending_counts = []
    cancelled_counts = []

    # Drop from Created -> Scheduled (never got an appointment — all are lost/closed)
    drop_0 = created & ~scheduled
    # Pending if status is still active (Pending Review, Authorized, Open)
    is_terminal = df["Status"].isin(["Closed", "Denied", "Canceled"])
    pending_counts.append(int((drop_0 & ~is_terminal).sum()))
    cancelled_counts.append(int((drop_0 & is_terminal).sum()))

    # Drop from Scheduled -> Completed
    drop_1 = scheduled & ~completed
    # Pending = future appt OR appt attached but no CV yet (visit hasn't happened)
    drop_1_pending = drop_1 & (has_future_appt | (appt_attached & ~cv_matched))
    pending_counts.append(int(drop_1_pending.sum()))
    # Cancelled = the rest (CV canceled/no-show or referral denied/canceled)
    cancelled_counts.append(int((drop_1 & ~drop_1_pending).sum()))

    # --- Inter-stage durations (with outlier caps) ---
    def _safe_stat(series, cap, func="median"):
        s = series.dropna()
        s = s[(s >= 0) & (s <= cap)]
        if s.empty:
            return 0.0
        return float(s.median()) if func == "median" else float(s.mean())

    # Created -> Scheduled: days from referral Created to appointment booked
    if "CVBookedDate" in df.columns and "Created" in df.columns:
        d0 = (df["CVBookedDate"] - df["Created"]).dt.days
    else:
        d0 = pd.Series(dtype=float)
    cap_total = cap_0 + cap_1
    median_days = [_safe_stat(d0, cap_0, "median")]
    mean_days = [_safe_stat(d0, cap_0, "mean")]

    # Scheduled -> Completed: days from booked to visit
    d1 = df["CVDaysBookedToAppt"] if "CVDaysBookedToAppt" in df.columns else pd.Series(dtype=float)
    median_days.append(_safe_stat(d1, cap_1, "median"))
    mean_days.append(_safe_stat(d1, cap_1, "mean"))

    # --- True per-patient total (median of individual totals, not sum of medians) ---
    if "CVBookedDate" in df.columns and "CVDaysBookedToAppt" in df.columns:
        _per_patient = (df["CVBookedDate"] - df["Created"]).dt.days + df["CVDaysBookedToAppt"]
        _per_patient = _per_patient[(_per_patient >= 0) & (_per_patient <= cap_total)].dropna()
        total_median = float(_per_patient.median()) if not _per_patient.empty else sum(median_days)
    else:
        total_median = sum(median_days)

    # --- X positions (evenly spaced for 3 stages) ---
    x_positions = [0.0, 0.5, 1.0]

    return {
        "stages": stages,
        "stageKeys": stages,
        "stageCounts": stage_counts,
        "flowValues": flow_values,
        "dropoffs": dropoffs,
        "pendingCounts": pending_counts,
        "cancelledCounts": cancelled_counts,
        "medianDays": median_days,
        "meanDays": mean_days,
        "aggFunc": "median",
        "allottedDays": [None] * (n - 1),
        "onTimePcts": [None] * (n - 1),
        "xPositions": x_positions,
        "colors": _FLOW_COLORS,
        "loopbacks": [0] * n,
        "loopbackPairs": [],
        "totalMedianDays": total_median,
        "totalPatients": stage_counts[0],
        "height": 480,
    }


def _simple_kde(values, n_points=200):
    """Quick KDE for distribution chart (Gaussian kernel, Silverman bandwidth)."""
    arr = np.asarray(values, dtype=float)
    if len(arr) < 2:
        return [0.0], [0.0]
    std = np.std(arr, ddof=1) or 1.0
    bw = 1.06 * std * len(arr) ** -0.2
    lo = max(0, arr.min() - 3 * bw)
    hi = arr.max() + 3 * bw
    x = np.linspace(lo, hi, n_points)
    density = np.zeros(n_points)
    for v in arr:
        density += np.exp(-0.5 * ((x - v) / bw) ** 2)
    density /= len(arr) * bw * np.sqrt(2 * np.pi)
    return [round(float(v), 3) for v in x], [round(float(v), 6) for v in density]


def _compute_referral_flow_details(df, cap_0=_CAP_CREATED_TO_SCHEDULED, cap_1=_CAP_SCHEDULED_TO_VISIT):
    """Compute per-transition detail data for clientside distribution & trend.

    Transitions:
        0: Created -> Scheduled   (days = Days to First Appt)
        1: Scheduled -> Completed (days = |CVDateOffset|, usually 0)
    Total: Created -> Completed   (days = Days to First Appt)
    """
    if df.empty:
        return None

    transitions = []
    today = pd.Timestamp.now().normalize()

    # Helper to build one transition dict
    def _build_transition(days_series, ref_dates, label, color, cap=365):
        days_arr = days_series.dropna().values
        days_arr = days_arr[(days_arr >= 0) & (days_arr <= cap)]
        if len(days_arr) == 0:
            return None

        kde_x, kde_y = _simple_kde(days_arr)

        # Build trend data at monthly granularity
        temp = pd.DataFrame({"_days": days_series, "_ref": ref_dates}).dropna()
        temp = temp[(temp["_days"] >= 0) & (temp["_days"] <= cap)]
        trend_by_agg = {}
        for agg_key in ("W", "M", "Y"):
            temp["_period"] = temp["_ref"].dt.to_period(agg_key).dt.to_timestamp()
            gmed = temp.groupby("_period")["_days"].median()
            gmean = temp.groupby("_period")["_days"].mean()
            gcnt = temp.groupby("_period")["_days"].size()
            all_periods = sorted(gmed.index)
            trend_by_agg[agg_key] = {
                "dates": [d.isoformat() for d in all_periods],
                "medians": [round(float(gmed[d]), 1) for d in all_periods],
                "means": [round(float(gmean[d]), 1) for d in all_periods],
                "kmMedians": [None] * len(all_periods),
                "counts": [int(gcnt.get(d, 0)) for d in all_periods],
                "completionRates": [1.0] * len(all_periods),
            }

        return {
            "label": label,
            "color": color,
            "days": [round(float(d), 3) for d in days_arr],
            "density": {"x": kde_x, "y": kde_y},
            "trendByAgg": trend_by_agg,
            "n": int(len(days_arr)),
            "nCensored": 0,
            "median": round(float(np.median(days_arr)), 3),
            "mean": round(float(np.mean(days_arr)), 3),
            "kmMedian": None,
            "p25": round(float(np.percentile(days_arr, 25)), 3),
            "p75": round(float(np.percentile(days_arr, 75)), 3),
        }

    # Transition 0: Created -> Scheduled (referral created to appt booked)
    if "CVBookedDate" in df.columns and "Created" in df.columns:
        d0 = (df["CVBookedDate"] - df["Created"]).dt.days
    else:
        d0 = pd.Series(dtype=float)
    ref0 = df["Created"] if "Created" in df.columns else pd.Series(dtype="datetime64[ns]")
    transitions.append(_build_transition(
        d0, ref0, "Created \u2192 Scheduled", _FLOW_COLORS[0],
        cap=cap_0,
    ))

    # Transition 1: Scheduled -> Completed (booked to visit)
    d1 = df["CVDaysBookedToAppt"] if "CVDaysBookedToAppt" in df.columns else pd.Series(dtype=float)
    ref1 = df["CVBookedDate"] if "CVBookedDate" in df.columns else pd.Series(dtype="datetime64[ns]")
    transitions.append(_build_transition(
        d1, ref1, "Scheduled \u2192 Visit", _FLOW_COLORS[1],
        cap=cap_1,
    ))

    # Total: Created -> Visit (same methodology as Gantt/KPI: booked + booked-to-visit)
    cap_total = cap_0 + cap_1
    if "CVBookedDate" in df.columns and "CVDaysBookedToAppt" in df.columns:
        d_total = (df["CVBookedDate"] - df["Created"]).dt.days + df["CVDaysBookedToAppt"]
    else:
        d_total = df["Days to First Appt"] if "Days to First Appt" in df.columns else pd.Series(dtype=float)
    total = _build_transition(
        d_total, ref0, "Total: Created \u2192 Visit", PRIMARY,
        cap=cap_total,
    )

    # --- Conversion rate trend data ---
    # For each period: % of referrals created that reached each stage
    conv_by_agg = {}
    for agg_key in ("W", "M", "Y"):
        created_periods = df["Created"].dt.to_period(agg_key).dt.to_timestamp()
        grp = df.groupby(created_periods)
        period_created = grp.size()
        period_scheduled = grp.apply(
            lambda g: ((g["Appt Attached"] == "Yes") if "Appt Attached" in g.columns
                       else pd.Series(False, index=g.index)).sum(),
            include_groups=False,
        )
        period_completed = grp.apply(
            lambda g: (g["CVMatch"].isin(["Confirmed", "Rescheduled"]) if "CVMatch" in g.columns
                       else pd.Series(False, index=g.index)).sum(),
            include_groups=False,
        )
        all_periods = sorted(period_created.index)
        conv_by_agg[agg_key] = {
            "dates": [d.isoformat() for d in all_periods],
            "created": period_created.reindex(all_periods, fill_value=0).tolist(),
            "scheduled": period_scheduled.reindex(all_periods, fill_value=0).tolist(),
            "completed": period_completed.reindex(all_periods, fill_value=0).tolist(),
            "schedPct": [
                round(period_scheduled.get(d, 0) / period_created.get(d, 1) * 100, 1)
                for d in all_periods
            ],
            "completePct": [
                round(period_completed.get(d, 0) / period_created.get(d, 1) * 100, 1)
                for d in all_periods
            ],
        }

    return {
        "transitions": transitions,
        "total": total,
        "aggFunc": "median",
        "convByAgg": conv_by_agg,
    }


# ---------------------------------------------------------------------------
# CV Cross-Validation
# ---------------------------------------------------------------------------

def _cross_validate_with_cv(df):
    """Enrich referrals with clinic-visit match status via tiered MRN matching.

    Adds columns:
        CVMatch: "Confirmed" | "Rescheduled" | "Canceled" | "No Show" | "No CV Match" | "Future" | ""
        CVStatus: raw clinic visit status from best match
        CVDateOffset: days between First Appt and matched CV date (0 = exact)

    Matching tiers:
        1. MRN + exact First Appt date
        2. MRN + first CV visit after referral Created (within reasonable window)
    """
    from data.loader import load_clinic_visits

    df = df.copy()
    df["CVMatch"] = ""
    df["CVStatus"] = ""
    df["CVDateOffset"] = pd.NA
    df["CVBookedDate"] = pd.NaT
    df["CVDaysBookedToAppt"] = pd.NA

    if "MRN" not in df.columns or "First Appt" not in df.columns:
        return df

    try:
        cv = load_clinic_visits()
    except Exception:
        return df

    if cv.empty or "PatientId" not in cv.columns:
        return df

    cv_slim = cv[["PatientId", "ScheduledDateTime", "Status",
                   "AppointmentCreatedDate", "DaysFromCreatedToAppt"]].copy()
    cv_slim["PatientId"] = pd.to_numeric(cv_slim["PatientId"], errors="coerce").astype("Int64")
    cv_slim["_cv_date"] = cv_slim["ScheduledDateTime"].dt.normalize()

    today = pd.Timestamp.now().normalize()

    # Classify referrals without any appt date
    no_appt = df["First Appt"].isna()
    df.loc[no_appt, "CVMatch"] = "No Appt"

    has_appt = df["First Appt"].notna()
    work_idx = df.index[has_appt]
    if work_idx.empty:
        return df

    appt_dates = df.loc[work_idx, "First Appt"].dt.normalize()
    is_future = appt_dates >= today

    # --- Vectorised CV status classifier ---
    def _classify_cv(status_series, default_match):
        """Vectorised: map CV status string to CVMatch label."""
        s = status_series.fillna("").astype(str)
        result = pd.Series(default_match, index=s.index)
        result[s.str.contains("Cancel", case=False)] = "Canceled"
        result[s.str.contains("No Show", case=False)] = "No Show"
        return result

    # --- Tier 1: MRN + exact date (vectorised merge) ---
    cv_dedup = cv_slim.drop_duplicates(subset=["PatientId", "_cv_date"], keep="first")
    t1_keys = pd.DataFrame({
        "Referral ID": df.loc[work_idx, "Referral ID"].values,
        "MRN": df.loc[work_idx, "MRN"].values,
        "_appt_date": appt_dates.values,
        "_orig_idx": work_idx,
    })
    tier1 = t1_keys.merge(
        cv_dedup[["PatientId", "_cv_date", "Status",
                  "AppointmentCreatedDate", "DaysFromCreatedToAppt"]].rename(
            columns={"Status": "_cvs"}),
        left_on=["MRN", "_appt_date"],
        right_on=["PatientId", "_cv_date"],
        how="left",
    ).drop_duplicates(subset="Referral ID", keep="first")

    matched_t1 = tier1["_cvs"].notna()
    if matched_t1.any():
        t1_hit = tier1.loc[matched_t1].set_index("_orig_idx")
        df.loc[t1_hit.index, "CVStatus"] = t1_hit["_cvs"].values
        df.loc[t1_hit.index, "CVDateOffset"] = 0
        df.loc[t1_hit.index, "CVBookedDate"] = t1_hit["AppointmentCreatedDate"].values
        df.loc[t1_hit.index, "CVDaysBookedToAppt"] = t1_hit["DaysFromCreatedToAppt"].values
        # Past visits → Confirmed; future visits → Future (scheduled but not yet seen)
        future_idx = t1_hit.index[t1_hit.index.isin(df.index[is_future.reindex(df.index, fill_value=False)])]
        past_idx = t1_hit.index.difference(future_idx)
        if len(past_idx):
            df.loc[past_idx, "CVMatch"] = _classify_cv(
                df.loc[past_idx, "CVStatus"], "Confirmed"
            ).values
        if len(future_idx):
            df.loc[future_idx, "CVMatch"] = "Future"

    # --- Tier 2: MRN + first post-referral CV visit (vectorised) ---
    unmatched = tier1.loc[~matched_t1]
    if not unmatched.empty:
        t2_keys = unmatched[["Referral ID", "MRN", "_appt_date", "_orig_idx"]].copy()
        t2_keys["_created"] = df.loc[t2_keys["_orig_idx"].values, "Created"].dt.normalize().values

        t2_joined = t2_keys.merge(
            cv_slim[["PatientId", "_cv_date", "Status",
                      "AppointmentCreatedDate", "DaysFromCreatedToAppt"]],
            left_on="MRN", right_on="PatientId", how="inner",
        )
        # Keep only visits on or after referral created
        t2_joined = t2_joined[t2_joined["_cv_date"] >= t2_joined["_created"]]

        if not t2_joined.empty:
            t2_joined = t2_joined.sort_values("_cv_date")
            t2_first = t2_joined.drop_duplicates(subset="Referral ID", keep="first")
            t2_first["_offset"] = (t2_first["_cv_date"] - t2_first["_appt_date"]).dt.days

            # Map back to original index
            t2_map = t2_first.set_index("Referral ID")[
                ["Status", "_offset", "_orig_idx",
                 "AppointmentCreatedDate", "DaysFromCreatedToAppt"]
            ]
            oidx = t2_map["_orig_idx"].values
            df.loc[oidx, "CVStatus"] = t2_map["Status"].values
            df.loc[oidx, "CVDateOffset"] = t2_map["_offset"].astype(int).values
            df.loc[oidx, "CVMatch"] = _classify_cv(t2_map["Status"], "Rescheduled").values
            df.loc[oidx, "CVBookedDate"] = t2_map["AppointmentCreatedDate"].values
            df.loc[oidx, "CVDaysBookedToAppt"] = t2_map["DaysFromCreatedToAppt"].values

    # Still blank + future appt → Future; still blank + past appt → No CV Match
    still_blank = has_appt & (df["CVMatch"] == "")
    future_blank = still_blank & is_future.reindex(df.index, fill_value=False)
    past_blank = still_blank & ~future_blank
    df.loc[future_blank, "CVMatch"] = "Future"
    df.loc[past_blank, "CVMatch"] = "No CV Match"

    return df


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _apply_grid_row_filter(dff, grid_rows):
    """Filter dff to only rows matching the grid's visible row indices."""
    if grid_rows is None or dff is None or dff.empty:
        return dff
    idx_set = set(int(i) for i in grid_rows)
    return dff.loc[dff.index.isin(idx_set)].reset_index(drop=True)


def _trend(curr, prior, invert=False):
    """Return (pct_text, direction, prior_value) for trend display."""
    if prior is None or prior == 0:
        return None, None, None
    pct = (curr - prior) / prior * 100
    direction = ("down" if pct > 0 else "up") if invert else ("up" if pct > 0 else "down")
    return f"{abs(pct):.0f}%", direction, prior


def _prior_range(start, end):
    """Return (prior_start, prior_end) of equal length before the current range."""
    delta = end - start
    return start - delta - timedelta(days=1), start - timedelta(days=1)


# ---------------------------------------------------------------------------
# Main Server Callback
# ---------------------------------------------------------------------------

@callback(
    Output(f"{PAGE_ID}-kpi-row", "children"),
    Output(f"{PAGE_ID}-store-flow-gantt", "data"),
    Output(f"{PAGE_ID}-store-flow-details", "data"),
    Output(f"{PAGE_ID}-detail-grid", "rowData"),
    Output(f"{PAGE_ID}-detail-grid", "columnDefs"),
    Output(f"{PAGE_ID}-chart-dim-trend-store", "data"),
    Output(f"{PAGE_ID}-store-dim-compare-figs", "data"),
    Output(f"{PAGE_ID}-filter-specialty", "data"),
    Output(f"{PAGE_ID}-filter-institution", "data"),
    Output(f"{PAGE_ID}-filter-provider", "data"),
    Output(f"{PAGE_ID}-dim-compare-period", "data"),
    Output(f"{PAGE_ID}-dim-compare-period", "value"),
    Output(f"{PAGE_ID}-dim-compare-settings-prior-periods", "max"),
    Output(f"{PAGE_ID}-dim-compare-settings-prior-periods", "marks"),
    Output(f"{PAGE_ID}-store-kpi-sparklines", "data"),
    Output(f"{PAGE_ID}-store-map-geo", "data"),
    # Inputs
    Input(f"{PAGE_ID}-interval", "n_intervals"),
    Input(f"{PAGE_ID}-filter-daterange", "start_date"),
    Input(f"{PAGE_ID}-filter-daterange", "end_date"),
    Input(f"{PAGE_ID}-filter-department", "value"),
    Input(f"{PAGE_ID}-filter-specialty", "value"),
    Input(f"{PAGE_ID}-filter-institution", "value"),
    Input(f"{PAGE_ID}-filter-provider", "value"),
    Input(f"{PAGE_ID}-diag-store", "data"),
    Input(f"{PAGE_ID}-diag-mode", "data"),
    Input(f"{PAGE_ID}-diag-subcategory", "value"),
    Input(f"{PAGE_ID}-outlier-enabled", "data"),
    Input(f"{PAGE_ID}-outlier-cap-0", "value"),
    Input(f"{PAGE_ID}-outlier-cap-1", "value"),
    Input(f"{PAGE_ID}-pipeline-window", "value"),
    Input(f"{PAGE_ID}-dim-toggle", "value"),
    Input(f"{PAGE_ID}-dim-compare-period", "value"),
    Input(f"{PAGE_ID}-table-filter-rows", "data"),
    Input(f"{PAGE_ID}-filter-payor-mode", "value"),
    Input(f"{PAGE_ID}-filter-payor", "value"),
    running=[
        (Output(f"{PAGE_ID}-chart-dim-trend-loading", "visible"), True, False),
        (Output(f"{PAGE_ID}-chart-dim-comparison-loading", "visible"), True, False),
        (Output(f"{PAGE_ID}-flow-dist-loading", "visible"), True, False),
        (Output(f"{PAGE_ID}-flow-trend-loading", "visible"), True, False),
        (Output(f"{PAGE_ID}-flow-conv-loading", "visible"), True, False),
        (Output(f"{PAGE_ID}-flow-gantt-loading", "visible"), True, False),
        (Output(f"{PAGE_ID}-map-loading", "visible"), True, False),
    ],
)
def update_referrals(_n, start_date, end_date, departments, specialty_filter,
                     institution_filter, provider_filter, diag_cats, diag_mode, diag_subs,
                     outlier_enabled, cap_0, cap_1,
                     pipeline_window, dim_toggle, dim_compare_period, grid_rows,
                     payor_mode, payor_selected):
    """Master callback: KPIs + all charts."""
    from data.loader import load_referrals, load_referring

    # Resolve outlier caps (dynamic from sliders, or disabled)
    if not outlier_enabled:
        cap_0 = 365
        cap_1 = 365
    cap_0 = cap_0 or _CAP_CREATED_TO_SCHEDULED
    cap_1 = cap_1 or _CAP_SCHEDULED_TO_VISIT
    cap_total = cap_0 + cap_1

    empty = empty_figure("No data")
    empty_kpis = [kpi_card("--", "N/A")] * 5
    empty_dim = empty_figure("No data for selected filters")
    empty_dim.update_layout(height=_DIM_RIDGE_HEIGHT)
    no_spec = []
    no_inst = []
    no_prov = []
    no_ctrl = (dash.no_update, dash.no_update, dash.no_update, dash.no_update)
    empty_out = (empty_kpis, None, None,
                 [], [], None, {}, no_spec, no_inst, no_prov) + no_ctrl + ({}, None)

    try:
        df = load_referrals()
        df = _cross_validate_with_cv(df)
    except Exception:
        return empty_out

    if df.empty:
        return empty_out

    # --- Date filter ---
    if start_date and end_date:
        s = pd.Timestamp(start_date)
        e = pd.Timestamp(end_date) + timedelta(days=1)
        df = df[(df["Created"] >= s) & (df["Created"] < e)]

    if df.empty:
        return empty_out

    # --- Department filter ---
    # Map "Referred to Department" (our site) to Lacey/Centralia/Aberdeen
    if departments and "Referred to Department" in df.columns:
        our_dept = df["Referred to Department"].apply(_map_to_our_dept)
        df = df[our_dept.isin(departments)]

    # --- Build specialty options (after dept filter, before specialty filter) ---
    spec_options = []
    if "DeptSpecialty" in df.columns:
        spec_options = sorted(df["DeptSpecialty"].dropna().unique().tolist())
        if specialty_filter:
            sel = list(specialty_filter)
            sel_set = set(sel)
            opt_set = set(spec_options)
            extras = [s for s in sel if s not in opt_set]
            others = [s for s in spec_options if s not in sel_set]
            spec_options = [s for s in sel if s in opt_set] + extras + others

    # --- Specialty filter ---
    if specialty_filter and "DeptSpecialty" in df.columns:
        df = df[df["DeptSpecialty"].isin(specialty_filter)]

    # --- Build institution options (after dept+specialty, before inst filter) ---
    inst_options = []
    if "DoctorInstitution" in df.columns:
        inst_options = sorted(df["DoctorInstitution"].dropna().astype(str).str.strip()
                              .loc[lambda s: s != ""].unique().tolist())
        if institution_filter:
            sel = list(institution_filter)
            sel_set = set(sel)
            opt_set = set(inst_options)
            extras = [s for s in sel if s not in opt_set]
            others = [s for s in inst_options if s not in sel_set]
            inst_options = [s for s in sel if s in opt_set] + extras + others

    # --- Institution filter ---
    if institution_filter and "DoctorInstitution" in df.columns:
        df = df[df["DoctorInstitution"].isin(institution_filter)]

    # --- Build provider options (after dept+spec+inst, before provider filter) ---
    prov_options = []
    if "Referred by Provider" in df.columns:
        prov_options = sorted(
            df["Referred by Provider"].dropna().astype(str).str.strip()
            .loc[lambda s: s != ""].unique().tolist()
        )
        # Float currently-selected providers to the top of the list so the
        # user can see/untick them without scrolling. Selected providers
        # outside the current cohort (e.g. picked before tightening dept
        # filter) are also surfaced.
        if provider_filter:
            sel = list(provider_filter)
            sel_set = set(sel)
            others = [p for p in prov_options if p not in sel_set]
            # Include any selected that aren't in the current option set
            extras = [p for p in sel if p not in prov_options]
            prov_options = [p for p in sel if p in set(prov_options)] + extras + others

    # --- Provider filter (multi-select) ---
    if provider_filter and "Referred by Provider" in df.columns:
        df = df[df["Referred by Provider"].isin(provider_filter)]

    # --- Diagnosis filter (accordion: categories + optional subcategories) ---
    if diag_cats:
        df["_diag_filt"] = df.apply(
            lambda r: _categorise_diagnosis(
                r.get("Diagnoses"), r.get("Rfl Prim Dx"), r.get("Onc Dx")
            ),
            axis=1,
        )
        cat_set = set(diag_cats)
        if diag_subs:
            cat_set.update(diag_subs)
        df = df[df["_diag_filt"].isin(cat_set)]
        df = df.drop(columns=["_diag_filt"])

    # --- Payor filter ---
    if payor_selected:
        df = _apply_payor_filter(df, payor_selected, payor_mode)

    if df.empty:
        return empty_out

    # Keep the full filtered set for charts that need all data
    all_data = df.reset_index(drop=True)

    # --- KPI Calculations ---
    total = len(df)
    converted = (df["Appt Attached"] == "Yes").sum()
    conv_rate = converted / total * 100 if total else 0
    # Median days: Created → booked + booked → visit (same as Gantt total)
    if "CVBookedDate" in df.columns and "CVDaysBookedToAppt" in df.columns:
        _d_to_book = (df["CVBookedDate"] - df["Created"]).dt.days
        _d_book_to_visit = df["CVDaysBookedToAppt"]
        _total_days = _d_to_book + _d_book_to_visit
        _total_days = _total_days[(_total_days >= 0) & (_total_days <= cap_total)]
        median_days = _total_days.median()
    else:
        median_days = df["Days to First Appt"].median()
    # True pending = not yet completed, waiting — capped to pipeline window
    # to exclude stale referrals that were never closed/denied but are
    # effectively abandoned.
    _pw = pipeline_window or 90
    _today = pd.Timestamp.now().normalize()
    _pending_cutoff = _today - pd.Timedelta(days=_pw)
    _recent = df["Created"] >= _pending_cutoff
    _cv_matched = df["CVMatch"].isin(["Confirmed", "Rescheduled", "Canceled", "No Show"]) if "CVMatch" in df.columns else pd.Series(False, index=df.index)
    _has_future = (df["First Appt"].notna() & (df["First Appt"] >= _today)) if "First Appt" in df.columns else pd.Series(False, index=df.index)
    _appt_att = (df["Appt Attached"] == "Yes") if "Appt Attached" in df.columns else pd.Series(False, index=df.index)
    _scheduled = _cv_matched | _has_future | _appt_att
    _completed = df["CVMatch"].isin(["Confirmed", "Rescheduled"]) if "CVMatch" in df.columns else pd.Series(False, index=df.index)
    _is_terminal = df["Status"].isin(["Closed", "Denied", "Canceled"])
    # Pending off Created (not scheduled, not terminal, within pipeline window)
    _p0 = (_recent & ~_scheduled & ~_is_terminal).sum()
    # Pending off Scheduled (has a future appointment but not yet completed)
    _p1 = (_has_future & ~_completed).sum()
    pending = int(_p0 + _p1)
    unique_mds = df["Referred by Provider"].dropna().nunique()
    denied_canceled = len(df[df["Status"].isin(["Denied", "Canceled"])])
    denial_rate = denied_canceled / total * 100 if total else 0

    # Prior period for trends
    if start_date and end_date:
        ps, pe = _prior_range(pd.Timestamp(start_date), pd.Timestamp(end_date))
        prior_df = load_referrals()
        prior_df = prior_df[(prior_df["Created"] >= ps) & (prior_df["Created"] < pe + timedelta(days=1))]
        if departments and "Referred to Department" in prior_df.columns:
            p_dept = prior_df["Referred to Department"].apply(_map_to_our_dept)
            prior_df = prior_df[p_dept.isin(departments)]
        prior_total = len(prior_df) if not prior_df.empty else None
        prior_conv = ((prior_df["Appt Attached"] == "Yes").sum() / prior_total * 100
                      if prior_total else None)
        prior_median = prior_df["Days to First Appt"].median() if not prior_df.empty else None
        prior_mds = prior_df["Referred by Provider"].dropna().nunique() if not prior_df.empty else None
    else:
        prior_total = prior_conv = prior_median = prior_mds = None

    # --- Sparkline data (monthly) ---
    spark_df = df.copy()
    spark_df["_month"] = spark_df["Created"].dt.to_period("M").dt.to_timestamp()
    monthly_grp = spark_df.groupby("_month")

    sp_total = monthly_grp.size()
    sp_conv = monthly_grp.apply(
        lambda g: (g["Appt Attached"] == "Yes").sum() / len(g) * 100 if len(g) else 0,
        include_groups=False,
    )
    # Sparkline lead time: same methodology as KPI (Created→booked + booked→visit)
    if "CVBookedDate" in spark_df.columns and "CVDaysBookedToAppt" in spark_df.columns:
        spark_df["_total_days"] = (spark_df["CVBookedDate"] - spark_df["Created"]).dt.days + spark_df["CVDaysBookedToAppt"]
        spark_df.loc[(spark_df["_total_days"] < 0) | (spark_df["_total_days"] > cap_total), "_total_days"] = pd.NA
        sp_lead = spark_df.groupby("_month")["_total_days"].median()
    else:
        sp_lead = monthly_grp["Days to First Appt"].median()
    sp_mds = monthly_grp["Referred by Provider"].nunique()

    # Drop partial last month
    for sp in [sp_total, sp_conv, sp_lead, sp_mds]:
        if len(sp) > 1 and sp.index[-1].month == pd.Timestamp.now().month:
            sp.drop(sp.index[-1], inplace=True, errors="ignore")

    sp_labels = [d.strftime("%Y-%m-%d") for d in sp_total.index]

    # Build sparkline store data for clientside smoothing
    sparkline_store = {
        "total": {"labels": sp_labels, "values": sp_total.tolist(), "color": PRIMARY},
        "conv": {"labels": sp_labels, "values": sp_conv.tolist(), "color": SEMANTIC_COLORS["success"]},
        "lead": {"labels": sp_labels, "values": [v if pd.notna(v) else 0 for v in sp_lead.tolist()], "color": CHART_COLORWAY[1]},
        "mds": {"labels": sp_labels, "values": sp_mds.tolist(), "color": CHART_COLORWAY[5]},
    }

    # Build KPIs
    t1, d1, p1 = _trend(total, prior_total)
    kpi_total = kpi_card(
        "Total Referrals", f"{total:,}",
        trend_text=f"{t1} vs prior ({p1:,.0f})" if t1 else None,
        trend_direction=d1, accent_color=PRIMARY,
        sparkline_id=f"{PAGE_ID}-spark-total",
    )

    t2, d2, p2 = _trend(conv_rate, prior_conv)
    kpi_conv = kpi_card(
        "Conversion Rate", f"{conv_rate:.1f}%",
        trend_text=f"{t2} vs prior ({p2:.1f}%)" if t2 else None,
        trend_direction=d2, accent_color=SEMANTIC_COLORS["success"],
        sparkline_id=f"{PAGE_ID}-spark-conv",
    )

    t3, d3, p3 = _trend(median_days, prior_median, invert=True)
    kpi_lead = kpi_card(
        "Median Days to Appt", f"{median_days:.0f}" if pd.notna(median_days) else "N/A",
        trend_text=f"{t3} vs prior ({p3:.0f}d)" if t3 else None,
        trend_direction=d3, accent_color=CHART_COLORWAY[1],
        sparkline_id=f"{PAGE_ID}-spark-lead",
    )

    kpi_pending = kpi_card(
        f"Pending Pipeline ({_pw}d)", f"{pending:,}",
        trend_text=f"{pending / total * 100:.0f}% of total" if total else None,
        accent_color=SEMANTIC_COLORS["warning"],
        sparkline_id=" ",
    )

    t5, d5, p5 = _trend(unique_mds, prior_mds)
    kpi_mds = kpi_card(
        "Unique Referring MDs", f"{unique_mds:,}",
        trend_text=f"{t5} vs prior ({p5:,.0f})" if t5 else None,
        trend_direction=d5, accent_color=CHART_COLORWAY[5],
        sparkline_id=f"{PAGE_ID}-spark-mds",
    )

    kpis = [kpi_total, kpi_conv, kpi_lead, kpi_pending, kpi_mds]

    # --- Table (built from all_data before grid row filter) ---
    triggered_by_grid = (
        dash.callback_context.triggered
        and len(dash.callback_context.triggered) == 1
        and dash.callback_context.triggered[0]["prop_id"] == f"{PAGE_ID}-table-filter-rows.data"
    )
    if triggered_by_grid:
        table_rows = dash.no_update
        table_cols = dash.no_update
    else:
        table_rows, table_cols = _build_detail_table(all_data)

    # Apply grid row filter — KPIs, sparklines, and charts use the subset
    all_data = _apply_grid_row_filter(all_data, grid_rows)

    # --- Flow Gantt ---
    flow_data = _compute_referral_flow_data(all_data, cap_0=cap_0, cap_1=cap_1)
    flow_details = _compute_referral_flow_details(all_data, cap_0=cap_0, cap_1=cap_1)

    # --- Map geo data (may block on geocoding — don't let it break the page) ---
    try:
        geo_df = _prepare_referral_geo_data(all_data)
        geo_store = geo_df.to_dict("records") if not geo_df.empty else None
    except Exception:
        geo_store = None

    # --- Dimension trend + comparison ---
    dimension = dim_toggle or "diagnosis"
    dim_df = _assign_dimension_group(all_data, dimension, payor_mode=payor_mode)

    dim_trend_store = _prepare_ref_trend_store(dim_df, dimension) if not dim_df.empty else None

    # Comparison: current vs N prior periods
    compare_type = dim_compare_period or "calendar"
    if start_date and end_date:
        dim_start = pd.Timestamp(start_date)
        dim_end = pd.Timestamp(end_date)
    else:
        dim_start = all_data["Created"].min()
        dim_end = all_data["Created"].max()

    period_days = (dim_end - dim_start).days
    cal_disabled = period_days > 365
    if cal_disabled and compare_type == "calendar":
        compare_type = "rolling"

    # Probe up to 3 prior periods to discover availability
    _MAX_PROBE = 3
    all_prior_windows = []
    try:
        prior_all = load_referrals()
        data_min = prior_all["Created"].min() if not prior_all.empty else dim_start
        # Apply same filters as current data
        if departments and "Referred to Department" in prior_all.columns:
            p_dept = prior_all["Referred to Department"].apply(_map_to_our_dept)
            prior_all = prior_all[p_dept.isin(departments)]
        if specialty_filter and "DeptSpecialty" in prior_all.columns:
            prior_all = prior_all[prior_all["DeptSpecialty"].isin(specialty_filter)]
        if institution_filter and "DoctorInstitution" in prior_all.columns:
            prior_all = prior_all[prior_all["DoctorInstitution"].isin(institution_filter)]
        if provider_filter and "Referred by Provider" in prior_all.columns:
            prior_all = prior_all[prior_all["Referred by Provider"].isin(provider_filter)]
        if diag_cats:
            prior_all["_diag_filt"] = prior_all.apply(
                lambda r: _categorise_diagnosis(
                    r.get("Diagnoses"), r.get("Rfl Prim Dx"), r.get("Onc Dx")
                ),
                axis=1,
            )
            _cat_set = set(diag_cats)
            if diag_subs:
                _cat_set.update(diag_subs)
            prior_all = prior_all[prior_all["_diag_filt"].isin(_cat_set)]
            prior_all = prior_all.drop(columns=["_diag_filt"])
        if payor_selected:
            prior_all = _apply_payor_filter(prior_all, payor_selected, payor_mode)

        for i in range(1, _MAX_PROBE + 1):
            if compare_type == "calendar":
                try:
                    ps = dim_start - pd.DateOffset(years=i)
                    pe = dim_end - pd.DateOffset(years=i)
                except Exception:
                    break
            else:
                shift = pd.Timedelta(days=period_days * i)
                ps = dim_start - shift
                pe = dim_end - shift
            if pe < data_min:
                break
            pw = prior_all[
                (prior_all["Created"] >= ps) & (prior_all["Created"] <= pe)
            ]
            pw = _assign_dimension_group(pw, dimension, payor_mode=payor_mode)
            all_prior_windows.append((pw, ps, pe))
    except Exception:
        pass

    avail_priors = max(len(all_prior_windows), 1)

    # Control outputs: calendar disable + slider cap
    pt_data = [
        {"value": "calendar", "label": "Calendar", "disabled": cal_disabled},
        {"value": "rolling", "label": "Rolling"},
    ]
    pt_value = "rolling" if cal_disabled and compare_type == "calendar" else dash.no_update
    slider_max = avail_priors
    slider_marks = [{"value": i, "label": str(i)} for i in range(0, slider_max + 1)]

    # Pre-build comparison figures for each prior period count (clientside picks)
    compare_figs = {}
    # 0 = current only, no comparison
    compare_figs["0"] = _build_ref_comparison_bars(
        dim_df, [], dim_start, dim_end,
    ) if not dim_df.empty else empty_dim
    for n_prior in range(1, avail_priors + 1):
        pw = all_prior_windows[:n_prior]
        fig_c = _build_ref_comparison_bars(
            dim_df, pw, dim_start, dim_end,
        ) if not dim_df.empty else empty_dim
        compare_figs[str(n_prior)] = fig_c

    # If the only thing the user changed was the dim-toggle (or the
    # current-vs-prior period mode), suppress the outputs that don't depend on
    # those inputs. Lets the row of 3 (flow-dist / flow-trend / flow-conv) and
    # the KPI sparklines stay put instead of flashing through a re-render on
    # every dimension flip. dim_trend_store + compare_figs (and the period
    # control state) still update so the two charts that DO depend on the
    # toggle re-render normally with their loading overlays.
    triggered = ctx.triggered_id
    _dim_only = {f"{PAGE_ID}-dim-toggle", f"{PAGE_ID}-dim-compare-period"}
    if triggered in _dim_only:
        nu = dash.no_update
        return (nu, nu, nu, nu, nu,
                dim_trend_store, compare_figs, nu, nu, nu,
                pt_data, pt_value, slider_max, slider_marks, nu, nu)
    return (kpis, flow_data, flow_details, table_rows, table_cols,
            dim_trend_store, compare_figs, spec_options, inst_options, prov_options,
            pt_data, pt_value, slider_max, slider_marks, sparkline_store, geo_store)


# ---------------------------------------------------------------------------
# Referral Volume Store Callback
# ---------------------------------------------------------------------------

@callback(
    Output(f"{PAGE_ID}-store-vol", "data"),
    Input(f"{PAGE_ID}-interval", "n_intervals"),
    Input(f"{PAGE_ID}-filter-daterange", "start_date"),
    Input(f"{PAGE_ID}-filter-daterange", "end_date"),
    Input(f"{PAGE_ID}-filter-department", "value"),
    Input(f"{PAGE_ID}-filter-specialty", "value"),
    Input(f"{PAGE_ID}-filter-institution", "value"),
    Input(f"{PAGE_ID}-filter-provider", "value"),
    Input(f"{PAGE_ID}-diag-store", "data"),
    Input(f"{PAGE_ID}-diag-mode", "data"),
    Input(f"{PAGE_ID}-diag-subcategory", "value"),
    Input(f"{PAGE_ID}-vol-slice", "value"),
    Input(f"{PAGE_ID}-vol-agg", "value"),
    Input(f"{PAGE_ID}-filter-payor-mode", "value"),
    Input(f"{PAGE_ID}-filter-payor", "value"),
    running=[(Output(f"{PAGE_ID}-chart-vol-loading", "visible"), True, False)],
)
def _update_ref_volume(_n, start_date, end_date, departments, specialty_filter,
                       institution_filter, provider_filter, diag_cats, diag_mode, diag_subs,
                       vol_slice, vol_agg, payor_mode, payor_selected):
    """Build census-format store data for referral volume trend."""
    from data.loader import load_referrals
    try:
        df = load_referrals()
        df = _cross_validate_with_cv(df)
    except Exception:
        return None
    if df.empty:
        return None

    # Apply filters
    if start_date and end_date:
        s = pd.Timestamp(start_date)
        e = pd.Timestamp(end_date) + timedelta(days=1)
        df = df[(df["Created"] >= s) & (df["Created"] < e)]
    if departments and "Referred to Department" in df.columns:
        our_dept = df["Referred to Department"].apply(_map_to_our_dept)
        df = df[our_dept.isin(departments)]
    if specialty_filter and "DeptSpecialty" in df.columns:
        df = df[df["DeptSpecialty"].isin(specialty_filter)]
    if institution_filter and "DoctorInstitution" in df.columns:
        df = df[df["DoctorInstitution"].isin(institution_filter)]
    if provider_filter and "Referred by Provider" in df.columns:
        df = df[df["Referred by Provider"].isin(provider_filter)]
    if diag_cats:
        df["_diag_filt"] = df.apply(
            lambda r: _categorise_diagnosis(
                r.get("Diagnoses"), r.get("Rfl Prim Dx"), r.get("Onc Dx")
            ), axis=1,
        )
        cat_set = set(diag_cats)
        if diag_subs:
            cat_set.update(diag_subs)
        df = df[df["_diag_filt"].isin(cat_set)]
    if payor_selected:
        df = _apply_payor_filter(df, payor_selected, payor_mode)

    if df.empty:
        return None

    return _prepare_ref_volume_data(df, vol_agg, vol_slice or "",
                                    payor_mode=payor_mode)


# ---------------------------------------------------------------------------
# Cumulative Referral Volume Store Callback
# ---------------------------------------------------------------------------

@callback(
    Output(f"{PAGE_ID}-store-cumulative", "data"),
    Output(f"{PAGE_ID}-cumulative-settings-prior-periods", "max"),
    Output(f"{PAGE_ID}-cumulative-settings-prior-periods", "marks"),
    Input(f"{PAGE_ID}-interval", "n_intervals"),
    Input(f"{PAGE_ID}-filter-daterange", "start_date"),
    Input(f"{PAGE_ID}-filter-daterange", "end_date"),
    Input(f"{PAGE_ID}-filter-department", "value"),
    Input(f"{PAGE_ID}-filter-specialty", "value"),
    Input(f"{PAGE_ID}-filter-institution", "value"),
    Input(f"{PAGE_ID}-filter-provider", "value"),
    Input(f"{PAGE_ID}-diag-store", "data"),
    Input(f"{PAGE_ID}-diag-mode", "data"),
    Input(f"{PAGE_ID}-diag-subcategory", "value"),
    Input(f"{PAGE_ID}-cumulative-mode", "value"),
    Input(f"{PAGE_ID}-cumulative-period-type", "value"),
    Input(f"{PAGE_ID}-cumulative-slice", "value"),
    Input(f"{PAGE_ID}-filter-date-preset", "value"),
    Input(f"{PAGE_ID}-filter-payor-mode", "value"),
    Input(f"{PAGE_ID}-filter-payor", "value"),
    running=[(Output(f"{PAGE_ID}-chart-cumulative-loading", "visible"), True, False)],
)
def _update_ref_cumulative(_n, start_date, end_date, departments, specialty_filter,
                           institution_filter, provider_filter, diag_cats, diag_mode, diag_subs,
                           cum_mode, period_type, slice_by, date_preset,
                           payor_mode, payor_selected):
    """Build cumulative referral volume store data."""
    from data.loader import load_referrals

    _default_marks = [{"value": i, "label": str(i)} for i in range(0, 6)]

    try:
        df_all = load_referrals()
        df_all = _cross_validate_with_cv(df_all)
    except Exception:
        return None, 5, _default_marks
    if df_all.empty or "Created" not in df_all.columns:
        return None, 5, _default_marks

    # Apply non-date filters to full dataset (for prior periods)
    if departments and "Referred to Department" in df_all.columns:
        our_dept = df_all["Referred to Department"].apply(_map_to_our_dept)
        df_all = df_all[our_dept.isin(departments)]
    if specialty_filter and "DeptSpecialty" in df_all.columns:
        df_all = df_all[df_all["DeptSpecialty"].isin(specialty_filter)]
    if institution_filter and "DoctorInstitution" in df_all.columns:
        df_all = df_all[df_all["DoctorInstitution"].isin(institution_filter)]
    if provider_filter and "Referred by Provider" in df_all.columns:
        df_all = df_all[df_all["Referred by Provider"].isin(provider_filter)]
    if diag_cats:
        df_all["_diag_filt"] = df_all.apply(
            lambda r: _categorise_diagnosis(
                r.get("Diagnoses"), r.get("Rfl Prim Dx"), r.get("Onc Dx")
            ), axis=1,
        )
        cat_set = set(diag_cats)
        if diag_subs:
            cat_set.update(diag_subs)
        df_all = df_all[df_all["_diag_filt"].isin(cat_set)]
    if payor_selected:
        df_all = _apply_payor_filter(df_all, payor_selected, payor_mode)

    if df_all.empty:
        return None, 5, _default_marks

    # Date range
    if start_date and end_date:
        start = pd.Timestamp(start_date)
        end = pd.Timestamp(end_date)
    else:
        start = df_all["Created"].min()
        end = df_all["Created"].max()

    # Use the standard _prepare_ref_cumulative_data pattern
    return _prepare_ref_cumulative_data(
        df_all, start, end, cum_mode or "prior",
        period_type or "calendar", slice_by or "department",
        date_preset=date_preset,
    )


# ---------------------------------------------------------------------------
# Payor filter: populate chips based on mode (actual/broad/phdsc)
# ---------------------------------------------------------------------------
@callback(
    Output(f"{PAGE_ID}-filter-payor", "children"),
    Output(f"{PAGE_ID}-filter-payor", "value"),
    Input(f"{PAGE_ID}-filter-payor-mode", "value"),
)
def _populate_payor_chips(mode):
    from data.loader import load_referrals
    mode = mode or "broad"
    mapping = _get_payor_mapping()

    if mode == "broad":
        options = list(_BROAD_PAYOR_CATEGORIES)
    elif mode == "phdsc":
        options = list(_PHDSC_PAYOR_CATEGORIES)
    else:
        # actual — standardized payor names observed in the data, by frequency
        try:
            df = load_referrals()
        except Exception:
            df = pd.DataFrame()
        if df.empty or "Payer" not in df.columns:
            options = []
        else:
            primary = df["Payer"].apply(_extract_primary_payor)
            groups = _payor_mode_groups(primary, "actual", mapping)
            options = groups.value_counts().head(60).index.tolist()

    chips = [dmc.Chip(opt, value=opt, size="xs", variant="filled") for opt in options]
    return chips, []


# Trigger label + clear-button visibility
clientside_callback(
    """function(vals) {
        var n = (vals && vals.length) || 0;
        var lbl = n > 0 ? "Payor (" + n + ")" : "Payor";
        var sty = n > 0 ? {"display": "inline-flex"} : {"display": "none"};
        return [lbl, sty];
    }""",
    Output(f"{PAGE_ID}-payor-filter-trigger", "children"),
    Output(f"{PAGE_ID}-payor-filter-clear", "style"),
    Input(f"{PAGE_ID}-filter-payor", "value"),
)

# Clear button action
clientside_callback(
    """function(n) { return []; }""",
    Output(f"{PAGE_ID}-filter-payor", "value", allow_duplicate=True),
    Input(f"{PAGE_ID}-payor-filter-clear", "n_clicks"),
    prevent_initial_call=True,
)


# ---------------------------------------------------------------------------
# Clientside callbacks for new census charts
# ---------------------------------------------------------------------------

_CENSUS_WITH_STACK = """function(rawData, smoothPct, chartType, stackVal, currentFig) {
    return window.dash_clientside.census.smoothChartWithType(rawData, smoothPct, chartType, currentFig, stackVal);
}"""
_CUMULATIVE_WITH_STACK = """function(rawData, smoothPct, chartType, stackVal, maxPrior, currentFig) {
    return window.dash_clientside.cumulative.renderCumulative(rawData, smoothPct, chartType, currentFig, stackVal, maxPrior);
}"""

clientside_callback(
    _CENSUS_WITH_STACK,
    Output(f"{PAGE_ID}-chart-vol", "figure"),
    Input(f"{PAGE_ID}-store-vol", "data"),
    Input(f"{PAGE_ID}-vol-settings-smooth", "value"),
    Input(f"{PAGE_ID}-vol-settings-type", "value"),
    Input(f"{PAGE_ID}-vol-settings-stack", "value"),
    State(f"{PAGE_ID}-chart-vol", "figure"),
    prevent_initial_call=True,
)

clientside_callback(f"""function() {{
        var fig = window.dash_clientside.cumulative.renderWithProjectToggle.apply(null, arguments);
        return window.dash_clientside.chartDeferred.wrap("{PAGE_ID}-chart-cumulative", fig, true);
    }}""",
    Output(f"{PAGE_ID}-chart-cumulative", "figure"),
    Input(f"{PAGE_ID}-store-cumulative", "data"),
    Input(f"{PAGE_ID}-cumulative-settings-smooth", "value"),
    Input(f"{PAGE_ID}-cumulative-settings-type", "value"),
    Input(f"{PAGE_ID}-cumulative-settings-stack", "value"),
    Input(f"{PAGE_ID}-cumulative-settings-prior-periods", "value"),
    Input(f"{PAGE_ID}-cumulative-project", "checked"),
    State(f"{PAGE_ID}-chart-cumulative", "figure"),
    prevent_initial_call=True,
)

# Cumulative sub-controls based on mode + chart-type:
#   bar           → hide mode toggle, show period-type + slice together
#   prior + non-bar → show mode + period-type, hide slice
#   slice + non-bar → show mode + slice, hide period-type
clientside_callback(
    """function(mode, chartType) {
        if (chartType === "bar") {
            return [{"display": "none"}, {}, {}];
        }
        if (mode === "prior") {
            return [{}, {}, {"display": "none"}];
        }
        return [{}, {"display": "none"}, {}];
    }""",
    Output(f"{PAGE_ID}-cumulative-mode", "style"),
    Output(f"{PAGE_ID}-cumulative-period-type", "style"),
    Output(f"{PAGE_ID}-cumulative-slice", "style"),
    Input(f"{PAGE_ID}-cumulative-mode", "value"),
    Input(f"{PAGE_ID}-cumulative-settings-type", "value"),
)

# Cumulative chart: hide grouping in single-dim, line, or non-bar prior mode
clientside_callback(
    """function(mode, sliceVal, chartType) {
        var single = !sliceVal || sliceVal === "total" || sliceVal === "";
        if (single) return {"display": "none"};
        if (chartType === "bar") return {};
        var isPrior = mode === "prior";
        var noStack = chartType === "line";
        return (isPrior || noStack) ? {"display": "none"} : {};
    }""",
    Output(f"{PAGE_ID}-cumulative-settings-stack-wrap", "style"),
    Input(f"{PAGE_ID}-cumulative-mode", "value"),
    Input(f"{PAGE_ID}-cumulative-slice", "value"),
    Input(f"{PAGE_ID}-cumulative-settings-type", "value"),
)

# Hide "Total" slice option in line/area mode (only useful for bar)
_REF_CUMUL_SLICE_ALL = [
    {"value": "total", "label": "Total"},
    {"value": "department", "label": "Ref Dept"},
    {"value": "institution", "label": "Institution"},
    {"value": "specialty", "label": "Specialty"},
    {"value": "diagnosis", "label": "Dx"},
    {"value": "site", "label": "Site"},
]
_REF_CUMUL_SLICE_NO_TOTAL = [o for o in _REF_CUMUL_SLICE_ALL if o["value"] != "total"]

clientside_callback(
    """function(chartType, sliceVal) {
        var all = %s;
        var noTotal = %s;
        if (chartType === "bar") {
            return [all, window.dash_clientside.no_update];
        }
        var newVal = (sliceVal === "total") ? "department" : window.dash_clientside.no_update;
        return [noTotal, newVal];
    }""" % (str(_REF_CUMUL_SLICE_ALL).replace("'", '"'), str(_REF_CUMUL_SLICE_NO_TOTAL).replace("'", '"')),
    Output(f"{PAGE_ID}-cumulative-slice", "data"),
    Output(f"{PAGE_ID}-cumulative-slice", "value", allow_duplicate=True),
    Input(f"{PAGE_ID}-cumulative-settings-type", "value"),
    State(f"{PAGE_ID}-cumulative-slice", "value"),
    prevent_initial_call=True,
)


# ---------------------------------------------------------------------------
# Referral Map callback (reads from store + inline controls)
# ---------------------------------------------------------------------------

@callback(
    Output(f"{PAGE_ID}-map", "figure"),
    Input(f"{PAGE_ID}-store-map-geo", "data"),
    Input(f"{PAGE_ID}-map-dept", "value"),
    Input(f"{PAGE_ID}-filter-department", "value"),
    Input(f"{PAGE_ID}-map-flow-toggle", "checked"),
    Input(f"{PAGE_ID}-map-region", "value"),
    Input(f"{PAGE_ID}-map-min-slider", "value"),
    Input(f"{PAGE_ID}-map-reset", "n_clicks"),
    Input("global-theme-store", "data"),
)
def _update_referral_map(geo_data, selected_dept, departments, show_flows,
                         region, min_referrals, _reset, theme):
    # Re-fit map when any view control changes; preserve zoom only on
    # data refresh (interval), flow line toggle (same bounds), and theme
    # store changes (style swap, bounds unchanged).
    _preserve = {f"{PAGE_ID}-store-map-geo", f"{PAGE_ID}-map-flow-toggle",
                 "global-theme-store"}
    triggered = dash.callback_context.triggered_id
    if triggered and triggered not in _preserve:
        ui_rev = f"{region}-{selected_dept}-{departments}-{min_referrals}-{_reset}"
    else:
        ui_rev = "referrals-map"

    map_style = "dark" if theme == "dark" else MAPBOX_STYLE

    if not geo_data:
        return _build_referral_map(
            pd.DataFrame(), departments,
            selected_dept=selected_dept,
            show_flows=show_flows,
            region=region,
            min_referrals=min_referrals or 3,
            uirevision=ui_rev,
            map_style=map_style,
        )

    geo_df = pd.DataFrame(geo_data)
    return _build_referral_map(
        geo_df, departments,
        selected_dept=selected_dept,
        show_flows=show_flows,
        region=region,
        min_referrals=min_referrals or 3,
        uirevision=ui_rev,
        map_style=map_style,
    )


# ==========================================================================
# Referring Physician Manager (RPM) Callbacks
# ==========================================================================
import threading

# Module-level progress state for background NPI/AI operations
_rpm_progress = {"done": 0, "total": 0, "running": False, "message": ""}
_rpm_npi_results = []  # Pending NPI lookup results for review
_rpm_ai_review_results = []  # Pending provider-AI results awaiting user review
_rpm_lock = threading.Lock()

# Diagnosis AI classification progress
_diag_ai_progress = {"done": 0, "total": 0, "running": False, "message": ""}
_diag_ai_results: list[dict] = []
_diag_ai_lock = threading.Lock()


def _build_rpm_grid_data() -> tuple[list[dict], str]:
    """Build the grid rowData from the Referrals Report + SQLite overrides.

    Aggregates unique referring physicians by NPI from the referrals xlsx.
    Returns (row_data, stats_text).
    """
    from data.loader import load_referrals
    from data.reviews_db import (
        get_all_referring_overrides, referring_table_is_empty,
        bulk_upsert_referring, sync_institutions_from_physicians,
        get_referring_merge_map, _addr_key,
    )

    ref = load_referrals()

    # Only rows with a valid 10-digit NPI
    ref = ref[ref["Referred By Prov NPI"].notna()].copy()
    ref["_npi"] = ref["Referred By Prov NPI"].astype(float).astype(int).astype(str)
    ref = ref[ref["_npi"].str.match(r"^\d{10}$")]

    if ref.empty:
        return [], "No referral data with valid NPIs"

    # Normalize address fields for grouping
    for col in ["Referring Provider City", "Referring Provider State", "Referring Provider Zip Code"]:
        ref[col] = ref[col].fillna("").astype(str).str.strip()

    # Build composite key: NPI + city/state/zip
    ref["_addr_key"] = ref.apply(
        lambda r: _addr_key(r["Referring Provider City"], r["Referring Provider State"], r["Referring Provider Zip Code"]),
        axis=1,
    )

    # Apply merge tombstones from DB: redirect any (npi, loser_addr_key) to
    # its survivor before aggregating. Keeps merged rows from reappearing
    # after a reload (the underlying CSV still has both address_keys).
    merge_map = get_referring_merge_map()
    if merge_map:
        def _redirect(row):
            return merge_map.get((row["_npi"], row["_addr_key"]), row["_addr_key"])
        ref["_addr_key"] = ref.apply(_redirect, axis=1)
    ref["_row_key"] = ref["_npi"] + "|" + ref["_addr_key"]

    # Aggregate per NPI+address: pick most common name/dept, count referrals
    def _mode_or_first(s):
        s = s.dropna()
        if s.empty:
            return ""
        m = s.mode()
        return m.iloc[0] if len(m) > 0 else s.iloc[0]

    agg = ref.groupby(["_npi", "_addr_key"]).agg(
        name=("Referred by Provider", _mode_or_first),
        department=("Referred by Department", _mode_or_first),
        address=("Referring Provider Address", _mode_or_first),
        city=("Referring Provider City", _mode_or_first),
        state=("Referring Provider State", _mode_or_first),
        zip_code=("Referring Provider Zip Code", _mode_or_first),
        specialty=("DoctorSpecialty", _mode_or_first),
        institution=("DoctorInstitution", _mode_or_first),
        name_raw=("Referred by Provider Raw", _mode_or_first),
        referral_count=("Referral ID", "count"),
        first_referral=("Created", "min"),
        last_referral=("Created", "max"),
    ).reset_index().rename(columns={"_npi": "npi", "_addr_key": "address_key"})

    # Seed SQLite from referrals data on first open
    if referring_table_is_empty():
        seed = [
            {"npi": r["npi"], "address_key": r["address_key"],
             "specialty": r["specialty"] or None,
             "institution": r["institution"] or None, "source": "lookup"}
            for _, r in agg.iterrows()
            if r["specialty"] or r["institution"]
        ]
        if seed:
            bulk_upsert_referring(seed)
        sync_institutions_from_physicians()

    # Apply SQLite overrides (keyed on "npi|address_key")
    overrides = get_all_referring_overrides()

    rows = []
    for _, r in agg.iterrows():
        npi = r["npi"]
        addr_k = r["address_key"]
        row_key = f"{npi}|{addr_k}"
        from config.settings import normalize_specialty
        spec = normalize_specialty(r["specialty"] or "")
        inst = r["institution"] or ""
        source = "lookup" if (spec or inst) else ""
        display_name_override = ""

        reviewed = False
        address_source = ""  # "": source data, "manual"/"claude_ai": user/AI override
        if row_key in overrides:
            ov = overrides[row_key]
            if ov.get("specialty"):
                spec = normalize_specialty(ov["specialty"])
            if ov.get("institution"):
                inst = ov["institution"]
            if ov.get("display_name"):
                display_name_override = ov["display_name"]
            source = ov.get("source", source)
            reviewed = ov.get("reviewed", False)
            # Use DB address if it was set by anything (manual edit, AI research,
            # etc.) — anything in address_source means "DB overrides the CSV".
            ov_addr_src = ov.get("address_source") or ""
            if ov_addr_src:
                address_source = ov_addr_src
                if ov.get("address"):
                    r = r.copy()
                    r["address"] = ov["address"]
                if ov.get("city"):
                    r["city"] = ov["city"]
                if ov.get("state"):
                    r["state"] = ov["state"]
                if ov.get("zip_code"):
                    r["zip_code"] = ov["zip_code"]

        _clean = lambda v: str(v) if v and str(v) not in ("", "nan") else ""
        addr = _clean(r["address"])
        city = _clean(r["city"])
        state = _clean(r["state"])
        zip_c = _clean(r["zip_code"])

        full_address = ", ".join(p for p in [addr, city, state, zip_c] if p)

        rows.append({
            "npi": npi,
            "address_key": addr_k,
            "row_key": row_key,
            "name": display_name_override or r["name"],
            "name_raw": r.get("name_raw") or r["name"],
            "department": r["department"],
            "address": addr,
            "city": city,
            "state": state,
            "zip": zip_c,
            "full_address": full_address,
            "address_source": address_source,
            "specialty": spec,
            "institution": inst,
            "source": source,
            "patient_count": int(r["referral_count"]),
            "first_referral": r["first_referral"].strftime("%m/%d/%Y") if pd.notna(r.get("first_referral")) else "",
            "last_referral": r["last_referral"].strftime("%m/%d/%Y") if pd.notna(r.get("last_referral")) else "",
            "reviewed": reviewed,
        })

    # Add DB-only rows (manually added addresses not in source data)
    seen_keys = {r["row_key"] for r in rows}
    for ov_key, ov in overrides.items():
        if ov_key in seen_keys:
            continue
        if ov.get("address_source") != "manual":
            continue
        npi, addr_k = ov_key.split("|", 1) if "|" in ov_key else (ov_key, "")
        # Find the provider name from existing rows with same NPI
        name = ""
        dept = ""
        for r in rows:
            if r["npi"] == npi:
                name = r["name"]
                dept = r["department"]
                break
        a_parts = [ov.get("address", ""), ov.get("city", ""), ov.get("state", ""), ov.get("zip_code", "")]
        full_addr = ", ".join(p for p in a_parts if p)
        rows.append({
            "npi": npi,
            "address_key": addr_k,
            "row_key": ov_key,
            "name": ov.get("display_name") or name,
            "name_raw": name,
            "department": dept,
            "address": ov.get("address", ""),
            "city": ov.get("city", ""),
            "state": ov.get("state", ""),
            "zip": ov.get("zip_code", ""),
            "full_address": full_addr,
            "address_source": "manual",
            "specialty": ov.get("specialty", ""),
            "institution": ov.get("institution", ""),
            "source": ov.get("source", "manual"),
            "patient_count": 0,
            "first_referral": "",
            "last_referral": "",
            "reviewed": ov.get("reviewed", False),
        })

    # Stats
    total = len(rows)
    with_spec = sum(1 for r in rows if r["specialty"])
    with_inst = sum(1 for r in rows if r["institution"])
    reviewed_n = sum(1 for r in rows if r.get("reviewed"))
    stats = (
        f"{total:,} providers  |  "
        f"{reviewed_n:,} reviewed  |  {total - reviewed_n:,} unreviewed  |  "
        f"{with_spec:,} specialty  |  {with_inst:,} institution"
    )

    return rows, stats


def _build_inst_grid_data(phys_rows: list[dict]) -> tuple[list[dict], str]:
    """Build institution management grid data from physician rows."""
    from collections import Counter
    counts = Counter(r["institution"] for r in phys_rows if r.get("institution"))
    inst_rows = [
        {"name": name, "physician_count": cnt, "original_name": name}
        for name, cnt in sorted(counts.items())
    ]
    return inst_rows, str(len(inst_rows))


def _rpm_visible(rows: list[dict], unreviewed_only: bool, dupes_only: bool) -> list[dict]:
    """Apply the RPM grid's toolbar filters (Unreviewed only, Duplicate NPIs only)
    to the full row data. Centralized so every callback that produces visible
    rowData uses the same logic."""
    if not rows:
        return rows
    out = rows
    if unreviewed_only:
        out = [r for r in out if not r.get("reviewed")]
    if dupes_only:
        from collections import Counter
        npi_counts = Counter(r.get("npi", "") for r in rows if r.get("npi"))
        out = [r for r in out if npi_counts.get(r.get("npi", ""), 0) > 1]
    return out


clientside_callback(
    """function(n) {
        if (!n) return [window.dash_clientside.no_update,
                         window.dash_clientside.no_update,
                         window.dash_clientside.no_update];
        return ['heavy-modal-overlay', 0, false];
    }""",
    Output(f"{PAGE_ID}-rpm-overlay", "className"),
    Output(f"{PAGE_ID}-rpm-delay", "n_intervals"),
    Output(f"{PAGE_ID}-rpm-delay", "disabled"),
    Input(f"{PAGE_ID}-rpm-btn", "n_clicks"),
    prevent_initial_call=True,
)

clientside_callback(
    """function(n) {
        if (!n) return [window.dash_clientside.no_update,
                         window.dash_clientside.no_update];
        return [true, true];
    }""",
    Output(f"{PAGE_ID}-rpm-modal", "opened"),
    Output(f"{PAGE_ID}-rpm-delay", "disabled", allow_duplicate=True),
    Input(f"{PAGE_ID}-rpm-delay", "n_intervals"),
    prevent_initial_call=True,
)

clientside_callback(
    """function(opened) {
        if (!opened) return window.dash_clientside.no_update;
        requestAnimationFrame(function() {
            setTimeout(function() {
                var el = document.getElementById('referrals-rpm-overlay');
                if (el) el.className = 'heavy-modal-overlay hidden';
            }, 50);
        });
        return window.dash_clientside.no_update;
    }""",
    Output(f"{PAGE_ID}-rpm-overlay", "className", allow_duplicate=True),
    Input(f"{PAGE_ID}-rpm-modal", "opened"),
    prevent_initial_call=True,
)


@callback(
    Output(f"{PAGE_ID}-rpm-grid", "rowData"),
    Output(f"{PAGE_ID}-rpm-grid-full-store", "data"),
    Output(f"{PAGE_ID}-rpm-stats", "children"),
    Output(f"{PAGE_ID}-rpm-inst-grid", "rowData"),
    Output(f"{PAGE_ID}-rpm-inst-count", "children"),
    Output(f"{PAGE_ID}-rpm-prov-count", "children"),
    Output(f"{PAGE_ID}-rpm-unreviewed-toggle", "checked"),
    Input(f"{PAGE_ID}-rpm-btn", "n_clicks"),
    prevent_initial_call=True,
)
def _rpm_open(n):
    if not n:
        return (dash.no_update,) * 7
    if not can_see_manager_modals():
        return (dash.no_update,) * 7
    rows, stats = _build_rpm_grid_data()
    inst_rows, inst_count = _build_inst_grid_data(rows)
    return rows, rows, stats, inst_rows, inst_count, str(len(rows)), False


# ---------------------------------------------------------------------------
# Role gate: hide the Referring Physician Manager trigger button from
# non-admins on page mount.
# ---------------------------------------------------------------------------
@callback(
    Output(f"{PAGE_ID}-rpm-btn", "style"),
    Input(f"{PAGE_ID}-rpm-btn", "id"),
)
def _rpm_role_gate(_id):
    if can_see_manager_modals():
        return dash.no_update
    return {"display": "none"}


@callback(
    Output(f"{PAGE_ID}-rpm-diag-grid", "rowData"),
    Output(f"{PAGE_ID}-rpm-diag-grid-full-store", "data"),
    Output(f"{PAGE_ID}-rpm-diag-count", "children"),
    Output(f"{PAGE_ID}-rpm-diag-stats", "children"),
    Output(f"{PAGE_ID}-rpm-diag-unreviewed-toggle", "checked"),
    Input(f"{PAGE_ID}-rpm-tabs", "value"),
    prevent_initial_call=True,
)
def _rpm_diag_tab_load(tab):
    """Lazy-load diagnosis grid only when the Diagnoses tab is selected."""
    if tab != "diagnoses":
        return (dash.no_update,) * 5
    rows, count, stats = _build_diag_grid_data()
    return rows, rows, count, stats, False


@callback(
    Output(f"{PAGE_ID}-rpm-inst-confirm", "opened"),
    Output(f"{PAGE_ID}-rpm-inst-confirm-text", "children"),
    Output(f"{PAGE_ID}-rpm-inst-confirm-all", "children"),
    Output(f"{PAGE_ID}-rpm-inst-pending", "data"),
    Input(f"{PAGE_ID}-rpm-grid", "cellValueChanged"),
    State(f"{PAGE_ID}-rpm-grid-full-store", "data"),
    prevent_initial_call=True,
)
def _rpm_save_edit(changed, full_data):
    """Persist a cell edit to the DB. The clientside cellValueChanged mirror
    (further down) handles all UI/store updates instantly. This callback
    runs in the background to write to Postgres and to open the
    institution-rename confirmation modal when needed.

    Outputs are intentionally limited to the modal so this can't race with
    the clientside mirror over the grid's rowData / full_store / stats."""
    if not changed:
        return (dash.no_update,) * 4
    from data.reviews_db import upsert_referring, add_institution, set_reviewed_bulk

    row_data = full_data or []

    row = changed[0].get("data", {}) if isinstance(changed, list) else changed.get("data", {})
    row_key = row.get("row_key", "")
    npi = row.get("npi", "")
    addr_k = row.get("address_key", "")
    if not npi:
        return (dash.no_update,) * 4

    col = changed[0].get("colId", "") if isinstance(changed, list) else changed.get("colId", "")
    old_value = changed[0].get("oldValue", "") if isinstance(changed, list) else changed.get("oldValue", "")

    if col == "institution" and old_value:
        new_inst = row.get("institution", "")
        # Count how many rows share the old institution name
        shared_count = sum(1 for r in row_data if r.get("institution") == old_value and r.get("row_key") != row_key)
        if shared_count > 0:
            # Open the confirmation modal. The cell's new value stays
            # visible (clientside already applied it). If the user picks
            # Cancel, the cancel branch in _rpm_inst_confirm_action reverts.
            pending = {
                "row_key": row_key, "npi": npi, "address_key": addr_k,
                "old_institution": old_value, "new_institution": new_inst,
            }
            confirm_text = (
                f'Rename "{old_value}" → "{new_inst}"?  '
                f'{shared_count + 1} providers currently have "{old_value}".'
            )
            all_btn = f"Rename all {shared_count + 1} providers"
            return True, confirm_text, all_btn, pending

    if col == "reviewed":
        reviewed = bool(row.get("reviewed", False))
        upsert_referring(npi, address_key=addr_k, source=row.get("source", "manual"))
        set_reviewed_bulk([(npi, addr_k)], reviewed=reviewed)
        # Update the full store
        for r in row_data:
            if r.get("row_key") == row_key:
                r["reviewed"] = reviewed
                break
    elif col == "full_address":
        full = row.get("full_address") or ""
        parts = [p.strip() for p in str(full).split(",")]
        addr_str, city_str, state_str, zip_str = "", "", "", ""
        if len(parts) >= 4:
            addr_str = ", ".join(parts[:-3])
            city_str, state_str, zip_str = parts[-3], parts[-2], parts[-1]
        elif len(parts) == 3:
            addr_str, city_str = parts[0], parts[1]
            last = parts[2].strip()
            sp = last.split()
            if len(sp) == 2 and len(sp[0]) == 2:
                state_str, zip_str = sp[0], sp[1]
            else:
                state_str = last
        elif len(parts) == 2:
            addr_str, city_str = parts[0], parts[1]
        elif len(parts) == 1:
            addr_str = parts[0]
        upsert_referring(
            npi, address_key=addr_k,
            address=addr_str, city=city_str,
            state=state_str, zip_code=zip_str,
            address_source="manual", source="manual",
        )
        if row_data:
            for r in row_data:
                if r.get("row_key") == row_key:
                    r["address_source"] = "manual"
                    r["full_address"] = full
                    r["address"] = addr_str
                    r["city"] = city_str
                    r["state"] = state_str
                    r["zip"] = zip_str
                    break
    elif col == "institution":
        # Single-row institution (old value was unique or empty)
        inst = row.get("institution")
        upsert_referring(npi, address_key=addr_k, institution=inst, source="manual")
        if inst:
            add_institution(inst)
        if row_data:
            for r in row_data:
                if r.get("row_key") == row_key:
                    r["institution"] = inst
                    r["source"] = "manual"
                    break
    elif col == "name":
        new_name = (row.get("name") or "").strip()
        upsert_referring(npi, address_key=addr_k,
                         display_name=(new_name or None), source="manual")
        if row_data:
            for r in row_data:
                if r.get("row_key") == row_key:
                    r["name"] = new_name
                    r["source"] = "manual"
                    break
    else:
        spec = row.get("specialty") if col == "specialty" else None
        upsert_referring(npi, address_key=addr_k, specialty=spec, source="manual")
        if row_data:
            for r in row_data:
                if r.get("row_key") == row_key:
                    r["source"] = "manual"
                    if spec is not None:
                        r["specialty"] = spec
                    break

    # Non-modal branches: DB write already happened above. The clientside
    # cellValueChanged mirror handles the UI/store. Modal stays closed.
    return False, "", "", None


# --- Institution rename confirmation actions ---
@callback(
    Output(f"{PAGE_ID}-rpm-grid", "rowData", allow_duplicate=True),
    Output(f"{PAGE_ID}-rpm-grid-full-store", "data", allow_duplicate=True),
    Output(f"{PAGE_ID}-rpm-stats", "children", allow_duplicate=True),
    Output(f"{PAGE_ID}-rpm-inst-confirm", "opened", allow_duplicate=True),
    Output(f"{PAGE_ID}-rpm-inst-grid", "rowData", allow_duplicate=True),
    Output(f"{PAGE_ID}-rpm-inst-count", "children", allow_duplicate=True),
    Input(f"{PAGE_ID}-rpm-inst-confirm-one", "n_clicks"),
    Input(f"{PAGE_ID}-rpm-inst-confirm-all", "n_clicks"),
    Input(f"{PAGE_ID}-rpm-inst-confirm-cancel", "n_clicks"),
    State(f"{PAGE_ID}-rpm-inst-pending", "data"),
    State(f"{PAGE_ID}-rpm-grid-full-store", "data"),
    State(f"{PAGE_ID}-rpm-unreviewed-toggle", "checked"),
    State(f"{PAGE_ID}-rpm-dupes-toggle", "checked"),
    prevent_initial_call=True,
)
def _rpm_inst_confirm_action(n_one, n_all, n_cancel, pending, full_data, unreviewed_only, dupes_only):
    from dash import ctx
    hide = False
    if not pending or not full_data:
        return (dash.no_update,) * 4 + (dash.no_update, dash.no_update)

    row_data = full_data
    old_inst = pending["old_institution"]
    new_inst = pending["new_institution"]
    row_key = pending["row_key"]
    npi = pending["npi"]
    addr_k = pending["address_key"]

    triggered = ctx.triggered_id

    if triggered == f"{PAGE_ID}-rpm-inst-confirm-cancel":
        # Revert the cell: the clientside cellValueChanged mirror already
        # wrote the new institution into full_store optimistically. Roll it
        # back to old_inst here and push the corrected rowData so AG Grid
        # also reverts the visual cell.
        for r in row_data:
            if r.get("row_key") == row_key:
                r["institution"] = old_inst
                break
        visible = _rpm_visible(row_data, unreviewed_only, dupes_only)
        return visible, row_data, dash.no_update, hide, dash.no_update, dash.no_update

    from data.reviews_db import upsert_referring, add_institution, rename_institution

    if triggered == f"{PAGE_ID}-rpm-inst-confirm-one":
        # Reassign just this one row
        upsert_referring(npi, address_key=addr_k, institution=new_inst, source="manual")
        if new_inst:
            add_institution(new_inst)
        for r in row_data:
            if r.get("row_key") == row_key:
                r["institution"] = new_inst
                r["source"] = "manual"
                break

    elif triggered == f"{PAGE_ID}-rpm-inst-confirm-all":
        # Rename institution globally
        rename_institution(old_inst, new_inst)
        if new_inst:
            add_institution(new_inst)
        for r in row_data:
            if r.get("institution") == old_inst:
                r["institution"] = new_inst

    # Rebuild stats
    total = len(row_data)
    with_spec = sum(1 for r in row_data if r.get("specialty"))
    with_inst = sum(1 for r in row_data if r.get("institution"))
    reviewed_n = sum(1 for r in row_data if r.get("reviewed"))
    stats = (
        f"{total:,} providers  |  "
        f"{reviewed_n:,} reviewed  |  {total - reviewed_n:,} unreviewed  |  "
        f"{with_spec:,} specialty  |  {with_inst:,} institution"
    )
    visible = _rpm_visible(row_data, unreviewed_only, dupes_only)

    # Rebuild institution grid
    inst_rows, inst_count = _build_inst_grid_data(row_data)

    return visible, row_data, stats, hide, inst_rows, inst_count


@callback(
    Output(f"{PAGE_ID}-rpm-grid", "rowData", allow_duplicate=True),
    Output(f"{PAGE_ID}-rpm-grid-full-store", "data", allow_duplicate=True),
    Output(f"{PAGE_ID}-rpm-stats", "children", allow_duplicate=True),
    Output(f"{PAGE_ID}-rpm-prov-count", "children", allow_duplicate=True),
    Input(f"{PAGE_ID}-rpm-add-addr-btn", "n_clicks"),
    State(f"{PAGE_ID}-rpm-grid", "rowData"),
    State(f"{PAGE_ID}-rpm-grid", "selectedRows"),
    prevent_initial_call=True,
)
def _rpm_add_address(n, row_data, selected_rows):
    """Add a new blank address row for the selected provider's NPI."""
    if not n or not row_data:
        return (dash.no_update,) * 4
    if not selected_rows or len(selected_rows) == 0:
        return (dash.no_update,) * 4

    src = selected_rows[0]
    npi = src.get("npi", "")
    if not npi:
        return (dash.no_update,) * 4

    # Create a new empty-address row with the same NPI
    new_addr_key = f"NEW_{pd.Timestamp.now().strftime('%H%M%S')}"
    new_row_key = f"{npi}|{new_addr_key}"

    new_row = {
        "npi": npi,
        "address_key": new_addr_key,
        "row_key": new_row_key,
        "name": src.get("name", ""),
        "name_raw": src.get("name_raw", ""),
        "department": src.get("department", ""),
        "address": "",
        "city": "",
        "state": "",
        "zip": "",
        "full_address": "",
        "address_source": "manual",
        "specialty": src.get("specialty", ""),
        "institution": "",
        "source": "manual",
        "patient_count": 0,
        "reviewed": False,
    }

    # Insert at the top of the grid so the user can see it
    row_data = [new_row] + row_data

    total = len(row_data)
    with_spec = sum(1 for r in row_data if r.get("specialty"))
    with_inst = sum(1 for r in row_data if r.get("institution"))
    reviewed_n = sum(1 for r in row_data if r.get("reviewed"))
    stats = (
        f"{total:,} providers  |  "
        f"{reviewed_n:,} reviewed  |  {total - reviewed_n:,} unreviewed  |  "
        f"{with_spec:,} specialty  |  {with_inst:,} institution"
    )
    return row_data, row_data, stats, str(total)


@callback(
    Output(f"{PAGE_ID}-rpm-grid", "rowData", allow_duplicate=True),
    Output(f"{PAGE_ID}-rpm-grid-full-store", "data", allow_duplicate=True),
    Output(f"{PAGE_ID}-rpm-stats", "children", allow_duplicate=True),
    Output(f"{PAGE_ID}-rpm-prov-count", "children", allow_duplicate=True),
    Input(f"{PAGE_ID}-rpm-delete-btn", "n_clicks"),
    State(f"{PAGE_ID}-rpm-grid-full-store", "data"),
    State(f"{PAGE_ID}-rpm-grid", "selectedRows"),
    State(f"{PAGE_ID}-rpm-unreviewed-toggle", "checked"),
    State(f"{PAGE_ID}-rpm-dupes-toggle", "checked"),
    prevent_initial_call=True,
)
def _rpm_delete_rows(n, full_data, selected_rows, unreviewed_only, dupes_only):
    """Delete selected rows from the grid and DB."""
    if not n or not full_data or not selected_rows:
        return (dash.no_update,) * 4
    from data.reviews_db import delete_referring

    # Delete from DB
    delete_keys = set()
    for r in selected_rows:
        npi = r.get("npi", "")
        addr_k = r.get("address_key", "")
        if npi:
            delete_referring(npi, addr_k)
            delete_keys.add(r.get("row_key", ""))

    # Remove from grid data
    row_data = [r for r in full_data if r.get("row_key") not in delete_keys]

    total = len(row_data)
    with_spec = sum(1 for r in row_data if r.get("specialty"))
    with_inst = sum(1 for r in row_data if r.get("institution"))
    reviewed_n = sum(1 for r in row_data if r.get("reviewed"))
    stats = (
        f"{total:,} providers  |  "
        f"{reviewed_n:,} reviewed  |  {total - reviewed_n:,} unreviewed  |  "
        f"{with_spec:,} specialty  |  {with_inst:,} institution"
    )
    visible = _rpm_visible(row_data, unreviewed_only, dupes_only)
    return visible, row_data, stats, str(total)


# --- Merge selected provider rows (same NPI, different address_key) ---

def _pick_merge_survivor(rows: list[dict]) -> dict:
    """Survivor: highest patient_count, ties broken by reviewed=True then first."""
    return max(rows, key=lambda r: (
        int(r.get("patient_count") or 0),
        1 if r.get("reviewed") else 0,
    ))


@callback(
    Output(f"{PAGE_ID}-rpm-merge-confirm", "opened", allow_duplicate=True),
    Output(f"{PAGE_ID}-rpm-merge-confirm-text", "children"),
    Output(f"{PAGE_ID}-rpm-merge-confirm-detail", "children"),
    Output(f"{PAGE_ID}-rpm-merge-pending", "data"),
    Input(f"{PAGE_ID}-rpm-merge-btn", "n_clicks"),
    State(f"{PAGE_ID}-rpm-grid", "selectedRows"),
    prevent_initial_call=True,
)
def _rpm_merge_open(n, selected_rows):
    """Validate selection and open the merge confirmation modal."""
    if not n or not selected_rows or len(selected_rows) < 2:
        return False, "Select at least two rows with the same NPI to merge.", "", None

    npis = {r.get("npi", "") for r in selected_rows}
    if len(npis) != 1 or not next(iter(npis)):
        return (False,
                "All selected rows must share the same NPI. Merging across "
                "different physicians isn't supported.", "", None)

    survivor = _pick_merge_survivor(selected_rows)
    survivor_key = survivor.get("row_key", "")
    losers = [r for r in selected_rows if r.get("row_key") != survivor_key]

    npi = next(iter(npis))
    total_referrals = sum(int(r.get("patient_count") or 0) for r in selected_rows)
    name = survivor.get("name", "")

    # Show survivor vs loser addresses + which blank fields will be filled in.
    fields = [("specialty", "Specialty"), ("institution", "Institution"),
              ("full_address", "Address")]
    fill_lines = []
    for key, label in fields:
        surv_val = (survivor.get(key) or "").strip()
        if surv_val:
            continue
        donor = next((l for l in losers if (l.get(key) or "").strip()), None)
        if donor:
            fill_lines.append(
                dmc.Text([f"{label}: ", dmc.Text("blank → ", span=True,
                                                  c=NEUTRAL["text_muted"]),
                          dmc.Text(donor.get(key, ""), span=True, fw=500)],
                         size="xs"))

    def _addr_line(r, role):
        addr = (r.get("full_address") or "").strip() or "(no address)"
        cnt = int(r.get("patient_count") or 0)
        color = "teal" if role == "Survivor" else NEUTRAL["text_muted"]
        return dmc.Group(
            gap="xs",
            children=[
                dmc.Badge(role, color=color, variant="light", size="xs"),
                dmc.Text(addr, size="xs"),
                dmc.Text(f"({cnt} referrals)", size="xs",
                         c=NEUTRAL["text_muted"]),
            ],
        )

    detail_children = [_addr_line(survivor, "Survivor")]
    detail_children.extend(_addr_line(l, "Merging") for l in losers)
    if fill_lines:
        detail_children.append(dmc.Divider(my="xs"))
        detail_children.append(dmc.Text("Survivor will gain:", size="xs",
                                        fw=500, c=NEUTRAL["text_muted"]))
        detail_children.extend(fill_lines)

    text = (
        f"Merge {len(selected_rows)} rows for NPI {npi} ({name}) into one. "
        f"Loser rows will be deleted; {total_referrals} total referrals will "
        f"appear under the surviving address."
    )

    # Use `or ""` (not the .get default) — Dash JSON serialization can hand back
    # explicit None for empty strings, which then propagates into merge_referring
    # and writes merged_into=NULL on the tombstone, breaking the redirect.
    pending = {
        "npi": npi,
        "survivor_row_key": survivor_key,
        "survivor_address_key": survivor.get("address_key") or "",
        "loser_address_keys": [(l.get("address_key") or "") for l in losers],
        "loser_row_keys": [(l.get("row_key") or "") for l in losers],
    }
    return True, text, detail_children, pending


@callback(
    Output(f"{PAGE_ID}-rpm-grid", "rowData", allow_duplicate=True),
    Output(f"{PAGE_ID}-rpm-grid-full-store", "data", allow_duplicate=True),
    Output(f"{PAGE_ID}-rpm-stats", "children", allow_duplicate=True),
    Output(f"{PAGE_ID}-rpm-prov-count", "children", allow_duplicate=True),
    Output(f"{PAGE_ID}-rpm-inst-grid", "rowData", allow_duplicate=True),
    Output(f"{PAGE_ID}-rpm-inst-count", "children", allow_duplicate=True),
    Output(f"{PAGE_ID}-rpm-merge-confirm", "opened", allow_duplicate=True),
    Output(f"{PAGE_ID}-rpm-merge-pending", "data", allow_duplicate=True),
    Input(f"{PAGE_ID}-rpm-merge-confirm-apply", "n_clicks"),
    Input(f"{PAGE_ID}-rpm-merge-confirm-cancel", "n_clicks"),
    State(f"{PAGE_ID}-rpm-merge-pending", "data"),
    State(f"{PAGE_ID}-rpm-grid-full-store", "data"),
    State(f"{PAGE_ID}-rpm-unreviewed-toggle", "checked"),
    State(f"{PAGE_ID}-rpm-dupes-toggle", "checked"),
    prevent_initial_call=True,
)
def _rpm_merge_resolve(n_apply, n_cancel, pending, full_data, unreviewed_only, dupes_only):
    from dash import ctx
    no = dash.no_update
    triggered = ctx.triggered_id

    if triggered == f"{PAGE_ID}-rpm-merge-confirm-cancel" or not pending or not full_data:
        return no, no, no, no, no, no, False, None

    from data.reviews_db import merge_referring

    npi = pending["npi"]
    surv_addr = pending["survivor_address_key"]
    surv_key = pending["survivor_row_key"]
    loser_addr = pending["loser_address_keys"]
    loser_keys = set(pending["loser_row_keys"])

    # Gather grid-side values so merge_referring can persist correctly even
    # when neither side has a DB override row yet (source="lookup" case).
    survivor = next((r for r in full_data if r.get("row_key") == surv_key), None)
    losers = [r for r in full_data if r.get("row_key") in loser_keys]

    def _grid_fields(r):
        if not r:
            return {}
        return {
            "address_key": r.get("address_key", ""),
            "specialty": (r.get("specialty") or "").strip(),
            "institution": (r.get("institution") or "").strip(),
            "address": (r.get("address") or "").strip(),
            "city": (r.get("city") or "").strip(),
            "state": (r.get("state") or "").strip(),
            "zip_code": (r.get("zip") or "").strip(),
            "address_source": (r.get("address_source") or "").strip(),
            "reviewed": bool(r.get("reviewed")),
        }

    merge_referring(
        npi, surv_addr, loser_addr,
        survivor_defaults=_grid_fields(survivor),
        loser_defaults=[_grid_fields(l) for l in losers],
    )

    # In-memory grid update: gather loser values, merge into survivor where blank,
    # add their patient_counts, then drop loser rows.
    if survivor is not None:
        for key in ("specialty", "institution", "address", "city",
                    "state", "zip", "full_address"):
            if not (survivor.get(key) or "").strip():
                donor = next((l for l in losers if (l.get(key) or "").strip()), None)
                if donor:
                    survivor[key] = donor.get(key, "")
        survivor["patient_count"] = sum(
            int(r.get("patient_count") or 0) for r in losers + [survivor]
        )
        if any(l.get("reviewed") for l in losers):
            survivor["reviewed"] = True
        if any((l.get("address_source") or "") == "manual" for l in losers) \
                and not (survivor.get("address_source") or ""):
            survivor["address_source"] = "manual"

    row_data = [r for r in full_data if r.get("row_key") not in loser_keys]

    total = len(row_data)
    with_spec = sum(1 for r in row_data if r.get("specialty"))
    with_inst = sum(1 for r in row_data if r.get("institution"))
    reviewed_n = sum(1 for r in row_data if r.get("reviewed"))
    stats = (
        f"{total:,} providers  |  "
        f"{reviewed_n:,} reviewed  |  {total - reviewed_n:,} unreviewed  |  "
        f"{with_spec:,} specialty  |  {with_inst:,} institution"
    )
    visible = _rpm_visible(row_data, unreviewed_only, dupes_only)
    inst_rows, inst_count = _build_inst_grid_data(row_data)
    return visible, row_data, stats, str(total), inst_rows, inst_count, False, None


@callback(
    Output(f"{PAGE_ID}-rpm-poll", "disabled", allow_duplicate=True),
    Output(f"{PAGE_ID}-rpm-progress", "style", allow_duplicate=True),
    Output(f"{PAGE_ID}-rpm-progress-text", "style", allow_duplicate=True),
    Output(f"{PAGE_ID}-rpm-progress-text", "children", allow_duplicate=True),
    Input(f"{PAGE_ID}-rpm-npi-btn", "n_clicks"),
    State(f"{PAGE_ID}-rpm-grid", "rowData"),
    State(f"{PAGE_ID}-rpm-grid", "selectedRows"),
    prevent_initial_call=True,
)
def _rpm_start_npi_lookup(n, row_data, selected_rows):
    """Start background NPI specialty lookup. Uses selected rows if any, else unreviewed blanks."""
    if not n or not row_data:
        return dash.no_update, dash.no_update, dash.no_update, dash.no_update

    with _rpm_lock:
        if _rpm_progress["running"]:
            return dash.no_update, dash.no_update, dash.no_update, "Already running..."

    # Only run on selected rows
    if not selected_rows:
        return True, {"display": "none"}, {"display": "block"}, "Select rows first, then click to look up."
    blanks = [r for r in selected_rows if r.get("npi") and not r.get("specialty")]
    if not blanks:
        return True, {"display": "none"}, {"display": "block"}, "Selected rows already have specialties."

    # Deduplicate NPIs for API calls (same NPI at different addresses = same specialty)
    unique_npis = list({r["npi"] for r in blanks})

    with _rpm_lock:
        _rpm_progress.update(done=0, total=len(unique_npis), running=True, message="Starting NPI lookups...")

    # Build a map from NPI to the row info for display in review
    npi_to_rows = {}
    for r in blanks:
        if r["npi"] not in npi_to_rows:
            npi_to_rows[r["npi"]] = r

    def _bg():
        global _rpm_npi_results
        from utils.npi_lookup import batch_lookup_npis

        def _on_progress(done, total):
            with _rpm_lock:
                _rpm_progress["done"] = done
                _rpm_progress["message"] = f"Looking up NPI {done}/{total}..."

        api_results = batch_lookup_npis(unique_npis, on_progress=_on_progress)

        # Build review rows — one per NPI+address that was in blanks
        review = []
        for r in api_results:
            npi = r["npi"]
            row_info = npi_to_rows.get(npi, {})
            review.append({
                "accept": r["status"] == "found" and bool(r.get("specialty")),
                "npi": npi,
                "name": row_info.get("name", ""),
                "name_raw": row_info.get("name_raw", row_info.get("name", "")),
                "city": row_info.get("city", ""),
                "state": row_info.get("state", ""),
                "address": row_info.get("address", ""),
                "full_address": row_info.get("full_address", ""),
                "current_specialty": row_info.get("specialty", ""),
                "raw_taxonomy": r.get("raw_taxonomy") or "",
                "mapped_specialty": r.get("specialty") or "",
                "status": r["status"],
                "address_key": row_info.get("address_key", ""),
                "row_key": row_info.get("row_key", ""),
                "referral_count": row_info.get("patient_count", 0),
            })

        with _rpm_lock:
            _rpm_npi_results.clear()
            _rpm_npi_results.extend(review)
            _rpm_progress["running"] = False
            found = sum(1 for r in review if r["status"] == "found")
            _rpm_progress["message"] = f"Done. {found} found, {len(review) - found} not found. Review below."

    t = threading.Thread(target=_bg, daemon=True)
    t.start()

    return (
        False,  # enable polling
        {"display": "block"},
        {"display": "block"},
        f"Starting NPI lookups for {len(unique_npis)} NPIs...",
    )


@callback(
    Output(f"{PAGE_ID}-rpm-poll", "disabled", allow_duplicate=True),
    Output(f"{PAGE_ID}-rpm-progress", "value"),
    Output(f"{PAGE_ID}-rpm-progress", "style", allow_duplicate=True),
    Output(f"{PAGE_ID}-rpm-progress-text", "children", allow_duplicate=True),
    Output(f"{PAGE_ID}-rpm-progress-text", "style", allow_duplicate=True),
    Output(f"{PAGE_ID}-rpm-npi-review", "style"),
    Output(f"{PAGE_ID}-rpm-npi-review-grid", "rowData"),
    Output(f"{PAGE_ID}-rpm-grid", "rowData", allow_duplicate=True),
    Output(f"{PAGE_ID}-rpm-grid-full-store", "data", allow_duplicate=True),
    Output(f"{PAGE_ID}-rpm-ai-review", "opened"),
    Output(f"{PAGE_ID}-rpm-ai-review-grid", "rowData"),
    Input(f"{PAGE_ID}-rpm-poll", "n_intervals"),
    State(f"{PAGE_ID}-rpm-unreviewed-toggle", "checked"),
    State(f"{PAGE_ID}-rpm-dupes-toggle", "checked"),
    prevent_initial_call=True,
)
def _rpm_poll_progress(n, unreviewed_only, dupes_only):
    """Poll background task progress.

    Three terminal cases when running flips to False:
      * Provider AI finished with results → open the rpm-ai-review modal;
        do NOT refresh the rpm-grid (writes happen only after Apply Selected).
      * NPI lookup finished with results → open the NPI review side-panel.
      * Otherwise (no results to review) → rebuild rpm-grid rowData (full
        store) AND filtered subset (so the "Unreviewed only" toggle is
        preserved across the refresh).
    """
    with _rpm_lock:
        done = _rpm_progress["done"]
        total = _rpm_progress["total"]
        running = _rpm_progress["running"]
        msg = _rpm_progress["message"]

    pct = int(done / total * 100) if total > 0 else 0
    no = dash.no_update

    if running:
        return (False, pct, {"display": "block"}, msg, {"display": "block"},
                no, no, no, no, no, no)

    with _rpm_lock:
        npi_review_data = list(_rpm_npi_results)
        ai_review_data = list(_rpm_ai_review_results)

    # AI review modal: open it, don't touch the grid yet.
    if ai_review_data:
        return (
            True, 100, {"display": "none"}, msg, {"display": "block"},
            no, no, no, no, True, ai_review_data,
        )

    def _refresh_with_filter():
        try:
            fresh, _ = _build_rpm_grid_data()
        except Exception as e:
            print(f"[rpm-poll] grid refresh failed: {e}", flush=True)
            return no, no
        visible = _rpm_visible(fresh, unreviewed_only, dupes_only)
        return visible, fresh

    # NPI lookup completion: show the NPI review panel.
    if npi_review_data:
        visible, fresh = _refresh_with_filter()
        return (
            True, 100, {"display": "none"}, msg, {"display": "block"},
            {"display": "block"}, npi_review_data, visible, fresh, no, no,
        )

    # Fallthrough (e.g. AI returned no rows): refresh both stores, respect filter.
    visible, fresh = _refresh_with_filter()
    return (True, 100, {"display": "none"}, msg, {"display": "block"},
            no, no, visible, fresh, no, no)


@callback(
    Output(f"{PAGE_ID}-rpm-poll", "disabled", allow_duplicate=True),
    Output(f"{PAGE_ID}-rpm-progress", "style", allow_duplicate=True),
    Output(f"{PAGE_ID}-rpm-progress", "color"),
    Output(f"{PAGE_ID}-rpm-progress-text", "style", allow_duplicate=True),
    Output(f"{PAGE_ID}-rpm-progress-text", "children", allow_duplicate=True),
    Input(f"{PAGE_ID}-rpm-ai-btn", "n_clicks"),
    State(f"{PAGE_ID}-rpm-grid", "rowData"),
    State(f"{PAGE_ID}-rpm-grid", "selectedRows"),
    prevent_initial_call=True,
)
def _rpm_start_ai_lookup(n, row_data, selected_rows):
    """Start background Claude AI institution research. Results always go to
    the review modal; the user must Apply Selected to write to the DB."""
    if not n or not row_data:
        return dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update

    with _rpm_lock:
        if _rpm_progress["running"]:
            return dash.no_update, dash.no_update, dash.no_update, dash.no_update, "Already running..."

    if not selected_rows:
        return True, {"display": "none"}, "grape", {"display": "block"}, "Select rows first, then click to research."
    # Run on every selected row that has an NPI — even rows that already have
    # an institution. Re-researching is fine because:
    #  * specialty + address fills are gated to blank-only writes (won't
    #    overwrite a real value);
    #  * institution fills via bulk_upsert_referring's COALESCE — passing the
    #    AI value DOES overwrite, but in review mode the user can reject;
    #  * in auto mode the user picked these rows on purpose, so respect that.
    targets = [r for r in selected_rows if r.get("npi")]
    if not targets:
        return True, {"display": "none"}, "grape", {"display": "block"}, "Selected rows have no NPI."

    # Each row is a unique NPI+address — pass all details for institution research.
    # Pass first/last referral as the time anchor so the AI returns the address
    # the physician held during the referral window (some MDs change practices).
    physicians = [
        {
            "npi": r["npi"],
            "address_key": r.get("address_key", ""),
            "row_key": r.get("row_key", ""),
            "name": r.get("name", ""),
            "city_state": f"{r.get('city', '')}, {r.get('state', '')}".strip(", "),
            "department": r.get("department", ""),
            "first_referral": r.get("first_referral", ""),
            "last_referral": r.get("last_referral", ""),
            # Snapshot existing address — used to gate whether we accept an
            # AI-suggested address ("only if blank otherwise").
            "_addr_blank": not any(
                (r.get(k) or "").strip()
                for k in ("address", "city", "state", "zip")
            ),
            # Snapshot existing specialty — same "fill only when blank" rule.
            "_spec_blank": not (r.get("specialty") or "").strip(),
        }
        for r in targets
    ]

    with _rpm_lock:
        _rpm_progress.update(done=0, total=len(physicians), running=True,
                             message="Starting AI research...")
        _rpm_ai_review_results.clear()

    def _bg():
        from utils.institution_inference import infer_institutions
        from data.reviews_db import get_referring_institutions

        existing = get_referring_institutions()

        # row_key -> dict from infer_institutions (institution + optional address)
        all_results: dict[str, dict] = {}
        chunk_size = 15
        for i in range(0, len(physicians), chunk_size):
            chunk = physicians[i : i + chunk_size]
            chunk_results = infer_institutions(chunk, existing)
            for p in chunk:
                if p["npi"] in chunk_results:
                    all_results[p["row_key"]] = chunk_results[p["npi"]]
            existing = list(set(
                existing + [r["institution"] for r in chunk_results.values() if r.get("institution")]
            ))
            with _rpm_lock:
                _rpm_progress["done"] = min(i + chunk_size, len(physicians))
                _rpm_progress["message"] = f"Researching institutions... {_rpm_progress['done']}/{len(physicians)}"

        # Build review rows for the modal grid; user inspects and edits
        # before any DB writes happen.
        review_rows = []
        for p in physicians:
            res = all_results.get(p["row_key"]) or {}
            # Look up the source row to show current values
            src = next((r for r in targets if r.get("row_key") == p["row_key"]), {})
            cur_addr_full = ", ".join(
                s for s in (
                    (src.get("address") or "").strip(),
                    (src.get("city") or "").strip(),
                    (src.get("state") or "").strip(),
                    (src.get("zip") or "").strip(),
                ) if s
            )
            ai_addr_full = ", ".join(
                s for s in (
                    (res.get("address") or "").strip(),
                    (res.get("city") or "").strip(),
                    (res.get("state") or "").strip(),
                    (res.get("zip_code") or "").strip(),
                ) if s
            )
            inst = (res.get("institution") or "").strip()
            spec = (res.get("specialty") or "").strip()
            review_rows.append({
                "row_key": p["row_key"],
                "npi": p["npi"],
                "address_key": p["address_key"],
                "name": src.get("name", ""),
                "current_institution": src.get("institution", "") or "",
                "ai_institution": inst,
                "current_specialty": src.get("specialty", "") or "",
                "ai_specialty": spec,
                "current_address": cur_addr_full,
                "ai_address": ai_addr_full,
                "window": (res.get("effective_date_range") or "").strip(),
                "_addr_blank": p.get("_addr_blank", False),
                "_spec_blank": p.get("_spec_blank", False),
                "accept": bool(inst),  # default-check rows the AI succeeded on
            })
        with _rpm_lock:
            _rpm_ai_review_results.clear()
            _rpm_ai_review_results.extend(review_rows)
            _rpm_progress["running"] = False
            got = sum(1 for r in review_rows if r["ai_institution"])
            _rpm_progress["message"] = (
                f"AI returned proposals for {got} of {len(physicians)} — "
                f"review and Apply."
            )

    t = threading.Thread(target=_bg, daemon=True)
    t.start()

    return (
        False,
        {"display": "block"},
        "grape",
        {"display": "block"},
        f"Starting AI research for {len(physicians)} physicians...",
    )


# ==========================================================================
# Provider AI Review Modal — Accept All / Reject All / Apply Selected
# ==========================================================================

@callback(
    Output(f"{PAGE_ID}-rpm-ai-review-grid", "rowData", allow_duplicate=True),
    Input(f"{PAGE_ID}-rpm-ai-accept-all", "n_clicks"),
    State(f"{PAGE_ID}-rpm-ai-review-grid", "rowData"),
    prevent_initial_call=True,
)
def _rpm_ai_accept_all(n, data):
    if not n or not data:
        return dash.no_update
    for r in data:
        if r.get("ai_institution"):
            r["accept"] = True
    return data


@callback(
    Output(f"{PAGE_ID}-rpm-ai-review", "opened", allow_duplicate=True),
    Output(f"{PAGE_ID}-rpm-progress-text", "children", allow_duplicate=True),
    Input(f"{PAGE_ID}-rpm-ai-reject-all", "n_clicks"),
    prevent_initial_call=True,
)
def _rpm_ai_reject_all(n):
    if not n:
        return dash.no_update, dash.no_update
    with _rpm_lock:
        _rpm_ai_review_results.clear()
    return False, "Rejected all — no changes applied."


@callback(
    Output(f"{PAGE_ID}-rpm-grid", "rowData", allow_duplicate=True),
    Output(f"{PAGE_ID}-rpm-grid-full-store", "data", allow_duplicate=True),
    Output(f"{PAGE_ID}-rpm-ai-review", "opened", allow_duplicate=True),
    Output(f"{PAGE_ID}-rpm-progress-text", "children", allow_duplicate=True),
    Input(f"{PAGE_ID}-rpm-ai-apply", "n_clicks"),
    State(f"{PAGE_ID}-rpm-ai-review-grid", "rowData"),
    State(f"{PAGE_ID}-rpm-unreviewed-toggle", "checked"),
    State(f"{PAGE_ID}-rpm-dupes-toggle", "checked"),
    prevent_initial_call=True,
)
def _rpm_ai_apply(n, review_data, unreviewed_only, dupes_only):
    """Persist accepted rows. Edits to ai_institution/ai_specialty/ai_address
    in the grid are honored — if the user corrected the AI's value before
    accepting, that corrected value is what gets written.
    """
    if not n or not review_data:
        return dash.no_update, dash.no_update, dash.no_update, dash.no_update

    accepted = [r for r in review_data
                if r.get("accept") and (r.get("ai_institution") or "").strip()]
    if not accepted:
        return dash.no_update, dash.no_update, False, "No rows accepted — no changes applied."

    from data.reviews_db import (
        bulk_upsert_referring, add_institution, upsert_referring,
    )

    records = []
    addr_filled = 0
    spec_filled = 0
    for r in accepted:
        npi = r.get("npi", "")
        addr_key = r.get("address_key", "") or ""
        inst = (r.get("ai_institution") or "").strip()
        if not npi or not inst:
            continue

        # Specialty: in review mode the user explicitly chose to accept
        # this row, so write whatever they kept (or edited) regardless of
        # whether the original was blank. Empty string → leave existing.
        spec = (r.get("ai_specialty") or "").strip()
        spec_to_write = spec or None
        if spec_to_write:
            spec_filled += 1

        records.append({
            "npi": npi, "address_key": addr_key,
            "institution": inst,
            "specialty": spec_to_write,
            "source": "claude_ai",
        })
        add_institution(inst)

        # Address: same rule as specialty — accept means accept. Write
        # whenever the user kept an address, regardless of prior state.
        ai_addr = (r.get("ai_address") or "").strip()
        if ai_addr:
            # Parse the user-edited combined address back into components.
            # Same heuristic as the mobile drawer's clientside parser:
            # strip USA, pull 5-digit ZIP from end, then 2-letter state,
            # then last comma-separated segment is city, rest is street.
            import re as _re
            s = _re.sub(r"\s+", " ", ai_addr).strip()
            s = _re.sub(r",?\s*(USA|U\.S\.A\.|United States)\s*$", "", s,
                        flags=_re.I).strip()
            zip_ = ""
            m = _re.search(r"(\d{5})(?:-\d{4})?\s*$", s)
            if m:
                zip_ = m.group(1)
                s = _re.sub(r"[,\s]+$", "", s[:m.start()].strip())
            state_ = ""
            m = _re.search(r"[,\s]+([A-Za-z]{2})\s*$", s)
            STATES = {"AL","AK","AZ","AR","CA","CO","CT","DE","FL","GA","HI",
                      "ID","IL","IN","IA","KS","KY","LA","ME","MD","MA","MI",
                      "MN","MS","MO","MT","NE","NV","NH","NJ","NM","NY","NC",
                      "ND","OH","OK","OR","PA","RI","SC","SD","TN","TX","UT",
                      "VT","VA","WA","WV","WI","WY","DC"}
            if m and m.group(1).upper() in STATES:
                state_ = m.group(1).upper()
                s = _re.sub(r"[,\s]+$", "", s[:m.start()].strip())
            parts = [x.strip() for x in s.split(",") if x.strip()]
            if len(parts) >= 2:
                city_ = parts.pop()
                street = ", ".join(parts)
            elif len(parts) == 1:
                street, city_ = parts[0], ""
            else:
                street, city_ = "", ""
            try:
                upsert_referring(
                    npi=npi, address_key=addr_key,
                    address=street or None,
                    city=city_ or None,
                    state=state_ or None,
                    zip_code=zip_ or None,
                    address_source="claude_ai",
                    source="claude_ai",
                )
                addr_filled += 1
            except Exception as e:
                print(f"[rpm-ai-apply] address write failed for {npi}: {e}",
                      flush=True)

    if records:
        bulk_upsert_referring(records)

    with _rpm_lock:
        _rpm_ai_review_results.clear()

    try:
        fresh_rows, _ = _build_rpm_grid_data()
    except Exception:
        fresh_rows = None

    msg = (f"Applied {len(records)} institutions, {spec_filled} specialties, "
           f"{addr_filled} addresses.")
    if fresh_rows is None:
        return dash.no_update, dash.no_update, False, msg
    visible = _rpm_visible(fresh_rows, unreviewed_only, dupes_only)
    return visible, fresh_rows, False, msg


@callback(
    Output(f"{PAGE_ID}-rpm-download", "data"),
    Input(f"{PAGE_ID}-rpm-export-btn", "n_clicks"),
    State(f"{PAGE_ID}-rpm-grid", "rowData"),
    prevent_initial_call=True,
)
def _rpm_export(n, row_data):
    """Export grid data as CSV."""
    if not n or not row_data:
        return dash.no_update
    df = pd.DataFrame(row_data)
    return dcc.send_data_frame(df.to_csv, "referring_physicians.csv", index=False)


# --- Main grid cellRendererData: badge X clear ---
@callback(
    Output(f"{PAGE_ID}-rpm-grid", "rowData", allow_duplicate=True),
    Output(f"{PAGE_ID}-rpm-stats", "children", allow_duplicate=True),
    Output(f"{PAGE_ID}-rpm-inst-grid", "rowData", allow_duplicate=True),
    Output(f"{PAGE_ID}-rpm-inst-count", "children", allow_duplicate=True),
    Input(f"{PAGE_ID}-rpm-grid", "cellRendererData"),
    State(f"{PAGE_ID}-rpm-grid", "rowData"),
    prevent_initial_call=True,
)
def _rpm_main_grid_action(renderer_data, row_data):
    """Handle badge X clear from main grid."""
    no = dash.no_update
    if not renderer_data or not row_data:
        return (no,) * 4

    npi = renderer_data.get("npi", "")
    if not npi:
        return (no,) * 4

    from data.reviews_db import upsert_referring
    addr_k = renderer_data.get("address_key", "")
    row_key = renderer_data.get("row_key", "")
    new_inst = renderer_data.get("institution", "")

    upsert_referring(npi, address_key=addr_k, institution=new_inst or None, source="manual")

    for r in row_data:
        if r.get("row_key") == row_key:
            r["institution"] = new_inst
            r["source"] = "manual"
            break

    total = len(row_data)
    with_spec = sum(1 for r in row_data if r.get("specialty"))
    with_inst = sum(1 for r in row_data if r.get("institution"))
    reviewed_n = sum(1 for r in row_data if r.get("reviewed"))
    stats = (
        f"{total:,} providers  |  "
        f"{reviewed_n:,} reviewed  |  {total - reviewed_n:,} unreviewed  |  "
        f"{with_spec:,} specialty  |  {with_inst:,} institution"
    )
    inst_rows, inst_count = _build_inst_grid_data(row_data)
    return row_data, stats, inst_rows, inst_count


# --- Institution rename (edit in institution management grid) ---
@callback(
    Output(f"{PAGE_ID}-rpm-grid", "rowData", allow_duplicate=True),
    Output(f"{PAGE_ID}-rpm-stats", "children", allow_duplicate=True),
    Output(f"{PAGE_ID}-rpm-inst-grid", "rowData", allow_duplicate=True),
    Output(f"{PAGE_ID}-rpm-inst-count", "children", allow_duplicate=True),
    Input(f"{PAGE_ID}-rpm-inst-grid", "cellValueChanged"),
    State(f"{PAGE_ID}-rpm-grid", "rowData"),
    prevent_initial_call=True,
)
def _rpm_inst_rename(changed, row_data):
    """Rename an institution — propagates to all physicians."""
    if not changed or not row_data:
        return (dash.no_update,) * 4

    from data.reviews_db import rename_institution, add_institution

    row = changed[0].get("data", {}) if isinstance(changed, list) else changed.get("data", {})
    old_name = row.get("original_name", "")
    new_name = (row.get("name", "") or "").strip()

    if not old_name or not new_name or old_name == new_name:
        return (dash.no_update,) * 4

    rename_institution(old_name, new_name)
    add_institution(new_name)

    # Update all physician rows in grid
    for r in row_data:
        if r.get("institution") == old_name:
            r["institution"] = new_name

    total = len(row_data)
    with_spec = sum(1 for r in row_data if r.get("specialty"))
    with_inst = sum(1 for r in row_data if r.get("institution"))
    stats = (
        f"{total:,} referring physicians  |  "
        f"{with_spec:,} with specialty  |  {with_inst:,} with institution  |  "
        f"{total - with_spec:,} specialty blank  |  {total - with_inst:,} institution blank"
    )
    inst_rows, inst_count = _build_inst_grid_data(row_data)
    return row_data, stats, inst_rows, inst_count


# --- Institution delete (cellRendererData from inst grid) ---
@callback(
    Output(f"{PAGE_ID}-rpm-grid", "rowData", allow_duplicate=True),
    Output(f"{PAGE_ID}-rpm-stats", "children", allow_duplicate=True),
    Output(f"{PAGE_ID}-rpm-inst-grid", "rowData", allow_duplicate=True),
    Output(f"{PAGE_ID}-rpm-inst-count", "children", allow_duplicate=True),
    Input(f"{PAGE_ID}-rpm-inst-grid", "cellRendererData"),
    State(f"{PAGE_ID}-rpm-grid", "rowData"),
    prevent_initial_call=True,
)
def _rpm_inst_delete(renderer_data, row_data):
    """Delete an institution — clears from all physicians."""
    if not renderer_data or not row_data:
        return (dash.no_update,) * 4

    action = renderer_data.get("_action", "")
    name = renderer_data.get("name", "")

    if action != "delete" or not name:
        return (dash.no_update,) * 4

    from data.reviews_db import delete_institution

    delete_institution(name)

    # Clear from physician rows
    for r in row_data:
        if r.get("institution") == name:
            r["institution"] = ""

    total = len(row_data)
    with_spec = sum(1 for r in row_data if r.get("specialty"))
    with_inst = sum(1 for r in row_data if r.get("institution"))
    stats = (
        f"{total:,} referring physicians  |  "
        f"{with_spec:,} with specialty  |  {with_inst:,} with institution  |  "
        f"{total - with_spec:,} specialty blank  |  {total - with_inst:,} institution blank"
    )
    inst_rows, inst_count = _build_inst_grid_data(row_data)
    return row_data, stats, inst_rows, inst_count


# --- Institution export ---
@callback(
    Output(f"{PAGE_ID}-rpm-inst-download", "data"),
    Input(f"{PAGE_ID}-rpm-inst-export-btn", "n_clicks"),
    State(f"{PAGE_ID}-rpm-inst-grid", "rowData"),
    prevent_initial_call=True,
)
def _rpm_inst_export(n, inst_data):
    if not n or not inst_data:
        return dash.no_update
    df = pd.DataFrame(inst_data)[["name", "physician_count"]]
    df.columns = ["Institution", "Provider Count"]
    return dcc.send_data_frame(df.to_csv, "institutions.csv", index=False)


# --- Mark Reviewed (bulk) ---
@callback(
    Output(f"{PAGE_ID}-rpm-grid", "rowData", allow_duplicate=True),
    Output(f"{PAGE_ID}-rpm-grid-full-store", "data", allow_duplicate=True),
    Output(f"{PAGE_ID}-rpm-stats", "children", allow_duplicate=True),
    Input(f"{PAGE_ID}-rpm-reviewed-btn", "n_clicks"),
    State(f"{PAGE_ID}-rpm-grid-full-store", "data"),
    State(f"{PAGE_ID}-rpm-grid", "selectedRows"),
    State(f"{PAGE_ID}-rpm-unreviewed-toggle", "checked"),
    State(f"{PAGE_ID}-rpm-dupes-toggle", "checked"),
    prevent_initial_call=True,
)
def _rpm_mark_reviewed(n, full_data, selected_rows, unreviewed_only, dupes_only):
    """Mark selected rows as reviewed."""
    if not n or not full_data:
        return dash.no_update, dash.no_update, dash.no_update
    from data.reviews_db import set_reviewed_bulk, upsert_referring

    if not selected_rows:
        return dash.no_update, dash.no_update, dash.no_update

    row_data = full_data
    keys = []
    for r in selected_rows:
        npi = r.get("npi", "")
        addr_k = r.get("address_key", "")
        if npi:
            upsert_referring(npi, address_key=addr_k, source=r.get("source", "manual"))
            keys.append((npi, addr_k))

    if keys:
        set_reviewed_bulk(keys, reviewed=True)

    target_keys = {r.get("row_key") for r in selected_rows}
    for r in row_data:
        if r.get("row_key") in target_keys:
            r["reviewed"] = True

    total = len(row_data)
    with_spec = sum(1 for r in row_data if r.get("specialty"))
    with_inst = sum(1 for r in row_data if r.get("institution"))
    reviewed_n = sum(1 for r in row_data if r.get("reviewed"))
    stats = (
        f"{total:,} providers  |  "
        f"{reviewed_n:,} reviewed  |  {total - reviewed_n:,} unreviewed  |  "
        f"{with_spec:,} specialty  |  {with_inst:,} institution"
    )
    visible = _rpm_visible(row_data, unreviewed_only, dupes_only)
    return visible, row_data, stats




# --- Show/hide provider action buttons based on active tab ---
@callback(
    Output(f"{PAGE_ID}-rpm-action-btns", "style"),
    Input(f"{PAGE_ID}-rpm-tabs", "value"),
    prevent_initial_call=True,
)
def _rpm_toggle_action_btns(tab):
    if tab == "providers":
        return {"display": "flex"}
    return {"display": "none"}


# --- Clientside mirror of cell edits to full_store + stats ---
# Server callback (_rpm_save_edit) handles DB persistence but no longer echoes
# rowData/full_store/stats back, because that round-trip was slow AND racy with
# rapid edits (a stale server response would revert in-flight UI changes).
# Here we apply the edit to the in-memory full_store and recompute the stats
# pill instantly. AG Grid keeps its own local cell state via getRowId diffing.

clientside_callback(
    """function(cellChange, fullData) {
        var no = window.dash_clientside.no_update;
        if (!cellChange || !fullData) return [no, no];
        var ch = Array.isArray(cellChange) ? cellChange[0] : cellChange;
        if (!ch || !ch.data) return [no, no];
        var rowKey = ch.data.row_key;
        var colId = ch.colId || "";
        if (!rowKey || !colId) return [no, no];
        var newVal = ch.data[colId];

        var updated = fullData.map(function(r) {
            if (r && r.row_key === rowKey) {
                var nr = Object.assign({}, r);
                nr[colId] = newVal;
                // Mirror server-side behavior: content edits flip source to manual.
                // Pure reviewed-flag toggles preserve the original source.
                if (colId !== "reviewed") nr.source = "manual";
                if (colId === "full_address") nr.address_source = "manual";
                return nr;
            }
            return r;
        });

        var total = updated.length;
        var reviewed_n = 0, with_spec = 0, with_inst = 0;
        for (var i = 0; i < updated.length; i++) {
            var r = updated[i];
            if (r.reviewed) reviewed_n++;
            if ((r.specialty || "").trim()) with_spec++;
            if ((r.institution || "").trim()) with_inst++;
        }
        var fmt = function(n) { return n.toLocaleString(); };
        var stats = fmt(total) + " providers  |  " +
                    fmt(reviewed_n) + " reviewed  |  " +
                    fmt(total - reviewed_n) + " unreviewed  |  " +
                    fmt(with_spec) + " specialty  |  " +
                    fmt(with_inst) + " institution";
        return [updated, stats];
    }""",
    Output(f"{PAGE_ID}-rpm-grid-full-store", "data", allow_duplicate=True),
    Output(f"{PAGE_ID}-rpm-stats", "children", allow_duplicate=True),
    Input(f"{PAGE_ID}-rpm-grid", "cellValueChanged"),
    State(f"{PAGE_ID}-rpm-grid-full-store", "data"),
    prevent_initial_call=True,
)


# --- Unreviewed-only toggles ---
# Store the full dataset in a hidden Store. The toggle filters into the grid.
# When the grid rowData changes (edits), we update the store too.

clientside_callback(
    """function(unreviewedOnly, dupesOnly, fullData) {
        if (!fullData) return window.dash_clientside.no_update;
        var out = fullData;
        if (unreviewedOnly) {
            out = out.filter(function(r) { return !r.reviewed; });
        }
        if (dupesOnly) {
            var counts = {};
            fullData.forEach(function(r) {
                if (r && r.npi) counts[r.npi] = (counts[r.npi] || 0) + 1;
            });
            out = out.filter(function(r) { return counts[r.npi] > 1; });
        }
        return out;
    }""",
    Output(f"{PAGE_ID}-rpm-grid", "rowData", allow_duplicate=True),
    Input(f"{PAGE_ID}-rpm-unreviewed-toggle", "checked"),
    Input(f"{PAGE_ID}-rpm-dupes-toggle", "checked"),
    State(f"{PAGE_ID}-rpm-grid-full-store", "data"),
    prevent_initial_call=True,
)

clientside_callback(
    """function(checked, fullData) {
        if (!fullData) return window.dash_clientside.no_update;
        if (checked) {
            return fullData.filter(function(r) { return !r.reviewed; });
        }
        return fullData;
    }""",
    Output(f"{PAGE_ID}-rpm-diag-grid", "rowData", allow_duplicate=True),
    Input(f"{PAGE_ID}-rpm-diag-unreviewed-toggle", "checked"),
    State(f"{PAGE_ID}-rpm-diag-grid-full-store", "data"),
    prevent_initial_call=True,
)


# --- NPI Review: Accept All (check all rows) ---
@callback(
    Output(f"{PAGE_ID}-rpm-npi-review-grid", "rowData", allow_duplicate=True),
    Input(f"{PAGE_ID}-rpm-npi-accept-all", "n_clicks"),
    State(f"{PAGE_ID}-rpm-npi-review-grid", "rowData"),
    prevent_initial_call=True,
)
def _rpm_npi_accept_all(n, data):
    if not n or not data:
        return dash.no_update
    for r in data:
        if r.get("status") == "found" and r.get("mapped_specialty"):
            r["accept"] = True
    return data


# --- NPI Review: Reject All (uncheck all rows) ---
@callback(
    Output(f"{PAGE_ID}-rpm-npi-review-grid", "rowData", allow_duplicate=True),
    Input(f"{PAGE_ID}-rpm-npi-reject-all", "n_clicks"),
    State(f"{PAGE_ID}-rpm-npi-review-grid", "rowData"),
    prevent_initial_call=True,
)
def _rpm_npi_reject_all(n, data):
    if not n or not data:
        return dash.no_update
    for r in data:
        r["accept"] = False
    return data


# --- NPI Review: Apply accepted rows ---
@callback(
    Output(f"{PAGE_ID}-rpm-grid", "rowData", allow_duplicate=True),
    Output(f"{PAGE_ID}-rpm-stats", "children", allow_duplicate=True),
    Output(f"{PAGE_ID}-rpm-npi-review", "style", allow_duplicate=True),
    Output(f"{PAGE_ID}-rpm-progress-text", "children", allow_duplicate=True),
    Input(f"{PAGE_ID}-rpm-npi-apply", "n_clicks"),
    State(f"{PAGE_ID}-rpm-npi-review-grid", "rowData"),
    State(f"{PAGE_ID}-rpm-grid", "rowData"),
    prevent_initial_call=True,
)
def _rpm_npi_apply(n, review_data, row_data):
    if not n or not review_data:
        return (dash.no_update,) * 4
    from data.reviews_db import bulk_upsert_referring

    from config.settings import normalize_specialty
    accepted = [r for r in review_data if r.get("accept") and r.get("mapped_specialty")]
    if not accepted:
        return dash.no_update, dash.no_update, {"display": "none"}, "No rows accepted."

    # Normalize before saving
    for r in accepted:
        r["mapped_specialty"] = normalize_specialty(r["mapped_specialty"])

    # Save to SQLite
    records = [
        {"npi": r["npi"], "address_key": r.get("address_key", ""),
         "specialty": r["mapped_specialty"], "source": "npi_registry"}
        for r in accepted
    ]
    # Also apply to other rows with the same NPI (different addresses)
    npi_spec = {r["npi"]: r["mapped_specialty"] for r in accepted}
    if row_data:
        for r in row_data:
            if r["npi"] in npi_spec and not r.get("specialty"):
                records.append({
                    "npi": r["npi"], "address_key": r.get("address_key", ""),
                    "specialty": npi_spec[r["npi"]], "source": "npi_registry",
                })

    bulk_upsert_referring(records)

    # Refresh grid
    rows, stats = _build_rpm_grid_data()
    return rows, stats, {"display": "none"}, f"Applied {len(accepted)} specialty updates."


def _fetch_referral_detail(npi, addr_key, name):
    """Fetch referral detail rows for a given NPI + address key."""
    from data.loader import load_referrals
    ref = load_referrals()

    mask = ref["Referred By Prov NPI"].notna()
    ref_npi = ref[mask].copy()
    ref_npi["_npi"] = ref_npi["Referred By Prov NPI"].astype(float).astype(int).astype(str)
    ref_npi = ref_npi[ref_npi["_npi"] == npi]

    from data.reviews_db import _addr_key
    ref_npi["_ak"] = ref_npi.apply(
        lambda r: _addr_key(
            str(r.get("Referring Provider City", "")),
            str(r.get("Referring Provider State", "")),
            str(r.get("Referring Provider Zip Code", "")),
        ), axis=1,
    )
    ref_npi = ref_npi[ref_npi["_ak"] == addr_key]

    cols = ["Created", "MRN", "Patient Name", "Rfl Prim Dx", "Diagnoses", "Status", "First Appt", "Days to First Appt"]
    detail = ref_npi[[c for c in cols if c in ref_npi.columns]].copy()

    for dc in ["Created", "First Appt"]:
        if dc in detail.columns:
            detail[dc] = detail[dc].dt.strftime("%m/%d/%Y").fillna("")

    title = f"Referrals from {name} ({npi}) — {len(detail)} records"
    return title, detail.fillna("").to_dict("records")


# --- Referral detail: from Store (both grids write to it) or close button ---
@callback(
    Output(f"{PAGE_ID}-rpm-detail-panel", "style"),
    Output(f"{PAGE_ID}-rpm-detail-title", "children"),
    Output(f"{PAGE_ID}-rpm-detail-grid", "rowData"),
    Input(f"{PAGE_ID}-rpm-detail-store", "data"),
    Input(f"{PAGE_ID}-rpm-detail-close", "n_clicks"),
    prevent_initial_call=True,
)
def _rpm_show_detail(store_data, close_clicks):
    from dash import ctx

    if ctx.triggered_id == f"{PAGE_ID}-rpm-detail-close":
        return {"display": "none"}, "", []

    if not store_data or not store_data.get("npi"):
        return dash.no_update, dash.no_update, dash.no_update

    npi = store_data["npi"]
    addr_key = store_data.get("address_key", "")
    name = store_data.get("name", "")

    title, records = _fetch_referral_detail(npi, addr_key, name)
    return {"display": "block", "marginTop": "6px"}, title, records


# ==========================================================================
# Diagnosis Manager Callbacks
# ==========================================================================

# ---------------------------------------------------------------------------
# Subcategory inference from free text (given a known category)
# ---------------------------------------------------------------------------
_SUBCAT_TEXT_PATTERNS: dict[str, list[tuple[str, re.Pattern]]] = {
    "Breast": [
        ("Left",                    re.compile(r"\bleft\b|\blt\b|\b[Ll]\s+breast|\b[Ll]\.?\s*breast", re.I)),
        ("Right",                   re.compile(r"\bright\b|\brt\b|\b[Rr]\s+breast|\b[Rr]\.?\s*breast", re.I)),
        ("Male",                    re.compile(r"\bmale\b", re.I)),
        ("Unspecified Laterality",  re.compile(r"breast|breaast|bresst|brest|bilat|mammary", re.I)),
    ],
    "Central Nervous System": [
        ("Meningioma",              re.compile(r"mening", re.I)),
        ("Pituitary / Pineal",      re.compile(r"pituit|pineal", re.I)),
        ("Schwannoma",              re.compile(r"schwann|acoustic.?neuroma|vestibul", re.I)),
        ("AVM",                     re.compile(r"\bAVM\b|arteriovenous", re.I)),
        ("Ocular / Orbit",          re.compile(r"\borbit\b|orbital|\beye\b|ocular|choroid|chorodial|retino|uveal", re.I)),
        ("Paraganglioma",           re.compile(r"paraganglio|glomus|chemodectoma", re.I)),
        ("Craniopharyngioma",       re.compile(r"craniopharyn", re.I)),
        ("Spinal Cord",             re.compile(r"spinal.?cord|intramedull|cauda.?equina|brachial.?plex", re.I)),
        ("Glioma / Primary Brain",  re.compile(r"glioma|oligodendro|astrocyt|ependym", re.I)),
        ("Primary Brain",           re.compile(r"\bbrain\b|\bGBM\b|glioblas|cerebr|frontal.?lobe|parietal|temporal.?lobe|occipital|brain.?stem|cerebell", re.I)),
    ],
    "GU – Prostate": [
        ("Prostate Cancer",         re.compile(r".", re.I)),  # all prostate is one subcategory
    ],
    "GU – Non-Prostate": [
        ("Bladder",                 re.compile(r"bladder|bkadder|urothel|transitional.?cell", re.I)),
        ("Kidney / RCC",            re.compile(r"renal|kidney|\bRCC\b", re.I)),
        ("Testicular",              re.compile(r"testic|testis|seminoma", re.I)),
        ("Penile",                  re.compile(r"penile|penis", re.I)),
        ("Adrenal",                 re.compile(r"adrenal", re.I)),
        ("Urethra",                 re.compile(r"ureth", re.I)),
    ],
    "Gastrointestinal": [
        ("Rectal",                  re.compile(r"rectal|rectum|rectosig", re.I)),
        ("Esophageal",              re.compile(r"esophag|esphag|esopah|esopheal|gastic", re.I)),
        ("Pancreatic",              re.compile(r"pancrea", re.I)),
        ("Colon",                   re.compile(r"colon|cecum|sigmoid|splenic.?flex", re.I)),
        ("Anal",                    re.compile(r"\banal\b|\banus\b", re.I)),
        ("Gastric",                 re.compile(r"gastri|stomach", re.I)),
        ("Liver / HCC",             re.compile(r"liver|\bHCC\b|hepato", re.I)),
        ("Biliary",                 re.compile(r"bile|biliary|cholang|gallbladder", re.I)),
        ("GIST",                    re.compile(r"\bGIST\b|gastrointestinal.?stromal", re.I)),
        ("Small Intestine",         re.compile(r"small.?bowel|small.?intestin|duoden|jejun|ileum", re.I)),
    ],
    "Gynecologic": [
        ("Cervical",                re.compile(r"cervi|cerivx", re.I)),
        ("Uterine / Endometrial",   re.compile(r"uter|endomet|edometr|endrometr", re.I)),
        ("Ovarian",                 re.compile(r"ovar", re.I)),
        ("Vulvar",                  re.compile(r"vulv", re.I)),
        ("Vaginal",                 re.compile(r"vagin", re.I)),
    ],
    "Head and Neck": [
        ("Oropharynx",              re.compile(r"tonsil|oropharyn|\bBOT\b|base.?of.?tongue|tongue|tounge", re.I)),
        ("Larynx",                  re.compile(r"laryn|vocal.?cord|glotti|epiglott|arytenoid", re.I)),
        ("Nasopharynx",             re.compile(r"nasopharyn", re.I)),
        ("Oral Cavity",             re.compile(r"oral|mouth|buccal|gingiv|palat|retromolar|mandib|floor.?of.?mouth|lingual", re.I)),
        ("Salivary Gland",          re.compile(r"saliva|parotid|submandib|adenoid.?cystic", re.I)),
        ("Nasal Cavity / Sinus",    re.compile(r"sinus|nasal|maxill|ethmoid", re.I)),
        ("Thyroid",                 re.compile(r"thyroid", re.I)),
        ("Hypopharynx",             re.compile(r"hypopharyn|hypoharyn|pyriform", re.I)),
        ("Lip",                     re.compile(r"\blip\b", re.I)),
        ("Trachea",                 re.compile(r"trache", re.I)),
        ("Unknown Primary/Other",   re.compile(r"unknown.?prim|\bSCCA\b|neck.?mass|\bH&N\b|head.?neck|head.?and.?neck|head.?\s*neck|\bneck\b|\bthroat\b|pharynx$", re.I)),
    ],
    "Hematologic": [
        ("Myeloma / Plasmacytoma",  re.compile(r"myelom|meyloma|plasmacyt|\bMGUS\b|amyloid", re.I)),
        ("Hodgkin Lymphoma",        re.compile(r"hodgkin", re.I)),
        ("Mycosis Fungoides",       re.compile(r"mycosis|fungoid|sezary", re.I)),
        ("Leukemia",                re.compile(r"leukemi|\bAML\b|\bCLL\b|\bALL\b", re.I)),
        ("MDS/PMF/Splenomegaly",    re.compile(r"myelofibro|polycythem|spleen|spleno|myelodyspl|\bMDS\b", re.I)),
        ("Mantle Cell",             re.compile(r"mantle", re.I)),
        ("MALT",                    re.compile(r"\bMALT\b|marginal.?zone", re.I)),
        ("T-Cell Lymphoma",         re.compile(r"T.?cell", re.I)),
        ("Non-Hodgkin Lymphoma (Diffuse)", re.compile(r"\bDLBCL\b|diffuse.?large", re.I)),
        ("Non-Hodgkin Lymphoma (Follicular)", re.compile(r"follicular", re.I)),
        ("Non-Hodgkin Lymphoma (Other)", re.compile(r"lymph|lymhoma|\bNHL\b", re.I)),
    ],
    "Metastases & Palliative": [
        ("Brain Metastases",        re.compile(r"brain.?met|brain.?mets|cerebr.?met", re.I)),
        ("Bone Metastases",         re.compile(r"bone.?met|bone.?les|bony|lytic|patholog.?fract|spine|spinal|vertebr|femur|humer|rib|pelvi|sacr|hip|sternum|skull|lumbar|thorac.?spine|cervic.?spine|\bT\d|L\d|C\d.?spin", re.I)),
        ("Lung Metastases",         re.compile(r"lung.?met|pulm.?met|lung.?nod", re.I)),
        ("Liver Metastases",        re.compile(r"liver.?met|hepat.?met", re.I)),
        ("Lymph Node Metastases",   re.compile(r"lymph.?node|nodal.?met|supraclavic|axiall|mediast.?met|inguinal.?met", re.I)),
        ("Skin Metastases",         re.compile(r"skin.?met|cutane.?met", re.I)),
        ("Adrenal Metastases",      re.compile(r"adrenal.?met", re.I)),
        ("Other Metastases",        re.compile(r"met|palliati|\bSVC\b|\bPCI\b|cord.?compress|chest.?wall|chest\b|flank|thigh|arm\b|leg\b|shoulder|back.?pain|clavicle|axilla|maxill|orbit|mandib|groin|parotid|scalp|abdom", re.I)),
        ("Bone Metastases",         re.compile(r"\bbone\b", re.I)),
    ],
    "Sarcomas": [
        ("Bone Sarcoma",            re.compile(r"osteosarc|osteoblas|chondro|ewing|bone.?sarc|giant.?cell", re.I)),
        ("Peripheral Nerve Sheath", re.compile(r"nerve.?sheath|\bMPNST\b|neurofibro.?sarc", re.I)),
        ("Retroperitoneal Sarcoma", re.compile(r"retroperit|liposarcoma", re.I)),
        ("Soft Tissue Sarcoma",     re.compile(r"sarc|soft.?tissue|leiomyo|fibro|synovial|rhabdo|spindle|angiosarcoma|desmoid|fibromyxoid|dermatofibro|myxoid|undifferentiated.?pleo", re.I)),
    ],
    "Skin": [
        ("Melanoma",                re.compile(r"melan", re.I)),
        ("Merkel Cell",             re.compile(r"merkel|\bMCC\b", re.I)),
        ("Non-Melanoma Skin Cancer", re.compile(r"squam|basal.?cell|basil.?cell|\bBCC\b|\bSCC\b|skin|cutane|scalp|ear\b|nose\b|eyelid|forehead|cheek|temple|sebaceous|carcinoma|\blip\b", re.I)),
    ],
    "Benign Diseases": [
        ("Dupuytren / Plantar",     re.compile(r"dupuytr|plantar.?fibro|palmar|ledderhose|finger", re.I)),
        ("Keloid / Scar",           re.compile(r"keloid|hypertrophic.?scar|\bHHT\b|osler.?weber", re.I)),
        ("Heterotopic Ossification", re.compile(r"heterotopic|het\s*erotrophic|\bHO\b", re.I)),
        ("Hemangioma",              re.compile(r"hemangioma|\bAVM\b|arteriovenous", re.I)),
        ("Orbital Pseudotumor",     re.compile(r"orbital|pseudotumor|trigeminal|neuralgia|graves", re.I)),
        ("Gynecomastia",            re.compile(r"gynecomast", re.I)),
        ("Osteoarthritis",          re.compile(r"osteoarthr|arthriti|bursitis|osteopor", re.I)),
        ("Neurofibromatosis",       re.compile(r"neurofibro", re.I)),
    ],
    "Thoracic": [
        ("Lung Cancer",             re.compile(r"lung|\bNSCL\b|\bSCLC\b|pulmon|bronch", re.I)),
        ("Mesothelioma",            re.compile(r"mesothel", re.I)),
        ("Thymic",                  re.compile(r"thym", re.I)),
        ("Mediastinal",             re.compile(r"mediast", re.I)),
        ("Neuroendocrine",          re.compile(r"neuroendoc|carcinoid|\bNET\b", re.I)),
    ],
}


def _infer_subcategory(text: str, category: str) -> str:
    """Infer subcategory from free text given a known category."""
    if not text or not category:
        return ""
    patterns = _SUBCAT_TEXT_PATTERNS.get(category)
    if not patterns:
        return ""
    for subcat, pat in patterns:
        if pat.search(text):
            return subcat
    return ""


# Load descriptions from the CSV file at module level
def _load_diag_descriptions() -> dict[str, str]:
    """Load ICD code descriptions from diagnosis_subcategories.csv."""
    import csv as csv_mod
    csv_path = Path(__file__).resolve().parent.parent / "data" / "diagnosis_subcategories.csv"
    if not csv_path.exists():
        return {}
    result = {}
    with open(csv_path, newline="", encoding="utf-8") as f:
        for row in csv_mod.DictReader(f):
            code = row["icd_code"].strip()
            desc = row.get("description", "").strip()
            if code and desc:
                result[code] = desc
    return result

_DIAG_DESCRIPTIONS: dict[str, str] = _load_diag_descriptions()

# Cached referral data + per-source index mapping for diagnosis detail panel.
# Keyed by ICD code (or lowercased free-text); each value lists the row
# indices for rad-onc and medonc separately so the drill-down can render
# rows from both dataframes with a Source column.
_diag_detail_ref: pd.DataFrame | None = None
_diag_detail_medonc_ref: pd.DataFrame | None = None
_diag_detail_indices: dict[str, dict[str, list[int]]] = {}


def _resolve_referral_diagnosis(row, cv_mrn_dx, course_mrn_dx, c2c, base_map,
                                is_medonc: bool = False):
    """Resolve a single referral row to (key, description, source_type).

    Priority cascade:
    1. CV DiagnosisCodes — what we actually treated them for (linked patients)
    2. Course DiagnosisCodes — temporally matched course (within -30 to +180 days)
    3. Med-Onc only: structured ``ICD-10 Diagnosis Code`` + ``Onc Dx`` columns
       (authoritative single-code fields, populated for ~56% of Med-Onc rows).
       Used in preference to the messy multi-code ``Diagnoses`` text since
       Med-Onc PRCS rows often carry admin/symptom companion codes alongside
       the real diagnosis.
    4. ICD-10 codes parsed from ``Diagnoses`` column (single, or _pick_best_icd
       for multi-code)
    5. ICD-9 codes from ``Diagnoses`` column
    6. Free-text fallback (Rfl Prim Dx or Diagnoses, lowercased as the key)

    For rad-onc rows the cascade is unchanged (tier 3 is skipped). Linked
    Med-Onc rows still resolve via tier 1/2 (rad-onc treatment data wins over
    Med-Onc's own coding when we know what we treated).

    Returns (key, description, source_type) where:
    - key: ICD code or lowercased free-text for aggregation
    - description: human-readable label
    - source_type: "cv", "course", "icd", or "free-text"
    """
    mrn = row.get("MRN")
    diag_text = str(row.get("Diagnoses", "")) if pd.notna(row.get("Diagnoses")) else ""
    prim_dx = str(row.get("Rfl Prim Dx", "")) if pd.notna(row.get("Rfl Prim Dx")) else ""

    # --- Tier 1: CV diagnosis (what we treated) ---
    if mrn is not None and pd.notna(mrn):
        cv_code = cv_mrn_dx.get(int(mrn))
        if cv_code and cv_code in c2c:
            desc = _DIAG_DESCRIPTIONS.get(cv_code, cv_code)
            return cv_code, desc, "cv"

    # --- Tier 2: Course diagnosis (temporally matched) ---
    if mrn is not None and pd.notna(mrn):
        created = row.get("Created")
        if created is not None and pd.notna(created):
            mrn_int = int(mrn)
            course_entries = course_mrn_dx.get(mrn_int, [])
            for course_date, course_code in course_entries:
                gap = (course_date - created).days
                if -30 <= gap <= 180:
                    if course_code in c2c:
                        desc = _DIAG_DESCRIPTIONS.get(course_code, course_code)
                        return course_code, desc, "course"
                    break  # found a temporal match but code not in c2c, fall through

    # --- Tier 3 (Med-Onc only): authoritative ICD-10 Diagnosis Code + Onc Dx ---
    # Standalone Med-Onc rows (no rad-onc treatment match) use the structured
    # PRCS columns directly instead of parsing the multi-code Diagnoses text,
    # which often carries admin/symptom codes (Z80.3, R19.x) alongside the
    # real diagnosis and produces the wrong pick.
    if is_medonc:
        icd_col = row.get("ICD-10 Diagnosis Code")
        if pd.notna(icd_col):
            # Field may be comma-separated when the referral lists multiple codes;
            # take the first one as the authoritative primary.
            first_code = str(icd_col).split(",")[0].strip()
            if first_code:
                onc_dx = row.get("Onc Dx")
                desc = (str(onc_dx).strip()
                        if pd.notna(onc_dx) and str(onc_dx).strip()
                        else _DIAG_DESCRIPTIONS.get(first_code, first_code))
                return first_code, desc, "icd"

    # --- Tier 4: ICD codes from Diagnoses column ---
    icd10_codes = _ICD10_RE.findall(diag_text)
    icd9_codes = _ICD9_RE.findall(diag_text)

    if icd10_codes:
        if len(icd10_codes) == 1:
            # Single code — straightforward
            code = icd10_codes[0]
            desc = _extract_icd_desc(diag_text, code)
            return code, desc, "icd"

        # Multi-code: pick the one that best matches Rfl Prim Dx
        if prim_dx:
            # Strip bracket reference from Rfl Prim Dx for matching
            prim_text = re.sub(r"\s*\[.*?\]\s*$", "", prim_dx).strip()
            best_code = _pick_best_icd(icd10_codes, prim_text, diag_text, c2c)
            desc = _extract_icd_desc(diag_text, best_code) or prim_text
            return best_code, desc, "icd"

        # No Rfl Prim Dx — take first code
        code = icd10_codes[0]
        desc = _extract_icd_desc(diag_text, code)
        return code, desc, "icd"

    if icd9_codes:
        code = icd9_codes[0]
        return code, "", "icd"

    # --- Tier 4: Free-text ---
    text = prim_dx.strip() if prim_dx.strip() else diag_text.strip()
    # Strip bracket reference
    text = re.sub(r"\s*\[.*?\]\s*$", "", text).strip()
    if text and text.lower() not in ("nan", "none", ""):
        return text.lower(), text, "free-text"

    return None, "", ""


def _extract_icd_desc(diag_text, code):
    """Extract the description text associated with an ICD code in a Diagnoses string."""
    # Find text after "code (ICD-...) - description"
    pattern = re.escape(code) + r"\s*\(ICD-\d+-CM\)\s*-\s*"
    m = re.search(pattern, diag_text)
    if m:
        rest = diag_text[m.end():]
        # Take until next ICD code or end of line
        end = re.search(r"\n|[A-Z]\d[0-9A-Z].*?\(ICD-", rest)
        desc = rest[:end.start()].strip() if end else rest.strip()
        # Also check for "ICD-9 code - desc" continuation
        desc = re.sub(r"\s*\d{3}(?:\.\d+)?\s*\(ICD-9-CM\)\s*-\s*", " ", desc).strip()
        return desc
    return _DIAG_DESCRIPTIONS.get(code, "")


def _is_cancer_code(code: str) -> bool:
    """True for ICD-10 Ch. II Neoplasm codes worth carrying as the primary
    diagnosis: C00-C97 (malignant) and D00-D49 (in situ / benign / uncertain
    behavior). Excludes D50-D89 (blood/blood-forming-organ diseases) and
    all non-Ch. II codes (Z = factors influencing health, R = symptoms,
    N = genitourinary diseases, etc.) — those are real ICD codes but not
    things rad-onc would code as the treated diagnosis.
    """
    if not code:
        return False
    head = code[0]
    if head == "C":
        return True
    if head == "D" and len(code) >= 3:
        try:
            return int(code[1:3]) <= 49
        except ValueError:
            return False
    return False


def _pick_best_icd(codes, prim_text, diag_text, c2c):
    """For multi-ICD referrals, pick the code that best matches Rfl Prim Dx.

    Priority cascade:
    1. If Rfl Prim Dx mentions mets → pick a C77/C78/C79 metastasis code
    2. Among non-mets candidates, search by quality tier:
       a. Codes already in our taxonomy (c2c-known)
       b. Cancer codes per ``_is_cancer_code`` (Ch. II Neoplasms)
       c. All non-mets codes (last resort)
    3. Within each tier, prefer the code whose category matches
       ``_categorise_text(Rfl Prim Dx)`` when that yields a category;
       else take the first code in the tier.
    4. Fall back to the first code overall when nothing else fits.

    The tiered approach addresses Med-Onc referrals where the Diagnoses
    column carries both a real cancer code (e.g. C50.911) and an
    administrative companion (Z80.3 family history, R19.00 swelling, etc.).
    The old behaviour took the first non-mets code, which was often the
    administrative one and left the referral permanently uncategorised.
    """
    prim_lower = prim_text.lower()

    # Check if Rfl Prim Dx is about metastases
    is_mets = bool(re.search(
        r"metast|bone met|brain met|lung met|liver met|cord.?compress"
        r"|secondary|mets\b|\bmet\b", prim_lower))

    # Separate mets codes (C79.x, C77.x, C78.x) from everything else
    mets_codes = [c for c in codes if re.match(r"C7[789]", c)]
    if is_mets and mets_codes:
        return mets_codes[0]

    non_mets = [c for c in codes if c not in mets_codes]
    if non_mets:
        text_cat = _categorise_text(prim_text)
        tiers = [
            [c for c in non_mets if c in c2c],          # known cancer codes first
            [c for c in non_mets if _is_cancer_code(c)],  # any Ch. II Neoplasm
            non_mets,                                    # anything left
        ]
        for pool in tiers:
            if not pool:
                continue
            if text_cat:
                for code in pool:
                    if c2c.get(code) == text_cat:
                        return code
            return pool[0]

    return codes[0]


def _build_diag_grid_data():
    """Build diagnosis grid for referral-only entries.

    Uses a priority cascade per referral to determine the primary diagnosis:
    1. CV DiagnosisCodes — what we actually treated them for
    2. Course DiagnosisCodes — temporally matched course (-30 to +180 days)
    3. Rfl Prim Dx — what the referral is for (+ best-match ICD from Diagnoses)
    4. ICD code from Diagnoses column
    5. Free-text from Diagnoses column

    Shows entries NOT in the base ARIA lookup CSV. Aggregated by unique
    diagnosis key (ICD code or normalized free-text), pooled across rad-onc
    referrals and med-onc PRCS referrals so a diagnosis appearing only on
    the med-onc side still surfaces here for review.
    """
    from data.loader import (
        load_referrals, load_medonc_referrals, load_clinic_visits, load_courses,
    )
    from data.reviews_db import get_all_diagnosis_overrides

    ref = load_referrals()
    medonc = load_medonc_referrals()
    overrides = get_all_diagnosis_overrides()
    base_map = get_all_subcategory_entries()

    # Build MRN → primary CV DiagnosisCode map
    cv_mrn_dx: dict[int, str] = {}
    try:
        cv = load_clinic_visits()
        if not cv.empty and "DiagnosisCodes" in cv.columns and "PatientId" in cv.columns:
            cv_diag = cv[cv["DiagnosisCodes"].notna()][["PatientId", "DiagnosisCodes"]].copy()
            cv_diag = cv_diag.drop_duplicates("PatientId")
            for _, r in cv_diag.iterrows():
                first_code = str(r["DiagnosisCodes"]).split(",")[0].strip()
                if first_code:
                    cv_mrn_dx[int(r["PatientId"])] = first_code
    except Exception:
        pass

    # Build MRN → [(course_start_date, dx_code), ...] sorted by date
    # Used for temporal matching: find a course within -30 to +180 days of referral
    course_mrn_dx: dict[int, list[tuple[pd.Timestamp, str]]] = {}
    try:
        courses = load_courses()
        if not courses.empty and "DiagnosisCodes" in courses.columns:
            c_dx = courses[courses["DiagnosisCodes"].notna() & courses["CourseStartDate"].notna()].copy()
            c_dx = c_dx.sort_values("CourseStartDate")
            for _, r in c_dx.iterrows():
                mrn = int(r["PatientId"])
                code = str(r["DiagnosisCodes"]).split(",")[0].strip()
                if code:
                    if mrn not in course_mrn_dx:
                        course_mrn_dx[mrn] = []
                    course_mrn_dx[mrn].append((r["CourseStartDate"], code))
    except Exception:
        pass

    # Aggregate: key → {count, description, source_type, indices_by_origin}
    # indices_by_origin tracks which referral rows contributed, split by
    # origin ("radonc" / "medonc"), so the detail panel can render rows
    # from the correct dataframe.
    agg: dict[str, dict] = {}

    def _ingest(df, origin):
        if df is None or df.empty:
            return
        is_medonc = (origin == "medonc")
        for idx, row in df.iterrows():
            key, desc, src_type = _resolve_referral_diagnosis(
                row, cv_mrn_dx, course_mrn_dx, _DIAG_C2C, base_map,
                is_medonc=is_medonc,
            )
            if key is None:
                continue
            # Skip codes already in the ARIA base CSV (managed on Diagnosis page)
            if src_type in ("icd", "cv", "course") and key in base_map:
                continue

            if key not in agg:
                agg[key] = {
                    "desc": desc, "type": src_type,
                    "indices": {"radonc": [], "medonc": []},
                }
            agg[key]["indices"][origin].append(idx)
            # Keep the best description (longest non-empty)
            if desc and len(desc) > len(agg[key]["desc"]):
                agg[key]["desc"] = desc

    _ingest(ref, "radonc")
    _ingest(medonc, "medonc")

    # Cache the referral dataframes + per-origin index mapping for the detail panel
    global _diag_detail_ref, _diag_detail_medonc_ref, _diag_detail_indices
    _diag_detail_ref = ref
    _diag_detail_medonc_ref = medonc
    _diag_detail_indices = {k: v["indices"] for k, v in agg.items()}

    # Build grid rows
    rows = []
    for key, info in agg.items():
        is_icd = info["type"] in ("icd", "cv")
        code = key if is_icd else ""
        desc = info["desc"]
        rad_n = len(info["indices"]["radonc"])
        med_n = len(info["indices"]["medonc"])
        pts = rad_n + med_n
        src_type = info["type"]

        # Origin badge: rad-onc-only / medonc-only / both
        if rad_n and med_n:
            origin = "both"
        elif med_n:
            origin = "medonc"
        else:
            origin = "rad-onc"

        # Resolve category/subcategory
        if is_icd:
            cat = _DIAG_C2C.get(code, "")
            sub = ""
        else:
            cat = _categorise_text(desc) or ""
            sub = ""

        source = src_type
        reviewed = False

        # Check DB override (keyed by code or raw text)
        override_key = code if is_icd else desc
        if override_key in overrides:
            ov = overrides[override_key]
            cat = ov["category"]
            sub = ov["subcategory"]
            source = ov["source"]
            reviewed = ov.get("reviewed", False)

        # Infer subcategory from text if we have category but not subcategory
        if cat and not sub:
            infer_text = desc if desc else (_DIAG_DESCRIPTIONS.get(code, "") if code else "")
            if infer_text:
                sub = _infer_subcategory(infer_text, cat)

        if not desc and code:
            desc = _DIAG_DESCRIPTIONS.get(code, "")

        rows.append({
            "icd_code": code,
            "description": desc,
            "category": cat,
            "subcategory": sub,
            "patients": pts,
            "rad_onc_count": rad_n,
            "medonc_count": med_n,
            "origin": origin,
            "source": source,
            "reviewed": reviewed,
        })

    rows.sort(key=lambda r: r["patients"], reverse=True)

    total = len(rows)
    icd_count = sum(1 for r in rows if r["icd_code"])
    text_count = total - icd_count
    categorized = sum(1 for r in rows if r["category"])
    overridden = sum(1 for r in rows if r["source"] not in ("icd", "cv", "course", "free-text"))
    medonc_only = sum(1 for r in rows if r["origin"] == "medonc")
    stats = (
        f"{icd_count:,} ICD  |  {text_count:,} free-text  |  "
        f"{categorized:,} categorized  |  {total - categorized:,} unmapped  |  "
        f"{medonc_only:,} med-onc only  |  "
        f"{overridden:,} overrides"
    )
    return rows, str(total), stats


@callback(
    Output(f"{PAGE_ID}-rpm-diag-grid", "rowData", allow_duplicate=True),
    Output(f"{PAGE_ID}-rpm-diag-grid-full-store", "data", allow_duplicate=True),
    Output(f"{PAGE_ID}-rpm-diag-stats", "children", allow_duplicate=True),
    Input(f"{PAGE_ID}-rpm-diag-grid", "cellValueChanged"),
    State(f"{PAGE_ID}-rpm-diag-grid-full-store", "data"),
    State(f"{PAGE_ID}-rpm-diag-unreviewed-toggle", "checked"),
    prevent_initial_call=True,
)
def _rpm_diag_save_edit(changed, full_data, unreviewed_only):
    """Save a manual cell edit (category, subcategory, or reviewed) to SQLite."""
    if not changed:
        return dash.no_update, dash.no_update, dash.no_update
    from data.reviews_db import upsert_diagnosis_override

    row_data = full_data or []
    row = changed[0].get("data", {}) if isinstance(changed, list) else changed.get("data", {})
    code = row.get("icd_code", "")
    desc = row.get("description", "")
    override_key = code or desc
    if not override_key:
        return dash.no_update, dash.no_update, dash.no_update

    col = changed[0].get("colId", "") if isinstance(changed, list) else changed.get("colId", "")
    cat = row.get("category", "")
    sub = row.get("subcategory", "")
    reviewed = row.get("reviewed", False)

    upsert_diagnosis_override(override_key, category=cat, subcategory=sub, source="manual")
    if col == "reviewed":
        from data.reviews_db import set_diagnosis_reviewed_bulk
        set_diagnosis_reviewed_bulk([override_key], reviewed=bool(reviewed))

    # Update full store
    match_key = code if code else desc
    for r in row_data:
        rk = r.get("icd_code") or r.get("description", "")
        if rk == match_key:
            r["category"] = cat
            r["subcategory"] = sub
            r["reviewed"] = reviewed
            r["source"] = "manual"
            break

    total = len(row_data)
    categorized = sum(1 for r in row_data if r.get("category"))
    reviewed_n = sum(1 for r in row_data if r.get("reviewed"))
    stats = (
        f"{total:,} entries  |  {categorized:,} categorized  |  "
        f"{reviewed_n:,} reviewed  |  {total - reviewed_n:,} unreviewed"
    )
    visible = [r for r in row_data if not r.get("reviewed")] if unreviewed_only else row_data
    return visible, row_data, stats


@callback(
    Output(f"{PAGE_ID}-rpm-diag-download", "data"),
    Input(f"{PAGE_ID}-rpm-diag-export-btn", "n_clicks"),
    State(f"{PAGE_ID}-rpm-diag-grid", "rowData"),
    prevent_initial_call=True,
)
def _rpm_diag_export(n, diag_data):
    """Export diagnosis mapping as CSV."""
    if not n or not diag_data:
        return dash.no_update
    df = pd.DataFrame(diag_data)[["icd_code", "description", "category", "subcategory", "patients", "source"]]
    df.columns = ["ICD Code", "Description", "Category", "Subcategory", "Patients", "Source"]
    return dcc.send_data_frame(df.to_csv, "referral_diagnosis_mappings.csv", index=False)


# --- Diagnosis Manager: Mark Reviewed ---
@callback(
    Output(f"{PAGE_ID}-rpm-diag-grid", "rowData", allow_duplicate=True),
    Output(f"{PAGE_ID}-rpm-diag-grid-full-store", "data", allow_duplicate=True),
    Output(f"{PAGE_ID}-rpm-diag-stats", "children", allow_duplicate=True),
    Input(f"{PAGE_ID}-rpm-diag-reviewed-btn", "n_clicks"),
    State(f"{PAGE_ID}-rpm-diag-grid-full-store", "data"),
    State(f"{PAGE_ID}-rpm-diag-grid", "selectedRows"),
    State(f"{PAGE_ID}-rpm-diag-unreviewed-toggle", "checked"),
    prevent_initial_call=True,
)
def _rpm_diag_mark_reviewed(n, full_data, selected_rows, unreviewed_only):
    if not n or not full_data or not selected_rows:
        return dash.no_update, dash.no_update, dash.no_update
    from data.reviews_db import upsert_diagnosis_override, set_diagnosis_reviewed_bulk

    row_data = full_data
    codes = []
    for r in selected_rows:
        key = r.get("icd_code") or r.get("description", "")
        if key:
            upsert_diagnosis_override(
                key, category=r.get("category", ""),
                subcategory=r.get("subcategory", ""), source=r.get("source", "manual"),
            )
            codes.append(key)
    if codes:
        set_diagnosis_reviewed_bulk(codes, reviewed=True)

    target_keys = {r.get("icd_code") or r.get("description", "") for r in selected_rows}
    for r in row_data:
        key = r.get("icd_code") or r.get("description", "")
        if key in target_keys:
            r["reviewed"] = True

    total = len(row_data)
    categorized = sum(1 for r in row_data if r.get("category"))
    reviewed_n = sum(1 for r in row_data if r.get("reviewed"))
    stats = (
        f"{total:,} entries  |  {categorized:,} categorized  |  "
        f"{reviewed_n:,} reviewed  |  {total - reviewed_n:,} unreviewed"
    )
    visible = [r for r in row_data if not r.get("reviewed")] if unreviewed_only else row_data
    return visible, row_data, stats


# --- Diagnosis Manager: Detail Panel ---
@callback(
    Output(f"{PAGE_ID}-rpm-diag-detail-panel", "style"),
    Output(f"{PAGE_ID}-rpm-diag-detail-title", "children"),
    Output(f"{PAGE_ID}-rpm-diag-detail-grid", "rowData"),
    Input(f"{PAGE_ID}-rpm-diag-detail-store", "data"),
    Input(f"{PAGE_ID}-rpm-diag-detail-close", "n_clicks"),
    prevent_initial_call=True,
)
def _rpm_diag_show_detail(store_data, close_clicks):
    from dash import ctx
    if ctx.triggered_id == f"{PAGE_ID}-rpm-diag-detail-close":
        return {"display": "none"}, "", []
    if not store_data:
        return dash.no_update, dash.no_update, dash.no_update

    icd_code = store_data.get("icd_code", "")
    description = store_data.get("description", "")

    # Use the cached index mapping from _build_diag_grid_data.
    # _diag_detail_indices is now {key: {"radonc": [...], "medonc": [...]}}
    # so the drill-down can show rows from both dataframes side-by-side.
    lookup_key = icd_code if icd_code else description.lower()
    idx_map = _diag_detail_indices.get(lookup_key) or {}
    rad_idx = idx_map.get("radonc", [])
    med_idx = idx_map.get("medonc", [])

    cols = ["Created", "MRN", "Patient Name", "Rfl Prim Dx", "Diagnoses", "Status"]
    frames = []

    if rad_idx and _diag_detail_ref is not None:
        rad = _diag_detail_ref.loc[rad_idx, [c for c in cols if c in _diag_detail_ref.columns]].copy()
        rad["Source"] = "Rad-Onc"
        frames.append(rad)

    if med_idx and _diag_detail_medonc_ref is not None:
        med = _diag_detail_medonc_ref.loc[med_idx, [c for c in cols if c in _diag_detail_medonc_ref.columns]].copy()
        med["Source"] = "Med-Onc"
        frames.append(med)

    if not frames:
        label = icd_code or description[:50]
        return {"display": "block", "marginTop": "6px"}, f"{label} — 0 records", []

    detail = pd.concat(frames, ignore_index=True)
    if "Created" in detail.columns:
        detail["Created"] = pd.to_datetime(detail["Created"], errors="coerce") \
            .dt.strftime("%m/%d/%Y").fillna("")
    detail = detail.sort_values("Created", ascending=False, na_position="last")

    label = f"ICD {icd_code}" if icd_code else f"\"{description[:50]}\""
    title = f"Referrals — {label} — {len(detail)} records"
    return {"display": "block", "marginTop": "6px"}, title, detail.fillna("").to_dict("records")


# ==========================================================================
# Diagnosis AI Classification
# ==========================================================================

@callback(
    Output(f"{PAGE_ID}-rpm-diag-ai-poll", "disabled"),
    Output(f"{PAGE_ID}-rpm-diag-ai-progress", "style"),
    Output(f"{PAGE_ID}-rpm-diag-ai-progress-text", "style"),
    Output(f"{PAGE_ID}-rpm-diag-ai-progress-text", "children"),
    Input(f"{PAGE_ID}-rpm-diag-ai-btn", "n_clicks"),
    State(f"{PAGE_ID}-rpm-diag-grid", "rowData"),
    State(f"{PAGE_ID}-rpm-diag-grid", "selectedRows"),
    prevent_initial_call=True,
)
def _rpm_diag_start_ai(n, row_data, selected_rows):
    """Start background AI classification for selected diagnosis entries."""
    if not n or not row_data:
        return dash.no_update, dash.no_update, dash.no_update, dash.no_update

    with _diag_ai_lock:
        if _diag_ai_progress["running"]:
            return dash.no_update, dash.no_update, dash.no_update, "Already running..."

    if not selected_rows:
        return True, {"display": "none"}, {"display": "block"}, "Select rows first, then click to classify."

    # Build entries for the API
    entries = []
    for r in selected_rows:
        key = r.get("icd_code") or r.get("description", "")
        if not key:
            continue
        entries.append({
            "key": key,
            "icd_code": r.get("icd_code", ""),
            "description": r.get("description", ""),
            "current_category": r.get("category", ""),
            "current_subcategory": r.get("subcategory", ""),
            "patients": r.get("patients", 0),
        })

    if not entries:
        return True, {"display": "none"}, {"display": "block"}, "No valid entries to classify."

    with _diag_ai_lock:
        _diag_ai_progress.update(done=0, total=len(entries), running=True, message="Starting AI classification...")
        _diag_ai_results.clear()

    def _bg():
        from utils.diagnosis_inference import infer_diagnosis_categories

        # Process in chunks
        chunk_size = 30
        all_results = {}
        for i in range(0, len(entries), chunk_size):
            chunk = entries[i : i + chunk_size]
            chunk_results = infer_diagnosis_categories(chunk)
            all_results.update(chunk_results)
            with _diag_ai_lock:
                _diag_ai_progress["done"] = min(i + chunk_size, len(entries))
                _diag_ai_progress["message"] = f"Classifying... {_diag_ai_progress['done']}/{len(entries)}"

        # Build review rows
        review = []
        for e in entries:
            key = e["key"]
            ai = all_results.get(key)
            review.append({
                "key": key,
                "icd_code": e["icd_code"],
                "description": e["description"],
                "current_category": e["current_category"],
                "current_subcategory": e["current_subcategory"],
                "ai_category": ai["category"] if ai else "",
                "ai_subcategory": ai["subcategory"] if ai else "",
                "category": ai["category"] if ai else "",  # for subcategory dropdown
                "patients": e["patients"],
                "accept": bool(ai),
            })

        with _diag_ai_lock:
            _diag_ai_results.clear()
            _diag_ai_results.extend(review)
            _diag_ai_progress["running"] = False
            _diag_ai_progress["message"] = f"Done. {sum(1 for r in review if r['ai_category']):,} classified of {len(review)}."

    t = threading.Thread(target=_bg, daemon=True)
    t.start()

    return (
        False,
        {"display": "block"},
        {"display": "block"},
        f"Classifying {len(entries)} entries...",
    )


@callback(
    Output(f"{PAGE_ID}-rpm-diag-ai-poll", "disabled", allow_duplicate=True),
    Output(f"{PAGE_ID}-rpm-diag-ai-progress", "value"),
    Output(f"{PAGE_ID}-rpm-diag-ai-progress", "style", allow_duplicate=True),
    Output(f"{PAGE_ID}-rpm-diag-ai-progress-text", "children", allow_duplicate=True),
    Output(f"{PAGE_ID}-rpm-diag-ai-progress-text", "style", allow_duplicate=True),
    Output(f"{PAGE_ID}-rpm-diag-ai-review", "opened"),
    Output(f"{PAGE_ID}-rpm-diag-ai-review-grid", "rowData"),
    Input(f"{PAGE_ID}-rpm-diag-ai-poll", "n_intervals"),
    prevent_initial_call=True,
)
def _rpm_diag_ai_poll(n):
    """Poll background AI classification progress."""
    no = dash.no_update
    with _diag_ai_lock:
        done = _diag_ai_progress["done"]
        total = _diag_ai_progress["total"]
        running = _diag_ai_progress["running"]
        msg = _diag_ai_progress["message"]
        review = list(_diag_ai_results) if not running and _diag_ai_results else None

    pct = int(done * 100 / total) if total > 0 else 0

    if running:
        return False, pct, {"display": "block"}, msg, {"display": "block"}, no, no

    if review:
        return (
            True, 100, {"display": "none"}, msg, {"display": "block"},
            True, review,
        )
    return True, 100, {"display": "none"}, msg, {"display": "block"}, no, no


# --- AI Review: Accept All ---
@callback(
    Output(f"{PAGE_ID}-rpm-diag-ai-review-grid", "rowData", allow_duplicate=True),
    Input(f"{PAGE_ID}-rpm-diag-ai-accept-all", "n_clicks"),
    State(f"{PAGE_ID}-rpm-diag-ai-review-grid", "rowData"),
    prevent_initial_call=True,
)
def _rpm_diag_ai_accept_all(n, data):
    if not n or not data:
        return dash.no_update
    for r in data:
        if r.get("ai_category"):
            r["accept"] = True
    return data


# --- AI Review: Reject All (dismiss panel) ---
@callback(
    Output(f"{PAGE_ID}-rpm-diag-ai-review", "opened", allow_duplicate=True),
    Output(f"{PAGE_ID}-rpm-diag-ai-progress-text", "children", allow_duplicate=True),
    Input(f"{PAGE_ID}-rpm-diag-ai-reject-all", "n_clicks"),
    prevent_initial_call=True,
)
def _rpm_diag_ai_reject_all(n):
    if not n:
        return dash.no_update, dash.no_update
    return False, "Rejected all — no changes applied."


# --- AI Review: Apply Selected ---
@callback(
    Output(f"{PAGE_ID}-rpm-diag-grid", "rowData", allow_duplicate=True),
    Output(f"{PAGE_ID}-rpm-diag-grid-full-store", "data", allow_duplicate=True),
    Output(f"{PAGE_ID}-rpm-diag-stats", "children", allow_duplicate=True),
    Output(f"{PAGE_ID}-rpm-diag-ai-review", "opened", allow_duplicate=True),
    Output(f"{PAGE_ID}-rpm-diag-ai-progress-text", "children", allow_duplicate=True),
    Input(f"{PAGE_ID}-rpm-diag-ai-apply", "n_clicks"),
    State(f"{PAGE_ID}-rpm-diag-ai-review-grid", "rowData"),
    State(f"{PAGE_ID}-rpm-diag-grid-full-store", "data"),
    State(f"{PAGE_ID}-rpm-diag-unreviewed-toggle", "checked"),
    prevent_initial_call=True,
)
def _rpm_diag_ai_apply(n, review_data, full_data, unreviewed_only):
    if not n or not review_data or not full_data:
        return (dash.no_update,) * 5
    from data.reviews_db import upsert_diagnosis_override

    accepted = [r for r in review_data if r.get("accept") and r.get("ai_category")]

    if not accepted:
        return (dash.no_update, dash.no_update, dash.no_update,
                False, "No rows accepted — no changes applied.")

    # Save to DB
    for r in accepted:
        key = r.get("icd_code") or r.get("description", "")
        if key:
            upsert_diagnosis_override(
                key, category=r["ai_category"],
                subcategory=r.get("ai_subcategory", ""),
                source="claude_ai",
            )

    # Update the grid's full store
    ai_map = {}
    for r in accepted:
        key = r.get("icd_code") or r.get("description", "")
        if key:
            ai_map[key] = (r["ai_category"], r.get("ai_subcategory", ""))

    for r in full_data:
        rk = r.get("icd_code") or r.get("description", "")
        if rk in ai_map:
            r["category"] = ai_map[rk][0]
            r["subcategory"] = ai_map[rk][1]
            r["source"] = "claude_ai"

    total = len(full_data)
    categorized = sum(1 for r in full_data if r.get("category"))
    reviewed_n = sum(1 for r in full_data if r.get("reviewed"))
    stats = (
        f"{total:,} entries  |  {categorized:,} categorized  |  "
        f"{reviewed_n:,} reviewed  |  {total - reviewed_n:,} unreviewed"
    )
    visible = [r for r in full_data if not r.get("reviewed")] if unreviewed_only else full_data
    msg = f"Applied {len(accepted)} AI classifications."
    return visible, full_data, stats, False, msg


# Project-to-year-end toggle visibility (shown only for current_year preset)
clientside_callback(
    """function(preset) {
        return preset === "current_year" ? {} : {"display": "none"};
    }""",
    Output(f"{PAGE_ID}-cumulative" + "-project-wrap", "style"),
    Input(f"{PAGE_ID}-filter-date-preset", "value"),
)


# Wire AI settings persistence (referrals prefix "ref")
register_ai_settings_callbacks("ref")

