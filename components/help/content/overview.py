"""Project-level Overview help content.

Overview uses a custom two-tab layout (Back-End SQL + Front-End App) instead
of the standard SQL-data-source / UI-processing tabs. The modal reads
`TABS` to know how to render.
"""

from __future__ import annotations

from pathlib import Path as _Path

import dash_mantine_components as dmc
from dash_iconify import DashIconify

from config.settings import NAV_PAGES, PRIMARY, PROJECT_ROOT
from ..sql_summaries import (
    LARGEST_SCRIPT,
    SMALLEST_SCRIPT,
    SQL_FIRST_COMMIT,
    SQL_LATEST_COMMIT,
    SQL_SCRIPTS,
    SQL_SHARE,
    TOTAL_COMMENT_LINES,
    TOTAL_FILE_LINES,
    TOTAL_SCRIPTS,
    TOTAL_SQL_LINES,
)
from ..renderers import body, bullets, section, subheading


def _screenshot(src: str, caption: str | None = None,
                max_width: str | int = "100%") -> dmc.Paper:
    """Inline screenshot used in the Overview's common-UI-components section."""
    children: list = [
        dmc.Image(
            src=src,
            fit="contain",
            radius="sm",
            style={
                "width": "100%",
                "maxWidth": max_width,
                "display": "block",
                "margin": "0 auto",
            },
        ),
    ]
    if caption:
        children.append(
            dmc.Text(caption, size="xs", c="dimmed", ta="center", mt=4)
        )
    return dmc.Paper(
        p="xs", radius="md", withBorder=True, mt="xs", mb="sm",
        style={"backgroundColor": "var(--bg-card-alt)"},
        children=children,
    )


# ---------------------------------------------------------------------------
# Front-end stats — LOC is recounted from the live project tree at import so
# the help modal stays accurate across refactors. Commit metadata stays
# hardcoded (requires git access to compute and can be stale in deployed
# environments).
# ---------------------------------------------------------------------------
def _count_lines(path: _Path) -> int:
    try:
        with path.open("r", encoding="utf-8", errors="replace") as f:
            return sum(1 for _ in f)
    except OSError:
        return 0


# Source dirs (app code only — excludes archive/, tools/, scripts/,
# docs/, tests, caches, vendored deps).
_PY_DIRS = ["pages", "components", "data", "utils", "config"]
_ROOT_PY = ["dash_app.py"]  # top-level app entry points

_FRONTEND_PY_BY_DIR: dict[str, int] = {}
for _dname in _PY_DIRS:
    _d = PROJECT_ROOT / _dname
    if _d.is_dir():
        _FRONTEND_PY_BY_DIR[_dname] = sum(
            _count_lines(p) for p in _d.rglob("*.py")
            if "__pycache__" not in p.parts
        )

_ROOT_PY_LOC = sum(
    _count_lines(PROJECT_ROOT / f) for f in _ROOT_PY
    if (PROJECT_ROOT / f).is_file()
)

FRONTEND_PYTHON_LOC = sum(_FRONTEND_PY_BY_DIR.values()) + _ROOT_PY_LOC
FRONTEND_PAGES_LOC = _FRONTEND_PY_BY_DIR.get("pages", 0)
FRONTEND_PY_NON_PAGES_LOC = FRONTEND_PYTHON_LOC - FRONTEND_PAGES_LOC

_ASSETS = PROJECT_ROOT / "assets"
FRONTEND_JS_LOC = sum(_count_lines(p) for p in _ASSETS.rglob("*.js")) if _ASSETS.is_dir() else 0
FRONTEND_CSS_LOC = sum(_count_lines(p) for p in _ASSETS.rglob("*.css")) if _ASSETS.is_dir() else 0
FRONTEND_TOTAL_LOC = FRONTEND_PYTHON_LOC + FRONTEND_JS_LOC + FRONTEND_CSS_LOC

