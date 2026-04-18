"""Clinic Visits page — UI and data-processing help content."""

from __future__ import annotations

import dash_mantine_components as dmc

from ..renderers import body, bullets, section, subheading


UI_CONTENT = dmc.Stack(
    gap="md",
    children=[
        dmc.Text(
            "The Clinic Visits page tracks consult, follow-up, and virtual "
            "appointment volume, lead times, and downstream conversion to "
            "simulation. It answers: how many consults are we doing, how long "
            "are patients waiting to get in, and what fraction end up getting "
            "a sim? Data comes from the ARIA Clinic Visits extract, joined to "
            "the Diagnosis lookup and Billing where needed.",
            size="sm", c="dimmed", style={"lineHeight": 1.6},
        ),

        section(
            "What's on this page",
            "tabler:layout-dashboard",
            body(
                "A 6-tile KPI row, six chart cards arranged in three rows, and a "
                "full-width detail table at the bottom. Filter state is shared "
                "across the page via dcc.Stores so every card re-renders together.",
            ),

            dmc.Space(h="xs"),

            dmc.Text("KPI row (6 cards, each with sparkline)", fw=600, size="xs", mb=4),
            bullets([
                "Total Visits — total count for the filtered period.",
                "Consults — visits classified as new consults.",
                "Follow-Ups — follow-up and established-patient visits.",
                "Median Lead Time — days from request creation to scheduled "
                "appointment (DaysFromCreatedToAppt).",
                "Sim Conversion — percentage of consults where "
                "HasSimulationWithin180Days = 1.",
                "Median Days to Sim — median of DaysToSimulation for consults only.",
            ]),

            dmc.Space(h="xs"),

            dmc.Text("Charts", fw=600, size="xs", mb=4),
            bullets([
                "Visit Volume Trend — line / bar / area, weekly / monthly / yearly "
                "aggregation. Slice by Total, Visit Type, Classified Type, "
                "Department, or Physician. Smoothing slider.",
                "Cumulative Visit Volume — running total with Prior Periods "
                "overlay and optional projection to period end. Toggle between "
                "calendar and rolling period windows.",
                "Lead Time Trend — median DaysFromCreatedToAppt over time. "
                "Slice by Total, Visit Type, Department, or Physician.",
                "Consult-to-Sim Conversion — percentage trend of consults that "
                "reach simulation within 180 days.",
                "Cancellation Rate — cancelled / no-show fraction over time.",
                "Diagnosis Mix — horizontal bar of visit counts by body-system "
                "diagnosis category; supports a current-vs-prior compare mode.",
                "Billing — CPT code or code-group distribution for the filtered "
                "visits, count or percent.",
            ]),

            dmc.Space(h="xs"),

            dmc.Text("Visit Detail table", fw=600, size="xs", mb=4),
            body(
                "One row per clinic visit — Date, Patient, Department, Physician, "
                "Visit Type, Duration, Lead Time (days), Has Sim flag, Days to Sim, "
                "Diagnosis, Payor. Sortable, column-filterable, CSV export. The "
                "\"Table Filtered\" badge in the filter bar lights up when any "
                "column filter is active.",
            ),
        ),

        section(
            "Filters",
            "tabler:filter",
            bullets([
                "Date preset + slider + manual DatePickerRange — all anchored to "
                "ScheduledDateTime.",
                "Department chips — Lacey / Centralia / Aberdeen, multi-select.",
                "Physician — single-select. Role toggle switches the physician "
                "source between AppointmentPhysician (who saw the patient) and "
                "the treating physician attached to the course.",
                "Visit type — raw ActivityName values (Consult, New Patient Visit, "
                "Follow-Up, etc.).",
                "Classified type — the normalized bucket (Consult / Follow-Up / "
                "Virtual / Other) produced by _classify_visit_type from the raw "
                "ActivityName.",
                "Status — defaults to Attended; can widen to include cancellations "
                "and no-shows.",
                "Inpatient switch — include or exclude inpatient consults.",
                "Weekend switch — include or exclude weekend visits (mostly urgent "
                "inpatient consults).",
                "Smoothing slider — shared across all trend charts.",
            ]),
        ),

        section(
            "How the data is processed",
            "tabler:cpu",
            bullets([
                "Source loader is load_clinic_visits() which reads from the "
                "Incremental/ClinicVisits directory and concatenates date-suffixed "
                "increment files. DepartmentName is normalized to Department and "
                "ActivityStatus is normalized to Status at load time.",
                "Visit type is derived, not stored — _classify_visit_type looks "
                "at ActivityName and returns Virtual / Consult / Follow-Up / "
                "Other. Anything containing \"virtual\" wins first, then "
                "\"consult\", then \"follow\" or \"f/u\".",
                "Sim conversion uses the pre-computed HasSimulationWithin180Days "
                "flag on consult rows — the page doesn't re-derive it from the "
                "Simulations extract.",
                "Cancel rate uses a case-insensitive substring match on Status "
                "for \"cancel\" or \"no-show\".",
                "Diagnosis mix joins DiagnosisCodes (comma-separated) to the "
                "Diagnosis lookup via build_code_to_category to resolve each "
                "visit's body-system group. Visits can have multiple codes — "
                "the primary category is used in Primary mode; all categories "
                "are counted in All mode.",
                "All KPIs and charts use data-relative dates anchored to the "
                "max ScheduledDateTime in the extract — not wall-clock today. "
                "Prior-period comparison windows on the Cumulative chart shift "
                "relative to that same anchor.",
                "Trend charts use the server/clientside split — the server loads "
                "the filtered data into dcc.Stores (cv-store-volume, cv-store-"
                "lead, cv-store-conversion, cv-store-cumulative, cv-store-cancel, "
                "cv-store-kpi-sparklines). Clientside callbacks handle chart-type "
                "switching, smoothing, and aggregation without a server round-trip.",
            ]),
        ),

        section(
            "Counting semantics",
            "tabler:calculator",
            bullets([
                "One row = one clinic-visit appointment. Total Visits is a simple "
                "row count after filters.",
                "Consults and Follow-Ups counts are based on the derived "
                "classified-type bucket, so an ARIA rename from \"Consult\" to "
                "\"New Patient Visit\" doesn't silently drop counts.",
                "Conversion rate is computed on consults only (follow-ups and "
                "virtuals are excluded from the denominator).",
                "Median Days to Sim excludes consults that never converted — "
                "DaysToSimulation is null on those rows.",
            ]),
        ),

        section(
            "Known quirks and limitations",
            "tabler:alert-triangle",
            bullets([
                "HasSimulationWithin180Days is populated by the SQL at export "
                "time. Recent consults (< 180 days old) that haven't had a sim "
                "yet will show as non-converted even if they're still on track "
                "to sim — the conversion KPI underestimates the true rate for "
                "the last 6 months and stabilizes only for older cohorts.",
                "Virtual visits are a recent addition and may not have "
                "DaysFromCreatedToAppt populated on earlier rows — the lead-time "
                "KPI and chart drop nulls silently.",
                "The physician-role toggle swaps which person the physician "
                "filter maps to. Switching from Appointment to Treating can "
                "change visit counts if covering physicians frequently ran a "
                "different person's clinic.",
                "Diagnosis mix relies on DiagnosisCodes being populated. "
                "Historical rows before mid-2021 often have nulls — those "
                "visits render in an \"Unclassified\" bucket.",
            ]),
        ),
    ],
)
