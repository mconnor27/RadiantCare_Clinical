"""Billing page help content.

UI tab documents the Billing page's revenue methodology (CMS fee schedules,
payer mix, realization factor). SQL tab is the standard rendering of the
Billing.sql summary from sql_summaries.
"""

from __future__ import annotations

import dash_mantine_components as dmc
from dash_iconify import DashIconify

from config.settings import PRIMARY
from ..renderers import body, bullets, section, subheading


# ---------------------------------------------------------------------------
# UI tab — Billing methodology (ported from legacy help modal content).
# ---------------------------------------------------------------------------

UI_CONTENT = dmc.Stack(
    gap="md",
    children=[
        dmc.Title("Billing Page Methodology", order=4, c=PRIMARY),

        dmc.Text(
            "Revenue estimates on this page are derived from CMS public fee "
            "schedules applied to billing data exported from ARIA. These are "
            "Medicare allowed-amount estimates, not actual collections.",
            size="sm", c="dimmed",
        ),

        # --- Professional Revenue -----------------------------------------
        dmc.Paper(
            p="md", radius="md", withBorder=True,
            children=[
                dmc.Group(
                    gap="xs", mb="xs",
                    children=[
                        DashIconify(icon="tabler:stethoscope", width=20, color=PRIMARY),
                        dmc.Text("Professional Revenue (Physician Group)", fw=600, size="sm"),
                    ],
                ),
                dmc.Text("Source: CMS Physician Fee Schedule (PFS)", size="xs", c="dimmed", mb="xs"),
                dmc.Code(
                    "[(wRVU × Work GPCI) + (PE RVU × PE GPCI) + (MP RVU × MP GPCI)] × CF × HPSA",
                    block=True,
                ),
                dmc.List(
                    size="xs", spacing="xs", mt="xs",
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
                            " — Non-Facility PE RVU. HPSA bonus ×1.10.",
                        ]),
                    ],
                ),
                dmc.Divider(my="xs"),
                subheading("RVU Lookup"),
                bullets([
                    "For codes with a 26/TC split: uses the 26-modifier (professional) row.",
                    "For codes without a 26 row that have wRVU > 0: uses the global row (E&M, management).",
                    "TC-only codes (wRVU = 0): physician gets $0 — these are hospital-billed.",
                ]),
                dmc.Divider(my="xs"),
                subheading("GPCI (Rest of Washington, Locality 99)"),
                body(
                    "Each RVU component is adjusted by its own Geographic Practice Cost Index "
                    "before summing and multiplying by the conversion factor. All three sites "
                    "use the same GPCI locality.",
                ),
            ],
        ),

        # --- Hospital Revenue --------------------------------------------
        dmc.Paper(
            p="md", radius="md", withBorder=True,
            children=[
                dmc.Group(
                    gap="xs", mb="xs",
                    children=[
                        DashIconify(icon="tabler:building-hospital", width=20, color=PRIMARY),
                        dmc.Text("Hospital Revenue (Providence)", fw=600, size="sm"),
                    ],
                ),

                dmc.Text("Lacey & Centralia (POS 22) — OPPS",
                         fw=500, size="xs", c=PRIMARY, mb=4),
                dmc.Text("Source: CMS OPPS Addendum B (APC payment rates)",
                         size="xs", c="dimmed", mb="xs"),
                dmc.Code(
                    "APC Payment Rate × [0.60 × Wage Index + 0.40] × 1.071 (SCH)",
                    block=True,
                ),
                bullets([
                    "APC Payment Rate = national unadjusted Medicare OPPS rate per CPT code.",
                    "Wage Index from Providence Centralia (CCN 500019), reclassified to CBSA 45104 (Tacoma-Lakewood).",
                    "60% labor share adjusted by wage index; 40% non-labor unadjusted.",
                    "7.1% SCH (Sole Community Hospital) bonus on most services.",
                    "Both Lacey and Centralia bill under Centralia's parent hospital CCN.",
                ], mt="xs"),

                dmc.Divider(my="xs"),

                dmc.Text("Aberdeen (POS 11) — PFS Technical Component",
                         fw=500, size="xs", c=PRIMARY, mb=4),
                dmc.Text("Source: CMS Physician Fee Schedule (TC modifier rows)",
                         size="xs", c="dimmed", mb="xs"),
                dmc.Code(
                    "[(TC wRVU × Work GPCI) + (TC PE RVU × PE GPCI) + (TC MP RVU × MP GPCI)] × CF",
                    block=True,
                ),
                bullets([
                    "Freestanding site — OPPS does not apply.",
                    "Hospital bills TC on split codes only (delivery, imaging). No facility fee on E&M.",
                    "No HPSA bonus on TC component.",
                    "Billed on CMS-1500, not UB-04.",
                ], mt="xs"),
            ],
        ),

        # --- wRVU Charts --------------------------------------------------
        section(
            "wRVU Charts",
            "tabler:chart-line",
            body(
                "wRVU (Work Relative Value Units) measure physician work volume. "
                "These are always professional-only and are hidden when the Hospital "
                "component filter is selected. RVUs come from the CMS Physician Fee "
                "Schedule and are not adjusted by GPCI or conversion factor.",
            ),
        ),

        # --- Data Sources -------------------------------------------------
        dmc.Paper(
            p="md", radius="md", withBorder=True,
            children=[
                dmc.Group(
                    gap="xs", mb="xs",
                    children=[
                        DashIconify(icon="tabler:database", width=20, color=PRIMARY),
                        dmc.Text("Data Sources", fw=600, size="sm"),
                    ],
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
                    striped=True, highlightOnHover=True,
                    withTableBorder=True, withColumnBorders=True, fz="xs",
                ),
                dmc.Text(
                    "* Pre-2024 hospital revenue uses national unadjusted OPPS rates "
                    "(wage index = 1.0). The SCH 7.1% bonus is still applied.",
                    size="xs", c="dimmed", mt=4,
                ),
            ],
        ),

        # --- Caveats ------------------------------------------------------
        dmc.Alert(
            title="Important Caveats",
            color="yellow",
            variant="light",
            children=dmc.List(
                size="xs", spacing=4,
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

        # --- Revenue Adjustments -----------------------------------------
        dmc.Paper(
            p="md", radius="md", withBorder=True,
            children=[
                dmc.Group(
                    gap="xs", mb="xs",
                    children=[
                        DashIconify(icon="tabler:adjustments-dollar", width=20, color=PRIMARY),
                        dmc.Text("Revenue Adjustments", fw=600, size="sm"),
                    ],
                ),
                dmc.Text(
                    "Found in the Payor Manager modal under the Revenue Adjustments tab. "
                    "These controls refine monetary estimates beyond raw Medicare allowed amounts.",
                    size="xs", c="dimmed", mb="xs",
                ),

                subheading("Realization Factor"),
                dmc.Text(
                    "A percentage (0\u2013100%, default 90%) applied to all revenue estimates to "
                    "account for denials, contractual adjustments, underpayments, and write-offs. "
                    "This is always active regardless of the payer-mix toggle. A value of 90% means "
                    "the dashboard assumes 10% of billed revenue is lost to these factors.",
                    size="xs", mb="xs",
                ),

                dmc.Divider(my="xs"),

                subheading("Payer-Mix Multipliers"),
                dmc.Text(
                    "When the toggle is enabled, each billing row's revenue is scaled by a "
                    "multiplier based on the patient's broad payer category. This models how "
                    "different payer types reimburse relative to Medicare. The final per-row "
                    "calculation is:",
                    size="xs", mb="xs",
                ),
                dmc.Code(
                    "Adjusted Revenue = Medicare Allowed Amount \u00d7 Category Multiplier \u00d7 Realization Factor",
                    block=True,
                ),
                dmc.Text(
                    "When the toggle is off, the category multiplier is 1.0 (i.e., pure Medicare "
                    "rates), and only the realization factor is applied.",
                    size="xs", mt="xs", mb="xs",
                ),

                dmc.Divider(my="xs"),

                subheading("Default Multipliers"),
                dmc.Table(
                    data={
                        "head": ["Category", "Default", "Basis"],
                        "body": [
                            ["Medicare", "100%", "CMS fee schedule (by definition)"],
                            ["Medicaid", "90%", "WA Medicaid ~80%; managed care plans ~100%"],
                            ["Private", "130%", "Volume-weighted avg of Regence 147%, Premera 141%, Kaiser ~120%, Aetna 133%"],
                            ["Military/VA", "100%", "TRICARE/VA generally follows Medicare rates"],
                            ["Workers Comp", "125%", "WA L&I fee schedule"],
                            ["Tribal/IHS", "100%", "Assumed at Medicare rates"],
                            ["Self Pay", "50%", "High write-off rate; no contract"],
                            ["Other/Unknown", "100%", "Catch-all; assumed at Medicare"],
                        ],
                    },
                    striped=True, highlightOnHover=True,
                    withTableBorder=True, withColumnBorders=True, fz="xs",
                ),
                dmc.Text(
                    "These defaults are estimates derived from available contract data. "
                    "Adjust sliders to match your actual payer mix experience. "
                    "Settings persist across sessions.",
                    size="xs", c="dimmed", mt=4,
                ),
            ],
        ),
    ],
)
