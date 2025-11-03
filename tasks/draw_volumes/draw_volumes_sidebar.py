"""
Draw Volumes sidebar layout (filters and controls)
"""
from dash import html, dcc
import dash_bootstrap_components as dbc


def create_sidebar_layout(task):
    """
    Create sidebar layout for Draw Volumes task.

    Args:
        task: DrawVolumesTask instance

    Returns:
        Dash component for sidebar
    """
    return html.Div([
        html.H5("Filters & Options", style={'marginBottom': '20px', 'marginTop': '20px'}),

        # Physician Filter
        html.Div([
            html.Label("Primary Oncologist", style={'fontWeight': 'bold', 'marginBottom': '10px'}),
            dbc.Accordion([
                dbc.AccordionItem([
                    html.Div([
                        dbc.Row([
                            dbc.Col(dbc.Button("All", id="select-all-phys", size="sm", color="secondary", className="w-100"), width=6),
                            dbc.Col(dbc.Button("None", id="clear-all-phys", size="sm", color="secondary", className="w-100"), width=6),
                        ])
                    ], className="button-panel purple-panel"),
                    html.Div([
                        dbc.Checklist(
                            id="physician-checklist",
                            options=[{"label": p, "value": p} for p in task.physicians],
                            value=task.physicians,
                            className="purple-checkbox"
                        )
                    ])
                ], title=f"{len(task.physicians)} of {len(task.physicians)} selected", id="phys-accordion-title")
            ], start_collapsed=True, id="physician-accordion")
        ], className='filter-section'),

        # Activity Filter
        html.Div([
            html.Label("Activity Name", style={'fontWeight': 'bold', 'marginBottom': '10px'}),
            dbc.Accordion([
                dbc.AccordionItem([
                    html.Div([
                        dbc.Row([
                            dbc.Col(dbc.Button("All", id="select-all-act", size="sm", color="secondary", className="w-100"), width=6),
                            dbc.Col(dbc.Button("None", id="clear-all-act", size="sm", color="secondary", className="w-100"), width=6),
                        ])
                    ], className="button-panel red-panel"),
                    html.Div([
                        dbc.Checklist(
                            id="activity-checklist",
                            options=[{"label": a, "value": a} for a in task.activity_names],
                            value=task.activity_names,
                            className="red-checkbox"
                        )
                    ])
                ], title=f"{len(task.activity_names)} of {len(task.activity_names)} selected", id="act-accordion-title")
            ], start_collapsed=True, id="activity-accordion")
        ], className='filter-section'),

        html.Hr(),

        # Year Range Dropdowns
        html.Div([
            html.Label("Year Range", style={'fontWeight': 'bold', 'marginBottom': '10px'}),
            # Quick select buttons
            html.Div([
                dbc.Button("All", id="year-all", size="sm", className="active"),
                dbc.Button("YTD", id="year-current", size="sm"),
                dbc.Button("YTD & Prior", id="year-current-last", size="sm"),
            ], className='year-select-buttons'),
            dbc.Row([
                dbc.Col([
                    html.Label("From", style={'fontSize': '0.85em', 'marginBottom': '5px', 'color': '#666'}),
                    dcc.Dropdown(
                        id='year-start',
                        options=[{'label': str(y), 'value': y} for y in range(task.min_year, task.max_year + 1)],
                        value=task.min_year,
                        clearable=False
                    )
                ], width=6),
                dbc.Col([
                    html.Label("To", style={'fontSize': '0.85em', 'marginBottom': '5px', 'color': '#666'}),
                    dcc.Dropdown(
                        id='year-end',
                        options=[{'label': str(y), 'value': y} for y in range(task.min_year, task.max_year + 1)],
                        value=task.max_year,
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
                id='aggregation-dropdown',
                options=[
                    {'label': 'None (Cumulative)', 'value': 'Daily'},
                    {'label': 'Daily', 'value': 'Daily-NonCumulative'},
                    {'label': 'Weekly', 'value': 'Weekly'},
                    {'label': 'Monthly', 'value': 'Monthly'},
                    {'label': 'Quarterly', 'value': 'Quarterly'},
                    {'label': 'Yearly', 'value': 'Yearly'}
                ],
                value='Daily',
                clearable=False
            )
        ], className='filter-section'),

        # Chart Type
        html.Div([
            html.Label("Chart Type", style={'fontWeight': 'bold'}),
            dbc.RadioItems(
                id='chart-type',
                options=[
                    {'label': 'Line Chart', 'value': 'line'},
                    {'label': 'Bar Chart', 'value': 'bar'}
                ],
                value='line'
            )
        ], className='filter-section'),

        # Smoothing (only for line charts)
        html.Div([
            html.Div([
                html.Label("Smoothing", style={'fontWeight': 'bold', 'marginBottom': '10px', 'display': 'inline-block'}),
                html.Span(id='smoothing-value', style={
                    'float': 'right',
                    'fontSize': '0.85em',
                    'color': '#3498DB',
                    'fontWeight': '600',
                    'marginTop': '2px'
                })
            ], style={'marginBottom': '10px'}),
            dcc.Slider(
                id='smoothing-slider',
                min=0,
                max=10,
                step=0.5,
                value=0,
                marks={0: '0', 2.5: '2.5', 5: '5', 7.5: '7.5', 10: '10'},
                tooltip={"placement": "bottom", "always_visible": False}
            )
        ], id='smoothing-section', className='filter-section', style={'display': 'none'}),

        html.Hr(),

        # Comparison Mode
        html.Div([
            html.H6("Comparison Mode", style={'fontWeight': 'bold'}),
            dcc.Dropdown(
                id='comparison-mode',
                options=[
                    {'label': 'None', 'value': 'none'},
                    {'label': 'Physician', 'value': 'physician'},
                    {'label': 'Previous Time Periods', 'value': 'previous_periods'}
                ],
                value='none',
                clearable=False
            )
        ], className='filter-section'),

        # Calendar-aligned checkbox (only visible in physician comparison mode)
        html.Div([
            dbc.Checklist(
                id='calendar-aligned',
                options=[{'label': ' Calendar-aligned', 'value': 'aligned'}],
                value=[],
                inline=True,
                switch=False
            )
        ], id='calendar-aligned-controls', className='filter-section', style={'display': 'none'}),

        # Historical Period Type Controls (only visible in previous_periods mode)
        html.Div([
            html.Div([
                dbc.Button("Year", id="period-type-year", size="sm", className="active"),
                dbc.Button("Quarter", id="period-type-quarter", size="sm"),
                dbc.Button("Month", id="period-type-month", size="sm"),
            ], className='year-select-buttons', style={'marginBottom': '15px'}),
            dbc.Row([
                dbc.Col([
                    dbc.Checklist(
                        id='show-mean',
                        options=[{'label': ' Mean', 'value': 'mean'}],
                        value=[],
                        inline=True,
                        switch=False
                    )
                ], width=6),
                dbc.Col([
                    dbc.Checklist(
                        id='show-std-dev',
                        options=[{'label': ' Std Dev', 'value': 'std'}],
                        value=[],
                        inline=True,
                        switch=False
                    )
                ], width=6)
            ], style={'marginBottom': '8px'}),
            dbc.Row([
                dbc.Col([
                    dbc.Checklist(
                        id='show-median',
                        options=[{'label': ' Median', 'value': 'median'}],
                        value=[],
                        inline=True,
                        switch=False
                    )
                ], width=6),
                dbc.Col([
                    dbc.Checklist(
                        id='show-ci',
                        options=[{'label': ' 95% CI', 'value': 'ci'}],
                        value=[],
                        inline=True,
                        switch=False
                    )
                ], width=6)
            ])
        ], id='historical-stats-controls', className='filter-section', style={'display': 'none'})
    ], className='sidebar')
