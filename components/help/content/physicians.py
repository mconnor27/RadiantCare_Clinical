"""Physicians page — UI and data-processing help content."""

from __future__ import annotations

import dash_mantine_components as dmc

from ..renderers import body, bullets, section, subheading


UI_CONTENT = dmc.Stack(
    gap="md",
    children=[
        dmc.Text(
            "The Physicians page tracks manpower, site assignments, after-"
            "hours work, and cross-coverage for the four radiation "
            "oncologists (Allen, Connor, Suszko, Tinnel). It cross-references "
            "the daily physician schedule (who was supposed to be at which "
            "site) with task completions (what actually got done, by whom, "
            "and when) to surface patterns like off-day work, weekend calls, "
            "and tasks picked up from another physician's patients.",
            size="sm", c="dimmed", style={"lineHeight": 1.6},
        ),

        section(
            "What's on this page",
            "tabler:layout-dashboard",
            body(
                "A 5-tile KPI row with sparklines, four analytic charts, a "
                "full-width physician schedule calendar heatmap, and a "
                "schedule detail table.",
            ),

            dmc.Space(h="xs"),

            dmc.Text("KPI row (5 cards, all with sparklines)", fw=600, size="xs", mb=4),
            bullets([
                "Avg Daily Coverage — mean unique on-duty physicians per "
                "weekday (excludes weekends and holidays). Statuses counted "
                "as on-duty: LACEY / CENTRALIA / ABERDEEN / ON CALL / ON / "
                "WEEKEND CALL.",
                "After-Hours Tasks — count of tasks completed outside the "
                "configured business-hours window or during weekends / "
                "holidays / off days / vacation, depending on which toggles "
                "are enabled.",
                "Cross-Coverage Tasks — tasks where CompletingMD ≠ AssignedMD "
                "(one physician picks up another's patient).",
                "Off/Vacation Days — schedule rows with Status OFF / "
                "VACATION / SICK / SICK LEAVE.",
                "Weekend Calls — schedule rows with Status WEEKEND CALL.",
            ]),
            body(
                "Each card shows a percent trend vs the prior equivalent "
                "period, plus a weekly-aggregated sparkline rendered "
                "clientside from the dcc.Store payload.",
            ),

            dmc.Space(h="xs"),

            dmc.Text("Charts", fw=600, size="xs", mb=4),
            bullets([
                "Manpower Over Time (half-width) — on-duty count by date, "
                "aggregatable Daily / Weekly / Monthly / Yearly. Smoothing "
                "up to 50. Line / Area / Bar (default bar).",
                "Site Assignments (half-width) — stacked or grouped bar of "
                "assignment days (or %) per department × physician. "
                "Department colors: Lacey blue, Centralia red, Aberdeen green.",
                "After-Hours Tasks (half-width) — horizontal bar per "
                "physician. A filter panel sets the business-hours window "
                "(0–48 tick range slider = 30-min increments, default 7 AM → "
                "6 PM) and which non-business-hour buckets count (weekends, "
                "holidays, off days, vacation).",
                "Cross-Coverage (half-width) — horizontal bar per completing "
                "physician, showing how many tasks were picked up from "
                "other physicians' patients. Count or % mode.",
            ]),

            dmc.Space(h="xs"),

            dmc.Text("Schedule calendar + detail table", fw=600, size="xs", mb=4),
            bullets([
                "Schedule Calendar — full-width heatmap, rows = physician, "
                "columns = date, colored by status (on-duty green, on call "
                "yellow, off gray, vacation/sick red).",
                "Schedule Detail — Date, Physician, Status, Department. "
                "Column filtering and sort available; CSV export.",
            ]),
        ),

        section(
            "Filters",
            "tabler:filter",
            bullets([
                "Date preset + date range picker + month-granularity range "
                "slider — all three synced. Default Prior 12 months. The "
                "slider auto-clears the preset to \"custom\" when adjusted.",
                "Smoothing slider (0.0–1.0) — drives the manpower chart "
                "LOWESS smoothing fraction.",
                "Per-chart inline controls — aggregation (manpower), Count "
                "vs % (sites / after-hours / cross-coverage), the After-"
                "Hours filter popover (weekend / holiday / off / vacation "
                "toggles + business-hours range).",
                "No physician dropdown — the page is intentionally all-"
                "physicians-at-once, since manpower and cross-coverage are "
                "group-level concepts. Individual physician detail lives in "
                "the Tasks page.",
            ]),
        ),

        section(
            "How after-hours is computed",
            "tabler:clock-hour-8",
            body(
                "After-hours is a composite rule, not just a clock window. A "
                "task counts as after-hours if ANY of the enabled criteria fire:",
            ),
            bullets([
                "Business-hours window — CompletedDateTime falls outside the "
                "user-configured biz_start → biz_end range. The slider ticks "
                "are half-hour increments (tick N = N × 0.5 hours), so the "
                "default [14, 36] becomes 7:00 AM → 6:00 PM. If the \"Business "
                "hours\" switch is off, this criterion is disabled.",
                "Weekends — CompletedDateTime.dayofweek ≥ 5.",
                "Holidays — date is in the utils.holidays.get_holidays() set.",
                "Off days — a schedule-based join: the completing physician's "
                "status on the task's date was OFF / SICK / SICK LEAVE.",
                "Vacation — same join, status VACATION.",
            ]),
            body(
                "The toggles are OR'd — enable Weekends + Off Days and a "
                "task completed on a Saturday is counted once, even though "
                "both criteria may fire. The default toggle set is "
                "Weekends only.",
            ),
        ),

        section(
            "How the data is processed",
            "tabler:cpu",
            bullets([
                "Two source datasets: Physician_Schedule "
                "(load_physician_schedule — one row per physician × date × "
                "status) and Tasks (load_tasks — one row per task completion "
                "with AssignedMD, CompletingMD, CompletedDateTime).",
                "Prior-period trends use the equal-length window immediately "
                "preceding the selected range (start − period_days to "
                "start − 1). Both schedule and tasks are re-filtered to the "
                "prior window for the KPI trend comparisons.",
                "Coverage KPI excludes holidays via "
                "utils.holidays.get_holidays() and weekends via dayofweek, so "
                "a holiday or weekend with no one on duty doesn't drag the "
                "average down.",
                "Coverage sparkline uses weekly resample of the daily unique "
                "on-duty count — not daily values — so the KPI card's small "
                "chart stays readable at any date range.",
                "Site assignments are grouped by (Department, Physician) on "
                "the schedule rows where Status maps to a site (LACEY, "
                "CENTRALIA, ABERDEEN). ON CALL typically resolves to Lacey; "
                "WEEKEND CALL has its own category.",
                "After-hours chart can operate on the task set alone or "
                "with a schedule-based join that pulls the completing "
                "physician's status on the completion date. The join uses "
                "(CompletingMD, date) as the key.",
                "The Manpower chart has its own clientside smoothing "
                "callback fed from phys-store-manpower; the other charts "
                "render server-side.",
                "Refresh interval: 5 minutes.",
            ]),
        ),

        section(
            "Known quirks and limitations",
            "tabler:alert-triangle",
            bullets([
                "Physician Schedule is a Complete/ file, not incremental — "
                "the dashboard picks up its full contents on each refresh. "
                "If the schedule extract lags, coverage KPIs may reflect "
                "stale data.",
                "Status strings vary in case across the source file. The "
                "page upper-cases everything and compares against the canonical "
                "sets (_ON_DUTY, _OFF_STATUSES). A new status value "
                "(e.g., \"MTG\", \"CME\") that isn't added to those sets will "
                "be silently ignored for KPI purposes.",
                "On Call usually resolves to Lacey, but this is a "
                "convention — a physician assigned ON CALL in the source "
                "data is counted as on-duty but their department attribution "
                "on the Site Assignments chart depends on the exact status "
                "string used.",
                "Cross-coverage only compares CompletingMD to AssignedMD. "
                "Legitimate scheduled coverage (e.g., a planned swap) looks "
                "the same as an after-hours pickup — the after-hours filter "
                "is the better lens for \"who is working off-shift.\"",
                "The 5 KPIs use the filter's date range in full. If you "
                "select 12 months and only the last 3 have data, the trend "
                "comparison is against the 12 months before that — a quiet "
                "prior window — and can look misleadingly favorable.",
            ]),
        ),
    ],
)
