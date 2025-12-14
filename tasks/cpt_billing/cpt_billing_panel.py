"""
CPT Billing main panel layout (summary table display)
"""
from dash import html, dcc, dash_table, Input, Output, State
import dash_bootstrap_components as dbc
import plotly.graph_objects as go


def create_main_panel_layout():
    """
    Create main panel layout for CPT Billing task.

    Returns:
        Dash component for main panel
    """
    return html.Div([
        html.Div([
            html.H5("2026 CPT Code Analysis", style={'marginTop': '20px', 'marginBottom': '20px', 'display': 'inline-block'}),
            html.Div([
                dbc.Button("Export to CSV", id="cpt-export-csv", color="primary", size="sm", style={'marginRight': '10px'}),
                dbc.Button("Export to Excel", id="cpt-export-excel", color="success", size="sm"),
            ], style={'display': 'inline-block', 'float': 'right', 'marginTop': '20px'})
        ], style={'overflow': 'hidden'}),

        # Parallel categories diagram
        html.Div([
            html.H6("Treatment Flow Analysis", style={'marginTop': '30px', 'marginBottom': '15px', 'textAlign': 'center'}),
            html.Div([
                html.Label("Select dimensions to include (in order):", style={'fontWeight': 'bold', 'marginRight': '15px'}),
                dcc.Checklist(
                    id='cpt-parallel-dimensions',
                    options=[
                        {'label': ' Actual Billing Codes', 'value': 'actual_codes'},
                        {'label': ' 2026 Codes', 'value': '2026_codes'},
                        {'label': ' Department', 'value': 'department'},
                        {'label': ' Machine', 'value': 'machine'},
                        {'label': ' Insurer Category', 'value': 'insurer_category'},
                        {'label': ' Technique', 'value': 'technique'},
                        {'label': ' Radiation Type', 'value': 'radiation_type'}
                    ],
                    value=['machine', 'insurer_category'],
                    inline=True,
                    labelStyle={'marginRight': '15px'},
                    inputStyle={'marginRight': '5px'}
                )
            ], style={'textAlign': 'center', 'marginBottom': '15px'}),
            dcc.Graph(id='cpt-parallel-diagram', style={'height': '700px'})
        ], style={'marginBottom': '40px'}),

        # Summary table
        html.Div([
            html.H6("Code Summary Table", style={'marginTop': '20px', 'marginBottom': '15px', 'textAlign': 'center'}),
            html.Div(id='cpt-summary-table-container', children=[
                dash_table.DataTable(
                    id='cpt-summary-table',
                    columns=[
                        {'name': 'Code Type', 'id': 'Type'},
                        {'name': 'Code', 'id': 'Code'},
                        {'name': 'Count', 'id': 'Count'},
                        {'name': 'Percentage', 'id': 'Percentage'}
                    ],
                    data=[],
                    style_table={'overflowX': 'auto'},
                    style_cell={
                        'textAlign': 'left',
                        'padding': '10px',
                        'fontSize': '14px'
                    },
                    style_header={
                        'backgroundColor': 'rgb(230, 230, 230)',
                        'fontWeight': 'bold'
                    },
                    style_data_conditional=[
                        {
                            'if': {'filter_query': '{Type} = "2026 Billing Code"'},
                            'backgroundColor': 'rgb(248, 248, 255)'
                        },
                        {
                            'if': {'filter_query': '{Type} = "Actual Billing Code"'},
                            'backgroundColor': 'rgb(255, 248, 248)'
                        }
                    ],
                    sort_action='native',
                    filter_action='native'
                )
            ], style={'maxWidth': '800px', 'margin': '0 auto'})
        ]),

        # Download components
        dcc.Download(id="cpt-download-csv"),
        dcc.Download(id="cpt-download-excel")
    ])


