"""Scheduling page — open appointment slots (HOLD CONSULT / HOLD RE EVAL).

Calendar (M-F, time-scaled) and list views of open slots from the latest
ScheduleUpcoming snapshot.
"""

import dash
import dash_mantine_components as dmc
from dash import callback, callback_context, Input, Output, State, dcc, html
from dash_iconify import DashIconify
import pandas as pd
from datetime import datetime, timedelta, date as date_class

from config.settings import (
    DEPARTMENTS, DEPARTMENT_COLORS, PRIMARY, NEUTRAL, PHYSICIANS,
)
from data.loader import (
    load_schedule_upcoming, load_clinic_visits, load_simulations,
    schedule_upcoming_last_modified,
)

dash.register_page(__name__, path="/scheduling", name="Scheduling", order=20)

PAGE_ID = "sched"

# Activity types we treat as "open slots" plus their display names
APPT_TYPES = {
    "HOLD CONSULT": "Consult",
    "HOLD RE EVAL/2 FOLLOW UPS": "Follow-up",
}

# Per-department card colors (light bg + border)
DEPT_CARD_COLORS = {
    "Lacey":     {"bg": "#e3f2fd", "border": "#2196f3"},
    "Centralia": {"bg": "#ffebee", "border": "#f44336"},
    "Aberdeen":  {"bg": "#e8f5e9", "border": "#4caf50"},
}

# 3-letter abbreviations used inside compact calendar slot badges
DEPT_ABBR = {"Lacey": "LAC", "Centralia": "CEN", "Aberdeen": "ABE"}
DEPT_ABBR_SHORT = {"Lacey": "L", "Centralia": "C", "Aberdeen": "A"}

# Calendar time scale
START_HOUR = 8
END_HOUR = 17
PIXELS_PER_HOUR = 75
TOTAL_HOURS = END_HOUR - START_HOUR + 1
TOTAL_HEIGHT = TOTAL_HOURS * PIXELS_PER_HOUR  # 750px


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------
# Clinic Visit ActivityName → Type bucket used by the page filter
_CV_TYPE_MAP = {
    "Consult": "HOLD CONSULT",
    "Re-eval": "HOLD RE EVAL/2 FOLLOW UPS",
    "Follow-Up": "HOLD RE EVAL/2 FOLLOW UPS",
}


_SLOT_COLUMNS = [
    "AppointmentDateTime", "ScheduledEndTime", "DurationMinutes",
    "ActivityName", "AssignedResource", "Department",
    "IsTaken", "IsBlocked", "Hour", "DayOfWeek",
]


def _empty_slots():
    """Empty slot DataFrame with the schema downstream callbacks expect.

    Without this, an upstream loader miss (R2 down, ScheduleUpcoming.csv
    absent in PHI mode) leaves the page callback with a column-less
    DataFrame that crashes on `df[~df["IsTaken"]]`.
    """
    return pd.DataFrame({col: pd.Series(dtype="object") for col in _SLOT_COLUMNS})


def _open_slots(mode="physicians"):
    """Dispatch to the right slot loader based on the selected mode."""
    if mode == "simulations":
        return _sim_slots()
    return _physician_slots()


def _blocked_flag(df):
    """Boolean Series: True when a slot is reserved/blocked by a front-desk note.

    ScheduleUpcoming does not carry an AppointmentNotes column, so HasNote
    is always False on the new feed and this helper returns all-False —
    blocked-vs-booked styling collapses to a single BOOKED state. Kept as
    a function so any future signal (e.g. ActivityStatus) can plug in here
    without touching the call sites.
    """
    if "HasNote" in df.columns:
        return df["HasNote"].fillna(False).astype(bool)
    notes = df.get("AppointmentNotes", pd.Series("", index=df.index))
    return notes.fillna("").astype(str).str.strip() != ""


