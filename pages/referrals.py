"""Referrals page — conversion funnel, lead times, referring sources, and trends."""

import re
from pathlib import Path
import dash
import dash_mantine_components as dmc
import dash_ag_grid as dag
from dash import callback, Input, Output, State, dcc, html, clientside_callback, ClientsideFunction
from dash_iconify import DashIconify
import plotly.graph_objects as go
import pandas as pd
import numpy as np
from datetime import timedelta

from config.settings import (
    DEPARTMENTS, DEPARTMENT_COLORS, CHART_COLORWAY, PRIMARY,
    DEFAULT_LAYOUT, FONT_FAMILY, SEMANTIC_COLORS, NEUTRAL, CHART_PAPER_HEIGHT,
    DEFAULT_COLUMN_DEFS, DEFAULT_GRID_OPTIONS, DEFAULT_GRID_STYLE, DEFAULT_GRID_CLASS, ABMS_SPECIALTIES,
)
from components.filter_bar import department_chips
from components.kpi_card import kpi_card, create_sparkline
from components.chart_card import chart_card, register_chart_callbacks
from components.outlier_panel import outlier_panel, register_outlier_callbacks
from utils.charts import apply_default_layout, empty_figure, dept_color, color_for_index
from utils.diagnosis_categories import (
    build_code_to_category, CATEGORIES as BODY_SYSTEMS,
    SUBCATEGORIES as DIAG_SUBCATEGORIES, ALL_SUBCATEGORIES,
    get_all_subcategory_entries,
)
from utils.date_slider import (
    month_idx, idx_to_date, MAX_IDX, DEFAULT_SLIDER, SLIDER_MARKS,
    preset_to_slider_val,
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
# Priority cascade:
#   1. ICD-10/ICD-9 code extracted from "Diagnoses" → diagnosis_categories lookup
#   2. Free-text regex on "Rfl Prim Dx"
#   3. Free-text regex on "Diagnoses"
#
# Free-text patterns use the same category names as diagnosis_categories.py
# so that ICD-resolved and text-resolved rows appear in the same buckets.

_ICD10_RE = re.compile(r"([A-Z]\d[0-9A-Z](?:\.[0-9A-Z]+)?)\s*\(ICD-10")
_ICD9_RE = re.compile(r"(\d{3}(?:\.\d+)?)\s*\(ICD-9")

# Free-text patterns → category names matching diagnosis_categories.py
# Order matters — first match wins, so specific patterns precede broad ones.
# Sarcomas early so "osteoblastoma" doesn't fall through to Mets via "bone".
_DIAG_TEXT_PATTERNS = [
    # --- Sarcomas (before Mets — osteoblastoma/fibromatosis are NOT mets) ---
    ("Sarcomas",               re.compile(
        r"sarcoma|soft.?tissue|lipomatous.?tumor|spindle.?cell"
        r"|giant.?cell.?tumor|osteoblas|fibrous.?tumor|fibromatosis", re.I)),
    # --- Mets / palliative (before organ-specific: "spine mets" ≠ CNS) ---
    ("Metastases & Palliative", re.compile(
        r"bone\s*met|brain\s*met|secondary.*bone|secondary.*brain|C79\.[35]"
        r"|metasta|\bmet\b|\bmets\b|spine\s*met|cord.?compress|spinal.?cord"
        r"|sternal\s*met|rib\s*met|hip\s*met|sacr\w*\s*met|pelvic\s*met"
        r"|lytic.?lesion|lystic|bone.?lesion|pathologic\w*\s*fracture"
        r"|\bbone\b|\bspine\b|lspine|\bfemur\b|femurs|\bhumerus\b|\brib\b|\bpelvi"
        r"|pevic|skull.?lesion|sternum|SVC.?syndrom|\bPCI\b"
        r"|T\d+\b|L\s*\d+\b|C\d+\s*spin|sacrum|clavicle|lumbar"
        r"|\bhip\b|shoulder|scapula|chest.?wall|chest\b|axilla"
        r"|flank|leg.?mass|thigh.?mass|arm\b|elbow|forearm|T-\d+"
        r"|calf\b|knee\b|dorsal.?hand|finger|ankle|wrist"
        r"|face.?mass|back.?pain", re.I)),
    # --- Specific organ sites ---
    ("GU – Prostate",          re.compile(r"prostat", re.I)),
    ("Breast",                 re.compile(
        r"breast|breat|bresst|breaast|mammary|left brest", re.I)),
    ("Thoracic",               re.compile(
        r"\blung\b|pulmon|bronch|\bSCLC\b|\bNSCL\b|mesothelioma"
        r"|mediastin|thymom|thymus|thymic|paratracheal", re.I)),
    ("Central Nervous System", re.compile(
        r"\bbrain\b|\bGBM\b|gliob|glioma|oligodendro|astrocyt|mening"
        r"|ependymoma|pituitary|schwannoma|acoustic.?neuroma|cerebell"
        r"|cranial|\borbit\b|orbital|choroid|chorodial|vestibul\w+\s*schwann"
        r"|frontal.?lobe.?lesion|parietal.?lobe|\bcns\b|optic.?nerve"
        r"|cauda.?equina|brachial.?plex|neuropath", re.I)),
    ("Head and Neck",          re.compile(
        r"tongue|tounge|tonsil|tonge|laryn|pharyn|pharny|hypo.?pharyn|hypoharyn"
        r"|oral|oropharyn|orophayn|nasopharyn|salivary|thyroid|palat"
        r"|sinus|nasal|\bBOT\b|base of tongue|parotid|vocal.?cord"
        r"|epiglott|glotti|mandib|submandib|buccal|retromolar"
        r"|adenoid.?cystic|lingual|\bH&N\b|\bSCCA\b|mouth|throat"
        r"|arytenoid|supraclav|neck.?mass|head.?neck|\bneck\b"
        r"|midface|zygoma|auditory|adenoid\b|otalgia|perianal", re.I)),
    ("Gastrointestinal",       re.compile(
        r"pancrea|hepato|esophag|esphag|esopah|esopheal|rectal|rectum"
        r"|recral|retum|rectosigmoid|colon|gastri|gastic|bile|biliary"
        r"|cholang|\banal\b|\banus\b|stomach|small.?bowel|pyloric|cecum"
        r"|splenic.?flexure|\bGI\b|\bliver\b|peritoneum|peritoneal"
        r"|stomal.?tumor", re.I)),
    ("Gynecologic",            re.compile(
        r"cervi|cerivx|uter|endomet|edometr|endrometr|ovar|vulv|vagin|vlava", re.I)),
    ("Hematologic",            re.compile(
        r"lymph|lymhoma|hodgkin|leukemi|\bAML\b|myelom|meyloma|myelona"
        r"|myelofibro|polycythem|plasmacytom|plasma.?cyt|plasma.?cell"
        r"|mycosis.?fungoid|mycosis.?fungod|spleen|spleno|\bSPLEN\b"
        r"|pancytopen|\bMGUS\b|amyloid", re.I)),
    ("Skin",                   re.compile(
        r"melan|squamous.{0,10}skin|basal.?cell|basil.?cell|\bBCC\b|\bSCC\b"
        r"|\bskin\b|cutane|merkel|\bMCC\b|keloid|scalp|ear\b|forehead"
        r"|cheek|temple|lip\b|nose\b|eyelid|sebaceous.?carcinom"
        r"|\bAFX\b|hidradenitis|squamous.?cell.?carcinom", re.I)),
    ("GU – Non-Prostate",      re.compile(
        r"bladder|bkadder|renal|kidney|ureter|ureth|urothel"
        r"|transitional.?cell|testic|testis|penile|penis|adrenocort|adrenal"
        r"|seminoma", re.I)),
    ("Benign Diseases",        re.compile(
        r"benign|keloid|dupuytren|\bAVM\b|arteriovenous|hemangioma"
        r"|heterotopic.?oss|het\s*erotrophic|hypertrophic.?scar"
        r"|osteopor|osteopeni|neurofibroma|Graves|psoriasis"
        r"|\bHHT\b|Osler.?Weber|trigeminal.?neuralgia|neuralgia"
        r"|arthritis|bursitis", re.I)),
]

# Build ICD→category lookup once at import time
from data.loader import load_diagnosis as _load_diag, load_clinic_visits as _load_cv
from utils.diagnosis_categories import primary_category as _primary_category
_DIAG_C2C: dict[str, str] = build_code_to_category(_load_diag())

# Build MRN→category map from clinic visit DiagnosisCodes (tier 3 fallback)
def _build_cv_mrn_map() -> dict[int, str]:
    cv = _load_cv()
    if cv.empty or "DiagnosisCodes" not in cv.columns:
        return {}
    cv_diag = cv[cv["DiagnosisCodes"].notna()][["PatientId", "DiagnosisCodes"]]
    cv_diag = cv_diag.drop_duplicates("PatientId")
    cv_diag["_cat"] = cv_diag["DiagnosisCodes"].apply(
        lambda v: _primary_category(v, _DIAG_C2C)
    )
    return cv_diag[cv_diag["_cat"] != "Unknown"].set_index("PatientId")["_cat"].to_dict()

_CV_MRN_MAP: dict[int, str] = _build_cv_mrn_map()


def _extract_icd_code(text):
    """Extract the first ICD-10 (preferred) or ICD-9 code from Diagnoses text."""
    if pd.isna(text):
        return None
    s = str(text)
    m = _ICD10_RE.search(s)
    if m:
        return m.group(1)
    m = _ICD9_RE.search(s)
    if m:
        return m.group(1)
    return None


def _categorise_text(text):
    """Map free-text diagnosis to a category via regex."""
    if pd.isna(text) or not str(text).strip():
        return None
    s = str(text)
    for name, pat in _DIAG_TEXT_PATTERNS:
        if pat.search(s):
            return name
    return None


def _categorise_diagnosis(diagnoses_text, prim_dx_text=None, mrn=None):
    """Cascade: ICD code → Rfl Prim Dx text → Diagnoses text → CV dx → 'Other'."""
    # 1. Try ICD code from Diagnoses column
    code = _extract_icd_code(diagnoses_text)
    if code:
        cat = _DIAG_C2C.get(code)
        if cat:
            return cat
    # 2. Try free-text on Rfl Prim Dx
    if prim_dx_text is not None:
        cat = _categorise_text(prim_dx_text)
        if cat:
            return cat
    # 3. Try free-text on Diagnoses column
    cat = _categorise_text(diagnoses_text)
    if cat:
        return cat
    # 4. Try clinic visit diagnosis for this patient
    if mrn is not None and pd.notna(mrn):
        cat = _CV_MRN_MAP.get(int(mrn))
        if cat:
            return cat
    return "Other"


# ---------------------------------------------------------------------------
# Department mapping from Referred-by Department
# ---------------------------------------------------------------------------

_DEPT_MAP_PATTERNS = [
    ("Lacey",     re.compile(r"LACEY", re.I)),
    ("Centralia", re.compile(r"CENTRALIA", re.I)),
    ("Aberdeen",  re.compile(r"ABERDEEN", re.I)),
]


def _map_to_our_dept(ref_dept):
    """Map 'Referred by Department' to our three departments (or None)."""
    if pd.isna(ref_dept):
        return None
    s = str(ref_dept)
    for dept, pat in _DEPT_MAP_PATTERNS:
        if pat.search(s):
            return dept
    return None


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
                    dmc.Select(
                        id=f"{PAGE_ID}-filter-specialty",
                        data=[],  # populated by callback
                        placeholder="All Specialties",
                        clearable=True,
                        searchable=True,
                        size="sm",
                        w=220,
                        maxDropdownHeight=800,
                        comboboxProps={"zIndex": 500},
                    ),
                    dmc.Select(
                        id=f"{PAGE_ID}-filter-diagnosis",
                        data=[{"value": bs, "label": bs} for bs in BODY_SYSTEMS],
                        placeholder="All Diagnoses",
                        clearable=True,
                        size="sm",
                        w=220,
                        maxDropdownHeight=800,
                        comboboxProps={"zIndex": 500},
                    ),
                    outlier_panel(PAGE_ID, transitions=[
                        ("Created \u2192 Scheduled", _CAP_CREATED_TO_SCHEDULED),
                        ("Scheduled \u2192 Visit", _CAP_SCHEDULED_TO_VISIT),
                    ]),
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
                            {"value": "ytd", "label": "Year to Date"},
                            {"value": "last_year", "label": "Last Year"},
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
                _build_filter_bar(),
            ],
        ),

        # KPI row — 6 cards, evenly spaced
        dmc.Group(
            id=f"{PAGE_ID}-kpi-row",
            gap="sm",
            grow=True,
            wrap="nowrap",
            style={"overflow": "hidden"},
        ),

        # Flow Gantt — referral pathway
        dmc.Paper(
            children=[
                dmc.Text("Referral Pathway", size="sm", fw=500, c=NEUTRAL["text_secondary"], mb="sm"),
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
            p="md", radius="md", shadow="xs", withBorder=True,
        ),

        # Flow distribution + trend (driven by Gantt band selection)
        dmc.Grid(
            gutter="md",
            children=[
                dmc.GridCol(
                    span={"base": 12, "md": 6},
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
                                    dmc.SegmentedControl(
                                        id=f"{PAGE_ID}-dist-type",
                                        data=[
                                            {"value": "density", "label": "Density"},
                                            {"value": "histogram", "label": "Histogram"},
                                        ],
                                        value="density", size="xs",
                                    ),
                                ],
                            ),
                            dcc.Graph(
                                id=f"{PAGE_ID}-flow-dist",
                                config={"displayModeBar": False, "responsive": True},
                                style={"height": "340px"},
                            ),
                        ],
                        p="sm", radius="md", shadow="xs", withBorder=True,
                    ),
                ),
                dmc.GridCol(
                    span={"base": 12, "md": 6},
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
                                    dmc.SegmentedControl(
                                        id=f"{PAGE_ID}-trend-agg",
                                        data=[
                                            {"value": "W", "label": "Weekly"},
                                            {"value": "M", "label": "Monthly"},
                                        ],
                                        value="M", size="xs",
                                    ),
                                ],
                            ),
                            dcc.Graph(
                                id=f"{PAGE_ID}-flow-trend",
                                config={"displayModeBar": False, "responsive": True},
                                style={"height": "340px"},
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
                                    {"value": "specialty", "label": "Specialty"},
                                    {"value": "diagnosis", "label": "Diagnosis"},
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
                                             c=NEUTRAL["text_secondary"]),
                                    dmc.SegmentedControl(
                                        id=f"{PAGE_ID}-dim-compare-period",
                                        data=[
                                            {"value": "calendar", "label": "Calendar"},
                                            {"value": "rolling", "label": "Rolling"},
                                        ],
                                        value="calendar",
                                        size="xs",
                                    ),
                                ],
                            ),
                            dmc.Box(
                                pos="relative",
                                style={"flex": "1", "minHeight": 0},
                                children=[
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

        # Row: Top Referring Providers + Top Referring Departments
        dmc.Grid(
            gutter="md",
            children=[
                dmc.GridCol(
                    span={"base": 12, "md": 6},
                    children=chart_card(
                        f"{PAGE_ID}-chart-providers", "Top Referring Providers",
                        show_settings=False, show_smooth=False,
                    ),
                ),
                dmc.GridCol(
                    span={"base": 12, "md": 6},
                    children=chart_card(
                        f"{PAGE_ID}-chart-departments", "Top Referring Departments",
                        show_settings=False, show_smooth=False,
                    ),
                ),
            ],
        ),

        # Row: Monthly Volume Trend + Conversion by Dept
        dmc.Grid(
            gutter="md",
            children=[
                dmc.GridCol(
                    span={"base": 12, "md": 6},
                    children=chart_card(
                        f"{PAGE_ID}-chart-trend", "Monthly Referral Volume & Conversion",
                        show_settings=False, show_smooth=False,
                    ),
                ),
                dmc.GridCol(
                    span={"base": 12, "md": 6},
                    children=chart_card(
                        f"{PAGE_ID}-chart-conv-dept", "Conversion Rate by Referring Dept",
                        show_settings=False, show_smooth=False,
                    ),
                ),
            ],
        ),

        # Row: New Referrer Trend + Diagnosis Ridge Plot
        dmc.Grid(
            gutter="md",
            children=[
                dmc.GridCol(
                    span={"base": 12, "md": 6},
                    children=chart_card(
                        f"{PAGE_ID}-chart-new-referrers", "New Referrer Trend",
                        show_settings=False, show_smooth=False,
                    ),
                ),
                dmc.GridCol(
                    span={"base": 12, "md": 6},
                    children=chart_card(
                        f"{PAGE_ID}-chart-ridge", "Referral Volume by Diagnosis (Ridge)",
                        show_settings=False, show_smooth=False,
                    ),
                ),
            ],
        ),

        # Detail table
        dmc.Box(id=f"{PAGE_ID}-table-container"),

        # ---------------------------------------------------------------
        # Referring Physician Manager Modal
        # ---------------------------------------------------------------
        dmc.Modal(
            id=f"{PAGE_ID}-rpm-modal",
            opened=False,
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
                                        dmc.Button(
                                            "Look Up Specialties (NPI)",
                                            id=f"{PAGE_ID}-rpm-npi-btn",
                                            leftSection=DashIconify(icon="tabler:search", width=14),
                                            variant="light", color="blue", size="xs",
                                        ),
                                        dmc.Button(
                                            "Research Institutions (AI)",
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
                                            defaultColDef={"sortable": True, "resizable": True},
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
                                         "cellRenderer": "NameSearch",
                                         "filter": "agTextColumnFilter", "floatingFilter": True},
                                        {"field": "department", "headerName": "Department", "flex": 1.4,
                                         "filter": "agTextColumnFilter", "floatingFilter": True},
                                        {"field": "full_address", "headerName": "Address", "flex": 1.6,
                                         "editable": True,
                                         "cellEditor": "agLargeTextCellEditor",
                                         "cellEditorPopup": True,
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
                                        {"field": "first_referral", "headerName": "First", "flex": 0.4,
                                         "filter": "agTextColumnFilter"},
                                        {"field": "last_referral", "headerName": "Last", "flex": 0.4,
                                         "filter": "agTextColumnFilter"},
                                        {"field": "reviewed", "headerName": "Reviewed", "flex": 0.4,
                                         "cellDataType": "boolean",
                                         "editable": True,
                                         "cellStyle": {"textAlign": "center"}},
                                    ],
                                    defaultColDef={"sortable": True, "resizable": True},
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
                                            columnDefs=[
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
                                            ],
                                            defaultColDef={"sortable": True, "resizable": True,
                                                           "filter": True, "floatingFilter": True},
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
                                    defaultColDef={"sortable": True, "resizable": True},
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
                                        {"field": "patients", "headerName": "Patients", "flex": 0.4,
                                         "cellRenderer": "DiagCountLink",
                                         "cellRendererParams": {"storeId": f"{PAGE_ID}-rpm-diag-detail-store"},
                                         "type": "numericColumn", "sort": "desc",
                                         "filter": "agNumberColumnFilter"},
                                        {"field": "source", "headerName": "Source", "flex": 0.4,
                                         "filter": "agTextColumnFilter", "floatingFilter": True,
                                         "cellStyle": {"fontStyle": "italic", "color": NEUTRAL["text_muted"]}},
                                        {"field": "reviewed", "headerName": "Reviewed", "flex": 0.3,
                                         "cellDataType": "boolean", "editable": True,
                                         "cellStyle": {"textAlign": "center"}},
                                    ],
                                    defaultColDef={"sortable": True, "resizable": True},
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
                                            columnDefs=[
                                                {"field": "Created", "headerName": "Date", "flex": 0.6, "sort": "desc"},
                                                {"field": "MRN", "headerName": "MRN", "flex": 0.5},
                                                {"field": "Patient Name", "headerName": "Patient", "flex": 1},
                                                {"field": "Rfl Prim Dx", "headerName": "Primary Dx", "flex": 1.2},
                                                {"field": "Diagnoses", "headerName": "Diagnoses", "flex": 1.5},
                                                {"field": "Status", "headerName": "Status", "flex": 0.6},
                                            ],
                                            defaultColDef={"sortable": True, "resizable": True,
                                                           "filter": True, "floatingFilter": True},
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
                    defaultColDef={"sortable": True, "resizable": True},
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
        dcc.Store(id=f"{PAGE_ID}-trend-smooth", data=0),
        dcc.Store(id=f"{PAGE_ID}-trend-settings-type", data="line"),
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

        dcc.Interval(id=f"{PAGE_ID}-interval", interval=300_000, n_intervals=0),
    ],
)


