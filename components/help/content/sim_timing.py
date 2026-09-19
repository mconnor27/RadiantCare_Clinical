"""Sim Timing page — UI and data-processing help content."""

from __future__ import annotations

import dash_mantine_components as dmc

from ..renderers import body, bullets, section


UI_CONTENT = dmc.Stack(
    gap="md",
    children=[
        dmc.Text(
            "The Sim Timing page measures how long a CT simulation takes, "
            "phase by phase. Data comes from the ARIA Simulation Timing "
            "extract: one row per completed Lacey CT_Sim simulation that has "
            "at least one CT series attributed to it. Department, physician "
            "and diagnosis are joined on from the Simulations extract "
            "(UniqueRowID, 1:1). The filter bar deliberately mirrors the "
            "Simulations page — same department chips, same chip-dropdown "
            "idiom, same date controls — so the two read as one product.",
            size="sm", c="dimmed", style={"lineHeight": 1.6},
        ),

        section(
            "This page is not a volume source",
            "tabler:alert-triangle",
            body(
                "The underlying report requires matched CT imaging, so real "
                "completed simulations that lack an attributed scan are absent "
                "from it — not blank. Recent-month matching runs around "
                "110/112 and 113/116, so the loss is small but neither zero "
                "nor random. Use the Simulations page for counts. This page "
                "answers a narrower question: for the sims we can see the CT "
                "for, how long did they take."
            ),
        ),

        section(
            "Milestones and phases",
            "tabler:timeline-event",
            body(
                "Every chart is driven by one milestone selection. Pick two or "
                "more timestamps; the composition chart stacks the gap between "
                "each consecutive pair, and the density chart histograms the "
                "span from the first selected milestone to the last. Presets "
                "set the selection and leave it editable."
            ),
            dmc.Space(h="xs"),
            dmc.Text("Presets", fw=600, size="xs", mb=4),
            bullets([
                "Visit — Check-In → CT Complete → Appointment End. The default.",
                "Full visit — adds Scheduled Start at the front and Note "
                "Entered at the back.",
                "Scan only — CT First Series → CT Complete.",
                "Doc tail — CT Complete → Note Entered.",
            ]),
            dmc.Space(h="xs"),
            dmc.Text("Milestones", fw=600, size="xs", mb=4),
            bullets([
                "Scheduled Start / Scheduled End — the booked slot (ARIA).",
                "Check-In — arrival. NULL means the patient was never checked "
                "in; that is real, not missing (ARIA).",
                "CT First Series / CT Complete — first and last series landing "
                "on the scanner (scanner clock).",
                "Appointment End — when the appointment was closed out (ARIA).",
                "Note Entered — earliest system-set Simulation Note or "
                "Set Up Note stamp. This is the documentation milestone the "
                "page uses by default.",
                "Doc Complete is deliberately not offered. The extract's "
                "DocumentationCompleteDateTime resolves to "
                "SetupNote_LastModified on ~93% of rows, and Set Up Notes are "
                "reopened and edited a median of ~10 days after the visit, so "
                "it measures how long notes stay open for revision rather than "
                "when documentation was done. Note Entered is the "
                "documentation milestone.",
            ]),
        ),

        section(
            "Charts",
            "tabler:chart-bar",
            bullets([
                "Phase Composition — stacked bar, median (or mean) minutes per "
                "phase, by week, month or year. Milestones are ordered by where "
                "they actually land, not by the order they appear in the "
                "picker, and each segment is the difference between two "
                "milestones' aggregate positions — so the parts add to the "
                "whole and the stack height is exactly the span named on the "
                "y-axis. The gear offers Stacked / Grouped and a PNG export; "
                "Grouped drops the total, since the bars no longer stack. A "
                "segment that still comes out negative is drawn below the axis "
                "rather than clipped.",
                "End-to-End Distribution — histogram of the span from the "
                "earliest to the latest milestone you have selected, so it "
                "follows the picker: Doc tail gives CT Complete → Note Entered, "
                "Scan only gives CT First Series → CT Complete. The median is "
                "marked and bin width is selectable (10 / 15 / 30 min).",
                "Booked vs Actual — dumbbell of median booked slot length "
                "against median actual occupancy (Check-In → Appointment End), "
                "grouped by sim type, therapist, or MD. The connector is red "
                "when actual exceeds booked, green when it fits. Categories "
                "with fewer than 3 sims are dropped.",
                "Overrun Rate — share of sims finishing past the booked end, "
                "as a monthly trend or a single total, with the period average "
                "as a dashed reference.",
                "Typical Sim — the aggregate of the drill-down strip: one "
                "lane per milestone, a bar for the spread and a tick for the "
                "centre, all in minutes from each sim's own booked start, with "
                "the median booked slot shaded behind. Centre switches between "
                "median and mean; spread between IQR, ±1 SD and P10–90. "
                "Compare mode splits each lane into an A and a B half. Median "
                "and IQR are the defaults because the distribution is "
                "right-skewed — on ±1 SD the Appointment End band runs roughly "
                "−10 to +145 min, which is the skew showing itself rather than "
                "a defect.",
                "When Sims Run Long — weekday x booked-start-hour heatmap, "
                "switchable between overrun %, median visit length and volume. "
                "Both endpoints of the overrun metric are ARIA-side, so this "
                "grid is valid across all history regardless of clock era. "
                "Rate cells backed by fewer than 3 sims are left uncoloured — "
                "a single overrun in a one-appointment cell reads as 100% and "
                "would otherwise own the colour scale.",
            ]),
        ),

        section(
            "Reading the Typical Sim chart",
            "tabler:chart-dots",
            body(
                "Milestone offsets are screened to a −12 h to +24 h window "
                "before aggregating. That screen is separate from the page's "
                "Outliers control, which applies to segment lengths: these are "
                "offsets from the booked start, so a note entered three days "
                "late would drag a mean badly without it. Each lane reports "
                "its own n in the tooltip, because a milestone can be null on "
                "rows where the others are not — a patient never checked in, "
                "or no in-scope note matched."
            ),
            dmc.Space(h="xs"),
            body(
                "Two things the default view shows straight away. Check-In's "
                "whole interquartile range sits left of zero, so arriving "
                "early is the norm, not the exception. And Note Entered "
                "typically lands before Appointment End — documentation is "
                "finished while the appointment is still open, rather than "
                "after it closes."
            ),
        ),

        section(
            "KPI row",
            "tabler:dashboard",
            bullets([
                "Sims Timed — appointments with matched CT in the current "
                "filter. Not a volume figure; see the scope note above.",
                "Median Visit — booked start to documentation (first note "
                "entered). ARIA-side at both ends, so clock-immune.",
                "Past Booked End — share whose documentation was entered after "
                "the booked end. Measured on the note stamp rather than the "
                "manual close-out, since closing an appointment is a clerical "
                "act while the note is when the work actually finished. Also "
                "ARIA-side at both ends. The Overrun chart defaults to the same "
                "definition, with appointment-end and CT-complete available for "
                "comparison.",
                "Median to CT Complete — booked start to the last CT series. "
                "Cross-clock; treat it as a population figure.",
                "Median Doc Lag — CT complete to first note entered. Also "
                "cross-clock. This and the KPI beside it add up exactly to "
                "Median Visit.",
            ]),
        ),

        section(
            "Drilling into one appointment",
            "tabler:zoom-in",
            body(
                "The heatmap is the entry point, the same way the year cards "
                "are on Machine Downtime. Click a cell to scope the detail "
                "table to that weekday and hour — the breadcrumb above the "
                "table tracks where you are, and the table opens itself. "
                "Clicking the same cell again clears the selection, as does "
                "the Clear selection button."
            ),
            dmc.Space(h="xs"),
            body(
                "Clicking a cell also draws the cohort strip: one lane per "
                "appointment in that weekday and hour, each aligned on its own "
                "booked start, with the booked slot shaded. A lane whose "
                "Appointment End sits outside the band ran over. At most 25 "
                "lanes are drawn — the subtitle says so whenever the cap bit — "
                "and the x-axis is clamped to the bulk of the marks, with any "
                "that fall outside counted in the top-right corner rather than "
                "silently dropped."
            ),
            dmc.Space(h="xs"),
            body(
                "Selecting a table row then replaces the strip with that one "
                "appointment's Timeline: every milestone plotted in minutes "
                "from the booked start, with the booked slot as a shaded band "
                "so an overrun is visible directly. Doc Complete is "
                "deliberately excluded from both views — its amendment-driven "
                "values are days out and would flatten the axis."
            ),
            dmc.Space(h="xs"),
            body(
                "The timeline header states the row's clock era. On a "
                "corrected row the badge reads \"CT corrected +N min\" and its "
                "two scanner milestones are drawn as hollow markers — in the "
                "cohort strip that makes the pre- and post-fix lanes tell "
                "themselves apart at a glance. This matters because "
                "the field guide is explicit that a corrected row must not be "
                "used to adjudicate an individual case — residual scatter is "
                "±10-20 minutes. The ARIA-side milestones on that same row are "
                "exact."
            ),
        ),

        section(
            "Filters",
            "tabler:filter",
            bullets([
                "Milestones — the phase selection described above.",
                "Department — the *patient's* department, joined from "
                "Simulations. The extract's own DepartmentName is the "
                "scanner's site (always Lacey), which is useless as a cohort "
                "filter because Centralia and Aberdeen patients are "
                "routinely simulated on the Lacey CT_Sim.",
                "Physician — joined from Simulations, with the same "
                "Consult / Supervising / Attending role toggle the "
                "Simulations page uses.",
                "Therapist — CompletedByUser, whoever closed the appointment. "
                "\"Everson, Winter(DNU)\" is merged into \"Everson, Winter\".",
                "Disease Site — primary diagnosis category, resolved from "
                "DiagnosisCodes through the shared diagnosis-category mapper.",
                "Type — ActivityName (Initial Simulation, Stereotactic, "
                "Re-Simulation, and the Centralia/Aberdeen-in-Lacey variants).",
                "Technique — the treatment technique of the course the sim "
                "led to (3D / Electron / IMRT / VMAT / SBRT / SRS), joined "
                "from Courses. Matching is ANY-match against the course's full "
                "technique set, so picking Electron also finds breast courses "
                "whose electron boost sits behind a 3D primary.",
                "Setup — 4D CT, APBI, breath hold, decubitus, prone, and free "
                "breathing. A flag means a scan of that kind was acquired "
                "during the appointment. Free breathing is the exception: it is "
                "only flagged when no breath-hold was acquired, because free "
                "breathing is the default state and a DIBH sim takes both scans "
                "by design. See the derivation note below.",
                "Series — distinct CT series on the appointment, with "
                "Conventional (1–6) and 4D CT (10+) presets.",
                "All / Initial, Inpatient, Duration and Weekend — the same "
                "scope controls the Simulations page carries, so the two pages "
                "filter alike. Duration filters on the booked slot length, and "
                "its top handle is unbounded. Weekend is present for parity "
                "but returns nothing on this dataset: there are no weekend CT "
                "sims in the extract.",
                "Clock era — All (corrected) or Reliable only. Choosing "
                "Reliable only also pulls the date range forward to 2026-07, "
                "since nothing before the clock fix can match and a full "
                "12-month window would otherwise render mostly empty months; "
                "switching back restores the range and preset you had. A range "
                "that already starts after the fix is left alone.",
                "Outliers — a plausibility window per milestone, in minutes "
                "from the booked start, with Default / Strict / Off presets and "
                "every window individually adjustable. See below.",
                "Compare — reveals a second, independent filter bar. Every "
                "chart then draws Dataset A and Dataset B together (B is drawn "
                "in orange, with dashed or open marks).",
            ]),
        ),

        section(
            "How technique and setup are derived",
            "tabler:git-merge",
            body(
                "The timing extract carries no technique of its own, so it is "
                "joined to Courses in two passes: first on same patient plus an "
                "identical first-treatment date, which matches about 86% of "
                "sims with no ambiguity at all; then, for the remainder, the "
                "course whose start date falls closest within −3 to +60 days of "
                "the sim. Together they reach 91%. The rest are left null "
                "rather than guessed — most of them are sims that never led to "
                "treatment."
            ),
            dmc.Space(h="xs"),
            body(
                "This matters because it is the only way to separate SBRT from "
                "SRS: the Stereotactic Simulation activity splits 108 SBRT / 34 "
                "SRS, and a further dozen or so stereotactic sims are booked "
                "under plain Initial Simulation or Re-Simulation, so activity "
                "name alone both conflates and under-counts them. Because the "
                "technique comes from the course that followed, it is only ever "
                "known in hindsight."
            ),
            dmc.Space(h="xs"),
            dmc.Text("Setup flags", fw=600, size="xs", mb=4),
            bullets([
                "4D CT — SeriesCount ≥ 10. A 4D CT is acquired as ten "
                "respiratory phase bins plus reconstructions, so the series "
                "count jumps an order of magnitude. The distribution is cleanly "
                "bimodal with nothing at all between 7 and 11 series, and every "
                "row whose series name is a phase bin (CT_00_1 … CT_90_1) sits "
                "above the threshold — so counting series detects 4D CT about "
                "three times more completely than matching the name, which only "
                "fires when the last series happens to be a phase bin.",
                "APBI, breath hold, decubitus, free breathing, prone — matched "
                "against the CT series name — the therapist's own label. The "
                "export currently emits only the last series, so a technique "
                "named on an earlier series is missed; the loader already reads "
                "a full series-name column instead, delimiter-agnostically, the "
                "moment one is exported. These are inferences from free text "
                "and are kept as "
                "separate flags rather than folded into Technique, so an "
                "inference never masquerades as a warehouse fact. About 15% of "
                "sims carry a generic series name (CT_1, AUTO_IMPORT) and can "
                "carry no flag at all, so absence of a flag is not evidence of "
                "absence.",
                "AppointmentNote is deliberately not parsed. It would improve "
                "breath-hold coverage roughly two-fold, but it is PHI, the "
                "sanitizer drops it, and the field guide warns against parsing "
                "it — so the flags would be empty in production anyway. "
                "CTLastImageId and SeriesCount are not PHI and survive "
                "sanitization, so these flags behave identically everywhere.",
            ]),
        ),

        section(
            "Outlier screening",
            "tabler:filter-cog",
            body(
                "Screening happens at the milestone, not at each derived "
                "interval. An appointment closed out two days later poisons "
                "every interval that ends on it, and one window removes it from "
                "all of them at once. Because both endpoints of any interval are "
                "screened this way, no separate per-segment clamp is applied "
                "anywhere on the page — the composition, density, Typical Sim, "
                "KPI, dumbbell and heatmap figures all inherit the same screen."
            ),
            dmc.Space(h="xs"),
            body(
                "A milestone outside its window is ignored rather than the whole "
                "appointment being thrown away, so a late close-out still "
                "contributes its clean check-in-to-CT time. If you would rather "
                "discard the appointment outright, the \"Drop the whole "
                "appointment instead\" switch does that — but only when the "
                "offending milestone is one your current selection actually uses."
            ),
            dmc.Space(h="xs"),
            body(
                "Defaults come from the observed distributions, roughly the 1st "
                "to 99th percentile rounded out generously so ordinary variation "
                "is never cut. Scheduled Start and Scheduled End are not "
                "screened: one is always exactly 0, and the other is the booked "
                "slot, observed between 30 and 210 minutes."
            ),
            dmc.Space(h="xs"),
            dmc.Text("Default windows (minutes from booked start)", fw=600,
                     size="xs", mb=4),
            bullets([
                "Check-In −120 to +120 — observed p1 −61, p99 +59.",
                "CT First Series −60 to +240 — observed p1 −21, p99 +72.",
                "CT Complete −60 to +240 — observed p1 −20, p99 +95.",
                "Appointment End −60 to +240 — observed p1 +4, p99 +258, but a "
                "long tail to 29,901 min (20 days). Only 15 sims (1.3%) close "
                "out more than 4 h after the booked start, and 2 more than a "
                "day; this window is what removes them.",
                "Note Entered −240 to +720 — observed p99 +187, with a tail to "
                "+8,255 and a backdated note at −113,782 min (−79 days).",
            ]),
        ),

        section(
            "The CT clock correction",
            "tabler:clock-alert",
            body(
                "The CT simulator's clock ran 75–90 minutes slow for over two "
                "years and was corrected the weekend of 2026-07-25/26. It was "
                "the scanner, not the warehouse — linac imaging held a steady "
                "−3 min through the same period — and the error drifted a "
                "further 1.5–2 min per month, so no single offset repairs it. "
                "Rows dated on or after 2026-07-27 carry CTTimestampEra = "
                "'Reliable'; everything earlier has had its CT timestamps "
                "algorithmically corrected, by the number of minutes recorded "
                "in CTClockOffsetMinutes."
            ),
            dmc.Space(h="xs"),
            body(
                "Corrected values are sound for population work — monthly "
                "medians, distributions, trends. They are not sound "
                "per-appointment: residual scatter is ±10–20 minutes. Never "
                "use a corrected row to adjudicate an individual case."
            ),
            dmc.Space(h="xs"),
            dmc.Text("What the clock touched", fw=600, size="xs", mb=4),
            bullets([
                "Safe always — Scheduled Start, Scheduled End, Check-In, "
                "Appointment End, and every note timestamp. Built only from "
                "ARIA stamps.",
                "Safe always — CT First Series → CT Complete. Both endpoints "
                "come from the scanner's own clock, so the offset cancels.",
                "Cross-clock — any segment with one ARIA endpoint and one "
                "scanner endpoint (e.g. Check-In → CT Complete, CT Complete → "
                "Appointment End). The page flags these with an amber "
                "\"cross-clock\" badge in the filter bar and a ⚠ on the "
                "affected series. Both disappear under Reliable only, where "
                "nothing was ever corrected.",
            ]),
        ),

        section(
            "Why documentation uses Note Entered, not Doc Complete",
            "tabler:file-alert",
            body(
                "The source column DocumentationCompleteDateTime resolves to "
                "SetupNote_LastModified on about 93% of rows, and Set Up Notes "
                "are routinely reopened and amended long after the visit — a "
                "median of roughly 10 days. As a result the extract's own "
                "CheckInToDocCompleteMinutes has a median near 14,500 minutes "
                "(≈10 days): it measures amendment latency, not the burden of "
                "the visit."
            ),
            dmc.Space(h="xs"),
            body(
                "The page therefore anchors documentation on "
                "FirstNoteEnteredDateTime — the earlier of "
                "SimNote_DateEntered and SetupNote_DateEntered. Those stamps "
                "are system-set and never move, and both endpoints are "
                "ARIA-side, so the interval is clock-immune and usable across "
                "all history. Check-In → Note Entered runs a median of about "
                "47 minutes. The raw doc-complete stamp is still available in "
                "the milestone picker, labelled \"(+amendments)\"."
            ),
        ),

        section(
            "Other things that will bite you",
            "tabler:bug",
            bullets([
                "Patients arrive early. StartDelayMinutes has a median of −10 "
                "and is negative on 79% of sims, so Scheduled Start → Check-In "
                "is usually a negative segment.",
                "Scan span is mostly zero. CTScanSpanMinutes is 0 on 63% of "
                "rows — most sims land a single series in a single minute — so "
                "\"Scan only\" is a near-flat chart by design, not a bug.",
                "Overrun depends on the definition. CT Complete past the "
                "booked end happens on about 2% of sims; Appointment End past "
                "the booked end happens on about 29%. The page defaults to the "
                "appointment-end definition, which is also ARIA-side on both "
                "ends and so valid across all history.",
                "A blank Set Up Note has two meanings — never written, or "
                "written outside the one-day look-back (e.g. drafted days "
                "ahead as prep). The report cannot tell them apart, so note "
                "coverage is not a compliance rate.",
                "Date of Service is editable; Date Entered is not. Anything "
                "built on *_DateOfService can be backdated by the author, "
                "which is why the *_WriteSeconds columns show negative and "
                "hour-scale values. This page does not use Date of Service.",
                "Pre-2025-10-01 does not exist here. The extract is clamped to "
                "that floor because CT image-to-machine attribution began "
                "2025-10-06.",
            ]),
        ),
    ],
)
