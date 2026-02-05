"""
Simulations page for Dash multi-page app with subtabs
"""
import dash
from dash import html, dcc, Input, Output, State, callback, dash_table
import dash_bootstrap_components as dbc
from pathlib import Path
import plotly.graph_objects as go
import plotly.express as px
import numpy as np

from config.settings import get_data_directory
from data.loader import load_data
from tasks.simulations.simulations_task import SimulationsTask

# Register this as a Dash page
dash.register_page(__name__, path='/simulations', name='Simulations')

# Load simulations data - use pd.read_csv directly instead of load_data()
# because load_data() filters for MD names which simulations don't have
data_dir = get_data_directory()
sim_file = Path(data_dir) / "Department Schedule No Grouping All_sim.csv"
if sim_file.exists():
    import pandas as pd
    sim_df = pd.read_csv(str(sim_file))
    sim_df['AppointmentTime'] = pd.to_datetime(sim_df['AppointmentTime'], errors='coerce')
    # Drop rows without appointment time
    sim_df = sim_df.dropna(subset=['AppointmentTime'])
else:
    import pandas as pd
    sim_df = pd.DataFrame()  # Empty fallback

# Initialize simulations task
simulations_task = SimulationsTask(sim_df)

# Page layout with subtabs
layout = dbc.Container([
    # Store for active subtab
    dcc.Store(id='sim-active-subtab', data='location-type'),
    # Store for period type selection
    dcc.Store(id='sim-period-type', data='year'),

    dbc.Row([
        # Sidebar
        dbc.Col([
            html.Div(id='sim-sidebar-content')
        ], width=2, id='sim-sidebar-column', style={'backgroundColor': '#f8f9fa', 'padding': '20px', 'minHeight': '100vh'}),

        # Main content with subtabs
        dbc.Col([
            # Subtabs
            html.Div([
                dbc.Nav([
                    dbc.NavItem(dbc.NavLink("Location/Type", id="sim-subtab-location-type", active=True, href="#")),
                    dbc.NavItem(dbc.NavLink("Duration", id="sim-subtab-duration", active=False, href="#")),
                ], pills=True, className="nav-pills")
            ], className="subtabs"),

            # Content area
            html.Div(id='sim-main-content', className="tab-content-area")
        ], width=10, style={'padding': '20px'})
    ], style={'margin': '0'})
], fluid=True, style={'backgroundColor': '#FFFFFF', 'padding': '0'})

# Callback to update active subtab
@callback(
    Output('sim-active-subtab', 'data'),
    [Input('sim-subtab-location-type', 'n_clicks'),
     Input('sim-subtab-duration', 'n_clicks')],
    [State('sim-active-subtab', 'data')]
)
def update_sim_active_subtab(loc_clicks, dur_clicks, current_subtab):
    ctx = dash.callback_context
    if not ctx.triggered:
        return 'location-type'

    button_id = ctx.triggered[0]['prop_id'].split('.')[0]

    if button_id == 'sim-subtab-location-type':
        return 'location-type'
    elif button_id == 'sim-subtab-duration':
        return 'duration'

    return current_subtab

# Callback to render sidebar and main content based on active subtab
@callback(
    [Output('sim-sidebar-content', 'children'),
     Output('sim-main-content', 'children'),
     Output('sim-subtab-location-type', 'active'),
     Output('sim-subtab-duration', 'active')],
    [Input('sim-active-subtab', 'data')]
)
def render_sim_content(active_subtab):
    if active_subtab == 'location-type':
        # Original Location/Type view
        sidebar = simulations_task.get_sidebar_layout()
        main_panel = simulations_task.get_main_panel_layout()
        return sidebar, main_panel, True, False

    elif active_subtab == 'duration':
        # Duration view - simplified sidebar
        sidebar = create_duration_sidebar()
        main_panel = create_duration_panel()
        return sidebar, main_panel, False, True

    return html.Div(), html.Div(), True, False