def register_callbacks(app, task):
    """
    Register callbacks for CPT Billing panel.

    Args:
        app: Dash app instance
        task: CPTBillingTask instance
    """

    @app.callback(
        Output('cpt-summary-table', 'data'),
        [Input('cpt-department-checklist', 'value'),
         Input('cpt-machine-checklist', 'value'),
         Input('cpt-insurer-category-checklist', 'value'),
         Input('cpt-insurer-checklist', 'value'),
         Input('cpt-start-date', 'date'),
         Input('cpt-end-date', 'date'),
         Input('cpt-technique-checklist', 'value'),
         Input('cpt-2026code-checklist', 'value'),
         Input('cpt-radiation-type-checklist', 'value'),
         Input('cpt-actual-code-checklist', 'value')]
    )
    def update_summary_table(selected_departments, selected_machines, selected_insurer_categories, selected_insurers,
                           start_date, end_date, selected_techniques, selected_codes_2026,
                           selected_radiation_types, selected_actual_codes):
        """
        Update the summary table based on filter selections.

        Args:
            selected_departments: List of selected departments
            selected_machines: List of selected machines
            selected_insurer_categories: List of selected insurer categories
            selected_insurers: List of selected insurers
            start_date: Start date string
            end_date: End date string

        Returns:
            List of dicts for table data
        """
        # Filter data
        filtered_df = task.filter_data(
            selected_departments,
            selected_machines,
            selected_insurer_categories,
            selected_insurers,
            start_date,
            end_date,
            selected_techniques,
            selected_codes_2026,
            selected_radiation_types,
            selected_actual_codes
        )

        # Calculate code summary
        summary_df = task.calculate_code_summary(filtered_df)

        # Convert to dict for DataTable
        return summary_df.to_dict('records')

    @app.callback(
        Output('cpt-parallel-diagram', 'figure'),
        [Input('cpt-department-checklist', 'value'),
         Input('cpt-machine-checklist', 'value'),
         Input('cpt-insurer-category-checklist', 'value'),
         Input('cpt-insurer-checklist', 'value'),
         Input('cpt-start-date', 'date'),
         Input('cpt-end-date', 'date'),
         Input('cpt-technique-checklist', 'value'),
         Input('cpt-2026code-checklist', 'value'),
         Input('cpt-radiation-type-checklist', 'value'),
         Input('cpt-actual-code-checklist', 'value'),
         Input('cpt-parallel-dimensions', 'value')]
    )
    def update_parallel_diagram(selected_departments, selected_machines, selected_insurer_categories, selected_insurers,
                              start_date, end_date, selected_techniques, selected_codes_2026,
                              selected_radiation_types, selected_actual_codes, parallel_dimensions):
        """
        Update the parallel categories diagram based on filter selections and dimension choices.

        Args:
            selected_departments: List of selected departments
            selected_machines: List of selected machines
            selected_insurer_categories: List of selected insurer categories
            selected_insurers: List of selected insurers
            start_date: Start date string
            end_date: End date string
            parallel_dimensions: List of selected dimension keys for parallel diagram

        Returns:
            Plotly figure object
        """
        # Filter data
        filtered_df = task.filter_data(
            selected_departments,
            selected_machines,
            selected_insurer_categories,
            selected_insurers,
            start_date,
            end_date,
            selected_techniques,
            selected_codes_2026,
            selected_radiation_types,
            selected_actual_codes
        )

        # Calculate parallel categories data with selected dimensions
        print(f"DEBUG CALLBACK: parallel_dimensions = {parallel_dimensions}")
        dimensions, counts, df_valid, code_2026_stats = task.calculate_parallel_categories_data(filtered_df, parallel_dimensions)

        # Create parallel categories diagram
        if not dimensions or df_valid is None or df_valid.empty:
            # Empty diagram
            fig = go.Figure()
            fig.update_layout(
                title="No data available for selected filters or dimensions",
                height=900
            )
            return fig

        # Create color mapping based on 2026 Code
        import time
        start = time.time()

        # Get unique codes more efficiently
        if hasattr(df_valid['ID2026Code'], 'cat'):
            unique_codes = df_valid['ID2026Code'].cat.categories.tolist()
        else:
            unique_codes = df_valid['ID2026Code'].unique().tolist()

        color_map = {code: i for i, code in enumerate(unique_codes)}
        colors = df_valid['ID2026Code'].map(color_map)

        print(f"DEBUG: Color mapping created in {time.time()-start:.2f}s")

        # Set categoryarray and ticktext for each dimension to prevent label wrapping/repetition
        start = time.time()
        for dim in dimensions:
            col_data = dim['values']
            # Use category attributes if available for speed
            if hasattr(col_data, 'cat'):
                # Get categories
                unique_vals = col_data.cat.categories.tolist()
            else:
                # Get unique values
                unique_vals = col_data.unique().tolist()

            # Apply custom ordering for 2026 codes
            if dim.get('label') == '2026 Code':
                codes_2026_order = task.codes_2026_order
                # Order according to custom order
                ordered_vals = [code for code in codes_2026_order if code in unique_vals]
                # Add any codes not in the predefined order at the end (sorted)
                other_vals = sorted([code for code in unique_vals if code not in codes_2026_order])
                ordered_vals.extend(other_vals)
                unique_vals = ordered_vals

                # Create ticktext with count and percentage
                ticktext = []
                for code in unique_vals:
                    stats = code_2026_stats.get(code, {'count': 0, 'percentage': 0})
                    count = stats['count']
                    percentage = stats['percentage']
                    ticktext.append(f"{code} ({count:,}, {percentage:.1f}%)")
                dim['ticktext'] = ticktext
            else:
                # Sort all other dimensions
                unique_vals = sorted(unique_vals)

            dim['categoryarray'] = unique_vals
            # Plotly parcats doesn't have a "label standoff" control; adding a <br>
            # increases label box height and creates space before the category blocks.
            if isinstance(dim.get('label'), str) and '<br>' not in dim['label']:
                dim['label'] = f"{dim['label']}"
            print(f"DEBUG: Dimension '{dim['label']}' has {len(unique_vals)} unique values")

        print(f"DEBUG: Category arrays set in {time.time()-start:.2f}s")

        start = time.time()

        # Calculate appropriate height based on max categories in any dimension
        max_categories = max(len(dim['categoryarray']) for dim in dimensions)
        # Use more vertical space per category to prevent wrapping
        min_height_per_category = 25  # pixels per category
        calculated_height = max(800, max_categories * min_height_per_category + 200)  # +200 for margins/title

        fig = go.Figure(data=[go.Parcats(
            dimensions=dimensions,
            line=dict(
                color=colors,
                colorscale='Viridis',
                shape='hspline'
            ),
            hoveron='color',
            hoverinfo='count+probability',
            labelfont=dict(size=12, family='Arial'),
            tickfont=dict(size=10, family='Arial'),
            arrangement='freeform'
        )])

        print(f"DEBUG: Figure created in {time.time()-start:.2f}s with height={calculated_height}")

        # Build dynamic title based on selected dimensions
        dim_labels = []
        dim_map = {
            'actual_codes': 'Actual Billing Code',
            '2026_codes': '2026 Code',
            'department': 'Department',
            'machine': 'Machine',
            'insurer_category': 'Insurer Category',
            'technique': 'Technique',
            'radiation_type': 'Radiation Type'
        }
        if parallel_dimensions:
            for dim in parallel_dimensions:
                if dim in dim_map:
                    dim_labels.append(dim_map[dim])

        title = "Treatment Flow: " + " → ".join(dim_labels) if dim_labels else "Treatment Flow"

        fig.update_layout(
            title_text=title,
            font_size=11,
            height=calculated_height,
            margin=dict(l=100, r=100, t=80, b=50)
        )

        return fig

    @app.callback(
        Output('cpt-download-csv', 'data'),
        Input('cpt-export-csv', 'n_clicks'),
        [State('cpt-department-checklist', 'value'),
         State('cpt-machine-checklist', 'value'),
         State('cpt-insurer-category-checklist', 'value'),
         State('cpt-insurer-checklist', 'value'),
         State('cpt-start-date', 'date'),
         State('cpt-end-date', 'date'),
         State('cpt-technique-checklist', 'value'),
         State('cpt-2026code-checklist', 'value'),
         State('cpt-radiation-type-checklist', 'value'),
         State('cpt-actual-code-checklist', 'value')],
        prevent_initial_call=True
    )
    def export_csv(n_clicks, selected_departments, selected_machines, selected_insurer_categories, selected_insurers,
                  start_date, end_date, selected_techniques, selected_codes_2026,
                  selected_radiation_types, selected_actual_codes):
        """Export table data to CSV"""
        # Filter data
        filtered_df = task.filter_data(
            selected_departments,
            selected_machines,
            selected_insurer_categories,
            selected_insurers,
            start_date,
            end_date,
            selected_techniques,
            selected_codes_2026,
            selected_radiation_types,
            selected_actual_codes
        )

        # Calculate code summary
        summary_df = task.calculate_code_summary(filtered_df)

        return dcc.send_data_frame(summary_df.to_csv, "cpt_billing_summary.csv", index=False)

    @app.callback(
        Output('cpt-download-excel', 'data'),
        Input('cpt-export-excel', 'n_clicks'),
        [State('cpt-department-checklist', 'value'),
         State('cpt-machine-checklist', 'value'),
         State('cpt-insurer-category-checklist', 'value'),
         State('cpt-insurer-checklist', 'value'),
         State('cpt-start-date', 'date'),
         State('cpt-end-date', 'date'),
         State('cpt-technique-checklist', 'value'),
         State('cpt-2026code-checklist', 'value'),
         State('cpt-radiation-type-checklist', 'value'),
         State('cpt-actual-code-checklist', 'value')],
        prevent_initial_call=True
    )
    def export_excel(n_clicks, selected_departments, selected_machines, selected_insurer_categories, selected_insurers,
                    start_date, end_date, selected_techniques, selected_codes_2026,
                    selected_radiation_types, selected_actual_codes):
        """Export table data to Excel"""
        # Filter data
        filtered_df = task.filter_data(
            selected_departments,
            selected_machines,
            selected_insurer_categories,
            selected_insurers,
            start_date,
            end_date,
            selected_techniques,
            selected_codes_2026,
            selected_radiation_types,
            selected_actual_codes
        )

        # Calculate code summary
        summary_df = task.calculate_code_summary(filtered_df)

        return dcc.send_data_frame(summary_df.to_excel, "cpt_billing_summary.xlsx", index=False)
