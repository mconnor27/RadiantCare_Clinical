"""CPT Audit page — UI and data-processing help content."""

from __future__ import annotations

import dash_mantine_components as dmc
from dash_iconify import DashIconify

from config.settings import PRIMARY
from ..renderers import body, bullets, section, subheading


UI_CONTENT = dmc.Stack(
    gap="md",
    children=[
        dmc.Text(
            "The CPT Audit page surfaces per-session 2026 treatment-delivery coding "
            "compliance. Each radiation fraction is compared against a \"correct\" CPT "
            "code derived from the plan's technique, isocenters, and gating modifiers, "
            "then matched against the codes that were actually billed. Sessions with a "
            "mismatch are flagged for review so billing can be corrected before claims "
            "go out, or missed revenue can be recovered.",
            size="sm", c="dimmed", style={"lineHeight": 1.6},
        ),

        section(
            "What's on this page",
            "tabler:layout-dashboard",
            body(
                "Sticky header with a compact filter bar, a single compliance-trend "
                "chart, and a full-width audit detail table with an inline review "
                "workflow. The trend chart and table share a single dcc.Store of "
                "per-session rows so filter changes re-render everything at once. "
                "Review actions are persisted server-side to the SQLite review "
                "database (data/reviews_db.py).",
            ),

            dmc.Space(h="xs"),

            dmc.Text("Compliance Trend chart", fw=600, size="xs", mb=4),
            bullets([
                "Pass rate (%) aggregated Daily / Weekly / Monthly.",
                "Line / Area / Bar chart modes. Bar mode drops zero-total periods "
                "so weekends and holidays don't produce empty bars.",
                "Y-axis is auto-scaled with a minimum floor of 0 and a ceiling of "
                "100% so small dips don't look catastrophic.",
                "A session counts as \"passing\" if AuditResult = PASS, OR the "
                "session has been reviewed OK / Fixed, OR the patient's course has "
                "been approved as a whole — the chart reflects the current review "
                "state, not just the raw audit result.",
            ]),

            dmc.Space(h="xs"),

            dmc.Text("CPT Audit Detail table", fw=600, size="xs", mb=4),
            body(
                "One row per treatment session (SessionUniqueID). Columns: Date, "
                "Patient (Last, F.), MRN, Department, Machine, Course, Technique "
                "(RxTechnique_Day), Isocenters, Gating, Correct CPT, Billed CPT, "
                "Audit Result, and an inline Review column with OK / Fixed / "
                "Course OK / Undo buttons rendered by a custom AG Grid cell "
                "renderer (CptReviewButtons).",
            ),
            bullets([
                "Table-local date chips (Yesterday, This Week, This Month, YTD, "
                "All) filter in-memory without re-querying — separate from the "
                "header date range which governs what's loaded into the store.",
                "Review-status chips (All / Unreviewed / Reviewed) hide rows that "
                "have already been signed off.",
                "Audit-result chips (All / Failed / Passed) narrow to just the "
                "FAIL rows when you're working through a review queue.",
                "The Billed column strips the IGRT image-guidance code (77387) "
                "from comma-separated CPT_Billed values so the display shows the "
                "primary delivery code only.",
                "The OK All button applies a PASS review to every currently "
                "filtered unreviewed row (confirmation modal). Undo All clears "
                "every session review and every course approval across the whole "
                "dataset.",
            ]),
        ),

        section(
            "Filters",
            "tabler:filter",
            bullets([
                "Date preset — Prior 12 / 6 / 3 mo, Prior 30 days, YTD, Current / "
                "Last Year, This / Last Month, All Time, Custom. Anchored to the "
                "last available TreatmentDate (data-relative) rather than wall-"
                "clock now.",
                "Date range picker — custom start / end dates. Syncs two-way with "
                "the date-preset select and the month-level RangeSlider.",
                "Department chips — Lacey (blue), Centralia (red), Aberdeen "
                "(green). Multi-select.",
                "Scope is limited to 2026-01-01 forward — the audit only applies "
                "to the 2026 CPT code set, so earlier treatments are excluded.",
            ]),
        ),

        dmc.Paper(
            p="md", radius="md", withBorder=True,
            children=[
                dmc.Group(
                    gap="xs", mb="xs",
                    children=[
                        DashIconify(icon="tabler:clipboard-check", width=20, color=PRIMARY),
                        dmc.Text("Review workflow", fw=600, size="sm"),
                    ],
                ),
                dmc.Text(
                    "The review column exposes four actions per row. State is "
                    "written to SQLite immediately (set_review / remove_review / "
                    "set_course_review) and reloaded every 5 minutes via the "
                    "page interval so multiple users stay in sync.",
                    size="xs", c="dimmed", mb="xs",
                ),
                subheading("Session-level actions"),
                bullets([
                    "OK — accept the mismatch (e.g. intentional downcoding). Marks "
                    "the session as reviewed PASS.",
                    "Fixed — the billing has been corrected downstream. Marks the "
                    "session as reviewed PASS with a different badge color so "
                    "you can tell real fixes from accepted mismatches.",
                    "Undo — clear the session review. Also clears any course-"
                    "level approval for the same (MRN, CourseName) pair, since a "
                    "course approval implicitly covers every session in it.",
                ]),
                subheading("Course-level actions"),
                body(
                    "Course OK applies a single approval keyed on (PatientMRN, "
                    "CourseName) that covers every session in that course without "
                    "writing individual per-session reviews. The table's "
                    "ReviewSource column tracks whether a given row is passing "
                    "because of a session-level review or a course-level one. "
                    "Undo on any session in the course clears the course "
                    "approval.",
                ),
            ],
        ),

        section(
            "How the data is processed",
            "tabler:cpu",
            bullets([
                "Source: load_cpt_audit() reads Complete/2026 CPT Delivery "
                "Audit.csv — the audit is pre-computed by a SQL job, not derived "
                "on the dashboard. The app only filters, displays, and layers the "
                "review workflow on top.",
                "Department is cleaned via _clean_department() to strip the * "
                "prefix that some extracts include.",
                "TreatmentDate is parsed to datetime on load; the slider range "
                "and detail table use it for filtering and sorting.",
                "Rows are served sorted by TreatmentDate DESC and assigned a "
                "_sort_key integer so the client-side table can preserve the "
                "server ordering even after in-memory filtering.",
                "Patient display formats \"LASTNAME, FIRSTNAME\" into \"Lastname, "
                "F.\" in JavaScript-adjacent Python (first-letter initial only) "
                "to keep the table compact.",
                "FieldGating is serialized as 1 / 0 in the source and rendered "
                "as Yes / No in the UI.",
                "Pass-rate aggregation in the chart treats session-level and "
                "course-level reviews as overriding a FAIL — so the trend "
                "reflects your current acceptance state, not the raw audit.",
            ]),
        ),

        section(
            "Audit result values and coding context",
            "tabler:code",
            bullets([
                "AuditResult is \"PASS\" when CPT_Billed matches CPT_Correct "
                "(after ignoring 77387 image-guidance add-ons).",
                "AuditResult is \"FAIL\" when the delivered technique implies a "
                "different CPT than what was billed — typically VMAT / IMRT / "
                "3D / SBRT crossovers.",
                "2026 consolidated the legacy 77385 / 77386 / G6xxx delivery "
                "codes into 77402 / 77407 / 77412. The \"correct\" column "
                "reflects the new code set; a mismatch frequently means the plan "
                "charge row still carries a legacy code.",
                "CPT_Billed can contain multiple comma-separated codes when "
                "IGRT (77387) or gating add-ons are applied. Only the primary "
                "delivery code is used for pass/fail comparison.",
            ]),
        ),

        section(
            "Known quirks and limitations",
            "tabler:alert-triangle",
            bullets([
                "The page only covers dates from 2026-01-01 forward. If you set "
                "a date preset that crosses into 2025 the slider clamps to "
                "2026-01.",
                "Table-local date chips use pd.Timestamp.now() as the anchor "
                "(wall-clock today), so \"Yesterday\" / \"This Week\" may not "
                "line up with the last data date if an export is delayed. The "
                "header filter bar is data-relative by contrast.",
                "Review state is stored in the local SQLite database "
                "(data/reviews_db.py). If the file is deleted all session and "
                "course reviews are lost — there's no central ARIA source of "
                "truth for this workflow.",
                "Course approvals are keyed on (MRN, CourseName) as strings. If "
                "a course is renamed in ARIA after approval the link breaks and "
                "the sessions revert to their raw AuditResult.",
                "Chart pass rate is computed after review overrides are applied, "
                "so reviewing failures as OK will improve the compliance trend "
                "even when the underlying billing remains mis-coded. Use the "
                "Failed + Unreviewed table filters for a raw-audit view.",
            ]),
        ),
    ],
)
