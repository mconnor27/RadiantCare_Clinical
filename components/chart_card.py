"""Reusable chart card component and callback registration helpers."""

import dash_mantine_components as dmc
from dash import dcc, clientside_callback, ClientsideFunction, Output, Input, State

from config.settings import (
    DEFAULT_GRAPH_CONFIG, CHART_PAPER_HEIGHT, CHART_GRAPH_HEIGHT,
    PRIMARY, NEUTRAL,
)
from components.chart_settings import chart_settings_popover


def chart_card(
    chart_id: str,
    title: str,
    chart_types=None,
    chart_type_default=None,
    show_smooth=True,
    smooth_min=0,
    smooth_max=40,
    smooth_step=1,
    smooth_default=15,
    slider_label="Smoothing",
    graph_height=CHART_GRAPH_HEIGHT,
    extra_controls=None,
    extra_controls_left=None,
    store_data=False,
    paper_height=CHART_PAPER_HEIGHT,
    paper_padding="sm",
    paper_style=None,
    graph_config=None,
    show_loading=True,
    show_settings=True,
    settings_id=None,
    sub_header=None,
    show_grouping=True,
    show_prior_periods=False,
    prior_periods_default=3,
    show_project_toggle=False,
    project_toggle_default=True,
    extra_settings=None,
):
    """Build a chart card with standardized Paper, Graph, LoadingOverlay, and settings.

    Args:
        chart_id: ID for the dcc.Graph component (e.g., "home-chart-physician").
        title: Card title text.
        chart_types: Chart type options for settings popover, e.g.
            [{"value": "line", "label": "Line"}, ...]. None hides type selector.
        show_smooth: Show smoothing slider in settings.
        smooth_max: Smoothing slider max value.
        smooth_default: Smoothing slider default value.
        graph_height: CSS height for the Graph (default "380px", or "100%" for flex).
        extra_controls: List of DMC components for the right side of the title row.
        extra_controls_left: List of DMC components grouped with the title (left side).
        store_data: If True, include a dcc.Store(id=f"{chart_id}-store").
        paper_height: CSS height for the Paper container (default "440px").
        paper_padding: Paper padding prop (default "sm").
        paper_style: Extra style dict merged onto Paper (e.g. flex layout).
        graph_config: Override DEFAULT_GRAPH_CONFIG if needed.
        show_loading: Include a LoadingOverlay (default True).
        show_settings: Include the settings gear popover (default True).
        settings_id: ID prefix for settings popover (defaults to chart_id).
            Use when the settings ID differs from the graph ID (e.g.,
            chart_id="home-chart-physician", settings_id="home-md").
    """
    # --- Title row ---
    left_children = []
    if title:
        left_children.append(
            dmc.Text(title, size="sm", fw=500, c=NEUTRAL["text_secondary"])
        )
    if extra_controls_left:
        left_children.extend(extra_controls_left)

    right_children = []
    if extra_controls:
        right_children.extend(extra_controls)
    sid = settings_id or chart_id
    if show_settings:
        right_children.append(
            chart_settings_popover(
                sid,
                chart_types=chart_types,
                chart_type_default=chart_type_default,
                show_smooth=show_smooth,
                smooth_min=smooth_min,
                smooth_max=smooth_max,
                smooth_step=smooth_step,
                smooth_default=smooth_default,
                show_grouping=show_grouping,
                slider_label=slider_label,
                show_prior_periods=show_prior_periods,
                prior_periods_default=prior_periods_default,
                show_project_toggle=show_project_toggle,
                project_toggle_default=project_toggle_default,
                extra_settings=extra_settings,
            )
        )

    if len(left_children) > 1:
        left_slot = dmc.Group(gap="sm", align="center", children=left_children)
    elif len(left_children) == 1:
        left_slot = left_children[0]
    else:
        left_slot = None

    header = dmc.Group(
        justify="space-between",
        mb=8,
        children=[
            left_slot,
            dmc.Group(gap="xs", align="center", wrap="nowrap", children=right_children)
            if right_children
            else None,
        ],
    )

    # --- Graph area ---
    # Flex: 1 on the outer box claims remaining space; the inner absolute-
    # positioned wrapper gives Plotly a fixed pixel size without the
    # measure→render→resize feedback loop that height:100% causes.
    config = {**DEFAULT_GRAPH_CONFIG, "responsive": True}
    if graph_config:
        config.update(graph_config)

    inner_children = []
    if show_loading:
        inner_children.append(
            dmc.LoadingOverlay(
                id=f"{chart_id}-loading",
                visible=False,
                loaderProps={"type": "dots", "color": PRIMARY},
                overlayProps={"radius": "sm", "blur": 2},
            )
        )
    inner_children.append(
        dcc.Graph(
            id=chart_id,
            config=config,
            responsive=True,
            style={"height": "100%", "width": "100%"},
        )
    )

    graph_box = dmc.Box(
        pos="relative",
        style={"flex": "1", "minHeight": 0},
        children=[
            dmc.Box(
                style={"position": "absolute", "top": 0, "left": 0, "right": 0, "bottom": 0},
                children=inner_children,
            )
        ],
    )

    # --- Assemble Paper ---
    paper_children = [header]
    if sub_header:
        paper_children.append(sub_header)
    paper_children.append(graph_box)
    if store_data:
        paper_children.append(dcc.Store(id=f"{chart_id}-store"))

    base_style = {"display": "flex", "flexDirection": "column"}
    if paper_style:
        base_style.update(paper_style)

    paper_kwargs = dict(
        children=paper_children,
        p=paper_padding,
        pb=8,
        radius="md",
        shadow="xs",
        withBorder=True,
    )
    if paper_height:
        paper_kwargs["h"] = paper_height
    if base_style:
        paper_kwargs["style"] = base_style

    return dmc.Paper(**paper_kwargs)


