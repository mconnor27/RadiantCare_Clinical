"""Sidebar navigation component."""

import dash_mantine_components as dmc
from dash import callback, html, Input, Output, State
from dash_iconify import DashIconify

from config.settings import NAV_PAGES, PRIMARY, NEUTRAL


def create_nav_link(page, active_path):
    """Create a single nav link."""
    is_active = page["path"] == active_path
    text_color = "#1A1A2E" if is_active else "white"
    icon_color = "#1A1A2E" if is_active else "white"
    return dmc.NavLink(
        label=page["label"],
        href=page["path"],
        leftSection=DashIconify(icon=page["icon"], width=20, color=icon_color),
        active=is_active,
        variant="filled" if is_active else "subtle",
        color="white",
        styles={
            "root": {
                "borderRadius": "6px",
                "marginBottom": "2px",
                "color": text_color,
                "backgroundColor": "rgba(255,255,255,0.2)" if is_active else "transparent",
            },
            "label": {"color": text_color, "fontWeight": "600" if is_active else "400"},
        },
    )


def create_sidebar():
    """Create the sidebar navigation."""
    return dmc.AppShellNavbar(
        children=[
            dmc.Stack(
                gap="xs",
                children=[
                    # Brand header with logo — white background
                    dmc.Group(
                        children=[
                            html.Img(
                                src="/assets/radiantcare.png",
                                style={"height": "32px", "objectFit": "contain"},
                            ),
                        ],
                        gap="sm",
                        px="md",
                        py="md",
                        justify="center",
                        style={
                            "backgroundColor": "#FFFFFF",
                            "borderBottom": "1px solid #E0E0E0",
                        },
                    ),
                    # Navigation links
                    dmc.Stack(
                        id="nav-links",
                        gap=2,
                        px="xs",
                        py="sm",
                        style={"flex": 1, "overflowY": "auto"},
                    ),
                    # Bottom section
                    dmc.Divider(color=NEUTRAL["bg_nav_hover"]),
                    dmc.Stack(
                        gap=2,
                        px="xs",
                        py="sm",
                        children=[
                            dmc.NavLink(
                                label="Help",
                                leftSection=DashIconify(
                                    icon="tabler:help-circle", width=20, color="white"
                                ),
                                variant="subtle",
                                color="white",
                                id="nav-help-btn",
                                styles={
                                    "root": {"borderRadius": "6px", "color": "white"},
                                    "label": {"color": "white"},
                                },
                            ),
                        ],
                    ),
                ],
                style={"height": "100%"},
            ),
        ],
        style={
            "backgroundColor": NEUTRAL["bg_nav"],
        },
    )


@callback(
    Output("nav-links", "children"),
    Input("_pages_location", "pathname"),
)
def update_nav_links(pathname):
    """Update nav links to reflect the active page."""
    if pathname is None:
        pathname = "/"
    return [create_nav_link(page, pathname) for page in NAV_PAGES]
