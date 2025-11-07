"""
Consults sidebar layout (filters and controls)
"""
from dash import html, dcc
import dash_bootstrap_components as dbc


def create_sidebar_layout(task, state=None):
    """
    Create sidebar layout for Consults task.

    Args:
        task: ConsultsTask instance
        state: Optional dict with persisted state values (from sidebar-state-store)

    Returns:
        Dash component for sidebar
    """
    # Use persisted state if available, otherwise use defaults
    if state is None:
        state = {}

    # Get values from state or defaults
    physician_value = state.get('physicians') if state.get('physicians') is not None else task.physicians
    # Department filter (placeholder for now)
    department_value = state.get('departments') if state.get('departments') is not None else task.departments
    # Activity names always reset (use task defaults)
    activity_value = task.activity_names
    # Appointment types always reset (use task defaults)
    appointment_type_value = task.appointment_types
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

    # Ensure physician_value contains only physicians that exist in current task
    physician_value = [p for p in physician_value if p in task.physicians] if physician_value else task.physicians
    # If all physicians were filtered out, use all available
    if not physician_value:
        physician_value = task.physicians

    # Ensure department_value contains only departments that exist in current task
    department_value = [d for d in department_value if d in task.departments] if department_value else task.departments
    if not department_value:
        department_value = task.departments

    return html.Div([
        html.H5("Filters & Options", style={'marginBottom': '20px', 'marginTop': '20px'}),

        # Physician Filter
        html.Div([
            html.Label("Primary Oncologist", style={'fontWeight': 'bold', 'marginBottom': '10px'}),
            dbc.Accordion([
                dbc.AccordionItem([
                    html.Div([
                        dbc.Row([
                            dbc.Col(dbc.Button("All", id="consults-select-all-phys", size="sm", color="secondary", className="w-100"), width=6),
                            dbc.Col(dbc.Button("None", id="consults-clear-all-phys", size="sm", color="secondary", className="w-100"), width=6),
                        ])
                    ], className="button-panel purple-panel"),
                    html.Div([
                        dbc.Checklist(
                            id="consults-physician-checklist",
                            options=[{"label": p, "value": p} for p in task.physicians],
                            value=physician_value,
                            className="purple-checkbox"
                        )
                    ])
                ], title=f"{len(physician_value)} of {len(task.physicians)} selected", id="consults-phys-accordion-title")
            ], start_collapsed=True, id="consults-physician-accordion")
        ], className='filter-section'),

        # Department Filter (placeholder)
        html.Div([
            html.Label("Department", style={'fontWeight': 'bold', 'marginBottom': '10px'}),
            dbc.Accordion([
                dbc.AccordionItem([
                    html.Div([
                        dbc.Row([
                            dbc.Col(dbc.Button("All", id="consults-select-all-dept", size="sm", color="secondary", className="w-100"), width=6),
                            dbc.Col(dbc.Button("None", id="consults-clear-all-dept", size="sm", color="secondary", className="w-100"), width=6),
                        ])
                    ], className="button-panel red-panel"),
                    html.Div([
                        dbc.Checklist(
                            id="consults-department-checklist",
                            options=[{"label": d, "value": d} for d in task.departments],
                            value=department_value,
                            className="red-checkbox"
                        ),
                        html.P("No departments available", style={'color': '#999', 'fontStyle': 'italic', 'marginTop': '10px', 'display': 'none' if task.departments else 'block'})
                    ])
                ], title=f"{len(department_value)} of {len(task.departments)} selected" if task.departments else "0 of 0 selected", id="consults-dept-accordion-title")
            ], start_collapsed=True, id="consults-department-accordion")
        ], className='filter-section'),

        # Activity Name Filter
        html.Div([
            html.Label("Activity Name", style={'fontWeight': 'bold', 'marginBottom': '10px'}),
            dbc.Accordion([
                dbc.AccordionItem([
                    html.Div([
                        dbc.Row([
                            dbc.Col(dbc.Button("All", id="consults-select-all-act", size="sm", color="secondary", className="w-100"), width=6),
                            dbc.Col(dbc.Button("None", id="consults-clear-all-act", size="sm", color="secondary", className="w-100"), width=6),
                        ])
                    ], className="button-panel red-panel"),
                    html.Div([
                        dbc.Checklist(
                            id="consults-activity-checklist",
                            options=[{"label": a, "value": a} for a in task.activity_names],
                            value=activity_value,
                            className="red-checkbox"
                        )
                    ])
                ], title=f"{len(activity_value)} of {len(task.activity_names)} selected", id="consults-act-accordion-title")
            ], start_collapsed=True, id="consults-activity-accordion")
        ], className='filter-section'),

        # Appointment Type Filter
        html.Div([
            html.Label("Appointment Type", style={'fontWeight': 'bold', 'marginBottom': '10px'}),
            dbc.Accordion([
                dbc.AccordionItem([
                    html.Div([
                        dbc.Row([
                            dbc.Col(dbc.Button("All", id="consults-select-all-type", size="sm", color="secondary", className="w-100"), width=6),
                            dbc.Col(dbc.Button("None", id="consults-clear-all-type", size="sm", color="secondary", className="w-100"), width=6),
                        ])
                    ], className="button-panel blue-panel"),
                    html.Div([
                        dbc.Checklist(
                            id="consults-type-checklist",
                            options=[{"label": t, "value": t} for t in task.appointment_types],
                            value=appointment_type_value,
                            className="blue-checkbox"
                        )
                    ])
                ], title=f"{len(appointment_type_value)} of {len(task.appointment_types)} selected", id="consults-type-accordion-title")
            ], start_collapsed=True, id="consults-type-accordion")
        ], className='filter-section'),

        html.Hr(),

        # Year Range Dropdowns
        html.Div([
            html.Label("Year Range", style={'fontWeight': 'bold', 'marginBottom': '10px'}),
            # Quick select buttons
            html.Div([
                dbc.Button("All", id="consults-year-all", size="sm", className="active"),
                dbc.Button("YTD", id="consults-year-current", size="sm"),
                dbc.Button("YTD & Prior", id="consults-year-current-last", size="sm"),
            ], className='year-select-buttons'),
            dbc.Row([
                dbc.Col([
                    html.Label("From", style={'fontSize': '0.85em', 'marginBottom': '5px', 'color': '#666'}),
                    dcc.Dropdown(
                        id='consults-year-start',
                        options=[{'label': str(y), 'value': y} for y in range(task.min_year, task.max_year + 1)],
                        value=year_start_value,
                        clearable=False
                    )
                ], width=6),
                dbc.Col([
                    html.Label("To", style={'fontSize': '0.85em', 'marginBottom': '5px', 'color': '#666'}),
                    dcc.Dropdown(
                        id='consults-year-end',
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
                id='consults-aggregation-dropdown',
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
                id='consults-chart-type',
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
                html.Span(id='consults-smoothing-value', style={
                    'float': 'right',
                    'fontSize': '0.85em',
                    'color': '#3498DB',
                    'fontWeight': '600',
                    'marginTop': '2px'
                })
            ], style={'marginBottom': '10px'}),
            dcc.Slider(
                id='consults-smoothing-slider',
                min=0,
                max=10,
                step=0.5,
                value=smoothing_value,
                marks={0: '0', 2.5: '2.5', 5: '5', 7.5: '7.5', 10: '10'},
                tooltip={"placement": "bottom", "always_visible": False}
            )
        ], id='consults-smoothing-section', className='filter-section', style={'display': 'none'}),

        html.Hr(),

        # Comparison Mode
        html.Div([
            html.H6("Comparison Mode", style={'fontWeight': 'bold'}),
            dcc.Dropdown(
                id='consults-comparison-mode',
                options=[
                    {'label': 'None', 'value': 'none'},
                    {'label': 'Physician', 'value': 'physician'},
                    {'label': 'Previous Time Periods', 'value': 'previous_periods'}
                ],
                value=comparison_mode_value,
                clearable=False
            )
        ], className='filter-section'),

        # Calendar-aligned checkbox (only visible in physician comparison mode)
        html.Div([
            dbc.Checklist(
                id='consults-calendar-aligned',
                options=[{'label': ' Calendar-aligned', 'value': 'aligned'}],
                value=calendar_aligned_value,
                inline=True,
                switch=False
            )
        ], id='consults-calendar-aligned-controls', className='filter-section', style={'display': 'none'}),

        # Historical Period Type Controls (only visible in previous_periods mode)
        html.Div([
            html.Div([
                dbc.Button("Year", id="consults-period-type-year", size="sm", className="active" if period_type_value == 'year' else ""),
                dbc.Button("Quarter", id="consults-period-type-quarter", size="sm", className="active" if period_type_value == 'quarter' else ""),
                dbc.Button("Month", id="consults-period-type-month", size="sm", className="active" if period_type_value == 'month' else ""),
            ], className='year-select-buttons', style={'marginBottom': '15px'}),
            dbc.Row([
                dbc.Col([
                    dbc.Checklist(
                        id='consults-show-mean',
                        options=[{'label': ' Mean', 'value': 'mean'}],
                        value=show_mean_value,
                        inline=True,
                        switch=False
                    )
                ], width=6),
                dbc.Col([
                    dbc.Checklist(
                        id='consults-show-std-dev',
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
                        id='consults-show-median',
                        options=[{'label': ' Median', 'value': 'median'}],
                        value=show_median_value,
                        inline=True,
                        switch=False
                    )
                ], width=6),
                dbc.Col([
                    dbc.Checklist(
                        id='consults-show-ci',
                        options=[{'label': ' 95% CI', 'value': 'ci'}],
                        value=show_ci_value,
                        inline=True,
                        switch=False
                    )
                ], width=6)
            ])
        ], id='consults-historical-stats-controls', className='filter-section', style={'display': 'none'})
    ], className='sidebar')
