"""
Radiant Care Clinical Dashboard - Main Application
"""
import dash
import dash_bootstrap_components as dbc
from dash import html

from config.settings import APP_TITLE, get_data_directory
from data.loader import find_task_file, load_data
from components.header import create_header
from tasks.draw_volumes.draw_volumes_task import DrawVolumesTask
from utils.styles import CUSTOM_CSS

# Initialize Dash app with Bootstrap theme
app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])
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

    # Main content
    dbc.Row([
        # Sidebar
        dbc.Col([
            draw_volumes_task.get_sidebar_layout()
        ], width=3),

        # Main panel
        dbc.Col([
            draw_volumes_task.get_main_panel_layout()
        ], width=9)
    ])
], fluid=True, style={'backgroundColor': '#FFFFFF'})

# Register callbacks
draw_volumes_task.register_callbacks(app)

if __name__ == '__main__':
    app.run(debug=True, port=8050)