def _sim_slots():
    """Sim-mode slots: HOLD SIM TIME from ScheduleUpcoming + booked Sims (gray)."""
    avail = load_schedule_upcoming()
    if avail.empty:
        return _empty_slots()
    avail = avail[avail["ActivityName"] == "HOLD SIM TIME"].copy()
    avail["AppointmentDateTime"] = pd.to_datetime(avail["AppointmentDateTime"])
    avail["ScheduledEndTime"] = pd.to_datetime(avail.get("ScheduledEndTime"))
    is_taken = avail["SlotTaken"].astype(str).str.lower() == "yes"
    is_blocked = _blocked_flag(avail)
    avail["IsTaken"] = is_taken | is_blocked
    avail["IsBlocked"] = is_blocked & ~is_taken
    avail = avail[[
        "AppointmentDateTime", "ScheduledEndTime", "DurationMinutes",
        "ActivityName", "AssignedResource", "Department", "IsTaken", "IsBlocked",
    ]]

    sim_extra = pd.DataFrame()
    if not avail.empty:
        win_start = avail["AppointmentDateTime"].min()
        win_end = avail["AppointmentDateTime"].max() + pd.Timedelta(days=1)
        sim = load_simulations()
        if not sim.empty and "ScheduledDateTime" in sim.columns:
            sim = sim.copy()
            sim["ScheduledDateTime"] = pd.to_datetime(sim["ScheduledDateTime"])
            sim = sim[
                (sim["ScheduledDateTime"] >= win_start)
                & (sim["ScheduledDateTime"] < win_end)
                & (sim["Status"].astype(str).str.lower() == "open")
                & (sim["ActivityName"] != "HOLD SIM TIME")  # avoid duplicating
            ]
            if not sim.empty:
                sim_extra = pd.DataFrame({
                    "AppointmentDateTime": sim["ScheduledDateTime"],
                    "ScheduledEndTime": sim["ScheduledDateTime"]
                        + pd.to_timedelta(sim["DurationMinutes"].fillna(60), unit="m"),
                    "DurationMinutes": sim["DurationMinutes"].fillna(60),
                    "ActivityName": sim["ActivityName"],
                    "AssignedResource": sim["ConsultPhysician"]
                        .fillna(sim.get("SimulationResource")),
                    "Department": sim["Department"],
                    "IsTaken": True,
                    "IsBlocked": False,
                })

    df = pd.concat([avail, sim_extra], ignore_index=True) if not sim_extra.empty else avail
    if df.empty:
        return _empty_slots()
    if "IsBlocked" not in df.columns:
        df["IsBlocked"] = False
    df["Hour"] = df["AppointmentDateTime"].dt.hour
    df["DayOfWeek"] = df["AppointmentDateTime"].dt.day_name()
    df = df.dropna(subset=["AppointmentDateTime", "Department"])
    df["AssignedResource"] = df["AssignedResource"].fillna("Sim Slot")
    return df.reset_index(drop=True)


def _physician_slots():
    avail = load_schedule_upcoming()
    if avail.empty:
        avail = _empty_slots()
    else:
        avail = avail[avail["ActivityName"].isin(APPT_TYPES.keys())].copy()
        avail["AppointmentDateTime"] = pd.to_datetime(avail["AppointmentDateTime"])
        avail["ScheduledEndTime"] = pd.to_datetime(avail.get("ScheduledEndTime"))
        is_taken = (
            avail["SlotTaken"].astype(str).str.lower() == "yes"
            if "SlotTaken" in avail.columns else pd.Series(False, index=avail.index)
        )
        is_blocked = _blocked_flag(avail)
        avail["IsTaken"] = is_taken | is_blocked
        avail["IsBlocked"] = is_blocked & ~is_taken
        avail = avail[[
            "AppointmentDateTime", "ScheduledEndTime", "DurationMinutes",
            "ActivityName", "AssignedResource", "Department", "IsTaken", "IsBlocked",
        ]]

    # Window for clinic visits = same span as availability snapshot
    cv_extra = pd.DataFrame()
    if not avail.empty:
        win_start = avail["AppointmentDateTime"].min()
        win_end = avail["AppointmentDateTime"].max() + pd.Timedelta(days=1)
        cv = load_clinic_visits()
        if not cv.empty and "ScheduledDateTime" in cv.columns:
            cv = cv.copy()
            cv["ScheduledDateTime"] = pd.to_datetime(cv["ScheduledDateTime"])
            cv = cv[
                (cv["ScheduledDateTime"] >= win_start)
                & (cv["ScheduledDateTime"] < win_end)
                & (cv["Status"].astype(str).str.lower() == "open")
                & (cv["ActivityName"].isin(_CV_TYPE_MAP.keys()))
            ]
            if not cv.empty:
                cv_extra = pd.DataFrame({
                    "AppointmentDateTime": cv["ScheduledDateTime"],
                    "ScheduledEndTime": cv["ScheduledDateTime"]
                        + pd.to_timedelta(cv["DurationMinutes"].fillna(60), unit="m"),
                    "DurationMinutes": cv["DurationMinutes"].fillna(60),
                    "ActivityName": cv["ActivityName"].map(_CV_TYPE_MAP),
                    "AssignedResource": cv["AppointmentPhysician"]
                        .fillna(cv.get("AttendingPhysician"))
                        .fillna(cv.get("SupervisingPhysician")),
                    "Department": cv["Department"],
                    "IsTaken": True,
                    "IsBlocked": False,
                })

    df = pd.concat([avail, cv_extra], ignore_index=True) if not cv_extra.empty else avail
    if df.empty:
        return _empty_slots()
    if "IsBlocked" not in df.columns:
        df["IsBlocked"] = False
    df["Hour"] = df["AppointmentDateTime"].dt.hour
    df["DayOfWeek"] = df["AppointmentDateTime"].dt.day_name()
    df = df.dropna(subset=["AppointmentDateTime", "Department"])
    df["AssignedResource"] = df["AssignedResource"].fillna("Unassigned")
    return df.reset_index(drop=True)


