"""Referrals page — UI and data-processing help content."""

from __future__ import annotations

import dash_mantine_components as dmc
from dash_iconify import DashIconify

from config.settings import PRIMARY
from ..renderers import body, bullets, section, subheading


UI_CONTENT = dmc.Stack(
    gap="md",
    children=[
        dmc.Text(
            "The Referrals page is the referring-provider intelligence layer: who "
            "sends us patients, from which institutions and specialties, how long "
            "the pipeline takes, and how conversion and lead-times trend. It drives "
            "outreach decisions and identifies pipeline bottlenecks (Created → "
            "Scheduled → Visit). The page combines a structured Referrals extract "
            "(lifecycle / authorization / lead-times) with the Referring physician "
            "directory and consult records from Clinic Visits.",
            size="sm", c="dimmed", style={"lineHeight": 1.6},
        ),

        section(
            "What's on this page",
            "tabler:layout-dashboard",
            body(
                "Sticky header with a two-row filter bar, a 5-card KPI row, a "
                "wide referral pathway Gantt, three linked flow-analysis charts, "
                "a dimension trend + current-vs-prior comparison pair, a volume "
                "/ cumulative volume pair, a full-width referring-provider "
                "origin map, and a full-width detail table. A separate "
                "Referring Physician Manager modal lets you edit provider / "
                "institution / diagnosis metadata with NPI lookup and AI-assist.",
            ),

            dmc.Space(h="xs"),

            dmc.Text("KPI row (5 cards, with sparklines)", fw=600, size="xs", mb=4),
            bullets([
                "Total Referrals — count in period, with trend vs prior window.",
                "Conversion Rate — % of referrals that converted to a completed "
                "first appointment.",
                "Median Days to Appt — Created → First Appt lead time in days. "
                "Trend arrow is inverted (lower is better).",
                "Pending Pipeline (90d) — referrals still open within the "
                "configurable pipeline window (slider: 30–180 days). Shows as "
                "% of total period referrals.",
                "Unique Referring MDs — distinct referring provider count.",
            ]),
            body(
                "Each KPI ships a 12-month monthly sparkline rendered "
                "clientside from a compact JSON store (labels + values + "
                "color). The current partial month is dropped from the "
                "sparkline so the last point isn't artificially short.",
            ),

            dmc.Space(h="xs"),

            dmc.Text("Referral Pathway Gantt", fw=600, size="xs", mb=4),
            body(
                "A wide horizontal flow visualization showing the two pipeline "
                "transitions (Created → Scheduled, Scheduled → Visit) and "
                "their outcomes. Bands are clickable — clicking a band scopes "
                "the three linked charts below (Distribution / Trend / "
                "Conversion) to just that cohort.",
            ),

            dmc.Space(h="xs"),

            dmc.Text("Linked flow charts (three columns)", fw=600, size="xs", mb=4),
            bullets([
                "Duration Distribution — density or histogram of transition "
                "times (days), with a bandwidth slider for KDE smoothing.",
                "Duration Trend — median transition time over time (Weekly / "
                "Monthly / Yearly), Line / Area / Bar.",
                "Conversion Rate Trend — % of the selected cohort that "
                "completed the transition, over time.",
            ]),

            dmc.Space(h="xs"),

            dmc.Text("Dimension Trend + Comparison", fw=600, size="xs", mb=4),
            body(
                "Left: a multi-series trend (ridgeline / area / bar) sliced by "
                "a dimension — Referring MD, Referring Dept, Institution, "
                "Specialty, Diagnosis, or Payor. When Payor is selected, the "
                "grouping unit follows the global Payor mode toggle in the "
                "filter bar (actual / broad / PHDSC). Right: the same dimension "
                "rolled up as a bar chart comparing the current period against "
                "1-N prior periods (Calendar or Rolling window mode).",
            ),

            dmc.Space(h="xs"),

            dmc.Text("Referral Volume + Cumulative", fw=600, size="xs", mb=4),
            bullets([
                "Referral Volume — trend of total referrals with Slice-by "
                "toggle (Total / Ref Dept / Institution / Specialty / "
                "Diagnosis / Site / Payor). The Payor slice respects the "
                "filter-bar Payor mode (actual / broad / PHDSC).",
                "Cumulative Referral Volume — year-to-date cumulative curve, "
                "with Prior-Periods overlay mode (show N prior years for "
                "pace comparison) or Slice-By mode.",
            ]),

            dmc.Space(h="xs"),

            dmc.Text("Referring Provider Origins map", fw=600, size="xs", mb=4),
            body(
                "Mapbox dots at referring physician addresses (geocoded from "
                "DoctorCompleteAddress), sized by patient count and colored by "
                "site. Addresses corrected in the Referring Physician Manager "
                "(manual edits or AI research) override the raw ARIA address "
                "before geocoding, so curated locations plot at the corrected "
                "spot. Same filter overlays as the Patients map — flow lines, "
                "min-count slider, region toggle, site filter.",
            ),

            dmc.Space(h="xs"),

            dmc.Text("Detail table + Referring Physician Manager", fw=600, size="xs", mb=4),
            bullets([
                "Detail table — one row per referral with Created / Scheduled "
                "/ First Appt dates, provider, institution, specialty, "
                "diagnosis, payer, lead-times, status. The Address column "
                "shows the curated address from the Referring Physician "
                "Manager when one exists, falling back to the raw ARIA value. "
                "AG Grid with column filtering; when filters are active a red "
                "badge appears and the KPIs / charts / sparklines reflect the "
                "filtered subset.",
                "Referring Physician Manager modal — three tabs (Providers / "
                "Institutions / Diagnoses) for editing directory metadata. "
                "Includes NPI registry lookup for specialty autofill, AI-"
                "assisted institution research, add-address and mark-reviewed "
                "workflows, and CSV export. The Diagnoses tab pools "
                "rad-onc and med-onc PRCS referrals into a single review "
                "queue: each row carries an Origin badge (rad-onc / medonc / "
                "both) plus separate Rad-Onc and Med-Onc referral counts. "
                "Drilling into a row shows the underlying referrals from "
                "both feeds with a Source column. Mappings written here "
                "flow to the shared diagnosis_overrides DB and immediately "
                "categorize on the Med-Onc Referrals page too.",
            ]),
        ),

        section(
            "Filters",
            "tabler:filter",
            bullets([
                "Date preset + date picker + month RangeSlider (two-way "
                "synced, data-relative to the max of Created date).",
                "Department chips — Lacey / Centralia / Aberdeen. Maps to the "
                "\"Referred to Department\" column which has ~100% site "
                "attribution — we do NOT map the external \"Referred by\" "
                "column to our sites (that column coincidentally contains our "
                "site names ~30% of the time and would mis-attribute).",
                "Specialty select — searchable, populated from ABMS specialty "
                "list.",
                "Diagnosis accordion — ICD-10 categories + subcategories, "
                "cascade resolution (ICD-10 code → free-text \"Rfl Prim Dx\" → "
                "free-text \"Diagnoses\" → clinic-visit diagnosis fallback).",
                "Payor chip-dropdown — multi-select scope to one or more "
                "payors. The mode toggle (Actual / Broad / PHDSC) at the top "
                "of the panel changes both the chip list and how the trend / "
                "volume charts group when sliced by Payor. Actual rolls raw "
                "insurance strings up to standardized payor names via the "
                "shared Payor Manager mapping; Broad collapses to 8 categories "
                "(Medicare, Medicaid, Private, Military/VA, etc.); PHDSC uses "
                "the public-health 8-bucket taxonomy.",
                "Outlier caps — per-transition day caps (Created→Scheduled: "
                "14d, Scheduled→Visit: 28d) to keep a single stalled referral "
                "from pulling the median.",
                "Pipeline Window slider — controls the \"Pending Pipeline\" "
                "KPI's look-back (30–180 days, default 90).",
                "Smoothing slider — shared LOWESS smoothing factor across the "
                "trend charts.",
            ]),
        ),

        dmc.Paper(
            p="md", radius="md", withBorder=True,
            children=[
                dmc.Group(
                    gap="xs", mb="xs",
                    children=[
                        DashIconify(icon="tabler:dna", width=20, color=PRIMARY),
                        dmc.Text("Diagnosis categorization", fw=600, size="sm"),
                    ],
                ),
                dmc.Text(
                    "The referral extract's diagnosis data is messy free text. "
                    "The page runs a four-tier cascade to classify each "
                    "referral into a body-system category:",
                    size="xs", c="dimmed", mb="xs",
                ),
                bullets([
                    "1. Extract an ICD-10 (preferred) or ICD-9 code from the "
                    "\"Diagnoses\" string and look it up against the diagnosis "
                    "categories table.",
                    "2. If no code, apply regex patterns to \"Rfl Prim Dx\" "
                    "(the structured primary-dx field).",
                    "3. If still unresolved, apply the same regexes to the "
                    "free-text \"Diagnoses\" field.",
                    "4. If still unresolved, fall back to the patient's most "
                    "recent clinic-visit diagnosis (matched by MRN to "
                    "PatientId). If nothing matches → \"Other\".",
                ]),
                dmc.Text(
                    "Regex order matters — Sarcomas come before Metastases & "
                    "Palliative (so \"osteoblastoma\" isn't captured by "
                    "\"bone\"), and Mets come before organ-specific categories "
                    "(so \"spine met\" → Mets, not CNS). Typos / misspellings "
                    "are baked into the patterns (\"breat\", \"tounge\", "
                    "\"uret\", etc.) because ARIA free-text is inconsistent.",
                    size="xs", c="dimmed", mt="xs",
                ),
                dmc.Text(
                    "\"Onc Dx\" is a patient-level field (the oncologic "
                    "diagnosis on record), used only as a last-resort safety "
                    "net — it never overrides a referral-specific code or text. "
                    "Because a vague referral (e.g. \"kidney pain\") can hide a "
                    "clear cancer on the Onc Dx, the Diagnosis Manager now "
                    "surfaces the contributing Onc Dx values in their own "
                    "column and raises a \"⚠ Review\" Flag whenever the Onc Dx "
                    "indicates a malignancy but the resolved diagnosis is a "
                    "symptom or benign / non-neoplasm code. Flagged rows are "
                    "for manual review — nothing is recategorized automatically.",
                    size="xs", c="dimmed", mt="xs",
                ),
            ],
        ),

        section(
            "How the data is processed",
            "tabler:cpu",
            bullets([
                "Primary source: load_referrals() reads "
                "Referrals_Report_RadiantCare_All_*.xlsx (a single Excel file, "
                "not incremental). Parquet-cached on first load for performance. "
                "Contains full lifecycle columns — Created, Assigned On, "
                "Authorized On, First Appt, Final Status Date, Days-to-* lead "
                "times, payer, referring provider, referring department, "
                "diagnoses.",
                "Enrichment sources: load_clinic_visits() for consult-level "
                "referring-physician records, load_referring() for the "
                "physician directory (specialty, institution, address, NPI), "
                "and load_diagnosis() for the ICD-10 categories lookup.",
                "Referring physician columns (any column name starting with "
                "\"referring\") are preserved via forward-fill during "
                "incremental dedup in the loader — so a non-null value in an "
                "earlier extract is not overwritten by a null in a later one.",
                "MRN is normalized to a nullable Int64 so it joins cleanly to "
                "PatientId on Clinic Visits.",
                "\"Referred by Department\" is cleaned: \"DO NOT USE - \" "
                "prefix is stripped, known renames are remapped (e.g. "
                "\"PMG SW WA CENTRALIA UROLOGY\" → \"PMG SW WA OLYMPIA "
                "UROLOGY\"), and self-referrals (rows sourced from our own "
                "RadiantCare departments, i.e. \"PRCS ... RADIANTCARE\") are "
                "dropped entirely.",
                "Referring provider credentials (MD, DO, ARNP, PA-C, PhD, "
                "etc.) and suffixes (Jr, III, PT, RN, etc.) are stripped "
                "before matching against the Referring lookup so "
                "\"Smith, John MD\" and \"Smith, John\" resolve to the same "
                "physician.",
                "Geocoding for the provider map uses utils.geocoding with "
                "address-level hashing (_addr_geocode_key) — cached across "
                "sessions.",
                "Prior-period trends use either Calendar-aligned or Rolling "
                "windows (toggle per chart) so a \"30 day\" prior can be "
                "compared to either the previous calendar month or the "
                "preceding 30-day rolling window.",
                "Grid row filters feed KPIs, sparklines, and dependent charts "
                "— but the detail table itself continues to show the full pre-"
                "filter row set so you can always see what's being filtered "
                "out.",
                "No dedicated SQL extract for this page — the referring-"
                "physician cascade is assembled from referral, clinic visit, "
                "simulation, and billing \"referring-*\" columns in the "
                "loader, then enriched from the Referring lookup.",
            ]),
        ),

        section(
            "Known quirks and limitations",
            "tabler:alert-triangle",
            bullets([
                "\"Referred by Department\" has ~30% overlap with our own site "
                "names by coincidence (e.g. an external Centralia clinic). "
                "The page intentionally maps the Department chip filter to "
                "\"Referred TO Department\" (our site) for accurate "
                "attribution, not \"Referred BY\".",
                "The referral file is a snapshot Excel export, not an "
                "incremental feed. Statuses that change after the export don't "
                "show up until the next file lands in the data folder.",
                "Diagnosis categorization is best-effort for free-text rows. "
                "Referrals with no ICD code AND no text match against the "
                "regexes fall into \"Other\" — review the Other bucket "
                "periodically and extend the pattern list if needed.",
                "Referring provider geocoding depends on the address quality "
                "in the Referring lookup. Providers without a full address "
                "(or with PO Boxes) are excluded from the map but remain in "
                "the charts and table.",
                "NPI Registry lookups and AI institution research in the "
                "Referring Physician Manager modal make external calls — "
                "rate-limited and best-effort. Reviewed status is persisted to "
                "the local reviews database.",
                "Lead-time outlier caps are applied before median / mean "
                "calculations, but the raw un-capped values are visible in "
                "the detail table columns so you can sanity-check the outlier "
                "thresholds.",
                "Mapbox map requires MAPBOX_TOKEN in the environment.",
            ]),
        ),
    ],
)
