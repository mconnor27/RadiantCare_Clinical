"""Sim Timing page — per-appointment CT-sim timing from Simulation Timing.csv.

Four charts (2x2), all driven by a shared milestone selection:

  Composition  stacked bar, median minutes per phase, monthly
  Density      histogram of first-milestone -> last-milestone minutes
  Booked vs Actual  dumbbell by ActivityName
  Overrun      % of sims running past the booked end

Dataset A / Dataset B compare mode mirrors the Workflow page: a second
filter bar appears and every chart renders both series.

Data caveats this page is built around (see docs/data-dictionary.md and the
help modal):

* The CT scanner clock ran 75-90 min slow and drifting until 2026-07-27.
  Any segment whose two endpoints come from different clocks (one ARIA, one
  scanner) is flagged CROSS-CLOCK and is only exact for rows where
  ``CTClockReliable`` is True.  Pre-fix rows carry an algorithmic correction
  (``CTClockOffsetMinutes``) that is sound for medians, not per-appointment.
* ``DocumentationCompleteDateTime`` is ``SetupNote_LastModified`` on ~93% of
  rows, and setup notes are amended a median of ~10 days after entry.  The
  default documentation milestone is therefore ``FirstNoteEnteredDateTime``
  (earliest system-set note stamp, ARIA-side, clock-immune).  The raw
  doc-complete stamp is still selectable, labelled as including amendments.
* This report requires matched CT imaging, so it is NOT a volume source.
  Sim counts come from the Simulations page.
"""

import dash
import dash_mantine_components as dmc
from dash import (
    callback, Input, Output, State, dcc, html, ctx,
    clientside_callback, ClientsideFunction,
)
from dash_iconify import DashIconify
import pandas as pd
import numpy as np

from config.settings import (
    CHART_COLORWAY, DEFAULT_GRAPH_CONFIG, PRIMARY, NEUTRAL,
)
from components.chart_card import chart_card, register_chart_callbacks
from components.kpi_card import kpi_card, kpi_placeholder
from components.detail_table import detail_table
from components.phi import apply_phi_grid_rules
from components.filter_bar import department_chips, physician_short_name
from components.diagnosis_filter import (
    diagnosis_accordion, register_diagnosis_callbacks,
)
from utils.diagnosis_categories import (
    build_code_to_category, build_code_to_subcategory, filter_by_diagnosis,
)

dash.register_page(__name__, path="/sim-timing", name="Simulation Timing", order=5)


# ---------------------------------------------------------------------------
# Date slider helpers (shared)
# ---------------------------------------------------------------------------

from utils.date_slider import (
    month_idx as _month_idx,
    idx_to_date as _idx_to_date,
    MAX_IDX as _MAX_IDX,
    preset_to_slider_val as _preset_to_slider_val,
    preset_to_exact_dates as _preset_to_exact_dates,
)

# The extract is clamped to a 2025-10-01 floor (CT image->machine attribution
# effectively began 2025-10-06), so there is no point letting the slider range
# back to the shared 2004 base year — it would crush all the data into the
# right edge.  Both the slider bounds and its marks are page-local.
_DEFAULT_DATE_PRESET = "12mo"
_DATA_FLOOR_IDX = _month_idx(2025, 10)
_ST_MARKS = [
    {"value": i, "label": _idx_to_date(i).strftime("%b '%y")}
    for i in range(_DATA_FLOOR_IDX, _MAX_IDX + 1)
    if (i - _DATA_FLOOR_IDX) % 3 == 0
]


# The CT clock was corrected 2026-07-27, so "Reliable only" has no data before
# that. The slider is month-granular, so July is the earliest useful month; it
# is a partial month and shown as such rather than rounded up to August, which
# would silently drop the reliable sims from the last days of July.
_RELIABLE_FLOOR_IDX = _month_idx(2026, 7)


def _clamp_slider(val):
    """Keep a slider value inside the page's data window."""
    if not val or len(val) != 2:
        return [_DATA_FLOOR_IDX, _MAX_IDX]
    lo = max(_DATA_FLOOR_IDX, min(val[0], _MAX_IDX))
    hi = max(lo, min(val[1], _MAX_IDX))
    return [lo, hi]


# ---------------------------------------------------------------------------
# Milestones
# ---------------------------------------------------------------------------
# ``clock`` is the lineage of the timestamp: "aria" (appointment/warehouse,
# trustworthy across all history) or "ct" (the scanner's own clock).  A segment
# spanning two different clocks is cross-clock and must be gated on
# CTClockReliable to be exact.

# Listed in the order they actually occur, which is what the charts plot.
# Two pairs are not in the order you would guess: patients check in a median of
# ~10 min before the booked start, and the note is entered a median of ~17 min
# before the appointment is closed out. Median offsets from the booked start:
# Check-In -10, Scheduled Start 0, CT First +20, CT Complete +22,
# Note Entered +37, Appointment End +55, Scheduled End +60.
MILESTONES = [
    # key,          label,               column,                          clock
    ("checkin",     "Check-In",          "CheckInDateTime",               "aria"),
    ("sched_start", "Scheduled Start",   "ScheduledStartDateTime",        "aria"),
    ("ct_first",    "CT First Series",   "CTFirstSeriesDateTime",         "ct"),
    ("ct_done",     "CT Complete",       "CTCompletedDateTime",           "ct"),
    ("note",        "Note Entered",      "FirstNoteEnteredDateTime",      "aria"),
    ("appt_end",    "Appointment End",   "ActualEndDateTime",             "aria"),
    ("sched_end",   "Scheduled End",     "ScheduledEndDateTime",          "aria"),
]
# DocumentationCompleteDateTime is deliberately NOT a milestone. It resolves to
# SetupNote_LastModified on ~93% of rows, and Set Up Notes are reopened and
# edited a median of ~10 days after the visit, so it measures how long notes
# stay open for revision rather than when documentation was done. Note Entered
# (the earliest system-set note stamp) is the documentation milestone.

_MS_BY_KEY = {k: (lbl, col, clock) for k, lbl, col, clock in MILESTONES}
_MS_ORDER = {k: i for i, (k, _, _, _) in enumerate(MILESTONES)}
_MS_LABEL = {k: lbl for k, lbl, _, _ in MILESTONES}

MILESTONE_OPTIONS = [{"value": k, "label": lbl} for k, lbl, _, _ in MILESTONES]

# Presets are chosen to be chronologically monotone in this data, so their
# composition stacks read cleanly.  "Full visit" deliberately includes the
# Scheduled Start -> Check-In segment, which is negative ~79% of the time
# (patients arrive early); it renders below the axis rather than being clipped.
PRESETS = {
    "visit":     ["checkin", "ct_done", "appt_end"],
    "full":      ["sched_start", "checkin", "ct_done", "appt_end", "note"],
    "scan":      ["ct_first", "ct_done"],
    "doc_tail":  ["ct_done", "note"],
}
PRESET_OPTIONS = [
    {"value": "visit", "label": "Visit"},
    {"value": "full", "label": "Full visit"},
    {"value": "scan", "label": "Scan only"},
    {"value": "doc_tail", "label": "Doc tail"},
]
_DEFAULT_MILESTONES = PRESETS["visit"]

# Per-milestone plausibility windows, in minutes from the booked start.
#
# Screening the milestone rather than each derived interval fixes the problem at
# source: an appointment closed out two days later poisons every interval that
# ends on it, and one window here removes it from all of them at once. Both
# endpoints of any interval are screened, so no separate per-segment clamp is
# needed.
#
# Defaults are drawn from the observed distributions — roughly p1 to p99,
# rounded out generously so ordinary variation is never cut. Scheduled Start is
# always exactly 0 and Scheduled End is the booked slot (observed 30-210 min);
# neither can be wrong, so neither is screened.
#
#   key, label, slider_min, slider_max, default (lo, hi), strict (lo, hi)
MILESTONE_WINDOWS = [
    ("checkin",  "Check-In",        -240,  240, (-120, 120), (-60,  90)),
    ("ct_first", "CT First Series", -240,  480, ( -60, 240), (-30, 120)),
    ("ct_done",  "CT Complete",     -240,  480, ( -60, 240), (-30, 150)),
    ("appt_end", "Appointment End", -240,  720, ( -60, 240), (  0, 180)),
    ("note",     "Note Entered",    -480, 1440, (-240, 720), (  0, 240)),
]
_WINDOW_KEYS = [w[0] for w in MILESTONE_WINDOWS]


def _window_preset(mode):
    """[[lo, hi], ...] for a named preset, in MILESTONE_WINDOWS order."""
    out = []
    for _k, _lbl, smin, smax, dflt, strict in MILESTONE_WINDOWS:
        if mode == "strict":
            out.append(list(strict))
        elif mode == "off":
            out.append([smin, smax])
        else:
            out.append(list(dflt))
    return out


def _apply_milestone_windows(df, windows, drop_rows=False, selected=None):
    """Null milestone timestamps that fall outside their plausibility window.

    Nulling rather than dropping keeps an appointment usable for the intervals
    it *is* clean for — a late close-out shouldn't discard its check-in-to-CT
    time. With *drop_rows* the whole appointment is removed instead, but only
    when the offending milestone is one the current selection actually uses.
    """
    if df.empty or "ScheduledStartDateTime" not in df.columns:
        return df
    base = df["ScheduledStartDateTime"]
    windows = windows or _window_preset("default")
    selected = set(selected or [])
    bad_any = pd.Series(False, index=df.index)

    for i, (key, _lbl, smin, smax, _d, _s) in enumerate(MILESTONE_WINDOWS):
        col = _MS_BY_KEY[key][1]
        if col not in df.columns or i >= len(windows):
            continue
        win = windows[i]
        if not isinstance(win, (list, tuple)) or len(win) != 2:
            continue
        lo, hi = win
        if lo is None or hi is None:
            continue
        # Handles parked at the ends mean "unbounded", not a real cut.
        lo_b = None if lo <= smin else lo
        hi_b = None if hi >= smax else hi
        if lo_b is None and hi_b is None:
            continue
        offs = (df[col] - base).dt.total_seconds() / 60.0
        outside = pd.Series(False, index=df.index)
        if lo_b is not None:
            outside |= offs < lo_b
        if hi_b is not None:
            outside |= offs > hi_b
        bad = offs.notna() & outside
        if drop_rows and key in selected:
            bad_any |= bad
        else:
            df.loc[bad, col] = pd.NaT

    if drop_rows and bad_any.any():
        df = df[~bad_any]
    return df

ERA_OPTIONS = [
    {"value": "all", "label": "All (corrected)"},
    {"value": "reliable", "label": "Reliable only"},
]

# Treatment technique of the course the sim led to, from Courses.csv. Filtering
# is ANY-match against the course's full technique set, not just the primary
# label, so picking "Electron" also finds the breast courses whose electron
# boost sits behind a 3D primary.
TECHNIQUES = ["3D", "Electron", "IMRT", "VMAT", "SBRT", "SRS"]

# Setup flags. 4DCT is derived from SeriesCount (a 4D CT is ten respiratory
# phase bins, and the series-count distribution is cleanly bimodal); the rest
# are read off the CT series names. Neither source is PHI.
#
# A flag means "a scan of this kind was acquired during the appointment" — with
# one deliberate exception: free breathing is the default state, so it is only
# flagged when no breath-hold was acquired. A DIBH sim takes both scans, and
# flagging its FB series would say nothing the DIBH flag does not already say.
SETUP_FLAGS = [
    ("4DCT", "4D CT"),
    ("APBI", "APBI"),
    ("DIBH", "Breath hold"),
    ("Decub", "Decubitus"),
    ("FreeBreath", "Free breathing (no BH)"),
    ("Prone", "Prone"),
]

SPREAD_OPTIONS = [
    {"value": "iqr", "label": "IQR"},
    {"value": "sd", "label": "±1 SD"},
    {"value": "p10_90", "label": "P10–90"},
]

OVERRUN_OPTIONS = [
    {"value": "doc", "label": "Documented"},
    {"value": "appt", "label": "Appointment end"},
    {"value": "ct", "label": "CT complete"},
]

_DATASET_COLORS = {"A": "#2196F3", "B": "#FF9800"}

# Duration filter — mirrors the Simulations page. The top handle is treated as
# unbounded so the long tail (booked slots up to 210 min) is kept.
_DURATION_SLIDER_MIN = 0
_DURATION_SLIDER_MAX = 180


# Series count. The distribution is bimodal — 1-6 for a conventional sim, then
# 12-26 for a 4D CT's ten phase bins plus reconstructions — with nothing at all
# in between, so the slider marks straddle that gap.
_SERIES_SLIDER_MIN = 1
_SERIES_SLIDER_MAX = 26


def _apply_series_filter(df, series):
    """Keep rows whose SeriesCount falls in [low, high]; top handle unbounded."""
    if "SeriesCount" not in df.columns:
        return df
    if not isinstance(series, (list, tuple)) or len(series) != 2:
        return df
    lo, hi = series
    if lo is None or hi is None:
        return df
    if lo <= _SERIES_SLIDER_MIN and hi >= _SERIES_SLIDER_MAX:
        return df
    d = pd.to_numeric(df["SeriesCount"], errors="coerce")
    mask = d.notna() & (d >= lo)
    if hi < _SERIES_SLIDER_MAX:
        mask &= d <= hi
    return df[mask]


def _apply_duration_filter(df, duration):
    """Keep rows whose ScheduledDurationMinutes falls in [low, high]."""
    if "ScheduledDurationMinutes" not in df.columns:
        return df
    if not isinstance(duration, (list, tuple)) or len(duration) != 2:
        return df
    lo, hi = duration
    if lo is None or hi is None:
        return df
    if lo <= _DURATION_SLIDER_MIN and hi >= _DURATION_SLIDER_MAX:
        return df
    d = pd.to_numeric(df["ScheduledDurationMinutes"], errors="coerce")
    mask = d.notna() & (d >= lo)
    if hi < _DURATION_SLIDER_MAX:
        mask &= d <= hi
    return df[mask]