# Smallest / largest page file (for the overview bullet).
_PAGES_DIR = PROJECT_ROOT / "pages"
_PAGE_SIZES: list[tuple[int, str]] = []
if _PAGES_DIR.is_dir():
    for _p in _PAGES_DIR.glob("*.py"):
        if _p.name == "__init__.py":
            continue
        _n = _count_lines(_p)
        if _n > 0:
            _PAGE_SIZES.append((_n, _p.stem))
_PAGE_SIZES.sort()
PAGE_LOC_MIN = _PAGE_SIZES[0] if _PAGE_SIZES else (0, "")
PAGE_LOC_MAX = _PAGE_SIZES[-1] if _PAGE_SIZES else (0, "")

FRONTEND_FIRST_COMMIT = "2025-11-01"
FRONTEND_LATEST_COMMIT = "2026-04-17"
FRONTEND_COMMIT_COUNT = 59
NUM_PAGES = len(NAV_PAGES)


def _stat(label: str, value: str, sublabel: str | None = None) -> dmc.Paper:
    """One stat tile for the project-overview grids."""
    return dmc.Paper(
        p="md", radius="md", withBorder=True,
        style={"height": "100%"},
        children=[
            dmc.Text(label, size="xs", c="dimmed", fw=500, tt="uppercase",
                     style={"letterSpacing": "0.5px"}),
            dmc.Text(value, size="lg", c=PRIMARY, fw=700, mt=4),
            (dmc.Text(sublabel, size="xs", c="dimmed", mt=2) if sublabel else None),
        ],
    )


# ---------------------------------------------------------------------------
# Back-End SQL tab
# ---------------------------------------------------------------------------

