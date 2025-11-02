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
                    {'label': 'Daily (Cumulative)', 'value': 'Daily'},
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

        html.Hr(),

        # Comparison Mode
        html.Div([
            html.H6("Comparison Mode", style={'fontWeight': 'bold'}),
            dcc.Dropdown(
                id='comparison-mode',
                options=[
                    {'label': 'None', 'value': 'none'},
                    {'label': 'Physician', 'value': 'physician'}
                ],
                value='none',
                clearable=False
            )
        ], className='filter-section')
    ], className='sidebar')