def _selected_milestones(milestone_keys):
    """De-duplicated, canonically ordered subset of valid milestone keys."""
    return sorted({k for k in (milestone_keys or []) if k in _MS_BY_KEY},
                  key=lambda k: _MS_ORDER[k])


def _segments_for(milestone_keys):
    """Ordered consecutive (start_key, end_key) pairs for a milestone selection.

    Returns [] when fewer than two milestones are selected — every chart on
    this page needs at least one start and one end.
    """
    keys = [k for k in (milestone_keys or []) if k in _MS_BY_KEY]
    keys = sorted(set(keys), key=lambda k: _MS_ORDER[k])
    return list(zip(keys, keys[1:]))


def _is_cross_clock(a_key, b_key):
    return _MS_BY_KEY[a_key][2] != _MS_BY_KEY[b_key][2]


def _segment_label(a_key, b_key):
    return f"{_MS_LABEL[a_key]} → {_MS_LABEL[b_key]}"


# ---------------------------------------------------------------------------
# ID helper
# ---------------------------------------------------------------------------

def _id(prefix, suffix):
    return f"{prefix}-{suffix}"


# ---------------------------------------------------------------------------
# Filter option builders — computed once at import from the full extract
# ---------------------------------------------------------------------------

def _distinct(col):
    """Sorted distinct non-blank values of a column in the timing extract."""
    try:
        from data.loader import load_simulation_timing
        df = load_simulation_timing()
    except Exception:
        return []
    if df.empty or col not in df.columns:
        return []
    return sorted({str(v) for v in df[col].dropna() if str(v).strip()})


# Physician role -> column, same mapping the Simulations page uses.
_PHYS_COL = {
    "consult": "ConsultPhysician",
    "supervising": "SupervisingPhysician",
    "attending": "AttendingPhysician",
}


# Display names for ARIA activity names. Deliberately a local copy of the map
# in pages/simulations.py rather than an import: importing a sibling page module
# re-executes it outside Dash's page registry, which registers every one of its
# @callback decorators a second time and breaks that page with duplicate-output
# errors. Only the six names below ever appear in the timing extract; the rest
# are carried so the two pages label things identically if that changes.
_SIM_TYPE_DISPLAY = {
    "Bite Block Fabrication-Stereotactic": "Bite Block Fabrication – SRS",
    "Decub Breast CT- Aberdeen":          "Decub Breast – Aberdeen",
    "Decub breast electron CT sim":       "Decub Breast",
    "Initial Aberdeen Simulation":        "Initial Simulation – Aberdeen",
    "Initial Centralia-in Lacey":         "Initial Simulation – Centralia",
    "Initial Simulation":                 "Initial Simulation",
    "RE-Simulation-Aberdeen":             "Re-Simulation – Aberdeen",
    "Re-Simulation":                      "Re-Simulation",
    "Re-seat  Bite Block Test":           "Bite Block Re-seat Test",
    "Stereotactic Simulation":            "Stereotactic Simulation (SRS)",
    "Treatment Device Fabrication":       "Treatment Device Fabrication",
    "electron- CSU on machine":           "Electron CSU On-Machine",
    "initial simulation on PET/CT table": "Initial Simulation – PET/CT",
}


def _sim_display_name(raw):
    """Clean display name for a sim type — mirrors the Simulations page."""
    return _SIM_TYPE_DISPLAY.get(raw, raw)


def _is_initial_sim(activity_name):
    """Initial (non-repeat) simulation — same rule as the Simulations page."""
    if pd.isna(activity_name):
        return False
    low = str(activity_name).lower()
    return "initial" in low or "stereotactic simulation" in low


# ---------------------------------------------------------------------------
# Filter bar
# ---------------------------------------------------------------------------

def _chip_dropdown(prefix, key, label, chips, multiple=True, panel_extra=None,
                   width=None, default=None):
    """Trigger button + click-away chip panel, matching the Simulations page.

    assets/chip_dropdown.js discovers these by convention: a button whose id
    ends in "-trigger" and a sibling ".wf-chip-dropdown" panel inside a shared
    inline-block wrapper.
    """
    panel_children = list(panel_extra or [])
    panel_children.append(
        dmc.ChipGroup(children=chips, id=_id(prefix, f"filter-{key}"),
                      multiple=multiple,
                      value=default if default is not None
                      else ([] if multiple else None))
    )
    style = {"display": "none"}
    if width:
        style["minWidth"] = width
    return html.Div(
        children=[
            html.Div(
                children=[
                    dmc.Button(
                        label, id=_id(prefix, f"{key}-trigger"),
                        variant="default", size="sm",
                        rightSection=DashIconify(icon="mdi:chevron-down", width=14),
                    ),
                    dmc.ActionIcon(
                        DashIconify(icon="mdi:close-circle", width=18),
                        id=_id(prefix, f"{key}-clear"),
                        variant="subtle", color="gray", size="sm",
                        className="wf-filter-clear-btn",
                    ),
                ],
                style={"position": "relative", "display": "inline-block"},
            ),
            dmc.Paper(
                children=panel_children,
                id=_id(prefix, f"{key}-panel"),
                p="xs", shadow="md", withBorder=True, radius="md",
                className="wf-chip-dropdown", style=style,
            ),
        ],
        style={"position": "relative", "display": "inline-block"},
    )


def _build_filter_bar(prefix, label=None):
    """Build a complete filter bar for one dataset.

    Mirrors the Simulations page's two-row layout and chip-dropdown idiom so
    the two pages feel like one product: department chips, a physician
    dropdown with a Consult/Supervising/Attending role toggle, sim type,
    diagnosis, inpatient and Initial-only scope.  The page-specific controls
    (milestone picker, CT clock era, outlier screen) use the same idiom.

    prefix: "st" for dataset A, "st-b" for dataset B.
    """
    badge = []
    if label:
        badge = [
            dmc.Badge(
                label, color="blue" if label == "A" else "orange",
                variant="filled", size="sm",
                className="st-dataset-badge-a" if label == "A" else "",
                style={"minWidth": "26px"},
            )
        ]

    sv = _clamp_slider(_preset_to_slider_val(_DEFAULT_DATE_PRESET, _MAX_IDX))

    return dmc.Paper(
        children=[
            # Row 1 — cohort filters (mirrors the Simulations page)
            dmc.Group(
                children=[
                    *badge,
                    department_chips(prefix),

                    # Physician, with the same role toggle the Simulations page uses
                    _chip_dropdown(
                        prefix, "physician", "Physician", [], multiple=False,
                        panel_extra=[
                            dcc.Store(id=_id(prefix, "physician-role"), data="consult"),
                            dmc.SegmentedControl(
                                id=_id(prefix, "physician-role-ctrl"),
                                data=[
                                    {"value": "consult", "label": "Consult"},
                                    {"value": "supervising", "label": "Supervising"},
                                    {"value": "attending", "label": "Attending"},
                                ],
                                value="consult", size="xs", fullWidth=True, mb="xs",
                            ),
                        ],
                    ),

                    # Therapist — this page's distinctive cohort cut
                    _chip_dropdown(
                        prefix, "therapist", "Therapist",
                        [dmc.Chip(physician_short_name(t), value=t, size="xs",
                                  variant="filled")
                         for t in _THERAPISTS],
                    ),

                    _chip_dropdown(
                        prefix, "simtype", "Type",
                        [dmc.Chip(_sim_display_name(t), value=t, size="xs",
                                  variant="filled")
                         for t in _SIM_TYPES],
                    ),

                    _chip_dropdown(
                        prefix, "technique", "Technique",
                        [dmc.Chip(t, value=t, size="xs", variant="filled")
                         for t in TECHNIQUES],
                    ),
                    _chip_dropdown(
                        prefix, "setup", "Setup",
                        [dmc.Chip(lbl, value=key, size="xs", variant="filled")
                         for key, lbl in SETUP_FLAGS],
                    ),

                    diagnosis_accordion(prefix),

                    # Scope: All / Initial (same control as the Simulations page)
                    dmc.SegmentedControl(
                        id=_id(prefix, "scope"),
                        data=[
                            {"value": "all", "label": "All"},
                            {"value": "initial", "label": "Initial"},
                        ],
                        value="all", size="xs",
                    ),
                    dmc.Switch(
                        id=_id(prefix, "inpatient-switch"),
                        label="Inpatient", size="xs", checked=False,
                    ),
                    dmc.Switch(
                        id=_id(prefix, "weekend-switch"),
                        label="Weekend", size="xs", checked=False,
                    ),

                    # marginLeft:auto on the flex child right-aligns Compare.
                    # A flex spacer would instead eat the row's slack and push
                    # the button onto a line of its own once the row wraps, and
                    # the prop has to sit on this wrapper rather than on the
                    # Button, since the Tooltip is what the Group lays out.
                    *(
                        [
                            html.Div(
                                style={"marginLeft": "auto"},
                                children=dmc.Tooltip(
                                    dmc.Button(
                                        "Compare", id="st-compare-toggle",
                                        variant="light", color="gray",
                                        size="compact-sm",
                                        leftSection=DashIconify(
                                            icon="mdi:compare-horizontal", width=16),
                                    ),
                                    label="Compare two filter sets side by side",
                                    withArrow=True, position="bottom",
                                ),
                            )
                        ]
                        if prefix == "st" else []
                    ),
                ],
                gap="md", wrap="wrap", align="center",
            ),

            # Row 2 — timing-specific controls
            dmc.Group(
                children=[
                    # Milestone picker: presets inside the panel, and the trigger
                    # label spells out the resulting chain.
                    _chip_dropdown(
                        prefix, "milestones", "Milestones",
                        [dmc.Chip(lbl, value=k, size="xs", variant="filled")
                         for k, lbl, _, _ in MILESTONES],
                        panel_extra=[
                            dmc.SegmentedControl(
                                id=_id(prefix, "preset-milestones"),
                                data=PRESET_OPTIONS, value="visit",
                                size="xs", fullWidth=True, mb="xs",
                            ),
                            dmc.Text("Pick 2+ — gaps between consecutive "
                                     "milestones become the phases.",
                                     size="xs", c="#6B7280", mb="xs"),
                        ],
                        width="260px",
                        default=list(_DEFAULT_MILESTONES),
                    ),
                    dmc.Tooltip(
                        dmc.Badge(
                            "cross-clock", id=_id(prefix, "crossclock-badge"),
                            color="orange", variant="light", size="sm",
                            leftSection=DashIconify(
                                icon="mdi:clock-alert-outline", width=13),
                            style={"display": "none"},
                        ),
                        label=(
                            "A selected segment spans the ARIA clock and the CT "
                            "scanner clock. The scanner ran 75-90 min slow until "
                            "2026-07-27; pre-fix rows are algorithmically corrected "
                            "(good for medians, +/-10-20 min per appointment)."
                        ),
                        multiline=True, w=300, withArrow=True, position="bottom",
                    ),
                    dmc.Tooltip(
                        dmc.SegmentedControl(
                            id=_id(prefix, "filter-era"), data=ERA_OPTIONS,
                            value="all", size="xs",
                        ),
                        label=(
                            "Reliable only keeps appointments on or after "
                            "2026-07-27, whose CT timestamps were never wrong. "
                            "Choosing it pulls the date range forward to that "
                            "era, since nothing earlier can match; switching "
                            "back restores the range you had."
                        ),
                        multiline=True, w=280, withArrow=True, position="bottom",
                    ),
                    dcc.Store(id=_id(prefix, "era-prev-range")),
                    # Per-milestone plausibility windows
                    html.Div(
                        children=[
                            dmc.Button(
                                "Outliers: Default",
                                id=_id(prefix, "outlier-trigger"),
                                variant="default", size="sm",
                                leftSection=DashIconify(icon="mdi:filter-variant", width=14),
                                rightSection=DashIconify(icon="mdi:chevron-down", width=14),
                            ),
                            dmc.Paper(
                                children=[
                                    dmc.Group(gap="xs", mb="sm", children=[
                                        dmc.Button("Default",
                                                   id=_id(prefix, "outlier-preset-default"),
                                                   size="compact-xs", variant="light",
                                                   color="violet"),
                                        dmc.Button("Strict",
                                                   id=_id(prefix, "outlier-preset-strict"),
                                                   size="compact-xs", variant="light",
                                                   color="violet"),
                                        dmc.Button("Off",
                                                   id=_id(prefix, "outlier-preset-off"),
                                                   size="compact-xs", variant="light"),
                                    ]),
                                    *[
                                        dmc.Box(mb=18, children=[
                                            dmc.Group(justify="space-between", children=[
                                                dmc.Text(lbl, size="xs", c="#6B7280"),
                                                dmc.Text(f"{d[0]} to {d[1]}",
                                                         id=_id(prefix, f"outlier-val-{i}"),
                                                         size="xs", fw=600, c=PRIMARY),
                                            ]),
                                            dmc.RangeSlider(
                                                id=_id(prefix, f"outlier-win-{i}"),
                                                min=smin, max=smax, step=15,
                                                value=list(d),
                                                marks=[{"value": 0, "label": "0"}],
                                                color="violet", size="xs", minRange=0,
                                                showLabelOnHover=True,
                                            ),
                                        ])
                                        for i, (_k, lbl, smin, smax, d, _st)
                                        in enumerate(MILESTONE_WINDOWS)
                                    ],
                                    dmc.Switch(
                                        id=_id(prefix, "outlier-drop-switch"),
                                        label="Drop the whole appointment instead",
                                        size="xs", checked=False, mt="xs",
                                    ),
                                    dmc.Text(
                                        "Scheduled Start and Scheduled End are not "
                                        "screened — one is always 0 and the other is "
                                        "the booked slot.",
                                        size="xs", c="#9CA3AF", mt="xs",
                                    ),
                                ],
                                id=_id(prefix, "outlier-panel"),
                                p="sm", shadow="md", withBorder=True, radius="md",
                                className="wf-chip-dropdown",
                                style={"display": "none", "minWidth": "320px"},
                            ),
                        ],
                        style={"position": "relative", "display": "inline-block"},
                    ),
                    # Duration range — same pop-down panel the Simulations page uses
                    html.Div(
                        children=[
                            dmc.Button(
                                "Duration", id=_id(prefix, "duration-trigger"),
                                variant="default", size="sm",
                                leftSection=DashIconify(icon="mdi:timer-outline", width=14),
                                rightSection=DashIconify(icon="mdi:chevron-down", width=14),
                            ),
                            dmc.Paper(
                                children=[
                                    dmc.Group(
                                        justify="space-between", mb=6,
                                        children=[
                                            dmc.Text("Booked Slot Length", size="xs",
                                                     c="#6B7280"),
                                            dmc.Text("All", id=_id(prefix, "duration-label"),
                                                     size="xs", fw=600, c=PRIMARY),
                                        ],
                                    ),
                                    dmc.RangeSlider(
                                        id=_id(prefix, "filter-duration"),
                                        min=_DURATION_SLIDER_MIN, max=_DURATION_SLIDER_MAX,
                                        step=5,
                                        value=[_DURATION_SLIDER_MIN, _DURATION_SLIDER_MAX],
                                        marks=[
                                            {"value": 0, "label": "0"},
                                            {"value": 30, "label": "30"},
                                            {"value": 60, "label": "60"},
                                            {"value": 90, "label": "90"},
                                            {"value": 120, "label": "120"},
                                            {"value": 150, "label": "150"},
                                            {"value": 180, "label": "180+"},
                                        ],
                                        color="violet", size="sm", minRange=0, mb="sm",
                                    ),
                                    dmc.Button(
                                        "Reset", id=_id(prefix, "duration-reset"),
                                        size="compact-xs", variant="light",
                                        color="violet", mt="sm",
                                    ),
                                ],
                                id=_id(prefix, "duration-panel"),
                                p="sm", shadow="md", withBorder=True, radius="md",
                                className="wf-chip-dropdown",
                                style={"display": "none", "minWidth": "280px"},
                            ),
                        ],
                        style={"position": "relative", "display": "inline-block"},
                    ),
                    # Series count — the 4D CT discriminator
                    html.Div(
                        children=[
                            dmc.Button(
                                "Series", id=_id(prefix, "series-trigger"),
                                variant="default", size="sm",
                                leftSection=DashIconify(icon="mdi:layers-outline", width=14),
                                rightSection=DashIconify(icon="mdi:chevron-down", width=14),
                            ),
                            dmc.Paper(
                                children=[
                                    dmc.Group(
                                        justify="space-between", mb=6,
                                        children=[
                                            dmc.Text("Series Count", size="xs", c="#6B7280"),
                                            dmc.Text("All", id=_id(prefix, "series-label"),
                                                     size="xs", fw=600, c=PRIMARY),
                                        ],
                                    ),
                                    dmc.RangeSlider(
                                        id=_id(prefix, "filter-series"),
                                        min=_SERIES_SLIDER_MIN, max=_SERIES_SLIDER_MAX,
                                        step=1,
                                        value=[_SERIES_SLIDER_MIN, _SERIES_SLIDER_MAX],
                                        marks=[
                                            {"value": 1, "label": "1"},
                                            {"value": 5, "label": "5"},
                                            {"value": 10, "label": "10"},
                                            {"value": 15, "label": "15"},
                                            {"value": 20, "label": "20"},
                                            {"value": 26, "label": "26+"},
                                        ],
                                        color="violet", size="sm", minRange=0, mb=26,
                                    ),
                                    dmc.Group(gap="xs", mt="sm", children=[
                                        dmc.Button("Conventional (1–6)",
                                                   id=_id(prefix, "series-preset-conv"),
                                                   size="compact-xs", variant="light",
                                                   color="violet"),
                                        dmc.Button("4D CT (10+)",
                                                   id=_id(prefix, "series-preset-4d"),
                                                   size="compact-xs", variant="light",
                                                   color="violet"),
                                        dmc.Button("Reset",
                                                   id=_id(prefix, "series-reset"),
                                                   size="compact-xs", variant="light"),
                                    ]),
                                ],
                                id=_id(prefix, "series-panel"),
                                p="sm", shadow="md", withBorder=True, radius="md",
                                className="wf-chip-dropdown",
                                style={"display": "none", "minWidth": "290px"},
                            ),
                        ],
                        style={"position": "relative", "display": "inline-block"},
                    ),
                ],
                gap="md", wrap="wrap", align="center", mt="xs",
            ),

            # Row 3 — date controls (identical to the Simulations page)
            dmc.Group(
                children=[
                    dmc.Select(
                        id=_id(prefix, "filter-date-preset"),
                        data=[
                            {"value": "12mo", "label": "Prior 12 mo"},
                            {"value": "6mo", "label": "Prior 6 mo"},
                            {"value": "3mo", "label": "Prior 3 mo"},
                            {"value": "30d", "label": "Prior 30 days"},
                            {"value": "ytd", "label": "Year to Date"},
                            {"value": "current_year", "label": "Current Year"},
                            {"value": "last_year", "label": "Last Year"},
                            {"value": "this_month", "label": "This Month"},
                            {"value": "last_month", "label": "Last Month"},
                            {"value": "all", "label": "All Time"},
                            {"value": "custom", "label": "Custom Range"},
                        ],
                        value=_DEFAULT_DATE_PRESET,
                        size="xs", w=150, allowDeselect=False,
                        leftSection=DashIconify(icon="mdi:clock-outline", width=14),
                        comboboxProps={"zIndex": 500, "offset": 2},
                        maxDropdownHeight=400,
                    ),
                    dmc.Paper(
                        dcc.DatePickerRange(
                            id=_id(prefix, "filter-daterange"),
                            display_format="MMM D, YYYY",
                            start_date_placeholder_text="Start",
                            end_date_placeholder_text="End",
                            clearable=True, number_of_months_shown=2, minimum_nights=0,
                            start_date=_idx_to_date(sv[0]).strftime("%Y-%m-%d"),
                            end_date=_idx_to_date(sv[1], end_of_month=True).strftime("%Y-%m-%d"),
                            className="wf-date-picker-range",
                        ),
                        px="xs", py=4, radius="sm", withBorder=True,
                        className="wf-datepicker-wrapper",
                    ),
                    dmc.Box(
                        children=[
                            html.Div(id=_id(prefix, "date-range-label"),
                                     style={"display": "none"}),
                            dmc.RangeSlider(
                                id=_id(prefix, "date-slider"),
                                min=_DATA_FLOOR_IDX, max=_MAX_IDX, step=1,
                                value=sv, marks=_ST_MARKS,
                                color="violet", size="sm", minRange=0,
                            ),
                        ],
                        # This page's marks are month-and-year ("Oct '25"), not
                        # the bare years other pages use, and the first one sits
                        # exactly at the track start — so it centres half its
                        # width off the left edge and collides with the date
                        # picker. The inset gives it room.
                        style={"flex": "1", "minWidth": "280px",
                               "paddingLeft": "14px", "paddingRight": "12px"},
                    ),
                ],
                gap="md", align="center", mt="xs",
            ),
        ],
        p="sm", px="md", radius="md", shadow="xs", withBorder=True,
    )



