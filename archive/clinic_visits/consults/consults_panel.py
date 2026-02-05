"""
Consults main panel layout and callbacks
"""
from dash import html, dcc, Input, Output, State, callback, dash_table
import dash_bootstrap_components as dbc
import dash
import pandas as pd


def create_main_panel_layout():
    """
    Create main content panel layout for Consults task.

    Returns:
        Dash component for main panel
    """
    return html.Div([
        # Metrics
        dbc.Row([
            dbc.Col([
                dbc.Card([
                    dbc.CardBody([
                        html.H6("Total Consults", className="text-muted"),
                        html.H3(id="consults-metric-total-tasks")
                    ])
                ])
            ], width=3),
            dbc.Col([
                dbc.Card([
                    dbc.CardBody([
                        html.H6("Date Range (Days)", className="text-muted"),
                        html.H3(id="consults-metric-date-range")
                    ])
                ])
            ], width=3),
            dbc.Col([
                dbc.Card([
                    dbc.CardBody([
                        html.H6("Avg per Physician", className="text-muted"),
                        html.H3(id="consults-metric-avg-physician")
                    ])
                ])
            ], width=3),
            dbc.Col([
                dbc.Card([
                    dbc.CardBody([
                        html.H6("Avg per Day", className="text-muted"),
                        html.H3(id="consults-metric-avg-day")
                    ])
                ])
            ], width=3),
        ], style={'marginBottom': '20px'}),

        # Chart
        dcc.Graph(id='consults-main-chart', style={
            'height': '500px',
            'border': '1px solid #dee2e6',
            'borderRadius': '4px',
            'boxShadow': '0 2px 4px rgba(0,0,0,0.1)'
        }),

        # Duration Histogram
        html.Div([
            html.H5("Appointment Duration Distribution", style={'marginTop': '30px', 'marginBottom': '15px'}),
            dcc.Graph(id='consults-duration-histogram', style={
                'height': '400px',
                'border': '1px solid #dee2e6',
                'borderRadius': '4px',
                'boxShadow': '0 2px 4px rgba(0,0,0,0.1)'
            })
        ]),

        # Data Table
        html.Div([
            html.Div([
                html.H5("Summary Table", style={'marginTop': '30px', 'marginBottom': '15px', 'display': 'inline-block'}),
                html.I(className="fas fa-download", id='consults-export-table', style={
                    'marginLeft': '15px',
                    'fontSize': '16px',
                    'color': 'rgb(124, 42, 131)',
                    'cursor': 'pointer'
                })
            ]),
            dash_table.DataTable(
                id='consults-data-table',
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
    Register all callbacks for Consults task.

    Args:
        app: Dash application instance
        task: ConsultsTask instance
    """

    # Store task reference globally so callbacks can access whichever task is currently active
    app._current_consults_task = task

    @callback(
        Output('consults-year-start', 'value'),
        Output('consults-year-end', 'value'),
        Output('consults-year-all', 'className'),
        Output('consults-year-current', 'className'),
        Output('consults-year-current-last', 'className'),
        Input('consults-year-all', 'n_clicks'),
        Input('consults-year-current', 'n_clicks'),
        Input('consults-year-current-last', 'n_clicks'),
        Input('consults-year-start', 'value'),
        Input('consults-year-end', 'value'),
        prevent_initial_call=True
    )
    def update_year_range_buttons(all_clicks, current_clicks, current_last_clicks, year_start, year_end):
        current_task = app._current_consults_task
        ctx = dash.callback_context
        button_id = ctx.triggered[0]['prop_id'].split('.')[0]

        all_class = ""
        current_class = ""
        current_last_class = ""

        if button_id == 'consults-year-all':
            all_class = "active"
            return current_task.min_year, current_task.max_year, all_class, current_class, current_last_class
        elif button_id == 'consults-year-current':
            current_class = "active"
            return current_task.max_year, current_task.max_year, all_class, current_class, current_last_class
        elif button_id == 'consults-year-current-last':
            current_last_class = "active"
            return max(current_task.min_year, current_task.max_year - 1), current_task.max_year, all_class, current_class, current_last_class
        elif button_id in ['consults-year-start', 'consults-year-end']:
            if year_start == current_task.min_year and year_end == current_task.max_year:
                all_class = "active"
            elif year_start == current_task.max_year and year_end == current_task.max_year:
                current_class = "active"
            elif year_start == max(current_task.min_year, current_task.max_year - 1) and year_end == current_task.max_year:
                current_last_class = "active"
            return dash.no_update, dash.no_update, all_class, current_class, current_last_class

        return dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update

    @callback(
        Output('consults-physician-checklist', 'options'),
        Output('consults-physician-checklist', 'value'),
        Input('consults-year-start', 'value'),
        Input('consults-year-end', 'value'),
        Input('consults-select-all-phys', 'n_clicks'),
        Input('consults-clear-all-phys', 'n_clicks'),
        prevent_initial_call=False
    )
    def update_physicians(year_start, year_end, select_all, clear_all):
        current_task = app._current_consults_task
        ctx = dash.callback_context

        year_range = [year_start, year_end]
        available_physicians = current_task.get_physicians_for_year_range(year_range)
        options = [{"label": p, "value": p} for p in available_physicians]

        if not ctx.triggered or ctx.triggered[0]['prop_id'] == '.':
            return options, available_physicians

        button_id = ctx.triggered[0]['prop_id'].split('.')[0]

        if button_id in ['consults-year-start', 'consults-year-end']:
            current_value = dash.callback_context.states.get('consults-physician-checklist.value', available_physicians)
            if current_value is None:
                current_value = available_physicians
            new_value = [p for p in current_value if p in available_physicians]
            return options, new_value
        elif button_id == 'consults-select-all-phys':
            return options, available_physicians
        elif button_id == 'consults-clear-all-phys':
            return options, []

        return dash.no_update, dash.no_update

    @callback(
        Output('consults-department-checklist', 'value'),
        Input('consults-select-all-dept', 'n_clicks'),
        Input('consults-clear-all-dept', 'n_clicks'),
        prevent_initial_call=True
    )
    def update_departments(select_all, clear_all):
        current_task = app._current_consults_task
        ctx = dash.callback_context
        button_id = ctx.triggered[0]['prop_id'].split('.')[0]

        if button_id == 'consults-select-all-dept':
            return current_task.departments
        elif button_id == 'consults-clear-all-dept':
            return []
        return dash.no_update

    @callback(
        Output('consults-phys-accordion-title', 'title'),
        Input('consults-physician-checklist', 'value'),
        Input('consults-physician-checklist', 'options')
    )
    def update_phys_title(selected, options):
        if selected is None:
            selected = []
        total_available = len(options) if options else 0
        return f"{len(selected)} of {total_available} selected"

    @callback(
        Output('consults-dept-accordion-title', 'title'),
        Input('consults-department-checklist', 'value')
    )
    def update_dept_title(selected):
        current_task = app._current_consults_task
        if selected is None:
            selected = current_task.departments
        return f"{len(selected)} of {len(current_task.departments)} selected"

    @callback(
        Output('consults-activity-checklist', 'value'),
        Input('consults-select-all-act', 'n_clicks'),
        Input('consults-clear-all-act', 'n_clicks'),
        prevent_initial_call=True
    )
    def update_activities(select_all, clear_all):
        current_task = app._current_consults_task
        ctx = dash.callback_context
        button_id = ctx.triggered[0]['prop_id'].split('.')[0]

        if button_id == 'consults-select-all-act':
            return current_task.activity_names
        elif button_id == 'consults-clear-all-act':
            return []
        return dash.no_update

    @callback(
        Output('consults-act-accordion-title', 'title'),
        Input('consults-activity-checklist', 'value')
    )
    def update_act_title(selected):
        current_task = app._current_consults_task
        if selected is None:
            selected = current_task.activity_names
        return f"{len(selected)} of {len(current_task.activity_names)} selected"

    @callback(
        Output('consults-type-checklist', 'value'),
        Input('consults-select-all-type', 'n_clicks'),
        Input('consults-clear-all-type', 'n_clicks'),
        prevent_initial_call=True
    )
    def update_appointment_types(select_all, clear_all):
        current_task = app._current_consults_task
        ctx = dash.callback_context
        button_id = ctx.triggered[0]['prop_id'].split('.')[0]

        if button_id == 'consults-select-all-type':
            return current_task.appointment_types
        elif button_id == 'consults-clear-all-type':
            return []
        return dash.no_update

    @callback(
        Output('consults-type-accordion-title', 'title'),
        Input('consults-type-checklist', 'value')
    )
    def update_type_title(selected):
        current_task = app._current_consults_task
        if selected is None:
            selected = current_task.appointment_types
        return f"{len(selected)} of {len(current_task.appointment_types)} selected"

    @callback(
        Output('consults-smoothing-section', 'style'),
        Input('consults-chart-type', 'value')
    )
    def update_smoothing_visibility(chart_type):
        if chart_type == 'line':
            return {'display': 'block'}
        else:
            return {'display': 'none'}

    @callback(
        Output('consults-historical-stats-controls', 'style'),
        Input('consults-comparison-mode', 'value'),
        Input('consults-aggregation-dropdown', 'value')
    )
    def update_stats_controls_visibility(comparison_mode, aggregation):
        if comparison_mode == 'previous_periods' and aggregation == 'Daily':
            return {'display': 'block'}
        else:
            return {'display': 'none'}

    @callback(
        Output('consults-calendar-aligned-controls', 'style'),
        Input('consults-comparison-mode', 'value')
    )
    def update_calendar_aligned_visibility(comparison_mode):
        if comparison_mode == 'physician':
            return {'display': 'block'}
        else:
            return {'display': 'none'}

    @callback(
        Output('consults-period-type-year', 'className'),
        Output('consults-period-type-month', 'className'),
        Output('consults-period-type-quarter', 'className'),
        Input('consults-period-type-year', 'n_clicks'),
        Input('consults-period-type-month', 'n_clicks'),
        Input('consults-period-type-quarter', 'n_clicks')
    )
    def update_period_type_buttons(year_clicks, month_clicks, quarter_clicks):
        ctx = dash.callback_context
        if not ctx.triggered:
            return "active", "", ""

        button_id = ctx.triggered[0]['prop_id'].split('.')[0]

        if button_id == 'consults-period-type-year':
            return "active", "", ""
        elif button_id == 'consults-period-type-month':
            return "", "active", ""
        elif button_id == 'consults-period-type-quarter':
            return "", "", "active"
        return "active", "", ""

    @callback(
        Output('consults-show-mean', 'value'),
        Input('consults-chart-type', 'value'),
        Input('consults-comparison-mode', 'value'),
        Input('consults-aggregation-dropdown', 'value'),
        State('consults-show-mean', 'value'),
        State('consults-show-median', 'value')
    )
    def auto_select_mean_for_bar_chart(chart_type, comparison_mode, aggregation, current_mean, current_median):
        if chart_type == 'bar' and comparison_mode == 'previous_periods' and aggregation == 'Daily':
            mean_selected = 'mean' in (current_mean or [])
            median_selected = 'median' in (current_median or [])
            if not mean_selected and not median_selected:
                return ['mean']
        return dash.no_update

    @callback(
        Output('consults-show-mean', 'value', allow_duplicate=True),
        Output('consults-show-median', 'value'),
        Input('consults-show-mean', 'value'),
        Input('consults-show-median', 'value'),
        Input('consults-chart-type', 'value'),
        Input('consults-comparison-mode', 'value'),
        Input('consults-aggregation-dropdown', 'value'),
        State('consults-show-mean', 'value'),
        State('consults-show-median', 'value'),
        prevent_initial_call=True
    )
    def enforce_single_statistic_selection(mean_val, median_val, chart_type, comparison_mode, aggregation, prev_mean, prev_median):
        ctx = dash.callback_context
        if not ctx.triggered:
            return dash.no_update, dash.no_update

        if chart_type == 'bar' and comparison_mode == 'previous_periods' and aggregation == 'Daily':
            trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]

            mean_selected = 'mean' in (mean_val or [])
            median_selected = 'median' in (median_val or [])

            if mean_selected and median_selected:
                if trigger_id == 'consults-show-mean':
                    return ['mean'], []
                elif trigger_id == 'consults-show-median':
                    return [], ['median']

            if not mean_selected and not median_selected:
                prev_mean_selected = 'mean' in (prev_mean or [])
                if prev_mean_selected:
                    return ['mean'], []
                else:
                    return [], ['median']

        return dash.no_update, dash.no_update

    @callback(
        Output('consults-show-std-dev', 'options'),
        Output('consults-show-ci', 'options'),
        Output('consults-show-std-dev', 'value'),
        Output('consults-show-ci', 'value'),
        Input('consults-show-mean', 'value'),
        Input('consults-show-median', 'value'),
        Input('consults-show-std-dev', 'value'),
        Input('consults-show-ci', 'value'),
        Input('consults-chart-type', 'value'),
        Input('consults-comparison-mode', 'value'),
        Input('consults-aggregation-dropdown', 'value')
    )
    def update_error_band_state(show_mean, show_median, std_val, ci_val, chart_type, comparison_mode, aggregation):
        ctx = dash.callback_context

        mean_or_median_selected = ('mean' in (show_mean or [])) or ('median' in (show_median or []))
        is_bar_comparison = (chart_type == 'bar' and comparison_mode == 'previous_periods' and aggregation == 'Daily')

        if mean_or_median_selected:
            std_options = [{'label': ' Std Dev', 'value': 'std'}]
            ci_options = [{'label': ' 95% CI', 'value': 'ci'}]

            current_std = std_val or []
            current_ci = ci_val or []

            if is_bar_comparison and ctx.triggered:
                trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]
                std_selected = 'std' in current_std
                ci_selected = 'ci' in current_ci

                if std_selected and ci_selected:
                    if trigger_id == 'consults-show-std-dev':
                        return std_options, ci_options, ['std'], []
                    elif trigger_id == 'consults-show-ci':
                        return std_options, ci_options, [], ['ci']

            return std_options, ci_options, current_std, current_ci
        else:
            std_options = [{'label': ' Std Dev', 'value': 'std', 'disabled': True}]
            ci_options = [{'label': ' 95% CI', 'value': 'ci', 'disabled': True}]
            return std_options, ci_options, [], []

    @callback(
        Output('consults-smoothing-value', 'children', allow_duplicate=True),
        Input('consults-smoothing-slider', 'value'),
        prevent_initial_call=True
    )
    def update_smoothing_display(smoothing_value):
        if smoothing_value == 0:
            return "Off"
        else:
            return f"{smoothing_value}"

    @callback(
        Output('consults-main-chart', 'figure'),
        Output('consults-duration-histogram', 'figure'),
        Output('consults-metric-total-tasks', 'children'),
        Output('consults-metric-date-range', 'children'),
        Output('consults-metric-avg-physician', 'children'),
        Output('consults-metric-avg-day', 'children'),
        Output('consults-data-table', 'data'),
        Output('consults-data-table', 'columns'),
        Input('consults-physician-checklist', 'value'),
        Input('consults-department-checklist', 'value'),
        Input('consults-activity-checklist', 'value'),
        Input('consults-type-checklist', 'value'),
        Input('consults-year-start', 'value'),
        Input('consults-year-end', 'value'),
        Input('consults-aggregation-dropdown', 'value'),
        Input('consults-chart-type', 'value'),
        Input('consults-comparison-mode', 'value'),
        Input('consults-smoothing-slider', 'value'),
        Input('consults-show-mean', 'value'),
        Input('consults-show-std-dev', 'value'),
        Input('consults-show-median', 'value'),
        Input('consults-show-ci', 'value'),
        Input('consults-calendar-aligned', 'value'),
        Input('consults-period-type-year', 'className'),
        Input('consults-period-type-month', 'className'),
        Input('consults-period-type-quarter', 'className')
    )
    def update_chart(selected_phys, selected_depts, selected_acts, selected_types, year_start, year_end, aggregation, chart_type, comparison_mode, smoothing,
                     show_mean, show_std_dev, show_median, show_ci, calendar_aligned, year_class, month_class, quarter_class):
        current_task = app._current_consults_task
        year_range = [year_start, year_end]
        # Filter data
        filtered_df = current_task.filter_data(selected_phys, selected_depts, selected_acts, selected_types, year_range)

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
        period_type = 'year'
        if 'active' in (month_class or ''):
            period_type = 'month'
        elif 'active' in (quarter_class or ''):
            period_type = 'quarter'

        # Create chart
        fig = current_task.create_chart(filtered_df, aggregation, chart_type, comparison_mode,
                                selected_phys if selected_phys else current_task.physicians, smoothing,
                                year_range=(year_start, year_end), stats_options=stats_options,
                                calendar_aligned=is_calendar_aligned, period_type=period_type)

        # Prepare aggregated table data
        if filtered_df.empty:
            table_data = []
            table_columns = []
        else:
            table_aggregation = aggregation
            if comparison_mode == 'previous_periods' and 'active' in (year_class or month_class or quarter_class):
                if 'active' in (month_class or ''):
                    table_aggregation = 'Monthly'
                elif 'active' in (quarter_class or ''):
                    table_aggregation = 'Quarterly'
                elif 'active' in (year_class or ''):
                    table_aggregation = 'Yearly'

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

            summary = filtered_df.groupby(['FirstMD', 'Period']).size().reset_index(name='count')
            pivot_table = summary.pivot(index='Period', columns='FirstMD', values='count').fillna(0).astype(int)
            pivot_table['Total'] = pivot_table.sum(axis=1)
            pivot_table = pivot_table.reset_index()
            pivot_table.columns.name = None
            pivot_table = pivot_table.rename(columns={'Period': 'Period'})

            table_data = pivot_table.to_dict('records')
            table_columns = [{"name": col, "id": col} for col in pivot_table.columns]

        # Create duration histogram
        import plotly.graph_objects as go
        import numpy as np

        if filtered_df.empty or 'ActivityPlannedLength' not in filtered_df.columns:
            # Empty histogram
            duration_fig = go.Figure()
            duration_fig.update_layout(
                title="No duration data available",
                plot_bgcolor='white',
                paper_bgcolor='white'
            )
        else:
            # Calculate duration (use ActivityPlannedLength if available, otherwise calculate from timestamps)
            df_with_duration = filtered_df.copy()

            # Try to use ActivityPlannedLength column
            if 'ActivityPlannedLength' in df_with_duration.columns:
                df_with_duration['Duration'] = pd.to_numeric(df_with_duration['ActivityPlannedLength'], errors='coerce')
            else:
                # Calculate from timestamps if available
                if 'ActivityStartDateTime' in df_with_duration.columns and 'ActivityEndDateTime' in df_with_duration.columns:
                    df_with_duration['Duration'] = (
                        pd.to_datetime(df_with_duration['ActivityEndDateTime'], errors='coerce') -
                        pd.to_datetime(df_with_duration['ActivityStartDateTime'], errors='coerce')
                    ).dt.total_seconds() / 60  # Convert to minutes
                else:
                    df_with_duration['Duration'] = np.nan

            # Remove invalid durations
            df_with_duration = df_with_duration[df_with_duration['Duration'].notna() & (df_with_duration['Duration'] > 0)]

            if df_with_duration.empty:
                duration_fig = go.Figure()
                duration_fig.update_layout(
                    title="No valid duration data available",
                    plot_bgcolor='white',
                    paper_bgcolor='white'
                )
            else:
                # Create histogram
                duration_fig = go.Figure()
                duration_fig.add_trace(go.Histogram(
                    x=df_with_duration['Duration'],
                    nbinsx=30,
                    marker_color='#8B5CF6',
                    opacity=0.7,
                    name='Consults'
                ))

                # Add mean line
                mean_duration = df_with_duration['Duration'].mean()
                duration_fig.add_vline(
                    x=mean_duration,
                    line_dash="dash",
                    line_color="red",
                    annotation_text=f"Mean: {mean_duration:.1f} min",
                    annotation_position="top"
                )

                # Add median line
                median_duration = df_with_duration['Duration'].median()
                duration_fig.add_vline(
                    x=median_duration,
                    line_dash="dash",
                    line_color="green",
                    annotation_text=f"Median: {median_duration:.1f} min",
                    annotation_position="bottom"
                )

                duration_fig.update_layout(
                    title="Appointment Duration Distribution",
                    xaxis_title="Duration (minutes)",
                    yaxis_title="Number of Appointments",
                    plot_bgcolor='white',
                    paper_bgcolor='white',
                    font=dict(color='#2C3E50', size=12),
                    xaxis=dict(
                        showgrid=True,
                        gridcolor='#ECF0F1',
                        zeroline=True,
                        zerolinewidth=1,
                        zerolinecolor='#6c757d'
                    ),
                    yaxis=dict(
                        showgrid=True,
                        gridcolor='#ECF0F1',
                        zeroline=True,
                        zerolinewidth=1,
                        zerolinecolor='#6c757d'
                    ),
                    height=400,
                    showlegend=False
                )

        return (
            fig,
            duration_fig,
            f"{metrics['total_tasks']:,}",
            f"{metrics['date_range']:,}",
            f"{metrics['avg_per_physician']:,.0f}",
            f"{metrics['avg_per_day']:.1f}",
            table_data,
            table_columns
        )
