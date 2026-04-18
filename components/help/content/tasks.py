"""Tasks page — UI and data-processing help content."""

from __future__ import annotations

import dash_mantine_components as dmc

from ..renderers import body, bullets, section, subheading


UI_CONTENT = dmc.Stack(
    gap="md",
    children=[
        dmc.Text(
            "The Tasks page tracks physician and planner task workload — Draw "
            "Volumes, SRS contouring, Contour Review, Isodose Plan, and Review "
            "Plan — against their SLA deadlines. Source data is the ARIA Tasks "
            "extract; the Physician Schedule extract provides cross-reference "
            "data for identifying after-hours and off-day work.",
            size="sm", c="dimmed", style={"lineHeight": 1.6},
        ),

        section(
            "What's on this page",
            "tabler:layout-dashboard",
            body(
                "A 5-tile KPI row (one card per task type, each clickable to "
                "filter the rest of the page), six chart cards across three "
                "rows, and a full-width detail table. The clickable KPI cards "
                "act as a quick way to drill into a single task type without "
                "opening the task-type filter panel.",
            ),

            dmc.Space(h="xs"),

            dmc.Text("KPI row (5 clickable group cards)", fw=600, size="xs", mb=4),
            bullets([
                "Draw — Draw Volumes tasks.",
                "SRS — SRS-specific contouring tasks.",
                "Contour — Contour Review tasks.",
                "Isodose — Isodose Plan tasks.",
                "Review — Review Plan tasks.",
            ]),
            body(
                "Each card shows count, median time to complete, SLA compliance, "
                "and a sparkline. Clicking a card sets the task-type filter to "
                "that single type; clicking again clears the selection.",
            ),

            dmc.Space(h="xs"),

            dmc.Text("Charts", fw=600, size="xs", mb=4),
            bullets([
                "Task Volume Trend — bar / line / area, weekly / monthly / "
                "yearly. Slice by Total, Task type, MD, Planner, or Diagnosis "
                "body site. Smoothing slider.",
                "Cumulative Task Volume — running total with Prior Periods "
                "overlay and projection option. Calendar or rolling period "
                "windows.",
                "Time Distribution — histogram or density of MinutesToComplete. "
                "Slice by Task, MD, or Planner. Density mode exposes a "
                "bandwidth slider.",
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
                "Planner — single-select. Drawn from CompletingMD values.",
                "Task type — multi-select (Draw Volumes, SRS contouring, "
                "Contour Review, Isodose Plan, Review Plan) matched by "
                "ActivityName substring.",
                "Status — Completed / Open / All (Open = CompletingMD is null).",
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