# Chip lists are built at import so both filter bars share them and the chips
# are stable (no callback race on first paint).
_THERAPISTS = _distinct("CompletedByUser")
_SIM_TYPES = _distinct("ActivityName")


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------

layout = dmc.Stack(
    gap=16,
    className="page-content",
    children=[
        dmc.Box(
            className="page-sticky-header",
            children=[
                dmc.Group(
                    justify="center", align="center", gap=8,
                    children=[
                        dmc.Title("Simulation Timing", order=2,
                                  className="page-title", style={"margin": 0}),
                        dmc.Tooltip(
                            DashIconify(icon="mdi:information-outline", width=18,
                                        color="#9CA3AF"),
                            label=(
                                "Lacey CT_Sim only, completed sims with matched "
                                "CT imaging. Not a volume source — sims without "
                                "an attributed scan are absent, not blank. Use "
                                "the Simulations page for counts."
                            ),
                            multiline=True, w=340, withArrow=True,
                            position="bottom",
                        ),
                    ],
                ),
                html.Div(
                    id="st-a-filter-container",
                    style={"position": "relative"},
                    children=[_build_filter_bar("st", "A")],
                ),
                html.Div(
                    id="st-b-filter-container",
                    style={"display": "none"},
                    children=[_build_filter_bar("st-b", "B")],
                ),
            ],
        ),

        # KPI row
        dmc.Grid(id="st-kpi-row", gutter=16, children=[
            dmc.GridCol(kpi_placeholder(), span={"base": 12, "sm": 6, "md": 2.4})
            for _ in range(5)
        ]),

        # Row 1 — Composition + Density
        dmc.Grid(
            gutter="md",
            children=[
                dmc.GridCol(
                    span={"base": 12, "lg": 6},
                    children=chart_card(
                        "st-chart-composition",
                        "Phase Composition",
                        settings_id="st-composition",
                        show_smooth=False,
                        show_grouping=True,
                        extra_controls=[
                            dmc.SegmentedControl(
                                id="st-composition-agg",
                                data=[
                                    {"value": "median", "label": "Median"},
                                    {"value": "mean", "label": "Mean"},
                                ],
                                value="median", size="xs",
                            ),
                            dmc.SegmentedControl(
                                id="st-composition-period",
                                data=[
                                    {"value": "W", "label": "Week"},
                                    {"value": "M", "label": "Month"},
                                    {"value": "Y", "label": "Year"},
                                ],
                                value="M", size="xs",
                            ),
                        ],
                    ),
                ),
                dmc.GridCol(
                    span={"base": 12, "lg": 6},
                    children=chart_card(
                        "st-chart-density",
                        "End-to-End Distribution",
                        settings_id="st-density",
                        show_smooth=False,
                        show_grouping=False,
                        extra_controls=[
                            dmc.SegmentedControl(
                                id="st-density-bins",
                                data=[
                                    {"value": "10", "label": "10m"},
                                    {"value": "15", "label": "15m"},
                                    {"value": "30", "label": "30m"},
                                ],
                                value="10", size="xs",
                            ),
                        ],
                    ),
                ),
            ],
        ),

        # Row 2 — Dumbbell + Overrun
        dmc.Grid(
            gutter="md",
            children=[
                dmc.GridCol(
                    span={"base": 12, "lg": 6},
                    children=chart_card(
                        "st-chart-dumbbell",
                        "Booked vs Actual",
                        settings_id="st-dumbbell",
                        chart_types=[
                            {"value": "violin", "label": "Violin"},
                            {"value": "dumbbell", "label": "Dumbbell"},
                        ],
                        chart_type_default="violin",
                        show_smooth=False,
                        show_grouping=False,
                        extra_controls=[
                            dmc.SegmentedControl(
                                id="st-dumbbell-group",
                                data=[
                                    {"value": "ActivityName", "label": "Sim Type"},
                                    {"value": "CompletedByUser", "label": "Therapist"},
                                    {"value": "ConsultPhysician", "label": "MD"},
                                    {"value": "SimTechnique", "label": "Technique"},
                                ],
                                value="ActivityName", size="xs",
                            ),
                        ],
                    ),
                ),
                dmc.GridCol(
                    span={"base": 12, "lg": 6},
                    children=chart_card(
                        "st-chart-overrun",
                        "Overrun Rate",
                        settings_id="st-overrun",
                        show_smooth=True,
                        smooth_min=0, smooth_max=1, smooth_step=0.05,
                        smooth_default=0,
                        slider_label="Smoothing",
                        show_grouping=False,
                        extra_controls=[
                            dmc.Tooltip(
                                dmc.SegmentedControl(
                                    id="st-overrun-def",
                                    data=OVERRUN_OPTIONS,
                                    value="doc", size="xs",
                                ),
                                label=(
                                    "Documented is when the note was entered — the "
                                    "work actually finishing, rather than the "
                                    "clerical act of closing the appointment. It is "
                                    "ARIA-side on both sides, so it is valid across "
                                    "all history, as is Appointment end. CT complete "
                                    "vs booked end is cross-clock."
                                ),
                                multiline=True, w=280, withArrow=True, position="bottom",
                            ),
                        ],
                    ),
                ),
            ],
        ),

        # Row 3 — the cohort's "typical sim", on the same axis as the drill-down
        dmc.Paper(
            children=[
                dmc.Group(justify="space-between", mb=0, children=[
                    dmc.Text("Typical Sim", size="sm", fw=500,
                             c=NEUTRAL["text_secondary"]),
                    dmc.Group(gap="xs", children=[
                        dmc.SegmentedControl(
                            id="st-typical-center",
                            data=[
                                {"value": "median", "label": "Median"},
                                {"value": "mean", "label": "Mean"},
                            ],
                            value="median", size="xs",
                        ),
                        dmc.SegmentedControl(
                            id="st-typical-spread",
                            data=SPREAD_OPTIONS, value="iqr", size="xs",
                        ),
                    ]),
                ]),
                dmc.Text(
                    "Each milestone across every filtered sim, aligned on its "
                    "own booked start — the same axis the drill-down strip "
                    "uses. Bar = spread, dot = centre.",
                    size="xs", c="#9CA3AF", mb=4,
                ),
                dmc.Box(
                    pos="relative",
                    style={"height": "300px"},
                    children=[
                        dmc.LoadingOverlay(
                            id="st-typical-loading", visible=False,
                            loaderProps={"type": "dots", "color": PRIMARY},
                            transitionProps={"duration": 600, "exitDuration": 80},
                        ),
                        dcc.Graph(id="st-chart-typical", config=DEFAULT_GRAPH_CONFIG,
                                  responsive=True,
                                  style={"height": "100%", "width": "100%"}),
                    ],
                ),
            ],
            p="sm", radius="md", shadow="xs", withBorder=True,
        ),

        # Row 4 — When overruns happen, and the per-appointment drill-down
        dmc.Paper(
            children=[
                dmc.Group(justify="space-between", mb=0, children=[
                    dmc.Text("When Sims Run Long", size="sm", fw=500,
                             c=NEUTRAL["text_secondary"]),
                    dmc.Group(gap="xs", children=[
                        dmc.SegmentedControl(
                            id="st-heatmap-metric",
                            data=[
                                {"value": "overrun", "label": "Overrun %"},
                                {"value": "visit", "label": "Median visit"},
                                {"value": "volume", "label": "Volume"},
                            ],
                            value="overrun", size="xs",
                        ),
                    ]),
                ]),
                dmc.Text(
                    "Rows = weekday, columns = booked start hour. "
                    "Click a cell to drill into those appointments. "
                    "Rate cells with fewer than 3 sims are left uncoloured.",
                    size="xs", c="#9CA3AF", mb=4,
                ),
                dmc.Box(
                    pos="relative",
                    style={"height": "300px"},
                    children=[
                        dmc.LoadingOverlay(
                            id="st-heatmap-loading", visible=False,
                            loaderProps={"type": "dots", "color": PRIMARY},
                            transitionProps={"duration": 600, "exitDuration": 80},
                        ),
                        dcc.Graph(id="st-chart-heatmap", config=DEFAULT_GRAPH_CONFIG,
                                  responsive=True,
                                  style={"height": "100%", "width": "100%"}),
                    ],
                ),
            ],
            p="sm", radius="md", shadow="xs", withBorder=True,
        ),

        # Breadcrumb — mirrors the Machine Downtime drill-down affordance
        dmc.Group(gap="xs", align="center", children=[
            html.Div("All appointments", id="st-breadcrumb",
                     className="machines-breadcrumb"),
            dmc.Button("Clear selection", id="st-drill-clear",
                       size="compact-xs", variant="light", color="violet",
                       style={"display": "none"}),
        ]),

        # Per-appointment timeline (level 3)
        dmc.Paper(
            id="st-timeline-card",
            style={"display": "none"},
            children=[
                dmc.Group(justify="space-between", mb=0, children=[
                    dmc.Text("Appointment Timeline", id="st-timeline-title",
                             size="sm", fw=500, c=NEUTRAL["text_secondary"]),
                    dmc.Group(gap="xs", children=[
                        dmc.Badge(id="st-timeline-era", size="sm", variant="light"),
                        dmc.Text(id="st-timeline-meta", size="xs", c="#9CA3AF"),
                    ]),
                ]),
                dmc.Box(
                    id="st-timeline-box",
                    style={"height": "210px"},
                    children=[
                        dcc.Graph(id="st-chart-timeline", config=DEFAULT_GRAPH_CONFIG,
                                  responsive=True,
                                  style={"height": "100%", "width": "100%"}),
                    ],
                ),
            ],
            p="sm", radius="md", shadow="xs", withBorder=True,
        ),

        detail_table(
            "st-detail-grid",
            title="Appointment Detail",
            export_id="st-table-export",
            accordion_id="st-detail-accordion",
            extra_controls=[
                dmc.Text("Click a row to see its timeline", size="xs", c="#9CA3AF"),
            ],
        ),

        dcc.Interval(id="st-interval", interval=300_000, n_intervals=0, max_intervals=0),

        # Dataset A stores
        dcc.Store(id="st-store-composition"),
        dcc.Store(id="st-store-density"),
        dcc.Store(id="st-store-dumbbell"),
        dcc.Store(id="st-store-overrun"),

        # Dataset B stores
        dcc.Store(id="st-b-store-composition"),
        dcc.Store(id="st-b-store-density"),
        dcc.Store(id="st-b-store-dumbbell"),
        dcc.Store(id="st-b-store-overrun"),

        dcc.Store(id="st-compare-mode", data=False),
        dcc.Store(id="st-store-kpis"),
        dcc.Store(id="st-store-heatmap"),
        dcc.Store(id="st-b-store-heatmap"),
        dcc.Store(id="st-store-typical"),
        dcc.Store(id="st-b-store-typical"),
        dcc.Store(id="st-store-timeline"),
        # {"dow": int|None, "hour": int|None, "row": UniqueRowID|None}
        dcc.Store(id="st-store-drill", data={"dow": None, "hour": None, "row": None}),
    ],
)


