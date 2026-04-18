"""Machine Downtime page — UI and data-processing help content."""

from __future__ import annotations

import dash_mantine_components as dmc

from ..renderers import body, bullets, section, subheading


UI_CONTENT = dmc.Stack(
    gap="md",
    children=[
        dmc.Text(
            "The Machine Downtime page reconstructs linac downtime from "
            "indirect evidence — gaps between beams, cancelled appointments, "
            "machine-terminated fields, and daily schedule activity. There is "
            "no single downtime log in ARIA, so the page pulls from three "
            "SQL extracts (Downtime_Gaps, Machine_Error, Downtime_FieldTicks), "
            "combines them into confidence-graded events, and quantifies the "
            "patient impact — cancelled fractions, rerouted patients, and "
            "interrupted courses — across all four treatment machines.",
            size="sm", c="dimmed", style={"lineHeight": 1.6},
        ),

        section(
            "What's on this page",
            "tabler:layout-dashboard",
            body(
                "A six-tile KPI row with sparklines, a narrative summary, a "
                "three-level drill-down (Year → Month → Day) rendered as SVG "
                "cards and heatmaps, a continuous Treatment Activity Strip, "
                "two clientside trend charts, and a full-width detail table.",
            ),

            dmc.Space(h="xs"),

            dmc.Text("KPI row (6 cards, all with sparklines)", fw=600, size="xs", mb=4),
            bullets([
                "Total Downtime (hrs) — gap hours summed across the filtered event set.",
                "Availability (%) — 1 − (downtime hours / operating hours), where "
                "operating hours = workdays × 10h × machines.",
                "Downtime Events — count of event rows matching the active filter rules.",
                "Cancelled Appts — sum of CancelledInGap across events (gap and "
                "full-day outage cancellations).",
                "Patients Rerouted — events with a non-null RerouteMachine.",
                "Courses Interrupted — unique (PatientId, CourseName) pairs where "
                "CancelledInGap > 0 and the patient's outcome wasn't \"Rerouted\".",
            ]),
            body(
                "Each KPI shows a trend vs the prior equivalent window and a "
                "monthly-or-yearly sparkline depending on the date range length.",
            ),

            dmc.Space(h="xs"),

            dmc.Text("Drill-down views", fw=600, size="xs", mb=4),
            bullets([
                "Level 1 — Year Overview cards, one per year in range, with "
                "total-hours and event-count summaries. Rendered as SVG "
                "clientside for speed.",
                "Level 2 — Month heatmap for the selected year: one cell per "
                "(machine, day) colored by downtime severity.",
                "Level 3 — Daily timeline strip showing every beam, image, and "
                "inferred gap on the selected day, per machine. A \"Show "
                "unmatched gaps\" switch lets you reveal gaps that the rule "
                "engine classified as non-events. Uses load_downtime_fields_"
                "for_date — lazy-loaded one day at a time, not pre-aggregated.",
            ]),

            dmc.Space(h="xs"),

            dmc.Text("Treatment Activity Strip", fw=600, size="xs", mb=4),
            body(
                "Continuous view across 3 months / 6 months / 1 year / 3 years "
                "/ all time. Each column is one workday, the Y-axis is time of "
                "day, every beam and inferred gap renders as a small band. "
                "Click a day to drop into Level 3.",
            ),

            dmc.Space(h="xs"),

            dmc.Text("Trend charts (clientside)", fw=600, size="xs", mb=4),
            bullets([
                "Downtime Trend — daily / weekly / monthly hours or events. "
                "Chart type (line / area / bar) and smoothing are clientside toggles.",
                "Patient Impact — cancelled appointments or interrupted courses "
                "over time, Appt mode vs Course mode.",
            ]),

            dmc.Space(h="xs"),

            dmc.Text("Detail table", fw=600, size="xs", mb=4),
            body(
                "One row per event with: Date, Patient, Machine, Start, End, "
                "Duration (min), Type (Gap / StartOfDay / EndOfDay / FullDay), "
                "Classification, Cancellations, Errors, Reroute, Outcome, "
                "Course, Downtime Note, Appointment Note. Column filters "
                "affect the charts above — a \"Table Filtered\" badge appears "
                "in the page header when filters are active. CSV export available.",
            ),
        ),

        section(
            "Filters and the condition builder",
            "tabler:filter",
            dmc.Text("Standard filters", fw=600, size="xs", mb=4),
            bullets([
                "Machine chips — TrueBeamNorth, 21EX, 21iX_CEN, 21iX_AB, 6EX "
                "(retired, off by default). Colored by department.",
                "Date preset + date range picker + month-granularity slider — "
                "all three kept in sync. Default preset is Prior 12 months.",
            ]),

            dmc.Space(h="xs"),

            dmc.Text("Signal filter builder (Filters button)", fw=600, size="xs", mb=4),
            body(
                "The core of the page. A visual condition builder lets you "
                "combine any of the following fields with AND / OR logic across "
                "groups. Each group is internally ALL-of or ANY-of; groups are "
                "then joined by ALL / ANY at the top level.",
            ),
            bullets([
                "GapMinutes — duration of the inferred downtime (slider 10–180 min).",
                "RowType — Intraday Gap, Start of Day, End of Day, Full Day Down.",
                "DowntimeType — Equipment Fault, Vendor Response, Patient "
                "Logistics, Unclassified (derived from the free-text note on the "
                "next appointment using a keyword map in _NOTE_TYPE_MAP).",
                "LocalConfidence — High / Medium / Low. Derived from "
                "per-row evidence scoring: cancelled appointments, machine-"
                "terminated fields, duration vs baseline, note keyword matches.",
                "CancelledInGap — number of appointments cancelled during the gap.",
                "MachineErrorsNearGap — machine-terminated fields within the "
                "gap window.",
                "LastFieldTerminationStatus — set to \"MACHINE\" when the "
                "last delivered field before the gap terminated with reason MACHINE.",
                "EventNote — exists / does not exist — filters for gaps that "
                "have a corresponding appointment note with a downtime keyword.",
                "MUDeliveredPct — percent of planned MU delivered on the last "
                "field before the gap (catches partial-deliveries).",
                "RerouteMachine — whether the patient was rerouted to a "
                "different machine.",
            ]),
            body(
                "Three quick presets: Probable Downtime (evidence-based default), "
                "Cancelled Appts (any event with cancellations), Clear (no filter).",
            ),
        ),

        section(
            "How events are assembled",
            "tabler:link",
            body(
                "The page does not work from a \"downtime\" table — ARIA has "
                "none. Instead it infers events from gaps in the treatment "
                "timeline and then scores each one for confidence.",
            ),

            subheading("Downtime_Gaps (primary source)"),
            body(
                "One row per inferred downtime band: intraday gap between two "
                "beam deliveries, start-of-day gap (first beam later than "
                "expected), end-of-day gap (last beam earlier), or a full-day "
                "outage (no beams delivered on a scheduled workday). Each row "
                "includes GapMinutes, CancelledInGap, PatientOutcome, "
                "RerouteMachine, the appointment note that followed the gap, "
                "and a LocalConfidence rating.",
            ),

            subheading("Machine_Error (secondary source)"),
            body(
                "One row per field that terminated with status = MACHINE. "
                "Used to score LocalConfidence and to populate the "
                "MachineErrorsNearGap signal — a gap that is bracketed by a "
                "MACHINE-terminated field on the prior beam is a near-certain "
                "downtime event.",
            ),

            subheading("Downtime_FieldTicks (drill-down only)"),
            body(
                "Per-beam and per-image ticks for a single day. Only fetched "
                "when a user drills into Level 3 or clicks a column in the "
                "Treatment Activity Strip — loaded lazily via "
                "load_downtime_fields_for_date. Not part of the KPI / chart pipeline.",
            ),

            subheading("Downtime classification (_NOTE_TYPE_MAP)"),
            body(
                "Free-text keywords on the next appointment's note are mapped "
                "to coarse DowntimeType categories — Machine Down / Component "
                "Down / Power → Equipment Fault; Varian Called → Vendor Response; "
                "Patient-logistics phrases → Patient Logistics. Anything "
                "unmatched becomes Unclassified.",
            ),
        ),

        section(
            "How the data is processed",
            "tabler:cpu",
            bullets([
                "Raw gaps are cached at load time (load_downtime_gaps is "
                "functools-cached; a parquet cache backs it for restart speed). "
                "Filter changes re-slice the cached frame, they don't re-query SQL.",
                "Full-day outages and intraday gaps are handled separately for "
                "the cancelled-appts KPI (both contribute) but the hours KPI "
                "treats each full-day outage as 10 hours (the standard operating day).",
                "Availability uses workdays × 10h × machine-count as the "
                "operating-hours denominator, measured over the filter's date "
                "range and machine set.",
                "Trend and Patient Impact charts follow the server/clientside "
                "split — server writes store data, clientside "
                "(smoothChartWithType) renders and re-smooths on toggle changes.",
                "Yearly and monthly drill-down cards are pre-aggregated in "
                "_build_yearly_summary during the main callback so Year → Month "
                "navigation is instant.",
                "The 6EX machine is retired — chip is present but deselected "
                "by default. Events before the machine retired are kept; events "
                "\"on\" 6EX in the current window will be zero.",
                "Prior-period trends use an equal-length window immediately "
                "preceding the selected range (start − period_days to start − 1).",
            ]),
        ),

        section(
            "Known quirks and limitations",
            "tabler:alert-triangle",
            bullets([
                "Downtime is inferred, not logged. An unusually long patient "
                "setup, a lunch break that ran over, or a machine QA block can "
                "all look like downtime gaps. The LocalConfidence rating plus "
                "the default Probable Downtime filter preset are meant to "
                "filter the inference noise, but false positives exist — the "
                "appointment-note signal (EventNote exists) is the strongest "
                "disambiguator when available.",
                "DowntimeType is keyword-based, not dropdown-driven. Notes "
                "without recognizable keywords fall into Unclassified even "
                "when they are clearly describing downtime. Expanding "
                "_NOTE_TYPE_MAP requires a code change.",
                "Machine_Error (load_machine_errors) has no Date column — the "
                "loader uses TreatmentStartTime / TreatmentEndTime for date "
                "filtering and grouping.",
                "Machine → Department mapping is derived (MACHINE_DEPT), not "
                "stored in the extract — if a new machine is deployed it "
                "must be added to config/settings.py to appear correctly.",
                "Level 3 drill-down is lazy-loaded one day at a time. The first "
                "view of a new date takes a fraction of a second longer than "
                "subsequent views (the day's fields get cached).",
                "Courses Interrupted counts unique (PatientId, CourseName). "
                "A patient with two overlapping courses affected by the same "
                "gap counts as 2 — intentional, since clinically they are "
                "separate treatment plans.",
            ]),
        ),
    ],
)
