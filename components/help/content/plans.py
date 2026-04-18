"""Plans page — UI and data-processing help content."""

from __future__ import annotations

import dash_mantine_components as dmc

from ..renderers import body, bullets, section, subheading


UI_CONTENT = dmc.Stack(
    gap="md",
    children=[
        dmc.Text(
            "The Plans page is the plan-level view — one row per treatment plan. "
            "A course can contain several plans (initial + boost, replan, "
            "site-specific plans), so plan counts will always exceed course "
            "counts for the same window. This page tracks fraction progress, "
            "technique mix, session-count distributions, and plan complexity "
            "metrics at the plan granularity.",
            size="sm", c="dimmed", style={"lineHeight": 1.6},
        ),

        section(
            "What's on this page",
            "tabler:layout-dashboard",
            body(
                "Six KPIs, a volume + cumulative pair, a ridgeline / trend / "
                "distribution trio, plus technique, complexity, site, and quitting-"
                "rate panels, then a full plan-detail table. Column filters on the "
                "table propagate back into every chart via the "
                "plans-table-filter-rows store.",
            ),

            dmc.Space(h="xs"),

            dmc.Text("KPI row (6 cards)", fw=600, size="xs", mb=4),
            bullets([
                "Currently Active — plans where NoFractionsRemaining > 0.",
                "Created — plans created in the filtered period (PlanCreationDate).",
                "Completed — plans completed in the filtered period. Completion "
                "uses ClinicalStatus = COMPLETED OR NoFractionsRemaining = 0.",
                "Median Fractions — median NoFractionsPlanned for plans in the "
                "period.",
                "Median Duration — median days from first to last treatment for "
                "completed plans.",
                "Multi-Machine — share of plans whose Machines field contains a "
                "comma (plan delivered on more than one linac).",
            ]),

            dmc.Space(h="xs"),

            dmc.Text("Charts", fw=600, size="xs", mb=4),
            bullets([
                "Plan Volume Trend — bar / line / area with a Total / MD / Site / "
                "Dx slice and weekly / monthly / yearly aggregation.",
                "Cumulative Plan Volume — running total with Prior Periods "
                "(calendar or rolling overlays) or Slice By modes.",
                "Fractions per Plan by Year — ridgeline (density) or histogram "
                "showing how planned-fraction distributions shift year over year "
                "— the clearest view of hypofractionation and SBRT uptake.",
                "Median Fractions Trend — median NoFractionsPlanned over the "
                "selected period, with the same Total / MD / Site / Dx slicer.",
                "Fractions Distribution — histogram or density of "
                "NoFractionsPlanned across the filtered set.",
                "Technique Distribution — stacked series (IMRT / VMAT / 3D / "
                "Electron / SRS-SBRT) over time, count or percent mode.",
                "Plan Complexity Trends — complexity metrics by period with a % "
                "/ Avg toggle.",
                "Treatment Site Distribution — horizontal bar of the most "
                "prescribed anatomical sites.",
                "Quitting Rate Trend — share of started plans that ended before "
                "reaching prescribed fraction count, trended over time.",
            ]),

            dmc.Space(h="xs"),

            dmc.Text("Detail table", fw=600, size="xs", mb=4),
            body(
                "One row per plan — Patient, Course, Plan Name, Created Date, "
                "Status, Technique, Planned / Delivered / Remaining fractions, "
                "% Complete, Duration (days), Department(s), Machine(s), "
                "Prescription Site. Column filters feed back into the charts; "
                "CSV export available.",
            ),
        ),

        section(
            "Filters",
            "tabler:filter",
            bullets([
                "Department chips — Lacey / Centralia / Aberdeen, multi-select.",
                "Physician — single-select with Treating / Consult role toggle "
                "(TreatingPhysician vs ConsultPhysician).",
                "Diagnosis — hierarchical accordion (category + subcategory).",
                "Technique — multi-select chip group (IMRT, VMAT, 3D, Electron, "
                "SRS/SBRT).",
                "Status — All / Active / Completed segmented control.",
                "Fractions range slider — 0 to 50, inclusive. Limits the chart / "
                "table set to plans whose NoFractionsPlanned falls in range.",
                "Date preset + date picker + month slider, all kept in sync.",
                "Date mode — Started / Treated / Completed — selects which plan "
                "date column the date filter anchors to (PlanCreationDate, "
                "FirstTreatmentDate, or completion date).",
                "Smoothing slider for the trend charts.",
            ]),
        ),

        section(
            "How the data is processed",
            "tabler:cpu",
            bullets([
                "Source: Plans.csv, loaded from Incremental/Plans/ via "
                "_load_incremental(). Column mapping: Departments→Department "
                "(comma-separated, first value kept), PatientName→PatientFullName.",
                "DNU plan filter: plans whose PlanName contains \"DNU\" (Do Not "
                "Use) are dropped at load time so planning scratch work doesn't "
                "inflate KPIs.",
                "Derived columns: FractionsDelivered = NoFractionsPlanned − "
                "NoFractionsRemaining, PctComplete is the corresponding ratio, "
                "IsActive is NoFractionsRemaining > 0.",
                "Completion detection is two-signal — ClinicalStatus = COMPLETED "
                "OR NoFractionsRemaining = 0. Some legacy plans carry one signal "
                "without the other.",
                "Multi-machine detection: IsMultiMachine flag is set when "
                "Machines contains a comma.",
                "Dates are data-relative — the filter anchors to the most recent "
                "available date in the selected Date mode column, not wall-clock "
                "today.",
                "Diagnosis handling: DiagnosisCodes may be comma-separated. The "
                "diagnosis filter uses primary_category / get_categories_for_codes "
                "(utils/diagnosis_categories.py) with primary / all-codes modes.",
                "Session-count distributions filter by the Fractions range slider "
                "before aggregation — disengaging the slider clears the filter.",
                "Server callbacks populate per-chart dcc.Stores "
                "(plans-store-volume, plans-store-ridgeline, "
                "plans-store-session-trend, plans-store-session-dist, …); "
                "clientside callbacks render figures from the stores plus "
                "chart-settings toggles without a server round-trip.",
                "Table column filters propagate back to charts via "
                "plans-table-filter-rows.",
            ]),
        ),

        section(
            "Known quirks and limitations",
            "tabler:alert-triangle",
            bullets([
                "Departments / Machines are comma-separated fields. The page takes "
                "the first value for filtering / coloring, so a plan delivered on "
                "both TrueBeamNorth and 21EX is treated as the first-listed "
                "machine. See the detail table's Machines column for the full list.",
                "Median Duration for active plans is relative to the last "
                "available treatment date, not completion — active plans show "
                "growing durations as they progress.",
                "A plan with NoFractionsPlanned = 0 (rare, typically a placeholder) "
                "would produce a div-by-zero in PctComplete; the loader filters "
                "those out upstream but watch for \"N/A\" cells in the detail "
                "table.",
                "The Fractions range slider defaults to [0, 50]. SBRT plans with "
                "very small fraction counts (1–5) and protracted IMRT plans with "
                "30+ fractions live at opposite ends of the distribution — "
                "zooming with the slider is often the fastest way to isolate one "
                "or the other.",
                "The Quitting Rate Trend excludes still-active plans — an "
                "in-progress plan is neither a quitter nor a completer. "
                "Short-aggregation trends (weekly) can be noisy because a single "
                "incomplete plan moves the rate several percentage points.",
            ]),
        ),
    ],
)
