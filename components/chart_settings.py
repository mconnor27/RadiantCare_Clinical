"""Chart settings component with gear icon and small dropdown panel."""

import dash_mantine_components as dmc
from dash_iconify import DashIconify
from dash import html


def _add_grouping_toggle(panel_children, chart_id, default="stacked"):
    """Append a Stacked/Grouped segmented control to panel_children."""
    panel_children.append(
        html.Div(
            id=f"{chart_id}-settings-stack-wrap",
            children=dmc.Stack(
                gap=4,
                children=[
                    dmc.Text("Grouping", size="xs", fw=500, c="#6B7280"),
                    dmc.SegmentedControl(
                        id=f"{chart_id}-settings-stack",
                        data=[
                            {"value": "stacked", "label": "Stacked"},
                            {"value": "grouped", "label": "Grouped"},
                        ],
                        value=default,
                        size="xs",
                        fullWidth=True,
                    ),
                ],
            ),
        )
    )


def chart_settings_button(
    chart_id: str,
    chart_types: list[dict] | None = None,
    chart_type_default: str | None = None,
    show_smooth: bool = True,
    smooth_min: float = 0,
    smooth_max: float = 50,
    smooth_step: float = 1,
    smooth_default: float = 15,
    show_grouping: bool = True,
    grouping_default: str = "stacked",
    slider_label: str = "Smoothing",
    show_prior_periods: bool = False,
    prior_periods_default: int = 3,
    extra_settings: list | None = None,
):
    """Create a settings gear icon with small dropdown panel.

    Args:
        chart_id: Base ID for the chart (used for component IDs)
        chart_types: List of {"value": str, "label": str} for chart type options.
                    If None, no chart type selector is shown.
        show_smooth: Whether to show smoothing slider
        smooth_max: Maximum value for smoothing slider
        smooth_default: Default smoothing value
    """
    panel_children = []

    # Chart type selector
    if chart_types:
        panel_children.append(
            html.Div(
                id=f"{chart_id}-settings-type-wrap",
                children=dmc.Stack(
                    gap=4,
                    children=[
                        dmc.Text("Chart Type", size="xs", fw=500, c="#6B7280"),
                        dmc.SegmentedControl(
                            id=f"{chart_id}-settings-type",
                            data=chart_types,
                            value=chart_type_default or chart_types[0]["value"],
                            size="xs",
                            fullWidth=True,
                        ),
                    ],
                ),
            )
        )
        # Stacked/Grouped toggle — visible only for area and bar chart types
        has_stackable = show_grouping and any(ct["value"] in ("bar", "area") for ct in chart_types)
        if has_stackable:
            _add_grouping_toggle(panel_children, chart_id, grouping_default)
    elif show_grouping and not chart_types:
        # Standalone grouping toggle (no chart type selector, always a bar/area chart)
        _add_grouping_toggle(panel_children, chart_id, grouping_default)

    # Smoothing slider
    if show_smooth:
        panel_children.append(
            html.Div(
                id=f"{chart_id}-settings-smooth-wrap",
                children=dmc.Stack(
                    gap=4,
                    children=[
                        dmc.Text(slider_label, size="xs", fw=500, c="#6B7280"),
                        dmc.Slider(
                            id=f"{chart_id}-settings-smooth",
                            min=smooth_min,
                            max=smooth_max,
                            step=smooth_step,
                            value=smooth_default,
                            size="xs",
                            showLabelOnHover=True,
                            updatemode="drag",
                        ),
                    ],
                ),
            )
        )

    # Prior periods slider
    if show_prior_periods:
        panel_children.append(
            html.Div(
                id=f"{chart_id}-settings-prior-wrap",
                children=dmc.Stack(
                    gap=4,
                    children=[
                        dmc.Text("Prior Periods", size="xs", fw=500, c="#6B7280"),
                        dmc.Slider(
                            id=f"{chart_id}-settings-prior-periods",
                            min=1,
                            max=5,
                            step=1,
                            value=prior_periods_default,
                            size="xs",
                            showLabelOnHover=True,
                            updatemode="drag",
                            marks=[{"value": i, "label": str(i)} for i in range(1, 6)],
                            mb=16,
                        ),
                    ],
                ),
            )
        )

    # Extra custom settings
    if extra_settings:
        panel_children.extend(extra_settings)

    # Export button
    panel_children.append(
        dmc.Button(
            "Export PNG",
            id=f"{chart_id}-settings-export",
            leftSection=DashIconify(icon="mdi:download", width=14),
            size="compact-xs",
            variant="light",
            fullWidth=True,
        )
    )

    return html.Div(
        [
            # Gear button
            dmc.ActionIcon(
                DashIconify(icon="mdi:cog", width=16),
                id=f"{chart_id}-settings-btn",
                variant="subtle",
                color="gray",
                size="sm",
            ),
            # Dropdown panel (hidden by default, shown via callback)
            html.Div(
                dmc.Paper(
                    dmc.Stack(gap="sm", children=panel_children),
                    p="sm",
                    radius="md",
                    shadow="md",
                    withBorder=True,
                    style={"backgroundColor": "white"},
                ),
                id=f"{chart_id}-settings-panel",
                className="chart-settings-panel",
                style={"display": "none"},
            ),
        ],
        className="chart-settings-container",
        style={"position": "relative", "display": "inline-block"},
    )


# Alias for backward compatibility
chart_settings_popover = chart_settings_button
