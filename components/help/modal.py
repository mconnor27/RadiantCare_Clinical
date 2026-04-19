"""Help modal shell — sidebar (pages) + right-hand content with SQL/UI tabs."""

from __future__ import annotations

import importlib

import dash_mantine_components as dmc
from dash import ALL, Input, Output, State, callback, callback_context, dcc, html, no_update
from dash_iconify import DashIconify

from config.settings import NEUTRAL, PRIMARY
from .registry import HELP_PAGES_BY_PATH, grouped_pages
from .renderers import help_tabs, sql_tab


# ---------------------------------------------------------------------------
# Content loader — dynamically imports the right content module
# ---------------------------------------------------------------------------

def _load_content(module_name: str):
    """Import components.help.content.<module_name>.

    A content module either defines:
      - `TABS`: a list of custom tab specs (overrides the standard layout),
        used by the Overview entry; OR
      - `UI_CONTENT`: the standard UI-tab content; SQL tab comes from the
        registry.
    """
    return importlib.import_module(f"components.help.content.{module_name}")


def _render_custom_tabs(tabs_spec: list[dict]) -> dmc.Tabs:
    """Render a `TABS` spec from a content module."""
    return dmc.Tabs(
        value=tabs_spec[0]["value"],
        children=[
            dmc.TabsList(
                children=[
                    dmc.TabsTab(
                        t["label"],
                        value=t["value"],
                        leftSection=DashIconify(icon=t["icon"], width=16),
                    )
                    for t in tabs_spec
                ],
            ),
            *[
                dmc.TabsPanel(value=t["value"], pt="md", children=t["content"])
                for t in tabs_spec
            ],
        ],
    )


def _render_page_content(path: str):
    """Build the full tabs content for a given page path."""
    entry = HELP_PAGES_BY_PATH.get(path)
    if entry is None:
        return help_tabs(
            sql_content=dmc.Text(
                "No help entry is registered for this page.",
                size="sm", c="dimmed",
            ),
            ui_content=dmc.Text(
                "Documentation for this page is coming soon.",
                size="sm", c="dimmed",
            ),
        )

    mod = _load_content(entry["ui_module"])

    # Dynamic tabs builder (used by Data Sources) — re-runs per render so
    # filesystem state is live. Takes precedence over static TABS / UI_CONTENT.
    build_tabs_fn = getattr(mod, "build_tabs", None)
    if callable(build_tabs_fn):
        return _render_custom_tabs(build_tabs_fn())

    # Custom tabs (used by Overview) take precedence over the standard layout.
    custom_tabs = getattr(mod, "TABS", None)
    if custom_tabs:
        return _render_custom_tabs(custom_tabs)

    ui_content = getattr(mod, "UI_CONTENT")

    if entry["sql"]:
        sql_content = sql_tab(entry["sql"], intro=entry.get("sql_intro"))
    else:
        sql_content = dmc.Text(
            "This page is derived from multiple non-dedicated sources. "
            "See individual per-page help entries for details on the "
            "underlying extracts.",
            size="sm", c="dimmed",
        )

    return help_tabs(sql_content=sql_content, ui_content=ui_content)


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

def _sidebar_item(page: dict, active_path: str) -> html.Div:
    """One clickable page entry in the modal sidebar."""
    is_active = page["path"] == active_path
    return html.Div(
        id={"type": "help-sidebar-item", "path": page["path"]},
        n_clicks=0,
        children=dmc.Group(
            gap="xs",
            wrap="nowrap",
            children=[
                DashIconify(
                    icon=page["icon"],
                    width=16,
                    color=PRIMARY if is_active else NEUTRAL["text_secondary"],
                ),
                dmc.Text(
                    page["label"],
                    size="sm",
                    fw=600 if is_active else 400,
                    c=PRIMARY if is_active else NEUTRAL["text_primary"],
                ),
            ],
        ),
        style={
            "padding": "6px 10px",
            "borderRadius": "6px",
            "cursor": "pointer",
            "backgroundColor": "var(--bg-hover)" if is_active else "transparent",
            "marginBottom": "2px",
            "userSelect": "none",
        },
        className="help-sidebar-item",
    )