def create_duration_sidebar():
    """Create simplified sidebar for Duration subtab"""
    return html.Div([
        html.H5("Filters", style={'marginBottom': '20px', 'marginTop': '20px'}),

        # Location Filter
        html.Div([
            html.Label("Location", style={'fontWeight': 'bold', 'marginBottom': '10px'}),
            dbc.Accordion([
                dbc.AccordionItem([
                    html.Div([
                        dbc.Row([
                            dbc.Col(dbc.Button("All", id="dur-select-all-location", size="sm", color="secondary", className="w-100"), width=6),
                            dbc.Col(dbc.Button("None", id="dur-clear-all-location", size="sm", color="secondary", className="w-100"), width=6),
                        ])
                    ], className="button-panel purple-panel"),
                    html.Div([
                        dbc.Checklist(
                            id="dur-location-checklist",
                            options=[{"label": loc, "value": loc} for loc in sorted(simulations_task.locations, reverse=True)],
                            value=simulations_task.locations,
                            className="purple-checkbox"
                        )
                    ])
                ], title=f"{len(simulations_task.locations)} of {len(simulations_task.locations)} selected", id="dur-location-accordion-title")
            ], start_collapsed=True, id="dur-location-accordion")
        ], className='filter-section'),

        # Simulation Type Filter
        html.Div([
            html.Label("Simulation Type", style={'fontWeight': 'bold', 'marginBottom': '10px'}),
            dbc.Accordion([
                dbc.AccordionItem([
                    html.Div([
                        dbc.Row([
                            dbc.Col(dbc.Button("All", id="dur-select-all-type", size="sm", color="secondary", className="w-100"), width=6),
                            dbc.Col(dbc.Button("None", id="dur-clear-all-type", size="sm", color="secondary", className="w-100"), width=6),
                        ])
                    ], className="button-panel red-panel"),
                    html.Div([
                        dbc.Checklist(
                            id="dur-type-checklist",
                            options=[{"label": t, "value": t} for t in simulations_task.simulation_types],
                            value=simulations_task.simulation_types,
                            className="red-checkbox"
                        )
                    ])
                ], title=f"{len(simulations_task.simulation_types)} of {len(simulations_task.simulation_types)} selected", id="dur-type-accordion-title")
            ], start_collapsed=True, id="dur-type-accordion")
        ], className='filter-section'),

        html.Hr(),

        # Year Range Dropdowns
        html.Div([
            html.Label("Year Range", style={'fontWeight': 'bold', 'marginBottom': '10px'}),
            html.Div([
                dbc.Button("All", id="dur-year-all", size="sm", className="active"),
                dbc.Button("YTD", id="dur-year-current", size="sm"),
                dbc.Button("YTD & Prior", id="dur-year-current-last", size="sm"),
            ], className='year-select-buttons'),
            dbc.Row([
                dbc.Col([
                    html.Label("From", style={'fontSize': '0.85em', 'marginBottom': '5px', 'color': '#666'}),
                    dcc.Dropdown(
                        id='dur-year-start',
                        options=[{'label': str(y), 'value': y} for y in range(simulations_task.min_year, simulations_task.max_year + 1)],
                        value=simulations_task.min_year,
                        clearable=False
                    )
                ], width=6),
                dbc.Col([
                    html.Label("To", style={'fontSize': '0.85em', 'marginBottom': '5px', 'color': '#666'}),
                    dcc.Dropdown(
                        id='dur-year-end',
                        options=[{'label': str(y), 'value': y} for y in range(simulations_task.min_year, simulations_task.max_year + 1)],
                        value=simulations_task.max_year,
                        clearable=False
                    )
                ], width=6)
            ])
        ], className='filter-section', style={'marginTop': '10px', 'marginBottom': '20px'}),
    ], className='sidebar')

