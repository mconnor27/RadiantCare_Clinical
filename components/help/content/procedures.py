"""Procedures page — UI and data-processing help content."""

from __future__ import annotations

import dash_mantine_components as dmc

from ..renderers import body, bullets, section, subheading


UI_CONTENT = dmc.Stack(
    gap="md",
    children=[
        dmc.Text(
            "The Procedures page tracks ancillary clinical procedures that sit "
            "alongside the main EBRT workflow — Pluvicto infusions, Rectal "
            "Spacer placements, Lupron injections, Prostate LDR brachytherapy, "
            "Volume Studies, and Gold Seed fiducial placements. Each category "
            "has its own tab with a detail grid (and, for Pluvicto and Rectal "
            "Spacer, a patient queue view), while shared volume and lead-time "
            "metrics sit above the tabs.",
            size="sm", c="dimmed", style={"lineHeight": 1.6},
        ),

        section(
            "What's on this page",
            "tabler:layout-dashboard",
            body(
                "Five KPIs across the top, a two-chart row (Volume Trend + "
                "Cumulative Volume) that respects the active tab, a category tab "
                "bar, and per-category detail grids. Pluvicto and Rectal Spacer "
                "tabs additionally render an inline patient queue above the "
                "detail grid.",
            ),

            dmc.Space(h="xs"),

            dmc.Text("KPI row (5 cards)", fw=600, size="xs", mb=4),
            bullets([
                "Pluvicto — count of completed Pluvicto procedures in the "
                "filtered period, with a sparkline trend.",
                "Upcoming Pluvicto — next few scheduled (Open) Pluvicto "
                "appointments with date + treating MD, rendered as a compact "
                "stacked list inside the KPI card.",
                "Rectal Spacer — count of completed Rectal Spacer placements in "
                "the period.",
                "Upcoming Rectal Spacer — next few scheduled Rectal Spacer "
                "appointments.",
                "Avg Lead Time — mean days from consult to procedure across the "
                "category set, sourced from Workflow_Events (consult → procedure "
                "pairing).",
            ]),

            dmc.Space(h="xs"),

            dmc.Text("Charts (shared across tabs)", fw=600, size="xs", mb=4),
            bullets([
                "Volume Trend — bar / line / area with a Total / MD / Dept slice "
                "and weekly / monthly / yearly aggregation. The active category "
                "tab scopes the chart to that category (or all categories on the "
                "rollup view).",
                "Cumulative Volume — running total with Prior Periods (calendar "
                "or rolling overlays) or Slice By modes.",
            ]),

            dmc.Space(h="xs"),

            dmc.Text("Tab content", fw=600, size="xs", mb=4),
            bullets([
                "Pluvicto tab — patient queue table (All / In Progress / Completed "
                "filter) built from Workflow_Events filtered to ModalityType = "
                "\"Pluvicto\", plus a detail grid of underlying Procedure rows.",
                "Rectal Spacer tab — upcoming patient queue (scheduled Open "
                "Spacer appointments, sorted by ScheduledDateTime) plus a detail "
                "grid.",
                "Lupron / Prostate LDR / Volume Study / Gold Seeds tabs — "
                "detail grid only.",
            ]),
        ),

        section(
            "Filters",
            "tabler:filter",
            bullets([
                "Department chips — Lacey / Centralia / Aberdeen, multi-select.",
                "Physician — single-select chip group.",
                "Status — All / Open / Completed segmented control. Open = "
                "scheduled appointments that haven't happened yet.",
                "Date preset + date picker + month slider, all kept in sync. "
                "Default is Prior 12 mo.",
                "Smoothing slider for the Volume Trend.",
            ]),
        ),

        section(
            "How the data is processed",
            "tabler:cpu",
            bullets([
                "Primary source: Procedures.csv, loaded from Incremental/Procedures/ "
                "via _load_incremental() on UniqueRowID. Column mapping: "
                "DepartmentName→Department; dates parsed on ScheduledDateTime "
                "and AppointmentCreatedDate.",
                "Category bucketing uses the ProcedureCategory column; the six "
                "display categories are Pluvicto, Rectal Spacer, Lupron, "
                "Prostate LDR, Volume Study, and Gold Seeds.",
                "Pluvicto patient queue pulls from load_pluvicto_workflow(), "
                "which filters the full Workflow extract to ModalityType = "
                "\"Pluvicto\" — this gives the full consult → infusion chain "
                "rather than just the appointment row.",
                "Lead-time KPI: days from consult activity to procedure activity, "
                "averaged across the category set. Uses paired Workflow_Events "
                "rows (consult → procedure) where both timestamps are present.",
                "Upcoming counts filter to ActivityStatus = \"Open\" and sort "
                "ascending by ScheduledDateTime, taking the next N for the "
                "KPI-card display.",
                "Dates are data-relative — the filter anchors to the most recent "
                "ScheduledDateTime, not wall-clock today.",
                "Server callbacks populate proc-store-trend and proc-store-cumul; "
                "clientside callbacks handle chart type / smoothing / aggregation "
                "toggles without a server round-trip.",
                "Tab switching is clientside — only the active tab's content div "
                "is shown; all detail grids remain mounted to preserve their "
                "column filter state across tab changes.",
            ]),
        ),

        section(
            "Known quirks and limitations",
            "tabler:alert-triangle",
            bullets([
                "Procedures.csv only lists scheduled appointments / completions. "
                "Unscheduled referrals for these procedures (particularly Rectal "
                "Spacer consults still in planning) won't appear until they're "
                "scheduled. Use the Workflow page for full lifecycle visibility.",
                "Pluvicto is tracked through both Procedures.csv (appointment "
                "rows) and Workflow (modality chains). The KPIs count completed "
                "appointments from Procedures; the patient queue reflects "
                "Workflow-state progress. Small count differences between the "
                "two views are expected when a chain is mid-flight.",
                "Rectal Spacer procedures are typically performed in the OR and "
                "logged as an \"Open\" appointment until marked complete — a "
                "long-open status doesn't necessarily mean the procedure hasn't "
                "happened, it may just not be closed out in ARIA yet.",
                "The Avg Lead Time KPI excludes consults without a matching "
                "procedure — a growing backlog of un-matched consults will not "
                "appear in the lead-time number. Cross-reference with the "
                "Upcoming counts to see the current backlog.",
                "Physician filter applies to the treating physician on the "
                "procedure row. The referring or consulting physician may "
                "differ, especially for Pluvicto (often referred from Urology / "
                "Med Onc).",
            ]),
        ),
    ],
)