def _sidebar_section_header(name: str) -> dmc.Text:
    return dmc.Text(
        name,
        size="xs", fw=600,
        c=NEUTRAL["text_muted"],
        pl=10, pt=12, pb=4,
        style={"letterSpacing": "0.5px"},
    )


def _build_sidebar(active_path: str) -> list:
    items: list = []
    for section_name, pages in grouped_pages():
        items.append(_sidebar_section_header(section_name))
        for page in pages:
            items.append(_sidebar_item(page, active_path))
    return items


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------

def create_help_modal():
    """Return the global help modal component (add to app layout)."""
    return dmc.Modal(
        id="help-modal",
        opened=False,
        title=dmc.Group(
            gap="xs",
            children=[
                DashIconify(icon="tabler:help-circle", width=22, color=PRIMARY),
                dmc.Text("Help & Methodology", fw=600, size="lg"),
            ],
        ),
        size="85%",
        centered=True,
        zIndex=1000,
        styles={
            "header": {"padding": "10px 16px"},
            "content": {"height": "92vh", "display": "flex", "flexDirection": "column"},
            "body": {"padding": "0px 0px 0px 0px", "flex": 1, "overflow": "hidden"},
        },
        children=[
            # Tracks the currently selected help page inside the modal.
            dcc.Store(id="help-modal-active-path", data="/"),

            html.Div(
                style={"display": "flex", "height": "100%", "minHeight": 0},
                children=[
                    # --- Sidebar -----------------------------------------
                    html.Div(
                        style={
                            "width": "230px",
                            "flexShrink": 0,
                            "borderRight": f"1px solid {NEUTRAL['border']}",
                            "backgroundColor": "var(--bg-card-alt)",
                            "overflowY": "auto",
                            "overflowX": "hidden",
                        },
                        children=dmc.Stack(
                            id="help-modal-sidebar",
                            gap=0,
                            px="xs",
                            py="sm",
                        ),
                    ),
                    # --- Content -----------------------------------------
                    html.Div(
                        style={
                            "flex": 1,
                            "minWidth": 0,
                            "overflowY": "auto",
                            "padding": "16px 20px",
                        },
                        children=dcc.Loading(
                            id="help-modal-loading",
                            type="circle",
                            color=PRIMARY,
                            delay_show=150,
                            children=html.Div(id="help-modal-content"),
                        ),
                    ),
                ],
            ),
        ],
    )


# ---------------------------------------------------------------------------
# Callbacks
# ---------------------------------------------------------------------------

@callback(
    Output("help-modal", "opened"),
    Output("help-modal-active-path", "data"),
    Input("nav-help-btn", "n_clicks"),
    State("_pages_location", "pathname"),
    State("help-modal", "opened"),
    prevent_initial_call=True,
)
def _open_help(n_clicks, pathname, already_open):
    """Open the modal to the current page's help entry."""
    if not n_clicks:
        return already_open, pathname or "/"
    target = pathname if pathname in HELP_PAGES_BY_PATH else "/"
    return True, target


@callback(
    Output("help-modal-active-path", "data", allow_duplicate=True),
    Input({"type": "help-sidebar-item", "path": ALL}, "n_clicks"),
    prevent_initial_call=True,
)
def _switch_page(n_clicks_list):
    """Clicking a sidebar item updates the active help path."""
    if not callback_context.triggered or not any(n_clicks_list or []):
        return no_update

    triggered = callback_context.triggered_id
    if isinstance(triggered, dict) and triggered.get("type") == "help-sidebar-item":
        return triggered["path"]
    return no_update


@callback(
    Output("help-modal-sidebar", "children"),
    Output("help-modal-content", "children"),
    Input("help-modal-active-path", "data"),
)
def _render_modal(active_path):
    """Render sidebar (with active highlighting) and content pane."""
    active_path = active_path or "/"
    return _build_sidebar(active_path), _render_page_content(active_path)
