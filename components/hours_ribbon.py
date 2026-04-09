"""Reusable Operating Hours ribbon chart card with week navigation.

Usage:
    from components.hours_ribbon import hours_ribbon_card, register_hours_ribbon_callbacks

    # In layout:
    hours_ribbon_card("home")   # or hours_ribbon_card("ops")

    # After layout, register all callbacks:
    register_hours_ribbon_callbacks("home", extra_inputs=[...])
"""

import dash_mantine_components as dmc
from dash import dcc, html, callback, clientside_callback, Input, Output, State, ClientsideFunction
from dash_iconify import DashIconify

from components.chart_settings import chart_settings_popover


def hours_ribbon_card(prefix, *, card_height="100%", chart_height=None):
    """Return a Paper card with Operating Hours ribbon chart and week navigation.

    Args:
        prefix: ID prefix (e.g. "home" or "ops"). All component IDs will be
                ``{prefix}-hours-*``.
        card_height: CSS height for the outer Paper.
        chart_height: CSS height for the dcc.Graph (default: fills remaining space).
    """
    return dmc.Paper(
        children=[
            dmc.Group(
                justify="space-between", mb=8,
                children=[
                    dmc.Group(gap="sm", align="center", children=[
                        dmc.Text("Operating Hours", size="sm", fw=500, c="#6B7280"),
                        dmc.SegmentedControl(
                            id=f"{prefix}-hours-site",
                            data=[
                                {"value": "all", "label": "All"},
                                {"value": "Lacey", "label": "Lacey"},
                                {"value": "Centralia", "label": "Centralia"},
                                {"value": "Aberdeen", "label": "Aberdeen"},
                            ],
                            value="all", size="xs",
                        ),
                    ]),
                    dmc.Group(gap="xs", align="center", wrap="nowrap", children=[
                        html.Div(
                            id=f"{prefix}-hours-week-nav",
                            children=dmc.Group(gap=4, align="center", children=[
                                dmc.ActionIcon(
                                    DashIconify(icon="mdi:chevron-left", width=18),
                                    id=f"{prefix}-hours-week-prev",
                                    variant="subtle", color="gray", size="sm",
                                ),
                                dmc.Button(
                                    "Today",
                                    id=f"{prefix}-hours-week-today",
                                    variant="subtle", color="gray",
                                    size="compact-xs",
                                ),
                                dmc.ActionIcon(
                                    DashIconify(icon="mdi:chevron-right", width=18),
                                    id=f"{prefix}-hours-week-next",
                                    variant="subtle", color="gray", size="sm",
                                ),
                            ]),
                        ),
                        dmc.SegmentedControl(
                            id=f"{prefix}-hours-range",
                            data=[
                                {"value": "thisweek", "label": "Week"},
                                {"value": "30", "label": "30d"},
                                {"value": "90", "label": "90d"},
                                {"value": "365", "label": "1y"},
                                {"value": "0", "label": "All"},
                            ],
                            value="thisweek", size="xs",
                        ),
                        chart_settings_popover(
                            f"{prefix}-hours",
                            chart_types=[
                                {"value": "ribbon", "label": "Ribbon"},
                                {"value": "line", "label": "Line"},
                                {"value": "bar", "label": "Bar"},
                            ],
                            show_smooth=True,
                            smooth_max=7,
                            smooth_default=3,
                            show_grouping=False,
                        ),
                    ]),
                ],
            ),
            dmc.Box(
                pos="relative",
                style={"flex": "1", "minHeight": 0},
                children=[
                    dmc.Box(
                        style={"position": "absolute", "top": 0, "left": 0, "right": 0, "bottom": 0},
                        children=[
                            dmc.LoadingOverlay(
                                id=f"{prefix}-hours-loading",
                                visible=False,
                                loaderProps={"type": "dots", "color": "#7C2A83"},
                                overlayProps={"radius": "sm", "blur": 2},
                            ),
                            dcc.Graph(
                                id=f"{prefix}-chart-hours",
                                config={
                                    "displayModeBar": False,
                                    "scrollZoom": False,
                                    "doubleClick": "reset",
                                },
                                style={"height": "100%"},
                            ),
                        ],
                    ),
                ],
            ),
            # Hidden stores
            dcc.Store(id=f"{prefix}-store-hours"),
            dcc.Store(id=f"{prefix}-hours-week-offset", data=0),
        ],
        p="sm", pb=8, radius="md", shadow="xs", withBorder=True, h=card_height,
        style={"display": "flex", "flexDirection": "column"},
    )