# ---------------------------------------------------------------------------
# Filter sync callbacks (registered per dataset prefix)
# ---------------------------------------------------------------------------

def _register_filter_callbacks(prefix):
    """Date-control sync + milestone preset wiring for one dataset prefix."""

    # A) Preset -> Slider + DatePicker
    @callback(
        Output(_id(prefix, "date-slider"), "value"),
        Output(_id(prefix, "filter-daterange"), "start_date", allow_duplicate=True),
        Output(_id(prefix, "filter-daterange"), "end_date", allow_duplicate=True),
        Input(_id(prefix, "filter-date-preset"), "value"),
        prevent_initial_call=True,
    )
    def _sync_preset(preset):
        if not preset or preset == "custom":
            return (dash.no_update,) * 3
        sv = _clamp_slider(_preset_to_slider_val(preset, _MAX_IDX))
        s, e = _preset_to_exact_dates(preset)
        # Never advertise a start earlier than the extract's floor.
        floor = _idx_to_date(_DATA_FLOOR_IDX).strftime("%Y-%m-%d")
        if s and s < floor:
            s = floor
        return sv, s, e

    # B) Slider -> DatePicker + label (clientside for speed)
    clientside_callback(
        ClientsideFunction(namespace="dateSlider", function_name="syncSlider"),
        Output(_id(prefix, "filter-daterange"), "start_date", allow_duplicate=True),
        Output(_id(prefix, "filter-daterange"), "end_date", allow_duplicate=True),
        Output(_id(prefix, "date-range-label"), "children"),
        Input(_id(prefix, "date-slider"), "value"),
        State(_id(prefix, "filter-daterange"), "start_date"),
        State(_id(prefix, "filter-daterange"), "end_date"),
        prevent_initial_call=True,
    )

    # C) DatePicker -> Slider
    @callback(
        Output(_id(prefix, "date-slider"), "value", allow_duplicate=True),
        Input(_id(prefix, "filter-daterange"), "start_date"),
        Input(_id(prefix, "filter-daterange"), "end_date"),
        State(_id(prefix, "date-slider"), "value"),
        prevent_initial_call=True,
    )
    def _sync_picker_to_slider(start, end, current):
        if not start or not end:
            return dash.no_update
        s, e = pd.Timestamp(start), pd.Timestamp(end)
        new_val = _clamp_slider(
            [_month_idx(s.year, s.month), _month_idx(e.year, e.month)])
        return dash.no_update if new_val == current else new_val

    # D) Slider -> preset becomes "custom" when it no longer matches
    @callback(
        Output(_id(prefix, "filter-date-preset"), "value", allow_duplicate=True),
        Input(_id(prefix, "date-slider"), "value"),
        State(_id(prefix, "filter-date-preset"), "value"),
        prevent_initial_call=True,
    )
    def _maybe_clear_preset(slider_val, current_preset):
        if not current_preset or current_preset == "custom":
            return dash.no_update
        if slider_val == _clamp_slider(_preset_to_slider_val(current_preset, _MAX_IDX)):
            return dash.no_update
        return "custom"

    # E) Era -> date range. "Reliable only" has no data before the clock fix,
    # so a 12-month window would render mostly empty months. Snap forward, and
    # put the previous range back when the user returns to the corrected view.
    # The preset is saved alongside the range: snapping forward flips it to
    # "Custom Range", and without restoring it the round trip would leave the
    # label reading Custom over a range that is once again exactly the preset.
    clientside_callback(
        f"""function(era, current, preset, saved) {{
            var nu = window.dash_clientside.no_update;
            var RF = {_RELIABLE_FLOOR_IDX};
            if (era === "reliable") {{
                if (!current || current[0] >= RF) return [nu, nu, nu];
                return [[RF, Math.max(RF, current[1])], nu,
                        {{range: current, preset: preset}}];
            }}
            if (saved && saved.range) {{
                return [saved.range, saved.preset || nu, null];
            }}
            return [nu, nu, nu];
        }}""",
        Output(_id(prefix, "date-slider"), "value", allow_duplicate=True),
        Output(_id(prefix, "filter-date-preset"), "value", allow_duplicate=True),
        Output(_id(prefix, "era-prev-range"), "data"),
        Input(_id(prefix, "filter-era"), "value"),
        State(_id(prefix, "date-slider"), "value"),
        State(_id(prefix, "filter-date-preset"), "value"),
        State(_id(prefix, "era-prev-range"), "data"),
        prevent_initial_call=True,
    )

    # F) Milestone preset -> milestone chips
    @callback(
        Output(_id(prefix, "filter-milestones"), "value"),
        Input(_id(prefix, "preset-milestones"), "value"),
        prevent_initial_call=True,
    )
    def _apply_milestone_preset(preset):
        return list(PRESETS.get(preset, _DEFAULT_MILESTONES))

    # G) Cross-clock badge visibility
    @callback(
        Output(_id(prefix, "crossclock-badge"), "style"),
        Input(_id(prefix, "filter-milestones"), "value"),
        Input(_id(prefix, "filter-era"), "value"),
    )
    def _crossclock_badge(milestones, era):
        if era == "reliable":
            return {"display": "none"}
        segs = _segments_for(milestones)
        any_cross = any(_is_cross_clock(a, b) for a, b in segs)
        return {} if any_cross else {"display": "none"}

    # H) Physician role toggle -> store
    clientside_callback(
        """function(val) { return val; }""",
        Output(_id(prefix, "physician-role"), "data"),
        Input(_id(prefix, "physician-role-ctrl"), "value"),
    )

    # I) Physician chips, rebuilt from whatever the other filters leave behind
    @callback(
        Output(_id(prefix, "filter-physician"), "children"),
        Input("st-interval", "n_intervals"),
        Input(_id(prefix, "date-slider"), "value"),
        Input(_id(prefix, "filter-department"), "value"),
        Input(_id(prefix, "filter-therapist"), "value"),
        Input(_id(prefix, "filter-simtype"), "value"),
        Input(_id(prefix, "physician-role"), "data"),
        Input(_id(prefix, "scope"), "value"),
        Input(_id(prefix, "inpatient-switch"), "checked"),
    )
    def _populate_physician_chips(_n, slider_val, departments, therapist,
                                  sim_types, role, scope, inpatient):
        data = _load_and_filter(
            slider_val=slider_val, milestones=_DEFAULT_MILESTONES,
            departments=departments, physician=None, physician_role=role,
            therapist=therapist, sim_types=sim_types, body_sites=None,
            diag_mode="primary", scope=scope, inpatient=inpatient,
            era="all", windows=_window_preset("off"), drop_rows=False,
            duration=None, weekend_only=False,
            techniques=None, setup_flags=None, series=None,
        )
        if data is None:
            return []
        col = data["phys_col"]
        df = data["df"]
        if col not in df.columns:
            return []
        return [
            dmc.Chip(physician_short_name(n), value=n, size="xs", variant="filled")
            for n in sorted(df[col].dropna().unique())
        ]

    # --- Trigger labels ---
    clientside_callback(
        """function(val) { return val ? val.split(", ")[0] : "Physician"; }""",
        Output(_id(prefix, "physician-trigger"), "children"),
        Input(_id(prefix, "filter-physician"), "value"),
    )
    clientside_callback(
        """function(v) {
            if (!v || v.length === 0) return "Therapist";
            if (v.length === 1) return v[0].split(", ")[0];
            return v.length + " therapists";
        }""",
        Output(_id(prefix, "therapist-trigger"), "children"),
        Input(_id(prefix, "filter-therapist"), "value"),
    )
    clientside_callback(
        """function(v) {
            if (!v || v.length === 0) return "Type";
            if (v.length === 1) return v[0];
            return v.length + " selected";
        }""",
        Output(_id(prefix, "simtype-trigger"), "children"),
        Input(_id(prefix, "filter-simtype"), "value"),
    )

    clientside_callback(
        """function(v) {
            if (!v || v.length === 0) return "Technique";
            if (v.length === 1) return v[0];
            return v.length + " techniques";
        }""",
        Output(_id(prefix, "technique-trigger"), "children"),
        Input(_id(prefix, "filter-technique"), "value"),
    )
    clientside_callback(
        """function(v) {
            if (!v || v.length === 0) return "Setup";
            if (v.length === 1) return v[0];
            return v.length + " setups";
        }""",
        Output(_id(prefix, "setup-trigger"), "children"),
        Input(_id(prefix, "filter-setup"), "value"),
    )

    # Milestone trigger spells out the resulting chain, in canonical order.
    _ms_labels = {k: lbl for k, lbl, _, _ in MILESTONES}
    _ms_order = {k: i for i, (k, _, _, _) in enumerate(MILESTONES)}
    clientside_callback(
        f"""function(v) {{
            var L = {_ms_labels!r}, O = {_ms_order!r};
            if (!v || v.length < 2) return "Milestones";
            var ks = v.slice().sort(function(a, b) {{ return O[a] - O[b]; }});
            if (ks.length > 3) return ks.length + " milestones";
            return ks.map(function(k) {{ return L[k]; }}).join(" \u2192 ");
        }}""".replace("'", '"'),
        Output(_id(prefix, "milestones-trigger"), "children"),
        Input(_id(prefix, "filter-milestones"), "value"),
    )

    # --- Clear-button visibility ---
    for key, empty_is_list in (("physician", False), ("therapist", True),
                               ("simtype", True), ("technique", True),
                               ("setup", True), ("milestones", True)):
        clientside_callback(
            """function(v) {
                var has = Array.isArray(v) ? v.length > 0 : !!v;
                return has ? {"display": "inline-flex"} : {"display": "none"};
            }""",
            Output(_id(prefix, f"{key}-clear"), "style"),
            Input(_id(prefix, f"filter-{key}"), "value"),
        )

    # --- Clear-button actions ---
    clientside_callback(
        """function(n) { return null; }""",
        Output(_id(prefix, "filter-physician"), "value", allow_duplicate=True),
        Input(_id(prefix, "physician-clear"), "n_clicks"),
        prevent_initial_call=True,
    )
    for key in ("therapist", "simtype", "technique", "setup"):
        clientside_callback(
            """function(n) { return []; }""",
            Output(_id(prefix, f"filter-{key}"), "value", allow_duplicate=True),
            Input(_id(prefix, f"{key}-clear"), "n_clicks"),
            prevent_initial_call=True,
        )
    # Clearing milestones returns to the default preset — the charts need at
    # least two, so an empty selection would just blank the page.
    clientside_callback(
        f"""function(n) {{ return [{", ".join(repr(k) for k in _DEFAULT_MILESTONES)}]; }}""".replace("'", '"'),
        Output(_id(prefix, "filter-milestones"), "value", allow_duplicate=True),
        Input(_id(prefix, "milestones-clear"), "n_clicks"),
        prevent_initial_call=True,
    )

    # --- Duration panel: label + reset ---
    clientside_callback(
        f"""function(v) {{
            if (!v) return "All";
            var lo = v[0], hi = v[1];
            if (lo <= {_DURATION_SLIDER_MIN} && hi >= {_DURATION_SLIDER_MAX}) return "All";
            return lo + "-" + (hi >= {_DURATION_SLIDER_MAX} ? "180+" : hi) + " min";
        }}""",
        Output(_id(prefix, "duration-label"), "children"),
        Input(_id(prefix, "filter-duration"), "value"),
    )
    clientside_callback(
        f"""function(n) {{ return [{_DURATION_SLIDER_MIN}, {_DURATION_SLIDER_MAX}]; }}""",
        Output(_id(prefix, "filter-duration"), "value", allow_duplicate=True),
        Input(_id(prefix, "duration-reset"), "n_clicks"),
        prevent_initial_call=True,
    )
    # Trigger reflects an active duration filter the way the chip triggers do.
    clientside_callback(
        f"""function(v) {{
            if (!v) return "Duration";
            var lo = v[0], hi = v[1];
            if (lo <= {_DURATION_SLIDER_MIN} && hi >= {_DURATION_SLIDER_MAX}) return "Duration";
            return lo + "-" + (hi >= {_DURATION_SLIDER_MAX} ? "180+" : hi) + "m";
        }}""",
        Output(_id(prefix, "duration-trigger"), "children"),
        Input(_id(prefix, "filter-duration"), "value"),
    )

    # --- Outlier windows: presets, per-row labels, trigger summary ---
    _n_win = len(MILESTONE_WINDOWS)
    _presets_js = (
        "var D=" + repr(_window_preset("default")).replace("'", '"') + ";"
        "var S=" + repr(_window_preset("strict")).replace("'", '"') + ";"
        "var O=" + repr(_window_preset("off")).replace("'", '"') + ";"
    )
    clientside_callback(
        f"""function(a, b, c) {{
            {_presets_js}
            var trig = window.dash_clientside.callback_context.triggered;
            if (!trig || !trig.length) return window.dash_clientside.no_update;
            var id = trig[0].prop_id.split(".")[0];
            var vals = id.indexOf("strict") !== -1 ? S
                     : id.indexOf("-off") !== -1 ? O : D;
            return vals;
        }}""",
        [Output(_id(prefix, f"outlier-win-{i}"), "value", allow_duplicate=True)
         for i in range(_n_win)],
        Input(_id(prefix, "outlier-preset-default"), "n_clicks"),
        Input(_id(prefix, "outlier-preset-strict"), "n_clicks"),
        Input(_id(prefix, "outlier-preset-off"), "n_clicks"),
        prevent_initial_call=True,
    )
    for _i, (_k, _lbl, _smin, _smax, _d, _st) in enumerate(MILESTONE_WINDOWS):
        clientside_callback(
            f"""function(v) {{
                if (!v) return "–";
                var lo = v[0] <= {_smin} ? "any" : v[0];
                var hi = v[1] >= {_smax} ? "any" : v[1];
                return lo + " to " + hi;
            }}""",
            Output(_id(prefix, f"outlier-val-{_i}"), "children"),
            Input(_id(prefix, f"outlier-win-{_i}"), "value"),
        )
    clientside_callback(
        f"""function() {{
            {_presets_js}
            var v = Array.prototype.slice.call(arguments, 0, {_n_win});
            var drop = arguments[{_n_win}];
            function eq(a, b) {{
                for (var i = 0; i < a.length; i++) {{
                    if (!a[i] || a[i][0] !== b[i][0] || a[i][1] !== b[i][1]) return false;
                }}
                return true;
            }}
            var name = eq(v, D) ? "Default" : eq(v, S) ? "Strict"
                     : eq(v, O) ? "Off" : "Custom";
            return "Outliers: " + name + (drop ? " (drop)" : "");
        }}""",
        Output(_id(prefix, "outlier-trigger"), "children"),
        *[Input(_id(prefix, f"outlier-win-{i}"), "value") for i in range(_n_win)],
        Input(_id(prefix, "outlier-drop-switch"), "checked"),
    )

    # --- Series panel: label, presets, reset ---
    _series_js = f"""function(v) {{
        if (!v) return "All";
        var lo = v[0], hi = v[1];
        if (lo <= {_SERIES_SLIDER_MIN} && hi >= {_SERIES_SLIDER_MAX}) return "All";
        return lo + "-" + (hi >= {_SERIES_SLIDER_MAX} ? "26+" : hi);
    }}"""
    clientside_callback(
        _series_js,
        Output(_id(prefix, "series-label"), "children"),
        Input(_id(prefix, "filter-series"), "value"),
    )
    clientside_callback(
        f"""function(v) {{
            if (!v) return "Series";
            var lo = v[0], hi = v[1];
            if (lo <= {_SERIES_SLIDER_MIN} && hi >= {_SERIES_SLIDER_MAX}) return "Series";
            if (lo >= 10) return "4D CT";
            if (hi <= 6) return "Conventional";
            return "Series " + lo + "-" + (hi >= {_SERIES_SLIDER_MAX} ? "26+" : hi);
        }}""",
        Output(_id(prefix, "series-trigger"), "children"),
        Input(_id(prefix, "filter-series"), "value"),
    )
    clientside_callback(
        f"""function(a, b, c) {{
            var trig = window.dash_clientside.callback_context.triggered;
            if (!trig || !trig.length) return window.dash_clientside.no_update;
            var id = trig[0].prop_id.split(".")[0];
            if (id.indexOf("preset-conv") !== -1) return [{_SERIES_SLIDER_MIN}, 6];
            if (id.indexOf("preset-4d") !== -1) return [10, {_SERIES_SLIDER_MAX}];
            return [{_SERIES_SLIDER_MIN}, {_SERIES_SLIDER_MAX}];
        }}""",
        Output(_id(prefix, "filter-series"), "value", allow_duplicate=True),
        Input(_id(prefix, "series-preset-conv"), "n_clicks"),
        Input(_id(prefix, "series-preset-4d"), "n_clicks"),
        Input(_id(prefix, "series-reset"), "n_clicks"),
        prevent_initial_call=True,
    )

    register_diagnosis_callbacks(prefix)


