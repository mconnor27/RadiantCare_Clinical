"""Patients page — UI and data-processing help content.

The rendered content adapts to PHI_MODE at import time: when sanitized-data
mode is active the map card is hidden in the app, so the help page drops
map / geocoding sections to avoid documenting a feature the user can't see.
"""

from __future__ import annotations

import dash_mantine_components as dmc
from dash_iconify import DashIconify

from config.settings import PHI_MODE, PRIMARY
from ..renderers import body, bullets, section, subheading


# ---------------------------------------------------------------------------
# KPI row bullets — same in both modes
# ---------------------------------------------------------------------------

_KPI_BULLETS = [
    "Total Patients — distinct PatientId count for the filtered period.",
    "Unique Cities — distinct non-blank City values after title-case "
    "normalization.",
    "Top City — single city with the largest patient count.",
    "Three per-site cards — Lacey (blue), Centralia (red), Aberdeen "
    "(green). Each shows count and % of the filtered total.",
]


# ---------------------------------------------------------------------------
# Chart bullets — differ slightly between modes (no map text in PHI_MODE)
# ---------------------------------------------------------------------------

_CHART_BULLETS_COMMON = [
    "Top Cities by Patient Count — horizontal stacked bar, up to the top 12 "
    "cities, stacked by department with department colors and a total "
    "annotation at the end of each bar.",
    "Demographics — switch between Age and Gender with the metric toggle.",
    "  • Age: density curve or histogram (toggle). All patients in one "
    "series, or per-site split. A smoothing slider controls KDE bandwidth "
    "for the density view. A dashed vertical line marks the median."
    + ("" if PHI_MODE else
       " Age can be computed as \"age at first appointment\" or \"age at "
       "last appointment\" — segmented control on the filter bar."),
    "  • Gender: horizontal bar of totals in All mode, or grouped bars per "
    "department in Per Site mode. A Count / Percent toggle switches between "
    "raw patient counts and share (of the whole in All mode, of each site's "
    "total in Per Site mode). Values come from the Gender column on Lookup - "
    "Patients; \"Unknown\" captures blank / null values.",
]


# ---------------------------------------------------------------------------
# Map section (skipped entirely in PHI_MODE)
# ---------------------------------------------------------------------------

def _map_overview_block():
    return [
        dmc.Text("Patient Origin Map", fw=600, size="xs", mb=4),
        body(
            "Mapbox scatter layer, one dot per ZIP centroid colored by "
            "department. Dot size scales with unique patient count at that "
            "ZIP. Three fixed site markers (Lacey / Centralia / Aberdeen) "
            "are anchored at their actual coordinates. Optional bezier "
            "\"flow lines\" draw from each ZIP cluster to the site(s) it "
            "feeds, line width proportional to volume.",
        ),
        bullets([
            "Flow lines switch — toggle the bezier arcs on / off.",
            "Min slider (1–20) — hide ZIPs below a minimum patient count so "
            "the map isn't dominated by one-offs.",
            "Region toggle — PNW (zoomed to WA / OR / ID) or All US.",
            "Flow department toggle — All or one of Lacey / Centralia / "
            "Aberdeen; filters the flow-line layer only, not the dots.",
            "Reset map view — recenter / rezoom.",
            "A geocoding status banner appears on first load while ZIPs are "
            "being resolved in a background thread; it disappears once the "
            "cache is warm.",
        ]),
        dmc.Space(h="xs"),
    ]


def _geocoding_section():
    return section(
        "Geocoding and map data",
        "tabler:map-pin",
        body(
            "ZIP-code to lat / lon resolution is handled by "
            "utils.geocoding. The first page load triggers a background "
            "geocode for any ZIPs not already in the cache; the page polls "
            "is_geocoding_complete() every 5 seconds (up to 10 minutes) and "
            "re-renders the map once the cache is warm. Aggregation is at "
            "the 5-digit ZIP centroid, not street-address precision — that "
            "keeps the visualization PHI-safe and avoids per-patient "
            "geocoding costs.",
        ),
        bullets([
            "ZIPs are normalized to 5-digit strings (leading zeros "
            "preserved) before cache lookup.",
            "Department site markers are hard-coded in utils.geocoding."
            "DEPT_COORDS: Lacey (47.0452, -122.8258), Centralia "
            "(46.7141, -123.0101), Aberdeen (46.9754, -123.8157).",
            "Flow-line arcs use a quadratic bezier for visual clarity, not "
            "a geodesic great-circle path — the curves are purely aesthetic.",
            "Requires MAPBOX_TOKEN in the environment. Without it the map "
            "falls back to a blank canvas and the dots / flows render on "
            "whatever style Plotly can produce locally.",
        ]),
    )


# ---------------------------------------------------------------------------
# Layout assembly
# ---------------------------------------------------------------------------

_intro_text = (
    "The Patients page is the demographic and geographic view of the "
    "practice. It shows where patients come from, which communities feed "
    "which site, and how the population breaks down by city, age, and "
    "gender. Data is per-patient (not per-visit), built from the Lookup - "
    "Patients extract which already joins demographics to each patient's "
    "primary treatment department."
) if not PHI_MODE else (
    "The Patients page is the demographic view of the practice — city, "
    "age, and gender breakdowns for the filtered patient set. Data is "
    "per-patient (not per-visit), built from the Lookup - Patients extract "
    "which already joins demographics to each patient's primary treatment "
    "department. The ZIP-level map is hidden in this PHI-safe build."
)

