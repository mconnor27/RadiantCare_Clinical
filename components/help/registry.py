"""Registry of help pages.

Each entry maps a page path to:
  label:   Display label in the help sidebar (matches nav label where possible).
  icon:    Tabler icon name (same as nav).
  section: Section header the page groups under (matches NAV_SECTIONS).
  sql:     List of SQL_SCRIPTS keys that feed this page's data.
           Empty list → page is derived from multiple/other sources.
  sql_intro: Optional intro paragraph for the SQL tab (for pages that derive
             from multiple scripts and need context about why).
  ui_module: Python module path under components.help.content that exports
             a `UI_CONTENT` attribute. Pages without UI content yet use
             "placeholder".
"""

from __future__ import annotations


HELP_PAGES = [
    # OVERVIEW ---------------------------------------------------------------
    {
        # Synthetic path — not a real Dash route. The Overview entry documents
        # the project as a whole and uses its own Back-End / Front-End tabs
        # (see overview.py TABS).
        "path": "/_overview",
        "label": "Overview",
        "icon": "tabler:book",
        "section": "OVERVIEW",
        "sql": list(),            # unused — overview.py defines custom TABS
        "ui_module": "overview",
    },
    {
        # Synthetic path — not a real Dash route. Data Sources renders a
        # live filesystem scan of every CSV / XLSX feeding the dashboard
        # (see data.py build_tabs).
        "path": "/_data",
        "label": "Data Sources",
        "icon": "tabler:database-search",
        "section": "OVERVIEW",
        "sql": list(),            # unused — data.py defines build_tabs()
        "ui_module": "data",
    },

    # HOME — its own bucket so it visually separates project-level docs
    # (Overview / Data Sources) from per-page help below.
    {
        "path": "/",
        "label": "Home",
        "icon": "tabler:home",
        "section": "",
        "sql": [
            "DailyVolume_Past",
            "Treatment_Detail",
            "Clinic_Visits",
            "Simulations",
            "Availability",
        ],
        "sql_intro": (
            "The Home page aggregates signals from several of the per-page "
            "data sources. Its SQL footprint is the union of those scripts — "
            "for a full project-level view of the SQL layer, see the Overview "
            "entry above."
        ),
        "ui_module": "home",
    },

    # CLINICAL ---------------------------------------------------------------
    {
        "path": "/operations",
        "label": "Operations",
        "icon": "tabler:chart-bar",
        "section": "CLINICAL",
        "sql": ["DailyVolume_Past", "DailyVolume_Future", "Treatment"],
        "sql_intro": (
            "The Operations page draws from the two DailyVolume reports (past and "
            "future) for machine-level time metrics and the Treatment report for "
            "technique-level volume counts."
        ),
        "ui_module": "operations",
    },
    {
        "path": "/workflow",
        "label": "Workflow",
        "icon": "tabler:arrows-right-left",
        "section": "CLINICAL",
        "sql": ["Workflow_Events"],
        "ui_module": "workflow",
    },
    {
        "path": "/clinic-visits",
        "label": "Clinic Visits",
        "icon": "tabler:stethoscope",
        "section": "CLINICAL",
        "sql": ["Clinic_Visits"],
        "ui_module": "clinic_visits",
    },
    {
        "path": "/simulations",
        "label": "Simulations",
        "icon": "tabler:scan",
        "section": "CLINICAL",
        "sql": ["Simulations"],
        "ui_module": "simulations",
    },
    {
        "path": "/tasks",
        "label": "Tasks",
        "icon": "tabler:checklist",
        "section": "CLINICAL",
        "sql": ["Tasks"],
        "ui_module": "tasks",
    },
    {
        "path": "/otvs",
        "label": "OTVs",
        "icon": "tabler:clipboard-check",
        "section": "CLINICAL",
        "sql": ["Weekly_Visits"],
        "ui_module": "otvs",
    },
    {
        "path": "/diagnosis",
        "label": "Diagnosis",
        "icon": "tabler:dna",
        "section": "CLINICAL",
        "sql": ["Clinic_Visits", "Simulations", "Courses", "Plans"],
        "sql_intro": (
            "The Diagnosis page aggregates diagnosis codes from multiple activity "
            "streams: clinic visits (consult-time diagnosis), simulations (sim-time), "
            "and courses/plans (treatment-time). Each stream applies its own "
            "diagnosis-resolution cascade — see the scripts below for details."
        ),
        "ui_module": "diagnosis",
    },

    # TREATMENT --------------------------------------------------------------
    {
        "path": "/treatment",
        "label": "Treatment",
        "icon": "tabler:activity",
        "section": "TREATMENT",
        "sql": ["Treatment", "Treatment_Detail"],
        "sql_intro": (
            "The Treatment page uses the aggregated Treatment report for daily "
            "volume charts and Treatment_Detail for drill-through tables and "
            "per-patient / per-physician breakdowns."
        ),
        "ui_module": "treatment",
    },
    {
        "path": "/courses",
        "label": "Courses",
        "icon": "tabler:package",
        "section": "TREATMENT",
        "sql": ["Courses"],
        "ui_module": "courses",
    },
    {
        "path": "/plans",
        "label": "Plans",
        "icon": "tabler:ruler-measure",
        "section": "TREATMENT",
        "sql": ["Plans"],
        "ui_module": "plans",
    },
    {
        "path": "/procedures",
        "label": "Procedures",
        "icon": "tabler:needle",
        "section": "TREATMENT",
        "sql": ["Procedures", "Workflow_Events"],
        "sql_intro": (
            "Procedures pulls primarily from the Procedures report for per-"
            "appointment detail, with Workflow_Events supplying the consult→procedure "
            "timeline context where available."
        ),
        "ui_module": "procedures",
    },

    # RESOURCES --------------------------------------------------------------
    {
        "path": "/machines",
        "label": "Machine Downtime",
        "icon": "tabler:alert-triangle",
        "section": "RESOURCES",
        "sql": ["Downtime_Gaps", "Machine_Error", "Downtime_FieldTicks"],
        "sql_intro": (
            "Machine Downtime overlays three reports: Downtime_Gaps (inferred "
            "downtime bands with confidence and patient impact), Machine_Error "
            "(discrete MACHINE-termination events), and Downtime_FieldTicks (the "
            "per-beam / per-image tick data that backs the drill-down Gantt)."
        ),
        "ui_module": "machines",
    },
    {
        "path": "/machine-statistics",
        "label": "Machine Statistics",
        "icon": "tabler:chart-dots-3",
        "section": "RESOURCES",
        "sql": ["Machine_Statistics"],
        "ui_module": "machine_statistics",
    },
    {
        "path": "/physicians",
        "label": "Physicians",
        "icon": "tabler:stethoscope-off",
        "section": "RESOURCES",
        "sql": [],
        "sql_intro": (
            "The Physicians page aggregates physician schedule and attribution "
            "data derived from multiple activity reports rather than a dedicated "
            "SQL script."
        ),
        "ui_module": "physicians",
    },
    {
        "path": "/scheduling",
        "label": "Scheduling",
        "icon": "tabler:calendar-event",
        "section": "RESOURCES",
        "sql": ["Availability", "Clinic_Visits", "Simulations"],
        "sql_intro": (
            "Scheduling is built on the Availability extract — a forward-looking "
            "snapshot of HOLD / scheduleable slots — and overlays already-booked "
            "appointments from Clinic Visits (consults, re-evals, follow-ups) "
            "and Simulations onto the same time grid so taken capacity is "
            "visible alongside open capacity."
        ),
        "ui_module": "scheduling",
    },

    # FINANCIAL --------------------------------------------------------------
    {
        "path": "/billing",
        "label": "Billing",
        "icon": "tabler:receipt",
        "section": "FINANCIAL",
        "sql": ["Billing"],
        "ui_module": "billing",
    },
    {
        "path": "/cpt-audit",
        "label": "CPT Audit",
        "icon": "tabler:file-invoice",
        "section": "FINANCIAL",
        "sql": ["Billing"],
        "sql_intro": (
            "CPT Audit reads from the same Billing extract as the Billing page; "
            "the difference is purely front-end — CPT Audit pivots on code to "
            "surface coding-completeness and mismatch issues."
        ),
        "ui_module": "cpt_audit",
    },
    {
        "path": "/otv-audit",
        "label": "OTV Audit",
        "icon": "tabler:report-medical",
        "section": "FINANCIAL",
        "sql": ["Weekly_Visits"],
        "sql_intro": (
            "OTV Audit reads the Weekly_Visits extract (CPT 77427/77431 weekly "
            "management visits) and the pre-computed OTV Audit file from "
            "Complete/ that tags each course as OK / Too Few / Extra Visit(s)."
        ),
        "ui_module": "otv_audit",
    },

    # POPULATION -------------------------------------------------------------
    {
        "path": "/patients",
        "label": "Patients",
        "icon": "tabler:users",
        "section": "POPULATION",
        "sql": ["Treatment_Detail"],
        "sql_intro": (
            "Patients is geography-first: it pulls per-patient rows from "
            "Treatment_Detail and joins to the Referrals extract for address and "
            "zip-code-level mapping."
        ),
        "ui_module": "patients",
    },
    {
        "path": "/referrals",
        "label": "Referrals",
        "icon": "tabler:link",
        "section": "POPULATION",
        "sql": [],
        "sql_intro": (
            "Referrals uses the Referrals CSV (referring physician directory, "
            "linked addresses, specialty) and the per-activity referring-physician "
            "fields from Clinic_Visits / Simulations / Billing. It does not have a "
            "dedicated SQL script — the referring-physician cascade is handled "
            "in the loader."
        ),
        "ui_module": "referrals",
    },
    {
        "path": "/medonc-referrals",
        "label": "Referrals (MedOnc)",
        "icon": "tabler:transfer",
        "section": "POPULATION",
        "sql": [],
        "sql_intro": (
            "Referrals (MedOnc) has no dedicated SQL script. Its primary source "
            "is a manual Excel export from the PRCS medical oncology scheduling "
            "system (Referrals_Report_PRCS_*.xlsx). That feed is joined by MRN "
            "against the rad-onc Referrals extract (same xlsx family as the "
            "Referrals page) and against Treatment_Detail in the loader, so the "
            "page inherits its SQL coverage from those scripts rather than "
            "having its own."
        ),
        "ui_module": "medonc_referrals",
    },
]


# Index by path for fast lookup
HELP_PAGES_BY_PATH = {p["path"]: p for p in HELP_PAGES}


# Grouped for sidebar rendering (same ordering as NAV_SECTIONS)
def grouped_pages() -> list[tuple[str, list[dict]]]:
    """Return [(section_name, [page_dict, ...]), ...] preserving order."""
    groups: list[tuple[str, list[dict]]] = []
    seen: dict[str, list[dict]] = {}
    for p in HELP_PAGES:
        if p["section"] not in seen:
            seen[p["section"]] = []
            groups.append((p["section"], seen[p["section"]]))
        seen[p["section"]].append(p)
    return groups
