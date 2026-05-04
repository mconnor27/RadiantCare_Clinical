"""Operations page — UI and data-processing help content."""

from __future__ import annotations

import dash_mantine_components as dmc

from ..renderers import body, bullets, section, subheading


UI_CONTENT = dmc.Stack(
    gap="md",
    children=[
        dmc.Text(
            "The Operations page is the department's day-to-day view of scheduling, "
            "throughput, and machine utilization. It pairs past-and-present activity "
            "(from the DailyVolume_Past and Treatment extracts) with a 14-day forward "
            "projection (from DailyVolume_Future) so clinical staff can see today's "
            "workload plus what's coming.",
            size="sm", c="dimmed", style={"lineHeight": 1.6},
        ),

        section(
            "What's on this page",
            "tabler:layout-dashboard",
            body(
                "A 7-tile KPI row, four main chart areas, and a detail table at the bottom. "
                "Filter state (department, machine, date preset, date range) is shared "
                "across the page via dcc.Stores — change one filter and every card and "
                "chart re-renders in lockstep.",
            ),

            dmc.Space(h="xs"),

            dmc.Text("KPI row (7 cards)", fw=600, size="xs", mb=4),
            bullets([
                "Today's Treatments — appointment count plus a per-site (Lacey / "
                "Centralia / Aberdeen) breakdown. 30-weekday sparkline.",
                "Operating Hours × 3 — one card per site, showing the day's first-to-"
                "last scheduled and actual hours.",
                "Consult Lead — days from request to first scheduled consult.",
                "Sim Lead — days from consult to completed simulation.",
                "New Starts — count of patients whose first-fraction treatment is today "
                "or the forward window.",
            ]),
            body(
                "All KPIs show a trend arrow (vs the prior equivalent window) and "
                "render on a fixed 30-weekday sparkline so the visuals stay comparable "
                "across filter changes.",
            ),

            dmc.Space(h="xs"),

            dmc.Text("Charts", fw=600, size="xs", mb=4),
            bullets([
                "Treatments chart — area / line / bar with Daily / Weekly / Monthly "
                "aggregation, a 30d / 60d / 90d / 180d / 1y / All range selector, and a "
                "shared smoothing slider. Projects 14 days forward from the last "
                "available data date.",
                "Upcoming 4 Weeks heatmap — rows are machines + clinic / sim slots, "
                "columns are the next 20 weekdays. A Scope toggle (Consults only vs "
                "All) changes which activity types fill the cells.",
                "Hours Ribbon — per-site opening / closing times over the selected "
                "range, rendered as a wide compact ribbon.",
                "Resource Utilization — per-machine utilization %, active minutes, or "
                "beam-on minutes. Metric toggle + machine chip group + aggregation + "
                "range selector. Utilization % is capped at 150% to prevent outliers "
                "from squashing the scale. See \"What the minute metrics measure\" "
                "below for definitions.",
            ]),

            dmc.Space(h="xs"),

            dmc.Text("Daily Detail table", fw=600, size="xs", mb=4),
            body(
                "One row per date × (location or machine) depending on the View-by "
                "toggle. Columns: Date, Location / Machine, Appts, Completed, Patients, "
                "Plans, New Starts, first-scheduled / first-actual / last times, plus "
                "the four minute breakdowns (Scheduled Active, Actual Active, Beam-On, "
                "Appt). The Include Future switch appends the 14-day projection; future "
                "rows show the forecast but zero Completed / Patients / New Starts.",
            ),
        ),

        section(
            "What the minute metrics measure",
            "tabler:clock-hour-8",
            body(
                "Four non-overlapping-minute totals per machine per day, each "
                "computed with the same interval-merging algorithm — sort "
                "intervals by start time, detect new groups wherever a start "
                "exceeds the running max of prior ends, merge within each group, "
                "sum the merged durations. Two 30-minute appointments that "
                "overlap by 15 minutes therefore count as 45 minutes, not 60.",
            ),

            subheading("Scheduled Active Minutes"),
            body(
                "Source: DimActivityTransaction — scheduled treatment appointments "
                "(ActivityCategoryENU = 'treatment', 21 allowed activity names) "
                "plus scheduled simulation appointments on DimResourceID 1 (CT_Sim) "
                "and 17 (CT_CEN). Interval: AppointmentDateTime → ScheduledEndTime. "
                "Counts the minutes of the day reserved for the machine on the "
                "schedule, with overlap removed.",
            ),

            subheading("Appointment Actual Minutes (ApptActualMinutes)"),
            body(
                "Same DimActivityTransaction rows as Scheduled Active, but using "
                "ActivityStartDateTime → ActivityEndDateTime — the timestamps "
                "therapists record when they activate the appointment in Mosaiq "
                "and when they mark it complete. Captures room-in to room-out "
                "for every patient on the machine that day.",
            ),

            subheading("Actual Active Minutes"),
            body(
                "Source: FactTreatmentHistory field-level rows where FieldStatus is "
                "'treated' or 'pt. treated', plus CBCT / kV events from "
                "FactPatientImage (filtered by a temporal EXISTS clause to 30 "
                "minutes before the patient's first beam on that machine+date "
                "through their last beam end). Computed in two steps:",
            ),
            bullets([
                "Per-patient session detection with three triggers: first field on "
                "the day, >60-min gap since the patient's previous field, OR "
                "another patient was treated in between this patient's consecutive "
                "fields (interleaving). Each (patient, machine, date, session) "
                "collapses to one interval — MIN(start) → MAX(end).",
                "Patient-session intervals then merged across all patients on "
                "that machine+date, and the merged durations summed.",
            ]),
            body(
                "The result: non-overlapping minutes where the machine was engaged "
                "with a patient, from imaging setup through the last beam-on. The "
                "BID / interleaving logic prevents a single patient's AM+PM fields "
                "from collapsing into one 6-hour interval that would then absorb "
                "every other patient treated that day.",
            ),

            subheading("Beam On Minutes"),
            body(
                "Source: FactTreatmentHistory WHERE IsImage = 0 — therapeutic beam "
                "deliveries only; no imaging, no port films. Interval: "
                "TreatmentStartTime → TreatmentEndTime per beam. Merged across all "
                "beams on the machine+date (no patient-session step needed because "
                "beams within a single fraction are contiguous). The #TreatmentData "
                "build uses SELECT DISTINCT on (machine, site, date, start, end, "
                "patient, IsImage) first — a VMAT / IMRT field with 20 reference "
                "points would otherwise produce 20 identical timestamp rows and "
                "inflate Beam On by 10–20×.",
            ),

            subheading("The gaps between metrics tell the operational story"),
            bullets([
                "Scheduled Active vs Appt Actual — scheduling accuracy. Actual "
                "shorter means appointments run faster than planned; actual "
                "longer means blocks regularly overrun.",
                "Appt Actual vs Actual Active — room-turnover overhead. Time the "
                "patient was in the appointment (activated → complete) but the "
                "machine wasn't imaging or delivering (check-in, setup before "
                "imaging started, post-treatment exit).",
                "Actual Active vs Beam On — imaging and between-beam overhead. "
                "VMAT / IMRT with CBCT pre-imaging has a much wider gap here "
                "than a simple palliative fraction on 2D portal films.",
            ]),

            dmc.Alert(
                color="yellow", variant="light",
                title="Data transition at 2025-10-06",
                mt="sm",
                children=dmc.Text(
                    "FactPatientImage only began capturing ImageType = 'Image' "
                    "(CBCT volumetric reconstructions) on treatment machines on "
                    "2025-10-06. Before that date the source table held DRRs and "
                    "portal images only — a small subset of patients. After it, "
                    "nearly every patient has a CBCT record, which pushes Actual "
                    "Active session starts ~2–4 min earlier to include imaging "
                    "setup. Actual Active therefore jumps 2–4× at the transition "
                    "across all machines. Pre / post comparison is not apples-to-"
                    "apples — use Beam On for long-term trend analysis and Actual "
                    "Active for post-cutoff operational insights.",
                    size="xs",
                ),
            ),

            subheading("Utilization %"),
            body(
                "ActualActiveMinutes / ScheduledActiveMinutes per machine per "
                "aggregation period. Values > 100% are normal on heavy-overrun "
                "days (the machine ran past its scheduled stop time); capped at "
                "150% so a single runaway day doesn't squash the scale.",
            ),
        ),

        section(
            "Data sources and loaders",
            "tabler:database-import",
            bullets([
                "load_daily_volume() — past per-machine daily minute metrics from "
                "DailyVolume_Past.sql.",
                "load_daily_volume_future() — forward-looking schedule (14 days) from "
                "DailyVolume_Future.sql.",
                "load_daily_volume_by_resource() — per-machine active / scheduled / "
                "beam-on minutes used for the utilization chart.",
                "load_treatment() — completed appointments, unique patients, unique "
                "plans, new starts per date × department.",
                "load_clinic_visits() and load_simulations() — consult and sim slots "
                "that fill the Upcoming 4 Weeks heatmap.",
                "load_schedule_upcoming() — exam / sim HOLD slots so the heatmap can "
                "show where there's still bookable capacity.",
            ]),
        ),

        section(
            "How the data is processed",
            "tabler:cpu",
            bullets([
                "Date anchor is data-relative — the page uses max(ScheduledDate) "
                "across the past extract as \"today\" rather than wall-clock today. "
                "Protects against overnight-export delays that would otherwise blank "
                "out the KPIs.",
                "Server loads the full extract into a dcc.Store once per filter "
                "change; clientside callbacks (smoothChartWithTypeAndRange, "
                "renderWithFilters) do the range / aggregation / smoothing without "
                "a server round-trip. Applies to the Treatments and Resource "
                "Utilization charts.",
                "Daily aggregation filters to weekdays only — weekend rows never "
                "produce bars. Weekly and monthly aggregations use pandas resample.",
                "Bar charts on ranges > 90 days automatically flip to a line chart to "
                "avoid visually unreadable density.",
                "Smoothing slider max dynamically adjusts to the selected range, so a "
                "0.5 smoothing on 90 days is comparable to 0.5 on a year.",
                "Patient / completed / new-start counts come from the pre-aggregated "
                "Treatment extract (UniquePatients, CompletedAppointments, "
                "NewStartsCourse columns). The page does not re-dedup patient IDs — "
                "the SQL already did that with the 3-trigger session detection.",
                "\"Lacey\" is a logical department that spans multiple machines "
                "(TrueBeamNorth, 21EX, 6EX). When a machine filter is active, the "
                "page maps machines back to their parent department for KPIs and "
                "department-colored series; the detail table can toggle to show raw "
                "machine names.",
            ]),
        ),

        section(
            "Known quirks and limitations",
            "tabler:alert-triangle",
            bullets([
                "Future projection covers 14 days. Beyond that the charts and KPIs "
                "show blanks; the heatmap fills at most 4 weeks (weekdays) and uses "
                "the availability extract for anything past day 14.",
                "Non-bookable sim HOLD slots are dropped before the heatmap counts "
                "open capacity — they would otherwise imply free capacity that "
                "doesn't actually exist. The 8 AM 30-min linac warm-up placeholder "
                "is dropped at the loader layer (so every consumer sees a clean "
                "feed); the lunch hold (hour=12) is filtered here at the page "
                "level because some pages may want to surface it.",
                "The detail table's Include Future toggle shows the forecast for "
                "appointment count and minute metrics, but Completed, Patients, and "
                "New Starts are zero in future rows because those columns come from "
                "the Treatment extract which only covers dates ≤ today.",
            ]),
        ),
    ],
)
