"""Centralized configuration for RadiantCare Clinical Dashboard."""

import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Load .env file if present (no dependency needed)
# ---------------------------------------------------------------------------
_env_path = Path(__file__).resolve().parent.parent / ".env"
if _env_path.is_file():
    with open(_env_path) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _key, _, _val = _line.partition("=")
                os.environ[_key.strip()] = _val.strip()

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent

DATA_DIR = Path(
    os.environ.get(
        "DATA_DIR",
        os.path.expanduser(
            "~/Library/CloudStorage/OneDrive-ProvidenceSt.JosephHealth/AURA_Reports"
        ),
    )
)
DATA_COMPLETE = DATA_DIR / "Complete"
DATA_INCREMENTAL = DATA_DIR / "Incremental"
DATA_LOOKUP = DATA_DIR / "Lookup"

MAPBOX_TOKEN = os.environ.get("MAPBOX_TOKEN", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

# ---------------------------------------------------------------------------
# Colors
# ---------------------------------------------------------------------------
PRIMARY = "#7C2A83"
PRIMARY_LIGHT = "#F3E8F5"
PRIMARY_DARK = "#5A1D60"

DEPARTMENT_COLORS = {
    "Lacey": "#2196F3",
    "Centralia": "#F44336",
    "Aberdeen": "#4CAF50",
}

SEMANTIC_COLORS = {
    "success": "#10B981",
    "warning": "#F59E0B",
    "error": "#EF4444",
    "info": "#3B82F6",
}

NEUTRAL = {
    "bg_page": "#F5F6F8",
    "bg_card": "#FFFFFF",
    "bg_nav": "#7C2A83",
    "bg_nav_hover": "#6B2472",
    "bg_filter_bar": "#FFFFFF",
    "border": "#E0E0E0",
    "border_light": "#F0F0F0",
    "text_primary": "#1A1A2E",
    "text_secondary": "#6B7280",
    "text_muted": "#9CA3AF",
    "text_nav": "#A0A4B8",
    "text_nav_active": "#FFFFFF",
}

CHART_COLORWAY = [
    "#7C2A83", "#2196F3", "#F44336", "#4CAF50",
    "#FF9800", "#00BCD4", "#9C27B0", "#795548",
]

# ---------------------------------------------------------------------------
# Physicians & Departments
# ---------------------------------------------------------------------------
PHYSICIANS = [
    "Allen, Gregory",
    "Connor, Michael",
    "Suszko, Justin",
    "Tinnel, Brent",
]

DEPARTMENTS = ["Lacey", "Centralia", "Aberdeen"]

MACHINE_MAP = {
    "Lacey": ["TrueBeamNorth", "21EX", "6EX"],
    "Centralia": ["21iX_CEN"],
    "Aberdeen": ["21iX_AB"],
}

# Reverse lookup: machine name → department
MACHINE_DEPT = {m: dept for dept, machines in MACHINE_MAP.items() for m in machines}

# ---------------------------------------------------------------------------
# Font stack
# ---------------------------------------------------------------------------
FONT_FAMILY = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif"

# ---------------------------------------------------------------------------
# DMC Theme
# ---------------------------------------------------------------------------
DMC_THEME = {
    "primaryColor": "violet",
    "colors": {
        "violet": [
            "#F3E8F5", "#E5CCE9", "#D4A9D9", "#C186C9", "#AE63B9",
            "#9B40A9", "#7C2A83", "#6B2472", "#5A1D60", "#49174F",
        ],
    },
    "fontFamily": FONT_FAMILY,
    "headings": {"fontFamily": FONT_FAMILY},
}

# ---------------------------------------------------------------------------
# Plotly defaults
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Chart card defaults
# ---------------------------------------------------------------------------
DEFAULT_GRAPH_CONFIG = {
    "displayModeBar": False,
    "scrollZoom": False,
    "doubleClick": "reset",
}
CHART_PAPER_HEIGHT = "466px"     # Standard Paper height (half-width / row of 2)
CHART_PAPER_HEIGHT_SM = "380px"  # Compact Paper height (third-width / row of 3)
CHART_GRAPH_HEIGHT = "380px"     # Graph area height within card (legacy, unused by flex layout)

# ---------------------------------------------------------------------------
# Plotly defaults
# ---------------------------------------------------------------------------
DEFAULT_LAYOUT = dict(
    font=dict(family=FONT_FAMILY, size=13),
    plot_bgcolor="#FFFFFF",
    paper_bgcolor="#FFFFFF",
    margin=dict(l=28, r=8, t=8, b=32),
    xaxis=dict(gridcolor="#F0F0F0", linecolor="#E0E0E0", showgrid=False),
    yaxis=dict(gridcolor="#F0F0F0", linecolor="#E0E0E0", showgrid=True),
    legend=dict(
        orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0,
        font=dict(size=12),
    ),
    hoverlabel=dict(
        bgcolor="#FFFFFF", bordercolor="#E0E0E0",
        font=dict(size=13, color="#1A1A2E"),
    ),
    colorway=CHART_COLORWAY,
)

# ---------------------------------------------------------------------------
# AG Grid defaults
# ---------------------------------------------------------------------------
DEFAULT_COLUMN_DEFS = {
    "sortable": True,
    "filter": True,
    "resizable": True,
    "floatingFilter": False,
}

DEFAULT_GRID_OPTIONS = {
    "pagination": True,
    "paginationPageSize": 50,
    "domLayout": "autoHeight",
    "rowSelection": "single",
    "animateRows": True,
}

# ---------------------------------------------------------------------------
# Mapbox
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# ABMS-aligned specialty list (canonical names for referring physician manager)
# ---------------------------------------------------------------------------
ABMS_SPECIALTIES = [
    "Allergy & Immunology",
    "Alternative Medicine",
    "Breast Surgery",
    "Cardiology",
    "Colorectal Surgery",
    "Dermatology",
    "Emergency Medicine",
    "Endocrinology",
    "Gastroenterology",
    "General Surgery",
    "Gynecologic Oncology",
    "Hepatology",
    "Hospital Medicine",
    "Infectious Disease",
    "Internal Medicine",
    "Medical Oncology",
    "Nephrology",
    "Neuro-Oncology",
    "Neurology",
    "Neurosurgery",
    "OB/GYN",
    "Ophthalmology",
    "Oral Surgery",
    "Orthopedic Oncology",
    "Orthopedics",
    "Otolaryngology",
    "PA/NP",
    "Palliative Care",
    "Pathology",
    "Pediatric Oncology",
    "Pediatrics",
    "Plastic Surgery",
    "PM&R",
    "Primary Care",
    "Psychiatry",
    "Pulmonary Medicine",
    "Radiation Oncology",
    "Radiology",
    "Resident",
    "Rheumatology",
    "Surgical Oncology",
    "Thoracic Surgery",
    "Unknown",
    "Urology",
    "Vascular Surgery",
]

# Map NPI Registry taxonomy names → our ABMS_SPECIALTIES
NPI_SPECIALTY_MAP: dict[str, str] = {
    # Exact matches (already in list) need no mapping
    # NPI variations → our canonical name
    "Cardiovascular Disease":               "Cardiology",
    "Colon & Rectal Surgery":               "Colorectal Surgery",
    "Family Medicine":                      "Primary Care",
    "Family Practice":                      "Primary Care",
    "General Practice":                     "Primary Care",
    "General Surgeon":                      "General Surgery",
    "Hematology & Medical Oncology":        "Medical Oncology",
    "Hematology & Oncology":                "Medical Oncology",
    "Hematology/Oncology":                  "Medical Oncology",
    "Internal Medicine, Hematology & Oncology": "Medical Oncology",
    "Oncology/Hematology":                  "Medical Oncology",
    "Hospice & Palliative Medicine":        "Palliative Care",
    "Hospice and Palliative Medicine":      "Palliative Care",
    "Internal Medicine, Pulmonary Disease": "Pulmonary Medicine",
    "Pulmonary Disease":                    "Pulmonary Medicine",
    "Neurological Surgery":                 "Neurosurgery",
    "Obstetrics & Gynecology":              "OB/GYN",
    "Obstetrics and Gynecology":            "OB/GYN",
    "Gynecology":                           "OB/GYN",
    "Opthamology":                          "Ophthalmology",
    "Optometry":                            "Ophthalmology",
    "Orthopaedic Surgery":                  "Orthopedics",
    "Orthopedic Surgery":                   "Orthopedics",
    "Physical Medicine & Rehabilitation":   "PM&R",
    "Physical Medicine and Rehabilitation": "PM&R",
    "Physiatry":                            "PM&R",
    "Thoracic & Cardiac Surgery":           "Thoracic Surgery",
    "Thoracic Surgery (Cardiothoracic Vascular Surgery)": "Thoracic Surgery",
    "Nurse Practitioner":                   "PA/NP",
    "Physician Assistant":                  "PA/NP",
    "Other":                                "Unknown",
}


def normalize_specialty(raw: str) -> str:
    """Map an NPI taxonomy specialty name to our canonical ABMS list."""
    if not raw:
        return ""
    raw = raw.strip()
    # Already in our list?
    if raw in ABMS_SPECIALTIES:
        return raw
    # Check mapping
    mapped = NPI_SPECIALTY_MAP.get(raw)
    if mapped:
        return mapped
    # Case-insensitive check
    raw_lower = raw.lower()
    for spec in ABMS_SPECIALTIES:
        if spec.lower() == raw_lower:
            return spec
    for key, val in NPI_SPECIALTY_MAP.items():
        if key.lower() == raw_lower:
            return val
    return raw  # Return as-is if no mapping found

# ---------------------------------------------------------------------------
# Mapbox
# ---------------------------------------------------------------------------
MAPBOX_CENTER = dict(lat=47.0, lon=-122.9)
MAPBOX_ZOOM = 7
MAPBOX_STYLE = "light"

# ---------------------------------------------------------------------------
# Nav page definitions (grouped)
# ---------------------------------------------------------------------------
NAV_SECTIONS = [
    {
        "section": "OVERVIEW",
        "pages": [
            {"label": "Home", "path": "/", "icon": "tabler:home"},
        ],
    },
    {
        "section": "CLINICAL",
        "pages": [
            {"label": "Operations",    "path": "/operations",    "icon": "tabler:chart-bar"},
            {"label": "Workflow",      "path": "/workflow",      "icon": "tabler:arrows-right-left"},
            {"label": "Clinic Visits", "path": "/clinic-visits", "icon": "tabler:stethoscope"},
            {"label": "Simulations",   "path": "/simulations",   "icon": "tabler:scan"},
            {"label": "Tasks",         "path": "/tasks",         "icon": "tabler:checklist"},
            {"label": "OTVs",          "path": "/otvs",          "icon": "tabler:clipboard-check"},
            {"label": "Diagnosis",    "path": "/diagnosis",    "icon": "tabler:dna"},
        ],
    },
    {
        "section": "TREATMENT",
        "pages": [
            {"label": "Treatment", "path": "/treatment", "icon": "tabler:activity"},
            {"label": "Courses", "path": "/courses", "icon": "tabler:package"},
            {"label": "Plans",   "path": "/plans",   "icon": "tabler:ruler-measure"},
            {"label": "Procedures", "path": "/procedures", "icon": "tabler:needle"},
        ],
    },
    {
        "section": "RESOURCES",
        "pages": [
            {"label": "Machine Downtime", "path": "/machines", "icon": "tabler:alert-triangle"},
            {"label": "Machine Statistics", "path": "/machine-statistics", "icon": "tabler:chart-dots-3"},
            {"label": "Physicians", "path": "/physicians", "icon": "tabler:stethoscope-off"},
        ],
    },
    {
        "section": "FINANCIAL",
        "pages": [
            {"label": "Billing",   "path": "/billing",   "icon": "tabler:receipt"},
            {"label": "CPT Audit", "path": "/cpt-audit", "icon": "tabler:file-invoice"},
            {"label": "OTV Audit", "path": "/otv-audit", "icon": "tabler:report-medical"},
        ],
    },
    {
        "section": "POPULATION",
        "pages": [
            {"label": "Patients",  "path": "/patients",  "icon": "tabler:users"},
            {"label": "Referrals", "path": "/referrals", "icon": "tabler:link"},
        ],
    },
]

# Flat list for backward compatibility (used by some components)
NAV_PAGES = [page for section in NAV_SECTIONS for page in section["pages"]]
