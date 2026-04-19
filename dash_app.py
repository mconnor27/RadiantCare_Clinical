"""RadiantCare Clinical Dashboard — main application entry point."""

import os

import dash
import dash_mantine_components as dmc
from dash import Dash, html, dcc, page_container, callback, Input, Output, State, no_update
from dash_iconify import DashIconify

from dash import clientside_callback

from config.settings import DMC_THEME, NEUTRAL, PRIMARY, MAPBOX_TOKEN, PHI_MODE
from components.nav import create_sidebar
from components.help_modal import create_help_modal
from utils.diagnosis_categories import get_taxonomy

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

# Optional Supabase-Auth gating. Set AUTH_ENABLED=true in production
# (and provide FLASK_SECRET, SUPABASE_URL, SUPABASE_ANON_KEY).
if os.environ.get("AUTH_ENABLED", "").lower() in ("1", "true", "yes", "on"):
    from auth import register_auth
    register_auth(server)

# Inject theme-init script into <head> so data-theme is applied BEFORE render
# (prevents flash of light content when dark mode is the user's saved preference).
app.index_string = """<!DOCTYPE html>
<html>
    <head>
        {%metas%}
        <title>{%title%}</title>
        {%favicon%}
        {%css%}
        <script>
            (function() {
                try {
                    var saved = localStorage.getItem('rc_theme') || 'light';
                    document.documentElement.setAttribute('data-theme', saved);
                    document.documentElement.setAttribute('data-mantine-color-scheme', saved);
                } catch(e) {}
            })();
        </script>
    </head>
    <body>
        {%app_entry%}
        <footer>
            {%config%}
            {%scripts%}
            {%renderer%}
        </footer>
    </body>
</html>"""


# Disable browser caching for JS/CSS assets during development
from flask import request as _flask_request


@server.after_request
def _no_cache(response):
    if _flask_request.path.startswith("/assets/"):
        response.headers["Cache-Control"] = "no-store"
    return response


