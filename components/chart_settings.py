"""Chart settings component with gear icon and small dropdown panel."""

import dash_mantine_components as dmc
from dash_iconify import DashIconify
from dash import html


def chart_settings_button(
    chart_id: str,
    chart_types: list[dict] | None = None,
    show_smooth: bool = True,
    smooth_max: int = 50,
    smooth_default: int = 15,
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
            dmc.Stack(
                gap=4,
                children=[
                    dmc.Text("Chart Type", size="xs", fw=500, c="#6B7280"),
                    dmc.SegmentedControl(
                        id=f"{chart_id}-settings-type",
                        data=chart_types,
                        value=chart_types[0]["value"],
                        size="xs",
                        fullWidth=True,
                    ),
                ],
            )
        )

    # Smoothing slider
    if show_smooth:
        panel_children.append(
            dmc.Stack(
                gap=4,
                children=[
                    dmc.Text("Smoothing", size="xs", fw=500, c="#6B7280"),
                    dmc.Slider(
                        id=f"{chart_id}-settings-smooth",
                        min=0,
                        max=smooth_max,
                        step=1,
                        value=smooth_default,
                        size="xs",
                        showLabelOnHover=True,
                        updatemode="drag",
                    ),
                ],
            )
        )

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
