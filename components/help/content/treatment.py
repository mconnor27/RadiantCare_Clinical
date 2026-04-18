"""Treatment page — UI and data-processing help content."""

from __future__ import annotations

import dash_mantine_components as dmc

from ..renderers import body, bullets, section, subheading


UI_CONTENT = dmc.Stack(
    gap="md",
    children=[
        dmc.Text(
            "The Treatment page is the per-session deep dive into what actually "
            "happens on the linacs — technique mix, field counts, image guidance, "
            "session duration, motion management, and new starts. Unlike Operations "
            "(which uses the pre-aggregated Treatment.csv daily rollup), Treatment "
            "reads per-session rows from Treatment-Detail so every KPI, chart, and "
            "table cell can be attributed to a specific patient, plan, machine, "
            "technique, and diagnosis.",
            size="sm", c="dimmed", style={"lineHeight": 1.6},
        ),

        section(
            "What's on this page",
            "tabler:layout-dashboard",
            body(
                "Six KPI cards across the top, eight charts organized in four "
                "half-width rows, and a detail table at the bottom. Every chart has "
                "a data-backed dcc.Store and a clientside re-render path so "
                "smoothing, chart type, and aggregation toggles are instant.",
            ),

            dmc.Space(h="xs"),

            dmc.Text("KPI row (6 cards)", fw=600, size="xs", mb=4),
            bullets([
                "Daily Treatments (avg) — mean of per-day session counts from "
                "Treatment-Detail. This is the canonical throughput number — "
                "Treatment.csv's CompletedAppointments caps at scheduled-appointment "
                "count and diverges on multi-session days.",
                "New Starts (period) — sum of IsNewStart_ByFraction across the "
                "filtered period (one row per first-fraction of a plan).",
                "Unique Patients (avg/day) — distinct PatientId per day, averaged.",
                "Session Time (median) — median SessionElapsedMinutes, filtered to "
                "0 < x ≤ 60 to drop zero-duration rows and obvious sensor errors.",
                "Fields/Session (avg) — mean of FieldCount per session.",
                "Gating Utilization — mean of the FieldGating flag, expressed as a "
                "percentage.",
            ]),
            body(
                "Every KPI shows a trend arrow vs the prior equivalent window and "
                "includes a clientside sparkline.",
            ),

            dmc.Space(h="xs"),

            dmc.Text("Charts", fw=600, size="xs", mb=4),
            bullets([
                "Treatment Volume — area / line / bar over Daily / Weekly / Monthly "
                "/ Yearly, with a Total / Dept / Machine slice toggle and a count "
                "vs % mode.",
                "Cumulative Treatment Volume — running total with prior-period "
                "overlays (calendar or rolling) or a per-slice comparison mode.",
                "Technique Mix — stacked series bucketed to Electron / 3D Conformal "
                "/ IMRT / VMAT / SRS-SBRT / Other. The primary PlanTechniques value "
                "is taken (first comma-separated entry) before bucketing.",
                "Field Type Mix — Arc / Dynamic MLC / Static MLC / Electron over "
                "time.",
                "Duration Distribution — histogram / density of SessionElapsedMinutes "
                "or Beam-On minutes, with a slice toggle (Total / Dept / Machine / "
                "Technique) and a density-smoothing slider.",
                "Image Guidance — CBCT / kV / MV / portal volume over time, with "
                "count / per-session / % sessions modes.",
                "New Starts Trend — by course (first-ever fraction) or by fraction "
                "(first fraction of any plan).",
                "Motion Management — breakdown of gated fields across gating "
                "methods (Breath Hold, Amplitude Based, Phase Based, OSMS) or a "
                "single \"any\" rollup.",
            ]),

            dmc.Space(h="xs"),

            dmc.Text("Detail table", fw=600, size="xs", mb=4),
            body(
                "One row per treatment session — Patient, Date, Machine, Department, "
                "Technique, Fields, Gating, session elapsed time. Column filters "
                "propagate back to the charts and KPIs via the tx-table-filter-rows "
                "store, and a red \"Table Filtered\" badge appears in the filter "
                "bar when column filters are active.",
            ),
        ),

        section(
            "Filters",
            "tabler:filter",
            bullets([
                "Department chips — Lacey / Centralia / Aberdeen, multi-select.",
                "Lacey Machines — when Lacey is in scope, a sub-panel lets you "
                "narrow to TrueBeamNorth or 21EX (Centralia uses 21iX_CEN, Aberdeen "
                "21iX_AB — single-machine sites have no sub-selector).",
                "Physician — multi-select with a Treating / Billing / Consult role "
                "toggle so the same filter can target TreatingPhysician, "
                "BillingPhysician, or ConsultPhysician.",
                "Diagnosis — hierarchical accordion with category + subcategory "
                "checkboxes.",
                "Date preset + date picker + month slider — all three stay in sync. "
                "Default is Prior 12 mo.",
                "Smoothing slider — page-wide LOWESS smoothing default for the "
                "trend charts.",
            ]),
        ),

        section(
            "How the data is processed",
            "tabler:cpu",
            bullets([
                "Data comes from Treatment-Detail.csv (per-session rows). Column "
                "mapping: TreatmentDate→ScheduledDateTime, PatientMRN→PatientId, "
                "PatientName→PatientFullName.",
                "Dates are data-relative — the filter anchors to max(ScheduledDateTime) "
                "in the extract, not wall-clock today.",
                "Technique bucketing takes the first comma-separated value from "
                "PlanTechniques and maps VMAT/IMRT/3D/Electron/SBRT/SRS to display "
                "buckets; anything unmapped becomes \"Other\". SBRT and SRS are "
                "merged into a single SRS/SBRT bucket.",
                "Session-duration filtering clamps SessionElapsedMinutes to "
                "0 < x ≤ 60 for KPI calculation to drop zero-duration and "
                "obvious-error rows (a scheduler-cancelled session left in the "
                "data can otherwise appear as a 24+ hour session).",
                "New Starts are counted two different ways: IsNewStart_ByCourse "
                "(one row per first-ever course fraction for a patient) and "
                "IsNewStart_ByFraction (one row per first-fraction-of-a-plan, which "
                "includes replans and boosts). The KPI uses by-fraction; the New "
                "Starts trend chart lets you switch.",
                "Machine-vs-department logic: when a machine chip is selected, the "
                "page treats it as an additional filter on top of the department "
                "chip. Dept-colored series use the parent-department color; "
                "machine-colored series use the per-machine palette from "
                "config.settings.MACHINE_COLORS.",
                "Server callbacks populate per-chart dcc.Stores; clientside "
                "callbacks read each store plus chart-settings toggles and render "
                "the figure without a server round-trip.",
                "Table column filters propagate back to charts — column filter "
                "state is written to tx-table-filter-rows, which every chart "
                "callback reads as an Input.",
            ]),
        ),

        section(
            "Known quirks and limitations",
            "tabler:alert-triangle",
            bullets([
                "FieldGating values are a 0/1 flag per field; the % metric assumes "
                "the flag is populated consistently across machines. Pre-gating-era "
                "records (rare in current extracts) show 0 rather than null.",
                "Image Guidance counts come from Treatment-Detail's aggregated CBCT / "
                "kV / MV / portal columns, which started receiving CBCT volumetric "
                "data on 2025-10-06. Pre-cutoff records show the older DRR/portal "
                "pattern. See the Operations page help for a full writeup.",
                "Beam-On vs Session duration use different Treatment-Detail "
                "columns — the gap between them represents imaging and inter-field "
                "overhead, not true idle time.",
                "Technique bucketing takes only the primary technique when "
                "PlanTechniques contains multiple entries (e.g., \"VMAT, IMRT\"). "
                "Mixed-technique plans therefore appear once under their dominant "
                "technique, not twice.",
                "Duration Distribution defaults to auto-bandwidth density; the "
                "Density Smoothing slider in the gear menu lets you override.",
            ]),
        ),
    ],
)