# Set Mapbox token globally
if MAPBOX_TOKEN:
    import plotly.express
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
                        "backgroundColor": "var(--bg-card)",
                        "borderRadius": "16px",
                        "boxShadow": "var(--shadow-md)",
                    },
                ),
            ],
            style={
                "position": "fixed",
                "top": 0,
                "left": 220,
                "right": 0,
                "height": "100vh",
                "backgroundColor": "var(--bg-page)",
                "display": "flex",
                "alignItems": "center",
                "justifyContent": "center",
                "zIndex": 9999,
            },
        ),
        # Theme toggle + refresh buttons — fixed top-right corner
        html.Div(
            style={
                "position": "fixed",
                "top": 10,
                "right": 16,
                "zIndex": 1000,
                "display": "flex",
                "gap": "4px",
                "alignItems": "center",
            },
            children=[
                *(
                    [dmc.Badge(
                        "De-Identified",
                        leftSection=DashIconify(icon="tabler:shield-lock", width=12),
                        color="violet",
                        variant="light",
                        size="sm",
                        radius="sm",
                        style={"marginRight": "4px"},
                    )]
                    if PHI_MODE else []
                ),
                dmc.ActionIcon(
                    DashIconify(id="global-theme-icon", icon="tabler:moon", width=22, color="#4B5563"),
                    id="global-theme-btn",
                    variant="transparent",
                    size="lg",
                    radius="xl",
                ),
                dmc.ActionIcon(
                    DashIconify(icon="tabler:refresh", width=20),
                    id="global-refresh-btn",
                    variant="subtle",
                    color="gray",
                    size="lg",
                    radius="xl",
                ),
                # Signed-in user chip — populated by a server callback from
                # flask.session. Empty div when auth is off / not logged in.
                html.Div(id="auth-user-chip", style={"marginLeft": "4px"}),
            ],
        ),
        # Theme state store (synced to localStorage via clientside)
        dcc.Store(id="global-theme-store", data="light"),
        # Global help modal
        create_help_modal(),
        # Hidden div to trigger page reload via clientside callback
        html.Div(id="global-refresh-trigger", style={"display": "none"}),
        # Diagnosis taxonomy store — populates window._diagTaxonomy for JS
        dcc.Store(id="global-diag-taxonomy", data=get_taxonomy()),
        dmc.AppShell(
            children=[
                create_sidebar(),
                dmc.AppShellMain(
                    children=[page_container],
                    style={
                        "backgroundColor": "var(--bg-page)",
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
        # Preload status bar (bottom of page, auto-hides when done)
        html.Div(id="preload-status-bar", style={"display": "none"}),
        dcc.Interval(id="preload-interval", interval=500, n_intervals=0),
        dcc.Store(id="preload-priority-trigger"),
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

# Populate window._diagTaxonomy from the Store so JS dropdown functions can read it
app.clientside_callback(
    """function(taxonomy) {
        window._diagTaxonomy = taxonomy || {};
        return window.dash_clientside.no_update;
    }""",
    Output("global-diag-taxonomy", "id"),
    Input("global-diag-taxonomy", "data"),
)

# ---------------------------------------------------------------------------
# Theme toggle — clientside (reads/writes localStorage, flips data-theme
# attributes on <html>, updates icon). Initial state seeded from localStorage
# via the index_string <head> script so the first paint matches the saved theme.
# ---------------------------------------------------------------------------
app.clientside_callback(
    """function(n_clicks, current) {
        // On first load (n_clicks is None/0), read localStorage and seed store.
        var saved = null;
        try { saved = localStorage.getItem('rc_theme'); } catch(e) {}

        var next;
        if (!n_clicks) {
            next = saved || current || 'light';
        } else {
            next = (current === 'dark') ? 'light' : 'dark';
        }

        document.documentElement.setAttribute('data-theme', next);
        document.documentElement.setAttribute('data-mantine-color-scheme', next);
        try { localStorage.setItem('rc_theme', next); } catch(e) {}

        var icon = (next === 'dark') ? 'tabler:sun' : 'tabler:moon';
        return [next, icon];
    }""",
    [Output("global-theme-store", "data"),
     Output("global-theme-icon", "icon")],
    Input("global-theme-btn", "n_clicks"),
    State("global-theme-store", "data"),
)

# ---------------------------------------------------------------------------
# Page-aware preload with progress tracking
# ---------------------------------------------------------------------------
import threading

# Map page paths to dataset loader names they need
_PAGE_DATASETS = {
    "/":                ["daily_volume", "treatment_detail", "clinic_visits", "simulations", "availability"],
    "/operations":      ["daily_volume", "daily_volume_future", "treatment", "clinic_visits", "simulations"],
    "/workflow":        ["workflow"],
    "/clinic-visits":   ["clinic_visits", "diagnosis"],
    "/simulations":     ["simulations", "diagnosis"],
    "/tasks":           ["tasks", "diagnosis"],
    "/otvs":            ["weekly_visits"],
    "/billing":         ["billing", "rvu_lookup", "patients"],
    "/treatment":       ["treatment_detail"],
    "/courses":         ["courses", "diagnosis"],
    "/plans":           ["plans", "diagnosis"],
    "/procedures":      ["procedures", "workflow"],
    "/machines":        ["machines"],
    "/machine-statistics": ["machine_statistics"],
    "/patients":        ["treatment_detail", "referrals"],
    "/referrals":       ["referrals", "referring"],
    "/diagnosis":       ["clinic_visits", "diagnosis"],
    "/physicians":      ["physician_schedule"],
    "/cpt-audit":       ["cpt_audit"],
    "/otv-audit":       ["weekly_visits"],
}

# All loaders keyed by name
def _get_all_loaders():
    from data.loader import (
        load_treatment_detail, load_billing, load_workflow,
        load_referrals, load_daily_volume, load_daily_volume_future,
        load_clinic_visits, load_simulations, load_tasks, load_courses,
        load_plans, load_weekly_visits, load_rvu_lookup,
        load_treatment, load_availability, load_machines,
        load_machine_statistics, load_procedures, load_patients,
        load_referring, load_diagnosis, load_physician_schedule,
        load_cpt_audit, load_otvs,
    )
    return {
        "treatment_detail": load_treatment_detail,
        "billing": load_billing,
        "workflow": load_workflow,
        "referrals": load_referrals,
        "daily_volume": load_daily_volume,
        "daily_volume_future": load_daily_volume_future,
        "clinic_visits": load_clinic_visits,
        "simulations": load_simulations,
        "tasks": load_tasks,
        "courses": load_courses,
        "plans": load_plans,
        "weekly_visits": load_weekly_visits,
        "rvu_lookup": load_rvu_lookup,
        "treatment": load_treatment,
        "availability": load_availability,
        "machines": load_machines,
        "machine_statistics": load_machine_statistics,
        "procedures": load_procedures,
        "patients": load_patients,
        "referring": load_referring,
        "diagnosis": load_diagnosis,
        "physician_schedule": load_physician_schedule,
        "cpt_audit": load_cpt_audit,
        "otvs": load_otvs,
    }


# Preload state: tracks loaded datasets, current activity, and priority queue
_preload_state = {
    "loaded": set(),
    "total": 12,  # heavy datasets count
    "current": None,
    "done": False,
}
_preload_lock = threading.Lock()
_priority_queue = []  # datasets to load next (set by page navigation)

# Heavy datasets to preload (ordered by load time, heaviest first)
_PRELOAD_ORDER = [
    "treatment_detail", "billing", "referrals", "workflow",
    "daily_volume", "clinic_visits", "simulations", "tasks",
    "courses", "plans", "weekly_visits", "rvu_lookup",
]


def _load_dataset(name, loaders):
    """Load a single dataset and update state."""
    if name in _preload_state["loaded"]:
        return
    with _preload_lock:
        _preload_state["current"] = name
    try:
        loaders[name]()
    except Exception:
        pass
    with _preload_lock:
        _preload_state["loaded"].add(name)
        _preload_state["current"] = None


def _preload():
    """Background preload: respects priority queue, then loads remaining."""
    loaders = _get_all_loaders()
    remaining = list(_PRELOAD_ORDER)

    while remaining:
        # Check priority queue first
        with _preload_lock:
            if _priority_queue:
                name = _priority_queue.pop(0)
            else:
                name = None

        if name and name in remaining:
            _load_dataset(name, loaders)
            remaining = [r for r in remaining if r not in _preload_state["loaded"]]
            continue

        if name is None and remaining:
            _load_dataset(remaining[0], loaders)
            remaining = [r for r in remaining if r not in _preload_state["loaded"]]

    with _preload_lock:
        _preload_state["done"] = True
        _preload_state["current"] = None


threading.Thread(target=_preload, daemon=True).start()


# --- Status bar polling callback ---

@callback(
    Output("preload-status-bar", "children"),
    Output("preload-status-bar", "style"),
    Output("preload-interval", "disabled"),
    Input("preload-interval", "n_intervals"),
)
def _update_preload_status(_n):
    with _preload_lock:
        done = _preload_state["done"]
        loaded = len(_preload_state["loaded"])
        total = _preload_state["total"]
        current = _preload_state["current"]

    if done:
        return "", {"display": "none"}, True

    label = current.replace("_", " ").title() if current else "..."
    text = f"Loading data: {label} ({loaded}/{total})"
    bar_style = {
        "position": "fixed",
        "bottom": 0,
        "left": 220,
        "right": 0,
        "height": "28px",
        "backgroundColor": "var(--bg-hover)",
        "borderTop": "1px solid var(--border-tint)",
        "display": "flex",
        "alignItems": "center",
        "justifyContent": "center",
        "zIndex": 1000,
        "fontSize": "12px",
        "color": "var(--color-primary)",
        "fontFamily": "Inter, system-ui, sans-serif",
        "fontWeight": 500,
    }
    return text, bar_style, False


# --- Signed-in user chip (top-right, only when auth is enabled) ---

@callback(
    Output("auth-user-chip", "children"),
    Input("_pages_location", "pathname"),
)
def _render_auth_chip(_pathname):
    """Read flask.session inside the Dash request context and render a
    small hover menu with the signed-in user's email + Sign Out link.
    Returns nothing when no session (e.g. AUTH_ENABLED=false)."""
    try:
        from flask import session, has_request_context
    except ImportError:
        return None
    if not has_request_context() or not session.get("user_id"):
        return None
    email = session.get("email") or ""
    display = email.split("@")[0] if email else "Account"
    # Clerk hosted user portal — "Manage account" opens password + MFA settings
    # without us needing to re-mount Clerk's JS on every page.
    import os as _os
    _frontend = _os.environ.get("CLERK_FRONTEND_HOST", "").strip()
    if not _frontend:
        # Derive from publishable key once.
        from auth import _clerk_frontend_host
        _pub = _os.environ.get("CLERK_PUBLISHABLE_KEY", "")
        try:
            _frontend = _clerk_frontend_host(_pub) if _pub else ""
        except Exception:
            _frontend = ""
    _account_url = f"https://{_frontend}/user" if _frontend else "#"

    return dmc.Menu(
        trigger="click-hover",
        position="bottom-end",
        shadow="md",
        width=220,
        offset=6,
        children=[
            dmc.MenuTarget(
                html.Button(
                    children=[
                        DashIconify(icon="tabler:user-circle", width=16,
                                    color=NEUTRAL["text_secondary"],
                                    style={"flexShrink": 0}),
                        html.Span(display, style={
                            "fontSize": "12px",
                            "color": NEUTRAL["text_secondary"],
                            "fontWeight": 500,
                            "maxWidth": "120px",
                            "overflow": "hidden",
                            "textOverflow": "ellipsis",
                            "whiteSpace": "nowrap",
                        }),
                    ],
                    style={
                        "display": "inline-flex",
                        "alignItems": "center",
                        "gap": "4px",
                        "padding": "4px 8px",
                        "border": "none",
                        "background": "transparent",
                        "borderRadius": "12px",
                        "cursor": "pointer",
                    },
                ),
            ),
            dmc.MenuDropdown(
                children=[
                    dmc.MenuLabel(email or "Signed in"),
                    dmc.MenuDivider(),
                    dmc.MenuItem(
                        "Manage account",
                        href=_account_url,
                        target="_blank",
                        leftSection=DashIconify(icon="tabler:settings", width=14),
                    ),
                    dmc.MenuItem(
                        "Reset password",
                        href=_account_url + "#/security" if _account_url != "#" else "#",
                        target="_blank",
                        leftSection=DashIconify(icon="tabler:key", width=14),
                    ),
                    dmc.MenuDivider(),
                    dmc.MenuItem(
                        "Sign out",
                        href="/logout",
                        leftSection=DashIconify(icon="tabler:logout", width=14),
                        color="red",
                    ),
                ],
            ),
        ],
    )


# --- Page navigation triggers priority loading ---

@callback(
    Output("preload-priority-trigger", "data"),
    Input("_pages_location", "pathname"),
)
def _prioritize_page_datasets(pathname):
    if _preload_state["done"]:
        return no_update
    datasets = _PAGE_DATASETS.get(pathname, [])
    with _preload_lock:
        for ds in datasets:
            if ds not in _preload_state["loaded"] and ds not in _priority_queue:
                _priority_queue.insert(0, ds)
    return ""

# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    app.run(debug=True, port=8050, host="localhost",
            dev_tools_hot_reload=True,
            dev_tools_hot_reload_interval=1.0,
            threaded=True)
