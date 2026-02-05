"""RadiantCare Clinical Dashboard — main application entry point."""

import dash
import dash_mantine_components as dmc
from dash import Dash, html, dcc, page_container

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
        dmc.AppShell(
            children=[
                create_sidebar(),
                dmc.AppShellMain(
                    children=[
                        # Page title row
                        dmc.Group(
                            id="page-title-row",
                            justify="space-between",
                            mb="md",
                        ),
                        page_container,
                    ],
                    style={
                        "backgroundColor": NEUTRAL["bg_page"],
                        "minHeight": "100vh",
                        "padding": "24px",
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
    app.run(debug=True, port=8050)