_register_filter_callbacks("st")
_register_filter_callbacks("st-b")


# ---------------------------------------------------------------------------
# Compare mode
# ---------------------------------------------------------------------------

@callback(
    Output("st-compare-mode", "data"),
    Input("st-compare-toggle", "n_clicks"),
    State("st-compare-mode", "data"),
    prevent_initial_call=True,
)
def _toggle_compare(n, current):
    return not current


clientside_callback(
    """function(compareMode) {
        if (compareMode) {
            return [{"display": "block", "marginTop": "8px"}, "violet"];
        }
        return [{"display": "none"}, "gray"];
    }""",
    Output("st-b-filter-container", "style"),
    Output("st-compare-toggle", "color"),
    Input("st-compare-mode", "data"),
)

# Hide the "A" badge when compare mode is off — no need to label one dataset.
clientside_callback(
    """function(compareMode) {
        var badges = document.querySelectorAll('.st-dataset-badge-a');
        for (var i = 0; i < badges.length; i++) {
            badges[i].style.display = compareMode ? '' : 'none';
        }
        return window.dash_clientside.no_update;
    }""",
    Output("st-a-filter-container", "className"),
    Input("st-compare-mode", "data"),
)


# ---------------------------------------------------------------------------
# Data loading + filtering
# ---------------------------------------------------------------------------

def _get_date_range(slider_val, first_date, last_date):
    """Resolve a [start_idx, end_idx] slider value into timestamps."""
    if not slider_val or len(slider_val) != 2:
        return first_date, last_date
    start = _idx_to_date(slider_val[0])
    end = _idx_to_date(slider_val[1], end_of_month=True) + pd.Timedelta(days=1)
    return start, end


def _load_and_filter(slider_val, milestones, departments, physician,
                     physician_role, therapist, sim_types, body_sites,
                     diag_mode, scope, inpatient, era, windows=None,
                     drop_rows=False, duration=None, weekend_only=False,
                     techniques=None, setup_flags=None, series=None):
    """Load the timing extract, apply every filter, and compute segment minutes.

    Returns None when there is nothing to chart (no data, or fewer than two
    milestones selected).  Otherwise a dict with the filtered frame, the
    ordered segment definitions, and a per-segment minutes DataFrame.
    """
    if len(_selected_milestones(milestones)) < 2:
        return None

    try:
        from data.loader import load_simulation_timing
        df = load_simulation_timing()
    except Exception:
        return None
    if df is None or df.empty:
        return None
    df = df.copy()

    if "ScheduledStartDateTime" not in df.columns:
        return None
    dates = df["ScheduledStartDateTime"].dropna()
    if dates.empty:
        return None
    start, end = _get_date_range(slider_val, dates.min(), dates.max())
    df = df[(df["ScheduledStartDateTime"] >= start)
            & (df["ScheduledStartDateTime"] < end)]

    if era == "reliable" and "CTClockReliable" in df.columns:
        df = df[df["CTClockReliable"]]

    # Department is the *patient's* (merged from Simulations), not the
    # scanner's — Centralia and Aberdeen patients sim on the Lacey CT_Sim.
    if departments and "Department" in df.columns:
        df = df[df["Department"].isin(departments) | df["Department"].isna()]

    phys_col = _PHYS_COL.get(physician_role or "consult", "ConsultPhysician")
    if physician and phys_col in df.columns:
        df = df[df[phys_col] == physician]

    if therapist and "CompletedByUser" in df.columns:
        df = df[df["CompletedByUser"].isin(therapist)]
    if sim_types and "ActivityName" in df.columns:
        df = df[df["ActivityName"].isin(sim_types)]
    if scope == "initial" and "ActivityName" in df.columns:
        df = df[df["ActivityName"].apply(_is_initial_sim)]
    if inpatient and "InPatientFlag" in df.columns:
        df = df[df["InPatientFlag"].astype(str).str.upper() == "YES"]
    if techniques and "TreatmentTechniques" in df.columns:
        want = set(techniques)
        df = df[df["TreatmentTechniques"].map(
            lambda v: bool(want & {x.strip() for x in str(v).split(",")})
            if pd.notna(v) else False)]
    if setup_flags and "SetupFlags" in df.columns:
        want = set(setup_flags)
        df = df[df["SetupFlags"].map(
            lambda v: bool(want & {x.strip() for x in str(v).split(",")})
            if pd.notna(v) else False)]
    df = _apply_duration_filter(df, duration)
    df = _apply_series_filter(df, series)
    if weekend_only:
        df = df[df["ScheduledStartDateTime"].dt.dayofweek >= 5]

    if body_sites:
        try:
            from data.loader import load_diagnosis
            c2c = build_code_to_category(load_diagnosis())
        except Exception:
            c2c = {}
        if c2c:
            df = filter_by_diagnosis(df, body_sites, c2c,
                                     mode=diag_mode or "primary")

    if df.empty:
        return None

    df = _apply_milestone_windows(
        df, windows, drop_rows=drop_rows,
        selected=[k for k in (milestones or []) if k in _MS_BY_KEY])
    if df.empty:
        return None

    # Order the selection by where each milestone actually lands, not by the
    # nominal MILESTONES order. In this data check-in precedes the booked start
    # (median -10 min) and the note is entered before the appointment is closed
    # out (+37 vs +55), so the nominal order produces backwards segments.
    # Ordering is always on the median, never the mean, so the sequence does not
    # rearrange itself when the aggregate toggle changes.
    base = df["ScheduledStartDateTime"]
    centres = {}
    for key in _selected_milestones(milestones):
        col = _MS_BY_KEY[key][1]
        if col not in df.columns:
            continue
        med = ((df[col] - base).dt.total_seconds() / 60.0).median()
        if pd.notna(med):
            centres[key] = float(med)
    if len(centres) < 2:
        return None
    ordered = sorted(centres, key=lambda k: (centres[k], _MS_ORDER[k]))
    segments = list(zip(ordered, ordered[1:]))

    # Both endpoints of every interval have already been screened by the
    # milestone windows above, so no separate per-segment clamp is applied.
    seg_defs = []
    seg_minutes = pd.DataFrame(index=df.index)
    for a_key, b_key in segments:
        a_col = _MS_BY_KEY[a_key][1]
        b_col = _MS_BY_KEY[b_key][1]
        name = _segment_label(a_key, b_key)
        if a_col not in df.columns or b_col not in df.columns:
            continue
        mins = (df[b_col] - df[a_col]).dt.total_seconds() / 60.0
        seg_minutes[name] = mins
        seg_defs.append({
            "key": f"{a_key}__{b_key}",
            "label": name,
            "cross_clock": _is_cross_clock(a_key, b_key),
        })

    if not seg_defs:
        return None

    return {
        "df": df,
        "segments": seg_defs,
        "seg_minutes": seg_minutes,
        "milestones": ordered,
        "era": era,
        "phys_col": phys_col,
    }


