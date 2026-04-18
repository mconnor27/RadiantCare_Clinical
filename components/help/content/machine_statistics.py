"""Machine Statistics page — UI and data-processing help content."""

from __future__ import annotations

import dash_mantine_components as dmc

from ..renderers import body, bullets, section, subheading


UI_CONTENT = dmc.Stack(
    gap="md",
    children=[
        dmc.Text(
            "The Machine Statistics page is the lifetime-and-yearly view of "
            "each linac's career — how many patients, sessions, fractions, "
            "fields, and total dose it has delivered, how old it is, and how "
            "its year-over-year throughput has trended. It's the long-horizon "
            "companion to the Machine Downtime page: Downtime answers \"what's "
            "happening now\" and Statistics answers \"what has this machine "
            "done in its life.\"",
            size="sm", c="dimmed", style={"lineHeight": 1.6},
        ),

        section(
            "What's on this page",
            "tabler:layout-dashboard",
            body(
                "An aggregate KPI row, one card per machine with "
                "per-machine totals and a mini sparkline, a machine-age "
                "timeline Gantt, and four yearly trend charts (Sessions / "
                "Patients / Avg Dose per Fraction / Fields per Fraction).",
            ),

            dmc.Space(h="xs"),

            dmc.Text("Aggregate KPI row (5 cards)", fw=600, size="xs", mb=4),
            bullets([
                "Total Patients — unique patients across the selected machines.",
                "Total Sessions — billing/treatment session count.",
                "Total Fractions — delivered fractions.",
                "Total Dose — cumulative delivered dose, in Gy.",
                "Total Fields — delivered treatment fields.",
            ]),
            body(
                "All KPIs are lifetime totals for the machines currently "
                "selected — no date filter applies to the KPI row.",
            ),

            dmc.Space(h="xs"),

            dmc.Text("Per-machine cards", fw=600, size="xs", mb=4),
            body(
                "One card per selected machine, in chip order. Shows a "
                "status badge (Active / Retired — retired = no treatment in "
                "the last 365 days), department, patient / session / fraction "
                "/ dose / field totals, average Gy per fraction, an operating-"
                "life range (\"Since Feb 2013 · 12.1 years\"), and a small "
                "sparkline of annual session counts. Left border is colored "
                "by machine.",
            ),

            dmc.Space(h="xs"),

            dmc.Text("Machine Age Timeline", fw=600, size="xs", mb=4),
            body(
                "Horizontal Gantt — one row per machine. Each bar spans from "
                "the machine's first treatment date (OperatingLife) to its "
                "most recent treatment (MostRecentTreatment, or today for "
                "active machines). Retired machines render at lower opacity. "
                "Label inside the bar shows years-of-life.",
            ),

            dmc.Space(h="xs"),

            dmc.Text("Yearly trend charts (4, clientside)", fw=600, size="xs", mb=4),
            bullets([
                "Sessions by Year — toggle between Sessions and Fractions. "
                "Area / Line / Bar types with smoothing and stack-vs-grouped.",
                "Patients by Year — same chart controls.",
                "Avg Dose per Fraction (Gy) — always grouped (no stack makes "
                "sense for a ratio).",
                "Fields per Fraction — computed ratio TotalFields / "
                "TotalFractions per year × machine.",
            ]),
            body(
                "Each chart has Area / Line / Bar chart types, a smoothing "
                "slider, and all four share the same server callback that "
                "writes raw yearly data to four dcc.Stores.",
            ),
        ),

        section(
            "Filters",
            "tabler:filter",
            bullets([
                "Machine chips — TrueBeamNorth, 21EX, 21iX_CEN, 21iX_AB, 6EX. "
                "Multi-select; labels are display names (\"TrueBeam North\", "
                "\"21iX Centralia\", \"21iX Aberdeen\", \"6EX (Retired)\").",
                "Data section — Real Patients (clinical treatments only) or "
                "All Data (includes QA, research, and test patients). Switches "
                "which sections of the Machine_Statistics extract are used "
                "(3-Real Patients vs 1-All Data for lifetime; 4-Real Patients "
                "by Year vs 2-All Data by Year for yearly).",
                "Current Year handling — Project YTD / Actual YTD / Exclude. "
                "Controls how the current (partial) year appears in the "
                "yearly trend charts (see below).",
            ]),
        ),

        section(
            "How the data is processed",
            "tabler:cpu",
            bullets([
                "Source: load_machine_statistics() — a single extract with a "
                "Section column that separates four views of the same data "
                "(lifetime × real-patients, lifetime × all-data, yearly × "
                "real-patients, yearly × all-data). The Data filter picks one "
                "lifetime slice and its matching yearly slice.",
                "Current-year handling — the Machine_Statistics extract "
                "reports the current year as a partial-year row. Project YTD "
                "scales patients / sessions / fractions / dose / fields by "
                "(365.25 / day-of-year) to estimate the full-year value; "
                "Actual YTD leaves the partial value as-is; Exclude drops the "
                "current-year row from the trend charts.",
                "Avg Dose per Fraction for the projected current year is "
                "recomputed from the projected totals (dose / fractions) "
                "rather than scaled directly, preserving the ratio semantics.",
                "Yearly stores are built as census-style {dates, series, "
                "yTitle, stacked, chartId} payloads keyed by machine — the "
                "shared clientside census namespace renders them.",
                "All four yearly trend charts share one server callback for "
                "efficiency; the Sessions/Fractions toggle drives which "
                "column feeds the Sessions-by-Year store.",
                "Machine age timeline uses OperatingLife (first treatment) "
                "and MostRecentTreatment from the lifetime rows. A machine "
                "with no MostRecentTreatment defaults to today so active "
                "machines extend to the right edge.",
                "Retired detection: MostRecentTreatment > 365 days ago. 6EX "
                "is retired under this rule.",
                "Refresh interval: 10 minutes (the page data changes slowly).",
            ]),
        ),

        section(
            "Known quirks and limitations",
            "tabler:alert-triangle",
            bullets([
                "No date filter — the page is lifetime-scoped by design. If "
                "you need a specific date window, use the Operations or "
                "Machines pages instead.",
                "\"All Data\" includes QA and test patients and will produce "
                "higher counts than Real Patients, particularly for Fields "
                "and Sessions. Clinical reporting should always use Real "
                "Patients.",
                "Project YTD assumes the year's throughput is linear. On "
                "machines with seasonal variation (e.g., vacation dips, "
                "holiday weeks) the projection will overshoot or undershoot. "
                "Use Actual YTD or Exclude for a cleaner trend line.",
                "Operating life dates come from the extract's OperatingLife "
                "column which is \"first treatment on record in ARIA\" — not "
                "the physical install date. If ARIA was migrated onto a "
                "pre-existing machine, the true operating life is longer "
                "than shown.",
                "6EX is retired — its lifetime totals remain but its "
                "yearly-trend series will end at the last active year.",
            ]),
        ),
    ],
)
