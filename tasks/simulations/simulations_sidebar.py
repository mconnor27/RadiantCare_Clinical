"""
Simulations sidebar layout
"""
from dash import html, dcc
import dash_bootstrap_components as dbc


def create_sidebar_layout(task, state=None):
    """
    Create the sidebar layout for simulations task

    Args:
        task: SimulationsTask instance
        state: Optional dict with persisted state values
    """
    # Extract state values if provided
    if state is None:
        state = {}

    selected_locations = state.get('locations', task.locations)
    selected_sim_types = state.get('simulation_types', task.simulation_types)
    year_start = state.get('year_start', task.min_year)
    year_end = state.get('year_end', task.max_year)
    aggregation = state.get('aggregation', 'Monthly')
    chart_type = state.get('chart_type', 'line')
    smoothing = state.get('smoothing', 0)
    comparison_mode = state.get('comparison_mode', 'none')
    calendar_aligned = state.get('calendar_aligned', [])

    return html.Div([
        # Location filter (replaces Physician filter)
        html.Div([
            html.Label("Location", style={'fontWeight': 'bold', 'marginBottom': '10px'}),
            dcc.Checklist(
                id='sim-location-checklist',
                options=[{'label': loc, 'value': loc} for loc in task.locations],
                value=selected_locations if selected_locations else task.locations,
                style={'marginBottom': '20px'}
            )
        ]),

        # Simulation Type filter (replaces Activity Name filter)
        html.Div([
            html.Label("Simulation Type", style={'fontWeight': 'bold', 'marginBottom': '10px'}),
            dcc.Checklist(
                id='sim-type-checklist',
                options=[{'label': st, 'value': st} for st in task.simulation_types],
                value=selected_sim_types if selected_sim_types else task.simulation_types,
                style={'marginBottom': '20px'}
            )
        ]),

        # Year range
        html.Div([
            html.Label("Year Range", style={'fontWeight': 'bold', 'marginBottom': '10px'}),
            html.Div([
                html.Label("Start Year", style={'fontSize': '12px', 'marginBottom': '5px'}),
                dcc.Dropdown(
                    id='sim-year-start',
                    options=[{'label': str(year), 'value': year} for year in range(task.min_year, task.max_year + 1)],
                    value=year_start,
                    clearable=False,
                    style={'marginBottom': '10px'}
                ),
                html.Label("End Year", style={'fontSize': '12px', 'marginBottom': '5px'}),
                dcc.Dropdown(
                    id='sim-year-end',
                    options=[{'label': str(year), 'value': year} for year in range(task.min_year, task.max_year + 1)],
                    value=year_end,
                    clearable=False,
                    style={'marginBottom': '10px'}
                ),
                # Quick select buttons
                html.Div([
                    dbc.Button("All Years", id='sim-select-all-years', size='sm', color='secondary', outline=True, style={'marginBottom': '5px', 'width': '100%'}),
                    dbc.Button("Last 5 Years", id='sim-select-last-5', size='sm', color='secondary', outline=True, style={'marginBottom': '5px', 'width': '100%'}),
                    dbc.Button("Last 10 Years", id='sim-select-last-10', size='sm', color='secondary', outline=True, style={'width': '100%'}),
                ], style={'marginTop': '10px', 'marginBottom': '20px'})
            ])
        ]),

        # Aggregation
        html.Div([
            html.Label("Aggregation", style={'fontWeight': 'bold', 'marginBottom': '10px'}),
            dcc.Dropdown(
                id='sim-aggregation-dropdown',
                options=[
                    {'label': 'Daily (Cumulative)', 'value': 'Daily'},
                    {'label': 'Daily (Non-Cumulative)', 'value': 'Daily-NonCumulative'},
                    {'label': 'Weekly', 'value': 'Weekly'},
                    {'label': 'Monthly', 'value': 'Monthly'},
                    {'label': 'Quarterly', 'value': 'Quarterly'},
                    {'label': 'Yearly', 'value': 'Yearly'}
                ],
                value=aggregation,
                clearable=False,
                style={'marginBottom': '20px'}
            )
        ]),

        # Chart Type
        html.Div([
            html.Label("Chart Type", style={'fontWeight': 'bold', 'marginBottom': '10px'}),
            dcc.RadioItems(
                id='sim-chart-type',
                options=[
                    {'label': ' Line', 'value': 'line'},
                    {'label': ' Bar', 'value': 'bar'}
                ],
                value=chart_type,
                style={'marginBottom': '20px'}
            )
        ]),

        # Smoothing slider
        html.Div([
            html.Label("Smoothing", style={'fontWeight': 'bold', 'marginBottom': '10px'}),
            dcc.Slider(
                id='sim-smoothing-slider',
                min=0,
                max=10,
                step=1,
                value=smoothing,
                marks={0: '0', 5: '5', 10: '10'},
                tooltip={'placement': 'bottom', 'always_visible': False}
            )
        ], style={'marginBottom': '20px'}),

        # Comparison Mode
        html.Div([
            html.Label("Comparison Mode", style={'fontWeight': 'bold', 'marginBottom': '10px'}),
            dcc.RadioItems(
                id='sim-comparison-mode',
                options=[
                    {'label': ' None', 'value': 'none'},
                    {'label': ' By Location', 'value': 'location'},
                ],
                value=comparison_mode,
                style={'marginBottom': '10px'}
            ),
            # Calendar aligned checkbox (only visible when comparing by location)
            html.Div([
                dcc.Checklist(
                    id='sim-calendar-aligned',
                    options=[{'label': ' Normalize Timeline', 'value': 'aligned'}],
                    value=calendar_aligned,
                )
            ], id='sim-calendar-aligned-container', style={'marginLeft': '20px', 'marginBottom': '20px'})
        ]),

    ], style={'padding': '20px'})
