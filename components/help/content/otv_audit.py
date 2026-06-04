"""OTV Audit page — UI and data-processing help content."""

from __future__ import annotations

import dash_mantine_components as dmc
from dash_iconify import DashIconify

from config.settings import PRIMARY
from ..renderers import body, bullets, section, subheading


UI_CONTENT = dmc.Stack(
    gap="md",
    children=[
        dmc.Text(
            "The OTV Audit page tracks weekly treatment-management visit compliance "
            "at the course level. Medicare pays for one OTV (CPT 77427 for "
            "conventional courses, 77431 for 1-2 fraction courses) per set of five "
            "fractions delivered — so each course has an expected OTV count, and "
            "under- or over-billing is a compliance problem. The page surfaces both "
            "directions: Too Few means missed revenue, Extra Visit(s) means billing "
            "risk.",
            size="sm", c="dimmed", style={"lineHeight": 1.6},
        ),

        section(
            "What's on this page",
            "tabler:layout-dashboard",
            body(
                "Sticky header with a two-row filter bar, a 6-tile KPI row, two "
                "charts rows (dept breakdown + trend; distribution donut + failure "
                "breakdown), and a full-width course-level detail table. All "
                "components share a single server callback; when AG Grid column "
                "filters are active, a red \"Table Filtered\" badge appears on the "
                "header and the KPIs / charts automatically reflect the filtered "
                "subset.",
            ),

            dmc.Space(h="xs"),

            dmc.Text("KPI row (6 cards)", fw=600, size="xs", mb=4),
            bullets([
                "Total Courses — count of courses in the filtered range.",
                "Compliance Rate — % of courses where AuditResult is not \"Too "
                "Few\". Color flips from green to amber below 90%.",
                "Extra Visits — count of courses with AuditResult = \"Extra "
                "Visit(s)\". Trend arrow is inverted (more extras is bad).",
                "Too Few Visits — count with AuditResult = \"Too Few\". Trend "
                "arrow inverted.",
                "Avg Discrepancy — mean of (ManagementCPTs_Total − AllowedOTVs) "
                "across non-OK courses. Positive = over-billing, negative = "
                "missed billing.",
                "Missed Revenue — estimated wRVU / allowed dollars left on the "
                "table from Too Few courses, using CMS PFS rates for 77427 / "
                "77431 / 77432 / 77435 with a fallback wRVU table.",
            ]),
            body(
                "Each KPI shows a prior-period trend arrow when a comparable "
                "preset is selected (e.g. \"Prior 3 mo\" compares to the preceding "
                "3-month window).",
            ),

            dmc.Space(h="xs"),

            dmc.Text("Charts", fw=600, size="xs", mb=4),
            bullets([
                "Compliance by Department — stacked bar of OK / Extra / Too Few "
                "per site. Count / % toggle.",
                "Compliance Trend — Line / Area / Bar rate over time, Weekly / "
                "Monthly / Yearly aggregation, with optional smoothing.",
                "Audit Result Distribution — donut of the three audit outcomes.",
                "Failed Cases Breakdown — segmented bar of failures by "
                "Physician / Diagnosis / Fraction count / Fraction mod-5 "
                "(remainder when divided by 5, which is what determines the "
                "Allowed OTV count).",
            ]),

            dmc.Space(h="xs"),

            dmc.Text("OTV Audit Detail table", fw=600, size="xs", mb=4),
            body(
                "One row per course. Columns: Patient, MRN, Department, "
                "Physician, First / Last Treatment Date, Prescribed Fractions, "
                "Allowed OTVs, Actual OTVs (ManagementCPTs_Total), Weekly Exams, "
                "Discrepancy, Audit Result, Course Status. Inline controls "
                "filter to Too Few / Extra only, and to completed courses only. "
                "The \"Completed courses only\" header switch is two-way synced "
                "with the table's course-status toggle.",
            ),
        ),

        section(
            "Filters",
            "tabler:filter",
            bullets([
                "Date preset + picker + month RangeSlider, all two-way synced. "
                "Anchored to the last available LastTreatmentDate (data-"
                "relative).",
                "Department chips — Lacey / Centralia / Aberdeen.",
                "Physician — dropdown of treating or consult physicians (Allen, "
                "Connor, Kahn, Suszko, Tinnel, + others). Physician isn't on the OTV "
                "Audit CSV directly; it's joined from the Courses dataset on "
                "(PatientId, CourseId).",
                "Diagnosis accordion — ICD-10 categories / sub-categories with "
                "primary-dx-only or any-dx match modes.",
                "Fraction RangeSlider — only engages when you drag it off the "
                "min / max endpoints (dims when inactive).",
                "Completed courses only — switch that hides active in-progress "
                "courses (they don't have a final OTV count yet).",
            ]),
        ),

        dmc.Paper(
            p="md", radius="md", withBorder=True,
            children=[
                dmc.Group(
                    gap="xs", mb="xs",
                    children=[
                        DashIconify(icon="tabler:ruler-measure", width=20, color=PRIMARY),
                        dmc.Text("Audit result values", fw=600, size="sm"),
                    ],
                ),
                dmc.Text(
                    "The OTV Audit file uses three values, not PASS/FAIL:",
                    size="xs", c="dimmed", mb="xs",
                ),
                dmc.Table(
                    data={
                        "head": ["Value", "Meaning", "Implication"],
                        "body": [
                            ["OK", "Billed OTV count matches allowed.", "No action needed."],
                            ["Extra Visit(s)", "More OTVs billed than the fraction count supports.", "Over-billing / compliance risk."],
                            ["Too Few", "Fewer OTVs billed than the course allows.", "Missed revenue — re-bill candidate."],
                        ],
                    },
                    striped=True, highlightOnHover=True,
                    withTableBorder=True, withColumnBorders=True, fz="xs",
                ),
                dmc.Text(
                    "The legacy Aug-2021 switchover from CPT 77336 (\"Weekly "
                    "Chart Check\") to 77427 (\"Weekly check oncochart\") can "
                    "make transition-era courses look like Too Few when CPTs "
                    "are partial but weekly exams are complete. The page fixes "
                    "this by using max(ManagementCPTs_ExcludingNC, "
                    "WeeklyExamActivities) as the effective count when flagging "
                    "Too Few.",
                    size="xs", c="dimmed", mt="xs",
                ),
            ],
        ),

        section(
            "How the data is processed",
            "tabler:cpu",
            bullets([
                "Primary source: load_otvs() reads Complete/OTV Audit.csv — a "
                "pre-computed course-level audit. The page applies filters, "
                "joins physician, and recomputes AuditResult for the 2021 "
                "billing transition edge case described above.",
                "Missed-revenue KPI also references Weekly Visits (CPT 77427, "
                "77431, 77432, 77435 billing events from Incremental/WeeklyVisits) "
                "to value Too Few courses at the CPT PFS rate for their missing "
                "OTVs. A fallback wRVU / malpractice / facility-total table is "
                "used if PFS lookup fails.",
                "Physician is joined from load_courses() on (PatientId, "
                "CourseId) — OTV Audit has no physician column. The physician-"
                "role segmented control switches between TreatingPhysician and "
                "ConsultPhysician from the Courses join.",
                "\"Completed courses only\" joins against the same completion "
                "logic used on the Courses page (PatientId|CourseId composite "
                "key) so the two pages stay consistent.",
                "Department filter only narrows when a subset is selected — "
                "when all three are on (or none are), rows with a missing "
                "Department still pass through.",
                "Prior-period trend arrows use calendar-aligned prior windows "
                "(e.g. Prior 3 mo → the 3 months before the current 3-mo "
                "window) so the KPI comparison is apples-to-apples.",
                "Date anchor is the max of LastTreatmentDate — data-relative, "
                "not wall-clock now.",
            ]),
        ),

        section(
            "Known quirks and limitations",
            "tabler:alert-triangle",
            bullets([
                "A course only gets an accurate audit once treatment has "
                "finished. Active courses are flagged but included by default; "
                "toggle \"Completed courses only\" to exclude them.",
                "Allowed OTV count is derived from PrescribedFractions in the "
                "source audit. If the prescription is amended mid-course (e.g. "
                "boost added) the audit may flag a fraction-count mismatch that "
                "isn't a real billing problem — these usually resolve once the "
                "course finalizes.",
                "Missed-revenue estimates are Medicare allowed-amount "
                "projections based on CMS PFS, not actual contracted rates. "
                "Treat as order-of-magnitude, not a collections forecast.",
                "The physician join uses (PatientId, CourseId); if Courses "
                "doesn't have a matching record the row shows blank for "
                "physician and drops out of physician-filtered views.",
                "When AG Grid column filters are active the KPIs, charts, and "
                "breakdowns use the filtered row set but the table itself "
                "reflects the pre-filter server state — watch for the red "
                "\"Table Filtered\" badge on the header.",
            ]),
        ),
    ],
)