# ---------------------------------------------------------------------------
# Date Slider Sync Callbacks
# ---------------------------------------------------------------------------

@callback(
    Output(f"{PAGE_ID}-date-slider", "value"),
    Input(f"{PAGE_ID}-filter-date-preset", "value"),
    prevent_initial_call=True,
)
def _preset_to_slider(preset):
    if preset == "custom":
        return dash.no_update
    return preset_to_slider_val(preset, MAX_IDX)


clientside_callback(
    ClientsideFunction(namespace="referralsDateSlider", function_name="syncSlider"),
    Output(f"{PAGE_ID}-filter-daterange", "start_date"),
    Output(f"{PAGE_ID}-filter-daterange", "end_date"),
    Output(f"{PAGE_ID}-date-range-label", "children"),
    Input(f"{PAGE_ID}-date-slider", "value"),
    State(f"{PAGE_ID}-filter-daterange", "start_date"),
    State(f"{PAGE_ID}-filter-daterange", "end_date"),
)

# Flow Gantt renderer — reuses flow_gantt.js via referralFlowGantt wrapper
clientside_callback(
    ClientsideFunction(namespace="referralFlowGantt", function_name="render"),
    Output(f"{PAGE_ID}-flow-gantt-trigger", "data"),
    Input(f"{PAGE_ID}-store-flow-gantt", "data"),
)

