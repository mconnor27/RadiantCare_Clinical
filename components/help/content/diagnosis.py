"""Diagnosis page — UI and data-processing help content."""

from __future__ import annotations

import dash_mantine_components as dmc

from ..renderers import body, bullets, section, subheading


UI_CONTENT = dmc.Stack(
    gap="md",
    children=[
        dmc.Text(
            "The Diagnosis page is a cross-cutting view of diagnosis-category "
            "mix — it answers \"what body systems are driving volume, and is "
            "the mix shifting?\" across any of seven activity datasets "
            "(consults, follow-ups, virtual visits, simulations, treatments, "
            "courses, OTVs). The Data Source toggle switches which dataset "
            "feeds the charts; diagnosis resolution runs through the same "
            "ARIA Diagnosis lookup regardless.",
            size="sm", c="dimmed", style={"lineHeight": 1.6},
        ),

        section(
            "What's on this page",
            "tabler:layout-dashboard",
            body(
                "Three main visualizations: a trend ridgeline, a current-vs-"
                "prior comparison bars chart, and a full-width distribution "
                "trend. No traditional KPI row — the ridgeline's per-category "
                "counts and the comparison bars' change values serve the same "
                "purpose. A Diagnosis Classification Manager modal (dna icon, "
                "top right) lets you edit category assignments for ARIA "
                "lookup diagnoses.",
            ),

            dmc.Space(h="xs"),

            dmc.Text("Charts", fw=600, size="xs", mb=4),
            bullets([
                "Trend (ridgeline) — one horizontal density strip per "
                "diagnosis category, stacked vertically. Area / line / bar "
                "types, weekly / monthly / yearly aggregation, smoothing "
                "slider (default 3), and a sort toggle (Volume / Change / "
                "A-Z).",
                "Current vs Prior Period — bar chart showing each category's "
                "current-period count against the prior-period count. "
                "Calendar / rolling period toggle; prior-periods depth is "
                "configurable; sort toggle (Volume / Change / A-Z).",
                "Diagnosis Distribution — full-width trend of the top-N "
                "categories plus an \"Other\" bucket. Area / line / bar "
                "types, weekly / monthly / yearly aggregation, smoothing "
                "slider (default 3). Toggle count vs percent.",
            ]),

            dmc.Space(h="xs"),

            dmc.Text("Data Source toggle", fw=600, size="xs", mb=4),
            body(
                "A 7-option segmented control at the top of the filter bar "
                "picks which activity feeds the page. Each mode has its own "
                "loader, date column, and physician column:",
            ),
            bullets([
                "Consults — Clinic Visits classified as new-patient consults "
                "(via _is_consult from pages.home). Date = ScheduledDateTime, "
                "physician = AppointmentPhysician.",
                "Follow-ups — Clinic Visits that aren't consults or virtual.",
                "Virtual — Clinic Visits whose ActivityName contains \"virtual\".",
                "Simulations — load_simulations(). Date = ScheduledDateTime, "
                "physician = SupervisingPhysician.",
                "Treatments — load_treatment_detail(). Date = ScheduledDateTime, "
                "physician = TreatingPhysician.",
                "Courses — load_courses(). Date = CourseStartDate, physician = "
                "TreatingPhysician.",
                "OTVs — load_weekly_visits() filtered to completed visits. "
                "Date = AppointmentDateTime, physician = TreatingPhysician.",
            ]),

            dmc.Space(h="xs"),

            dmc.Text("Classification Manager modal", fw=600, size="xs", mb=4),
            body(
                "Opens via the dna icon in the page title. Full-height grid "
                "of every ARIA lookup diagnosis code with editable category / "
                "subcategory assignments. Overrides persist to the database "
                "(not just the session). Controls: Unreviewed-only toggle, "
                "Mark Reviewed, Delete Selected, Export CSV. A detail panel "
                "opens when a code is selected.",
            ),
        ),

        section(
            "Filters",
            "tabler:filter",
            bullets([
                "Data Source — the 7-mode toggle described above (default = "
                "Consults).",
                "Date preset + slider + manual DatePickerRange — anchored to "
                "the per-mode date column. Slider min is clamped to each "
                "mode's floor date (see below).",
                "Department chips — Lacey / Centralia / Aberdeen.",
                "Physician — single-select from the per-mode physician column.",
                "Diagnosis accordion — hierarchical category / subcategory "
                "picker with a Primary / All mode toggle. When Primary, only "
                "each row's primary category contributes; when All, every "
                "category a row's comma-separated DiagnosisCodes maps to is "
                "counted.",
            ]),
        ),

        section(
            "How the data is processed",
            "tabler:cpu",
            bullets([
                "_load_for_mode() dispatches to the appropriate loader and "
                "returns (df, date_col, phys_col). Each mode applies a floor "
                "date (currently 2021-08-01 for consults/followups/virtual/"
                "otvs) to exclude periods where DiagnosisCodes was not "
                "reliably populated in ARIA — the slider min is set to this "
                "floor so you can't accidentally include the null-diagnosis "
                "era.",
                "Diagnosis classification uses build_code_to_category() over "
                "the Diagnosis lookup — a code-to-category map built from the "
                "DIAG_SUBCATEGORIES table. DiagnosisCodes on the source rows "
                "are comma-separated and split before joining.",
                "_assign_diagnosis() adds a _diag_group column using "
                "primary_category() — the first (principal) category the "
                "row's codes resolve to. Diagnosis mode = All switches this "
                "to per-row fan-out: one row with multiple codes contributes "
                "to each category it maps to.",
                "Category palette is a fixed 13-color sequence (_DIAG_COLORS, "
                "led by PRIMARY #7C2A83) so the same category renders the "
                "same color across all three charts and across Data Source "
                "switches.",
                "The ridgeline is a fixed 840px tall (constant regardless of "
                "visible category count — rows auto-size within). This keeps "
                "the visual comparable when toggling sort or data source.",
                "Trend and Distribution charts use the server/clientside "
                "split — server loads raw per-period counts into the "
                "chart_card's built-in store (store_data=True); clientside "
                "callbacks handle smoothing, aggregation, and chart-type "
                "switching.",
                "The comparison chart is fully server-rendered (no store) "
                "because prior-periods depth and period-type changes require "
                "re-aggregation that's cleaner to do in pandas.",
                "Data-relative — every calculation uses the data's own "
                "max-date as the anchor, not wall-clock today.",
            ]),
        ),

        section(
            "Counting semantics",
            "tabler:calculator",
            bullets([
                "Unit of count depends on data source — consults / follow-ups "
                "/ virtual / OTVs are appointment rows; simulations are sim "
                "appointments; treatments are treatment detail rows (per-"
                "session); courses are unique CourseIds.",
                "In Primary diagnosis mode, total counts match the underlying "
                "dataset exactly. In All mode, totals can exceed the raw row "
                "count because multi-code rows contribute to multiple "
                "categories.",
                "Current vs Prior windows use either calendar periods (e.g., "
                "Jan vs Dec, YTD vs same-period-last-year) or rolling "
                "windows (last N days vs prior N days) depending on the "
                "period-type toggle.",
            ]),
        ),

        section(
            "Known quirks and limitations",
            "tabler:alert-triangle",
            bullets([
                "DiagnosisCodes was unreliably populated in ARIA before mid-"
                "2021. The floor-date clamp prevents naive queries against "
                "that era, but it also means long-term trends predating "
                "2021-08-01 aren't accessible here.",
                "A row with no mapped category resolves to \"Unclassified\". "
                "Filter selections that don't include Unclassified will drop "
                "these rows silently.",
                "The 7-mode toggle changes what a \"row\" means (see "
                "Counting semantics). Switching from Consults to Treatments "
                "will dramatically increase total counts because treatments "
                "are per-session.",
                "Category assignments edited in the Classification Manager "
                "persist — the next page load picks them up. If you're "
                "debugging a diagnosis-mix number, check whether a recent "
                "override reassigned a high-volume code.",
                "The Treatments and Courses modes don't apply a floor date "
                "(they weren't in the _MODE_FLOOR dict); DiagnosisCodes "
                "coverage on those datasets varies historically.",
            ]),
        ),
    ],
)