def create_duration_panel():
    """Create main panel for Duration subtab"""
    return html.Div([
        html.H4("Mean Appointment Duration Over Time (Weekly)", style={'marginBottom': '20px'}),
        html.Div([
            html.Label("Rolling Window (weeks):", style={'marginRight': '10px', 'fontWeight': 'bold'}),
            html.Div([
                dcc.Slider(
                    id='dur-rolling-window',
                    min=0,
                    max=26,
                    step=1,
                    value=0,
                    marks={
                        0: '0',
                        4: '4',
                        8: '8',
                        13: '13',
                        18: '18',
                        26: '26'
                    },
                    tooltip={"placement": "bottom", "always_visible": True}
                )
            ], style={'width': '400px', 'display': 'inline-block', 'verticalAlign': 'middle'}),
            html.Span(id='dur-window-label', style={'marginLeft': '20px', 'fontSize': '14px', 'color': '#666'})
        ], style={'marginBottom': '20px'}),
        dcc.Graph(id='dur-timeline-plot', style={
            'height': '700px',
            'border': '1px solid #dee2e6',
            'borderRadius': '4px',
            'boxShadow': '0 2px 4px rgba(0,0,0,0.1)'
        })
    ])

# Duration sidebar callbacks
@callback(
    Output('dur-location-checklist', 'value'),
    [Input('dur-select-all-location', 'n_clicks'),
     Input('dur-clear-all-location', 'n_clicks')],
    prevent_initial_call=True
)
def update_dur_locations(select_all, clear_all):
    ctx = dash.callback_context
    button_id = ctx.triggered[0]['prop_id'].split('.')[0]

    if button_id == 'dur-select-all-location':
        return simulations_task.locations
    elif button_id == 'dur-clear-all-location':
        return []
    return dash.no_update

@callback(
    Output('dur-type-checklist', 'value'),
    [Input('dur-select-all-type', 'n_clicks'),
     Input('dur-clear-all-type', 'n_clicks')],
    prevent_initial_call=True
)
def update_dur_types(select_all, clear_all):
    ctx = dash.callback_context
    button_id = ctx.triggered[0]['prop_id'].split('.')[0]

    if button_id == 'dur-select-all-type':
        return simulations_task.simulation_types
    elif button_id == 'dur-clear-all-type':
        return []
    return dash.no_update

@callback(
    Output('dur-location-accordion-title', 'title'),
    [Input('dur-location-checklist', 'value')]
)
def update_dur_location_title(selected):
    if selected is None:
        selected = []
    return f"{len(selected)} of {len(simulations_task.locations)} selected"

@callback(
    Output('dur-type-accordion-title', 'title'),
    [Input('dur-type-checklist', 'value')]
)
def update_dur_type_title(selected):
    if selected is None:
        selected = simulations_task.simulation_types
    return f"{len(selected)} of {len(simulations_task.simulation_types)} selected"

@callback(
    [Output('dur-year-start', 'value'),
     Output('dur-year-end', 'value'),
     Output('dur-year-all', 'className'),
     Output('dur-year-current', 'className'),
     Output('dur-year-current-last', 'className')],
    [Input('dur-year-all', 'n_clicks'),
     Input('dur-year-current', 'n_clicks'),
     Input('dur-year-current-last', 'n_clicks'),
     Input('dur-year-start', 'value'),
     Input('dur-year-end', 'value')],
    prevent_initial_call=True
)
def update_dur_year_range_buttons(all_clicks, current_clicks, current_last_clicks, year_start, year_end):
    ctx = dash.callback_context
    button_id = ctx.triggered[0]['prop_id'].split('.')[0]

    all_class = ""
    current_class = ""
    current_last_class = ""

    if button_id == 'dur-year-all':
        all_class = "active"
        return simulations_task.min_year, simulations_task.max_year, all_class, current_class, current_last_class
    elif button_id == 'dur-year-current':
        current_class = "active"
        return simulations_task.max_year, simulations_task.max_year, all_class, current_class, current_last_class
    elif button_id == 'dur-year-current-last':
        current_last_class = "active"
        return max(simulations_task.min_year, simulations_task.max_year - 1), simulations_task.max_year, all_class, current_class, current_last_class
    elif button_id in ['dur-year-start', 'dur-year-end']:
        if year_start == simulations_task.min_year and year_end == simulations_task.max_year:
            all_class = "active"
        elif year_start == simulations_task.max_year and year_end == simulations_task.max_year:
            current_class = "active"
        elif year_start == max(simulations_task.min_year, simulations_task.max_year - 1) and year_end == simulations_task.max_year:
            current_last_class = "active"
        return dash.no_update, dash.no_update, all_class, current_class, current_last_class

    return dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update