_whats_on_page_body = (
    "A single-row filter bar, a 5-card KPI row, a full-width Mapbox map "
    "with inline overlay controls, and a row of two charts (Top Cities bar "
    "+ Demographics — Age / Gender with mode-specific controls)."
) if not PHI_MODE else (
    "A single-row filter bar, a 5-card KPI row, and a row of two charts "
    "(Top Cities bar + Demographics — Age / Gender with mode-specific "
    "controls). The patient-origin map is omitted in PHI-safe mode."
)

_whats_on_page_children = [
    body(_whats_on_page_body),
    dmc.Space(h="xs"),
    dmc.Text("KPI row (5 cards)", fw=600, size="xs", mb=4),
    bullets(_KPI_BULLETS),
    dmc.Space(h="xs"),
]

if not PHI_MODE:
    _whats_on_page_children.extend(_map_overview_block())

_whats_on_page_children.extend([
    dmc.Text("Charts", fw=600, size="xs", mb=4),
    bullets(_CHART_BULLETS_COMMON),
])


_filters_bullets = [
    "Date preset + date picker + month RangeSlider, all two-way "
    "synced. Anchored data-relatively to the max of FirstAppointment / "
    "LastAppointment.",
    "Department chips — Lacey / Centralia / Aberdeen.",
]
if PHI_MODE:
    _filters_bullets.append(
        "Age RangeSlider — dynamic min / max computed from the current "
        "date+department subset so the range always covers the visible "
        "data. In PHI-safe mode age comes from the pre-computed AgeAtLoad "
        "column (capped at 90), so the First Appt / Last Appt reference "
        "toggle is hidden."
    )
else:
    _filters_bullets.append(
        "Age RangeSlider — dynamic min / max computed from the current "
        "date+department subset so the range always covers the visible "
        "data; age-reference toggle switches between First Appt and Last "
        "Appt."
    )


_data_processing_bullets = [
    "Source: load_patients() reads Lookup/Lookup - Patients.csv — "
    "one row per patient with demographics, primary Department, "
    "FirstAppointment, LastAppointment, DateOfBirth, Gender, City, "
    "County, Zip.",
    "Department is stripped of the * prefix on load "
    "(DataFrame.str.replace).",
    "Dates (FirstAppointment, LastAppointment, DateOfBirth) are "
    "parsed with format=\"%m/%d/%Y\" — the ARIA date-only format.",
    "Age is computed in-page from DateOfBirth vs the chosen "
    "reference appointment; the age min / max / marks on the "
    "slider are rebuilt on every filter change so the range always "
    "matches the filtered dataset."
    + (" In PHI_MODE DOB is dropped at build time and age reads from the "
       "pre-computed AgeAtLoad column instead (ages 90+ reported as 90)."
       if PHI_MODE else ""),
    "Gender is taken straight from the Lookup - Patients Gender column. "
    "Nulls and blanks are coalesced to \"Unknown\" so they still appear "
    "in the chart instead of silently dropping out. Counts are deduped "
    "to one row per patient (per patient-per-department in Per Site "
    "mode) so the Gender totals match the Total Patients KPI.",
    "Top cities are computed with City.str.strip().str.title() and "
    "null-blank replacement, then grouped by (City, Department) for "
    "the stacked bar totals.",
]

if not PHI_MODE:
    _data_processing_bullets.append(
        "Only aggregated ZIP-level data is serialized to the clientside "
        "Store — patient IDs stay server-side to avoid exposing PHI in "
        "the browser state."
    )

_data_processing_bullets.extend([
    "Demographics data is stored raw and rendered clientside so the "
    "Age / Gender, density / histogram, smoothing, Count / Percent, and "
    "per-site toggles don't trigger a server round-trip.",
])

if not PHI_MODE:
    _data_processing_bullets.append(
        "When the user changes a filter the map selection state "
        "(highlighted ZIPs from click) is cleared; interval refreshes "
        "preserve selection."
    )


_known_quirks_bullets = []
if not PHI_MODE:
    _known_quirks_bullets.extend([
        "Geocoding is ZIP-centroid only — a patient in a very large rural "
        "ZIP shows up at the ZIP's geographic center, not their actual "
        "address. Flow volumes are aggregated accordingly.",
        "First-load geocode can take up to a few minutes the very first "
        "time a new ZIP appears. The banner will tell you when it's done; "
        "subsequent loads read from the cache and are instant.",
    ])
_known_quirks_bullets.extend([
    "The \"Top City\" KPI can be a small city if a larger city "
    "doesn't title-case cleanly — normalization is best-effort but "
    "ARIA address data has free-text variance.",
    "Gender is self-reported in ARIA and reflects whatever value was "
    "entered at registration — historical records may use a different "
    "taxonomy than current practice.",
    "The physician filter is not present on this page — patient "
    "lookup data is pre-aggregated per patient, not per visit, so "
    "there is no treating-physician dimension to filter on.",
    "The Patients data source is a single Lookup file, not "
    "incremental. The most-recent load replaces the whole snapshot "
    "each refresh; historical patient counts will shift if a "
    "patient's primary department changes between snapshots.",
])


_stack_children = [
    dmc.Text(
        _intro_text,
        size="sm", c="dimmed", style={"lineHeight": 1.6},
    ),
    section(
        "What's on this page",
        "tabler:layout-dashboard",
        *_whats_on_page_children,
    ),
    section(
        "Filters",
        "tabler:filter",
        bullets(_filters_bullets),
    ),
]

if not PHI_MODE:
    _stack_children.append(_geocoding_section())

_stack_children.extend([
    section(
        "How the data is processed",
        "tabler:cpu",
        bullets(_data_processing_bullets),
    ),
    section(
        "Known quirks and limitations",
        "tabler:alert-triangle",
        bullets(_known_quirks_bullets),
    ),
])


UI_CONTENT = dmc.Stack(gap="md", children=_stack_children)
