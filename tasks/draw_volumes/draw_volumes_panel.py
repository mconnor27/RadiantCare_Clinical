"""
Draw Volumes main panel layout and callbacks
"""
from dash import html, dcc, Input, Output, callback
import dash_bootstrap_components as dbc
import dash


def create_main_panel_layout():
    """
    Create main content panel layout for Draw Volumes task.

    Returns:
        Dash component for main panel
    """
    return html.Div([
        html.H4("Task Completion Analysis", style={'marginBottom': '20px'}),

        # Metrics
        dbc.Row([
            dbc.Col([
                dbc.Card([
                    dbc.CardBody([
                        html.H6("Total Tasks", className="text-muted"),
                        html.H3(id="metric-total-tasks")
                    ])
                ])
            ], width=3),
            dbc.Col([
                dbc.Card([
                    dbc.CardBody([
                        html.H6("Date Range (Days)", className="text-muted"),
                        html.H3(id="metric-date-range")
                    ])
                ])
            ], width=3),
            dbc.Col([
                dbc.Card([
                    dbc.CardBody([
                        html.H6("Avg per Physician", className="text-muted"),
                        html.H3(id="metric-avg-physician")
                    ])
                ])
            ], width=3),
            dbc.Col([
                dbc.Card([
                    dbc.CardBody([
                        html.H6("Avg per Day", className="text-muted"),
                        html.H3(id="metric-avg-day")
                    ])
                ])
            ], width=3),
        ], style={'marginBottom': '20px'}),

        # Chart
        dcc.Graph(id='main-chart', style={'height': '500px'}),
    ])


def register_callbacks(app, task):
    """
    Register all callbacks for Draw Volumes task.

    Args:
        app: Dash application instance
        task: DrawVolumesTask instance
    """

    @callback(
        Output('physician-checklist', 'value'),
        Input('select-all-phys', 'n_clicks'),
        Input('clear-all-phys', 'n_clicks'),
        prevent_initial_call=True
    )
    def update_physicians(select_all, clear_all):
        ctx = dash.callback_context
        button_id = ctx.triggered[0]['prop_id'].split('.')[0]

        if button_id == 'select-all-phys':
            return task.physicians
        elif button_id == 'clear-all-phys':
            return []
        return dash.no_update

    @callback(
        Output('activity-checklist', 'value'),
        Input('select-all-act', 'n_clicks'),
        Input('clear-all-act', 'n_clicks'),
        prevent_initial_call=True
    )
    def update_activities(select_all, clear_all):
        ctx = dash.callback_context
        button_id = ctx.triggered[0]['prop_id'].split('.')[0]

        if button_id == 'select-all-act':
            return task.activity_names
        elif button_id == 'clear-all-act':
            return []
        return dash.no_update

    @callback(
        Output('phys-accordion-title', 'title'),
        Input('physician-checklist', 'value')
    )
    def update_phys_title(selected):
        if selected is None:
            selected = task.physicians
        return f"{len(selected)} of {len(task.physicians)} selected"

    @callback(
        Output('act-accordion-title', 'title'),
        Input('activity-checklist', 'value')
    )
    def update_act_title(selected):
        if selected is None:
            selected = task.activity_names
        return f"{len(selected)} of {len(task.activity_names)} selected"

    @callback(
        Output('main-chart', 'figure'),
        Output('metric-total-tasks', 'children'),
        Output('metric-date-range', 'children'),
        Output('metric-avg-physician', 'children'),
        Output('metric-avg-day', 'children'),
        Input('physician-checklist', 'value'),
        Input('activity-checklist', 'value'),
        Input('year-range-slider', 'value'),
        Input('aggregation-dropdown', 'value'),
        Input('chart-type', 'value'),
        Input('comparison-mode', 'value')
    )
    def update_chart(selected_phys, selected_acts, year_range, aggregation, chart_type, comparison_mode):
        # Filter data
        filtered_df = task.filter_data(selected_phys, selected_acts, year_range)

        # Calculate metrics
        metrics = task.calculate_metrics(filtered_df, selected_phys if selected_phys else task.physicians)

        # Create chart
        fig = task.create_chart(filtered_df, aggregation, chart_type, comparison_mode,
                                selected_phys if selected_phys else task.physicians)

        return (
            fig,
            f"{metrics['total_tasks']:,}",
            f"{metrics['date_range']:,}",
            f"{metrics['avg_per_physician']:,.0f}",
            f"{metrics['avg_per_day']:.1f}"
        )