def _physician_options():
    """Build physician chip options. Use canonical four; add extras present in either mode."""
    extras = set()
    for df in (_physician_slots(), _sim_slots()):
        if not df.empty and "AssignedResource" in df.columns:
            present = df["AssignedResource"].dropna().unique()
            for p in present:
                # Only include human names (Last, First) — skip machines like CT_RC_LACEY
                if isinstance(p, str) and "," in p and p not in PHYSICIANS:
                    extras.add(p)
    return list(PHYSICIANS) + sorted(extras)


def _filter(df, depts, phys, appt_types, time_range, mode="physicians"):
    if df.empty:
        return df
    base = df["Department"].isin(depts)
    if mode == "simulations":
        # Open HOLD SIM TIME slots aren't tied to a physician (resource is the
        # CT scanner). Apply physician filter only to booked sims.
        phys_match = (~df["IsTaken"]) | df["AssignedResource"].isin(phys)
        out = df[base & phys_match]
    else:
        out = df[base
                 & df["AssignedResource"].isin(phys)
                 & df["ActivityName"].isin(appt_types)]
    if time_range:
        lo, hi = time_range
        out = out[(out["Hour"] >= lo) & (out["Hour"] <= hi)]
    return out.sort_values("AppointmentDateTime")


def _data_today():
    """Use the data's reference date — earliest open slot — as 'today' for week navigation."""
    df = _open_slots()
    if df.empty:
        return datetime.now()
    return df["AppointmentDateTime"].min().to_pydatetime()


def _week_bounds(week_offset):
    today = _data_today()
    week_start = today - timedelta(days=today.weekday())
    week_start = week_start + timedelta(weeks=week_offset)
    week_start = datetime(week_start.year, week_start.month, week_start.day)
    week_end = week_start + timedelta(days=4)
    return week_start, week_end


# ---------------------------------------------------------------------------
# Renderers
# ---------------------------------------------------------------------------
def _hex_to_rgb(hex_color):
    h = hex_color.lstrip("#")
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))


def _darken(hex_color, ratio=0.75):
    r, g, b = _hex_to_rgb(hex_color)
    return f"#{int(r*(1-ratio)):02x}{int(g*(1-ratio)):02x}{int(b*(1-ratio)):02x}"


def _appointment_card(appt):
    is_taken = bool(appt.get("IsTaken"))
    if is_taken:
        border = "#adb5bd"
        subtle_bg = "rgba(241, 243, 245, 0.6)"
        badge_bg = "rgba(108, 117, 125, 0.15)"
        badge_color = "#495057"
        badge_text = "BOOKED"
    else:
        colors = DEPT_CARD_COLORS.get(appt["Department"], {"bg": "#e3f2fd", "border": "#2196f3"})
        border = colors["border"]
        rgb_border = _hex_to_rgb(border)
        rgb_bg = _hex_to_rgb(colors["bg"])
        subtle_bg = f"rgba({rgb_bg[0]}, {rgb_bg[1]}, {rgb_bg[2]}, 0.3)"
        badge_bg = f"rgba({rgb_border[0]}, {rgb_border[1]}, {rgb_border[2]}, 0.15)"
        badge_color = border
        badge_text = appt["Department"]

    start = appt["AppointmentDateTime"]
    end = appt.get("ScheduledEndTime")
    duration = int(appt["DurationMinutes"]) if pd.notna(appt.get("DurationMinutes")) else 0

    date_str = start.strftime("%A, %B %d, %Y")
    time_str = start.strftime("%I:%M %p").lstrip("0")
    end_str = end.strftime("%I:%M %p").lstrip("0") if pd.notna(end) else ""
    appt_label = APPT_TYPES.get(appt["ActivityName"], appt["ActivityName"])

    dept_badge = html.Span(badge_text, style={
        "display": "inline-block", "fontSize": "11px", "fontWeight": 600,
        "color": badge_color, "backgroundColor": badge_bg,
        "padding": "4px 10px", "borderRadius": "6px",
        "border": f"1px solid {border}", "whiteSpace": "nowrap",
    })
    phys_badge = html.Span(appt["AssignedResource"], style={
        "display": "inline-block", "fontSize": "11px", "fontWeight": 600,
        "color": "#6c757d" if is_taken else "#7b1fa2",
        "backgroundColor": "rgba(108, 117, 125, 0.15)" if is_taken else "rgba(156, 39, 176, 0.15)",
        "padding": "4px 10px", "borderRadius": "6px",
        "border": f"1px solid {'#adb5bd' if is_taken else '#9c27b0'}",
        "whiteSpace": "nowrap",
    })

    return html.Div([
        html.Div([
            html.Div([
                html.Div([
                    DashIconify(icon="tabler:calendar", width=14, color="#6c757d"),
                    html.Strong(date_str, style={"fontSize": "15px", "marginLeft": "8px"}),
                ], style={"display": "flex", "alignItems": "center", "marginBottom": "8px"}),
                html.Div([
                    DashIconify(icon="tabler:clock", width=14, color="#6c757d"),
                    html.Span(f"{time_str} – {end_str} ({duration} min)",
                              style={"fontSize": "14px", "color": "#495057", "marginLeft": "8px"}),
                ], style={"display": "flex", "alignItems": "center", "marginBottom": "8px"}),
                html.Div([
                    DashIconify(icon="tabler:notes", width=14, color="#6c757d"),
                    html.Span(appt_label,
                              style={"fontSize": "13px", "color": "#6c757d", "marginLeft": "8px"}),
                ], style={"display": "flex", "alignItems": "center"}),
            ], style={"flex": "1"}),
            html.Div([
                html.Div(phys_badge, style={"marginBottom": "8px", "textAlign": "right"}),
                html.Div(dept_badge, style={"textAlign": "right"}),
            ]),
        ], style={"display": "flex", "justifyContent": "space-between",
                  "alignItems": "flex-start", "padding": "16px"}),
    ], style={
        "marginBottom": "12px",
        "boxShadow": "0 2px 6px rgba(0,0,0,0.08)",
        "border": f"1px solid {border}",
        "borderLeft": f"4px solid {border}",
        "borderRadius": "8px",
        "backgroundColor": subtle_bg,
        "opacity": "0.7" if is_taken else "1",
    })


