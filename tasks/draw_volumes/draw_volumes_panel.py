"""
Draw Volumes main panel layout and callbacks
"""
from dash import html, dcc, Input, Output, State, callback, dash_table
import dash_bootstrap_components as dbc
import dash


def create_main_panel_layout():
    """
    Create main content panel layout for Draw Volumes task.

    Returns:
        Dash component for main panel
    """
    return html.Div([
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
        dcc.Graph(id='main-chart', style={
            'height': '500px',
            'border': '1px solid #dee2e6',
            'borderRadius': '4px',
            'boxShadow': '0 2px 4px rgba(0,0,0,0.1)'
        }),

        # Data Table
        html.Div([
            html.Div([
                html.H5("Summary Table", style={'marginTop': '30px', 'marginBottom': '15px', 'display': 'inline-block'}),
                html.I(className="fas fa-download", id='export-table', style={
                    'marginLeft': '15px',
                    'fontSize': '16px',
                    'color': 'rgb(124, 42, 131)',
                    'cursor': 'pointer'
                })
            ]),
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
                sort_mode='single'
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

    # Store task reference globally so callbacks can access whichever task is currently active
    # This will be updated by the render_content callback
    app._current_task = task

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
        current_task = app._current_task
        ctx = dash.callback_context
        button_id = ctx.triggered[0]['prop_id'].split('.')[0]

        # Default: no button active
        all_class = ""
        current_class = ""
        current_last_class = ""

        if button_id == 'year-all':
            all_class = "active"
            return current_task.min_year, current_task.max_year, all_class, current_class, current_last_class
        elif button_id == 'year-current':
            current_class = "active"
            return current_task.max_year, current_task.max_year, all_class, current_class, current_last_class
        elif button_id == 'year-current-last':
            current_last_class = "active"
            return max(current_task.min_year, current_task.max_year - 1), current_task.max_year, all_class, current_class, current_last_class
        elif button_id in ['year-start', 'year-end']:
            # User manually changed dropdown - check if it matches a preset
            if year_start == current_task.min_year and year_end == current_task.max_year:
                all_class = "active"
            elif year_start == current_task.max_year and year_end == current_task.max_year:
                current_class = "active"
            elif year_start == max(current_task.min_year, current_task.max_year - 1) and year_end == current_task.max_year:
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
        current_task = app._current_task
        ctx = dash.callback_context

        # Get physicians for the current year range
        year_range = [year_start, year_end]
        available_physicians = current_task.get_physicians_for_year_range(year_range)
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
        current_task = app._current_task
        ctx = dash.callback_context
        button_id = ctx.triggered[0]['prop_id'].split('.')[0]

        if button_id == 'select-all-act':
            return current_task.activity_names
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
        current_task = app._current_task
        if selected is None:
            selected = current_task.activity_names
        return f"{len(selected)} of {len(current_task.activity_names)} selected"

    @callback(
        Output('smoothing-section', 'style'),
        Input('chart-type', 'value')
    )
    def update_smoothing_visibility(chart_type):
        if chart_type == 'line':
            return {'display': 'block'}
        else:
            return {'display': 'none'}

    @callback(
        Output('historical-stats-controls', 'style'),
        Input('comparison-mode', 'value'),
        Input('aggregation-dropdown', 'value')
    )
    def update_stats_controls_visibility(comparison_mode, aggregation):
        if comparison_mode == 'previous_periods' and aggregation == 'Daily':
            return {'display': 'block'}
        else:
            return {'display': 'none'}

    @callback(
        Output('calendar-aligned-controls', 'style'),
        Input('comparison-mode', 'value')
    )
    def update_calendar_aligned_visibility(comparison_mode):
        if comparison_mode == 'physician':
            return {'display': 'block'}
        else:
            return {'display': 'none'}

    @callback(
        Output('period-type-year', 'className'),
        Output('period-type-month', 'className'),
        Output('period-type-quarter', 'className'),
        Input('period-type-year', 'n_clicks'),
        Input('period-type-month', 'n_clicks'),
        Input('period-type-quarter', 'n_clicks')
    )
    def update_period_type_buttons(year_clicks, month_clicks, quarter_clicks):
        ctx = dash.callback_context
        if not ctx.triggered:
            return "active", "", ""

        button_id = ctx.triggered[0]['prop_id'].split('.')[0]

        if button_id == 'period-type-year':
            return "active", "", ""
        elif button_id == 'period-type-month':
            return "", "active", ""
        elif button_id == 'period-type-quarter':
            return "", "", "active"
        return "active", "", ""

    @callback(
        Output('show-mean', 'value'),
        Input('chart-type', 'value'),
        Input('comparison-mode', 'value'),
        Input('aggregation-dropdown', 'value'),
        State('show-mean', 'value'),
        State('show-median', 'value')
    )
    def auto_select_mean_for_bar_chart(chart_type, comparison_mode, aggregation, current_mean, current_median):
        # Auto-select Mean when entering bar chart + previous periods mode
        if chart_type == 'bar' and comparison_mode == 'previous_periods' and aggregation == 'Daily':
            # If neither mean nor median is selected, default to mean
            mean_selected = 'mean' in (current_mean or [])
            median_selected = 'median' in (current_median or [])
            if not mean_selected and not median_selected:
                return ['mean']
        return dash.no_update

    @callback(
        Output('show-mean', 'value', allow_duplicate=True),
        Output('show-median', 'value'),
        Input('show-mean', 'value'),
        Input('show-median', 'value'),
        Input('chart-type', 'value'),
        Input('comparison-mode', 'value'),
        Input('aggregation-dropdown', 'value'),
        State('show-mean', 'value'),
        State('show-median', 'value'),
        prevent_initial_call=True
    )
    def enforce_single_statistic_selection(mean_val, median_val, chart_type, comparison_mode, aggregation, prev_mean, prev_median):
        ctx = dash.callback_context
        if not ctx.triggered:
            return dash.no_update, dash.no_update

        # Only enforce in bar chart + previous periods mode
        if chart_type == 'bar' and comparison_mode == 'previous_periods' and aggregation == 'Daily':
            trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]

            mean_selected = 'mean' in (mean_val or [])
            median_selected = 'median' in (median_val or [])

            # If both are selected, unselect the one that wasn't just clicked
            if mean_selected and median_selected:
                if trigger_id == 'show-mean':
                    return ['mean'], []
                elif trigger_id == 'show-median':
                    return [], ['median']

            # If neither is selected, select mean (user tried to unselect the last one)
            if not mean_selected and not median_selected:
                prev_mean_selected = 'mean' in (prev_mean or [])
                if prev_mean_selected:
                    return ['mean'], []
                else:
                    return [], ['median']

        return dash.no_update, dash.no_update

    @callback(
        Output('show-std-dev', 'options'),
        Output('show-ci', 'options'),
        Output('show-std-dev', 'value'),
        Output('show-ci', 'value'),
        Input('show-mean', 'value'),
        Input('show-median', 'value'),
        Input('show-std-dev', 'value'),
        Input('show-ci', 'value'),
        Input('chart-type', 'value'),
        Input('comparison-mode', 'value'),
        Input('aggregation-dropdown', 'value')
    )
    def update_error_band_state(show_mean, show_median, std_val, ci_val, chart_type, comparison_mode, aggregation):
        ctx = dash.callback_context

        # Enable error bands only if mean or median is selected
        mean_or_median_selected = ('mean' in (show_mean or [])) or ('median' in (show_median or []))

        # In bar chart + previous periods mode, enforce single error bar selection
        is_bar_comparison = (chart_type == 'bar' and comparison_mode == 'previous_periods' and aggregation == 'Daily')

        if mean_or_median_selected:
            # Enable the checkboxes
            std_options = [{'label': ' Std Dev', 'value': 'std'}]
            ci_options = [{'label': ' 95% CI', 'value': 'ci'}]

            current_std = std_val or []
            current_ci = ci_val or []

            # In bar mode, enforce only one error bar type
            if is_bar_comparison and ctx.triggered:
                trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]
                std_selected = 'std' in current_std
                ci_selected = 'ci' in current_ci

                # If both are selected, unselect the one that wasn't just clicked
                if std_selected and ci_selected:
                    if trigger_id == 'show-std-dev':
                        return std_options, ci_options, ['std'], []
                    elif trigger_id == 'show-ci':
                        return std_options, ci_options, [], ['ci']

            return std_options, ci_options, current_std, current_ci
        else:
            # Disable the checkboxes
            std_options = [{'label': ' Std Dev', 'value': 'std', 'disabled': True}]
            ci_options = [{'label': ' 95% CI', 'value': 'ci', 'disabled': True}]
            # Clear the values
            return std_options, ci_options, [], []

    @callback(
        Output('smoothing-value', 'children', allow_duplicate=True),
        Input('smoothing-slider', 'value'),
        prevent_initial_call=True
    )
    def update_smoothing_display(smoothing_value):
        if smoothing_value == 0:
            return "Off"
        else:
            return f"{smoothing_value}"

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
        Input('comparison-mode', 'value'),
        Input('smoothing-slider', 'value'),
        Input('show-mean', 'value'),
        Input('show-std-dev', 'value'),
        Input('show-median', 'value'),
        Input('show-ci', 'value'),
        Input('calendar-aligned', 'value'),
        Input('period-type-year', 'className'),
        Input('period-type-month', 'className'),
        Input('period-type-quarter', 'className')
    )
    def update_chart(selected_phys, selected_acts, year_start, year_end, aggregation, chart_type, comparison_mode, smoothing,
                     show_mean, show_std_dev, show_median, show_ci, calendar_aligned, year_class, month_class, quarter_class):
        current_task = app._current_task
        year_range = [year_start, year_end]
        # Filter data
        filtered_df = current_task.filter_data(selected_phys, selected_acts, year_range)

        # Calculate metrics
        metrics = current_task.calculate_metrics(filtered_df, selected_phys if selected_phys else current_task.physicians)

        # Prepare stats options
        stats_options = {
            'show_mean': 'mean' in (show_mean or []),
            'show_std_dev': 'std' in (show_std_dev or []),
            'show_median': 'median' in (show_median or []),
            'show_ci': 'ci' in (show_ci or [])
        }

        # Check if calendar-aligned mode is enabled
        is_calendar_aligned = 'aligned' in (calendar_aligned or [])

        # Determine period type for previous_periods mode
        period_type = 'year'  # default
        if 'active' in (month_class or ''):
            period_type = 'month'
        elif 'active' in (quarter_class or ''):
            period_type = 'quarter'

        # Create chart
        fig = current_task.create_chart(filtered_df, aggregation, chart_type, comparison_mode,
                                selected_phys if selected_phys else current_task.physicians, smoothing,
                                year_range=(year_start, year_end), stats_options=stats_options,
                                calendar_aligned=is_calendar_aligned, period_type=period_type)

        # Prepare aggregated table data (physicians as rows, periods as columns)
        if filtered_df.empty:
            table_data = []
            table_columns = []
        else:
            # Determine aggregation type for table
            # If in "Previous Time Periods" comparison mode, use the selected period type
            table_aggregation = aggregation
            if comparison_mode == 'previous_periods' and 'active' in (year_class or month_class or quarter_class):
                if 'active' in (month_class or ''):
                    table_aggregation = 'Monthly'
                elif 'active' in (quarter_class or ''):
                    table_aggregation = 'Quarterly'
                elif 'active' in (year_class or ''):
                    table_aggregation = 'Yearly'

            # Aggregate by time period and physician
            if table_aggregation == 'Daily' or table_aggregation == 'Daily-NonCumulative':
                filtered_df['Period'] = filtered_df['AppointmentTime'].dt.strftime('%Y-%m-%d')
            elif table_aggregation == 'Weekly':
                filtered_df['Period'] = filtered_df['AppointmentTime'].dt.to_period('W').dt.start_time.dt.strftime('%Y-%m-%d')
            elif table_aggregation == 'Monthly':
                filtered_df['Period'] = filtered_df['AppointmentTime'].dt.strftime('%Y-%m')
            elif table_aggregation == 'Quarterly':
                filtered_df['Period'] = filtered_df['AppointmentTime'].dt.to_period('Q').astype(str)
            elif table_aggregation == 'Yearly':
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