# Distribution chart — reuses flowGantt.renderFlowDistribution
clientside_callback(
    ClientsideFunction(namespace="flowGantt", function_name="renderFlowDistribution"),
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
)

# Trend chart — reuses flowGantt.renderFlowTrend
clientside_callback(
    ClientsideFunction(namespace="flowGantt", function_name="renderFlowTrend"),
    Output(f"{PAGE_ID}-flow-trend", "figure"),
    Output(f"{PAGE_ID}-trend-title", "children"),
    Output(f"{PAGE_ID}-trend-maturity", "style"),
    Input(f"{PAGE_ID}-store-flow-details", "data"),
    Input(f"{PAGE_ID}-store-selected-flow", "data"),
    Input(f"{PAGE_ID}-store-trend-legacy", "data"),
    Input(f"{PAGE_ID}-trend-smooth", "data"),
    Input(f"{PAGE_ID}-trend-settings-type", "data"),
    Input(f"{PAGE_ID}-trend-agg", "value"),
    Input(f"{PAGE_ID}-trend-km-switch", "data"),
    Input(f"{PAGE_ID}-store-flow-details-b", "data"),
    Input(f"{PAGE_ID}-store-trend-legacy-b", "data"),
    Input(f"{PAGE_ID}-compare-mode", "data"),
    Input(f"{PAGE_ID}-agg-toggle", "data"),
    Input(f"{PAGE_ID}-agg-toggle-b", "data"),
)


# Register outlier panel callbacks
register_outlier_callbacks(
    PAGE_ID, n_transitions=2,
    defaults=[_CAP_CREATED_TO_SCHEDULED, _CAP_SCHEDULED_TO_VISIT],
)

# Register gear-icon toggle + export callbacks for dimension trend chart
register_chart_callbacks([f"{PAGE_ID}-chart-dim-trend"])