# ---------------------------------------------------------------------------
# Store builders
# ---------------------------------------------------------------------------

def _build_composition(data, agg, period):
    """Minutes per phase, by period, as a genuine composition.

    Each segment is the difference between the two milestones' aggregate
    *positions* relative to the booked start — not the aggregate of the
    per-appointment gaps. The distinction matters: median(A→B) + median(B→C)
    does not equal median(A→C), so summing per-gap medians produced a stack
    whose height was not any real duration (it came to 67 min on a selection
    whose true median span was 60). Differencing positions makes the parts add
    to the whole by construction, so the top of the stack is exactly the
    aggregate span from the first selected milestone to the last.
    """
    df = data["df"]
    ordered = data["milestones"]
    if len(ordered) < 2:
        return None
    period = period if period in ("W", "M", "Y") else "M"
    base = df["ScheduledStartDateTime"]
    buckets = base.dt.to_period(period)
    fn = "mean" if agg == "mean" else "median"
    # "Reliable only" means no CT timestamp was ever corrected, so a
    # cross-clock segment carries no caveat and should not be flagged.
    corrected = data.get("era") != "reliable"

    # Aggregate position of each milestone, per period.
    positions = {}
    for key in ordered:
        col = _MS_BY_KEY[key][1]
        if col not in df.columns:
            continue
        offs = (df[col] - base).dt.total_seconds() / 60.0
        positions[key] = getattr(offs.groupby(buckets), fn)()
    keys = [k for k in ordered if k in positions]
    if len(keys) < 2:
        return None

    counts = buckets.value_counts().sort_index()
    index = counts.index
    if period == "W":
        labels = [p.start_time.strftime("%d %b %y") for p in index]
    else:
        labels = [str(p) for p in index]

    series = []
    for i, (a_key, b_key) in enumerate(zip(keys, keys[1:])):
        vals = (positions[b_key].reindex(index) - positions[a_key].reindex(index))
        series.append({
            "label": _segment_label(a_key, b_key),
            "values": [None if pd.isna(v) else round(float(v), 1) for v in vals],
            "color": CHART_COLORWAY[i % len(CHART_COLORWAY)],
            "crossClock": corrected and _is_cross_clock(a_key, b_key),
        })

    # The span the stack adds up to, stated outright so the total is checkable.
    span = (positions[keys[-1]].reindex(index) - positions[keys[0]].reindex(index))
    return {
        "periods": labels,
        "series": series,
        "counts": [int(c) for c in counts],
        "span": [None if pd.isna(v) else round(float(v), 1) for v in span],
        "spanLabel": f"{_MS_LABEL[keys[0]]} → {_MS_LABEL[keys[-1]]}",
        "agg": fn,
        "period": period,
    }


def _build_density(data, bin_size):
    """Raw first-milestone -> last-milestone minutes for a histogram."""
    ms = data["milestones"]
    if len(ms) < 2:
        return None
    a_key, b_key = ms[0], ms[-1]
    a_col, b_col = _MS_BY_KEY[a_key][1], _MS_BY_KEY[b_key][1]
    df = data["df"]
    if a_col not in df.columns or b_col not in df.columns:
        return None

    mins = (df[b_col] - df[a_col]).dt.total_seconds() / 60.0
    # Apply the same screen the composition uses, scaled to the full span.
    mins = mins.dropna()
    if mins.empty:
        return None

    try:
        bs = int(bin_size)
    except (TypeError, ValueError):
        bs = 10

    return {
        "values": [round(float(v), 2) for v in mins],
        "label": _segment_label(a_key, b_key),
        "binSize": bs,
        "median": round(float(mins.median()), 1),
        "p95": round(float(mins.quantile(0.95)), 1),
        "n": int(mins.size),
        "crossClock": _is_cross_clock(a_key, b_key),
    }


# Categories thinner than this are dropped: a violin off two appointments is
# shape-less and a median off two is noise. The chart says how many it dropped.
_BOOKED_MIN_N = 5


def _build_dumbbell(data, group_col):
    """Booked slot length against the actual occupied span, per category.

    The "actual" span follows the milestone picker — it is the same
    earliest-to-latest interval the distribution chart histograms — so this
    chart answers "how long did we hold the room for what we booked" in
    whatever terms the rest of the page is currently expressed in.

    Raw per-appointment values are returned alongside the medians so the client
    can draw either a violin or a dumbbell from the same payload.
    """
    df = data["df"]
    ordered = data["milestones"]
    if len(ordered) < 2 or "ScheduledDurationMinutes" not in df.columns:
        return None
    if group_col not in df.columns:
        group_col = "ActivityName"
    if group_col not in df.columns:
        return None

    a_col = _MS_BY_KEY[ordered[0]][1]
    b_col = _MS_BY_KEY[ordered[-1]][1]
    if a_col not in df.columns or b_col not in df.columns:
        return None

    work = pd.DataFrame({
        "grp": df[group_col],
        "booked": pd.to_numeric(df["ScheduledDurationMinutes"], errors="coerce"),
        # Endpoints are already screened by the milestone plausibility windows.
        "actual": (df[b_col] - df[a_col]).dt.total_seconds() / 60.0,
    }).dropna(subset=["grp", "actual"])
    if work.empty:
        return None

    rows, dropped = [], 0
    for name, g in work.groupby("grp"):
        if len(g) < _BOOKED_MIN_N:
            dropped += 1
            continue
        vals = g["actual"].tolist()
        rows.append({
            "category": str(name),
            "booked": (None if g["booked"].dropna().empty
                       else round(float(g["booked"].median()), 1)),
            "actual": round(float(g["actual"].median()), 1),
            "p25": round(float(g["actual"].quantile(0.25)), 1),
            "p75": round(float(g["actual"].quantile(0.75)), 1),
            "n": int(len(g)),
            "values": [round(float(v), 1) for v in vals],
        })
    if not rows:
        return None
    rows.sort(key=lambda r: r["actual"])

    return {
        "rows": rows,
        "spanLabel": _segment_label(ordered[0], ordered[-1]),
        "crossClock": (data.get("era") != "reliable"
                       and _is_cross_clock(ordered[0], ordered[-1])),
        "droppedCategories": dropped,
        "minN": _BOOKED_MIN_N,
        "groupLabel": {"ActivityName": "Sim Type",
                       "CompletedByUser": "Therapist",
                       "ConsultPhysician": "MD",
                       "SimTechnique": "Technique"}.get(group_col, group_col),
    }


def _build_overrun(data, definition):
    """Share of sims running past the booked end, overall and by month."""
    df = data["df"]
    if "ScheduledEndDateTime" not in df.columns:
        return None

    if definition == "ct":
        end_col = "CTCompletedDateTime"
        label = "CT complete past booked end"
        cross = True
    elif definition == "appt":
        end_col = "ActualEndDateTime"
        label = "Appointment end past booked end"
        cross = False
    else:
        end_col = "FirstNoteEnteredDateTime"
        label = "Documented after booked end"
        cross = False
    if end_col not in df.columns:
        return None

    over_min = (df[end_col] - df["ScheduledEndDateTime"]).dt.total_seconds() / 60.0
    valid = over_min.notna()
    if not valid.any():
        return None
    is_over = (over_min > 0) & valid

    buckets = df["ScheduledStartDateTime"].dt.to_period("M")
    grp = pd.DataFrame({"over": is_over, "valid": valid, "p": buckets})
    grp = grp[grp["valid"]]
    agg = grp.groupby("p").agg(over=("over", "sum"), n=("valid", "size")).sort_index()
    agg["rate"] = 100.0 * agg["over"] / agg["n"]

    # Median minutes over, among the sims that actually ran over.
    over_only = over_min[is_over]

    return {
        "periods": [str(p) for p in agg.index],
        "rate": [round(float(v), 1) for v in agg["rate"]],
        "counts": [int(v) for v in agg["n"]],
        "over": [int(v) for v in agg["over"]],
        "overall": round(float(100.0 * is_over.sum() / valid.sum()), 1),
        "totalN": int(valid.sum()),
        "totalOver": int(is_over.sum()),
        "medianOverMinutes": (round(float(over_only.median()), 1)
                              if not over_only.empty else None),
        "label": label,
        "crossClock": cross,
    }


def _kpi_series(df, a_key, b_key):
    """Minutes between two milestones, as a plain float Series."""
    a_col, b_col = _MS_BY_KEY[a_key][1], _MS_BY_KEY[b_key][1]
    if a_col not in df.columns or b_col not in df.columns:
        return pd.Series(dtype=float)
    return (df[b_col] - df[a_col]).dt.total_seconds() / 60.0


def _build_kpis(data):
    """Five headline numbers, each with a 12-point monthly sparkline.

    Every metric here is ARIA-side on both ends except the documentation lag,
    which is flagged, so the KPI row stays honest under "All (corrected)".
    """
    df = data["df"]
    months = df["ScheduledStartDateTime"].dt.to_period("M")

    def spark(series, how="median"):
        s = series.dropna()
        if s.empty:
            return [], []
        g = s.groupby(months.reindex(s.index))
        agg = getattr(g, how)().sort_index()
        return ([round(float(v), 1) for v in agg],
                [str(p) for p in agg.index])

    # Endpoints are already screened by the milestone plausibility windows.
    #
    # The visit is anchored on the booked start and closed on documentation
    # rather than on check-in and close-out: both ends are ARIA-side, so the
    # headline number is clock-immune, and it splits exactly into the two
    # KPIs beside it (booked start -> CT complete, then CT complete -> note).
    visit = _kpi_series(df, "sched_start", "note")
    to_ct = _kpi_series(df, "sched_start", "ct_done")
    doc = _kpi_series(df, "ct_done", "note")

    # Overrun is measured on documentation, not on the manual close-out: an
    # appointment marked complete is a clerical act, whereas the note stamp is
    # when the work was actually finished.
    over_min = _kpi_series(df, "sched_end", "note")
    valid = over_min.notna()
    is_over = (over_min > 0) & valid
    over_rate = (100.0 * is_over.sum() / valid.sum()) if valid.any() else None
    over_by_month = (
        pd.DataFrame({"o": is_over[valid], "m": months[valid]})
        .groupby("m")["o"].mean().mul(100).round(1).sort_index()
    ) if valid.any() else pd.Series(dtype=float)

    v_vals, v_lbl = spark(visit)
    ct_vals, ct_lbl = spark(to_ct)
    doc_vals, doc_lbl = spark(doc)

    return {
        "n": int(len(df)),
        "n_spark": [int(v) for v in months.value_counts().sort_index()],
        "n_spark_labels": [str(p) for p in months.value_counts().sort_index().index],
        "visit_median": None if visit.dropna().empty else round(float(visit.median()), 0),
        "visit_spark": v_vals, "visit_labels": v_lbl,
        "to_ct_median": None if to_ct.dropna().empty else round(float(to_ct.median()), 0),
        "to_ct_spark": ct_vals, "to_ct_labels": ct_lbl,
        "overrun_rate": None if over_rate is None else round(float(over_rate), 1),
        "overrun_spark": [float(v) for v in over_by_month],
        "overrun_labels": [str(p) for p in over_by_month.index],
        "doc_median": None if doc.dropna().empty else round(float(doc.median()), 0),
        "doc_spark": doc_vals, "doc_labels": doc_lbl,
        "reliable_share": (round(100.0 * float(df["CTClockReliable"].mean()), 0)
                           if "CTClockReliable" in df.columns and len(df) else None),
    }


# Weekday labels for the heatmap, Monday-first.
_WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

# Minimum appointments before a heatmap cell gets a rate colour.
_HEATMAP_MIN_N = 3


