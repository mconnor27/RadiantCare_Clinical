"""Reusable outlier cap panel for duration-based pages.

Provides an expandable dropdown panel with per-transition sliders
to cap outlier durations. Uses the chip_dropdown.js auto-discovery
pattern (ID ending in "-trigger" + sibling with class "wf-chip-dropdown").

Usage:
    from components.outlier_panel import outlier_panel, register_outlier_callbacks

    # In layout — add to filter bar:
    outlier_panel("mypage", transitions=[
        ("Created → Scheduled", 14),
        ("Scheduled → Visit", 28),
    ])

    # After layout — register callbacks:
    register_outlier_callbacks("mypage", n_transitions=2, defaults=[14, 28])
"""

import dash_mantine_components as dmc
from dash import dcc, html, clientside_callback, Output, Input
from dash_iconify import DashIconify


OUTLIER_SLIDER_MAX = 120


def outlier_panel(page_id, transitions, slider_max=OUTLIER_SLIDER_MAX):
    """Build the outlier cap dropdown panel.

    Args:
        page_id: page prefix for IDs (e.g., "referrals", "cv")
        transitions: list of (label, default_days) tuples
        slider_max: maximum slider value
    """
    sliders = []
    for i, (label, default) in enumerate(transitions):
        sliders.append(
            dmc.Box(
                children=[
                    dmc.Group(
                        justify="space-between",
                        children=[
                            dmc.Text(label, size="xs", c="#6B7280"),
                            dmc.Text(
                                f"{default}d",
                                id=f"{page_id}-outlier-val-{i}",
                                size="xs", fw=600, c="#7C2A83",
                            ),
                        ],
                    ),
                    dmc.Slider(
                        id=f"{page_id}-outlier-cap-{i}",
                        min=1, max=slider_max, step=1,
                        value=default, size="xs", color="violet",
                        showLabelOnHover=True,
                    ),
                ],
                mb="xs",
            )
        )

    return html.Div(
        children=[
            dmc.Button(
                "Outliers: " + " / ".join(f"{d}d" for _, d in transitions),
                id=f"{page_id}-outlier-trigger",
                variant="default", size="sm",
                rightSection=DashIconify(icon="mdi:chevron-down", width=14),
            ),
            dmc.Paper(
                children=[
                    dmc.Group(gap="xs", mb="sm", children=[
                        dmc.Button(
                            "None",
                            id=f"{page_id}-outlier-preset-none",
                            size="compact-xs", variant="light",
                        ),
                        dmc.Button(
                            "Default",
                            id=f"{page_id}-outlier-preset-default",
                            size="compact-xs", variant="light", color="violet",
                        ),
                    ]),
                    html.Div(
                        id=f"{page_id}-outlier-sliders",
                        className="wf-outlier-sliders",
                        children=sliders,
                    ),
                ],
                id=f"{page_id}-outlier-panel",
                p="sm", shadow="md", withBorder=True, radius="md",
                className="wf-chip-dropdown",
                style={"display": "none", "minWidth": "260px"},
            ),
            # Store: whether outlier caps are enabled
            dcc.Store(id=f"{page_id}-outlier-enabled", data=True),
        ],
        style={"position": "relative", "display": "inline-block"},
    )


def register_outlier_callbacks(page_id, n_transitions, defaults):
    """Register clientside callbacks for the outlier panel.

    Args:
        page_id: page prefix matching outlier_panel()
        n_transitions: number of transitions (len of defaults)
        defaults: list of default cap values
    """
    enabled_id = f"{page_id}-outlier-enabled"

    # "None" preset → disable
    clientside_callback(
        """function(n) { return false; }""",
        Output(enabled_id, "data", allow_duplicate=True),
        Input(f"{page_id}-outlier-preset-none", "n_clicks"),
        prevent_initial_call=True,
    )

    # "Default" preset → enable + reset sliders
    default_js = ", ".join(str(d) for d in defaults)
    outputs = [Output(enabled_id, "data", allow_duplicate=True)]
    outputs += [
        Output(f"{page_id}-outlier-cap-{i}", "value", allow_duplicate=True)
        for i in range(n_transitions)
    ]
    clientside_callback(
        f"""function(n) {{ return [true, {default_js}]; }}""",
        *outputs,
        Input(f"{page_id}-outlier-preset-default", "n_clicks"),
        prevent_initial_call=True,
    )

    # Any slider change → auto-enable
    clientside_callback(
        """function() { return true; }""",
        Output(enabled_id, "data", allow_duplicate=True),
        *[Input(f"{page_id}-outlier-cap-{i}", "value") for i in range(n_transitions)],
        prevent_initial_call=True,
    )

    # Slider value labels
    for i in range(n_transitions):
        clientside_callback(
            """function(v) { return v + "d"; }""",
            Output(f"{page_id}-outlier-val-{i}", "children"),
            Input(f"{page_id}-outlier-cap-{i}", "value"),
        )

    # Trigger button summary label
    defaults_js = "[" + ", ".join(str(d) for d in defaults) + "]"
    vals_args = ", ".join(f"v{i}" for i in range(n_transitions))
    vals_array = "[" + ", ".join(f"v{i}" for i in range(n_transitions)) + "]"
    clientside_callback(
        f"""function(enabled, {vals_args}) {{
            if (!enabled) return "Outliers: Off";
            var vals = {vals_array};
            return "Outliers: " + vals.map(function(v) {{ return v + "d"; }}).join(" / ");
        }}""",
        Output(f"{page_id}-outlier-trigger", "children"),
        Input(enabled_id, "data"),
        *[Input(f"{page_id}-outlier-cap-{i}", "value") for i in range(n_transitions)],
    )

    # Dim sliders when disabled
    clientside_callback(
        """function(enabled) {
            return enabled ? "wf-outlier-sliders" : "wf-outlier-sliders is-disabled";
        }""",
        Output(f"{page_id}-outlier-sliders", "className"),
        Input(enabled_id, "data"),
    )
