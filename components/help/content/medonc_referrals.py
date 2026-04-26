"""Referrals (MedOnc) page — UI and data-processing help content."""

from __future__ import annotations

import dash_mantine_components as dmc
from dash_iconify import DashIconify

from config.settings import PRIMARY
from ..renderers import body, bullets, section, subheading


UI_CONTENT = dmc.Stack(
    gap="md",
    children=[
        dmc.Text(
            "The Referrals (MedOnc) page answers a clinical-operations question "
            "that no single ARIA report can: of the patients referred to PRCS "
            "medical oncology at the five sites (Lacey, Centralia, Aberdeen, "
            "Yelm, Shelton), how many are actually seen, how many reach rad-"
            "onc, when, and for which diagnoses? Gaps between the expected and "
            "observed rad-onc conversion rate flag potential under-referral. "
            "The page joins a Med-Onc Referrals Excel export (by MRN) against "
            "RadiantCare's rad-onc referrals, consults, and treatment records.",
            size="sm", c="dimmed", style={"lineHeight": 1.6},
        ),

        section(
            "What's on this page",
            "tabler:layout-dashboard",
            body(
                "Sticky header with a filter bar + \"Table Filtered\" warning "
                "badge, a 5-card KPI row with sparklines, a full-width Med-Onc "
                "→ Rad-Onc pathway Flow-Gantt, three linked companion charts "
                "(Duration Distribution / Duration Trend / Conversion Rate "
                "Trend), a tall Rad-Onc Conversion by Diagnosis horizontal bar "
                "chart paired on the right with Site Conversion and a KM-style "
                "cumulative-incidence curve, and a collapsible patient-detail "
                "accordion table whose column filters propagate back into every "
                "chart.",
            ),

            dmc.Space(h="xs"),

            dmc.Text("KPI row (5 cards, with 12-mo sparklines)", fw=600, size="xs", mb=4),
            bullets([
                "Unique Patients — distinct MRN count in the cohort.",
                "Seen by Med-Onc — count with First Appt recorded. Sublabel "
                "shows % of referred.",
                "Reached Rad-Onc (Any Stage) — count seen-AND-linked to "
                "rad-onc. Sublabel: % of Seen.",
                "Treated by Rad-Onc — count seen-AND-treatment-started. "
                "Sublabel: % of Seen.",
                "Median Days → Rad-Onc — median DaysToRadOnc for linked "
                "seen patients.",
            ]),
            body(
                "The denominator across all rad-onc KPIs is deliberately "
                "\"Seen by Med-Onc\", not total referred, so the metric "
                "isolates med-onc physicians' referral-out behavior from "
                "med-onc's own show-rate.",
            ),

            dmc.Space(h="xs"),

            dmc.Text("Med-Onc → Rad-Onc Pathway Flow-Gantt", fw=600, size="xs", mb=4),
            body(
                "Four-stage time-proportional pipeline: Created → Scheduled "
                "→ Med-Onc Appt → Rad-Onc (Contact or Referral — label "
                "follows the top Linkage toggle). Stage masks are cumulative, "
                "so each stage's count is bounded by its predecessor's. "
                "Percentages are denominated by the seen-by-med-onc count "
                "(stage 2), so the final bar reads as \"% of seen\"; the "
                "earlier Created/Scheduled stages will render as >100% of "
                "that base, correctly conveying the in-flow of referrals "
                "into med-onc.",
            ),

            dmc.Space(h="xs"),

            dmc.Text("Linked companion charts (three columns)", fw=600, size="xs", mb=4),
            bullets([
                "Duration Distribution — density (KDE) or histogram of the "
                "selected transition's days, with a bandwidth slider. When "
                "nothing is selected, shows the total Created → Rad-Onc Ref "
                "pipeline duration.",
                "Duration Trend — median transition days over Weekly / "
                "Monthly / Yearly periods (default: area, smoothing 7).",
                "Conversion Rate Trend — when no band is selected, stacks "
                "three cumulative-from-Created rates on one chart (Created "
                "→ Scheduled, → Seen, → Rad-Onc Ref) so the full funnel "
                "retention is visible over time. Click a band to drop into "
                "the stage-specific inter-stage rate.",
            ]),

            dmc.Space(h="xs"),

            dmc.Text("Conversion by Diagnosis + Site, KM curve", fw=600, size="xs", mb=4),
            bullets([
                "Rad-Onc Conversion by Diagnosis — tall horizontal bar "
                "chart, one pair per dx category (Reached Rad-Onc / Treated "
                "by Rad-Onc), denominated by Seen by Med-Onc.",
                "Conversion by Med-Onc Site — same metric broken out across "
                "Lacey / Centralia / Aberdeen / Yelm / Shelton, site-colored.",
                "Cumulative Rad-Onc Contact Over Time — Kaplan-Meier-style "
                "cumulative-incidence curve. Segmented control switches "
                "stratification (Total / Diagnosis / Site). Estimator is "
                "naive (n_events_by_t / n_total_seen) rather than censoring-"
                "adjusted, so the final plateau equals the Flow-Gantt's "
                "stage-4 proportion exactly — the page's two endpoints "
                "reconcile.",
            ]),

            dmc.Space(h="xs"),

            dmc.Text("Patient detail table (accordion)", fw=600, size="xs", mb=4),
            bullets([
                "One row per MRN, collapsed by default. Columns: MRN, "
                "Patient, Med-Onc Ref date, Site, Dx Category, Onc "
                "Diagnosis, Referred by Dept / Provider, Seen by Med-Onc, "
                "rad-onc ref / consult / tx-start dates, Days → Rad-Onc, "
                "Linked flag. Export CSV and Clear Filters buttons float "
                "over the accordion header so clicks don't toggle it.",
                "When the user sets AG Grid column filters, a red \"Table "
                "Filtered\" badge appears on the filter bar and the entire "
                "page (KPIs, Flow Gantt, companion charts, KM) recomputes "
                "over the filtered row subset. Click the badge to scroll "
                "to the table; click Clear Filters (or change a page "
                "filter) to reset.",
            ]),
        ),

        section(
            "Filters",
            "tabler:filter",
            bullets([
                "Cohort Period — segmented control (12 Mo / 24 Mo / 3 Yr / "
                "5 Yr / YTD / All). Default: All.",
                "Linkage toggle — Any Rad-Onc Contact vs. Referred by "
                "Med-Onc. \"Any\" counts any rad-onc referral / consult / "
                "treatment in the linkage window. \"Referred by Med-Onc\" "
                "restricts to rad-onc referrals whose source is one of the "
                "five PRCS med-onc departments (regex-matched on Referred "
                "by Department), and gates treatment-linkage on having "
                "that referral. The Flow Gantt's terminal stage and the "
                "KM event definition both follow this toggle so the page "
                "self-reconciles.",
                "Med-Onc Site — compact dropdown chip group, multi-select "
                "across the five PRCS sites; collapses to \"N sites\" when "
                "more than one is picked.",
                "Diagnosis accordion — ICD-10 categories + subcategories. "
                "Match is against the derived DxCategory (not the raw ICD "
                "code) because this page's category signal is cascaded from "
                "free-text fields.",
                "Outlier caps — per-transition day caps for the first two "
                "transitions (Created → Scheduled: 14d, Scheduled → Appt: "
                "30d). The third transition (Appt → Rad-Onc Ref) uses a "
                "fixed 180-day visualization cap — deliberately decoupled "
                "from the linkage window so a 10-year linkage bound doesn't "
                "flatten the distribution into a spike at 0.",
                "Linkage Window — two sliders. Pre-days (how far back rad-"
                "onc contact can precede med-onc referral, default 60d) and "
                "post-days (how far forward, default 10 years). Pre-window "
                "is non-zero because rad-onc contact legitimately predates "
                "med-onc in palliative-RT-first, concurrent chemoRT, and "
                "paperwork-ordering edge cases.",
            ]),
        ),

        dmc.Paper(
            p="md", radius="md", withBorder=True,
            children=[
                dmc.Group(
                    gap="xs", mb="xs",
                    children=[
                        DashIconify(icon="tabler:transfer-in", width=20, color=PRIMARY),
                        dmc.Text("Linkage logic", fw=600, size="sm"),
                    ],
                ),
                dmc.Text(
                    "Each med-onc cohort patient is joined by MRN to three "
                    "rad-onc signals and assigned a composite linkage flag:",
                    size="xs", c="dimmed", mb="xs",
                ),
                bullets([
                    "RadOncReferralCreated — earliest rad-onc Referral "
                    "Created for this MRN (earliest med-onc-sourced ref in "
                    "\"Referred by Med-Onc\" mode).",
                    "RadOncFirstAppt — First Appt on that rad-onc referral.",
                    "RadOncTreatmentStart — earliest ScheduledDateTime from "
                    "Treatment Detail for this MRN.",
                    "A contact is \"linked\" if the earliest of the three "
                    "falls within the [-pre, +post] days window around the "
                    "med-onc referral's Created date. DaysToRadOnc is the "
                    "signed offset when linked.",
                    "In Referred-by-Med-Onc mode, treatment-linkage is "
                    "additionally gated on the patient having a rad-onc "
                    "referral from PRCS med-onc — so a patient treated "
                    "via some other path doesn't get credited to med-onc.",
                ]),
            ],
        ),

        section(
            "How the data is processed",
            "tabler:cpu",
            bullets([
                "Primary source: load_medonc_referrals() reads Referrals_"
                "Report_PRCS_*.xlsx from DATA_DIR. Parquet-cached on first "
                "load. Distinct from the rad-onc Referrals_Report_"
                "RadiantCare_All_*.xlsx the Referrals page uses — the two "
                "feeds are disambiguated purely by filename prefix.",
                "Pre-filter: rows with no oncologic diagnosis (Onc Dx = "
                "\"No onc dx\" or null) are dropped, and self-referrals "
                "(rows sourced from one of the five PRCS med-onc "
                "departments or from RadiantCare) are dropped — they "
                "aren't true cross-referrals and would distort metrics.",
                "DxCategory is derived from a four-field cascade (ICD code "
                "in Diagnoses → Rfl Prim Dx text → Diagnoses text → Onc Dx "
                "text) using the same utils.diagnosis_categories helper as "
                "the rad-onc Referrals page, so the two pages' diagnosis "
                "rollups are comparable.",
                "Cohort collapses multiple referrals per patient to one "
                "row — the earliest med-onc referral in the filter window.",
                "SeenByMedOnc = First Appt is not null. All rad-onc "
                "conversion percentages are denominated by this.",
                "Rad-onc referrals in \"Referred by Med-Onc\" linkage mode "
                "are filtered by regex on Referred by Department: "
                "PRCS\\s+(LACEY|CENTRALIA|ABERDEEN|YELM|SHELTON). Only "
                "referrals whose source is one of the five PRCS med-onc "
                "departments count — external Medical Oncology groups "
                "(WSP, SFH Swedish, SCCA) are intentionally excluded.",
                "Cohort's pandas index is reset to 0..N-1 after filtering "
                "so _row_idx stamped on the detail-grid rows maps 1:1 back "
                "to the cohort via _apply_grid_row_filter. A clientside "
                "listener on the grid's virtualRowData updates the filter-"
                "rows store whenever column filters change.",
                "KM cumulative-incidence curves use a naive estimator "
                "(running n_events / n_total), not the censoring-adjusted "
                "Kaplan-Meier estimator. This is a deliberate choice: it "
                "keeps the KM plateau numerically equal to the Flow Gantt's "
                "stage-4 proportion so the two endpoints reconcile. Curves "
                "extend horizontally past the last observation up to the "
                "linkage-window cap so the x axis always spans the "
                "configured follow-up window.",
                "PHI pipeline: scripts/sanitize.py has a dedicated "
                "sanitize_medonc_referrals() rule that drops Patient Name "
                "and DOB, hashes MRN with the same 52-bit SHA-256 stable "
                "hash used for the rad-onc feed (so joins survive across "
                "datasets), and derives AgeAtReferral from DOB + Created "
                "before dropping. Keyed off the PRCS filename prefix so "
                "the two xlsx feeds stay separable.",
            ]),
        ),

        section(
            "Known quirks and limitations",
            "tabler:alert-triangle",
            bullets([
                "Referred to Provider on the med-onc feed (who the patient "
                "was assigned to at the PRCS site) is populated on only "
                "~21% of seen rows — too sparse for reliable per-provider "
                "under-referral analysis, which is why this page shows "
                "site-level conversion but not provider-level.",
                "Diagnosis cascade relies on free-text fields; referrals "
                "with no ICD code AND no text match fall into \"Other\" or "
                "\"Unknown\" (the latter is excluded from charts). The "
                "categorizer logic and regex list are shared with the "
                "rad-onc Referrals page — extensions improve both pages. "
                "Medonc-only ICD codes and free-text diagnoses (i.e. those "
                "never seen in rad-onc referrals) are surfaced for "
                "classification in two places: the Diagnoses tab of the "
                "rad-onc Referring Physician Manager modal and the mobile "
                "Mappings page. Each row there is tagged with an origin "
                "badge (rad-onc / medonc / both); mappings written through "
                "either UI immediately propagate back to this page via the "
                "shared diagnosis_overrides DB.",
                "~40% of rad-onc referrals for patients in this cohort "
                "have a blank Referred by Department (external referrals "
                "from outside Providence). In \"Referred by Med-Onc\" "
                "mode those rows are excluded; in \"Any\" mode they still "
                "count as linkage. The gap between the two modes for the "
                "same cohort is one of the most interesting signals on "
                "the page.",
                "Flow Gantt percentages >100% on the Created/Scheduled "
                "stages are intentional under the \"denominator = seen\" "
                "rule — they convey how many referrals flow in to med-onc "
                "relative to how many result in a kept appointment.",
                "Med-Onc Referrals xlsx is a manual export (not an ARIA "
                "Report Builder feed), so it lags more than the other "
                "datasets. Fresh data requires a fresh Excel pull.",
                "Appt → Rad-Onc Ref duration is capped at 180 days for "
                "the distribution / median charts regardless of the "
                "linkage window. The KM curve uses the full linkage "
                "window for cumulative incidence — they answer different "
                "questions (operational-pipeline timing vs. eventual-"
                "conversion rate).",
            ]),
        ),
    ],
)