def _build_heatmap(data, metric):
    """Weekday x hour-of-day grid, by booked start time.

    Both endpoints of the overrun metric are ARIA-side, so this is valid across
    all history regardless of clock era.
    """
    df = data["df"]
    if df.empty:
        return None
    start = df["ScheduledStartDateTime"]
    hour = start.dt.hour
    dow = start.dt.dayofweek

    # Same overrun definition the KPI and the Overrun chart use.
    over_min = _kpi_series(df, "sched_end", "note")
    visit = _kpi_series(df, "sched_start", "note")

    work = pd.DataFrame({
        "dow": dow, "hour": hour,
        "over": (over_min > 0) & over_min.notna(),
        "over_valid": over_min.notna(),
        "over_min": over_min,
        "visit": visit,
    })

    hours = sorted(work["hour"].dropna().unique().tolist())
    if not hours:
        return None
    days = sorted(work["dow"].dropna().unique().tolist())

    z, counts, detail = [], [], []
    for d in days:
        row_z, row_n, row_d = [], [], []
        for h in hours:
            cell = work[(work["dow"] == d) & (work["hour"] == h)]
            n = int(len(cell))
            if n == 0:
                row_z.append(None); row_n.append(0); row_d.append(None); continue
            if metric == "volume":
                val = float(n)
            elif n < _HEATMAP_MIN_N:
                # A rate off one or two appointments is noise that would own the
                # colour scale (a single overrun reads as 100%). Keep the count
                # in the tooltip but leave the cell uncoloured.
                val = None
            elif metric == "visit":
                val = cell["visit"].median()
            else:
                v = cell["over_valid"].sum()
                val = (100.0 * cell["over"].sum() / v) if v else None
            row_z.append(None if val is None or pd.isna(val) else round(float(val), 1))
            row_n.append(n)
            med_over = cell.loc[cell["over"], "over_min"].median()
            row_d.append(None if pd.isna(med_over) else round(float(med_over), 0))
        z.append(row_z); counts.append(row_n); detail.append(row_d)

    label = {"visit": "Median visit (min)", "volume": "Sims"}.get(
        metric, "% past booked end")
    return {
        "z": z, "counts": counts, "detail": detail,
        "minN": _HEATMAP_MIN_N,
        "days": [_WEEKDAYS[d] for d in days],
        "dayIdx": [int(d) for d in days],
        "hours": [int(h) for h in hours],
        "hourLabels": [f"{h % 12 or 12}{'a' if h < 12 else 'p'}" for h in hours],
        "metric": metric or "overrun",
        "label": label,
    }


def _appointment_records(data, drill=None):
    """Flat per-appointment records for the detail table and the drill-down."""
    df = data["df"]
    if drill and drill.get("dow") is not None and drill.get("hour") is not None:
        start = df["ScheduledStartDateTime"]
        df = df[(start.dt.dayofweek == drill["dow"]) & (start.dt.hour == drill["hour"])]
    if df.empty:
        return []

    out = pd.DataFrame({
        "UniqueRowID": df["UniqueRowID"],
        "Date": df["ScheduledStartDateTime"].dt.strftime("%Y-%m-%d"),
        "Booked": df["ScheduledStartDateTime"].dt.strftime("%H:%M"),
        "Department": df.get("Department"),
        "ActivityName": df.get("ActivityName"),
        "Physician": df.get("ConsultPhysician"),
        "Therapist": df.get("CompletedByUser"),
        "Technique": df.get("SimTechnique"),
        "Setup": df.get("SetupFlags"),
        "BookedMin": pd.to_numeric(df.get("ScheduledDurationMinutes"), errors="coerce"),
        "StartDelayMin": pd.to_numeric(df.get("StartDelayMinutes"), errors="coerce"),
        "VisitMin": _kpi_series(df, "checkin", "appt_end").round(0),
        "ScanSpanMin": pd.to_numeric(df.get("CTScanSpanMinutes"), errors="coerce"),
        "DocLagMin": _kpi_series(df, "ct_done", "note").round(0),
        "OverrunMin": _kpi_series(df, "sched_end", "appt_end").round(0),
        "SeriesCount": pd.to_numeric(df.get("SeriesCount"), errors="coerce"),
        "ClockEra": np.where(df.get("CTClockReliable", False), "Reliable", "Corrected"),
    })
    if "PatientFullName" in df.columns:
        out["Patient"] = df["PatientFullName"]
    out = out.sort_values("Date", ascending=False)
    return out.to_dict("records")


def _build_typical(data, center, spread):
    """The 'typical sim': one lane per milestone, centre plus a spread band.

    Aggregates the same offsets the cohort strip draws individually, so the two
    read on the same axis — minutes from the appointment's own booked start.
    """
    df = data["df"]
    if df.empty or "ScheduledStartDateTime" not in df.columns:
        return None
    base = df["ScheduledStartDateTime"]
    use_mean = center == "mean"

    out = []
    for key, lbl, col, clock in MILESTONES:
        if col not in df.columns:
            continue
        # Already screened by the milestone plausibility windows.
        offs = ((df[col] - base).dt.total_seconds() / 60.0).dropna()
        if offs.empty:
            continue
        ctr = float(offs.mean() if use_mean else offs.median())
        if spread == "sd":
            sd = float(offs.std(ddof=1)) if offs.size > 1 else 0.0
            lo, hi = ctr - sd, ctr + sd
        elif spread == "p10_90":
            lo, hi = float(offs.quantile(0.10)), float(offs.quantile(0.90))
        else:
            lo, hi = float(offs.quantile(0.25)), float(offs.quantile(0.75))
        out.append({
            "key": key, "label": lbl, "clock": clock,
            "center": round(ctr, 1),
            "lo": round(lo, 1), "hi": round(hi, 1),
            "p10": round(float(offs.quantile(0.10)), 1),
            "p90": round(float(offs.quantile(0.90)), 1),
            "n": int(offs.size),
        })
    if not out:
        return None

    booked = pd.to_numeric(df.get("ScheduledDurationMinutes"), errors="coerce").dropna()
    reliable = (float(df["CTClockReliable"].mean())
                if "CTClockReliable" in df.columns and len(df) else 0.0)
    return {
        "milestones": out,
        "bookedLen": None if booked.empty else float(booked.median()),
        "n": int(len(df)),
        "center": "mean" if use_mean else "median",
        "spread": spread or "iqr",
        "spreadLabel": {"sd": "±1 SD", "p10_90": "P10–90"}.get(spread, "IQR"),
        "reliableShare": round(100.0 * reliable, 0),
    }


# At most this many appointments are drawn in the cohort strip. The subtitle
# always reports when the cap bit, so a truncated view never reads as complete.
_COHORT_LANE_CAP = 25


def _milestone_marks(row, base):
    """Milestones for one appointment, in minutes from its booked start."""
    marks = []
    for key, lbl, col, clock in MILESTONES:
        if col not in row or pd.isna(row[col]):
            continue
        marks.append({
            "key": key, "label": lbl,
            "at": round((row[col] - base).total_seconds() / 60.0, 1),
            "clock": clock,
        })
    return marks


def _build_timeline(data, drill):
    """Level-2 cohort strip, or the level-3 single-appointment timeline.

    With a heatmap cell selected we draw one lane per appointment in that
    weekday/hour, so the cell click has its own visual. Selecting a table row
    then drops to that single appointment in full detail.
    """
    drill = drill or {}
    df = data["df"]

    # ---- Level 3: one appointment -----------------------------------------
    row_id = drill.get("row")
    if row_id is not None:
        match = df[df["UniqueRowID"] == row_id]
        if match.empty:
            return None
        r = match.iloc[0]
        base = r["ScheduledStartDateTime"]
        if pd.isna(base):
            return None
        booked_len = pd.to_numeric(pd.Series([r.get("ScheduledDurationMinutes")]),
                                   errors="coerce").iloc[0]
        return {
            "mode": "single",
            "id": int(row_id),
            "date": base.strftime("%a %d %b %Y"),
            "bookedStart": base.strftime("%H:%M"),
            "bookedLen": None if pd.isna(booked_len) else float(booked_len),
            "marks": _milestone_marks(r, base),
            "reliable": bool(r.get("CTClockReliable", False)),
            "clockOffset": (int(r["CTClockOffsetMinutes"])
                            if "CTClockOffsetMinutes" in match.columns
                            and not pd.isna(r["CTClockOffsetMinutes"]) else 0),
            "activity": str(r.get("ActivityName") or "–"),
            "therapist": str(r.get("CompletedByUser") or "–"),
            "physician": str(r.get("ConsultPhysician") or "–"),
            "department": str(r.get("Department") or "–"),
            "seriesCount": (int(r["SeriesCount"])
                            if "SeriesCount" in match.columns
                            and not pd.isna(r["SeriesCount"]) else None),
        }

    # ---- Level 2: every appointment in the selected cell -------------------
    if drill.get("dow") is None or drill.get("hour") is None:
        return None
    start = df["ScheduledStartDateTime"]
    cell = df[(start.dt.dayofweek == drill["dow"]) & (start.dt.hour == drill["hour"])]
    if cell.empty:
        return None
    total = int(len(cell))
    cell = cell.sort_values("ScheduledStartDateTime", ascending=False).head(_COHORT_LANE_CAP)

    lanes = []
    for _, r in cell.iterrows():
        base = r["ScheduledStartDateTime"]
        if pd.isna(base):
            continue
        booked_len = pd.to_numeric(pd.Series([r.get("ScheduledDurationMinutes")]),
                                   errors="coerce").iloc[0]
        lanes.append({
            "id": int(r["UniqueRowID"]),
            "label": base.strftime("%d %b %H:%M"),
            "bookedLen": None if pd.isna(booked_len) else float(booked_len),
            "marks": _milestone_marks(r, base),
            "reliable": bool(r.get("CTClockReliable", False)),
            "therapist": str(r.get("CompletedByUser") or "–"),
        })
    if not lanes:
        return None

    hr = int(drill["hour"])
    return {
        "mode": "cohort",
        "lanes": lanes,
        "shown": len(lanes),
        "total": total,
        "cell": f"{_WEEKDAYS[int(drill['dow'])]} {hr % 12 or 12} {'AM' if hr < 12 else 'PM'}",
    }


# ---------------------------------------------------------------------------
# Filter inputs
# ---------------------------------------------------------------------------

def _filter_inputs(prefix, include_compare=False):
    base = []
    if include_compare:
        base.append(Input("st-compare-mode", "data"))
    base += [
        Input("st-interval", "n_intervals"),
        Input(_id(prefix, "date-slider"), "value"),
        Input(_id(prefix, "filter-milestones"), "value"),
        Input(_id(prefix, "filter-department"), "value"),
        Input(_id(prefix, "filter-physician"), "value"),
        Input(_id(prefix, "physician-role"), "data"),
        Input(_id(prefix, "filter-therapist"), "value"),
        Input(_id(prefix, "filter-simtype"), "value"),
        Input(_id(prefix, "filter-technique"), "value"),
        Input(_id(prefix, "filter-setup"), "value"),
        Input(_id(prefix, "diag-store"), "data"),
        Input(_id(prefix, "diag-mode"), "data"),
        Input(_id(prefix, "scope"), "value"),
        Input(_id(prefix, "inpatient-switch"), "checked"),
        Input(_id(prefix, "weekend-switch"), "checked"),
        Input(_id(prefix, "filter-duration"), "value"),
        Input(_id(prefix, "filter-series"), "value"),
        Input(_id(prefix, "filter-era"), "value"),
        Input(_id(prefix, "outlier-drop-switch"), "checked"),
    ] + [
        Input(_id(prefix, f"outlier-win-{i}"), "value")
        for i in range(len(MILESTONE_WINDOWS))
    ]
    return base


# Scalar filter args, then one range slider per screened milestone. Asserted
# against the built input list below so the two can never drift apart.
_N_SCALAR = 19
_N_SHARED = _N_SCALAR + len(MILESTONE_WINDOWS)


_A_INPUTS = _filter_inputs("st")
_B_INPUTS = _filter_inputs("st-b", include_compare=True)
_N_A = len(_A_INPUTS)
_N_B = len(_B_INPUTS)
assert _N_A == _N_SHARED, (
    f"filter input count ({_N_A}) does not match _unpack's expectation "
    f"({_N_SHARED}); update _N_SCALAR when adding or removing a filter")
def _unpack(args, compare=False):
    offset = 1 if compare else 0
    (_n, slider_val, milestones, departments, physician, physician_role,
     therapist, sim_types, techniques, setup_flags, body_sites, diag_mode,
     scope, inpatient, weekend_only, duration, series,
     era, drop_rows) = args[offset:offset + _N_SCALAR]
    windows = list(args[offset + _N_SCALAR:offset + _N_SHARED])
    return dict(
        slider_val=slider_val, milestones=milestones, departments=departments,
        physician=physician, physician_role=physician_role,
        therapist=therapist, sim_types=sim_types, techniques=techniques,
        setup_flags=setup_flags, body_sites=body_sites,
        diag_mode=diag_mode, scope=scope, inpatient=inpatient,
        weekend_only=weekend_only, duration=duration, series=series,
        era=era, windows=windows, drop_rows=drop_rows,
    )


# ---------------------------------------------------------------------------
# Server callbacks — Dataset A
# ---------------------------------------------------------------------------

@callback(
    Output("st-store-composition", "data"),
    *_A_INPUTS,
    Input("st-composition-agg", "value"),
    Input("st-composition-period", "value"),
    running=[(Output("st-chart-composition-loading", "visible"), True, False)],
)
def _update_composition(*args):
    data = _load_and_filter(**_unpack(args))
    if data is None:
        return None
    return _build_composition(data, args[_N_A], args[_N_A + 1])


@callback(
    Output("st-store-density", "data"),
    *_A_INPUTS,
    Input("st-density-bins", "value"),
    running=[(Output("st-chart-density-loading", "visible"), True, False)],
)
def _update_density(*args):
    data = _load_and_filter(**_unpack(args))
    if data is None:
        return None
    return _build_density(data, args[_N_A])


@callback(
    Output("st-store-dumbbell", "data"),
    *_A_INPUTS,
    Input("st-dumbbell-group", "value"),
    running=[(Output("st-chart-dumbbell-loading", "visible"), True, False)],
)
def _update_dumbbell(*args):
    data = _load_and_filter(**_unpack(args))
    if data is None:
        return None
    return _build_dumbbell(data, args[_N_A])


@callback(
    Output("st-store-overrun", "data"),
    *_A_INPUTS,
    Input("st-overrun-def", "value"),
    running=[(Output("st-chart-overrun-loading", "visible"), True, False)],
)
def _update_overrun(*args):
    data = _load_and_filter(**_unpack(args))
    if data is None:
        return None
    return _build_overrun(data, args[_N_A])


# ---------------------------------------------------------------------------
# Server callbacks — Dataset B (only compute when compare mode is on)
# ---------------------------------------------------------------------------