BACKEND_SQL_CONTENT = dmc.Stack(
    gap="md",
    children=[
        dmc.Text(
            "The production SQL layer that extracts data from the Varian ARIA "
            "warehouse. Per-page SQL details are available under each individual "
            "page entry in the sidebar at left.",
            size="sm", c="dimmed", style={"lineHeight": 1.6},
        ),

        dmc.Grid(
            gutter="md",
            children=[
                dmc.GridCol(_stat("SQL Scripts", f"{TOTAL_SCRIPTS}", "production reports"), span=3),
                dmc.GridCol(_stat("SQL Code", f"{TOTAL_SQL_LINES:,}", f"{SQL_SHARE:.0%} of {TOTAL_FILE_LINES:,} file lines"), span=3),
                dmc.GridCol(_stat("Comments / Blank", f"{TOTAL_COMMENT_LINES:,}", "documentation & whitespace"), span=3),
                dmc.GridCol(_stat("Development Span", "≈ 5 months", f"{SQL_FIRST_COMMIT} → {SQL_LATEST_COMMIT}"), span=3),
            ],
        ),

        section(
            "Production SQL Layer",
            "tabler:database-cog",
            body(
                f"The dashboard is fed by {TOTAL_SCRIPTS} production SQL scripts "
                f"totaling {TOTAL_FILE_LINES:,} file lines — {TOTAL_SQL_LINES:,} "
                f"lines of SQL code ({SQL_SHARE:.0%}) plus {TOTAL_COMMENT_LINES:,} "
                "lines of in-script documentation and whitespace. The scripts target "
                "the Varian ARIA data warehouse (SQL Server); each is a Report "
                "Builder export that runs on a schedule and writes a CSV to OneDrive "
                "where the dashboard picks it up.",
            ),

            subheading("Overall timeline"),
            body(
                f"First commit: {SQL_FIRST_COMMIT}. Most recent commit: "
                f"{SQL_LATEST_COMMIT}. Development spans ~5 months of iterative "
                "work — moving from scheduling-focused reports (Availability, "
                "DailyVolume) through operational detail (Machine_Error, "
                "Downtime_Gaps, Downtime_FieldTicks, Machine_Statistics), "
                "workflow analytics (Clinic_Visits, Simulations, Tasks, "
                "Workflow_Events), clinical census reporting (Courses, Plans, "
                "Treatment, Treatment_Detail, Weekly_Visits, Procedures), and "
                "revenue-cycle reporting (Billing).",
            ),

            subheading("Largest and smallest"),
            bullets([
                f"Largest: {LARGEST_SCRIPT[0]}.sql at {LARGEST_SCRIPT[1]['total']:,} "
                f"file lines ({LARGEST_SCRIPT[1]['sql']:,} SQL) — the consult-to-"
                "treatment event log with 36 output columns and 15 temp tables.",
                f"Smallest: {SMALLEST_SCRIPT[0]}.sql at {SMALLEST_SCRIPT[1]['total']:,} "
                f"file lines ({SMALLEST_SCRIPT[1]['sql']:,} SQL) — the forward-looking "
                "schedule capacity report.",
            ]),

            subheading("Per-script line counts"),
            dmc.Table(
                striped=True, highlightOnHover=True,
                withTableBorder=True, withColumnBorders=True,
                fz="xs", mt="xs",
                children=[
                    dmc.TableThead(
                        dmc.TableTr([
                            dmc.TableTh("Script"),
                            dmc.TableTh("Total"),
                            dmc.TableTh("SQL"),
                            dmc.TableTh("Comments / Blank"),
                        ]),
                    ),
                    dmc.TableTbody([
                        *[
                            dmc.TableTr([
                                dmc.TableTd(f"{key}.sql"),
                                dmc.TableTd(f"{s['total']:,}"),
                                dmc.TableTd(f"{s['sql']:,}"),
                                dmc.TableTd(f"{s['total'] - s['sql']:,}"),
                            ])
                            for key, s in sorted(
                                SQL_SCRIPTS.items(),
                                key=lambda kv: kv[1]["total"],
                                reverse=True,
                            )
                        ],
                        dmc.TableTr([
                            dmc.TableTd(dmc.Text("Total", fw=700, size="xs")),
                            dmc.TableTd(dmc.Text(f"{TOTAL_FILE_LINES:,}", fw=700, size="xs")),
                            dmc.TableTd(dmc.Text(f"{TOTAL_SQL_LINES:,}", fw=700, size="xs")),
                            dmc.TableTd(dmc.Text(f"{TOTAL_COMMENT_LINES:,}", fw=700, size="xs")),
                        ]),
                    ]),
                ],
            ),

            subheading("Cross-cutting design patterns refined across scripts"),
            bullets([
                "Entity-first filtering — filter the primary entity (course, plan, "
                "exam) first, pull related treatments / billing, aggregate, then "
                "apply the reporting date window. Minimizes redundant scans of "
                "FactTreatmentHistory and FactActivityBilling.",
                "Materialized temp tables with clustered indexes instead of CTEs "
                "when a result set is referenced more than once.",
                "Overlap-based date filtering — pulls entities whose lifecycle overlaps "
                "the reporting window (e.g., a course whose start is before @StartDate "
                "but is still active), rather than strict BETWEEN filtering that would "
                "drop mid-flight work.",
                "10-tier plan-level treatment technique classification, cascading from "
                "most-specific (prescription metadata, electron) to least-specific "
                "(field-count heuristic). Consistent across Courses, Plans, Treatment, "
                "Treatment_Detail.",
                "Multi-tier physician attribution: Most Frequent Billing Physician "
                "(scoped to the relevant time window) > Prior Exam Physician > other fallbacks.",
                "Multi-tier diagnosis resolution: billing-linked diagnoses first, "
                "activity-level fallback, patient-level fallback.",
                "3-trigger session detection with CONTINUATION suppression and "
                "FractionNumber cross-check so BID patients, interleaved treatments, "
                "and mid-treatment machine-malfunction recoveries count correctly.",
                "Reference-point deduplication — VMAT/IMRT fields generate multiple "
                "FactTreatmentHistory rows (one per control point); SELECT DISTINCT on "
                "DimFieldID + timestamps collapses these to prevent 10–20× inflation "
                "of beam-on metrics.",
                "Interval merging for non-overlapping minute metrics (Scheduled / "
                "Actual / BeamOn / ApptActual) — each tells a different operational story.",
                "Hybrid baseline start-of-day downtime detection — rolling median "
                "+ peer-machine + cancellations — so the logic works for single-machine "
                "sites as well as multi-machine Lacey.",
            ]),
        ),

        section(
            "ARIA Reporting — Overnight Automation",
            "tabler:clock-hour-4",
            bullets([
                "All production SQL scripts run as scheduled reports in Varian ARIA's "
                "Report Builder. Each executes overnight after a business day so the "
                "dashboard is up to date by the next workday, and runs off-peak so "
                "extraction load doesn't contend with clinical use of ARIA.",
                "Each report writes its output as a timestamped CSV "
                "(Courses_20260417.csv, Plans_20260417.csv, …) to a OneDrive folder "
                "shared with the dashboard host.",
                "Incremental reports (Courses, Plans, Treatment, Billing, Clinic_Visits, "
                "Simulations, Tasks, Workflow, Procedures, Weekly_Visits, Treatment-Detail, "
                "Availability) are date-suffixed — the loader concatenates all increments "
                "in chronological order and deduplicates on UniqueRowID (keeping the latest "
                "record per key).",
                "Complete/ reports (Daily Volume Past/Future, Tasks, OTV Audit, Machine "
                "Errors, Physician Schedule) are full-refresh files — each run replaces "
                "the prior snapshot.",
                "Data may lag by 1–2 days during periods when overnight exports miss their "
                "window. The dashboard uses data-relative dates (max date in the dataset) "
                "rather than wall-clock today, so KPIs and filters handle that lag gracefully.",
                "CSV parsing prefers pyarrow (≈3× faster than the C engine); a fallback to "
                "C with on_bad_lines='skip' handles CSVs with embedded newlines in free-text "
                "fields (Clinic Visits activity notes, Workflow comments).",
                "Treatment-Detail is pre-loaded in a background thread at app startup "
                "because it is the heaviest single CSV.",
            ]),
        ),

        dmc.Alert(
            color="violet", variant="light",
            title="About this count",
            icon=DashIconify(icon="tabler:info-circle", width=20),
            children=dmc.Text(
                "Counts cover active production scripts only; deprecated variants and "
                "internal working copies are excluded. \"SQL code\" excludes single-line "
                "(--), block (/* */), and fully-blank lines.",
                size="xs",
            ),
        ),
    ],
)


