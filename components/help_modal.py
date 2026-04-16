"""Global help modal — methodology and documentation per page."""

import dash_mantine_components as dmc
from dash import callback, Input, Output, State, html, dcc
from dash_iconify import DashIconify

from config.settings import PRIMARY

# ---------------------------------------------------------------------------
# Page-specific help content
# ---------------------------------------------------------------------------

_BILLING_HELP = dmc.Stack(
    gap="md",
    children=[
        dmc.Title("Billing Page Methodology", order=4, c=PRIMARY),

        dmc.Text(
            "Revenue estimates on this page are derived from CMS public fee "
            "schedules applied to billing data exported from ARIA. These are "
            "Medicare allowed-amount estimates, not actual collections.",
            size="sm", c="dimmed",
        ),

        # --- Professional Revenue ---
        dmc.Paper(
            p="md", radius="md", withBorder=True,
            children=[
                dmc.Group(
                    children=[
                        DashIconify(icon="tabler:stethoscope", width=20, color=PRIMARY),
                        dmc.Text("Professional Revenue (Physician Group)", fw=600, size="sm"),
                    ],
                    gap="xs", mb="xs",
                ),
                dmc.Text("Source: CMS Physician Fee Schedule (PFS)", size="xs", c="dimmed", mb="xs"),
                dmc.Code(
                    "[(wRVU × Work GPCI) + (PE RVU × PE GPCI) + (MP RVU × MP GPCI)] × CF × HPSA",
                    block=True,
                ),
                dmc.List(
                    size="xs",
                    spacing="xs",
                    mt="xs",
                    children=[
                        dmc.ListItem([
                            dmc.Text("Lacey (POS 22)", fw=600, span=True, size="xs"),
                            " — Facility PE RVU. No HPSA bonus.",
                        ]),
                        dmc.ListItem([
                            dmc.Text("Centralia (POS 22)", fw=600, span=True, size="xs"),
                            " — Facility PE RVU. HPSA bonus ×1.10.",
                        ]),
                        dmc.ListItem([
                            dmc.Text("Aberdeen (POS 11)", fw=600, span=True, size="xs"),
                            " — Non-Facility PE RVU (higher, covers equipment/overhead). HPSA bonus ×1.10.",
                        ]),
                    ],
                ),
                dmc.Divider(my="xs"),
                dmc.Text("RVU Lookup", fw=500, size="xs", mb=4),
                dmc.List(
                    size="xs",
                    spacing=2,
                    children=[
                        dmc.ListItem("For codes with a 26/TC split: uses the 26-modifier (professional) row."),
                        dmc.ListItem("For codes without a 26 row that have wRVU > 0: uses the global row (E&M, management)."),
                        dmc.ListItem("TC-only codes (wRVU = 0): physician gets $0 — these are hospital-billed."),
                    ],
                ),
                dmc.Divider(my="xs"),
                dmc.Text("GPCI (Rest of Washington, Locality 99)", fw=500, size="xs", mb=4),
                dmc.Text(
                    "Each RVU component is adjusted by its own Geographic Practice Cost Index "
                    "before summing and multiplying by the conversion factor. All three sites "
                    "use the same GPCI locality.",
                    size="xs",
                ),
            ],
        ),

        # --- Hospital Revenue ---
        dmc.Paper(
            p="md", radius="md", withBorder=True,
            children=[
                dmc.Group(
                    children=[
                        DashIconify(icon="tabler:building-hospital", width=20, color=PRIMARY),
                        dmc.Text("Hospital Revenue (Providence)", fw=600, size="sm"),
                    ],
                    gap="xs", mb="xs",
                ),

                dmc.Text("Lacey & Centralia (POS 22) — OPPS", fw=500, size="xs", c=PRIMARY, mb=4),
                dmc.Text("Source: CMS OPPS Addendum B (APC payment rates)", size="xs", c="dimmed", mb="xs"),
                dmc.Code(
                    "APC Payment Rate × [0.60 × Wage Index + 0.40] × 1.071 (SCH)",
                    block=True,
                ),
                dmc.List(
                    size="xs",
                    spacing=2,
                    mt="xs",
                    children=[
                        dmc.ListItem("APC Payment Rate = national unadjusted Medicare OPPS rate per CPT code."),
                        dmc.ListItem("Wage Index from Providence Centralia (CCN 500019), reclassified to CBSA 45104 (Tacoma-Lakewood)."),
                        dmc.ListItem("60% labor share adjusted by wage index; 40% non-labor unadjusted."),
                        dmc.ListItem("7.1% SCH (Sole Community Hospital) bonus on most services."),
                        dmc.ListItem("Both Lacey and Centralia bill under Centralia's parent hospital CCN."),
                    ],
                ),

                dmc.Divider(my="xs"),

                dmc.Text("Aberdeen (POS 11) — PFS Technical Component", fw=500, size="xs", c=PRIMARY, mb=4),
                dmc.Text("Source: CMS Physician Fee Schedule (TC modifier rows)", size="xs", c="dimmed", mb="xs"),
                dmc.Code(
                    "[(TC wRVU × Work GPCI) + (TC PE RVU × PE GPCI) + (TC MP RVU × MP GPCI)] × CF",
                    block=True,
                ),
                dmc.List(
                    size="xs",
                    spacing=2,
                    mt="xs",
                    children=[
                        dmc.ListItem("Freestanding site — OPPS does not apply."),
                        dmc.ListItem("Hospital bills TC on split codes only (delivery, imaging). No facility fee on E&M."),
                        dmc.ListItem("No HPSA bonus on TC component."),
                        dmc.ListItem("Billed on CMS-1500, not UB-04."),
                    ],
                ),
            ],
        ),

        # --- wRVU Charts ---
        dmc.Paper(
            p="md", radius="md", withBorder=True,
            children=[
                dmc.Group(
                    children=[
                        DashIconify(icon="tabler:chart-line", width=20, color=PRIMARY),
                        dmc.Text("wRVU Charts", fw=600, size="sm"),
                    ],
                    gap="xs", mb="xs",
                ),
                dmc.Text(
                    "wRVU (Work Relative Value Units) measure physician work volume. "
                    "These are always professional-only and are hidden when the Hospital "
                    "component filter is selected. RVUs come from the CMS Physician Fee "
                    "Schedule and are not adjusted by GPCI or conversion factor.",
                    size="xs",
                ),
            ],
        ),

        # --- Data Sources ---
        dmc.Paper(
            p="md", radius="md", withBorder=True,
            children=[
                dmc.Group(
                    children=[
                        DashIconify(icon="tabler:database", width=20, color=PRIMARY),
                        dmc.Text("Data Sources", fw=600, size="sm"),
                    ],
                    gap="xs", mb="xs",
                ),
                dmc.Table(
                    data={
                        "head": ["Dataset", "Source", "Years"],
                        "body": [
                            ["Billing events", "ARIA SQL export (Billing.csv)", "Incremental"],
                            ["Physician RVUs (wRVU, PE, MP)", "CMS PFS (PPRRVU files)", "2015–2026"],
                            ["OPPS APC rates", "CMS OPPS Addendum B", "2015–2026"],
                            ["GPCI (Work, PE, MP)", "CMS PFS (GPCI files)", "2015–2026"],
                            ["PFS Conversion Factor", "CMS PFS Final Rule", "2015–2026"],
                            ["OPPS Conversion Factor", "CMS OPPS Final Rule", "2015–2026"],
                            ["Wage Index (CCN 500019)", "CMS IPPS Table 2", "2024–2026*"],
                        ],
                    },
                    striped=True,
                    highlightOnHover=True,
                    withTableBorder=True,
                    withColumnBorders=True,
                    fz="xs",
                ),
                dmc.Text(
                    "* Pre-2024 hospital revenue uses national unadjusted OPPS rates "
                    "(wage index = 1.0). The SCH 7.1% bonus is still applied.",
                    size="xs", c="dimmed", mt=4,
                ),
            ],
        ),

        # --- Caveats ---
        dmc.Alert(
            title="Important Caveats",
            color="yellow",
            variant="light",
            children=dmc.List(
                size="xs",
                spacing=4,
                children=[
                    dmc.ListItem(
                        "These are Medicare allowed-amount estimates based on CMS fee schedules. "
                        "Actual reimbursement varies by payer contract, sequestration, and other adjustments."
                    ),
                    dmc.ListItem(
                        "Professional revenue uses PFS with GPCI adjustments for all years. "
                        "The 2026 PFS CF is $33.40 (non-APM), up from $32.35 in 2025."
                    ),
                    dmc.ListItem(
                        "Hospital OPPS estimates for 2024–2026 include wage index adjustment "
                        "using Providence Centralia's reclassified CBSA 45104 (Tacoma-Lakewood). "
                        "Pre-2024 estimates use national unadjusted rates (no wage index data available)."
                    ),
                    dmc.ListItem(
                        "SCH 7.1% payment adjustment is applied to all OPPS years. "
                        "The SCH hold-harmless calculation (cost-based comparison) is not modeled."
                    ),
                    dmc.ListItem(
                        "HPSA physician bonus (10%) applied to Centralia and Aberdeen professional fees. "
                        "Lacey (Thurston County) does not qualify."
                    ),
                    dmc.ListItem(
                        "2025 and earlier: delivery codes 77385/77386/G6xxx were structured differently. "
                        "G-codes had OPPS Status Indicator 'B' (bundled) — no separate facility payment. "
                        "2026 consolidation into 77402/77407/77412 changed APC assignments and rates significantly."
                    ),
                    dmc.ListItem(
                        "Aberdeen (freestanding, POS 11): hospital revenue uses PFS Technical Component "
                        "rates, not OPPS. E&M visits at Aberdeen generate no hospital claim."
                    ),
                ],
            ),
        ),
    ],
)