@callback(
    Output("st-b-store-composition", "data"),
    *_B_INPUTS,
    Input("st-composition-agg", "value"),
    Input("st-composition-period", "value"),
)
def _update_b_composition(*args):
    if not args[0]:
        return None
    data = _load_and_filter(**_unpack(args, compare=True))
    if data is None:
        return None
    return _build_composition(data, args[_N_B], args[_N_B + 1])


@callback(
    Output("st-b-store-density", "data"),
    *_B_INPUTS,
    Input("st-density-bins", "value"),
)
def _update_b_density(*args):
    if not args[0]:
        return None
    data = _load_and_filter(**_unpack(args, compare=True))
    if data is None:
        return None
    return _build_density(data, args[_N_B])


@callback(
    Output("st-b-store-dumbbell", "data"),
    *_B_INPUTS,
    Input("st-dumbbell-group", "value"),
)
def _update_b_dumbbell(*args):
    if not args[0]:
        return None
    data = _load_and_filter(**_unpack(args, compare=True))
    if data is None:
        return None
    return _build_dumbbell(data, args[_N_B])


@callback(
    Output("st-b-store-overrun", "data"),
    *_B_INPUTS,
    Input("st-overrun-def", "value"),
)
def _update_b_overrun(*args):
    if not args[0]:
        return None
    data = _load_and_filter(**_unpack(args, compare=True))
    if data is None:
        return None
    return _build_overrun(data, args[_N_B])


# ---------------------------------------------------------------------------
# KPI row, heatmap, drill-down and detail table (Dataset A only)
# ---------------------------------------------------------------------------

def _fmt_min(v, suffix=" min"):
    return "–" if v is None else f"{v:,.0f}{suffix}"


@callback(
    Output("st-kpi-row", "children"),
    *_A_INPUTS,
)
def _update_kpis(*args):
    data = _load_and_filter(**_unpack(args))
    if data is None:
        return [dmc.GridCol(kpi_placeholder(), span={"base": 12, "sm": 6, "md": 2.4})
                for _ in range(5)]
    k = _build_kpis(data)

    cards = [
        kpi_card(
            "Sims Timed", f"{k['n']:,}",
            value_detail="with matched CT",
            sparkline_past=k["n_spark"], sparkline_past_labels=k["n_spark_labels"],
            accent_color=PRIMARY,
        ),
        kpi_card(
            "Median Visit", _fmt_min(k["visit_median"]),
            value_detail="booked start → documented",
            sparkline_past=k["visit_spark"], sparkline_past_labels=k["visit_labels"],
            accent_color="#2196F3",
        ),
        kpi_card(
            "Past Booked End",
            "–" if k["overrun_rate"] is None else f"{k['overrun_rate']:.1f}%",
            value_detail="documented after booked end",
            sparkline_past=k["overrun_spark"], sparkline_past_labels=k["overrun_labels"],
            accent_color="#F44336",
        ),
        kpi_card(
            "Median to CT Complete", _fmt_min(k["to_ct_median"]),
            value_detail="booked start → CT done",
            sparkline_past=k["to_ct_spark"], sparkline_past_labels=k["to_ct_labels"],
            accent_color="#FF9800",
        ),
        kpi_card(
            "Median Doc Lag", _fmt_min(k["doc_median"]),
            value_detail="CT done → note entered",
            sparkline_past=k["doc_spark"], sparkline_past_labels=k["doc_labels"],
            accent_color="#4CAF50",
        ),
    ]
    return [dmc.GridCol(c, span={"base": 12, "sm": 6, "md": 2.4}) for c in cards]


@callback(
    Output("st-store-heatmap", "data"),
    *_A_INPUTS,
    Input("st-heatmap-metric", "value"),
    running=[(Output("st-heatmap-loading", "visible"), True, False)],
)
def _update_heatmap(*args):
    data = _load_and_filter(**_unpack(args))
    if data is None:
        return None
    return _build_heatmap(data, args[_N_A])


@callback(
    Output("st-store-typical", "data"),
    *_A_INPUTS,
    Input("st-typical-center", "value"),
    Input("st-typical-spread", "value"),
    running=[(Output("st-typical-loading", "visible"), True, False)],
)
def _update_typical(*args):
    data = _load_and_filter(**_unpack(args))
    if data is None:
        return None
    return _build_typical(data, args[_N_A], args[_N_A + 1])


@callback(
    Output("st-b-store-typical", "data"),
    *_B_INPUTS,
    Input("st-typical-center", "value"),
    Input("st-typical-spread", "value"),
)
def _update_b_typical(*args):
    if not args[0]:
        return None
    data = _load_and_filter(**_unpack(args, compare=True))
    if data is None:
        return None
    return _build_typical(data, args[_N_B], args[_N_B + 1])


@callback(
    Output("st-b-store-heatmap", "data"),
    *_B_INPUTS,
    Input("st-heatmap-metric", "value"),
)
def _update_b_heatmap(*args):
    if not args[0]:
        return None
    data = _load_and_filter(**_unpack(args, compare=True))
    if data is None:
        return None
    return _build_heatmap(data, args[_N_B])


# --- Drill-down state -------------------------------------------------------

# Heatmap cell clicks write st-store-drill directly from JS via set_props (see
# assets/sim_timing.js). dcc.Graph.clickData is deliberately NOT wired: Plotly
# emits plotly_click on this graph, but Dash never propagates the clickData
# prop for it, so a callback on it never fires. set_props is the pattern the
# Workflow flow-Gantt already uses for chart clicks.
@callback(
    Output("st-store-drill", "data"),
    Input("st-detail-grid", "selectedRows"),
    Input("st-drill-clear", "n_clicks"),
    State("st-store-drill", "data"),
    prevent_initial_call=True,
)
def _update_drill(selected_rows, _clear, current):
    trigger = ctx.triggered_id
    current = current or {"dow": None, "hour": None, "row": None}

    if trigger == "st-drill-clear":
        return {"dow": None, "hour": None, "row": None}

    if trigger == "st-detail-grid" and selected_rows:
        return {**current, "row": selected_rows[0].get("UniqueRowID")}

    return dash.no_update


# Mirror the drill store back into the JS cell-toggle memory.
clientside_callback(
    ClientsideFunction(namespace="simTiming", function_name="syncDrill"),
    Output("st-breadcrumb", "title"),
    Input("st-store-drill", "data"),
)


@callback(
    Output("st-detail-grid", "rowData"),
    Output("st-detail-grid", "columnDefs"),
    *_A_INPUTS,
    Input("st-store-drill", "data"),
)
def _update_table(*args):
    drill = args[_N_A]
    data = _load_and_filter(**_unpack(args))
    if data is None:
        return [], []
    records = _appointment_records(data, drill)

    num = {"type": "numericColumn", "width": 110}
    cols = [
        {"field": "Date", "width": 110, "pinned": "left"},
        {"field": "Booked", "headerName": "Start", "width": 90},
        {"field": "Patient", "headerName": "Patient", "width": 170},
        {"field": "Department", "width": 110},
        {"field": "ActivityName", "headerName": "Sim Type", "width": 190},
        {"field": "Physician", "headerName": "MD", "width": 150},
        {"field": "Therapist", "width": 150},
        {"field": "Technique", "width": 110},
        {"field": "Setup", "width": 170},
        {"field": "BookedMin", "headerName": "Booked (min)", **num},
        {"field": "StartDelayMin", "headerName": "Start Delay", **num},
        {"field": "VisitMin", "headerName": "Visit (min)", **num},
        {"field": "ScanSpanMin", "headerName": "Scan Span", **num},
        {"field": "DocLagMin", "headerName": "Doc Lag", **num},
        {"field": "OverrunMin", "headerName": "Overrun (min)", **num},
        {"field": "SeriesCount", "headerName": "Series", **num},
        {"field": "ClockEra", "headerName": "CT Clock", "width": 110},
    ]
    if records and "Patient" not in records[0]:
        cols = [c for c in cols if c["field"] != "Patient"]
    return records, apply_phi_grid_rules(cols)


@callback(
    Output("st-store-timeline", "data"),
    *_A_INPUTS,
    Input("st-store-drill", "data"),
)
def _update_timeline(*args):
    drill = args[_N_A] or {}
    if drill.get("row") is None and drill.get("dow") is None:
        return None
    data = _load_and_filter(**_unpack(args))
    if data is None:
        return None
    return _build_timeline(data, drill)


# Breadcrumb + drill affordances
clientside_callback(
    """function(drill, tl) {
        var DAYS = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"];
        drill = drill || {};
        var parts = ["All appointments"];
        if (drill.dow !== null && drill.dow !== undefined) {
            var h = drill.hour;
            var hl = (h % 12 || 12) + (h < 12 ? " AM" : " PM");
            parts.push(DAYS[drill.dow] + " " + hl);
        }
        if (tl && tl.mode === "single") parts.push(tl.date + " " + tl.bookedStart);
        var hasSel = parts.length > 1;
        var h = (tl && tl.mode === "cohort")
            ? Math.min(560, Math.max(220, 26 * tl.lanes.length + 70)) + "px"
            : "210px";
        return [
            parts.join("  ›  "),
            hasSel ? {} : {"display": "none"},
            tl ? {} : {"display": "none"},
            {"height": h}
        ];
    }""",
    Output("st-breadcrumb", "children"),
    Output("st-drill-clear", "style"),
    Output("st-timeline-card", "style"),
    Output("st-timeline-box", "style"),
    Input("st-store-drill", "data"),
    Input("st-store-timeline", "data"),
)

# Drilling into a heatmap cell opens the detail table, so the next step of the
# drill-down is visible without hunting for it.
clientside_callback(
    """function(drill, current) {
        if (drill && drill.dow !== null && drill.dow !== undefined) return "detail";
        return current;
    }""",
    Output("st-detail-accordion", "value"),
    Input("st-store-drill", "data"),
    State("st-detail-accordion", "value"),
)

# Timeline header: clock-era badge + one-line context
clientside_callback(
    """function(tl) {
        if (!tl) return ["Appointment Timeline", "", "gray", ""];
        if (tl.mode === "cohort") {
            var note = tl.shown < tl.total
                ? ("showing the " + tl.shown + " most recent of " + tl.total)
                : (tl.total + " appointments");
            return ["Appointments in " + tl.cell, "", "gray",
                    note + "  ·  click a table row for one appointment"];
        }
        var label = tl.reliable ? "Reliable CT clock"
                                : "CT corrected +" + tl.clockOffset + " min";
        var meta = [tl.activity, tl.department, "MD " + tl.physician,
                    "Therapist " + tl.therapist];
        if (tl.seriesCount !== null) meta.push(tl.seriesCount + " series");
        return ["Appointment Timeline", label, tl.reliable ? "green" : "orange",
                meta.join("  ·  ")];
    }""",
    Output("st-timeline-title", "children"),
    Output("st-timeline-era", "children"),
    Output("st-timeline-era", "color"),
    Output("st-timeline-meta", "children"),
    Input("st-store-timeline", "data"),
)


# ---------------------------------------------------------------------------
# Clientside renderers
# ---------------------------------------------------------------------------

# Panel toggle + PNG export for every chart_card-based chart.
register_chart_callbacks([
    {"sid": "st-composition", "gid": "st-chart-composition", "show_smooth": False},
    {"sid": "st-density", "gid": "st-chart-density",
     "show_smooth": False, "show_grouping": False},
    {"sid": "st-dumbbell", "gid": "st-chart-dumbbell",
     "show_smooth": False, "show_grouping": False},
    {"sid": "st-overrun", "gid": "st-chart-overrun",
     "show_smooth": True, "show_grouping": False},
])

# Composition is registered on its own because it also takes the gear's
# Stacked/Grouped toggle.
clientside_callback(
    ClientsideFunction(namespace="simTiming", function_name="renderComposition"),
    Output("st-chart-composition", "figure"),
    Input("st-store-composition", "data"),
    Input("st-b-store-composition", "data"),
    Input("st-compare-mode", "data"),
    Input("st-composition-settings-stack", "value"),
)

clientside_callback(
    ClientsideFunction(namespace="simTiming", function_name="renderDumbbell"),
    Output("st-chart-dumbbell", "figure"),
    Input("st-store-dumbbell", "data"),
    Input("st-b-store-dumbbell", "data"),
    Input("st-compare-mode", "data"),
    Input("st-dumbbell-settings-type", "value"),
)

clientside_callback(
    ClientsideFunction(namespace="simTiming", function_name="renderOverrun"),
    Output("st-chart-overrun", "figure"),
    Input("st-store-overrun", "data"),
    Input("st-b-store-overrun", "data"),
    Input("st-compare-mode", "data"),
    Input("st-overrun-settings-smooth", "value"),
)

# The heatmap also takes the drill state, so it can outline the selected cell.
clientside_callback(
    ClientsideFunction(namespace="simTiming", function_name="renderHeatmap"),
    Output("st-chart-heatmap", "figure"),
    Input("st-store-heatmap", "data"),
    Input("st-b-store-heatmap", "data"),
    Input("st-compare-mode", "data"),
    Input("st-store-drill", "data"),
)

for _chart, _fn in [
    ("density", "renderDensity"),
    ("typical", "renderTypical"),
]:
    clientside_callback(
        ClientsideFunction(namespace="simTiming", function_name=_fn),
        Output(f"st-chart-{_chart}", "figure"),
        Input(f"st-store-{_chart}", "data"),
        Input(f"st-b-store-{_chart}", "data"),
        Input("st-compare-mode", "data"),
    )

# The per-appointment timeline is single-dataset by design: it shows one real
# appointment, so there is nothing to compare it against.
clientside_callback(
    ClientsideFunction(namespace="simTiming", function_name="renderTimeline"),
    Output("st-chart-timeline", "figure"),
    Input("st-store-timeline", "data"),
)