# ---------------------------------------------------------------------------
# Front-End App tab
# ---------------------------------------------------------------------------

FRONTEND_CONTENT = dmc.Stack(
    gap="md",
    children=[
        dmc.Text(
            "The Dash application that consumes the SQL extracts. Per-page "
            "UI details are under each individual page entry in the sidebar at left.",
            size="sm", c="dimmed", style={"lineHeight": 1.6},
        ),

        dmc.Grid(
            gutter="md",
            children=[
                dmc.GridCol(_stat("Front-End LOC", f"{FRONTEND_TOTAL_LOC:,}", "Python + JS + CSS"), span=3),
                dmc.GridCol(_stat("Pages", f"{NUM_PAGES}", "across 6 sections"), span=3),
                dmc.GridCol(_stat("Server Callbacks", "310+", "across all pages"), span=3),
                dmc.GridCol(_stat("Commits", f"{FRONTEND_COMMIT_COUNT}", f"{FRONTEND_FIRST_COMMIT} → {FRONTEND_LATEST_COMMIT}"), span=3),
            ],
        ),

        section(
            "Code layout",
            "tabler:device-desktop",
            body(
                f"The dashboard is built with Dash across {NUM_PAGES} pages in "
                "six functional sections (Overview, Clinical, Treatment, Resources, "
                "Financial, Population). Code totals:",
            ),

            dmc.Table(
                striped=True, highlightOnHover=True,
                withTableBorder=True, withColumnBorders=True,
                fz="xs", mt="xs",
                data={
                    "head": ["Layer", "Lines", "Role"],
                    "body": [
                        ["Python — pages/",
                         f"{FRONTEND_PAGES_LOC:,}",
                         f"One file per page; {NUM_PAGES} pages, ranging from "
                         f"{PAGE_LOC_MIN[0]:,} ({PAGE_LOC_MIN[1]}) to "
                         f"{PAGE_LOC_MAX[0]:,} ({PAGE_LOC_MAX[1]})"],
                        ["Python — components/ data/ utils/ config/",
                         f"{FRONTEND_PY_NON_PAGES_LOC:,}",
                         "Reusable components, loaders (1,476 lines), SQLite ORM (983 lines), statistical utilities, "
                         "chart helpers, NPI lookup, payor manager, help system"],
                        ["JavaScript (assets/)",
                         f"{FRONTEND_JS_LOC:,}",
                         "Clientside callbacks: LOESS smoothing, rolling averages, downsampling, chart-type switching, "
                         "date-slider marks, AG Grid dag-funcs, diagnosis taxonomy"],
                        ["CSS (assets/custom.css)",
                         f"{FRONTEND_CSS_LOC:,}",
                         "Sidebar theme, DMC overrides, AG Grid compact theme, date-slider styling"],
                        ["Total",
                         f"{FRONTEND_TOTAL_LOC:,}",
                         "—"],
                    ],
                },
            ),

            subheading("Stack"),
            bullets([
                "Dash 3.4+ with Dash Mantine Components (DMC) for UI primitives — "
                "not dash-bootstrap-components.",
                "dash-ag-grid for tables — not the deprecated dash_table. Used on 18 pages "
                "with custom cell renderers, dependent dropdowns, and CSV export.",
                "Plotly 6.5+ for charts, with a consistent layout (horizontal legend "
                "above chart, light horizontal grid only, department-colored series).",
                "dash-iconify (Tabler icons) throughout.",
                "Mapbox on Patients and Referrals pages for geographic patient / referral distribution.",
                "310+ server-side @callback decorators; 22 in the Billing page alone for revenue, "
                "payer, and rate management.",
            ]),

            subheading("Timeline and commits"),
            body(
                f"Front-end development started {FRONTEND_FIRST_COMMIT} (Dash app "
                f"scaffolding, initial analysis scripts). Most recent commit: "
                f"{FRONTEND_LATEST_COMMIT}. Total commits: {FRONTEND_COMMIT_COUNT}. "
                "Like the SQL layer, development spans ~5 months of iterative work.",
            ),
        ),

        # --- Local SQLite --------------------------------------------------
        section(
            "Local state — SQLite database",
            "tabler:database",
            body(
                "An embedded SQLite database (reviews.db, WAL mode for concurrent reads) "
                "holds all user-editable state that isn't in the ARIA warehouse. 983 lines "
                "of hand-written ORM in data/reviews_db.py manage 8 tables with full CRUD "
                "and bulk-upsert support:",
            ),
            bullets([
                "CPT audit reviews — session-level and course-level approval tracking.",
                "Referring physicians — NPI + address composite key, specialty and "
                "institution enrichment, bulk upsert from the NPPES registry.",
                "Diagnosis taxonomy — category / subcategory tree.",
                "Diagnosis overrides — reviewable ICD-10 → category mappings.",
                "Insurance rates — current rates plus an immutable history table with "
                "effective_date / end_date ranges (audit trail for rate changes).",
                "Payor mappings — raw insurance names from ARIA mapped to standardized "
                "payor names and PHDSC broad categories.",
                "Revenue adjustment settings — per-category payer-mix multipliers plus a "
                "realization factor, with sane defaults baked in.",
            ]),
        ),

        # --- CMS rate data -------------------------------------------------
        section(
            "CMS rate data — Billing",
            "tabler:receipt-2",
            body(
                "The Billing page is a full revenue-estimation engine with multi-year "
                "CMS rate data. Rate tables are loaded at startup, memoized with "
                "@lru_cache, and applied per-CPT according to site-specific rules:",
            ),
            bullets([
                "Physician Fee Schedule (PFS) — 2015–2026 across ~115 CSVs in "
                "data/rvu_files/extracted/ covering RVU tables, GPCI, wage index, and "
                "anesthesia add-ons.",
                "OPPS Addendum B (hospital rates) — 2024–2026, 10 MB CSV with APC payment "
                "rates, status indicators, and wage-adjusted facility / non-facility splits.",
                "GPCI by locality — Rest of Washington (Locality 99) for Work / PE / MP "
                "components, 2015–2026, applied per-year.",
                "Annual CMS conversion factors hardcoded 2015–2026 (_CMS_CF dict). 2026 PFS "
                "CF is $33.40 (non-APM), up from $32.35 in 2025.",
                "26/TC modifier handling — codes with a 26/TC split use the 26-modifier row "
                "for professional; TC-only codes return $0 for the physician (hospital-billed).",
                "HPSA 10% site-level bonus — Centralia and Aberdeen qualify, Lacey does not.",
                "SCH 7.1% Sole Community Hospital bonus applied to OPPS payments for all "
                "Providence Centralia claims.",
                "OPPS wage-index formula: 60% labor share × wage index + 40% non-labor "
                "(unadjusted), using Centralia's reclassified CBSA 45104 (Tacoma-Lakewood).",
                "Aberdeen freestanding (POS 11) — hospital revenue uses PFS Technical "
                "Component rows, not OPPS. Billed on CMS-1500, not UB-04.",
                "Payer-mix multipliers — 8 broad payer categories (Medicare, Medicaid, "
                "Private, Military/VA, Workers Comp, Tribal/IHS, Self Pay, Other) with "
                "adjustable multipliers stored in SQLite and persisted across sessions.",
                "Realization factor — user-adjustable global factor (default 90%) applied "
                "to every revenue estimate to account for denials, contractual adjustments, "
                "and write-offs.",
            ]),
        ),

        # --- Stats / smoothing --------------------------------------------
        section(
            "Statistical compute — server + clientside",
            "tabler:chart-line",
            bullets([
                "LOWESS smoothing via statsmodels on the server (utils/stats.py) for "
                "pre-computed trend lines on the heavier pages.",
                "Custom clientside LOESS implementation in assets/00_utils.js — tricube-"
                "weighted sliding-window regression, O(n·k), used on 2,000+ point time series "
                "so smoothing interactions (slider changes, bandwidth tweaks) stay snappy "
                "without server round-trips.",
                "Null-aware rolling average that preserves pre-go-live gaps — only averages "
                "non-null neighbors, so the line doesn't artificially flatten across a "
                "data-free stretch.",
                "Two downsampling modes — label-preserving (keeps every Nth point) and "
                "bucket-average (for >10K-point series) — chosen per-chart.",
                "Clientside date parsing and label auto-formatting: detects aggregation "
                "level (yearly / monthly / weekly / daily) and swaps label format to avoid "
                "Plotly bar-merging artifacts at dense zoom levels.",
            ]),
        ),

        # --- Caching / startup --------------------------------------------
        section(
            "Data loading and caching",
            "tabler:cpu",
            bullets([
                "Parquet cache layer — first CSV read parses via pyarrow, writes a "
                "zstd-compressed parquet to .data_cache/. Subsequent reads hit parquet in "
                "~50 ms instead of a full CSV reparse.",
                "Cache invalidation by source-file mtime — the loader compares the parquet's "
                "mtime to the newest CSV's mtime and reparses automatically when upstream "
                "changes.",
                "@lru_cache on every public loader so a given dataset is parsed once per "
                "app lifecycle.",
                "Page-aware preloader — a background thread starts on app launch and walks "
                "a priority queue of the 12 heaviest datasets. Navigation hints reorder the "
                "queue so the next page the user visits is prioritized.",
                "Preload progress bar at the bottom of the viewport shows current loader and "
                "N/total completed; auto-hides when everything is warm.",
                "Global loading overlay covers the app until Treatment-Detail (the heaviest "
                "single CSV) has been pre-loaded on a dedicated thread.",
                "Refresh button in the top-right corner clears the LRU caches and reloads "
                "the page — cheapest way to pick up a newly-delivered overnight export.",
            ]),
        ),

        # --- External integrations ----------------------------------------
        section(
            "External integrations",
            "tabler:plug-connected",
            bullets([
                "NPPES Registry — utils/npi_lookup.py (210 lines) provides batch NPI lookups "
                "via CMS's public API with 300 ms rate limiting. Results normalized from 130+ "
                "raw taxonomy strings into ~20 canonical ABMS specialties (Radiation Oncology, "
                "Medical Oncology, Surgical Oncology, …) and written to the referring-"
                "physician table.",
                "Mapbox — Patients and Referrals pages render patient geography and referring-"
                "physician distribution on a light-style base map. Token via MAPBOX_TOKEN env "
                "variable.",
                "ICD-10 taxonomy — a diagnosis category/subcategory tree is published to "
                "the browser via a dcc.Store + clientside bootstrap so dependent dropdowns "
                "on AG Grid cells can filter without server round-trips.",
            ]),
        ),

        # --- Common UI components ----------------------------------------
        section(
            "Common UI components",
            "tabler:components",
            body(
                "Four building blocks appear across many pages. Once you know "
                "them, any page in the dashboard works the same way:",
            ),

            subheading("Top filter bar"),
            body(
                "Sticky header at the top of every content page. The default "
                "layout renders four controls, left to right: a date preset "
                "segmented control (YTD / 12 mo / All), a custom date range "
                "picker, department chips (Lacey / Centralia / Aberdeen as "
                "blue / red / green), and a physician multi-select. Any filter "
                "change updates every card, chart, and table on the page in "
                "lockstep via a shared dcc.Store. Pages that need different "
                "controls (Workflow's hierarchical diagnosis picker, Billing's "
                "payer-mix controls, Operations' machine chip group) pass "
                "custom children to replace or augment the defaults. Appears "
                "on 17 of the 20 pages.",
            ),
            _screenshot(
                "/assets/topbar.png",
                "Example — Workflow page filter bar with department chips, "
                "physician and diagnosis selects, category / type pickers, "
                "inpatient and weekend switches, outlier caps, smoothing "
                "slider, and the custom date-range preset + slider.",
            ),

            subheading("Census trend plot"),
            body(
                "A time series of \"how many X happened per day / week / month\" "
                "— the most common chart type on the dashboard. Controls, all "
                "clientside so changes are instant:",
            ),
            bullets([
                "Chart type toggle — area (stacked), line, or bar.",
                "Aggregation level — Daily / Weekly / Monthly, applied as a "
                "pandas-style resample, not just a visual collapse.",
                "Smoothing slider — rolling-average window size (0 – 50 days / "
                "weeks / months depending on aggregation).",
                "Series grouping — by department or by physician, colored from "
                "DEPARTMENT_COLORS or the shared chart colorway.",
            ]),
            body(
                "Appears on Home (as a metric card), Operations, Clinic "
                "Visits, Treatment, Courses, Billing, Diagnosis, and "
                "Machine Statistics.",
            ),
            _screenshot(
                "/assets/trend.png",
                "Example — Clinic Visits weekly trend, stacked by category "
                "(Consult / Follow-Up / Re-eval / Virtual). Segmented "
                "controls switch series grouping (Total / Category / Type / "
                "MD / Site / Dx) and aggregation (Weekly / Monthly / Yearly).",
                max_width="620px",
            ),

            subheading("Census cumulative plot"),
            body(
                "A running cumulative count across a single year, overlaid with "
                "prior-year curves in a fading gray spectrum (most recent year "
                "darkest, oldest year lightest). The x-axis is day-of-year (Jan "
                "through Dec with month-start tick labels) so years align "
                "regardless of calendar date; the y-axis is the cumulative "
                "count. The current year uses the purple brand color; prior "
                "years sit behind it as a reference band. Controls:",
            ),
            bullets([
                "Max prior years slider — how many historical years to overlay "
                "(1 to 5).",
                "Projection toggle — extends the current year with a dashed "
                "projection line to end-of-year based on the year-to-date pace.",
                "Chart type toggle and smoothing slider — same as the trend plot.",
            ]),
            body(
                "Appears on Home metric cards (Consultations, Bookings, "
                "Simulations, Treatment Starts) when the \"current year\" "
                "preset is active.",
            ),
            _screenshot(
                "/assets/cumulative.png",
                "Example — Cumulative Visit Volume with the current year "
                "(2026) in brand purple overlaid on three prior years in a "
                "fading gray spectrum. Prior Periods / Slice By and Calendar "
                "/ Rolling toggles switch the comparison basis.",
                max_width="620px",
            ),

            subheading("Flow-Gantt (pipeline visualization)"),
            body(
                "A time-proportional pipeline rendered as a chain of stage "
                "nodes connected by horizontal bands. Node spacing is "
                "proportional to the median (or mean) days between each "
                "stage, so a slow consult-to-sim gap shows up visually as a "
                "wide band — not just a number. Each patient is a horizontal "
                "row across the chain; click one to highlight it and dim the "
                "rest. SVG-native (no Plotly overhead) so per-row click "
                "interactivity scales to thousands of chains.",
            ),
            bullets([
                "Loopback arcs — curved lines below the pipeline that show "
                "backward transitions (Isodose → Draw when contours get "
                "reworked, Review → Sim for a resim). Toggle on / off; top "
                "10 most-frequent pairs rendered.",
                "Hover tooltips — stage counts, pending, cancelled, and "
                "loopback totals at each node; per-patient dates and total "
                "days when hovering a row.",
                "A/B compare mode — splits the view vertically and scales "
                "the two pipelines by total-duration ratio so relative speed "
                "is visible at a glance.",
            ]),
            body(
                "Appears on the Workflow page. The same component is planned "
                "for other pipeline-style views (Tasks, Procedures).",
            ),
            _screenshot(
                "/assets/flowgantt.png",
                "Example — Workflow Flow-Gantt. Band widths between nodes "
                "are proportional to the median inter-stage days; per-stage "
                "counts and % of chains that reached the stage are shown "
                "inside each node. Pending and Cancelled tails on the right "
                "carry the chains that haven't completed (or never will).",
            ),
        ),

        # --- UI patterns --------------------------------------------------
        section(
            "UI patterns and interactions",
            "tabler:layout-grid",
            bullets([
                "Clientside / server split — server renders raw data into a dcc.Store; "
                "clientside callbacks turn that store + user settings into the final figure. "
                "All chart-type switches, smoothing-frac slides, grouping toggles, and rolling-"
                "window changes happen without a server round-trip.",
                "Custom month-granularity date slider (utils/date_slider.py) with preset "
                "buttons — 12mo / 6mo / 3mo / 30d / YTD / all — and two modes: month-bounded "
                "for bar charts and exact-date offsets for time series.",
                "AG Grid dag-funcs (assets/dagfuncs.js) — custom cell renderers, type-to-filter "
                "institution dropdowns, diagnosis category/subcategory dependent dropdowns "
                "backed by the diagnosis taxonomy.",
                "Universal AG Grid null handling — every cell shows an en-dash ('–') for "
                "null/blank/NaN values so blanks never look like loading failures.",
                "Payor Manager modal — full CRUD UI for editing payor mappings, PHDSC "
                "categories, payer-mix multipliers, and the realization factor, with all "
                "changes written straight to SQLite and surviving a server restart.",
                "Page-level help modal (this one) — sidebar nav + tabbed per-page "
                "documentation with script-level and UI-level detail.",
            ]),
        ),

        dmc.Alert(
            color="violet", variant="light",
            title="About this count",
            icon=DashIconify(icon="tabler:info-circle", width=20),
            children=dmc.Text(
                "Front-end line counts are Python + JS + CSS only; they exclude tests, "
                "vendored dependencies, the .data_cache directory, and the docs/ folder.",
                size="xs",
            ),
        ),
    ],
)


# ---------------------------------------------------------------------------
# Tabs definition — consumed by modal.py
# ---------------------------------------------------------------------------

TABS = [
    {
        "value": "frontend",
        "label": "Front-End App",
        "icon": "tabler:device-desktop",
        "content": FRONTEND_CONTENT,
    },
    {
        "value": "backend",
        "label": "Back-End SQL",
        "icon": "tabler:database",
        "content": BACKEND_SQL_CONTENT,
    },
]