def register_chart_callbacks(chart_ids):
    """Register settings-toggle and PNG-export clientside callbacks for chart IDs.

    Each per-behavior concern is consolidated into ONE batched callback per
    page (4 total: panel toggle, export click, stack-wrap visibility, smooth-
    wrap visibility) instead of 4 callbacks PER CHART. This dramatically
    reduces Dash's per-store selector-walk cost on pages with many charts.

    Each entry can be:
    - A string: used as both the settings prefix AND the graph ID for export.
    - A 2-tuple (settings_id, graph_id): settings prefix differs from graph ID.
    - A 3-tuple (settings_id, graph_id, store_id): also wire the Stacked/Grouped
      toggle and smooth-hide-on-bar to the chart's settings type selector.
    - A dict with keys: sid, gid, store_id, show_smooth (for fine-grained control).
    """
    # Normalize entries
    norm = []
    for entry in chart_ids:
        show_smooth = True
        show_grouping = True
        if isinstance(entry, dict):
            sid = entry["sid"]
            gid = entry["gid"]
            store_id = entry.get("store_id")
            show_smooth = entry.get("show_smooth", True)
            show_grouping = entry.get("show_grouping", True)
        elif isinstance(entry, tuple) and len(entry) == 3:
            sid, gid, store_id = entry
        elif isinstance(entry, tuple):
            sid, gid = entry
            store_id = None
        else:
            sid = gid = entry
            store_id = None
        norm.append((sid, gid, store_id, show_grouping, show_smooth))

    # ----- Settings-panel toggle: one callback for all charts -----
    # Takes N btn.n_clicks + N panel.style states; finds the triggered btn
    # via callback_context and flips only that panel.
    # Single-output case returns a scalar; multi-output returns an array.
    if len(norm) == 1:
        sid, _, _, _, _ = norm[0]
        clientside_callback(
            """function(n_clicks, curStyle) {
                curStyle = curStyle || {};
                var hidden = (curStyle && curStyle.display === 'none');
                return Object.assign({}, curStyle, {display: hidden ? 'block' : 'none'});
            }""",
            Output(f"{sid}-settings-panel", "style"),
            Input(f"{sid}-settings-btn", "n_clicks"),
            State(f"{sid}-settings-panel", "style"),
            prevent_initial_call=True,
        )
        clientside_callback(
            ClientsideFunction("chartExport", "exportPng"),
            Output(f"{sid}-settings-export", "n_clicks"),
            Input(f"{sid}-settings-export", "n_clicks"),
            State(norm[0][1], "id"),
            prevent_initial_call=True,
        )
    else:
        toggle_inputs = [Input(f"{sid}-settings-btn", "n_clicks") for sid, _, _, _, _ in norm]
        toggle_states = [State(f"{sid}-settings-panel", "style") for sid, _, _, _, _ in norm]
        toggle_outputs = [Output(f"{sid}-settings-panel", "style") for sid, _, _, _, _ in norm]
        sid_list_js = "[" + ",".join(f'"{sid}"' for sid, _, _, _, _ in norm) + "]"
        clientside_callback(
            f"""function() {{
                var args = arguments;
                var n = {len(norm)};
                var sids = {sid_list_js};
                var nu = window.dash_clientside.no_update;
                var ctx = window.dash_clientside.callback_context;
                var trig = (ctx.triggered && ctx.triggered[0]) ? ctx.triggered[0].prop_id : "";
                var out = [];
                for (var i = 0; i < n; i++) {{
                    if (trig.indexOf(sids[i] + '-settings-btn') === 0) {{
                        var curStyle = args[n + i] || {{}};
                        var hidden = (curStyle && curStyle.display === 'none');
                        out.push(Object.assign({{}}, curStyle, {{display: hidden ? 'block' : 'none'}}));
                    }} else {{
                        out.push(nu);
                    }}
                }}
                return out;
            }}""",
            *toggle_outputs,
            *toggle_inputs,
            *toggle_states,
            prevent_initial_call=True,
        )

        # ----- PNG export: one callback for all charts -----
        export_inputs = [Input(f"{sid}-settings-export", "n_clicks") for sid, _, _, _, _ in norm]
        export_states = [State(gid, "id") for _, gid, _, _, _ in norm]
        export_outputs = [Output(f"{sid}-settings-export", "n_clicks") for sid, _, _, _, _ in norm]
        clientside_callback(
            f"""function() {{
                var args = arguments;
                var n = {len(norm)};
                var sids = {sid_list_js};
                var nu = window.dash_clientside.no_update;
                var ctx = window.dash_clientside.callback_context;
                var trig = (ctx.triggered && ctx.triggered[0]) ? ctx.triggered[0].prop_id : "";
                var out = new Array(n).fill(nu);
                for (var i = 0; i < n; i++) {{
                    if (trig.indexOf(sids[i] + '-settings-export') === 0) {{
                        var gid = args[n + i];
                        if (gid && window.dash_clientside.chartExport) {{
                            window.dash_clientside.chartExport.exportPng(args[i], gid);
                        }}
                        return out;
                    }}
                }}
                return out;
            }}""",
            *export_outputs,
            *export_inputs,
            *export_states,
            prevent_initial_call=True,
        )

    # ----- Stack-wrap + smooth-wrap visibility -----
    # Kept as PER-CHART callbacks (not batched) because stack-wrap / smooth-wrap
    # DOM elements only exist when chart_card was built with show_grouping=True
    # or show_smooth=True. Multi-output batched callbacks can't tolerate
    # missing targets, but single-output ones can via suppress_callback_exceptions.
    for sid, _gid, store_id, show_grouping, show_smooth in norm:
        if not store_id:
            continue
        if show_grouping:
            clientside_callback(
                """function(chartType) {
                    return chartType === "line" ? {"display": "none"} : {"display": ""};
                }""",
                Output(f"{sid}-settings-stack-wrap", "style"),
                Input(f"{sid}-settings-type", "value"),
            )
        if show_smooth:
            clientside_callback(
                """function(chartType) {
                    return chartType === "bar" ? {"display": "none"} : {"display": ""};
                }""",
                Output(f"{sid}-settings-smooth-wrap", "style"),
                Input(f"{sid}-settings-type", "value"),
            )