# Clientside callback — renders dimension trend ridgeline from store + settings
clientside_callback(
    ClientsideFunction(namespace="referralRidge", function_name="renderTrend"),
    Output(f"{PAGE_ID}-chart-dim-trend", "figure"),
    Input(f"{PAGE_ID}-chart-dim-trend-store", "data"),
    Input(f"{PAGE_ID}-chart-dim-trend-settings-smooth", "value"),
    Input(f"{PAGE_ID}-chart-dim-trend-settings-type", "value"),
    Input(f"{PAGE_ID}-dim-trend-agg", "value"),
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


def _build_top_providers(df, n=20):
    """Horizontal bar chart of top N referring providers."""
    if df.empty or "Referred by Provider" not in df.columns:
        return empty_figure("No referral data")

    counts = df["Referred by Provider"].dropna().value_counts().head(n)
    counts = counts.sort_values(ascending=True)

    fig = go.Figure()
    fig.add_trace(go.Bar(
        y=counts.index,
        x=counts.values,
        orientation="h",
        marker_color=CHART_COLORWAY[0],
        hovertemplate="%{y}<br>%{x:,} referrals<extra></extra>",
        showlegend=False,
    ))

    fig = apply_default_layout(fig,
        height=380,
        margin=dict(l=200, r=16, t=8, b=32),
        yaxis=dict(showgrid=False, tickfont=dict(size=10)),
        xaxis=dict(showgrid=True, gridcolor="#F0F0F0", title="Referrals"),
    )
    return fig


def _build_top_departments(df, n=15):
    """Horizontal bar chart of top N referring departments."""
    if df.empty or "Referred by Department" not in df.columns:
        return empty_figure("No department data")

    counts = df["Referred by Department"].dropna().value_counts().head(n)
    counts = counts.sort_values(ascending=True)

    # Truncate long names
    labels = [n if len(n) <= 40 else n[:37] + "..." for n in counts.index]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        y=labels,
        x=counts.values,
        orientation="h",
        marker_color=CHART_COLORWAY[1],
        hovertemplate="%{y}<br>%{x:,} referrals<extra></extra>",
        showlegend=False,
        customdata=counts.index.tolist(),
    ))

    fig = apply_default_layout(fig,
        height=380,
        margin=dict(l=260, r=16, t=8, b=32),
        yaxis=dict(showgrid=False, tickfont=dict(size=10)),
        xaxis=dict(showgrid=True, gridcolor="#F0F0F0", title="Referrals"),
    )
    return fig


def _build_volume_trend(df):
    """Monthly referral volume with conversion rate on secondary axis."""
    if df.empty or "Created" not in df.columns:
        return empty_figure("No referral data")

    df = df.copy()
    df["_month"] = df["Created"].dt.to_period("M").dt.to_timestamp()

    monthly = df.groupby("_month").agg(
        total=("Referral ID", "count"),
        converted=("Appt Attached", lambda x: (x == "Yes").sum()),
    ).reset_index().sort_values("_month")

    monthly["conv_rate"] = (monthly["converted"] / monthly["total"] * 100).round(1)

    # Drop the last month if it's partial (< 15 days of data)
    if len(monthly) > 1:
        last_month_data = df[df["_month"] == monthly["_month"].iloc[-1]]
        if len(last_month_data) < 15:
            monthly = monthly.iloc[:-1]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=monthly["_month"], y=monthly["total"],
        name="Total Referrals",
        marker_color=CHART_COLORWAY[0],
        opacity=0.6,
        hovertemplate="%{x|%b %Y}: %{y:,} referrals<extra></extra>",
        yaxis="y",
    ))
    fig.add_trace(go.Scatter(
        x=monthly["_month"], y=monthly["conv_rate"],
        name="Conversion %",
        mode="lines+markers",
        line=dict(color=SEMANTIC_COLORS["success"], width=2),
        marker=dict(size=4),
        hovertemplate="%{x|%b %Y}: %{y:.1f}%<extra></extra>",
        yaxis="y2",
    ))

    fig = apply_default_layout(fig,
        height=380,
        margin=dict(l=48, r=48, t=8, b=48),
        xaxis=dict(showgrid=False, dtick="M3", tickformat="%b '%y"),
        yaxis=dict(showgrid=True, gridcolor="#F0F0F0", title="Referrals"),
        yaxis2=dict(
            title="Conversion %", overlaying="y", side="right",
            showgrid=False, range=[0, 105],
            ticksuffix="%",
        ),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        barmode="overlay",
    )
    return fig


def _build_ridge_plot(df):
    """Ridge-line plot of monthly referral volume by diagnosis category."""
    if df.empty or "Created" not in df.columns:
        return empty_figure("No referral data")

    df = df.copy()
    df["_diag_cat"] = df.apply(
        lambda r: _categorise_diagnosis(
            r.get("Diagnoses"), r.get("Rfl Prim Dx"), r.get("MRN")
        ),
        axis=1,
    )
    df["_month"] = df["Created"].dt.to_period("M").dt.to_timestamp()

    # Get top categories by volume (exclude Other)
    cat_counts = df["_diag_cat"].value_counts()
    categories = [c for c in cat_counts.index if c != "Other"][:8]
    categories = list(reversed(categories))  # Bottom to top

    if not categories:
        return empty_figure("No diagnosis data")

    # Monthly counts per category
    pivot = (
        df[df["_diag_cat"].isin(categories)]
        .groupby(["_month", "_diag_cat"]).size()
        .unstack(fill_value=0)
    )

    fig = go.Figure()
    spacing = 1.0  # vertical spacing between ridges

    for i, cat in enumerate(categories):
        if cat not in pivot.columns:
            continue
        y_vals = pivot[cat].values.astype(float)
        x_vals = pivot.index

        # Normalise to [0, spacing*0.8] for visual consistency
        y_max = y_vals.max() if y_vals.max() > 0 else 1
        y_norm = y_vals / y_max * spacing * 0.7
        y_offset = i * spacing

        color = color_for_index(i)

        # Convert hex to rgba for fill
        def _hex_to_rgba(hex_c, alpha=0.3):
            r = int(hex_c[1:3], 16)
            g = int(hex_c[3:5], 16)
            b = int(hex_c[5:7], 16)
            return f"rgba({r},{g},{b},{alpha})"

        fill_color = _hex_to_rgba(color, 0.3) if color.startswith("#") else color

        # Fill area
        fig.add_trace(go.Scatter(
            x=x_vals, y=y_norm + y_offset,
            mode="lines",
            line=dict(color=color, width=1.5),
            fill="toself",
            fillcolor=fill_color,
            hovertemplate=f"{cat}<br>%{{x|%b %Y}}: %{{customdata:,}}<extra></extra>",
            customdata=y_vals.astype(int),
            showlegend=False,
        ))
        # Baseline
        fig.add_trace(go.Scatter(
            x=x_vals, y=[y_offset] * len(x_vals),
            mode="lines",
            line=dict(color=color, width=0.5),
            hoverinfo="skip",
            showlegend=False,
        ))

    # Y-axis labels for categories
    tickvals = [i * spacing for i in range(len(categories))]
    ticktext = categories

    fig = apply_default_layout(fig,
        height=380,
        margin=dict(l=90, r=16, t=8, b=48),
        xaxis=dict(showgrid=False, dtick="M6", tickformat="%b '%y"),
        yaxis=dict(
            showgrid=False, zeroline=False,
            tickmode="array", tickvals=tickvals, ticktext=ticktext,
            tickfont=dict(size=10),
        ),
    )
    return fig


def _build_conv_by_dept(df, n=15):
    """Horizontal bar chart of conversion rate by referring department."""
    if df.empty or "Referred by Department" not in df.columns:
        return empty_figure("No department data")

    grp = df.groupby("Referred by Department").agg(
        total=("Referral ID", "count"),
        converted=("Appt Attached", lambda x: (x == "Yes").sum()),
    ).reset_index()

    # Only departments with meaningful volume
    grp = grp[grp["total"] >= 10].copy()
    grp["conv_rate"] = (grp["converted"] / grp["total"] * 100).round(1)
    grp = grp.sort_values("conv_rate", ascending=True).tail(n)

    labels = [n if len(n) <= 40 else n[:37] + "..." for n in grp["Referred by Department"]]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        y=labels,
        x=grp["conv_rate"].values,
        orientation="h",
        marker_color=[
            SEMANTIC_COLORS["success"] if v >= 85
            else SEMANTIC_COLORS["warning"] if v >= 70
            else SEMANTIC_COLORS["error"]
            for v in grp["conv_rate"]
        ],
        text=[f"{v:.0f}%" for v in grp["conv_rate"]],
        textposition="auto",
        textfont=dict(size=11),
        hovertemplate="%{y}<br>%{x:.1f}% (%{customdata:,} total)<extra></extra>",
        customdata=grp["total"].values,
        showlegend=False,
    ))

    fig = apply_default_layout(fig,
        height=380,
        margin=dict(l=260, r=16, t=8, b=32),
        yaxis=dict(showgrid=False, tickfont=dict(size=10)),
        xaxis=dict(showgrid=True, gridcolor="#F0F0F0", title="Conversion %",
                   range=[0, 105], ticksuffix="%"),
    )
    return fig