# Window label callback
@callback(
    Output('dur-window-label', 'children'),
    Input('dur-rolling-window', 'value')
)
def update_window_label(window_periods):
    if window_periods == 0:
        return "(No smoothing)"

    plural = 's' if window_periods > 1 else ''
    return f"({window_periods}-week{plural} moving average)"

# Duration timeline plot callback
@callback(
    Output('dur-timeline-plot', 'figure'),
    [Input('dur-location-checklist', 'value'),
     Input('dur-type-checklist', 'value'),
     Input('dur-year-start', 'value'),
     Input('dur-year-end', 'value'),
     Input('dur-rolling-window', 'value')]
)
def update_dur_timeline_plot(selected_locations, selected_types, year_start, year_end, rolling_window):
    import pandas as pd
    from plotly.subplots import make_subplots

    # Hardcode weekly aggregation
    time_agg = 'W'

    # Filter data
    year_range = [year_start, year_end]
    filtered_df = simulations_task.filter_data(selected_locations, selected_types, year_range)

    if filtered_df.empty:
        fig = go.Figure()
        fig.update_layout(title="No data available for selected filters")
        return fig

    # Get ActivityPlannedLength from original dataframe
    df_with_duration = simulations_task.df.merge(
        filtered_df[['PatientId', 'AppointmentTime', 'Location', 'SimulationType']],
        on=['PatientId', 'AppointmentTime', 'Location', 'SimulationType'],
        how='inner'
    )

    # Convert ActivityPlannedLength to numeric and filter
    # DATA PROCESSING: Filter out durations <= 0 or > 240 minutes
    df_with_duration['Duration'] = pd.to_numeric(df_with_duration.get('ActivityPlannedLength', 0), errors='coerce')
    df_with_duration = df_with_duration[df_with_duration['Duration'].notna()]
    df_with_duration = df_with_duration[
        (df_with_duration['Duration'] > 0) &
        (df_with_duration['Duration'] <= 240)
    ]

    if df_with_duration.empty:
        fig = go.Figure()
        fig.update_layout(title="No duration data available for selected filters")
        return fig

    # Prepare data with datetime index
    df_with_duration['Date'] = pd.to_datetime(df_with_duration['AppointmentTime'])
    df_with_duration = df_with_duration.sort_values('Date')

    locations = sorted(df_with_duration['Location'].unique(), reverse=True)

    # If only one location selected, show just that location
    # Otherwise show "All Locations" + individual locations
    if len(locations) == 1:
        n_rows = 1
        subplot_titles = locations
        show_all_locations = False
    else:
        n_rows = len(locations) + 1
        subplot_titles = ['All Locations'] + locations
        show_all_locations = True

    fig = make_subplots(
        rows=n_rows,
        cols=1,
        subplot_titles=subplot_titles,
        vertical_spacing=0.05,
        shared_xaxes=True
    )

    # Color scheme
    colors = {
        'All Locations': 'rgb(124, 42, 131)',
        'Aberdeen': 'rgb(31, 119, 180)',
        'Centralia': 'rgb(255, 127, 14)',
        'Lacey': 'rgb(44, 160, 44)'
    }

    # Plot "All Locations" first (only if multiple locations selected)
    if show_all_locations:
        df_all = df_with_duration.set_index('Date').sort_index()

        # STEP 1: Aggregate to time periods (weekly)
        overall = df_all['Duration'].resample(time_agg).agg(['mean', 'std', 'count']).reset_index()

        # Interpolate missing values for smooth lines
        overall['mean'] = overall['mean'].interpolate(method='linear')
        overall['std'] = overall['std'].interpolate(method='linear')

        # STEP 2: Apply rolling window smoothing if requested
        if rolling_window > 0:
            overall['mean'] = overall['mean'].rolling(window=rolling_window, min_periods=1, center=True).mean()
            overall['std'] = overall['std'].rolling(window=rolling_window, min_periods=1, center=True).mean()
            overall['count'] = overall['count'].rolling(window=rolling_window, min_periods=1, center=True).sum()

        overall['Date_str'] = overall['Date'].dt.strftime('%Y-%m-%d')

        # Calculate confidence bands
        overall['upper_std'] = overall['mean'] + overall['std']
        overall['lower_std'] = overall['mean'] - overall['std']

        color = colors.get('All Locations', 'rgb(124, 42, 131)')

        # Add 1 std band
        fig.add_trace(
            go.Scatter(
                x=overall['Date_str'],
                y=overall['upper_std'],
                mode='lines',
                line=dict(width=0),
                showlegend=False,
                hoverinfo='skip'
            ),
            row=1, col=1
        )
        fig.add_trace(
            go.Scatter(
                x=overall['Date_str'],
                y=overall['lower_std'],
                mode='lines',
                line=dict(width=0),
                fillcolor='rgba(124, 42, 131, 0.25)',
                fill='tonexty',
                showlegend=False,
                hoverinfo='skip'
            ),
            row=1, col=1
        )

        # Add mean line
        fig.add_trace(
            go.Scatter(
                x=overall['Date_str'],
                y=overall['mean'],
                mode='lines',
                name='All Locations',
                line=dict(color=color, width=2.5),
                hovertemplate='<b>%{x}</b><br>Mean: %{y:.1f} min<br><extra></extra>',
                showlegend=False
            ),
            row=1, col=1
        )

    # Plot individual locations
    # If single location: start at row 1
    # If multiple locations: start at row 2 (after "All Locations")
    start_row = 1 if not show_all_locations else 2
    for idx, location in enumerate(locations, start=start_row):
        loc_data = df_with_duration[df_with_duration['Location'] == location].set_index('Date').sort_index()

        # STEP 1: Aggregate to time periods (D, W, M, Q, Y)
        loc_agg = loc_data['Duration'].resample(time_agg).agg(['mean', 'std', 'count']).reset_index()

        # Interpolate missing values for smooth lines
        loc_agg['mean'] = loc_agg['mean'].interpolate(method='linear')
        loc_agg['std'] = loc_agg['std'].interpolate(method='linear')

        # STEP 2: Apply rolling window smoothing if requested
        if rolling_window > 0:
            loc_agg['mean'] = loc_agg['mean'].rolling(window=rolling_window, min_periods=1, center=True).mean()
            loc_agg['std'] = loc_agg['std'].rolling(window=rolling_window, min_periods=1, center=True).mean()
            loc_agg['count'] = loc_agg['count'].rolling(window=rolling_window, min_periods=1, center=True).sum()

        loc_agg['Date_str'] = loc_agg['Date'].dt.strftime('%Y-%m-%d')

        # Calculate confidence bands
        # ±1 std covers ~68% of data
        loc_agg['upper_std'] = loc_agg['mean'] + loc_agg['std']
        loc_agg['lower_std'] = loc_agg['mean'] - loc_agg['std']

        color_rgb = colors.get(location, f'rgb({idx*50},{idx*30},{idx*70})')
        color_rgba = color_rgb.replace('rgb(', '').replace(')', '').split(',')

        # Add 1 std band
        fig.add_trace(
            go.Scatter(
                x=loc_agg['Date_str'],
                y=loc_agg['upper_std'],
                mode='lines',
                line=dict(width=0),
                showlegend=False,
                hoverinfo='skip'
            ),
            row=idx, col=1
        )
        fig.add_trace(
            go.Scatter(
                x=loc_agg['Date_str'],
                y=loc_agg['lower_std'],
                mode='lines',
                line=dict(width=0),
                fillcolor=f'rgba({color_rgba[0]},{color_rgba[1]},{color_rgba[2]}, 0.25)',
                fill='tonexty',
                showlegend=False,
                hoverinfo='skip'
            ),
            row=idx, col=1
        )

        # Add mean line
        fig.add_trace(
            go.Scatter(
                x=loc_agg['Date_str'],
                y=loc_agg['mean'],
                mode='lines',
                name=location,
                line=dict(color=color_rgb, width=2.5),
                hovertemplate=f'<b>{location} - %{{x}}</b><br>Mean: %{{y:.1f}} min<br><extra></extra>',
                showlegend=False
            ),
            row=idx, col=1
        )

    # Update layout
    fig.update_layout(
        height=700,
        showlegend=False,
        hovermode='closest',
        plot_bgcolor='white',
        paper_bgcolor='white',
        font=dict(color='#2C3E50', size=11),
        margin=dict(l=60, r=30, t=40, b=60)
    )

    # Update all y-axes to start at zero
    for i in range(1, n_rows + 1):
        fig.update_yaxes(
            title_text="Minutes" if i == (n_rows + 1) // 2 else "",
            showgrid=True,
            gridcolor='#ECF0F1',
            zeroline=True,
            zerolinewidth=1,
            zerolinecolor='#6c757d',
            rangemode='tozero',
            row=i, col=1
        )

    # Update x-axis (only last one since shared)
    fig.update_xaxes(
        title_text="Time Period",
        showgrid=True,
        gridcolor='#ECF0F1',
        row=n_rows, col=1
    )

    return fig

