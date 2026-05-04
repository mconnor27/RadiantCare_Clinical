"""Scheduling page — UI and data-processing help content."""

from __future__ import annotations

import dash_mantine_components as dmc

from ..renderers import body, bullets, section


UI_CONTENT = dmc.Stack(
    gap="md",
    children=[
        dmc.Text(
            "The Scheduling page surfaces open appointment slots — held consult "
            "and follow-up slots in physician mode, held sim slots in simulation "
            "mode — and overlays already-booked appointments on the same grid so "
            "you can see, at a glance, where capacity actually exists across the "
            "next two months. The view is built from the ScheduleUpcoming extract "
            "and augmented by the Clinic Visits and Simulations extracts to fill in "
            "what's already booked against those resources.",
            size="sm", c="dimmed", style={"lineHeight": 1.6},
        ),

        section(
            "What's on this page",
            "tabler:layout-dashboard",
            body(
                "A mode toggle (Physicians / Simulations), a filter bar, and two "
                "alternative views of the same filtered slot list:",
            ),

            dmc.Space(h="xs"),

            dmc.Text("Calendar view (default)", fw=600, size="xs", mb=4),
            bullets([
                "Mon–Fri columns, time-scaled vertically from 8 AM to 5 PM at 75 "
                "px/hour.",
                "Each slot is an absolutely-positioned card sized to its real "
                "duration — a 30-minute follow-up takes half the height of a "
                "60-minute consult.",
                "Overlapping slots split horizontally with a greedy column-pack "
                "algorithm: 2 overlapping → 50/50, 3 → thirds, etc. Badge text "
                "auto-abbreviates (full → 3-letter → single-letter) as columns "
                "narrow.",
                "Department color codes the border and badge of open slots "
                "(Lacey blue, Centralia red, Aberdeen green). Booked and "
                "blocked/held slots render in muted gray with strike-through "
                "or HOLD/BOOKED badges.",
                "Hover any slot for a native tooltip with full date, time range, "
                "duration, physician/resource, department, type, and status.",
                "Prev / Today / Next buttons step through weeks. \"Today\" is "
                "anchored to the earliest open slot in the data, not wall-clock "
                "today, so an empty current week doesn't strand you on a blank "
                "view.",
            ]),

            dmc.Space(h="xs"),

            dmc.Text("List view", fw=600, size="xs", mb=4),
            bullets([
                "Paginated card list (10 per page) sorted by AppointmentDateTime.",
                "Each card shows the date, time range and duration, slot type, "
                "physician/resource, and department badge. Booked slots are "
                "rendered at reduced opacity with a BOOKED badge.",
            ]),
        ),

        section(
            "Modes",
            "tabler:switch-horizontal",
            bullets([
                "Physicians — open slots are HOLD CONSULT and HOLD RE EVAL / "
                "2 FOLLOW UPS rows from ScheduleUpcoming. Booked overlays come "
                "from Clinic Visits filtered to Consult / Re-eval / Follow-Up "
                "ActivityNames with Status = open.",
                "Simulations — open slots are HOLD SIM TIME rows from "
                "ScheduleUpcoming (the sim machine is the resource, not a "
                "physician). Booked overlays come from Simulations with Status "
                "= open. The Type filter is hidden in this mode since there's "
                "only one sim slot type.",
            ]),
        ),

        section(
            "Filters",
            "tabler:filter",
            bullets([
                "View — Calendar vs. List.",
                "Show — Open Only (default) hides booked rows entirely; All "
                "renders booked appointments in muted gray alongside the open "
                "slots.",
                "Dept chips — Lacey / Centralia / Aberdeen, color-coded to "
                "match the slot cards.",
                "Physician chips — the canonical four (Allen, Connor, Suszko, "
                "Tinnel) plus any additional human resources present in the "
                "current data. Non-human resources like CT_RC_LACEY are "
                "filtered out of the chip list. In Simulations mode the "
                "physician filter only applies to booked sims (open HOLD SIM "
                "TIME rows aren't tied to a physician).",
                "Type chips (Physicians mode only) — Consult vs. Follow-up.",
            ]),
        ),

        section(
            "How the data is processed",
            "tabler:cpu",
            bullets([
                "ScheduleUpcoming is the spine: load_schedule_upcoming() reads "
                "the single-file ScheduleUpcoming extract (full-refresh "
                "snapshot regenerated on each ARIA export — not incremental).",
                "SlotTaken / IsTaken — the loader maps the source "
                "BookingStatus column (Available / Booked) into the legacy "
                "SlotTaken Yes / No vocabulary, so a HOLD slot is treated as "
                "taken when its BookingStatus = Booked. ScheduleUpcoming has "
                "no AppointmentNotes column, so the IsBlocked / HOLD-badge "
                "path collapses to all-False — every taken slot now renders "
                "as BOOKED. (The _blocked_flag helper is kept so any future "
                "signal — e.g. ActivityStatus — can plug in without touching "
                "the call sites.)",
                "Booked overlays are joined by date window, not by id: the "
                "page takes ScheduleUpcoming's min/max AppointmentDateTime "
                "and pulls Clinic Visits / Simulations rows whose "
                "ScheduledDateTime falls inside that window, with Status = "
                "open and matching ActivityName. This means booked rows from "
                "outside the ScheduleUpcoming snapshot's two-month window "
                "won't appear.",
                "Open Clinic Visits map to slot types via ActivityName: "
                "Consult → HOLD CONSULT, Re-eval and Follow-Up → HOLD RE EVAL / "
                "2 FOLLOW UPS. The HOLD SIM TIME activity name is explicitly "
                "filtered out of the booked-sim overlay to avoid double-counting "
                "with the ScheduleUpcoming rows.",
                "AssignedResource cascade for booked rows uses "
                "AppointmentPhysician → AttendingPhysician → SupervisingPhysician "
                "(physicians) or ConsultPhysician → SimulationResource (sims).",
                "\"Today\" for week navigation is data-relative: min "
                "(AppointmentDateTime) across all open slots, not "
                "datetime.now() — so the calendar always opens on a week that "
                "has at least one slot.",
                "Calendar layout uses a greedy column-pack — events sorted by "
                "start, each placed in the leftmost free column. Per event, "
                "total_cols is the max columns active anywhere in its span, "
                "so a slot that overlaps a 3-event cluster renders at 1/3 "
                "width even if its own peak is only 2-wide.",
            ]),
        ),

        section(
            "Counting semantics",
            "tabler:calculator",
            bullets([
                "One row = one slot (open or booked). Card counts in the list "
                "view are post-filter row counts.",
                "A taken HOLD row renders as BOOKED. With ScheduleUpcoming "
                "there is no separate BLOCKED state — the upstream extract "
                "no longer carries the AppointmentNotes free text that the "
                "legacy Availability path used to detect front-desk holds.",
                "Open Only mode drops every IsTaken row. To see booked rows "
                "alongside the open slots, switch Show to All.",
                "The physician chip list is the union across both modes "
                "(physicians and simulations) so toggling modes doesn't "
                "rebuild the chips.",
            ]),
        ),

        section(
            "Known quirks and limitations",
            "tabler:alert-triangle",
            bullets([
                "ScheduleUpcoming uses a dedicated live-refresh path: ARIA "
                "writes the CSV directly to R2 (no email / Power Automate "
                "step, no sanitize, no daily tarball) and the loader fetches "
                "it with a 5-minute TTL. The booked-overlay datasets (Clinic "
                "Visits, Simulations) still come from the daily sanitized "
                "tarball — so newly opened slots appear within minutes, but "
                "new bookings against existing slots may take up to a day to "
                "render in the gray (BOOKED) state.",
                "ScheduleUpcoming hard-codes a GETDATE() → +2 months window "
                "at extract time. Slots beyond that window do not appear, "
                "even if they exist on the schedule.",
                "Calendar view clips to 8 AM – 5 PM. Slots starting before 8 "
                "AM or after 5 PM are dropped from the calendar view but "
                "still appear in the list view.",
                "Calendar view is Mon–Fri only — weekend slots, if any, only "
                "show up in the list view.",
                "Booked overlays only appear when both ends of the join are "
                "present — if a Clinic Visits row exists for a date the "
                "ScheduleUpcoming snapshot doesn't cover, the booked overlay "
                "is skipped.",
                "Open HOLD SIM TIME slots have no physician attached. The "
                "physician chip filter therefore only narrows booked sims, "
                "not open ones — open sim availability is always shown "
                "regardless of which physicians are selected.",
            ]),
        ),
    ],
)