def _build_new_referrer_trend(df):
    """Bar chart of new referring providers by month."""
    if df.empty or "Created" not in df.columns or "Referred by Provider" not in df.columns:
        return empty_figure("No referral data")

    df = df.copy()
    df_with = df[df["Referred by Provider"].notna()]
    if df_with.empty:
        return empty_figure("No provider data")

    first_ref = df_with.groupby("Referred by Provider")["Created"].min().reset_index()
    first_ref.columns = ["Provider", "FirstDate"]
    first_ref["_month"] = first_ref["FirstDate"].dt.to_period("M").dt.to_timestamp()

    monthly = first_ref.groupby("_month").size().reset_index(name="count").sort_values("_month")

    # Drop partial last month
    if len(monthly) > 1 and monthly["count"].iloc[-1] < 3:
        monthly = monthly.iloc[:-1]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=monthly["_month"], y=monthly["count"],
        marker_color=CHART_COLORWAY[4],
        hovertemplate="%{x|%b %Y}: %{y} new referrers<extra></extra>",
        showlegend=False,
    ))

    fig = apply_default_layout(fig,
        height=380,
        margin=dict(l=48, r=16, t=8, b=48),
        xaxis=dict(showgrid=False, dtick="M3", tickformat="%b '%y"),
        yaxis=dict(showgrid=True, gridcolor="#F0F0F0", title="New Referring MDs"),
    )
    return fig


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