# LOCATION/TYPE SUBTAB CALLBACKS (original callbacks)

# Location filter callbacks
@callback(
    Output('sim-location-checklist', 'value'),
    [Input('sim-select-all-location', 'n_clicks'),
     Input('sim-clear-all-location', 'n_clicks')],
    prevent_initial_call=True
)
def update_sim_locations(select_all, clear_all):
    ctx = dash.callback_context
    button_id = ctx.triggered[0]['prop_id'].split('.')[0]

    if button_id == 'sim-select-all-location':
        return simulations_task.locations
    elif button_id == 'sim-clear-all-location':
        return []
    return dash.no_update

# Simulation type filter callbacks
@callback(
    Output('sim-type-checklist', 'value'),
    [Input('sim-select-all-type', 'n_clicks'),
     Input('sim-clear-all-type', 'n_clicks')],
    prevent_initial_call=True
)
def update_sim_types(select_all, clear_all):
    ctx = dash.callback_context
    button_id = ctx.triggered[0]['prop_id'].split('.')[0]

    if button_id == 'sim-select-all-type':
        return simulations_task.simulation_types
    elif button_id == 'sim-clear-all-type':
        return []
    return dash.no_update

# Update location accordion title
@callback(
    Output('sim-location-accordion-title', 'title'),
    [Input('sim-location-checklist', 'value')]
)
def update_sim_location_title(selected):
    if selected is None:
        selected = []
    return f"{len(selected)} of {len(simulations_task.locations)} selected"