# Placeholder for other pages
_PLACEHOLDER_HELP = dmc.Stack(
    gap="md",
    children=[
        dmc.Text("Documentation for this page is coming soon.", size="sm", c="dimmed"),
    ],
)

# Map page paths to help content
_PAGE_HELP = {
    "/billing": _BILLING_HELP,
}


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------

def create_help_modal():
    """Return the global help modal component (add to app layout)."""
    return dmc.Modal(
        id="help-modal",
        opened=False,
        title=dmc.Group(
            children=[
                DashIconify(icon="tabler:help-circle", width=22, color=PRIMARY),
                dmc.Text("Help & Methodology", fw=600, size="lg"),
            ],
            gap="xs",
        ),
        size="80%",
        centered=True,
        zIndex=1000,
        styles={
            "header": {"padding": "10px 16px"},
            "content": {"height": "90vh", "display": "flex", "flexDirection": "column"},
            "body": {"padding": "0px 16px 16px 16px", "flex": 1, "overflow": "auto"},
        },
        children=[
            html.Div(id="help-modal-content"),
        ],
    )


# ---------------------------------------------------------------------------
# Callbacks
# ---------------------------------------------------------------------------

@callback(
    Output("help-modal", "opened"),
    Output("help-modal-content", "children"),
    Input("nav-help-btn", "n_clicks"),
    State("_pages_location", "pathname"),
    prevent_initial_call=True,
)
def _open_help(n, pathname):
    if not n:
        return False, []
    content = _PAGE_HELP.get(pathname, _PLACEHOLDER_HELP)
    return True, content
