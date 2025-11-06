"""
Scheduling sidebar layout (filters and controls)
"""
from dash import html, dcc
import dash_bootstrap_components as dbc


def create_sidebar_layout(task, state=None):
    """
    Create sidebar layout for Scheduling task.

    Args:
        task: SchedulingTask instance
        state: Optional dict with persisted state values

    Returns:
        Dash component for sidebar
    """
    # Use persisted state if available, otherwise use defaults
    if state is None:
        state = {}

    # Get values from state or defaults
    department_value = state.get('departments') if state.get('departments') is not None else task.departments
    physician_value = state.get('physicians') if state.get('physicians') is not None else task.physicians
    activity_value = state.get('activity_types') if state.get('activity_types') is not None else task.activity_types
    view_mode_value = state.get('view_mode') if state.get('view_mode') is not None else 'calendar'
    time_range_value = state.get('time_range') if state.get('time_range') is not None else [8, 17]

    return html.Div([
        html.H5("Filters & Options", style={'marginBottom': '20px', 'marginTop': '20px'}),

        # View Mode Toggle
        html.Div([
            html.Label("View Mode", style={'fontWeight': 'bold', 'marginBottom': '10px'}),
            dbc.RadioItems(
                id="sched-view-mode",
                options=[
                    {"label": "Calendar View", "value": "calendar"},
                    {"label": "List View", "value": "list"}
                ],
                value=view_mode_value,
                inline=False,
                className="view-mode-radio"
            )
        ], className='filter-section'),

        html.Hr(),

        # Department Filter Buttons
        html.Div([
            html.Label("Department", style={'fontWeight': 'bold', 'marginBottom': '10px'}),
            html.Div([
                dbc.Button(
                    "Lacey",
                    id="sched-dept-btn-lacey",
                    className="dept-filter-btn dept-filter-btn-active dept-filter-btn-lacey",
                    n_clicks=0
                ),
                dbc.Button(
                    "Centralia",
                    id="sched-dept-btn-centralia",
                    className="dept-filter-btn dept-filter-btn-active dept-filter-btn-centralia",
                    n_clicks=0
                ),
                dbc.Button(
                    "Aberdeen",
                    id="sched-dept-btn-aberdeen",
                    className="dept-filter-btn dept-filter-btn-active dept-filter-btn-aberdeen",
                    n_clicks=0
                ),
            ], style={'display': 'flex', 'gap': '0px', 'flexWrap': 'wrap'})
        ], className='filter-section'),

        # Physician Filter Buttons (2x2 grid)
        html.Div([
            html.Label("Physician", style={'fontWeight': 'bold', 'marginBottom': '10px'}),
            html.Div([
                # First row
                html.Div([
                    dbc.Button(
                        task.physicians[0].split(', ')[0] if len(task.physicians) > 0 else "",
                        id="sched-phys-btn-0",
                        className="phys-filter-btn phys-filter-btn-active",
                        n_clicks=0,
                        style={'width': 'calc(50% - 1.5px)'}
                    ),
                    dbc.Button(
                        task.physicians[1].split(', ')[0] if len(task.physicians) > 1 else "",
                        id="sched-phys-btn-1",
                        className="phys-filter-btn phys-filter-btn-active",
                        n_clicks=0,
                        style={'width': 'calc(50% - 1.5px)', 'marginLeft': '3px'}
                    ),
                ], style={'display': 'flex', 'marginBottom': '3px'}),
                # Second row
                html.Div([
                    dbc.Button(
                        task.physicians[2].split(', ')[0] if len(task.physicians) > 2 else "",
                        id="sched-phys-btn-2",
                        className="phys-filter-btn phys-filter-btn-active",
                        n_clicks=0,
                        style={'width': 'calc(50% - 1.5px)'}
                    ),
                    dbc.Button(
                        task.physicians[3].split(', ')[0] if len(task.physicians) > 3 else "",
                        id="sched-phys-btn-3",
                        className="phys-filter-btn phys-filter-btn-active",
                        n_clicks=0,
                        style={'width': 'calc(50% - 1.5px)', 'marginLeft': '3px'}
                    ),
                ], style={'display': 'flex'}),
            ])
        ], className='filter-section'),

        # Appointment Type Filter Buttons
        html.Div([
            html.Label("Appointment Type", style={'fontWeight': 'bold', 'marginBottom': '10px'}),
            html.Div([
                dbc.Button(
                    "Consult",
                    id="sched-appt-btn-consult",
                    className="appt-filter-btn appt-filter-btn-active",
                    n_clicks=0,
                    style={'width': 'calc(50% - 1.5px)'}
                ),
                dbc.Button(
                    "Follow Up",
                    id="sched-appt-btn-followup",
                    className="appt-filter-btn appt-filter-btn-active",
                    n_clicks=0,
                    style={'width': 'calc(50% - 1.5px)', 'marginLeft': '3px'}
                ),
            ], style={'display': 'flex'})
        ], className='filter-section'),

        html.Hr(),

        # Time Range Filter
        html.Div([
            html.Label("Time of Day", style={'fontWeight': 'bold', 'marginBottom': '10px'}),
            html.Div(id='sched-time-range-display', style={'textAlign': 'center', 'marginBottom': '10px', 'fontSize': '14px'}),
            dcc.RangeSlider(
                id='sched-time-range-slider',
                min=8,
                max=17,
                step=1,
                value=time_range_value,
                marks={
                    8: '8a',
                    12: '12p',
                    17: '5p'
                },
                tooltip={"placement": "bottom", "always_visible": False},
                className='time-range-slider'
            )
        ], className='filter-section'),

    ])