# Update simulation type accordion title
@callback(
    Output('sim-type-accordion-title', 'title'),
    [Input('sim-type-checklist', 'value')]
)
def update_sim_type_title(selected):
    if selected is None:
        selected = simulations_task.simulation_types
    return f"{len(selected)} of {len(simulations_task.simulation_types)} selected"

# Year range button callbacks
@callback(
    [Output('sim-year-start', 'value'),
     Output('sim-year-end', 'value'),
     Output('sim-year-all', 'className'),
     Output('sim-year-current', 'className'),
     Output('sim-year-current-last', 'className')],
    [Input('sim-year-all', 'n_clicks'),
     Input('sim-year-current', 'n_clicks'),
     Input('sim-year-current-last', 'n_clicks'),
     Input('sim-year-start', 'value'),
     Input('sim-year-end', 'value')],
    prevent_initial_call=True
)
def update_sim_year_range_buttons(all_clicks, current_clicks, current_last_clicks, year_start, year_end):
    ctx = dash.callback_context
    button_id = ctx.triggered[0]['prop_id'].split('.')[0]

    all_class = ""
    current_class = ""
    current_last_class = ""

    if button_id == 'sim-year-all':
        all_class = "active"
        return simulations_task.min_year, simulations_task.max_year, all_class, current_class, current_last_class
    elif button_id == 'sim-year-current':
        current_class = "active"
        return simulations_task.max_year, simulations_task.max_year, all_class, current_class, current_last_class
    elif button_id == 'sim-year-current-last':
        current_last_class = "active"
        return max(simulations_task.min_year, simulations_task.max_year - 1), simulations_task.max_year, all_class, current_class, current_last_class
    elif button_id in ['sim-year-start', 'sim-year-end']:
        if year_start == simulations_task.min_year and year_end == simulations_task.max_year:
            all_class = "active"
        elif year_start == simulations_task.max_year and year_end == simulations_task.max_year:
            current_class = "active"
        elif year_start == max(simulations_task.min_year, simulations_task.max_year - 1) and year_end == simulations_task.max_year:
            current_last_class = "active"
        return dash.no_update, dash.no_update, all_class, current_class, current_last_class

    return dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update

