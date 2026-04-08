"""Page-level filter bar component."""

import dash_mantine_components as dmc
from dash_iconify import DashIconify

from config.settings import DEPARTMENTS, DEPARTMENT_COLORS


def department_chips(page_id, default_value=None):
    """Department multi-select chips with department colors."""
    if default_value is None:
        default_value = list(DEPARTMENTS)
    return dmc.ChipGroup(
        children=[
            dmc.Chip(
                dept,
                value=dept,
                color=DEPARTMENT_COLORS.get(dept, "violet"),
                variant="filled",
                size="sm",
            )
            for dept in DEPARTMENTS
        ],
        id=f"{page_id}-filter-department",
        value=default_value,
        multiple=True,
    )


def physician_short_name(full_name):
    """Convert 'Last, First' to 'Last' for chip labels.

    Generic placeholders like 'Physician, Centralia' become 'Centralia MD'.
    """
    if not full_name or "," not in full_name:
        return full_name or ""
    last, first = full_name.split(", ", 1)
    if last.lower() == "physician":
        return f"{first} MD"
    return last


def physician_options(series):
    """Build physician dropdown options from a pandas Series.

    Returns a list of {"value": name, "label": name} dicts sorted alphabetically.
    """
    names = sorted(series.dropna().unique())
    return [{"value": p, "label": p} for p in names]


def physician_select(page_id, multi=True):
    """Physician dropdown — starts empty, populated dynamically by page callback."""
    if multi:
        return dmc.MultiSelect(
            id=f"{page_id}-filter-physician",
            data=[],
            placeholder="All Physicians",
            clearable=True,
            size="sm",
            w=220,
        )
    return dmc.Select(
        id=f"{page_id}-filter-physician",
        data=[],
        placeholder="All Physicians",
        clearable=True,
        size="sm",
        w=180,
    )


def date_range_picker(page_id):
    """Date range picker."""
    return dmc.DatePickerInput(
        id=f"{page_id}-filter-daterange",
        type="range",
        placeholder="Date range",
        size="sm",
        w=260,
        clearable=True,
    )


def date_presets(page_id):
    """Date preset segmented control (YTD / 12mo / All)."""
    return dmc.SegmentedControl(
        id=f"{page_id}-filter-date-preset",
        data=[
            {"value": "ytd", "label": "YTD"},
            {"value": "12mo", "label": "12 mo"},
            {"value": "all", "label": "All"},
        ],
        value="12mo",
        size="sm",
    )


def filter_bar(page_id, children=None):
    """Create the filter bar container.

    Args:
        page_id: page identifier for namespacing IDs
        children: list of filter components to include
    """
    if children is None:
        children = [
            date_presets(page_id),
            date_range_picker(page_id),
            department_chips(page_id),
            physician_select(page_id),
        ]

    return dmc.Paper(
        children=[
            dmc.Group(
                children=children,
                gap="md",
                wrap="wrap",
            ),
        ],
        p="sm",
        px="md",
        radius="md",
        shadow="xs",
        withBorder=True,
    )
