"""Courses page — UI and data-processing help content."""

from __future__ import annotations

import dash_mantine_components as dmc

from ..renderers import body, bullets, section, subheading


UI_CONTENT = dmc.Stack(
    gap="md",
    children=[
        dmc.Text(
            "The Courses page is the course-level lifecycle view — every "
            "prescribed treatment course from consult through completion. "
            "A course may contain multiple plans (initial + boost, replans) "
            "and can span multiple sites or machines; this page tracks the "
            "course as the unit of care, not the individual plan or fraction. "
            "Volume trends, fraction distributions, technique mix, prescription "
            "site patterns, completion / interruption rates, and plan-complexity "
            "metrics all live here.",
            size="sm", c="dimmed", style={"lineHeight": 1.6},
        ),

        section(
            "What's on this page",
            "tabler:layout-dashboard",
            body(
                "Six KPIs, a volume + cumulative pair at the top, then a stack of "
                "distribution and trend charts, and a full course-detail table "
                "at the bottom. Column filters on the table propagate back into "
                "every chart via the courses-table-filter-rows store.",
            ),

            dmc.Space(h="xs"),

            dmc.Text("KPI row (6 cards)", fw=600, size="xs", mb=4),
            bullets([
                "Currently Active — count of courses with ClinicalStatus = ACTIVE.",
                "Started — courses started in the filtered period (by "
                "CourseStartDate).",
                "Completed — courses completed in the filtered period.",
                "Median Fractions — median FractionsPrescribed for courses in the "
                "period.",
                "Median Duration — median TreatmentDurationDays for completed "
                "courses.",
                "Multi-Plan Courses — share of courses with more than one plan "
                "attached (initial + boost, replan, etc.).",
            ]),

            dmc.Space(h="xs"),

            dmc.Text("Charts", fw=600, size="xs", mb=4),
            bullets([
                "Course Volume Trend — bar / line / area with a Total / MD / Site "
                "/ Dx slice toggle and weekly / monthly / yearly aggregation.",
                "Cumulative Course Volume — running total with Prior Periods "
                "(calendar or rolling overlays) or Slice By (per-dimension curves) "
                "modes.",
                "Fractions per Course by Year — ridgeline (density) or histogram "
                "distribution showing how fraction counts have shifted over time "
                "— hypofractionation trends, SBRT uptake.",
                "Median Fractions Trend — median FractionsPrescribed over the "
                "selected period, with the same Total / MD / Site / Dx slicer.",
                "Fractions Distribution — histogram or density of FractionsPrescribed "
                "across the filtered set.",
                "Technique Distribution — stacked series (IMRT / VMAT / 3D / "
                "Electron / SRS-SBRT) over time, in count or percent mode.",
                "Plan Complexity Trends — complexity metrics (MU / cGy, field "
                "count, iso count) by period, with a % / Avg toggle.",
                "Treatment Site Distribution — horizontal bar of the most "
                "prescribed anatomical sites.",
                "Quitting Rate Trend — share of started courses that ended "
                "prematurely (did not reach prescribed fraction count), trended "
                "over time.",
                "Interruption — gap / pause analysis for active courses.",
            ]),

            dmc.Space(h="xs"),

            dmc.Text("Detail table", fw=600, size="xs", mb=4),
            body(
                "One row per course — Patient, CourseId, Start Date, Status, "
                "Treating MD, Technique, Prescribed / Delivered fractions, "
                "Duration (days), Department(s), Machine(s), Diagnosis, "
                "Prescription Site. Column filters feed back into the charts; "
                "CSV export available.",
            ),
        ),

        section(
            "Filters",
            "tabler:filter",
            bullets([
                "Department chips — Lacey / Centralia / Aberdeen, multi-select.",
                "Physician — multi-select with Treating / Consult role toggle.",
                "Diagnosis — hierarchical accordion (category + subcategory).",
                "Status — All / Active / Completed segmented control.",
                "Technique — multi-select chip group.",
                "Date preset + date picker + month slider, all kept in sync. "
                "Anchored to CourseStartDate by default.",
                "Smoothing slider for the trend charts.",
            ]),
        ),

        section(
            "How the data is processed",
            "tabler:cpu",
            bullets([
                "Source: Courses.csv, loaded from Incremental/Courses/ via "
                "_load_incremental() using UniqueRowID for dedup. Column mapping: "
                "CourseStartDateTime→CourseStartDate, Departments→Department "
                "(comma-separated, first value kept).",
                "Multi-site detection: IsMultiSite flag is set when Departments "
                "contains a comma.",
                "Diagnosis handling: DiagnosisCodes may be comma-separated. For "
                "joining to Lookup - Diagnosis, the field is split and exploded; "
                "for the diagnosis filter the primary-category helper "
                "(primary_category / get_categories_for_codes in "
                "utils/diagnosis_categories.py) provides both \"primary\" and "
                "\"all codes\" modes.",
                "Dates are data-relative — the filter anchors to the last "
                "available CourseStartDate, not wall-clock today. Prevents the "
                "page from blanking when an overnight export is delayed.",
                "The active / completed split uses ClinicalStatus for the "
                "explicit column and also supports NoFractionsRemaining == 0 as "
                "a fallback completion signal.",
                "Quitting-rate and interruption calculations exclude courses "
                "that are still active — an in-progress course is neither a "
                "quitter nor a completer, so including them would bias the "
                "numerator.",
                "Server callbacks populate per-chart dcc.Stores "
                "(courses-store-volume, courses-store-cumulative, "
                "courses-store-ridgeline, …); clientside callbacks render "
                "figures from the stores plus chart-settings toggles (chart type, "
                "smoothing, prior-period count, etc.) without a server "
                "round-trip.",
                "Table column filters propagate back to charts — the grid writes "
                "filtered row indices into courses-table-filter-rows, which every "
                "chart callback reads as an Input.",
            ]),
        ),

        section(
            "Known quirks and limitations",
            "tabler:alert-triangle",
            bullets([
                "Departments is a comma-separated field. The page takes the first "
                "value for department filtering — a course that spans Lacey and "
                "Centralia is classified as Lacey. The Multi-Plan Courses KPI "
                "reflects plan fan-out, not site fan-out. See the detail table's "
                "Department(s) column for the full list.",
                "TreatmentDurationDays for active courses is relative to the last "
                "treatment date available, not to completion — expect active "
                "courses to show growing durations as they progress.",
                "Quitting-rate trends can look noisy on short aggregation windows "
                "because a single interrupted course can move the weekly rate by "
                "many percentage points; use monthly or yearly aggregation for "
                "comparison to prior years.",
                "Diagnosis filtering uses either primary-code (first ICD in the "
                "DiagnosisCodes comma list) or all-codes mode — results differ "
                "for courses with multiple diagnoses. Toggle the diagnosis "
                "accordion's mode to compare.",
            ]),
        ),
    ],
)
