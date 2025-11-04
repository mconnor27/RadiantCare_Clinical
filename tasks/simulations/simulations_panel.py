"""
Simulations main panel layout and callbacks
"""
from dash import html, dcc, Input, Output, State, dash_table
import dash_bootstrap_components as dbc


def create_main_panel_layout():
    """Create the main panel layout for simulations task"""
    return html.Div([
        # Metrics cards
        dbc.Row([
            dbc.Col([
                dbc.Card([
                    dbc.CardBody([
                        html.H6("Total Simulations", className="text-muted"),
                        html.H3(id='metric-total-tasks', children='0')
                    ])
                ], className='metric-card')
            ], width=3),
            dbc.Col([
                dbc.Card([
                    dbc.CardBody([
                        html.H6("Date Range (Days)", className="text-muted"),
                        html.H3(id='metric-date-range', children='0')
                    ])
                ], className='metric-card')
            ], width=3),
            dbc.Col([
                dbc.Card([
                    dbc.CardBody([
                        html.H6("Avg per Location", className="text-muted"),
                        html.H3(id='metric-avg-physician', children='0')
                    ])
                ], className='metric-card')
            ], width=3),
            dbc.Col([
                dbc.Card([
                    dbc.CardBody([
                        html.H6("Avg per Day", className="text-muted"),
                        html.H3(id='metric-avg-day', children='0.0')
                    ])
                ], className='metric-card')
            ], width=3),
        ], className='mb-3'),

        # Chart
        dbc.Row([
            dbc.Col([
                dcc.Graph(id='main-chart', config={'displayModeBar': True})
            ], width=12)
        ]),

        # Data table
        dbc.Row([
            dbc.Col([
                html.H5("Simulation Data Summary", style={'marginTop': '30px', 'marginBottom': '15px'}),
                dbc.Table(id='data-table')
            ], width=12)
        ])
    ])


def register_callbacks(app, task):
    """Register callbacks for simulations panel"""

    # Year range quick select buttons
    @app.callback(
        [Output('sim-year-start', 'value', allow_duplicate=True),
         Output('sim-year-end', 'value', allow_duplicate=True)],
        [Input('sim-select-all-years', 'n_clicks'),
         Input('sim-select-last-5', 'n_clicks'),
         Input('sim-select-last-10', 'n_clicks')],
        [State('main-tabs', 'active_tab'),
         State('sim-year-start', 'value'),
         State('sim-year-end', 'value')],
        prevent_initial_call=True
    )
    def quick_select_sim_years(all_clicks, last_5_clicks, last_10_clicks, active_tab, current_start, current_end):
        """Handle quick select year buttons for simulations"""
        if active_tab != 'simulations':
            return current_start, current_end

        import dash
        ctx = dash.callback_context

        if not ctx.triggered:
            return current_start, current_end

        button_id = ctx.triggered[0]['prop_id'].split('.')[0]

        if button_id == 'sim-select-all-years':
            return task.min_year, task.max_year
        elif button_id == 'sim-select-last-5':
            return max(task.min_year, task.max_year - 4), task.max_year
        elif button_id == 'sim-select-last-10':
            return max(task.min_year, task.max_year - 9), task.max_year

        return current_start, current_end

    # Show/hide calendar-aligned checkbox based on comparison mode
    @app.callback(
        Output('sim-calendar-aligned-container', 'style'),
        [Input('sim-comparison-mode', 'value'),
         Input('main-tabs', 'active_tab')],
        prevent_initial_call=False
    )
    def toggle_sim_calendar_aligned(comparison_mode, active_tab):
        """Show calendar-aligned checkbox only when comparing by location"""
        if active_tab != 'simulations':
            return {'display': 'none'}

        if comparison_mode == 'location':
            return {'marginLeft': '20px', 'marginBottom': '20px'}
        return {'display': 'none'}

    # Update metrics, chart, and table
    @app.callback(
        [Output('metric-total-tasks', 'children', allow_duplicate=True),
         Output('metric-date-range', 'children', allow_duplicate=True),
         Output('metric-avg-physician', 'children', allow_duplicate=True),
         Output('metric-avg-day', 'children', allow_duplicate=True),
         Output('main-chart', 'figure', allow_duplicate=True),
         Output('data-table', 'children', allow_duplicate=True)],
        [Input('sim-location-checklist', 'value'),
         Input('sim-type-checklist', 'value'),
         Input('sim-year-start', 'value'),
         Input('sim-year-end', 'value'),
         Input('sim-aggregation-dropdown', 'value'),
         Input('sim-chart-type', 'value'),
         Input('sim-comparison-mode', 'value'),
         Input('sim-smoothing-slider', 'value'),
         Input('sim-calendar-aligned', 'value'),
         Input('main-tabs', 'active_tab')],
        prevent_initial_call=True
    )
    def update_simulations_visualizations(locations, sim_types, year_start, year_end,
                            aggregation, chart_type, comparison_mode, smoothing,
                            calendar_aligned, active_tab):
        """Update all visualizations based on filter selections"""
        import dash
        from dash.exceptions import PreventUpdate

        if active_tab != 'simulations':
            # Don't update if not on simulations tab
            raise PreventUpdate

        import pandas as pd

        # Handle None values
        if year_start is None or year_end is None:
            year_start = task.min_year
            year_end = task.max_year

        year_range = (year_start, year_end)

        # Convert calendar_aligned list to boolean
        is_calendar_aligned = 'aligned' in (calendar_aligned or [])

        # Filter data
        filtered_df = task.filter_data(locations, sim_types, year_range)

        # Calculate metrics
        metrics = task.calculate_metrics(filtered_df)

        # Create chart
        fig = task.create_chart(
            filtered_df,
            aggregation=aggregation,
            chart_type=chart_type,
            comparison_mode=comparison_mode,
            smoothing=smoothing,
            year_range=year_range,
            calendar_aligned=is_calendar_aligned
        )

        # Create summary table using the same format as draw_volumes
        if not filtered_df.empty:
            # Group by location and simulation type
            summary = filtered_df.groupby(['Location', 'SimulationType']).size().reset_index(name='Count')
            summary = summary.sort_values('Count', ascending=False)

            # Create table rows
            table_header = [
                html.Thead(html.Tr([html.Th("Location"), html.Th("Simulation Type"), html.Th("Count")]))
            ]
            table_body = [
                html.Tbody([
                    html.Tr([html.Td(row['Location']), html.Td(row['SimulationType']), html.Td(row['Count'])])
                    for _, row in summary.iterrows()
                ])
            ]
            table = dbc.Table(table_header + table_body, bordered=True, striped=True, hover=True, responsive=True)
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