def _list_view(df, page, page_size=10):
    if df.empty:
        return [html.Div(
            "No open slots match the selected filters.",
            style={"textAlign": "center", "padding": "40px", "color": "#6c757d"},
        )], "No data"

    total = len(df)
    pages = max(1, (total + page_size - 1) // page_size)
    page = max(1, min(page, pages))
    start_idx = (page - 1) * page_size
    chunk = df.iloc[start_idx:start_idx + page_size]
    cards = [_appointment_card(row) for _, row in chunk.iterrows()]
    return cards, f"Page {page} of {pages} ({total} slots)"


def _layout_overlapping(events):
    """Assign column index + total cols for side-by-side rendering.

    Standard greedy column-pack algorithm: events sorted by start, each placed
    in the leftmost column that's free. The total-cols width for an event is
    the max columns active anywhere in its time range, so a 2-event overlap
    splits 50/50, a 3-event overlap 33/33/33, etc.

    Args:
        events: list of dicts with 'start' and 'end' (minutes from midnight).

    Returns:
        list of dicts with original event + 'col' and 'total_cols'.
    """
    if not events:
        return []
    events = sorted(events, key=lambda e: (e["start"], -e["end"]))
    col_end = []  # last end-minute per column
    placed = []
    for ev in events:
        col = None
        for i, end in enumerate(col_end):
            if end <= ev["start"]:
                col = i
                col_end[i] = ev["end"]
                break
        if col is None:
            col = len(col_end)
            col_end.append(ev["end"])
        placed.append({**ev, "col": col})

    # For each event, find max col index among events that overlap it
    out = []
    for p in placed:
        max_col = p["col"]
        for q in placed:
            if q is p:
                continue
            if q["start"] < p["end"] and q["end"] > p["start"]:
                if q["col"] > max_col:
                    max_col = q["col"]
        out.append({**p, "total_cols": max_col + 1})
    return out


def _slot_card(appt, top, height, left_pct, width_pct, total_cols=1):
    """Render a single appointment as an absolutely-positioned card.

    Badge text uses abbreviations only when 3+ overlapping slots make the
    column narrow; with 1-2 cols there's room for the full name.
    """
    is_taken = bool(appt.get("IsTaken"))
    is_blocked = bool(appt.get("IsBlocked"))
    duration = float(appt["DurationMinutes"]) if pd.notna(appt.get("DurationMinutes")) else 60
    time_str = appt["AppointmentDateTime"].strftime("%I:%M %p").lstrip("0")
    end_dt = appt.get("ScheduledEndTime")
    end_str = end_dt.strftime("%I:%M %p").lstrip("0") if pd.notna(end_dt) else ""
    label = APPT_TYPES.get(appt["ActivityName"], appt["ActivityName"])
    # 1-2 cols → full text; 3 cols → 3-letter; 4+ cols → single letter
    if total_cols >= 4:
        abbr_level = "short"
    elif total_cols == 3:
        abbr_level = "medium"
    else:
        abbr_level = "full"

    # With 3+ overlapping slots, show only the physician's last name
    resource_text = appt["AssignedResource"]
    if abbr_level != "full" and isinstance(resource_text, str) and "," in resource_text:
        resource_text = resource_text.split(",", 1)[0]

    if is_taken:
        slot_class = "sched-slot-booked"
        if is_blocked:
            badge_text = "H" if abbr_level == "short" else "HOLD"
        elif abbr_level == "short":
            badge_text = "B"
        elif abbr_level == "medium":
            badge_text = "BKD"
        else:
            badge_text = "BOOKED"
        badge_bg = "rgba(108, 117, 125, 0.18)"
        badge_color = "var(--text-muted)"
        name_decoration = "line-through" if not is_blocked else "none"
    else:
        slot_class = f"sched-slot-{appt['Department'].lower()}"
        rgb_border = _hex_to_rgb(DEPT_CARD_COLORS.get(
            appt["Department"], {"border": "#2196f3"})["border"])
        badge_bg = f"rgba({rgb_border[0]}, {rgb_border[1]}, {rgb_border[2]}, 0.28)"
        badge_color = "var(--text-primary)"
        if abbr_level == "short":
            badge_text = DEPT_ABBR_SHORT.get(appt["Department"], appt["Department"][:1])
        elif abbr_level == "medium":
            badge_text = DEPT_ABBR.get(appt["Department"], appt["Department"][:3].upper())
        else:
            badge_text = appt["Department"]
        name_decoration = "none"

    if is_blocked:
        status_line = "RESERVED / BLOCKED"
    elif is_taken:
        status_line = "BOOKED"
    else:
        status_line = "OPEN"

    # Native HTML tooltip — full detail readout on hover
    tooltip = (
        f"{appt['AppointmentDateTime'].strftime('%A, %b %d')}\n"
        f"{time_str} – {end_str}  ({int(duration)} min)\n"
        f"{appt['AssignedResource']}\n"
        f"{appt['Department']} • {label}\n"
        f"{status_line}"
    )

    badge = html.Div(badge_text, style={
        "fontSize": "9px", "fontWeight": "bold",
        "color": badge_color,
        "backgroundColor": badge_bg,
        "padding": "2px 6px", "borderRadius": "3px",
        "whiteSpace": "nowrap", "width": "fit-content",
    })

    container_style = {
        "position": "absolute", "top": f"{top}px",
        "left": f"calc({left_pct}% + 1px)",
        "width": f"calc({width_pct}% - 2px)",
        "height": f"{height}px",
        "borderWidth": "2px", "borderStyle": "solid",
        "borderRadius": "4px",
        "padding": "4px", "boxSizing": "border-box",
        "cursor": "default",
    }

    tooltip_div = html.Div(tooltip, className="sched-slot-tooltip")

    if duration <= 30:
        container_style.update({"display": "flex", "alignItems": "center", "gap": "4px"})
        return html.Div([
            html.Div(time_str, style={"fontWeight": "bold", "fontSize": "10px",
                                      "whiteSpace": "nowrap"}),
            html.Div(resource_text, style={
                "fontSize": "11px", "overflow": "hidden",
                "textOverflow": "ellipsis", "whiteSpace": "nowrap",
                "flex": "1", "minWidth": "0"}),
            badge,
            tooltip_div,
        ], style=container_style, className=f"sched-slot {slot_class}")

    return html.Div([
        html.Div([
            html.Div(time_str, style={"fontWeight": "bold", "fontSize": "10px",
                                      "whiteSpace": "nowrap"}),
            badge,
        ], style={
            "display": "flex", "justifyContent": "space-between",
            "alignItems": "center", "gap": "4px", "marginBottom": "2px",
        }),
        html.Div(resource_text, style={
            "fontSize": "11px", "marginBottom": "1px", "overflow": "hidden",
            "textOverflow": "ellipsis", "whiteSpace": "nowrap",
            "textDecoration": name_decoration}),
        html.Div(label, style={"fontSize": "10px", "color": "var(--text-muted)",
                               "overflow": "hidden", "textOverflow": "ellipsis",
                               "whiteSpace": "nowrap"}),
        tooltip_div,
    ], style=container_style, className=f"sched-slot {slot_class}")


def _calendar_view(df, week_start, week_end):
    weekdays = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
    dates = [(week_start + timedelta(days=i)) for i in range(5)]

    weekly = pd.DataFrame()
    if not df.empty:
        weekly = df[
            (df["AppointmentDateTime"] >= week_start)
            & (df["AppointmentDateTime"] < week_end + timedelta(days=1))
            & (df["AppointmentDateTime"].dt.dayofweek < 5)
        ]

    by_day = {d: [] for d in weekdays}
    for _, appt in weekly.iterrows():
        if appt["DayOfWeek"] in by_day:
            by_day[appt["DayOfWeek"]].append(appt)

    # Time labels
    time_labels = []
    for hour in range(START_HOUR, END_HOUR + 1):
        suffix = "AM" if hour < 12 else "PM"
        disp = hour if hour <= 12 else hour - 12
        time_labels.append(html.Div(f"{disp} {suffix}", className="sched-time-label", style={
            "height": f"{PIXELS_PER_HOUR}px",
            "lineHeight": f"{PIXELS_PER_HOUR}px",
            "fontSize": "11px",
            "borderTop": "1px solid",
            "paddingRight": "8px", "textAlign": "right",
        }))

    cols = []
    cols.append(html.Div([
        html.Div(style={"height": "50px"}),
        html.Div(time_labels),
    ], style={"width": "56px", "flexShrink": "0"}))

    today = date_class.today()
    for day, d in zip(weekdays, dates):
        is_today = d.date() == today

        # Hour grid background
        hour_cells = [html.Div(className="sched-hour-cell", style={
            "height": f"{PIXELS_PER_HOUR}px",
            "borderTop": "1px solid",
            "borderLeft": "1px solid",
            "borderRight": "1px solid",
        }) for _ in range(START_HOUR, END_HOUR + 1)]

        # Build event list with start/end in minutes from midnight, then layout
        day_appts = []
        for appt in by_day[day]:
            hr = appt["AppointmentDateTime"].hour
            mn = appt["AppointmentDateTime"].minute
            if hr < START_HOUR or hr > END_HOUR:
                continue
            duration = float(appt["DurationMinutes"]) if pd.notna(appt.get("DurationMinutes")) else 60
            start_min = hr * 60 + mn
            day_appts.append({
                "appt": appt,
                "start": start_min,
                "end": start_min + duration,
                "duration": duration,
            })

        laid_out = _layout_overlapping(day_appts)

        items = []
        for entry in laid_out:
            appt = entry["appt"]
            hr = appt["AppointmentDateTime"].hour
            mn = appt["AppointmentDateTime"].minute
            top = ((hr - START_HOUR) + (mn / 60)) * PIXELS_PER_HOUR
            height = (entry["duration"] / 60) * PIXELS_PER_HOUR
            width_pct = 100.0 / entry["total_cols"]
            left_pct = entry["col"] * width_pct
            items.append(_slot_card(appt, top, height, left_pct, width_pct,
                                    total_cols=entry["total_cols"]))

        header_class = "sched-day-header sched-day-today" if is_today else "sched-day-header"
        card_class = "sched-day-card sched-day-today" if is_today else "sched-day-card"

        cols.append(html.Div([
            html.Div([
                html.Div(day, className="sched-day-name",
                         style={"fontWeight": "bold", "fontSize": "12px"}),
                html.Div(d.strftime("%b %d"), className="sched-day-date",
                         style={"fontSize": "11px"}),
            ], className=header_class,
               style={"textAlign": "center", "padding": "8px", "height": "50px"}),
            # Day grid: hour cells fill the parent, items are absolutely positioned
            # over them — no height:0 hack so each slot has a real bounding rect
            # for tooltip positioning.
            html.Div([
                html.Div(hour_cells, style={
                    "position": "absolute", "top": "0", "left": "0",
                    "right": "0", "bottom": "0",
                }),
                html.Div(items, style={
                    "position": "absolute", "top": "0", "left": "0",
                    "right": "0", "bottom": "0",
                }),
            ], style={"position": "relative", "height": f"{TOTAL_HEIGHT}px"}),
        ], className=card_class,
           style={"borderRadius": "6px",
                  "flex": "1", "minWidth": "0"}))

    cols.append(html.Div([
        html.Div(style={"height": "50px"}),
        html.Div(time_labels),
    ], style={"width": "56px", "flexShrink": "0"}))

    return html.Div(cols, style={
        "display": "flex", "gap": "3px", "alignItems": "stretch",
        "width": "calc(100% + 32px)", "maxWidth": "calc(100vw - 240px)",
        "marginLeft": "-16px", "marginRight": "-16px",
    })


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------
_LABEL_STYLE = {"color": "#6B7280", "fontWeight": 500, "fontSize": "12px",
                "marginRight": "6px", "whiteSpace": "nowrap"}


def _inline_filter(label, chip_group):
    """Inline label + chip group on one line, no vertical wrap."""
    return html.Div([
        html.Span(label, style=_LABEL_STYLE),
        chip_group,
    ], style={"display": "inline-flex", "alignItems": "center", "gap": "4px"})


def _chips_row(chip_id, value, options, color="violet"):
    """ChipGroup whose chips are forced into a single non-wrapping row."""
    if isinstance(options, dict):
        items = list(options.items())
    else:
        items = [(o, o) for o in options]
    return dmc.ChipGroup(
        id=chip_id,
        value=value,
        multiple=True,
        children=html.Div(
            [
                dmc.Chip(
                    label,
                    value=val,
                    color=color(val) if callable(color) else color,
                    variant="filled",
                    size="xs",
                )
                for val, label in items
            ],
            style={"display": "inline-flex", "flexWrap": "nowrap", "gap": "4px"},
        ),
    )


def _filter_bar():
    phys_options = _physician_options()
    return dmc.Paper(
        children=[
            html.Div(
                style={
                    "display": "flex", "flexWrap": "wrap",
                    "alignItems": "center", "gap": "20px", "rowGap": "10px",
                },
                children=[
                    _inline_filter("View", dmc.SegmentedControl(
                        id=f"{PAGE_ID}-view-mode",
                        data=[
                            {"value": "calendar", "label": "Calendar"},
                            {"value": "list", "label": "List"},
                        ],
                        value="calendar",
                        size="xs",
                    )),
                    _inline_filter("Show", dmc.SegmentedControl(
                        id=f"{PAGE_ID}-show-mode",
                        data=[
                            {"value": "open", "label": "Open Only"},
                            {"value": "all", "label": "All"},
                        ],
                        value="open",
                        size="xs",
                    )),
                    _inline_filter("Dept", _chips_row(
                        f"{PAGE_ID}-filter-department",
                        list(DEPARTMENTS),
                        {d: d for d in DEPARTMENTS},
                        color=lambda d: DEPARTMENT_COLORS.get(d, "violet"),
                    )),
                    _inline_filter("Physician", _chips_row(
                        f"{PAGE_ID}-filter-physician",
                        list(phys_options),
                        {p: p.split(", ")[0] for p in phys_options},
                        color="violet",
                    )),
                    html.Div(
                        id=f"{PAGE_ID}-type-wrapper",
                        children=_inline_filter("Type", _chips_row(
                            f"{PAGE_ID}-filter-appt-type",
                            list(APPT_TYPES.keys()),
                            APPT_TYPES,
                            color="grape",
                        )),
                    ),
                ],
            ),
        ],
        p="xs", px="md", radius="md", shadow="xs", withBorder=True,
    )


layout = dmc.Stack(
    gap=16,
    className="page-content",
    children=[
        dmc.Box(
            className="page-sticky-header",
            children=[
                dmc.Group(justify="center", align="center", gap="xl", children=[
                    dmc.Title("Scheduling", order=2, className="page-title",
                              style={"margin": 0}),
                    dmc.SegmentedControl(
                        id=f"{PAGE_ID}-mode",
                        data=[
                            {"value": "physicians", "label": "Physicians"},
                            {"value": "simulations", "label": "Simulations"},
                        ],
                        value="physicians",
                        size="md",
                        color="violet",
                    ),
                ]),
                _filter_bar(),
            ],
        ),
        # Stores
        dcc.Store(id=f"{PAGE_ID}-week-offset", data=0),
        dcc.Store(id=f"{PAGE_ID}-list-page", data=1),
        # Calendar view
        html.Div(id=f"{PAGE_ID}-calendar-container", children=[
            dmc.Group(justify="center", gap="md", mb="sm", align="center", children=[
                dmc.Button("Prev", id=f"{PAGE_ID}-prev-week", size="sm",
                           variant="default",
                           leftSection=DashIconify(icon="tabler:chevron-left", width=14)),
                dmc.Button("Today", id=f"{PAGE_ID}-this-week", size="sm",
                           color="violet", variant="filled"),
                dmc.Title(id=f"{PAGE_ID}-week-title", order=4, c=PRIMARY,
                          style={"margin": 0, "minWidth": "260px", "textAlign": "center"}),
                dmc.Button("Next", id=f"{PAGE_ID}-next-week", size="sm",
                           variant="default",
                           rightSection=DashIconify(icon="tabler:chevron-right", width=14)),
            ]),
            html.Div(id=f"{PAGE_ID}-calendar-grid"),
            dmc.Text(
                id=f"{PAGE_ID}-last-updated",
                size="xs", c="dimmed", ta="center",
                mt="md", mb="xs",
            ),
        ]),
        # List view
        html.Div(id=f"{PAGE_ID}-list-container", style={"display": "none"}, children=[
            dmc.Title("Open Appointments", order=4, c=PRIMARY,
                      ta="center", mb="sm", style={"margin": 0}),
            html.Div(id=f"{PAGE_ID}-list-cards",
                     style={"maxWidth": "780px", "margin": "0 auto"}),
            dmc.Group(justify="center", gap="xs", mt="md", children=[
                dmc.Button("Prev", id=f"{PAGE_ID}-prev-page", size="sm", variant="default",
                           leftSection=DashIconify(icon="tabler:chevron-left", width=14)),
                dmc.Text(id=f"{PAGE_ID}-page-display", size="sm", fw=500),
                dmc.Button("Next", id=f"{PAGE_ID}-next-page", size="sm", variant="default",
                           rightSection=DashIconify(icon="tabler:chevron-right", width=14)),
            ]),
        ]),
    ],
)


# ---------------------------------------------------------------------------
# Callbacks
# ---------------------------------------------------------------------------
@callback(
    Output(f"{PAGE_ID}-week-offset", "data"),
    Input(f"{PAGE_ID}-prev-week", "n_clicks"),
    Input(f"{PAGE_ID}-next-week", "n_clicks"),
    Input(f"{PAGE_ID}-this-week", "n_clicks"),
    State(f"{PAGE_ID}-week-offset", "data"),
    prevent_initial_call=True,
)
def _update_week(prev_n, next_n, today_n, current):
    ctx = callback_context
    if not ctx.triggered:
        return current or 0
    btn = ctx.triggered[0]["prop_id"].split(".")[0]
    cur = current or 0
    if btn == f"{PAGE_ID}-prev-week":
        return cur - 1
    if btn == f"{PAGE_ID}-next-week":
        return cur + 1
    return 0


@callback(
    Output(f"{PAGE_ID}-list-page", "data"),
    Input(f"{PAGE_ID}-prev-page", "n_clicks"),
    Input(f"{PAGE_ID}-next-page", "n_clicks"),
    Input(f"{PAGE_ID}-filter-department", "value"),
    Input(f"{PAGE_ID}-filter-physician", "value"),
    Input(f"{PAGE_ID}-filter-appt-type", "value"),
    Input(f"{PAGE_ID}-show-mode", "value"),
    Input(f"{PAGE_ID}-mode", "value"),
    State(f"{PAGE_ID}-list-page", "data"),
    prevent_initial_call=True,
)
def _update_page(prev_n, next_n, depts, phys, appts, show_mode, mode, current):
    ctx = callback_context
    if not ctx.triggered:
        return 1
    btn = ctx.triggered[0]["prop_id"].split(".")[0]
    cur = current or 1
    if btn == f"{PAGE_ID}-prev-page":
        return max(1, cur - 1)
    if btn == f"{PAGE_ID}-next-page":
        return cur + 1
    return 1  # Filters changed


@callback(
    Output(f"{PAGE_ID}-calendar-container", "style"),
    Output(f"{PAGE_ID}-list-container", "style"),
    Input(f"{PAGE_ID}-view-mode", "value"),
)
def _toggle_view(mode):
    if mode == "list":
        return {"display": "none"}, {"display": "block"}
    return {"display": "block"}, {"display": "none"}


@callback(
    Output(f"{PAGE_ID}-type-wrapper", "style"),
    Input(f"{PAGE_ID}-mode", "value"),
)
def _toggle_type_filter(mode):
    if mode == "simulations":
        return {"display": "none"}
    return {"display": "block"}


@callback(
    Output(f"{PAGE_ID}-calendar-grid", "children"),
    Output(f"{PAGE_ID}-week-title", "children"),
    Output(f"{PAGE_ID}-list-cards", "children"),
    Output(f"{PAGE_ID}-page-display", "children"),
    Output(f"{PAGE_ID}-last-updated", "children"),
    Input(f"{PAGE_ID}-filter-department", "value"),
    Input(f"{PAGE_ID}-filter-physician", "value"),
    Input(f"{PAGE_ID}-filter-appt-type", "value"),
    Input(f"{PAGE_ID}-view-mode", "value"),
    Input(f"{PAGE_ID}-show-mode", "value"),
    Input(f"{PAGE_ID}-mode", "value"),
    Input(f"{PAGE_ID}-week-offset", "data"),
    Input(f"{PAGE_ID}-list-page", "data"),
)
def _update_content(depts, phys, appts, view, show_mode, mode,
                    week_offset, page):
    depts = depts or list(DEPARTMENTS)
    phys = phys or _physician_options()
    appts = appts or list(APPT_TYPES.keys())
    df = _filter(_open_slots(mode), depts, phys, appts, None, mode)
    if show_mode == "open":
        df = df[~df["IsTaken"]]

    # Calendar
    week_start, week_end = _week_bounds(week_offset or 0)
    grid = _calendar_view(df, week_start, week_end)
    title = f"Week of {week_start.strftime('%B %d, %Y')}"

    # List
    cards, page_label = _list_view(df, page or 1)

    # Last updated — read after the loader has run so the cache is populated
    last_updated = _format_last_updated()

    return grid, title, cards, page_label, last_updated


def _format_last_updated():
    """Format the ScheduleUpcoming source's last-modified time for display."""
    ts, source = schedule_upcoming_last_modified()
    if ts is None:
        return ""
    local = pd.Timestamp(ts).tz_convert("America/Los_Angeles")
    when = local.strftime("%b %-d, %Y at %-I:%M %p PT")
    where = "live R2 feed" if source == "r2" else "local file"
    return f"Last updated: {when} ({where})"
