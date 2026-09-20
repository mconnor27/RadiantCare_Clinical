"""EOT Audit page — UI and data-processing help content."""

from __future__ import annotations

import dash_mantine_components as dmc

from ..renderers import body, bullets, section


UI_CONTENT = dmc.Stack(
    gap="md",
    children=[
        dmc.Text(
            "The EOT Audit page tracks end-of-treatment documentation compliance "
            "at the course level. When a radiation course ends, the treating "
            "physician owes a treatment summary (an \"End of Treatment\" note) "
            "within 30 days of the last fraction. Each row of the underlying feed "
            "is one patient-course with a verdict: Documented (a note exists in "
            "the course's completion-anchored window), Pending (completed, still "
            "inside the 30-day grace period), or Missing (past due, nothing "
            "written). Missing + Pending together are the open task set that "
            "also drives the per-physician Planner tasks via Power Automate.",
            size="sm", c="dimmed", style={"lineHeight": 1.6},
        ),

        section(
            "What's on this page",
            "tabler:layout-dashboard",
            body(
                "Sticky header with department / treating-physician / date "
                "filters (the date range applies to the LAST FRACTION date; the "
                "timeline floors at mid-2021, when EOT notes first exist in the "
                "warehouse), a "
                "4-tile KPI row, two chart rows, and the open-documentation "
                "worklist. When AG Grid column filters are active on the "
                "worklist, a red \"Table Filtered\" badge appears and the KPIs / "
                "charts reflect the filtered subset.",
            ),

            dmc.Space(h="xs"),

            dmc.Text("KPI row (5 cards)", fw=600, size="xs", mb=4),
            bullets([
                "Courses Completed — completed courses whose last fraction "
                "falls in the selected range.",
                "Open Tasks — Missing + Pending count (split shown inline). "
                "Trend arrow is inverted: fewer open tasks is better.",
                "Documented Rate — % of resolved courses (Documented + "
                "Missing; Pending is excluded as still inside its writing "
                "window) that got a summary at ALL, however late. Green at "
                "≥95%.",
                "On-Time Rate — same denominator, but the note must land "
                "within 30 days of the last fraction. Green at ≥90%.",
                "Median Days to Note — median DaysAfterLastTx across documented "
                "courses; green when at or under the 30-day due window.",
            ]),

            dmc.Space(h="xs"),

            dmc.Text("Charts", fw=600, size="xs", mb=4),
            bullets([
                "Documentation Compliance Trend — On-Time %, Documented % "
                "(done at all, any lag), or Median Days over time (weekly / "
                "monthly / yearly), with optional smoothing.",
                "By Treating Physician — horizontal bars of Open Tasks (Missing "
                "/ Pending, stacked or grouped via the gear menu), On-Time %, or "
                "Median Days per physician. Rate and lag views require ≥3 "
                "courses per physician.",
                "Days From Last Fraction to Note — 5-day-bin histogram of "
                "documentation lag; bins past the 30-day due line are red, and "
                "everything beyond 120 days pools into a 120+ bin. The All / "
                "Treating MD / Author MD toggle stacks each bin by physician — "
                "Treating is the course's treating physician, Author is who "
                "actually signed the note (they differ on ~9% of notes); the "
                "gear menu switches per-MD bars between stacked and grouped.",
                "Open-Task Aging — open items bucketed 0–30 / 31–60 / 61–90 / "
                "90+ days since last fraction, stacked by physician or "
                "department.",
            ]),

            dmc.Space(h="xs"),

            dmc.Text("Worklist", fw=600, size="xs", mb=4),
            body(
                "The Documentation Worklist defaults to open items (Missing + "
                "Pending + Reopened) sorted most-overdue first. Quick filters: "
                "All Open / Missing / Pending / Documented / Waived / All "
                "Items, plus a "
                "Per MD select to jump to one treating physician's items. "
                "Documented and All Items views add the note date, author, and "
                "days-to-note columns; Export CSV downloads the current view.",
            ),

            dmc.Space(h="xs"),

            dmc.Text("Waive / Reopen overrides", fw=600, size="xs", mb=4),
            bullets([
                "Every row carries an Override button: Waive on an open item "
                "(\"no summary needed — stop tracking it\"), Reopen on a "
                "documented one (\"this note doesn't count — put it back on "
                "the list\"), Undo on either.",
                "Overrides persist in the same database as CPT reviews "
                "(SQLite locally, Postgres in production), keyed on the "
                "feed's CourseKey, so they survive restarts and data "
                "refreshes.",
                "They flow through every metric: a Waived course leaves the "
                "open counts AND the compliance denominators entirely; a "
                "Reopened course rejoins the open set and counts as "
                "not-documented in the Documented / On-Time rates.",
                "If the feed later resolves the course itself (e.g. a waived "
                "MISSING course finally gets its note), the override no "
                "longer applies and the feed's verdict wins.",
                "The Waived quick filter lists everything waived, where the "
                "Undo button restores it.",
            ]),
        ),

        section(
            "How the verdict works",
            "tabler:scale",
            bullets([
                "A course only enters the audit once it has COMPLETED — judged "
                "by the same 8-tier completion cascade the Courses page uses "
                "(ARIA stamp, discharge / last-day activities, plan-fulfilled "
                "counters, inactivity timeouts). An in-progress course is never "
                "reported as undocumented.",
                "There is no key linking notes to courses in the warehouse — a "
                "note is matched by patient + date window, anchored on the "
                "completion cascade and capped by the neighbouring courses so "
                "one summary can never credit two courses.",
                "The grace clock runs from the last fraction, not the "
                "completion date: the note is due 30 days after treatment ends.",
                "\"Plan Fulfilled\" can legitimately sit next to 4 of 30 "
                "fractions — when a patient stops early, ARIA closes the "
                "session counters at what was delivered, and the course is "
                "finished (the summary is still due).",
                "Author columns cross-check who signed the note against the "
                "oncologist of record (AuthorIsPrimaryOnc) and the treating "
                "physician (AuthorIsTreatingPhysician).",
            ]),
        ),

        section(
            "Data handling",
            "tabler:database",
            bullets([
                "Source: EOT_yyyymmdd.csv files in Incremental/EOT, exported "
                "daily with a 365-day lookback.",
                "The loader upserts on CourseKey (ARIA's own course serial): "
                "all files concatenate in date order and the newest row per "
                "course wins, so a course flips Missing → Documented in place "
                "while courses that age out of the export window keep their "
                "last verdict. History therefore extends beyond any single "
                "file's range — the first export seeded back to 2021.",
                "Pluvicto courses carry negative CourseKeys by design (no "
                "DimCourse row exists); the loader keeps them.",
                "Free-text fields arrive CSV-safe (commas replaced with "
                "semicolons for the Power Automate feed); the loader restores "
                "'Last, First' name formatting for display.",
                "Multi-site courses list several departments — the first one "
                "is used for department filtering.",
                "Old Missing rows from 2021-2023 are historical compliance "
                "findings from the all-history seed export; the default "
                "12-month view scopes the worklist to the actionable set. "
                "Switch to All Time to see the full history.",
            ]),
        ),
    ],
)
