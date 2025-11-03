"""
Radiant Care Clinical Dashboard - Main Application
"""
import dash
import dash_bootstrap_components as dbc
from dash import html, Input, Output

from config.settings import APP_TITLE, get_data_directory
from data.loader import find_task_file, load_data
from components.header import create_header
from tasks.draw_volumes.draw_volumes_task import DrawVolumesTask
from utils.styles import CUSTOM_CSS

# Initialize Dash app with Bootstrap theme
app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP], suppress_callback_exceptions=True)
app.title = APP_TITLE

# Add custom CSS
app.index_string = '''
<!DOCTYPE html>
<html>
    <head>
        {%metas%}
        <title>{%title%}</title>
        {%favicon%}
        {%css%}
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
        <style>
''' + CUSTOM_CSS + '''
        </style>
    </head>
    <body>
        {%app_entry%}
        <footer>
            {%config%}
            {%scripts%}
            {%renderer%}
        </footer>
    </body>
</html>
'''

# Load data
data_dir = get_data_directory()
task_file = find_task_file(data_dir)

if task_file is None:
    print(f"Error: Data file not found in {data_dir}")
    exit(1)

df = load_data(task_file)

# Initialize Draw Volumes task
draw_volumes_task = DrawVolumesTask(df)

# App layout
app.layout = dbc.Container([
    # Header
    dbc.Row([
        dbc.Col([
            create_header()
        ], width=12)
    ]),

    # Row with tabs
    dbc.Row([
        dbc.Col(width=3),
        dbc.Col([
            dbc.Tabs(
                id="main-tabs",
                active_tab="tasks",
                className="main-tabs",
                children=[
                    dbc.Tab(label="Tasks", tab_id="tasks"),
                    dbc.Tab(label="Clinic Visits", tab_id="clinic_visits", disabled=True),
                    dbc.Tab(label="Simulations", tab_id="simulations", disabled=True),
                    dbc.Tab(label="Billing", tab_id="billing", disabled=True),
                    dbc.Tab(label="Treatment", tab_id="treatment", disabled=True),
                ]
            )
        ], width=9, style={'padding': '0'})
    ], style={'margin': '0'}),

    # Horizontal rule
    dbc.Row([
        dbc.Col([
            html.Div(style={'borderTop': '2px solid #E8E8E8'})
        ], width=12, style={'padding': '0'})
    ], style={'margin': '0', 'position': 'relative'}),

    # Main content with sidebar and panel
    dbc.Row([
        # Sidebar
        dbc.Col([
            draw_volumes_task.get_sidebar_layout()
        ], width=2),

        # Main panel content
        dbc.Col([
            html.Div(id="tab-content")
        ], width=9, style={'padding': '0'})
    ])
], fluid=True, style={'backgroundColor': '#FFFFFF'})

# Register callbacks
draw_volumes_task.register_callbacks(app)

# Tab switching callback
@app.callback(
    Output("tab-content", "children"),
    Input("main-tabs", "active_tab")
)
def render_tab_content(active_tab):
    """Render content based on active tab"""
    if active_tab == "tasks":
        return html.Div([
            # Subtabs for Tasks
            html.Div([
                dbc.Nav(
                    [
                        dbc.NavItem(dbc.NavLink("Draw Volumes", id="subtab-draw-volumes", active=True, href="#")),
                    ],
                    pills=True,
                    className="nav-pills"
                )
            ], className="subtabs"),

            # Content area
            html.Div([
                draw_volumes_task.get_main_panel_layout()
            ], className="tab-content-area")
        ])

    # Placeholder for other tabs
    return html.Div([
        html.Div([
            html.H4("Coming Soon", style={'textAlign': 'center', 'marginTop': '50px', 'color': '#6c757d'})
        ], className="tab-content-area")
    ])

if __name__ == '__main__':
    app.run(debug=True, port=8050)
