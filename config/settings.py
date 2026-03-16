"""Centralized configuration for RadiantCare Clinical Dashboard."""

import os
from pathlib import Path

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

MAPBOX_TOKEN = os.environ.get(
    "MAPBOX_TOKEN",
    "",
)

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
    "Lacey": ["TrueBeamNorth", "21EX"],
    "Centralia": ["21iX_CEN"],
    "Aberdeen": ["21iX_AB"],
}

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
        ],
    },
    {
        "section": "TREATMENT",
        "pages": [
            {"label": "Courses", "path": "/courses", "icon": "tabler:package"},
            {"label": "Plans",   "path": "/plans",   "icon": "tabler:ruler-measure"},
        ],
    },
    {
        "section": "RESOURCES",
        "pages": [
            {"label": "Machines",   "path": "/machines",   "icon": "tabler:cpu"},
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
