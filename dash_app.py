"""RadiantCare Clinical Dashboard — main application entry point."""

import dash
import dash_mantine_components as dmc
from dash import Dash, html, dcc, page_container, callback, Input, Output, no_update
from dash_iconify import DashIconify

from config.settings import DMC_THEME, NEUTRAL, PRIMARY, MAPBOX_TOKEN
from components.nav import create_sidebar

# ---------------------------------------------------------------------------
# App initialization
# ---------------------------------------------------------------------------
app = Dash(
    __name__,
    use_pages=True,
    suppress_callback_exceptions=True,
    title="RadiantCare Clinical",
    update_title="Loading...",
)
server = app.server  # for gunicorn

# Set Mapbox token globally
if MAPBOX_TOKEN:
    import plotly
    plotly.express.set_mapbox_access_token(MAPBOX_TOKEN)

# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------
app.layout = dmc.MantineProvider(
    theme=DMC_THEME,
    children=[
        # Global loading overlay — managed by assets/loading.js
        html.Div(
            id="global-loading-overlay",
            children=[
                html.Div(
                    children=[
                        dmc.Loader(color=PRIMARY, size="xl", type="dots"),
                        dmc.Text(
                            "Loading data\u2026",
                            c=NEUTRAL["text_secondary"],
                            size="lg",
                            mt="md",
                            fw=500,
                        ),
                    ],
                    style={
                        "display": "flex",
                        "flexDirection": "column",
                        "alignItems": "center",
                        "padding": "48px 72px",
                        "backgroundColor": "white",
                        "borderRadius": "16px",
                        "boxShadow": "0 8px 32px rgba(0,0,0,0.15)",
                    },
                ),
            ],
            style={
                "position": "fixed",
                "top": 0,
                "left": 220,
                "right": 0,
                "height": "100vh",
                "backgroundColor": NEUTRAL["bg_page"],
                "display": "flex",
                "alignItems": "center",
                "justifyContent": "center",
                "zIndex": 9999,
            },
        ),
        # Refresh data button — fixed top-right corner
        dmc.ActionIcon(
            DashIconify(icon="tabler:refresh", width=20),
            id="global-refresh-btn",
            variant="subtle",
            color="gray",
            size="lg",
            radius="xl",
            style={
                "position": "fixed",
                "top": 10,
                "right": 16,
                "zIndex": 1000,
            },
        ),
        # Hidden div to trigger page reload via clientside callback
        html.Div(id="global-refresh-trigger", style={"display": "none"}),
        dmc.AppShell(
            children=[
                create_sidebar(),
                dmc.AppShellMain(
                    children=[page_container],
                    style={
                        "backgroundColor": NEUTRAL["bg_page"],
                        "minHeight": "100vh",
                        "padding": "12px 24px 12px 24px",
                    },
                ),
            ],
            navbar={
                "width": {"base": 220, "sm": 220},
                "breakpoint": "sm",
            },
            layout="default",
            padding="md",
        ),
    ],
)

# ---------------------------------------------------------------------------
# Refresh-data callback — clears LRU caches, then reloads the page
# ---------------------------------------------------------------------------
@callback(
    Output("global-refresh-trigger", "children"),
    Input("global-refresh-btn", "n_clicks"),
    prevent_initial_call=True,
)
def _refresh_data(_n):
    from data.loader import clear_cache
    clear_cache()
    return ""

app.clientside_callback(
    """function(children) { location.reload(); return window.dash_clientside.no_update; }""",
    Output("global-refresh-btn", "loading"),
    Input("global-refresh-trigger", "children"),
    prevent_initial_call=True,
)

# ---------------------------------------------------------------------------
# Pre-load heavy datasets in background so the cache is warm before the
# first page visit.  Treatment Detail is by far the largest (~3 s cold).
# ---------------------------------------------------------------------------
import threading

def _preload():
    from data.loader import load_treatment_detail
    load_treatment_detail()

threading.Thread(target=_preload, daemon=True).start()

# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    app.run(debug=True, port=8050, host="localhost")
