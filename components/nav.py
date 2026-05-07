"""Sidebar navigation component with grouped sections."""

import dash_mantine_components as dmc
from dash import callback, html, Input, Output
from dash_iconify import DashIconify

from config.settings import NAV_SECTIONS, NEUTRAL


def _create_nav_link(page, active_path):
    """Create a single nav link."""
    is_active = page["path"] == active_path
    return dmc.NavLink(
        label=page["label"],
        href=page["path"],
        leftSection=DashIconify(icon=page["icon"], width=18, color="currentColor"),
        active=is_active,
        variant="subtle",
        color="white",
        className="nav-link-item nav-link-active" if is_active else "nav-link-item",
        styles={
            "root": {
                "borderRadius": "6px",
                "marginBottom": "2px",
                "padding": "4px 8px 4px 12px",
                "minHeight": "unset",
                "color": "var(--sidebar-text)",
            },
            "label": {"color": "var(--sidebar-text)", "fontWeight": "700" if is_active else "400", "fontSize": "13px"},
        },
    )


def _create_section_header(section_name):
    """Create a section header label."""
    return dmc.Text(
        section_name,
        size="xs",
        fw=600,
        c="var(--sidebar-text-muted)",
        pl=12,
        pt=10,
        pb=3,
        style={"letterSpacing": "0.5px"},
    )


def _build_nav_items(active_path):
    """Build all nav items with section headers."""
    items = []
    for section in NAV_SECTIONS:
        # Add section header (skip for OVERVIEW to keep Home at top without label)
        if section["section"] != "OVERVIEW":
            items.append(_create_section_header(section["section"]))
        # Add page links
        for page in section["pages"]:
            items.append(_create_nav_link(page, active_path))
    return items


def create_sidebar():
    """Create the sidebar navigation."""
    return dmc.AppShellNavbar(
        children=[
            dmc.Stack(
                gap=0,
                children=[
                    # Brand header with logo — themes to match sidebar
                    dmc.Group(
                        children=[
                            html.A(
                                html.Img(
                                    src="/assets/radiantcare.png",
                                    style={"height": "38px", "objectFit": "contain"},
                                ),
                                href="https://radiantcare.app",
                                target="_blank",
                                style={"display": "inline-flex", "alignItems": "center"},
                            ),
                        ],
                        gap="sm",
                        pl=12,
                        pr="md",
                        py="md",
                        justify="flex-start",
                        style={
                            "backgroundColor": "var(--bg-sidebar-header)",
                            "borderBottom": "1px solid var(--sidebar-border)",
                        },
                    ),
                    # Navigation links
                    dmc.ScrollArea(
                        id="nav-scroll-area",
                        type="scroll",
                        offsetScrollbars=True,
                        style={"flex": 1},
                        children=dmc.Stack(
                            id="nav-links",
                            gap=0,
                            px="xs",
                            pt="md",
                            pb="md",
                        ),
                    ),
                    # Bottom section — pinned below the scrollable nav.
                    # Divider + soft top-shadow give it the "raised sticky
                    # footer" cue so on short viewports (where the nav
                    # scrolls) the Help button reads as a separate region
                    # instead of just the next item in the list.
                    dmc.Stack(
                        gap=2,
                        px="xs",
                        py=8,
                        style={
                            "borderTop": "1px solid rgba(255, 255, 255, 0.22)",
                            "boxShadow": "0 -6px 10px -6px rgba(0, 0, 0, 0.35)",
                            # Use the sidebar bg explicitly so the shadow
                            # casts onto the section above (rather than
                            # showing through transparency).
                            "backgroundColor": "var(--bg-sidebar)",
                            "position": "relative",
                            "zIndex": 1,
                        },
                        children=[
                            dmc.NavLink(
                                label="Help",
                                leftSection=DashIconify(
                                    icon="tabler:help-circle", width=18, color="currentColor"
                                ),
                                variant="subtle",
                                color="white",
                                id="nav-help-btn",
                                className="nav-link-item",
                                styles={
                                    "root": {
                                        "borderRadius": "6px",
                                        "padding": "4px 8px 4px 12px",
                                        "minHeight": "unset",
                                        "color": "var(--sidebar-text)",
                                    },
                                    "label": {"color": "var(--sidebar-text)", "fontSize": "13px"},
                                },
                            ),
                        ],
                    ),
                ],
                style={"height": "100%"},
            ),
        ],
        style={
            "backgroundColor": "var(--bg-sidebar)",
            "borderRight": "1px solid var(--sidebar-border)",
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
    return _build_nav_items(pathname)
