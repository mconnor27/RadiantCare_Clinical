"""
Simulations sidebar layout (filters and controls)
"""
from dash import html, dcc
import dash_bootstrap_components as dbc


def create_sidebar_layout(task, state=None):
    """
    Create sidebar layout for Simulations task.

    Args:
        task: SimulationsTask instance
        state: Optional dict with persisted state values

    Returns:
        Dash component for sidebar
    """
    # Use persisted state if available, otherwise use defaults
    if state is None:
        state = {}

    # Get values from state or defaults
    location_value = state.get('locations') if state.get('locations') is not None else task.locations
    sim_type_value = state.get('simulation_types') if state.get('simulation_types') is not None else task.simulation_types
    year_start_value = state.get('year_start') if state.get('year_start') is not None else task.min_year
    year_end_value = state.get('year_end') if state.get('year_end') is not None else task.max_year
    aggregation_value = state.get('aggregation') if state.get('aggregation') is not None else 'Daily'
    chart_type_value = state.get('chart_type') if state.get('chart_type') is not None else 'line'
    smoothing_value = state.get('smoothing') if state.get('smoothing') is not None else 0
    comparison_mode_value = state.get('comparison_mode') if state.get('comparison_mode') is not None else 'none'
    calendar_aligned_value = state.get('calendar_aligned') if state.get('calendar_aligned') is not None else []
    period_type_value = state.get('period_type') if state.get('period_type') is not None else 'year'
    show_mean_value = state.get('show_mean') if state.get('show_mean') is not None else []
    show_std_dev_value = state.get('show_std_dev') if state.get('show_std_dev') is not None else []
    show_median_value = state.get('show_median') if state.get('show_median') is not None else []
    show_ci_value = state.get('show_ci') if state.get('show_ci') is not None else []

    return html.Div([
        html.H5("Filters & Options", style={'marginBottom': '20px', 'marginTop': '20px'}),

        # Location Filter
        html.Div([
            html.Label("Location", style={'fontWeight': 'bold', 'marginBottom': '10px'}),
            dbc.Accordion([
                dbc.AccordionItem([
                    html.Div([
                        dbc.Row([
                            dbc.Col(dbc.Button("All", id="sim-select-all-location", size="sm", color="secondary", className="w-100"), width=6),
                            dbc.Col(dbc.Button("None", id="sim-clear-all-location", size="sm", color="secondary", className="w-100"), width=6),
                        ])
                    ], className="button-panel purple-panel"),
                    html.Div([
                        dbc.Checklist(
                            id="sim-location-checklist",
                            options=[{"label": loc, "value": loc} for loc in task.locations],
                            value=location_value,
                            className="purple-checkbox"
                        )
                    ])
                ], title=f"{len(task.locations)} of {len(task.locations)} selected", id="sim-location-accordion-title")
            ], start_collapsed=True, id="sim-location-accordion")
        ], className='filter-section'),

        # Simulation Type Filter
        html.Div([
            html.Label("Simulation Type", style={'fontWeight': 'bold', 'marginBottom': '10px'}),
            dbc.Accordion([
                dbc.AccordionItem([
                    html.Div([
                        dbc.Row([
                            dbc.Col(dbc.Button("All", id="sim-select-all-type", size="sm", color="secondary", className="w-100"), width=6),
                            dbc.Col(dbc.Button("None", id="sim-clear-all-type", size="sm", color="secondary", className="w-100"), width=6),
                        ])
                    ], className="button-panel red-panel"),
                    html.Div([
                        dbc.Checklist(
                            id="sim-type-checklist",
                            options=[{"label": t, "value": t} for t in task.simulation_types],
                            value=sim_type_value,
                            className="red-checkbox"
                        )
                    ])
                ], title=f"{len(task.simulation_types)} of {len(task.simulation_types)} selected", id="sim-type-accordion-title")
            ], start_collapsed=True, id="sim-type-accordion")
        ], className='filter-section'),

        html.Hr(),

        # Year Range Dropdowns
        html.Div([
            html.Label("Year Range", style={'fontWeight': 'bold', 'marginBottom': '10px'}),
            # Quick select buttons
            html.Div([
                dbc.Button("All", id="sim-year-all", size="sm", className="active"),
                dbc.Button("YTD", id="sim-year-current", size="sm"),
                dbc.Button("YTD & Prior", id="sim-year-current-last", size="sm"),
            ], className='year-select-buttons'),
            dbc.Row([
                dbc.Col([
                    html.Label("From", style={'fontSize': '0.85em', 'marginBottom': '5px', 'color': '#666'}),
                    dcc.Dropdown(
                        id='sim-year-start',
                        options=[{'label': str(y), 'value': y} for y in range(task.min_year, task.max_year + 1)],
                        value=year_start_value,
                        clearable=False
                    )
                ], width=6),
                dbc.Col([
                    html.Label("To", style={'fontSize': '0.85em', 'marginBottom': '5px', 'color': '#666'}),
                    dcc.Dropdown(
                        id='sim-year-end',
                        options=[{'label': str(y), 'value': y} for y in range(task.min_year, task.max_year + 1)],
                        value=year_end_value,
                        clearable=False
                    )
                ], width=6)
            ])
        ], className='filter-section', style={'marginTop': '10px', 'marginBottom': '20px'}),

        html.Hr(),

        # Time Aggregation
        html.Div([
            html.Label("Time Aggregation", style={'fontWeight': 'bold'}),
            dcc.Dropdown(
                id='sim-aggregation-dropdown',
                options=[
                    {'label': 'None (Cumulative)', 'value': 'Daily'},
                    {'label': 'Daily', 'value': 'Daily-NonCumulative'},
                    {'label': 'Weekly', 'value': 'Weekly'},
                    {'label': 'Monthly', 'value': 'Monthly'},
                    {'label': 'Quarterly', 'value': 'Quarterly'},
                    {'label': 'Yearly', 'value': 'Yearly'}
                ],
                value=aggregation_value,
                clearable=False
            )
        ], className='filter-section'),

        # Chart Type
        html.Div([
            html.Label("Chart Type", style={'fontWeight': 'bold'}),
            dbc.RadioItems(
                id='sim-chart-type',
                options=[
                    {'label': 'Line Chart', 'value': 'line'},
                    {'label': 'Bar Chart', 'value': 'bar'}
                ],
                value=chart_type_value
            )
        ], className='filter-section'),

        # Smoothing (only for line charts)
        html.Div([
            html.Div([
                html.Label("Smoothing", style={'fontWeight': 'bold', 'marginBottom': '10px', 'display': 'inline-block'}),
                html.Span(id='sim-smoothing-value', style={
                    'float': 'right',
                    'fontSize': '0.85em',
                    'color': '#3498DB',
                    'fontWeight': '600',
                    'marginTop': '2px'
                })
            ], style={'marginBottom': '10px'}),
            dcc.Slider(
                id='sim-smoothing-slider',
                min=0,
                max=10,
                step=0.5,
                value=smoothing_value,
                marks={0: '0', 2.5: '2.5', 5: '5', 7.5: '7.5', 10: '10'},
                tooltip={"placement": "bottom", "always_visible": False}
            )
        ], id='sim-smoothing-section', className='filter-section', style={'display': 'none'}),

        html.Hr(),

        # Comparison Mode
        html.Div([
            html.H6("Comparison Mode", style={'fontWeight': 'bold'}),
            dcc.Dropdown(
                id='sim-comparison-mode',
                options=[
                    {'label': 'None', 'value': 'none'},
                    {'label': 'Location', 'value': 'location'},
                    {'label': 'Previous Time Periods', 'value': 'previous_periods'}
                ],
                value=comparison_mode_value,
                clearable=False
            )
        ], className='filter-section'),

        # Calendar-aligned checkbox (only visible in location comparison mode)
        html.Div([
            dbc.Checklist(
                id='sim-calendar-aligned',
                options=[{'label': ' Calendar-aligned', 'value': 'aligned'}],
                value=calendar_aligned_value,
                inline=True,
                switch=False
            )
        ], id='sim-calendar-aligned-controls', className='filter-section', style={'display': 'none'}),

        # Historical Period Type Controls (only visible in previous_periods mode)
        html.Div([
            html.Div([
                dbc.Button("Year", id="sim-period-type-year", size="sm", className="active" if period_type_value == 'year' else ""),
                dbc.Button("Quarter", id="sim-period-type-quarter", size="sm", className="active" if period_type_value == 'quarter' else ""),
                dbc.Button("Month", id="sim-period-type-month", size="sm", className="active" if period_type_value == 'month' else ""),
            ], className='year-select-buttons', style={'marginBottom': '15px'}),
            dbc.Row([
                dbc.Col([
                    dbc.Checklist(
                        id='sim-show-mean',
                        options=[{'label': ' Mean', 'value': 'mean'}],
                        value=show_mean_value,
                        inline=True,
                        switch=False
                    )
                ], width=6),
                dbc.Col([
                    dbc.Checklist(
                        id='sim-show-std-dev',
                        options=[{'label': ' Std Dev', 'value': 'std'}],
                        value=show_std_dev_value,
                        inline=True,
                        switch=False
                    )
                ], width=6)
            ], style={'marginBottom': '8px'}),
            dbc.Row([
                dbc.Col([
                    dbc.Checklist(
                        id='sim-show-median',
                        options=[{'label': ' Median', 'value': 'median'}],
                        value=show_median_value,
                        inline=True,
                        switch=False
                    )
                ], width=6),
                dbc.Col([
                    dbc.Checklist(
                        id='sim-show-ci',
                        options=[{'label': ' 95% CI', 'value': 'ci'}],
                        value=show_ci_value,
                        inline=True,
                        switch=False
                    )
                ], width=6)
            ])
        ], id='sim-historical-stats-controls', className='filter-section', style={'display': 'none'})
    ], className='sidebar')
