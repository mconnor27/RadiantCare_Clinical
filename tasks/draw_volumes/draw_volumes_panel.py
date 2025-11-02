"""
Draw Volumes main panel layout and callbacks
"""
from dash import html, dcc, Input, Output, callback, dash_table
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

        # Data Table
        html.Div([
            html.H5("Summary Table", style={'marginTop': '30px', 'marginBottom': '15px'}),
            dash_table.DataTable(
                id='data-table',
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
                        'if': {'column_id': 'Period'},
                        'textAlign': 'left',
                        'fontWeight': '500'
                    },
                    {
                        'if': {'column_id': 'Total'},
                        'fontWeight': 'bold',
                        'backgroundColor': '#F0F8FF'
                    }
                ],
                css=[{
                    'selector': 'table',
                    'rule': 'table-layout: auto !important; width: auto !important;'
                }],
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
                export_format='xlsx',
                export_headers='display'
            )
        ])
    ])


def register_callbacks(app, task):
    """
    Register all callbacks for Draw Volumes task.

    Args:
        app: Dash application instance
        task: DrawVolumesTask instance
    """

    @callback(
        Output('year-start', 'value'),
        Output('year-end', 'value'),
        Output('year-all', 'className'),
        Output('year-current', 'className'),
        Output('year-current-last', 'className'),
        Input('year-all', 'n_clicks'),
        Input('year-current', 'n_clicks'),
        Input('year-current-last', 'n_clicks'),
        Input('year-start', 'value'),
        Input('year-end', 'value'),
        prevent_initial_call=True
    )
    def update_year_range_buttons(all_clicks, current_clicks, current_last_clicks, year_start, year_end):
        ctx = dash.callback_context
        button_id = ctx.triggered[0]['prop_id'].split('.')[0]

        # Default: no button active
        all_class = ""
        current_class = ""
        current_last_class = ""

        if button_id == 'year-all':
            all_class = "active"
            return task.min_year, task.max_year, all_class, current_class, current_last_class
        elif button_id == 'year-current':
            current_class = "active"
            return task.max_year, task.max_year, all_class, current_class, current_last_class
        elif button_id == 'year-current-last':
            current_last_class = "active"
            return max(task.min_year, task.max_year - 1), task.max_year, all_class, current_class, current_last_class
        elif button_id in ['year-start', 'year-end']:
            # User manually changed dropdown - check if it matches a preset
            if year_start == task.min_year and year_end == task.max_year:
                all_class = "active"
            elif year_start == task.max_year and year_end == task.max_year:
                current_class = "active"
            elif year_start == max(task.min_year, task.max_year - 1) and year_end == task.max_year:
                current_last_class = "active"
            # Don't change the dropdown values, just update button states
            return dash.no_update, dash.no_update, all_class, current_class, current_last_class

        return dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update

    @callback(
        Output('physician-checklist', 'options'),
        Output('physician-checklist', 'value'),
        Input('year-start', 'value'),
        Input('year-end', 'value'),
        Input('select-all-phys', 'n_clicks'),
        Input('clear-all-phys', 'n_clicks'),
        prevent_initial_call=False
    )
    def update_physicians(year_start, year_end, select_all, clear_all):
        ctx = dash.callback_context

        # Get physicians for the current year range
        year_range = [year_start, year_end]
        available_physicians = task.get_physicians_for_year_range(year_range)
        options = [{"label": p, "value": p} for p in available_physicians]

        if not ctx.triggered or ctx.triggered[0]['prop_id'] == '.':
            # Initial load
            return options, available_physicians

        button_id = ctx.triggered[0]['prop_id'].split('.')[0]

        if button_id in ['year-start', 'year-end']:
            # Year range changed - keep only physicians that are still available
            current_value = dash.callback_context.states.get('physician-checklist.value', available_physicians)
            if current_value is None:
                current_value = available_physicians
            # Keep selected physicians that are still in the available list
            new_value = [p for p in current_value if p in available_physicians]
            return options, new_value
        elif button_id == 'select-all-phys':
            return options, available_physicians
        elif button_id == 'clear-all-phys':
            return options, []

        return dash.no_update, dash.no_update

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
        Input('physician-checklist', 'value'),
        Input('physician-checklist', 'options')
    )
    def update_phys_title(selected, options):
        if selected is None:
            selected = []
        total_available = len(options) if options else 0
        return f"{len(selected)} of {total_available} selected"

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
        Output('data-table', 'data'),
        Output('data-table', 'columns'),
        Input('physician-checklist', 'value'),
        Input('activity-checklist', 'value'),
        Input('year-start', 'value'),
        Input('year-end', 'value'),
        Input('aggregation-dropdown', 'value'),
        Input('chart-type', 'value'),
        Input('comparison-mode', 'value')
    )
    def update_chart(selected_phys, selected_acts, year_start, year_end, aggregation, chart_type, comparison_mode):
        year_range = [year_start, year_end]
        # Filter data
        filtered_df = task.filter_data(selected_phys, selected_acts, year_range)

        # Calculate metrics
        metrics = task.calculate_metrics(filtered_df, selected_phys if selected_phys else task.physicians)

        # Create chart
        fig = task.create_chart(filtered_df, aggregation, chart_type, comparison_mode,
                                selected_phys if selected_phys else task.physicians)

        # Prepare aggregated table data (physicians as rows, periods as columns)
        if filtered_df.empty:
            table_data = []
            table_columns = []
        else:
            # Aggregate by time period and physician
            if aggregation == 'Daily':
                filtered_df['Period'] = filtered_df['AppointmentTime'].dt.strftime('%Y-%m-%d')
            elif aggregation == 'Weekly':
                filtered_df['Period'] = filtered_df['AppointmentTime'].dt.to_period('W').dt.start_time.dt.strftime('%Y-%m-%d')
            elif aggregation == 'Monthly':
                filtered_df['Period'] = filtered_df['AppointmentTime'].dt.strftime('%Y-%m')
            elif aggregation == 'Quarterly':
                filtered_df['Period'] = filtered_df['AppointmentTime'].dt.to_period('Q').astype(str)
            elif aggregation == 'Yearly':
                filtered_df['Period'] = filtered_df['AppointmentTime'].dt.year.astype(str)

            # Group by period and physician (aggregate all selected activities)
            summary = filtered_df.groupby(['FirstMD', 'Period']).size().reset_index(name='count')

            # Pivot to get periods as rows, physicians as columns
            pivot_table = summary.pivot(index='Period', columns='FirstMD', values='count').fillna(0).astype(int)

            # Add a Total column
            pivot_table['Total'] = pivot_table.sum(axis=1)

            # Reset index to make Period a column
            pivot_table = pivot_table.reset_index()
            pivot_table.columns.name = None

            # Rename Period column
            pivot_table = pivot_table.rename(columns={'Period': 'Period'})

            table_data = pivot_table.to_dict('records')
            table_columns = [{"name": col, "id": col} for col in pivot_table.columns]

        return (
            fig,
            f"{metrics['total_tasks']:,}",
            f"{metrics['date_range']:,}",
            f"{metrics['avg_per_physician']:,.0f}",
            f"{metrics['avg_per_day']:.1f}",
            table_data,
            table_columns
        )