def _assign_dimension_group(df, dimension):
    """Add _dim_group column based on the chosen dimension.

    dimension: "provider" | "department" | "specialty" | "diagnosis"
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
    elif dimension == "specialty":
        col = "DeptSpecialty"
        if col not in df.columns:
            df["_dim_group"] = None
        else:
            df["_dim_group"] = df[col]
    elif dimension == "diagnosis":
        df["_dim_group"] = df.apply(
            lambda r: _categorise_diagnosis(
                r.get("Diagnoses"), r.get("Rfl Prim Dx"), r.get("MRN")
            ),
            axis=1,
        )
        # Drop "Other" from diagnosis grouping for cleaner charts
        df.loc[df["_dim_group"] == "Other", "_dim_group"] = None
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


def _build_ref_comparison_bars(dff_curr, dff_prior, start, end, prior_start, prior_end):
    """Horizontal grouped bar chart: current vs prior period per dimension group.

    Same layout as the Diagnosis page comparison chart.
    """
    if dff_curr.empty or "_dim_group" not in dff_curr.columns:
        fig = empty_figure("No data for selected filters")
        fig.update_layout(height=_DIM_RIDGE_HEIGHT)
        return fig

    curr_label = _period_label(start, end)
    prior_label = _period_label(prior_start, prior_end)

    curr_counts = dff_curr["_dim_group"].value_counts()
    prior_counts = (
        dff_prior["_dim_group"].value_counts()
        if dff_prior is not None and not dff_prior.empty and "_dim_group" in dff_prior.columns
        else pd.Series(dtype=int)
    )

    all_groups = sorted(set(curr_counts.index) | set(prior_counts.index))
    # Sort by absolute change (biggest movers first), then keep top N
    # This highlights what shifted between periods, not just what's largest
    all_groups = sorted(
        all_groups,
        key=lambda g: abs(curr_counts.get(g, 0) - prior_counts.get(g, 0)),
        reverse=True,
    )
    all_groups = all_groups[:_DIM_TOP_N]
    # Re-sort ascending by current count for horizontal bar display (largest at top)
    all_groups = sorted(all_groups, key=lambda g: curr_counts.get(g, 0))

    cmap = _dim_color_map(all_groups)
    curr_vals = [int(curr_counts.get(g, 0)) for g in all_groups]
    prior_vals = [int(prior_counts.get(g, 0)) for g in all_groups]

    fig = go.Figure()

    # Prior bars (behind, muted)
    fig.add_trace(go.Bar(
        x=prior_vals, y=all_groups, orientation="h",
        marker_color="rgba(156, 163, 175, 0.45)",
        name=prior_label,
        text=[f"{v:,}" for v in prior_vals],
        textposition="inside", insidetextanchor="end", textangle=0,
        textfont=dict(size=12, color="#6B7280"),
        hovertemplate=[
            f"<b>{g}</b><br>{prior_label}: {v:,}<extra></extra>"
            for g, v in zip(all_groups, prior_vals)
        ],
    ))

    # Current bars (front, colored per group)
    bar_colors = [cmap.get(g, CHART_COLORWAY[0]) for g in all_groups]
    fig.add_trace(go.Bar(
        x=curr_vals, y=all_groups, orientation="h",
        marker_color=bar_colors,
        name=curr_label,
        text=[f"{v:,}" for v in curr_vals],
        textposition="inside", insidetextanchor="end", textangle=0,
        textfont=dict(size=12, color="white"),
        hovertemplate=[
            f"<b>{g}</b><br>{curr_label}: {v:,}<extra></extra>"
            for g, v in zip(all_groups, curr_vals)
        ],
    ))

    # Delta annotations
    max_val = max(max(curr_vals, default=0), max(prior_vals, default=0))
    annot_x = max_val * 1.05 if max_val > 0 else 1

    annotations = []
    for i, g in enumerate(all_groups):
        c, p = curr_vals[i], prior_vals[i]
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
    """AG Grid detail table."""
    if df.empty:
        return dmc.Text("No referral data to display.", c="#9CA3AF", ta="center", py="xl")

    df = df.copy()

    # Format dates
    for col in ["Created", "First Appt"]:
        if col in df.columns:
            df[col] = df[col].dt.strftime("%m/%d/%Y")

    # Select display columns
    display_cols = {
        "Created": "Created",
        "Patient Name": "Patient",
        "Status": "Status",
        "Referred by Provider": "Referring Provider",
        "Referred by Department": "Referring Dept",
        "Diagnoses": "Diagnosis",
        "First Appt": "First Appt",
        "Days to First Appt": "Days to Appt",
        "Appt Attached": "Appt?",
        "CVMatch": "Visit Status",
    }
    available = {k: v for k, v in display_cols.items() if k in df.columns}
    table_df = df[list(available.keys())].rename(columns=available)
    table_df = table_df.sort_values("Created", ascending=False, na_position="last")

    column_defs = []
    widths = {
        "Created": 110, "Patient": 180, "Status": 120,
        "Referring Provider": 200, "Referring Dept": 220,
        "Diagnosis": 250, "First Appt": 110,
        "Days to Appt": 100, "Appt?": 70, "Visit Status": 110,
    }
    for col in table_df.columns:
        col_def = {"field": col, "headerName": col, **DEFAULT_COLUMN_DEFS}
        if col in widths:
            col_def["width"] = widths[col]
        if col == "Diagnosis":
            col_def["flex"] = 1
            col_def["minWidth"] = 200
        column_defs.append(col_def)

    return dmc.Paper(
        children=[
            dmc.Group(
                justify="space-between", mb="sm",
                children=[
                    dmc.Text("Referral Detail", size="sm", fw=500, c="#6B7280"),
                    dmc.Text(f"{len(table_df):,} records", size="xs", c="#9CA3AF"),
                ],
            ),
            dag.AgGrid(
                id=f"{PAGE_ID}-detail-grid",
                rowData=table_df.to_dict("records"),
                columnDefs=column_defs,
                defaultColDef=DEFAULT_COLUMN_DEFS,
                columnSize="autoSize",
                dashGridOptions={**DEFAULT_GRID_OPTIONS, "paginationPageSize": 25},
                style=DEFAULT_GRID_STYLE,
                className=DEFAULT_GRID_CLASS,
            ),
        ],
        p="sm", radius="md", shadow="xs", withBorder=True,
    )


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
        for agg_key in ("W", "M"):
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

    return {
        "transitions": transitions,
        "total": total,
        "aggFunc": "median",
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
    Output(f"{PAGE_ID}-chart-providers", "figure"),
    Output(f"{PAGE_ID}-chart-departments", "figure"),
    Output(f"{PAGE_ID}-chart-trend", "figure"),
    Output(f"{PAGE_ID}-chart-ridge", "figure"),
    Output(f"{PAGE_ID}-chart-conv-dept", "figure"),
    Output(f"{PAGE_ID}-chart-new-referrers", "figure"),
    Output(f"{PAGE_ID}-table-container", "children"),
    Output(f"{PAGE_ID}-chart-dim-trend-store", "data"),
    Output(f"{PAGE_ID}-chart-dim-comparison", "figure"),
    Output(f"{PAGE_ID}-filter-specialty", "data"),
    # Inputs
    Input(f"{PAGE_ID}-interval", "n_intervals"),
    Input(f"{PAGE_ID}-filter-daterange", "start_date"),
    Input(f"{PAGE_ID}-filter-daterange", "end_date"),
    Input(f"{PAGE_ID}-filter-department", "value"),
    Input(f"{PAGE_ID}-filter-specialty", "value"),
    Input(f"{PAGE_ID}-filter-diagnosis", "value"),
    Input(f"{PAGE_ID}-outlier-enabled", "data"),
    Input(f"{PAGE_ID}-outlier-cap-0", "value"),
    Input(f"{PAGE_ID}-outlier-cap-1", "value"),
    Input(f"{PAGE_ID}-dim-toggle", "value"),
    Input(f"{PAGE_ID}-dim-compare-period", "value"),
    running=[
        (Output(f"{PAGE_ID}-chart-dim-trend-loading", "visible"), True, False),
        (Output(f"{PAGE_ID}-chart-providers-loading", "visible"), True, False),
        (Output(f"{PAGE_ID}-chart-departments-loading", "visible"), True, False),
        (Output(f"{PAGE_ID}-chart-trend-loading", "visible"), True, False),
        (Output(f"{PAGE_ID}-chart-ridge-loading", "visible"), True, False),
        (Output(f"{PAGE_ID}-chart-conv-dept-loading", "visible"), True, False),
        (Output(f"{PAGE_ID}-chart-new-referrers-loading", "visible"), True, False),
    ],
)
def update_referrals(_n, start_date, end_date, departments, specialty_filter,
                     diagnosis_filter, outlier_enabled, cap_0, cap_1,
                     dim_toggle, dim_compare_period):
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
    empty_out = (empty_kpis, None, None, empty, empty, empty, empty, empty, empty,
                 dmc.Text("No data", c="#9CA3AF"), None, empty_dim, no_spec)

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
    # Map "Referred by Department" to our departments, filter
    if departments and "Referred by Department" in df.columns:
        our_dept = df["Referred by Department"].apply(_map_to_our_dept)
        df = df[our_dept.isin(departments) | our_dept.isna()]

    # --- Build specialty options (after dept filter, before specialty filter) ---
    spec_options = []
    if "DeptSpecialty" in df.columns:
        spec_options = sorted(df["DeptSpecialty"].dropna().unique().tolist())

    # --- Specialty filter ---
    if specialty_filter and "DeptSpecialty" in df.columns:
        df = df[df["DeptSpecialty"] == specialty_filter]

    # --- Diagnosis filter ---
    if diagnosis_filter:
        df["_diag_filt"] = df.apply(
            lambda r: _categorise_diagnosis(
                r.get("Diagnoses"), r.get("Rfl Prim Dx"), r.get("MRN")
            ),
            axis=1,
        )
        df = df[df["_diag_filt"] == diagnosis_filter]
        df = df.drop(columns=["_diag_filt"])

    if df.empty:
        return empty_out

    # Keep the full filtered set for charts that need all data
    all_data = df.copy()

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
    # True pending = same logic as Gantt flow: not yet completed, waiting
    _today = pd.Timestamp.now().normalize()
    _cv_matched = df["CVMatch"].isin(["Confirmed", "Rescheduled", "Canceled", "No Show"]) if "CVMatch" in df.columns else pd.Series(False, index=df.index)
    _has_future = (df["First Appt"].notna() & (df["First Appt"] >= _today)) if "First Appt" in df.columns else pd.Series(False, index=df.index)
    _appt_att = (df["Appt Attached"] == "Yes") if "Appt Attached" in df.columns else pd.Series(False, index=df.index)
    _scheduled = _cv_matched | _has_future | _appt_att
    _completed = df["CVMatch"].isin(["Confirmed", "Rescheduled"]) if "CVMatch" in df.columns else pd.Series(False, index=df.index)
    _is_terminal = df["Status"].isin(["Closed", "Denied", "Canceled"])
    # Pending off Created (not scheduled, not terminal)
    _p0 = (~_scheduled & ~_is_terminal).sum()
    # Pending off Scheduled (scheduled but not completed, future appt or appt without CV)
    _p1 = (_scheduled & ~_completed & (_has_future | (_appt_att & ~_cv_matched))).sum()
    pending = int(_p0 + _p1)
    unique_mds = df["Referred by Provider"].dropna().nunique()
    denied_canceled = len(df[df["Status"].isin(["Denied", "Canceled"])])
    denial_rate = denied_canceled / total * 100 if total else 0

    # Prior period for trends
    if start_date and end_date:
        ps, pe = _prior_range(pd.Timestamp(start_date), pd.Timestamp(end_date))
        prior_df = load_referrals()
        prior_df = prior_df[(prior_df["Created"] >= ps) & (prior_df["Created"] < pe + timedelta(days=1))]
        if departments and "Referred by Department" in prior_df.columns:
            p_dept = prior_df["Referred by Department"].apply(_map_to_our_dept)
            prior_df = prior_df[p_dept.isin(departments) | p_dept.isna()]
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

    sp_labels = list(sp_total.index)

    # Build KPIs
    t1, d1, p1 = _trend(total, prior_total)
    kpi_total = kpi_card(
        "Total Referrals", f"{total:,}",
        trend_text=f"{t1} vs prior ({p1:,.0f})" if t1 else None,
        trend_direction=d1, accent_color=PRIMARY,
        sparkline_past=sp_total.tolist(),
        sparkline_past_labels=sp_labels,
    )

    t2, d2, p2 = _trend(conv_rate, prior_conv)
    kpi_conv = kpi_card(
        "Conversion Rate", f"{conv_rate:.1f}%",
        trend_text=f"{t2} vs prior ({p2:.1f}%)" if t2 else None,
        trend_direction=d2, accent_color=SEMANTIC_COLORS["success"],
        sparkline_past=sp_conv.tolist(),
        sparkline_past_labels=sp_labels,
    )

    t3, d3, p3 = _trend(median_days, prior_median, invert=True)
    kpi_lead = kpi_card(
        "Median Days to Appt", f"{median_days:.0f}" if pd.notna(median_days) else "N/A",
        trend_text=f"{t3} vs prior ({p3:.0f}d)" if t3 else None,
        trend_direction=d3, accent_color=CHART_COLORWAY[1],
        sparkline_past=sp_lead.tolist(),
        sparkline_past_labels=sp_labels,
    )

    kpi_pending = kpi_card(
        "Pending Pipeline", f"{pending:,}",
        trend_text=f"{pending / total * 100:.0f}% of total" if total else None,
        accent_color=SEMANTIC_COLORS["warning"],
        sparkline_id=" ",
    )

    t5, d5, p5 = _trend(unique_mds, prior_mds)
    kpi_mds = kpi_card(
        "Unique Referring MDs", f"{unique_mds:,}",
        trend_text=f"{t5} vs prior ({p5:,.0f})" if t5 else None,
        trend_direction=d5, accent_color=CHART_COLORWAY[5],
        sparkline_past=sp_mds.tolist(),
        sparkline_past_labels=sp_labels,
    )

    kpis = [kpi_total, kpi_conv, kpi_lead, kpi_pending, kpi_mds]

    # --- Flow Gantt ---
    flow_data = _compute_referral_flow_data(all_data, cap_0=cap_0, cap_1=cap_1)
    flow_details = _compute_referral_flow_details(all_data, cap_0=cap_0, cap_1=cap_1)

    # --- Charts ---
    fig_providers = _build_top_providers(all_data)
    fig_departments = _build_top_departments(all_data)
    fig_trend = _build_volume_trend(all_data)
    fig_ridge = _build_ridge_plot(all_data)
    fig_conv_dept = _build_conv_by_dept(all_data)
    fig_new = _build_new_referrer_trend(all_data)
    table = _build_detail_table(all_data)

    # --- Dimension trend + comparison ---
    dimension = dim_toggle or "diagnosis"
    dim_df = _assign_dimension_group(all_data, dimension)

    dim_trend_store = _prepare_ref_trend_store(dim_df, dimension) if not dim_df.empty else None

    # Comparison: current vs prior period
    compare_type = dim_compare_period or "calendar"
    if start_date and end_date:
        dim_start = pd.Timestamp(start_date)
        dim_end = pd.Timestamp(end_date)
        if compare_type == "calendar":
            try:
                dim_prior_start = dim_start - pd.DateOffset(years=1)
                dim_prior_end = dim_end - pd.DateOffset(years=1)
            except Exception:
                span = dim_end - dim_start
                dim_prior_end = dim_start - pd.Timedelta(days=1)
                dim_prior_start = dim_prior_end - span
        else:
            span = dim_end - dim_start
            dim_prior_end = dim_start - pd.Timedelta(days=1)
            dim_prior_start = dim_prior_end - span
    else:
        dim_start = all_data["Created"].min()
        dim_end = all_data["Created"].max()
        span = dim_end - dim_start
        dim_prior_end = dim_start - pd.Timedelta(days=1)
        dim_prior_start = dim_prior_end - span

    # Build prior-period dimension-grouped data from unfiltered referrals
    try:
        prior_raw = load_referrals()
        prior_raw = prior_raw[
            (prior_raw["Created"] >= dim_prior_start) &
            (prior_raw["Created"] <= dim_prior_end)
        ]
        if departments and "Referred by Department" in prior_raw.columns:
            p_dept = prior_raw["Referred by Department"].apply(_map_to_our_dept)
            prior_raw = prior_raw[p_dept.isin(departments) | p_dept.isna()]
        if specialty_filter and "DeptSpecialty" in prior_raw.columns:
            prior_raw = prior_raw[prior_raw["DeptSpecialty"] == specialty_filter]
        if diagnosis_filter:
            prior_raw["_diag_filt"] = prior_raw.apply(
                lambda r: _categorise_diagnosis(
                    r.get("Diagnoses"), r.get("Rfl Prim Dx"), r.get("MRN")
                ),
                axis=1,
            )
            prior_raw = prior_raw[prior_raw["_diag_filt"] == diagnosis_filter]
            prior_raw = prior_raw.drop(columns=["_diag_filt"])
        dim_prior_df = _assign_dimension_group(prior_raw, dimension)
    except Exception:
        dim_prior_df = pd.DataFrame()

    fig_dim_comparison = _build_ref_comparison_bars(
        dim_df, dim_prior_df, dim_start, dim_end, dim_prior_start, dim_prior_end,
    ) if not dim_df.empty else empty_dim

    return (kpis, flow_data, flow_details, fig_providers,
            fig_departments, fig_trend, fig_ridge, fig_conv_dept, fig_new, table,
            dim_trend_store, fig_dim_comparison, spec_options)


# ==========================================================================
# Referring Physician Manager (RPM) Callbacks
# ==========================================================================
import threading

# Module-level progress state for background NPI/AI operations
_rpm_progress = {"done": 0, "total": 0, "running": False, "message": ""}
_rpm_npi_results = []  # Pending NPI lookup results for review
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
        _addr_key,
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

        reviewed = False
        address_source = ""  # "": source data, "manual": user-edited/added
        if row_key in overrides:
            ov = overrides[row_key]
            if ov.get("specialty"):
                spec = normalize_specialty(ov["specialty"])
            if ov.get("institution"):
                inst = ov["institution"]
            source = ov.get("source", source)
            reviewed = ov.get("reviewed", False)
            # Use DB address if it was manually set
            if ov.get("address_source") == "manual":
                address_source = "manual"
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
            "name": r["name"],
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
            "name": name,
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


@callback(
    Output(f"{PAGE_ID}-rpm-modal", "opened"),
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
        return (dash.no_update,) * 8
    rows, stats = _build_rpm_grid_data()
    inst_rows, inst_count = _build_inst_grid_data(rows)
    return True, rows, rows, stats, inst_rows, inst_count, str(len(rows)), False


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
    Output(f"{PAGE_ID}-rpm-grid", "rowData", allow_duplicate=True),
    Output(f"{PAGE_ID}-rpm-grid-full-store", "data", allow_duplicate=True),
    Output(f"{PAGE_ID}-rpm-stats", "children", allow_duplicate=True),
    Output(f"{PAGE_ID}-rpm-inst-confirm", "opened"),
    Output(f"{PAGE_ID}-rpm-inst-confirm-text", "children"),
    Output(f"{PAGE_ID}-rpm-inst-confirm-all", "children"),
    Output(f"{PAGE_ID}-rpm-inst-pending", "data"),
    Input(f"{PAGE_ID}-rpm-grid", "cellValueChanged"),
    State(f"{PAGE_ID}-rpm-grid-full-store", "data"),
    State(f"{PAGE_ID}-rpm-unreviewed-toggle", "checked"),
    prevent_initial_call=True,
)
def _rpm_save_edit(changed, full_data, unreviewed_only):
    """Save a manual cell edit. For institution edits where the old value
    is shared by multiple rows, show a confirmation instead of saving."""
    if not changed:
        return (dash.no_update,) * 7
    from data.reviews_db import upsert_referring, add_institution, set_reviewed_bulk

    row_data = full_data or []

    row = changed[0].get("data", {}) if isinstance(changed, list) else changed.get("data", {})
    row_key = row.get("row_key", "")
    npi = row.get("npi", "")
    addr_k = row.get("address_key", "")
    if not npi:
        return (dash.no_update,) * 7

    col = changed[0].get("colId", "") if isinstance(changed, list) else changed.get("colId", "")
    old_value = changed[0].get("oldValue", "") if isinstance(changed, list) else changed.get("oldValue", "")

    if col == "institution" and old_value:
        new_inst = row.get("institution", "")
        # Count how many rows share the old institution name
        shared_count = sum(1 for r in row_data if r.get("institution") == old_value and r.get("row_key") != row_key)
        if shared_count > 0:
            # Show confirmation — don't save yet
            pending = {
                "row_key": row_key, "npi": npi, "address_key": addr_k,
                "old_institution": old_value, "new_institution": new_inst,
            }
            confirm_text = (
                f'Rename "{old_value}" → "{new_inst}"?  '
                f'{shared_count + 1} providers currently have "{old_value}".'
            )
            all_btn = f"Rename all {shared_count + 1} providers"
            # Revert the cell value in row_data (will be applied after confirmation)
            for r in row_data:
                if r.get("row_key") == row_key:
                    r["institution"] = old_value
                    break
            visible = [r for r in row_data if not r.get("reviewed")] if unreviewed_only else row_data
            return visible, row_data, dash.no_update, True, confirm_text, all_btn, pending

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

    total = len(row_data) if row_data else 0
    with_spec = sum(1 for r in row_data if r.get("specialty")) if row_data else 0
    with_inst = sum(1 for r in row_data if r.get("institution")) if row_data else 0
    reviewed_n = sum(1 for r in row_data if r.get("reviewed")) if row_data else 0
    stats = (
        f"{total:,} providers  |  "
        f"{reviewed_n:,} reviewed  |  {total - reviewed_n:,} unreviewed  |  "
        f"{with_spec:,} specialty  |  {with_inst:,} institution"
    )
    visible = [r for r in row_data if not r.get("reviewed")] if unreviewed_only else row_data
    return visible, row_data, stats, False, "", "", None


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
    prevent_initial_call=True,
)
def _rpm_inst_confirm_action(n_one, n_all, n_cancel, pending, full_data, unreviewed_only):
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
        # Cancel — just hide, data already reverted
        visible = [r for r in row_data if not r.get("reviewed")] if unreviewed_only else row_data
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
    visible = [r for r in row_data if not r.get("reviewed")] if unreviewed_only else row_data

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
    prevent_initial_call=True,
)
def _rpm_delete_rows(n, full_data, selected_rows, unreviewed_only):
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
    visible = [r for r in row_data if not r.get("reviewed")] if unreviewed_only else row_data
    return visible, row_data, stats, str(total)


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
    Input(f"{PAGE_ID}-rpm-poll", "n_intervals"),
    prevent_initial_call=True,
)
def _rpm_poll_progress(n):
    """Poll background task progress."""
    with _rpm_lock:
        done = _rpm_progress["done"]
        total = _rpm_progress["total"]
        running = _rpm_progress["running"]
        msg = _rpm_progress["message"]

    pct = int(done / total * 100) if total > 0 else 0
    no = dash.no_update

    if running:
        return (False, pct, {"display": "block"}, msg, {"display": "block"}, no, no)

    # Finished — show review panel with results
    with _rpm_lock:
        review_data = list(_rpm_npi_results)

    if review_data:
        return (
            True, 100, {"display": "none"}, msg, {"display": "block"},
            {"display": "block"}, review_data,
        )
    # No results (e.g. AI lookup finished) — just hide progress
    return (True, 100, {"display": "none"}, msg, {"display": "block"}, no, no)


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
    """Start background Claude AI institution research. Uses selected rows if any, else unreviewed blanks."""
    if not n or not row_data:
        return dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update

    with _rpm_lock:
        if _rpm_progress["running"]:
            return dash.no_update, dash.no_update, dash.no_update, dash.no_update, "Already running..."

    if not selected_rows:
        return True, {"display": "none"}, "grape", {"display": "block"}, "Select rows first, then click to research."
    blanks = [r for r in selected_rows if r.get("npi") and not r.get("institution")]
    if not blanks:
        return True, {"display": "none"}, "grape", {"display": "block"}, "Selected rows already have institutions."

    # Each row is a unique NPI+address — pass all details for institution research
    physicians = [
        {
            "npi": r["npi"],
            "address_key": r.get("address_key", ""),
            "row_key": r.get("row_key", ""),
            "name": r.get("name", ""),
            "city_state": f"{r.get('city', '')}, {r.get('state', '')}".strip(", "),
            "department": r.get("department", ""),
        }
        for r in blanks
    ]

    with _rpm_lock:
        _rpm_progress.update(done=0, total=len(physicians), running=True, message="Starting AI research...")

    def _bg():
        from utils.institution_inference import infer_institutions
        from data.reviews_db import bulk_upsert_referring, get_referring_institutions, add_institution

        existing = get_referring_institutions()

        # Process in chunks of 15 and track progress
        all_results = {}  # row_key -> institution
        chunk_size = 15
        for i in range(0, len(physicians), chunk_size):
            chunk = physicians[i : i + chunk_size]
            # infer_institutions keys results by NPI — map back to row_key
            chunk_results = infer_institutions(chunk, existing)
            # Map NPI results to each row that has that NPI
            for p in chunk:
                if p["npi"] in chunk_results:
                    all_results[p["row_key"]] = chunk_results[p["npi"]]
            existing = list(set(existing + list(chunk_results.values())))
            with _rpm_lock:
                _rpm_progress["done"] = min(i + chunk_size, len(physicians))
                _rpm_progress["message"] = f"Researching institutions... {_rpm_progress['done']}/{len(physicians)}"

        records = []
        for p in physicians:
            if p["row_key"] in all_results:
                inst = all_results[p["row_key"]]
                records.append({
                    "npi": p["npi"], "address_key": p["address_key"],
                    "institution": inst, "source": "claude_ai",
                })
                add_institution(inst)
        if records:
            bulk_upsert_referring(records)

        with _rpm_lock:
            _rpm_progress["running"] = False
            _rpm_progress["message"] = f"Done. Updated {len(records)} of {len(physicians)} rows."

    t = threading.Thread(target=_bg, daemon=True)
    t.start()

    return (
        False,
        {"display": "block"},
        "grape",
        {"display": "block"},
        f"Starting AI research for {len(physicians)} physicians...",
    )


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
    prevent_initial_call=True,
)
def _rpm_mark_reviewed(n, full_data, selected_rows, unreviewed_only):
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
    visible = [r for r in row_data if not r.get("reviewed")] if unreviewed_only else row_data
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


# --- Unreviewed-only toggles ---
# Store the full dataset in a hidden Store. The toggle filters into the grid.
# When the grid rowData changes (edits), we update the store too.

clientside_callback(
    """function(checked, fullData) {
        if (!fullData) return window.dash_clientside.no_update;
        if (checked) {
            return fullData.filter(function(r) { return !r.reviewed; });
        }
        return fullData;
    }""",
    Output(f"{PAGE_ID}-rpm-grid", "rowData", allow_duplicate=True),
    Input(f"{PAGE_ID}-rpm-unreviewed-toggle", "checked"),
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

# Cached referral data + index mapping for diagnosis detail panel
_diag_detail_ref: pd.DataFrame | None = None
_diag_detail_indices: dict[str, list[int]] = {}


def _resolve_referral_diagnosis(row, cv_mrn_dx, course_mrn_dx, c2c, base_map):
    """Resolve a single referral row to (key, description, source_type).

    Priority cascade:
    1. CV DiagnosisCodes — what we actually treated them for
    2. Course DiagnosisCodes — temporally matched course (within -30 to +180 days)
    3. Rfl Prim Dx — what the referral is for (uses ICD from Diagnoses to match)
    4. First ICD-10 code from Diagnoses (for multi-code, pick the one matching Rfl Prim Dx)
    5. Free-text from Diagnoses column

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

    # --- Tier 3/4: ICD codes from Diagnoses column ---
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


