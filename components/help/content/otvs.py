"""OTVs page — UI and data-processing help content."""

from __future__ import annotations

import dash_mantine_components as dmc

from ..renderers import body, bullets, section, subheading


UI_CONTENT = dmc.Stack(
    gap="md",
    children=[
        dmc.Text(
            "The OTVs page tracks weekly on-treatment visits (OTVs) — the "
            "per-week physician check-ins that occur during a course of "
            "radiation. It focuses on who did the check (treating MD vs. "
            "covering physician), volume by site, and the mix of management "
            "CPT codes billed. Source is the ARIA Weekly Visits extract "
            "(CPT 77427 / 77431).",
            size="sm", c="dimmed", style={"lineHeight": 1.6},
        ),

        section(
            "What's on this page",
            "tabler:layout-dashboard",
            body(
                "A 6-tile KPI row, two chart rows (volume + cumulative, then "
                "coverage + billing), and a full-width collapsible detail "
                "table. Filter state is shared via dcc.Stores and trend charts "
                "use the clientside smoothing / aggregation pattern.",
            ),

            dmc.Space(h="xs"),

            dmc.Text("KPI row (6 cards with sparklines)", fw=600, size="xs", mb=4),
            bullets([
                "Total OTVs — weekly check count for the filtered period.",
                "Lacey — count at Lacey.",
                "Centralia — count at Centralia.",
                "Aberdeen — count at Aberdeen.",
                "Avg per Week — averaged across the period.",
                "Self-rate — percentage of weekly checks where the treating "
                "physician (TreatingPhysician) was also the visit physician "
                "(AppointmentPhysician). High self-rate = low covering activity.",
            ]),

            dmc.Space(h="xs"),

            dmc.Text("Charts", fw=600, size="xs", mb=4),
            bullets([
                "Weekly Check Volume Trend — bar / line / area, weekly / "
                "monthly / yearly. Slice by Total, Treating MD, Completing "
                "(appointment) MD, or Site. Smoothing slider.",
                "Cumulative Weekly Check Volume — running total with Prior "
                "Periods overlay and a projection line option. Toggle between "
                "calendar and rolling windows.",
                "Coverage Analysis — matrix of Treating Physician (rows) vs "
                "Appointment Physician (columns). Off-diagonal cells are "
                "covering-physician weekly checks — \"who covered whom, and "
                "how often\".",
                "Billing — CPT code distribution for the filtered weekly "
                "checks (77427, 77431, etc.). Slice by Total, Treating MD, "
                "Completing MD, or Site; toggle between count and percent.",
            ]),

            dmc.Space(h="xs"),

            dmc.Text("Detail table", fw=600, size="xs", mb=4),
            body(
                "One row per weekly-check appointment — Date, Patient, Course, "
                "Department, Treating MD, Appointment MD, CPT code. Sortable, "
                "column-filterable, CSV export. The \"Table Filtered\" badge "
                "lights when any column filter is active.",
            ),
        ),

        section(
            "Filters",
            "tabler:filter",
            bullets([
                "Date preset + slider + manual DatePickerRange — anchored to "
                "AppointmentDateTime.",
                "Department chips — Lacey / Centralia / Aberdeen, multi-select.",
                "Treating MD — single-select, driven by TreatingPhysician "
                "(the physician on the course).",
                "Completing MD — single-select, driven by AppointmentPhysician "
                "(who actually saw the patient that week).",
                "Diagnosis accordion — body-system picker with Primary / All "
                "mode toggle; matches via DiagnosisCodes join.",
                "Inpatient switch — include or exclude inpatient visits.",
                "Smoothing slider — shared across trend charts.",
            ]),
        ),

        section(
            "How the data is processed",
            "tabler:cpu",
            bullets([
                "Source loader is load_weekly_visits() which reads from the "
                "Incremental/WeeklyVisits directory. Department is already "
                "clean (no * prefix) at load time.",
                "Rows are filtered to ActivityStatus in (\"Completed\", "
                "\"Manually Completed\") at the page level — scheduled but "
                "not-yet-delivered weekly checks are excluded.",
                "Self-rate compares TreatingPhysician to AppointmentPhysician "
                "per row. A null on either side drops the row from the "
                "denominator.",
                "The Coverage matrix aggregates rows by (TreatingPhysician, "
                "AppointmentPhysician) — diagonal = self-performed, "
                "off-diagonal = covering.",
                "Data-relative dates anchor every KPI and chart to "
                "max(AppointmentDateTime) — not wall-clock today.",
                "Server/clientside split — volume and cumulative charts use "
                "dcc.Stores (otvs-store-volume, otvs-store-cumulative, "
                "otvs-store-kpi-sparklines). Aggregation, smoothing, and "
                "chart-type switching run clientside.",
            ]),
        ),

        section(
            "Counting semantics",
            "tabler:calculator",
            bullets([
                "One row = one weekly-check appointment. Total OTVs is the row "
                "count after filters.",
                "CPT 77427 = five fractions of on-treatment management; CPT "
                "77431 = one-to-two-fraction course management. Billing chart "
                "shows the distribution directly.",
                "Coverage Analysis counts visits, not distinct patients — a "
                "covering physician who ran three weekly checks for one "
                "patient in a single course shows as 3 in that cell.",
                "Self-rate is computed at the visit level, not the "
                "patient / course level.",
            ]),
        ),

        section(
            "Related page — OTV Audit",
            "tabler:info-circle",
            body(
                "This page is volume-focused. The compliance side — audit "
                "results (OK / Too Few / Extra Visit(s)) from the OTV Audit "
                "extract — would live in a separate audit view. The spec calls "
                "for load_otv_audit() integration for compliance KPIs and an "
                "audit-result distribution chart; the current implementation "
                "focuses on Weekly Visits only.",
            ),
        ),

        section(
            "Known quirks and limitations",
            "tabler:alert-triangle",
            bullets([
                "Covering patterns only show up where AppointmentPhysician is "
                "populated and differs from TreatingPhysician. If a covering "
                "MD signs a weekly note without the appointment being "
                "re-attributed in ARIA, the row falsely reads as self-performed.",
                "The page applies a \"completed only\" filter — a weekly "
                "check that was scheduled but cancelled / no-showed won't "
                "appear anywhere on the page, even when the status filter "
                "widens elsewhere.",
                "CPT 77431 (short-course management) can apply to the whole "
                "course, not to a single week — billing counts of 77431 "
                "should not be interpreted as \"one check per unit\" the "
                "way 77427 can be.",
            ]),
        ),
    ],
)
