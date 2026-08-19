"""Reusable outlier cap panel for duration-based pages.

Provides an expandable dropdown panel with per-transition sliders
to cap outlier durations. Uses the chip_dropdown.js auto-discovery
pattern (ID ending in "-trigger" + sibling with class "wf-chip-dropdown").

Two modes (filter mode is opt-in via ``allow_filter_mode=True``):
    - "cap":   single-handle sliders that cap long-tail values out of the
               timing metrics (the historical behavior).
    - "filter": dual-handle range sliders where each transition's [low, high]
               becomes an inclusion filter on that transition's day-count.
               High handle at ``filter_max`` == unbounded (keeps long-tail rows).

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
FILTER_SLIDER_MAX = 60


def _filter_marks(filter_max):
    """Evenly-spaced marks for the filter range slider (top mark shows '+')."""
    stops = [0, filter_max // 3, (2 * filter_max) // 3, filter_max]
    marks = []
    for s in stops:
        label = f"{filter_max}+" if s == filter_max else str(s)
        marks.append({"value": s, "label": label})
    return marks


def outlier_panel(page_id, transitions, slider_max=OUTLIER_SLIDER_MAX,
                  extra_children=None, allow_filter_mode=False,
                  filter_max=FILTER_SLIDER_MAX):
    """Build the outlier cap dropdown panel.

    Args:
        page_id: page prefix for IDs (e.g., "referrals", "cv")
        transitions: list of (label, default_days) tuples
        slider_max: maximum cap-slider value
        extra_children: optional list of additional components to append inside the panel
        allow_filter_mode: when True, add a Cap/Filter mode toggle and dual-handle
            range sliders that act as inclusion filters on each transition's day-count
        filter_max: maximum value for the filter range sliders (top handle == unbounded)
    """
    blocks = []
    for i, (label, default) in enumerate(transitions):
        cap_block = dmc.Box(
            id=f"{page_id}-outlier-cap-wrap-{i}",
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
        )

        block_children = [cap_block]

        if allow_filter_mode:
            range_block = dmc.Box(
                id=f"{page_id}-outlier-range-wrap-{i}",
                style={"display": "none"},
                children=[
                    dmc.Group(
                        justify="space-between",
                        children=[
                            dmc.Text(label, size="xs", c="#6B7280"),
                            dmc.Text(
                                "All",
                                id=f"{page_id}-outlier-range-val-{i}",
                                size="xs", fw=600, c="#7C2A83",
                            ),
                        ],
                    ),
                    dmc.RangeSlider(
                        id=f"{page_id}-outlier-range-{i}",
                        min=0, max=filter_max, step=1,
                        value=[0, filter_max],
                        marks=_filter_marks(filter_max),
                        size="xs", color="violet", minRange=0,
                        mb=26,  # room for the mark labels below the track
                    ),
                ],
            )
            block_children.append(range_block)

        blocks.append(dmc.Box(children=block_children, mb="xs"))

    panel_children = []

    if allow_filter_mode:
        panel_children.append(
            dmc.SegmentedControl(
                id=f"{page_id}-outlier-mode",
                data=[
                    {"value": "cap", "label": "Cap"},
                    {"value": "filter", "label": "Filter"},
                ],
                value="cap", size="xs", fullWidth=True, mb="xs",
            )
        )

    panel_children += [
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
            children=blocks,
        ),
    ]

    return html.Div(
        children=[
            dmc.Button(
                "Outliers: " + " / ".join(f"{d}d" for _, d in transitions),
                id=f"{page_id}-outlier-trigger",
                variant="default", size="sm",
                rightSection=DashIconify(icon="mdi:chevron-down", width=14),
            ),
            dmc.Paper(
                children=panel_children + (extra_children or []),
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


def register_outlier_callbacks(page_id, n_transitions, defaults,
                               allow_filter_mode=False,
                               filter_max=FILTER_SLIDER_MAX):
    """Register clientside callbacks for the outlier panel.

    Args:
        page_id: page prefix matching outlier_panel()
        n_transitions: number of transitions (len of defaults)
        defaults: list of default cap values
        allow_filter_mode: must match the value passed to outlier_panel()
        filter_max: must match the value passed to outlier_panel()
    """
    enabled_id = f"{page_id}-outlier-enabled"

    # "None" preset → disable
    clientside_callback(
        """function(n) { return false; }""",
        Output(enabled_id, "data", allow_duplicate=True),
        Input(f"{page_id}-outlier-preset-none", "n_clicks"),
        prevent_initial_call=True,
    )

    # "Default" preset → enable + reset sliders (and ranges, in filter mode)
    default_js = ", ".join(str(d) for d in defaults)
    outputs = [Output(enabled_id, "data", allow_duplicate=True)]
    outputs += [
        Output(f"{page_id}-outlier-cap-{i}", "value", allow_duplicate=True)
        for i in range(n_transitions)
    ]
    if allow_filter_mode:
        outputs += [
            Output(f"{page_id}-outlier-range-{i}", "value", allow_duplicate=True)
            for i in range(n_transitions)
        ]
        range_reset_js = ", ".join(f"[0, {filter_max}]" for _ in range(n_transitions))
        return_arr = f"[true, {default_js}, {range_reset_js}]"
    else:
        return_arr = f"[true, {default_js}]"
    clientside_callback(
        f"""function(n) {{ return {return_arr}; }}""",
        *outputs,
        Input(f"{page_id}-outlier-preset-default", "n_clicks"),
        prevent_initial_call=True,
    )

    # Any cap-slider change → auto-enable
    clientside_callback(
        """function() { return true; }""",
        Output(enabled_id, "data", allow_duplicate=True),
        *[Input(f"{page_id}-outlier-cap-{i}", "value") for i in range(n_transitions)],
        prevent_initial_call=True,
    )

    # Cap-slider value labels
    for i in range(n_transitions):
        clientside_callback(
            """function(v) { return v + "d"; }""",
            Output(f"{page_id}-outlier-val-{i}", "children"),
            Input(f"{page_id}-outlier-cap-{i}", "value"),
        )

    # Dim sliders when caps are disabled. In filter mode the range sliders are
    # the active control, so never dim there (only dim the cap sliders).
    if allow_filter_mode:
        clientside_callback(
            """function(enabled, mode) {
                if (mode === "filter") return "wf-outlier-sliders";
                return enabled ? "wf-outlier-sliders" : "wf-outlier-sliders is-disabled";
            }""",
            Output(f"{page_id}-outlier-sliders", "className"),
            Input(enabled_id, "data"),
            Input(f"{page_id}-outlier-mode", "value"),
        )
    else:
        clientside_callback(
            """function(enabled) {
                return enabled ? "wf-outlier-sliders" : "wf-outlier-sliders is-disabled";
            }""",
            Output(f"{page_id}-outlier-sliders", "className"),
            Input(enabled_id, "data"),
        )

    # Active-state styling for the None / Default presets: highlight the active
    # one, gray out the other so it's clear which is in effect.
    clientside_callback(
        """function(enabled) {
            return enabled
                ? ["subtle", "gray", "light", "violet"]
                : ["light", "violet", "subtle", "gray"];
        }""",
        Output(f"{page_id}-outlier-preset-none", "variant"),
        Output(f"{page_id}-outlier-preset-none", "color"),
        Output(f"{page_id}-outlier-preset-default", "variant"),
        Output(f"{page_id}-outlier-preset-default", "color"),
        Input(enabled_id, "data"),
    )

    if not allow_filter_mode:
        # Trigger button summary label (cap-only)
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
        return

    # --- Filter-mode extras ---

    # Mode toggle → show/hide cap vs range sliders per transition
    for i in range(n_transitions):
        clientside_callback(
            """function(m) {
                var show = {"display": "block"}, hide = {"display": "none"};
                return m === "filter" ? [hide, show] : [show, hide];
            }""",
            Output(f"{page_id}-outlier-cap-wrap-{i}", "style"),
            Output(f"{page_id}-outlier-range-wrap-{i}", "style"),
            Input(f"{page_id}-outlier-mode", "value"),
        )

    # Range value labels (unbounded top handle)
    for i in range(n_transitions):
        clientside_callback(
            f"""function(val) {{
                if (!val || val.length !== 2) return "All";
                var lo = val[0], hi = val[1], MAX = {filter_max};
                if (lo <= 0 && hi >= MAX) return "All";
                var hiTxt = hi >= MAX ? (MAX + "+") : ("" + hi);
                if (lo <= 0) return "≤ " + hiTxt + "d";
                if (hi >= MAX) return "≥ " + lo + "d";
                return lo + "–" + hiTxt + "d";
            }}""",
            Output(f"{page_id}-outlier-range-val-{i}", "children"),
            Input(f"{page_id}-outlier-range-{i}", "value"),
        )

    # Trigger button summary label (mode-aware)
    vals_args = ", ".join(f"v{i}" for i in range(n_transitions))
    vals_array = "[" + ", ".join(f"v{i}" for i in range(n_transitions)) + "]"
    range_args = ", ".join(f"r{i}" for i in range(n_transitions))
    range_array = "[" + ", ".join(f"r{i}" for i in range(n_transitions)) + "]"
    clientside_callback(
        f"""function(mode, enabled, {vals_args}, {range_args}) {{
            if (mode === "filter") {{
                var rs = {range_array}, MAX = {filter_max}, active = 0;
                for (var i = 0; i < rs.length; i++) {{
                    var r = rs[i];
                    if (r && r.length === 2 && !(r[0] <= 0 && r[1] >= MAX)) active++;
                }}
                return active ? ("Filters: " + active + " active") : "Filters: Off";
            }}
            if (!enabled) return "Outliers: Off";
            var vals = {vals_array};
            return "Outliers: " + vals.map(function(v) {{ return v + "d"; }}).join(" / ");
        }}""",
        Output(f"{page_id}-outlier-trigger", "children"),
        Input(f"{page_id}-outlier-mode", "value"),
        Input(enabled_id, "data"),
        *[Input(f"{page_id}-outlier-cap-{i}", "value") for i in range(n_transitions)],
        *[Input(f"{page_id}-outlier-range-{i}", "value") for i in range(n_transitions)],
    )