def _pick_best_icd(codes, prim_text, diag_text, c2c):
    """For multi-ICD referrals, pick the code that best matches Rfl Prim Dx.

    Strategy:
    1. If Rfl Prim Dx mentions mets/metastasis → pick the C79.x code
    2. If Rfl Prim Dx mentions a primary site → pick the non-C79.x code
    3. Check which code's category matches what _categorise_text returns for Rfl Prim Dx
    4. Fall back to first code
    """
    prim_lower = prim_text.lower()

    # Check if Rfl Prim Dx is about metastases
    is_mets = bool(re.search(
        r"metast|bone met|brain met|lung met|liver met|cord.?compress"
        r"|secondary|mets\b|\bmet\b", prim_lower))

    # Separate mets codes (C79.x, C77.x, C78.x) from primary codes
    mets_codes = [c for c in codes if re.match(r"C7[789]", c)]
    primary_codes = [c for c in codes if c not in mets_codes]

    if is_mets and mets_codes:
        return mets_codes[0]
    if not is_mets and primary_codes:
        return primary_codes[0]

    # Try matching Rfl Prim Dx text to code categories
    text_cat = _categorise_text(prim_text)
    if text_cat:
        for code in codes:
            if c2c.get(code) == text_cat:
                return code

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
    diagnosis key (ICD code or normalized free-text).
    """
    from data.loader import load_referrals, load_clinic_visits, load_courses
    from data.reviews_db import get_all_diagnosis_overrides

    ref = load_referrals()
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

    # Aggregate: key → {count, description, source_type, row_indices}
    agg: dict[str, dict] = {}

    if not ref.empty:
        for idx, row in ref.iterrows():
            key, desc, src_type = _resolve_referral_diagnosis(row, cv_mrn_dx, course_mrn_dx, _DIAG_C2C, base_map)
            if key is None:
                continue
            # Skip codes already in the ARIA base CSV (managed on Diagnosis page)
            if src_type in ("icd", "cv", "course") and key in base_map:
                continue

            if key not in agg:
                agg[key] = {"desc": desc, "count": 0, "type": src_type, "indices": []}
            agg[key]["count"] += 1
            agg[key]["indices"].append(idx)
            # Keep the best description (longest non-empty)
            if desc and len(desc) > len(agg[key]["desc"]):
                agg[key]["desc"] = desc

    # Cache the referral dataframe + index mapping for the detail panel
    global _diag_detail_ref, _diag_detail_indices
    _diag_detail_ref = ref
    _diag_detail_indices = {k: v["indices"] for k, v in agg.items()}

    # Build grid rows
    rows = []
    for key, info in agg.items():
        is_icd = info["type"] in ("icd", "cv")
        code = key if is_icd else ""
        desc = info["desc"]
        pts = info["count"]
        src_type = info["type"]

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
            "source": source,
            "reviewed": reviewed,
        })

    rows.sort(key=lambda r: r["patients"], reverse=True)

    total = len(rows)
    icd_count = sum(1 for r in rows if r["icd_code"])
    text_count = total - icd_count
    categorized = sum(1 for r in rows if r["category"])
    overridden = sum(1 for r in rows if r["source"] not in ("icd", "cv", "course", "free-text"))
    stats = (
        f"{icd_count:,} ICD  |  {text_count:,} free-text  |  "
        f"{categorized:,} categorized  |  {total - categorized:,} unmapped  |  "
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

    # Use the cached index mapping from _build_diag_grid_data
    # This shows ONLY referrals that resolved to this entry via the cascade
    lookup_key = icd_code if icd_code else description.lower()
    indices = _diag_detail_indices.get(lookup_key, [])
    ref = _diag_detail_ref

    if ref is None or not indices:
        label = icd_code or description[:50]
        return {"display": "block", "marginTop": "6px"}, f"{label} — 0 records", []

    detail = ref.loc[indices].copy()
    cols = ["Created", "MRN", "Patient Name", "Rfl Prim Dx", "Diagnoses", "Status"]
    detail = detail[[c for c in cols if c in detail.columns]]
    for dc in ["Created"]:
        if dc in detail.columns:
            detail[dc] = detail[dc].dt.strftime("%m/%d/%Y").fillna("")

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
