"""Simulations page — UI and data-processing help content."""

from __future__ import annotations

import dash_mantine_components as dmc

from ..renderers import body, bullets, section, subheading


UI_CONTENT = dmc.Stack(
    gap="md",
    children=[
        dmc.Text(
            "The Simulations page tracks CT simulation volume, the timing "
            "intervals around each sim (consult-to-sim, sim-to-treatment, "
            "consult-to-treatment), re-simulation rate, and the daily sim "
            "scheduling window. Data comes from the ARIA Simulations extract, "
            "which already carries a per-row Department column (no Patient-to-"
            "Department merge is needed on this page any more).",
            size="sm", c="dimmed", style={"lineHeight": 1.6},
        ),

        section(
            "What's on this page",
            "tabler:layout-dashboard",
            body(
                "A 6-tile KPI row, five chart cards across three rows, and a "
                "full-width detail table. Filter state is shared via dcc.Stores "
                "and chart toggles (chart type, smoothing, aggregation) run "
                "clientside.",
            ),

            dmc.Space(h="xs"),

            dmc.Text("KPI row (6 cards with sparklines)", fw=600, size="xs", mb=4),
            bullets([
                "Total Simulations — count for the filtered period.",
                "Initial Sims — count excluding re-simulations.",
                "Median Lead — median DaysFromClinicExamToSimulation.",
                "Median Consult-to-Sim — alternate cut of the consult→sim gap.",
                "Median Time to Treatment — median DaysFromSimToTreatment.",
                "Re-Sim Rate — percentage of sims where ActivityName contains "
                "\"Re-Simulation\".",
            ]),

            dmc.Space(h="xs"),

            dmc.Text("Charts", fw=600, size="xs", mb=4),
            bullets([
                "Simulation Volume Trend — line / bar / area, weekly / monthly / "
                "yearly. Slice by Total, Sim Type, Department, Machine, or "
                "Physician. Smoothing slider.",
                "Cumulative Sim Volume — running total with Prior Periods overlay "
                "and an optional projection line to period end. Toggle between "
                "calendar and rolling period windows.",
                "Timing Intervals — median consult→sim, sim→treatment, and "
                "consult→treatment days over time. Metric toggle picks which "
                "interval is shown; slice-by splits by department or physician.",
                "Schedule Ribbon — per-day sim operating window across the full "
                "history. Can render as Ribbon (fill between earliest start and "
                "latest end-of-day), Bar (sim count), or Line. Machine toggle "
                "filters to a single sim machine (CT_Sim, CT_CEN).",
                "Cancellation Rate — cancelled-sim fraction over time.",
                "Diagnosis Mix — body-system distribution of the filtered sims "
                "with a current-vs-prior compare mode.",
                "Billing — CPT code distribution for sim-associated charges.",
            ]),

            dmc.Space(h="xs"),

            dmc.Text("Simulation Detail table", fw=600, size="xs", mb=4),
            body(
                "One row per simulation — Date, Patient, Sim Type, Duration, "
                "Physician, Days from Consult, Days to Treatment, CPT Codes. "
                "Sortable, column-filterable, CSV export.",
            ),
        ),

        section(
            "Filters",
            "tabler:filter",
            bullets([
                "Date preset + slider + manual DatePickerRange — anchored to "
                "ScheduledDateTime.",
                "Department chips — Lacey / Centralia / Aberdeen.",
                "Physician — single-select. Role toggle switches between the "
                "consult physician (who saw the patient) and the supervising "
                "physician on the sim.",
                "Sim Type — multi-select of ActivityName values (Initial "
                "Simulation, Stereotactic Simulation, Re-Simulation, Initial "
                "Centralia-in-Lacey, Initial Aberdeen Simulation).",
                "Machine — multi-select of SimulationResource values (CT_Sim, "
                "CT_CEN).",
                "Re-sim scope — toggles whether re-sims are counted as "
                "\"resim of the original consult\" or as \"new sim with a "
                "separate lead time\".",
                "Volume scope — all sims vs. initial-only.",
                "Inpatient switch — include or exclude inpatient consults.",
                "Weekend switch — include or exclude weekend sims.",
                "Smoothing slider — shared across all trend charts.",
            ]),
        ),

        section(
            "How the data is processed",
            "tabler:cpu",
            bullets([
                "Source loader is load_simulations(), which reads from "
                "Incremental/Simulations and concatenates date-suffixed "
                "increment files. ActivityStatus is normalized to Status at "
                "load time. Recent extracts carry Department directly per row, "
                "plus SimulationResource, ActivityNote, InPatientFlag, "
                "TreatmentStatus, TreatmentModality, ScheduledTreatmentDate, "
                "and DaysToScheduledTreatment.",
                "The _patient_department_map() merge that earlier versions of "
                "this page used is no longer needed — Department is authoritative "
                "on each sim row.",
                "Timing KPIs use the pre-computed DaysFromClinicExamToSimulation, "
                "DaysFromSimToTreatment, and DaysFromClinicExamToTreatment "
                "columns rather than re-joining to Clinic Visits or Treatment "
                "Detail.",
                "Re-sim rate uses a case-insensitive substring match on "
                "ActivityName for \"Re-Simulation\".",
                "The Schedule Ribbon spans the full history of the extract, "
                "not just the current date filter — earliest ScheduledDateTime "
                "time-of-day and latest ScheduledDateTime + Duration per day "
                "form the top and bottom edges of a filled band (6 AM – 8 PM "
                "clip).",
                "Data-relative dates anchor every KPI and chart to max("
                "ScheduledDateTime) in the extract, not wall-clock today — "
                "protects against overnight-export lag.",
                "Server/clientside split — the server fills dcc.Stores "
                "(sim-store-volume, sim-store-timing, sim-store-ribbon, "
                "sim-store-cumulative, sim-store-cancel, sim-store-kpi-"
                "sparklines). Chart-type, smoothing, and aggregation toggles "
                "run clientside.",
            ]),
        ),

        section(
            "Counting semantics",
            "tabler:calculator",
            bullets([
                "One row = one simulation appointment. Total Sims is the row "
                "count after filters.",
                "Initial vs re-sim is based on ActivityName substring — a patient "
                "getting 3 sims in a course shows as 1 initial + 2 re-sims.",
                "Cancellation rate divides by total sims (attended + cancelled). "
                "Cancelled sims are removed from the volume chart unless the "
                "Status widen toggle is active.",
                "Timing medians drop nulls — consults that never reached sim, "
                "and sims that never reached treatment, don't contribute to the "
                "denominator.",
            ]),
        ),

        section(
            "Known quirks and limitations",
            "tabler:alert-triangle",
            bullets([
                "DaysToScheduledTreatment is a newer column — sim rows from "
                "earlier periods may have it null. The timing chart's "
                "\"scheduled\" metric falls back to the delivered equivalent "
                "when null.",
                "Sim type \"Initial Centralia-in-Lacey\" is a workflow label — "
                "it identifies Centralia patients simmed on the Lacey CT. These "
                "count as Lacey sims for volume purposes but follow the "
                "Centralia treatment course.",
                "The Schedule Ribbon always uses the full sim history. It "
                "ignores the date slider so you can see long-run schedule "
                "shifts; machine and department filters do apply.",
                "Re-sims share a course with their original consult, so the "
                "same DaysFromClinicExamToSimulation value appears on multiple "
                "sim rows. The re-sim scope toggle controls whether that's "
                "treated as a loopback or a separate measurement.",
            ]),
        ),
    ],
)