# Show/hide smoothing slider based on chart type
@callback(
    Output('sim-smoothing-section', 'style'),
    [Input('sim-chart-type', 'value')]
)
def toggle_sim_smoothing_visibility(chart_type):
    if chart_type == 'line':
        return {'display': 'block'}
    return {'display': 'none'}

# Update smoothing value display
@callback(
    Output('sim-smoothing-value', 'children'),
    [Input('sim-smoothing-slider', 'value')]
)
def update_sim_smoothing_value(value):
    if value == 0:
        return "Off"
    return f"{value}"

# Show/hide calendar-aligned controls based on comparison mode
@callback(
    Output('sim-calendar-aligned-controls', 'style'),
    [Input('sim-comparison-mode', 'value')]
)
def toggle_sim_calendar_aligned(comparison_mode):
    if comparison_mode == 'location':
        return {'display': 'block'}
    return {'display': 'none'}

# Show/hide historical stats controls based on comparison mode
@callback(
    Output('sim-historical-stats-controls', 'style'),
    [Input('sim-comparison-mode', 'value'),
     Input('sim-aggregation-dropdown', 'value')]
)
def toggle_sim_historical_stats(comparison_mode, aggregation):
    if comparison_mode == 'previous_periods' and aggregation == 'Daily':
        return {'display': 'block'}
    return {'display': 'none'}

# Period type button callbacks
@callback(
    [Output('sim-period-type-year', 'className'),
     Output('sim-period-type-quarter', 'className'),
     Output('sim-period-type-month', 'className')],
    [Input('sim-period-type-year', 'n_clicks'),
     Input('sim-period-type-quarter', 'n_clicks'),
     Input('sim-period-type-month', 'n_clicks')],
    prevent_initial_call=True
)
def update_sim_period_type_buttons(year_clicks, quarter_clicks, month_clicks):
    ctx = dash.callback_context
    button_id = ctx.triggered[0]['prop_id'].split('.')[0]

    year_class = ""
    quarter_class = ""
    month_class = ""

    if button_id == 'sim-period-type-year':
        year_class = "active"
    elif button_id == 'sim-period-type-quarter':
        quarter_class = "active"
    elif button_id == 'sim-period-type-month':
        month_class = "active"

    return year_class, quarter_class, month_class

# Update period type store based on button clicks
@callback(
    Output('sim-period-type', 'data'),
    [Input('sim-period-type-year', 'n_clicks'),
     Input('sim-period-type-quarter', 'n_clicks'),
     Input('sim-period-type-month', 'n_clicks')],
    prevent_initial_call=True
)
def update_sim_period_type_store(year_clicks, quarter_clicks, month_clicks):
    ctx = dash.callback_context
    button_id = ctx.triggered[0]['prop_id'].split('.')[0]

    if button_id == 'sim-period-type-year':
        return 'year'
    elif button_id == 'sim-period-type-quarter':
        return 'quarter'
    elif button_id == 'sim-period-type-month':
        return 'month'

    return 'year'

