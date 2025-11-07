"""
Radiant Care Clinical Dashboard - Main Application
"""
import dash
import dash_bootstrap_components as dbc
from dash import html, Input, Output, State, dcc

from config.settings import APP_TITLE, get_data_directory
from data.loader import find_task_file, load_data
from components.header import create_header
from tasks.draw_volumes.draw_volumes_task import DrawVolumesTask
from tasks.review_plan.review_plan_task import ReviewPlanTask
from tasks.contour_review.contour_review_task import ContourReviewTask
from tasks.scheduling.scheduling_task import SchedulingTask
from utils.styles import CUSTOM_CSS

# Initialize Dash app with Bootstrap theme and pages support
app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP], use_pages=True, suppress_callback_exceptions=True)
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
        <script>
            window.formatTimeTooltip = function(value) {
                const hour = parseInt(value);
                if (hour === 12) {
                    return hour + ' PM';
                } else if (hour < 12) {
                    return hour + ' AM';
                } else {
                    return (hour - 12) + ' PM';
                }
            };
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
</html>
'''

# Load data
data_dir = get_data_directory()
task_file = find_task_file(data_dir)

if task_file is None:
    print(f"Error: Data file not found in {data_dir}")
    exit(1)

df = load_data(task_file)

# Load review data
from pathlib import Path
review_file = Path(data_dir) / "Department Schedule No Grouping All_review.csv"
if review_file.exists():
    review_df = load_data(str(review_file))
else:
    print(f"Warning: Review data file not found at {review_file}")
    review_df = df  # Fallback to main data

# Load contour data
contour_file = Path(data_dir) / "Department Schedule No Grouping All_contour.csv"
if contour_file.exists():
    contour_df = load_data(str(contour_file))
else:
    print(f"Warning: Contour data file not found at {contour_file}")
    contour_df = df  # Fallback to main data

# Load scheduling data
scheduling_file = Path(data_dir) / "Appointment Status per Activity (Mike).csv"
if scheduling_file.exists():
    # Read CSV with special handling - skip footer rows with filter metadata
    import pandas as pd
    # First read to find the actual data rows (stop at empty line)
    with open(scheduling_file, 'r') as f:
        lines = f.readlines()
        # Find first empty line (marks end of data)
        data_end = len(lines)
        for i, line in enumerate(lines):
            if line.strip() == '':
                data_end = i
                break
    # Now read only the data rows
    scheduling_df = pd.read_csv(str(scheduling_file), nrows=data_end-1)
else:
    print(f"Warning: Scheduling data file not found at {scheduling_file}")
    scheduling_df = None

# Initialize tasks (simulations is now a separate page)
draw_volumes_task = DrawVolumesTask(df)
review_plan_task = ReviewPlanTask(review_df)
contour_review_task = ContourReviewTask(contour_df)
if scheduling_df is not None:
    scheduling_task = SchedulingTask(scheduling_df)
else:
    scheduling_task = None

# Define the main layout
_layout = dbc.Container([
    # Store component to track active task
    dcc.Store(id='active-task-store', data='draw-volumes'),
    # Store component to persist sidebar state across task switches
    dcc.Store(id='sidebar-state-store', data={
        'physicians': None,
        'activity_names': None,  # Will reset on task switch
        'year_start': None,
        'year_end': None,
        'aggregation': None,
        'chart_type': None,
        'smoothing': None,
        'comparison_mode': None,
        'calendar_aligned': None,
        'period_type': None,
        'show_mean': None,
        'show_std_dev': None,
        'show_median': None,
        'show_ci': None,
    }),

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
                    dbc.Tab(label="Simulations", tab_id="simulations"),
                    dbc.Tab(label="Scheduling", tab_id="scheduling", disabled=(scheduling_task is None)),
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

    # Location component for URL navigation (required for pages)
    dcc.Location(id='url', refresh=False),

    # Main content area - show either Tasks content OR page container
    html.Div(id='main-content-area')
], fluid=True, style={'backgroundColor': '#FFFFFF'})

# Set the actual app layout
app.layout = _layout

# Note: We only register callbacks once. Both tasks share the same UI components,
# and the correct task is used based on which sidebar/panel is currently rendered.
# No need to register duplicate callbacks.
draw_volumes_task.register_callbacks(app)

# Register scheduling callbacks if available
if scheduling_task is not None:
    scheduling_task.register_callbacks(app)

# Simulations is now a separate Dash page - callbacks registered in pages/simulations.py

# Sync URL and tabs
@app.callback(
    Output('url', 'pathname', allow_duplicate=True),
    Input('main-tabs', 'active_tab'),
    prevent_initial_call=True
)
def navigate_from_tabs(active_tab):
    """Update URL when tabs are clicked"""
    if active_tab == 'simulations':
        return '/simulations'
    elif active_tab == 'scheduling':
        return '/scheduling'
    return '/'

@app.callback(
    Output('main-tabs', 'active_tab'),
    Input('url', 'pathname'),
    prevent_initial_call=True
)
def sync_tabs_from_url(pathname):
    """Update active tab when URL changes"""
    if pathname == '/simulations':
        return 'simulations'
    elif pathname == '/scheduling':
        return 'scheduling'
    return 'tasks'

# Store active task when subtabs are clicked
@app.callback(
    Output('active-task-store', 'data'),
    [Input("subtab-draw-volumes", "n_clicks"),
     Input("subtab-review-plan", "n_clicks"),
     Input("subtab-contour-review", "n_clicks")],
    [State('active-task-store', 'data')]
)
def update_active_task(draw_clicks, review_clicks, contour_clicks, current_task):
    """Update which task is active in the store"""
    ctx = dash.callback_context
    if not ctx.triggered:
        return 'draw-volumes'

    button_id = ctx.triggered[0]["prop_id"].split(".")[0]

    if button_id == "subtab-draw-volumes":
        return 'draw-volumes'
    elif button_id == "subtab-review-plan":
        return 'review-plan'
    elif button_id == "subtab-contour-review":
        return 'contour-review'

    return current_task

# Update sidebar state store when sidebar values change
@app.callback(
    Output('sidebar-state-store', 'data'),
    [Input('physician-checklist', 'value'),
     Input('year-start', 'value'),
     Input('year-end', 'value'),
     Input('aggregation-dropdown', 'value'),
     Input('chart-type', 'value'),
     Input('smoothing-slider', 'value'),
     Input('comparison-mode', 'value'),
     Input('calendar-aligned', 'value'),
     Input('period-type-year', 'n_clicks'),
     Input('period-type-quarter', 'n_clicks'),
     Input('period-type-month', 'n_clicks'),
     Input('show-mean', 'value'),
     Input('show-std-dev', 'value'),
     Input('show-median', 'value'),
     Input('show-ci', 'value')],
    [State('sidebar-state-store', 'data')],
    prevent_initial_call=True
)
def update_sidebar_state(physicians, year_start, year_end, aggregation, chart_type, smoothing,
                         comparison_mode, calendar_aligned, period_year_clicks, period_quarter_clicks,
                         period_month_clicks, show_mean, show_std_dev, show_median, show_ci, current_state):
    """Update sidebar state store when any sidebar component changes"""
    ctx = dash.callback_context
    if not ctx.triggered:
        return current_state or {}
    
    # Get current state or initialize
    new_state = current_state.copy() if current_state else {}
    
    # Update values for each changed component
    triggered_prop = ctx.triggered[0]["prop_id"]
    
    if 'physician-checklist' in triggered_prop:
        new_state['physicians'] = physicians
    if 'year-start' in triggered_prop:
        new_state['year_start'] = year_start
    if 'year-end' in triggered_prop:
        new_state['year_end'] = year_end
    if 'aggregation-dropdown' in triggered_prop:
        new_state['aggregation'] = aggregation
    if 'chart-type' in triggered_prop:
        new_state['chart_type'] = chart_type
    if 'smoothing-slider' in triggered_prop:
        new_state['smoothing'] = smoothing
    if 'comparison-mode' in triggered_prop:
        new_state['comparison_mode'] = comparison_mode
    if 'calendar-aligned' in triggered_prop:
        new_state['calendar_aligned'] = calendar_aligned
    if 'period-type' in triggered_prop:
        # Determine which period type button was clicked
        if 'period-type-year' in triggered_prop:
            new_state['period_type'] = 'year'
        elif 'period-type-quarter' in triggered_prop:
            new_state['period_type'] = 'quarter'
        elif 'period-type-month' in triggered_prop:
            new_state['period_type'] = 'month'
    if 'show-mean' in triggered_prop:
        new_state['show_mean'] = show_mean
    if 'show-std-dev' in triggered_prop:
        new_state['show_std_dev'] = show_std_dev
    if 'show-median' in triggered_prop:
        new_state['show_median'] = show_median
    if 'show-ci' in triggered_prop:
        new_state['show_ci'] = show_ci
    
    return new_state

# Tab and subtab content callbacks
@app.callback(
    Output('main-content-area', 'children'),
    [Input('url', 'pathname'),
     Input('active-task-store', 'data')],
    [State('sidebar-state-store', 'data')]
)
def render_main_content(pathname, active_task_id, sidebar_state):
    """Render either Tasks content, Scheduling, or Simulations page based on URL"""

    # If on the Simulations page route, show page container
    if pathname == '/simulations':
        return dash.page_container

    # If on the Scheduling page route, show Scheduling content
    if pathname == '/scheduling' and scheduling_task is not None:
        sidebar = scheduling_task.get_sidebar_layout()
        content = html.Div([
            scheduling_task.get_main_panel_layout()
        ], className="tab-content-area")

        return dbc.Row([
            # Sidebar
            dbc.Col([
                html.Div(sidebar)
            ], width=2, id="sidebar-column", style={'flex': '0 0 auto', 'width': 'auto'}),

            # Main panel content
            dbc.Col([
                html.Div(content)
            ], width=9, id="content-column", style={'padding': '0'})
        ])

    # Otherwise show Tasks content
    # Get the active task and update the current task reference for callbacks
    if active_task_id == "review-plan":
        task = review_plan_task
    elif active_task_id == "contour-review":
        task = contour_review_task
    else:
        task = draw_volumes_task

    # Update the current task that callbacks will use
    app._current_task = task

    # Use persisted state but reset activity_names (will be set to task defaults in sidebar)
    # Make a copy of state to avoid mutating the store
    sidebar_state_copy = sidebar_state.copy() if sidebar_state else {}
    sidebar_state_copy['activity_names'] = None  # Force reset to task defaults

    sidebar = task.get_sidebar_layout(state=sidebar_state_copy)

    content = html.Div([
        # Subtabs for Tasks
        html.Div([
            dbc.Nav(
                [
                    dbc.NavItem(dbc.NavLink("Draw Volumes", id="subtab-draw-volumes", active=(active_task_id == "draw-volumes"), href="#")),
                    dbc.NavItem(dbc.NavLink("Review Plan", id="subtab-review-plan", active=(active_task_id == "review-plan"), href="#")),
                    dbc.NavItem(dbc.NavLink("Contour Review", id="subtab-contour-review", active=(active_task_id == "contour-review"), href="#")),
                ],
                pills=True,
                className="nav-pills"
            )
        ], className="subtabs"),

        # Content area
        html.Div([
            task.get_main_panel_layout()
        ], className="tab-content-area")
    ])

    # Return Tasks content with sidebar
    return dbc.Row([
        # Sidebar
        dbc.Col([
            html.Div(sidebar)
        ], width=2, id="sidebar-column"),

        # Main panel content
        dbc.Col([
            html.Div(content)
        ], width=9, id="content-column", style={'padding': '0'})
    ], id='tasks-content-row')

# Help modal toggle callback
@app.callback(
    Output("help-modal", "is_open"),
    [Input("help-icon", "n_clicks"),
     Input("close-help-modal", "n_clicks")],
    [State("help-modal", "is_open")],
)
def toggle_help_modal(help_clicks, close_clicks, is_open):
    """Toggle the help modal when icon is clicked or close button is pressed"""
    if help_clicks or close_clicks:
        return not is_open
    return is_open

if __name__ == '__main__':
    app.run(debug=True, port=8050)
