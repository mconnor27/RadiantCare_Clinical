"""Workflow page — UI and data-processing help content."""

from __future__ import annotations

import dash_mantine_components as dmc

from ..renderers import body, bullets, section, subheading


UI_CONTENT = dmc.Stack(
    gap="md",
    children=[
        dmc.Text(
            "The Workflow page visualizes the external-beam (EBRT) consult-to-"
            "treatment pipeline end to end. Each patient's care traverses up to "
            "seven stages — Exam, Simulation, Draw Volumes, Contour Review, "
            "Isodose Plan, Review Plan, and First Fraction — and this page "
            "quantifies how long each gap takes, where loopbacks (resims, "
            "replans) are happening, and how recent trends compare with "
            "historical medians. Brachytherapy and Pluvicto / radiopharmaceutical "
            "courses are filtered out at load time because they don't follow the "
            "sim-and-plan workflow this page is built for.",
            size="sm", c="dimmed", style={"lineHeight": 1.6},
        ),

        section(
            "What's on this page",
            "tabler:layout-dashboard",
            body(
                "The page is filter-heavy and chart-dense. Unlike the other pages "
                "it has no traditional KPI row — stage counts, pending, cancelled, "
                "and loopback counts are embedded directly in the Flow-Gantt's "
                "hover tooltips instead.",
            ),

            dmc.Space(h="xs"),

            dmc.Text("Filter bar (sticky header)", fw=600, size="xs", mb=4),
            bullets([
                "Date preset + slider + manual range — anchored to exam date.",
                "Department chips (Lacey / Centralia / Aberdeen).",
                "Physician — single-select; pulls the list from Exam rows only.",
                "Technique — multi-select Electron / 3D / IMRT / VMAT / SBRT / SRS.",
                "Diagnosis — hierarchical picker with a Primary / All mode toggle and "
                "expandable category + subcategory checkboxes.",
                "Aggregation toggle — Median (default) or Mean for inter-stage gaps.",
                "Business Days switch — if on, weekends and after-hours are "
                "subtracted using a 5-day / 9-hour-per-day (8 AM–5 PM) calendar; "
                "if off, calendar days are used.",
                "Loopbacks switch — include or exclude workflow chains with "
                "StageOccurrence > 1 (resims, replans).",
                "Inpatient switch — include or exclude inpatient consults.",
                "Outlier caps panel — None / Default presets plus per-gap sliders "
                "(0–120 days). Drops chains where an individual gap exceeds the cap.",
            ]),

            dmc.Space(h="xs"),

            dmc.Text("Charts", fw=600, size="xs", mb=4),
            bullets([
                "Flow-Gantt (full-width) — the pipeline as a chain of stage nodes, "
                "with inter-node spacing proportional to the median (or mean) days "
                "for each gap. Hover any node to see total chains, pending, cancelled, "
                "and loopback counts at that stage. Loopback arcs render on top for "
                "the top 10 most frequent backward transitions (e.g., Isodose → Draw "
                "when contours get reworked).",
                "Stage Duration Distribution — histogram or density view of the "
                "days-between for a selectable stage pair. Kaplan-Meier adjust "
                "switch handles right-censored chains (patients still in progress); "
                "smoothing control for the density curve.",
                "Duration Trend — time series of the median / mean gap by exam date "
                "for the chosen stage pair. Maturity legend distinguishes points "
                "with ≥50% completion (filled circles) from <50% (hollow circles) "
                "so you can see where the most recent values are still maturing.",
            ]),

            dmc.Space(h="xs"),

            dmc.Text("Detail table (bottom of page)", fw=600, size="xs", mb=4),
            body(
                "One row per workflow chain — Consult (exam date), Patient, Dept, "
                "Physician, Sim date, days-to-sim, Draw, Isodose, Review, First Tx "
                "date, Total Days, Status (Complete / In Progress). Row selection "
                "filters the charts above; CSV export available.",
            ),
        ),

        section(
            "How inter-stage gaps are computed",
            "tabler:ruler-measure-2",
            body(
                "Each gap is the duration from the prior stage's completion to the "
                "next stage's completion. The Workflow_Events extract pre-computes "
                "a BaselineDateTime column for each non-Exam stage so the front end "
                "doesn't have to re-derive it.",
            ),

            subheading("Baseline resolution, per stage"),
            bullets([
                "Simulation_baseline → Exam date (consult).",
                "Draw Volumes_baseline → task creation time "
                "(from DimActivityTransactionHistory) if present; else sim's "
                "ActivityEndDateTime; else sim's ScheduledEndTime; else the draw "
                "task's own StartDateTime. Creation-time is preferred because "
                "replans and new care paths often assign Draw before the sim "
                "actually ends.",
                "Contour Review_baseline → Draw Volumes completion.",
                "Isodose Plan_baseline → Contour Review completion (preferred) or "
                "Draw Volumes completion as fallback.",
                "Review Plan_baseline → Isodose completion.",
                "First Fraction_baseline → Review Plan completion.",
            ]),

            subheading("Duration formula"),
            body(
                "For each (chain, stage) pair: "
                "days = StageEndDateTime − BaselineDateTime. "
                "Returned as a float in either calendar or business days depending "
                "on the Business Days filter. Business-day mode uses a vectorized "
                "numpy calendar (5 days/week, 9 hours/day, 8 AM–5 PM), not a plain "
                "weekend-skip — an eligibility gap that starts Friday at 4 PM and "
                "ends Monday at 9 AM counts as ~1 business hour, not 0.",
            ),

            subheading("Outlier capping"),
            body(
                "Each gap has its own cap (consult→sim default 21, sim→contour "
                "default 8, contour→plan 8, plan→review 5, review→tx 8, SRS draw "
                "7 — from config/settings.OUTLIER_CAPS). Chains with any gap "
                "exceeding the cap are excluded from the distribution and trend "
                "charts to prevent long-tail outliers from skewing medians. The "
                "cap panel in the filter bar lets you adjust or disable caps per-"
                "gap; the Flow-Gantt uses the filtered set so apparent medians "
                "match what's on the other two charts.",
            ),
        ),

        section(
            "How chains are assembled",
            "tabler:link",
            bullets([
                "The pivot uses UniqueRowID (= ExamActivityTransactionID) as the "
                "chain key. One row per workflow chain, with each stage's "
                "datetime, status, and baseline in its own column.",
                "Department, Physician, and Diagnosis only exist on Exam rows in "
                "the source data. They're forward-filled to the rest of the "
                "chain via a DimCourseID merge (preferred) with PatientId as "
                "fallback.",
                "Loopback-aware filtering: when the Loopbacks switch is OFF, the "
                "pivot enforces StageOccurrence = 1 (first occurrence only of "
                "each stage in each chain). When ON, every occurrence is kept and "
                "rendered as a separate contributor to the duration distribution.",
                "Chains with gap holes (e.g., Sim but no Draw, then Isodose "
                "appears later) are dropped — the pivot requires consecutive non-"
                "null stages for any gap to be counted.",
                "Kaplan-Meier adjustment on the distribution and trend charts "
                "treats chains with no final stage as right-censored rather than "
                "excluded, reducing the bias that would otherwise make recent "
                "months look artificially fast (because only the quick-through "
                "chains have reached their final stage in time).",
            ]),
        ),

        section(
            "Server-to-clientside split",
            "tabler:transfer",
            body(
                "The server callbacks load the full Workflow_Events extract, apply "
                "filters (dept, physician, technique, diagnosis, inpatient, "
                "loopbacks, date range), pivot to chain-level, compute flow / "
                "distribution / trend, and write the results into a dcc.Store. "
                "Clientside callbacks then render the three charts from the store "
                "plus the UI toggles (aggregation, KM, smoothing, chart type). "
                "Changing a toggle is instant — no server round-trip.",
            ),
        ),

        section(
            "Known quirks and limitations",
            "tabler:alert-triangle",
            bullets([
                "EBRT-only. Chains where ModalityType resolves to BRACHYTHERAPY or "
                "PLUVICTO are dropped at load time (see _EXCLUDED_MODALITIES in "
                "pages/workflow.py). Rows with a null ModalityType are kept — they're "
                "usually unresolved-modality consults that either later become EBRT "
                "or haven't reached a sim yet. Use the Procedures page for brachy "
                "and Pluvicto workflows.",
                "Open stages — where StageDateTime is in the future — are excluded "
                "from duration calculations even though they appear in the raw "
                "Workflow_Events extract. Pending counts track them for the "
                "Flow-Gantt hover tooltip but don't contribute to medians.",
                "Cancelled and deleted stages are filtered out during load.",
                "The pivot groups on UniqueRowID so multiple simultaneously-"
                "assigned physicians on a Contour Review (common for peer review) "
                "don't fan the chain out into N duplicate rows. Per-physician "
                "Contour Review attribution lives on the Tasks page instead.",
                "The detail table uses first-occurrence for each stage; if you "
                "need replan dates, enable Loopbacks and inspect the Flow-Gantt's "
                "arcs for the paired backward transitions.",
            ]),
        ),
    ],
)
