"""Home page help content.

Just the Home page itself — project-level overview lives under the separate
Overview entry in the sidebar.
"""

from __future__ import annotations

import dash_mantine_components as dmc

from ..renderers import bullets, section


UI_CONTENT = dmc.Stack(
    gap="md",
    children=[
        dmc.Text(
            "The Home page is the dashboard's single-glance overview — it pulls "
            "signals from several of the page-specific data sources to produce a "
            "compact set of KPIs and trend sparklines across the full clinical "
            "operation.",
            size="sm", c="dimmed", style={"lineHeight": 1.6},
        ),

        section(
            "What's on this page",
            "tabler:layout-dashboard",
            bullets([
                "KPI row — high-level counts for the most recent 30-day window, "
                "each with an inline sparkline showing trend over the last several months.",
                "Census data — who is currently in active treatment, grouped by "
                "department and modality.",
                "Recent activity — rolling summaries of consults, simulations, and "
                "treatments for the last few days.",
                "Date and department chips that scope all KPIs and charts on the page.",
            ]),
        ),

        section(
            "Filters",
            "tabler:filter",
            bullets([
                "Date preset — 7 / 30 / 90 / 180 days or custom range. Anchored to the "
                "last available data date (not wall-clock today), so KPIs remain stable "
                "when an overnight export is delayed.",
                "Date range picker — custom start/end dates.",
                "Department chips — Lacey (blue), Centralia (red), Aberdeen (green). "
                "Multi-select.",
                "Physician select — one of the four radiation oncologists or \"All\".",
            ]),
        ),

        section(
            "How the data is processed",
            "tabler:cpu",
            bullets([
                "Pulls from daily_volume, treatment_detail, clinic_visits, simulations, "
                "and availability (same loaders as the individual pages — see the SQL tab "
                "for the scripts behind each).",
                "Dates on the page are data-relative — KPIs use the latest date in the "
                "dataset as the anchor, not pd.Timestamp.now().",
                "All KPI cards use the server/clientside callback split: the server "
                "renders raw data into a dcc.Store, clientside callbacks read the store "
                "plus settings to produce the sparkline figure without a round-trip.",
                "Home is the reference implementation for all page patterns — "
                "KPI cards with sparklines, clientside chart interactivity, date-filter "
                "helpers, and the overall layout structure.",
            ]),
        ),

        section(
            "Known limitations",
            "tabler:alert-triangle",
            bullets([
                "The physician filter is accepted on pages where the underlying data "
                "is aggregated (e.g., Operations uses Treatment.csv, which is summed by "
                "department and has no per-physician rows). On those pages the filter "
                "renders but cannot filter — this is a data-model limitation, not a bug.",
                "Sparklines on the KPI cards use a rolling 30-day window relative to the "
                "last data date. If an overnight export misses its window, the trend may "
                "cover a slightly earlier period than expected.",
            ]),
        ),
    ],
)
