"""'Cancellations by Notice' card shared by Simulations and Clinic Visits.

Stacked bars of cancellations bucketed by how much notice was given, stacked
by what happened to the vacated slot. Figure is built server-side by
utils.cancellations.build_notice_figure; this module only provides layout.

IDs (p = page prefix, e.g. "sim" / "cv"):
    {p}-chart-cancel-notice     dcc.Graph
    {p}-cancel-notice-mode      "count" | "pct"
    {p}-cancel-notice-edges     bucket edges as tags ("4h", "3d", "1w", …)
    {p}-cancel-notice-summary   one-line summary text
    {p}-cancel-notice-loading   LoadingOverlay

cancel_addon_settings(p) returns the add-on controls for the trend card's gear
menu (they drive both cancellation charts):
    {p}-cancel-addon-mode       "include" | "exclude"
    {p}-cancel-addon-days       short-notice cutoff, business days (blank = off)
    {p}-cancel-addon-template   bool — off-template start times count as add-ons
"""

import dash_mantine_components as dmc
from dash import dcc
from dash_iconify import DashIconify

from config.settings import CHART_PAPER_HEIGHT
from utils.cancellations import (
    ADDON_DEFAULT_DAYS, DEFAULT_NOTICE_EDGES, NOTICE_EDGE_SUGGESTIONS,
)


def cancel_addon_settings(p):
    """Gear-menu controls for add-on handling (both cancellation charts)."""
    label = {"size": "xs", "fw": 500, "c": "#6B7280"}
    return [
        dmc.Stack(gap=4, children=[
            dmc.Group(gap=4, wrap="nowrap", children=[
                dmc.Text("Add-on Appointments", **label),
                dmc.Tooltip(
                    label="Add-ons are squeezed in outside normal capacity — "
                          "booked at short notice or at an unusual start time "
                          "(e.g. over lunch, late in the day). Cancelling one "
                          "doesn't free a slot that was really on offer. "
                          "Include splits Lost hours into Regular vs Add-on; "
                          "Exclude drops add-ons from both cancellation charts.",
                    multiline=True, w=260, withArrow=True, position="left",
                    zIndex=1000,
                    children=DashIconify(icon="mdi:information-outline", width=13,
                                         color="#9CA3AF", style={"cursor": "help"}),
                ),
            ]),
            dmc.SegmentedControl(
                id=f"{p}-cancel-addon-mode",
                data=[{"value": "include", "label": "Include"},
                      {"value": "exclude", "label": "Exclude"}],
                value="include", size="xs", fullWidth=True,
            ),
        ]),
        dmc.Stack(gap=4, children=[
            dmc.Text("Add-on If Booked Within (Business Days)", **label),
            dmc.NumberInput(
                id=f"{p}-cancel-addon-days",
                value=ADDON_DEFAULT_DAYS, min=0, max=10, step=1,
                allowDecimal=False, size="xs",
                placeholder="Off",
            ),
        ]),
        dmc.Switch(
            id=f"{p}-cancel-addon-template",
            label="Off-template start times are add-ons",
            checked=True, size="xs",
        ),
    ]


def cancel_notice_card(p, height=CHART_PAPER_HEIGHT):
    return dmc.Paper(
        children=[
            dmc.Group(
                justify="space-between", mb=4, gap="sm", wrap="nowrap",
                children=[
                    dmc.Group(gap=6, wrap="nowrap", children=[
                        dmc.Text("Cancellations by Notice", size="sm", fw=500, c="#6B7280",
                                 style={"whiteSpace": "nowrap"}),
                        dmc.Tooltip(
                            label="Bucket edges — type a value and press Enter "
                                  "(e.g. 4h, 2d, 1w; a bare number = hours). "
                                  "Clear all to reset to 24h / 3d / 7d.",
                            position="top-start", withArrow=True, multiline=True, w=260,
                            children=DashIconify(icon="mdi:information-outline", width=15,
                                                 color="#9CA3AF", style={"cursor": "help"}),
                        ),
                    ]),
                    # Edges fill all space between title and toggle. Not wrapped
                    # in a Tooltip — the wrapper shrinks it to content width.
                    dmc.TagsInput(
                        id=f"{p}-cancel-notice-edges",
                        value=list(DEFAULT_NOTICE_EDGES),
                        data=NOTICE_EDGE_SUGGESTIONS,
                        placeholder="Add edge",
                        splitChars=[",", " "],
                        acceptValueOnBlur=True,
                        clearable=True,
                        size="xs",
                        style={"flex": "1 1 0", "minWidth": 0},
                        leftSection=DashIconify(icon="mdi:timer-outline", width=14),
                        styles={"inputField": {"minWidth": "4rem", "flex": "1 1 4rem"}},
                        comboboxProps={"zIndex": 500, "offset": 2},
                        maxDropdownHeight=240,
                    ),
                    dmc.SegmentedControl(
                        id=f"{p}-cancel-notice-mode",
                        data=[
                            {"value": "count", "label": "#"},
                            {"value": "pct", "label": "%"},
                        ],
                        value="count",
                        size="xs",
                        style={"flexShrink": 0},
                    ),
                ],
            ),
            dmc.Text(id=f"{p}-cancel-notice-summary", size="xs", c="dimmed", mb=4,
                     style={"minHeight": 18}),
            dmc.Box(
                pos="relative",
                style={"flex": "1", "minHeight": 0},
                children=[
                    dmc.Box(
                        style={"position": "absolute", "top": 0, "left": 0, "right": 0, "bottom": 0},
                        children=[
                            dmc.LoadingOverlay(
                                id=f"{p}-cancel-notice-loading", visible=False,
                                loaderProps={"type": "dots", "color": "#7C2A83"},
                                transitionProps={"duration": 600, "exitDuration": 80},
                            ),
                            dcc.Graph(id=f"{p}-chart-cancel-notice",
                                      config={"displayModeBar": False},
                                      style={"height": "100%"}),
                        ],
                    ),
                ],
            ),
        ],
        p="sm", pb=8, radius="md", shadow="xs", withBorder=True,
        h=height, style={"display": "flex", "flexDirection": "column"},
    )
