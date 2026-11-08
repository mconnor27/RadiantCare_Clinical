"""Tasks page — UI and data-processing help content."""

from __future__ import annotations

import dash_mantine_components as dmc

from ..renderers import body, bullets, section, subheading


UI_CONTENT = dmc.Stack(
    gap="md",
    children=[
        dmc.Text(
            "The Tasks page tracks physician and staff task workload — Dosi "
            "Prep, Draw Volumes, SRS contouring, Contour Review, Isodose Plan, "
            "Review Plan, Sign Plan/Rx and Physics QA — against their SLA "
            "deadlines. Source data is the ARIA Tasks "
            "extract; the Physician Schedule extract provides cross-reference "
            "data for identifying after-hours and off-day work.",
            size="sm", c="dimmed", style={"lineHeight": 1.6},
        ),

        section(
            "What's on this page",
            "tabler:layout-dashboard",
            body(
                "An 8-tile KPI row (one card per task type, each clickable to "
                "filter the rest of the page), a full-width Open Tasks per Day "
                "workload chart, six chart cards across three rows, and a "
                "full-width detail table. The clickable KPI cards "
                "act as a quick way to drill into a single task type without "
                "opening the task-type filter panel.",
            ),

            dmc.Space(h="xs"),

            dmc.Text("KPI row (8 clickable group cards)", fw=600, size="xs", mb=4),
            bullets([
                "Dosi Prep — dosimetry prep after sim, timed from sim end "
                "(standard since 2026-05-18).",
                "Draw — Draw Volumes tasks.",
                "SRS — SRS-specific contouring tasks.",
                "Contour — Contour Review tasks.",
                "Isodose — Isodose Plan tasks.",
                "Review — Review Plan tasks.",
                "Sign Plan/Rx — the MD's plan and prescription sign-off (older "
                "courses: separate Sign Plan and Sign Rx tasks), timed from "
                "Review Plan completion.",
                "Physics QA — one physics sign-off per course: Check Plan "
                "Physics (3D) or Sign IMRT Verification (IMRT), timed from "
                "Review Plan completion, so IMRT acquisition and analysis fall "
                "inside it.",
            ]),
            body(
                "Each card shows count, median time to complete, SLA compliance, "
                "and a sparkline. Clicking a card sets the task-type filter to "
                "that single type; clicking again clears the selection.",
            ),

            dmc.Space(h="xs"),

            dmc.Text("Charts", fw=600, size="xs", mb=4),
            bullets([
                "Open Tasks per Day — the workload backlog: how many tasks were "
                "open at the end of each weekday. A task is open from when it "
                "became actionable (its prior step finished — the same start "
                "point actual time uses) until it was completed; tasks still "
                "waiting on their prior step aren't counted. With outlier caps "
                "on, a task counts for at most its cap's worth of days before "
                "it closed, so a stale prior-step timestamp can't add a task to "
                "every day for years. Daily, or Weekly / Monthly as the average "
                "daily backlog. Slice by Total, Task, MD, Planner, or Dx. "
                "Ignores the Status filter, since Completed-only would erase "
                "the current backlog.",
                "Task Volume Trend — bar / line / area, weekly / monthly / "
                "yearly. Slice by Total, Task type, MD, Planner, or Diagnosis "
                "body site. Smoothing slider.",
                "Cumulative Task Volume — running total with Prior Periods "
                "overlay and projection option. Calendar or rolling period "
                "windows. Count / Actual Time / Allowed Time switches what "
                "accumulates: number of tasks, summed MinutesToComplete on "
                "completed tasks (outlier caps apply), or summed "
                "MinutesAllowed (Isodose and tasks without an allowed time "
                "excluded). Time is shown in hours, or days for larger "
                "totals. Note this is summed turnaround time, not hands-on "
                "effort.",
                "Time Distribution — histogram or density of MinutesToComplete "
                "(Actual) or MinutesAllowed (Allowed, the SLA; Isodose tasks "
                "and tasks without an allowed time are excluded). Slice by "
                "Task, MD, or Planner. The stats line shows Total — the sum "
                "of every task's time in the distribution. Density mode "
                "exposes a bandwidth slider.",
                "Actual vs Allowed Time — comparison of MinutesToComplete "
                "against MinutesAllowed (the SLA threshold) per task, MD, or "
                "planner.",
                "Time to Complete Trend — median completion time over time, "
                "sliceable by task / MD / planner / body site.",
                "On-Time Trend — percentage of tasks meeting SLA over time.",
            ]),

            dmc.Space(h="xs"),

            dmc.Text("Task Detail table", fw=600, size="xs", mb=4),
            body(
                "One row per task — Start Date, Due Date, Completed Date, "
                "Patient, Task Type, Assigned MD, Completing MD, Minutes to "
                "Complete, SLA minutes, On-Time flag, After-Hours flag. "
                "Collapsible accordion; sortable, column-filterable, CSV export.",
            ),
        ),

        section(
            "Filters",
            "tabler:filter",
            bullets([
                "Date preset + slider + manual DatePickerRange — anchored to "
                "StartDateTime.",
                "Physician — single-select. Drawn from a known-MD list rather "
                "than raw AssignedMD values so residents and admin accounts "
                "stay out of the picker.",
                "Staff — single-select. Who completed the staff tasks (Dosi "
                "Prep, Isodose Plan, Physics QA). Shown when those task types "
                "are in scope; those tasks are credited to the completing "
                "staff member rather than an MD.",
                "Task type — multi-select (Dosi Prep, Draw Volumes, SRS "
                "contouring, Contour Review, Isodose Plan, Review Plan, Sign "
                "Plan/Rx, Physics QA), matched by ActivityName.",
                "Status — Completed / Open / All (Open = CompletingMD is null).",
                "Time — narrows every KPI, chart and the table to tasks whose "
                "Actual time (MinutesToComplete, following the Business Hours "
                "switch) or Allowed time (MinutesAllowed, the SLA) falls in a "
                "range from 0 to 21 days or more. Allowed leaves out Isodose "
                "tasks and tasks with no allowed time; an active Actual range "
                "leaves out open tasks, which have no actual time yet. This is "
                "a row filter, unlike the per-task outlier caps, which only "
                "trim the long tail out of time statistics.",
                "Business hours switch — restrict counts and SLA to 8 AM – 5 PM "
                "weekdays only, or include 24×7 activity.",
                "Smoothing slider — shared across trend charts.",
            ]),
        ),

        section(
            "How the data is processed",
            "tabler:cpu",
            bullets([
                "Source loader is load_tasks() which reads from Complete/Tasks.csv "
                "(a single non-incremental file). PatientName is normalized to "
                "PatientFullName at load time.",
                "Task type lives in the ActivityName column (the source doesn't "
                "have a separate TaskType column) — classification is "
                "case-insensitive substring matching: \"Draw\", \"SRS\", "
                "\"Contour\", \"Isodose\", \"Review\".",
                "Open vs completed is derived from CompletedDateTime being null, "
                "not from a status column. Some source rows use the sentinel "
                "string \"NA\" on CompletingMD for open tasks — both are "
                "treated equivalently.",
                "SLA compliance uses MinutesToComplete ≤ MinutesAllowed on "
                "completed tasks only. Open tasks don't contribute to the "
                "compliance denominator (they haven't had a chance to breach "
                "yet — they're tracked separately in the Open Tasks counts).",
                "After-hours flagging is a simple hour-of-day check on "
                "CompletedDateTime (before 8 AM or at/after 5 PM). The page "
                "does not currently cross-reference the Physician Schedule "
                "extract to detect OFF days or WEEKEND CALL — that's on the "
                "upgrade list.",
                "Diagnosis body-site slicing joins each task's patient to the "
                "Diagnosis lookup via DiagnosisCodes.",
                "Physician names in the x-axis are shortened via "
                "physician_short_name (first token after the comma) for "
                "legibility.",
                "Data-relative dates anchor every KPI and chart to "
                "max(StartDateTime) in the extract, not wall-clock today.",
                "Server/clientside split — dcc.Stores (tasks-store-volume, "
                "tasks-store-cumulative, tasks-store-histogram, "
                "tasks-store-time-compare, tasks-store-time-trend, "
                "tasks-store-sla, tasks-store-kpi-sparklines) carry the raw "
                "data; clientside callbacks handle smoothing, aggregation, "
                "and chart-type switching.",
            ]),
        ),

        section(
            "Counting semantics",
            "tabler:calculator",
            bullets([
                "One row = one task. KPI counts are row counts after filters.",
                "Completed (period) counts tasks whose CompletedDateTime falls "
                "inside the date range — a task started before the range and "
                "finished inside still counts.",
                "Open Tasks counts rows with null CompletedDateTime regardless "
                "of when StartDateTime was — these are still-on-the-board items.",
                "Median Time to Complete is over completed tasks only.",
            ]),
        ),

        section(
            "Known quirks and limitations",
            "tabler:alert-triangle",
            bullets([
                "After-hours detection is a simple hour-of-day check. A task "
                "completed on Saturday afternoon during business hours will "
                "NOT flag as after-hours, even though it was a weekend. "
                "Cross-referencing Physician Schedule would fix this.",
                "Draw task times start when the Draw became the MD's to do "
                "(same rule as the Workflow page): the latest completed Dosi "
                "Prep or Fusion Review, else the Draw task's first activation, "
                "else the later of sim end and task creation. Dosi Prep began "
                "2026-05-18, so older Draws mostly use the fallbacks and can "
                "still include informal prep. The extract's DrawMDReadySource "
                "column says which rule applied. ARIA's In Progress status is "
                "not used.",
                "SLA thresholds (MinutesAllowed) come from the source extract "
                "per task type. If a task type has no allowed-minutes policy "
                "configured in ARIA, compliance for that type will be "
                "0% / null depending on the filter mix.",
                "Task type classification uses substring matching — a new "
                "ActivityName like \"Draw Volumes - SRS\" would match both "
                "Draw and SRS buckets. The task-type filter resolves this by "
                "checking buckets in order, but histogram / distribution "
                "slicing by task may double-count.",
                "The clickable KPI cards use page-level n_clicks state — "
                "hard-refreshing the page clears the selection.",
            ]),
        ),
    ],
)