def register_hours_ribbon_callbacks(prefix):
    """Register all clientside callbacks for the hours ribbon chart.

    Must be called at module level (not inside a function) so Dash
    registers the callbacks at import time.

    Args:
        prefix: Same ID prefix passed to ``hours_ribbon_card()``.
    """
    # Main chart render
    clientside_callback(
        ClientsideFunction(namespace="hoursRibbon", function_name="smoothChartWithTypeAndRange"),
        Output(f"{prefix}-chart-hours", "figure"),
        Input(f"{prefix}-store-hours", "data"),
        Input(f"{prefix}-hours-settings-smooth", "value"),
        Input(f"{prefix}-hours-settings-type", "value"),
        Input(f"{prefix}-hours-range", "value"),
        Input(f"{prefix}-hours-week-offset", "data"),
    )

    # Show/hide week nav buttons
    clientside_callback(
        """function(range) {
            // Keep layout width stable across modes to avoid graph area jumping.
            // Hide with visibility instead of display:none so header height/width
            // does not reflow when toggling Week mode on/off.
            return range === "thisweek"
                ? {visibility: "visible", pointerEvents: "auto"}
                : {visibility: "hidden", pointerEvents: "none"};
        }""",
        Output(f"{prefix}-hours-week-nav", "style"),
        Input(f"{prefix}-hours-range", "value"),
    )

    # Range change → reset week offset
    clientside_callback(
        """function(range) { return 0; }""",
        Output(f"{prefix}-hours-week-offset", "data"),
        Input(f"{prefix}-hours-range", "value"),
    )

    # Previous week
    clientside_callback(
        """function(n, current) { return (current || 0) - 1; }""",
        Output(f"{prefix}-hours-week-offset", "data", allow_duplicate=True),
        Input(f"{prefix}-hours-week-prev", "n_clicks"),
        State(f"{prefix}-hours-week-offset", "data"),
        prevent_initial_call=True,
    )

    # Next week
    clientside_callback(
        """function(n, current) { return (current || 0) + 1; }""",
        Output(f"{prefix}-hours-week-offset", "data", allow_duplicate=True),
        Input(f"{prefix}-hours-week-next", "n_clicks"),
        State(f"{prefix}-hours-week-offset", "data"),
        prevent_initial_call=True,
    )

    # Today → reset
    clientside_callback(
        """function(n) { return 0; }""",
        Output(f"{prefix}-hours-week-offset", "data", allow_duplicate=True),
        Input(f"{prefix}-hours-week-today", "n_clicks"),
        prevent_initial_call=True,
    )

    # Y-axis rescaling on pan
    clientside_callback(
        ClientsideFunction(namespace="hoursYAxis", function_name="updateOnPan"),
        Output(f"{prefix}-chart-hours", "figure", allow_duplicate=True),
        Input(f"{prefix}-chart-hours", "relayoutData"),
        State(f"{prefix}-chart-hours", "figure"),
        State(f"{prefix}-store-hours", "data"),
        State(f"{prefix}-hours-range", "value"),
        prevent_initial_call=True,
    )

    # Hide chart type selector in Week mode (calendar view ignores chart type)
    clientside_callback(
        """function(rangeDays) {
            return rangeDays === "thisweek"
                ? {display: "none"} : {display: "block"};
        }""",
        Output(f"{prefix}-hours-settings-type-wrap", "style"),
        Input(f"{prefix}-hours-range", "value"),
    )

    # Hide smoothing slider in Week mode or Bar mode (neither uses smoothing)
    clientside_callback(
        """function(rangeDays, chartType) {
            var hide = (rangeDays === "thisweek") || (chartType === "bar");
            return hide ? {display: "none"} : {display: "block"};
        }""",
        Output(f"{prefix}-hours-settings-smooth-wrap", "style"),
        Input(f"{prefix}-hours-range", "value"),
        Input(f"{prefix}-hours-settings-type", "value"),
    )

    # Smoothing slider max based on range
    @callback(
        Output(f"{prefix}-hours-settings-smooth", "max"),
        Output(f"{prefix}-hours-settings-smooth", "value"),
        Input(f"{prefix}-hours-range", "value"),
        State(f"{prefix}-hours-settings-smooth", "value"),
    )
    def _update_smooth_max(range_days, current_value):
        if range_days == "thisweek":
            return 3, min(current_value or 0, 3)
        days = int(range_days) if range_days else 30
        if days == 0:
            max_val = 50
        elif days <= 7:
            max_val = 3
        elif days <= 30:
            max_val = 7
        elif days <= 60:
            max_val = 12
        elif days <= 90:
            max_val = 18
        elif days <= 365:
            max_val = 30
        else:
            max_val = 50
        return max_val, min(current_value or 0, max_val)

    # Settings panel toggle
    @callback(
        Output(f"{prefix}-hours-settings-panel", "style"),
        Input(f"{prefix}-hours-settings-btn", "n_clicks"),
        State(f"{prefix}-hours-settings-panel", "style"),
        prevent_initial_call=True,
    )
    def _toggle_settings(n, style):
        if not n:
            return style
        current = style or {}
        is_hidden = current.get("display") == "none"
        return {"display": "block"} if is_hidden else {"display": "none"}

    # PNG export
    clientside_callback(
        f"""function(n) {{
            if (!n) return window.dash_clientside.no_update;
            var wrapper = document.getElementById('{prefix}-chart-hours');
            var graphEl = wrapper ? wrapper.querySelector('.js-plotly-plot') : null;
            if (graphEl) {{
                Plotly.downloadImage(graphEl, {{format: 'png', width: 1200, height: 600, filename: 'operating_hours'}});
            }}
            return window.dash_clientside.no_update;
        }}""",
        Output(f"{prefix}-hours-settings-export", "n_clicks"),
        Input(f"{prefix}-hours-settings-export", "n_clicks"),
        prevent_initial_call=True,
    )