# Main chart update callback
@callback(
    [Output('sim-metric-total-tasks', 'children'),
     Output('sim-metric-date-range', 'children'),
     Output('sim-metric-avg-physician', 'children'),
     Output('sim-metric-avg-day', 'children'),
     Output('sim-main-chart', 'figure'),
     Output('sim-data-table', 'children')],
    [Input('sim-location-checklist', 'value'),
     Input('sim-type-checklist', 'value'),
     Input('sim-year-start', 'value'),
     Input('sim-year-end', 'value'),
     Input('sim-aggregation-dropdown', 'value'),
     Input('sim-chart-type', 'value'),
     Input('sim-comparison-mode', 'value'),
     Input('sim-smoothing-slider', 'value'),
     Input('sim-calendar-aligned', 'value'),
     Input('sim-period-type', 'data'),
     Input('sim-show-mean', 'value'),
     Input('sim-show-std-dev', 'value'),
     Input('sim-show-median', 'value'),
     Input('sim-show-ci', 'value')]
)
def update_sim_visualizations(locations, sim_types, year_start, year_end,
                              aggregation, chart_type, comparison_mode, smoothing,
                              calendar_aligned, period_type,
                              show_mean, show_std_dev, show_median, show_ci):
    """Update all visualizations based on filter selections"""
    import pandas as pd

    # Handle None values
    if year_start is None or year_end is None:
        year_start = simulations_task.min_year
        year_end = simulations_task.max_year

    year_range = (year_start, year_end)

    # Convert calendar_aligned list to boolean
    is_calendar_aligned = 'aligned' in (calendar_aligned or [])

    # Build stats options dict
    stats_options = {
        'show_mean': 'mean' in (show_mean or []),
        'show_std_dev': 'std' in (show_std_dev or []),
        'show_median': 'median' in (show_median or []),
        'show_ci': 'ci' in (show_ci or [])
    }

    # Filter data
    filtered_df = simulations_task.filter_data(locations, sim_types, year_range)

    # Calculate metrics
    metrics = simulations_task.calculate_metrics(filtered_df)

    # Create chart
    fig = simulations_task.create_chart(
        filtered_df,
        aggregation=aggregation,
        chart_type=chart_type,
        comparison_mode=comparison_mode,
        smoothing=smoothing,
        year_range=year_range,
        stats_options=stats_options,
        calendar_aligned=is_calendar_aligned,
        period_type=period_type if period_type else 'year'
    )

    # Create summary table
    if not filtered_df.empty:
        # Group by location and simulation type
        summary = filtered_df.groupby(['Location', 'SimulationType']).size().reset_index(name='Count')
        summary = summary.sort_values('Count', ascending=False)

        # Create DataTable with purple header and sortable columns
        table = dash_table.DataTable(
            data=summary.to_dict('records'),
            columns=[
                {'name': 'Location', 'id': 'Location'},
                {'name': 'Simulation Type', 'id': 'SimulationType'},
                {'name': 'Count', 'id': 'Count'}
            ],
            style_table={'overflowX': 'auto'},
            style_cell={
                'textAlign': 'center',
                'padding': '8px 12px',
                'fontFamily': '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto',
                'fontSize': '13px',
                'whiteSpace': 'normal',
                'height': 'auto'
            },
            style_cell_conditional=[
                {
                    'if': {'column_id': 'Location'},
                    'textAlign': 'left',
                    'fontWeight': '500'
                },
                {
                    'if': {'column_id': 'SimulationType'},
                    'textAlign': 'left'
                }
            ],
            style_header={
                'backgroundColor': 'rgb(124, 42, 131)',
                'color': 'white',
                'fontWeight': 'bold',
                'textAlign': 'center',
                'padding': '10px'
            },
            style_data={
                'borderBottom': '1px solid #E8E8E8'
            },
            style_data_conditional=[
                {
                    'if': {'row_index': 'odd'},
                    'backgroundColor': '#F8F9FA'
                }
            ],
            sort_action='native',
            sort_mode='single'
        )
    else:
        table = html.Div("No data available", style={'padding': '20px', 'textAlign': 'center', 'color': '#6c757d'})

    return (
        f"{metrics['total_simulations']:,}",
        f"{metrics['date_range']:,}",
        f"{metrics['avg_per_location']:.1f}",
        f"{metrics['avg_per_day']:.2f}",
        fig,
        table
    )
