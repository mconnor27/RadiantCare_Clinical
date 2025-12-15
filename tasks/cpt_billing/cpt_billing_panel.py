"""
CPT Billing main panel layout (summary table display)
"""
from dash import html, dcc, dash_table, Input, Output, State
import dash_bootstrap_components as dbc
import plotly.graph_objects as go


# 2026 CPT code explanations (new consolidated codes)
_2026_CODE_EXPLANATIONS = {
    "77402": "Simple",
    "77407": "Intermediate",
    "77412": "Complex",
    "77372": "SRS",
    "77373": "SBRT",
}

# Actual billed code explanations (current codes being billed)
_ACTUAL_CODE_EXPLANATIONS = {
    # IMRT codes that map to Simple (77402)
    "77402": "IMRT (Simple)",
    "G6003": "IMRT (Simple)",
    "G6004": "IMRT (Simple)",
    "G6005": "IMRT (Simple)",
    "G6006": "IMRT (Simple)",
    # IMRT codes that map to Intermediate (77407)
    "77407": "IMRT (Intermediate)",
    "G6007": "IMRT (Intermediate)",
    "G6008": "IMRT (Intermediate)",
    "G6009": "IMRT (Intermediate)",
    "G6010": "IMRT (Intermediate)",
    # IMRT codes that map to Complex (77412)
    "77412": "IMRT (Complex)",
    "G6011": "IMRT (Complex)",
    "G6012": "IMRT (Complex)",
    "G6013": "IMRT (Complex)",
    "G6014": "IMRT (Complex)",
    # Other IMRT delivery codes
    "77385": "IMRT (Simple)",
    "77386": "IMRT (Complex)",
    "G6015": "IMRT (Simple)",
    "G6016": "IMRT (Complex)",
    # Guidance (IGRT)
    "77014": "CBCT",
    "77387": "IGRT",
    "G6002": "IGRT",
    # SRS/SBRT
    "77372": "SRS",
    "77373": "SBRT",
}


def _format_code_label(code: str, code_type: str = "2026") -> str:
    """Return `CODE: Description` when known; otherwise just `CODE`.
    
    Args:
        code: The CPT code
        code_type: Either "2026" or "actual" to select the appropriate dictionary
    """
    code = ("" if code is None else str(code)).strip()
    if code_type == "actual":
        desc = _ACTUAL_CODE_EXPLANATIONS.get(code)
    else:
        desc = _2026_CODE_EXPLANATIONS.get(code)
    return f"{code}: {desc}" if desc else code


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
                    value=['actual_codes', '2026_codes'],
                    inline=True,
                    labelStyle={'marginRight': '15px'},
                    inputStyle={'marginRight': '5px'}
                )
            ], style={'textAlign': 'center', 'marginBottom': '15px'}),
            dcc.Graph(id='cpt-parallel-diagram', style={'height': '700px'}),
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
        # If Actual Billing Code is present (df_valid was expanded), build stats for label enrichment
        actual_code_stats = {}
        if 'ActualCode' in df_valid.columns:
            actual_counts = df_valid['ActualCode'].value_counts()
            total_actual = int(actual_counts.sum())
            for code, count in actual_counts.items():
                pct = (count / total_actual * 100) if total_actual else 0
                actual_code_stats[str(code)] = {"count": int(count), "percentage": float(pct)}

        for dim in dimensions:
            col_data = dim['values']
            dim_label = dim.get('label') or ""
            
            # Convert values to strings (don't remap, keep original)
            dim['values'] = dim['values'].astype(str).fillna("Unknown")
            
            # Get unique values after string conversion
            unique_vals = dim['values'].unique().tolist()

            # Apply custom ordering for 2026 codes
            if dim.get('label') == '2026 Code':
                codes_2026_order = task.codes_2026_order
                ordered_vals = [code for code in codes_2026_order if code in unique_vals]
                other_vals = sorted([code for code in unique_vals if code not in codes_2026_order])
                ordered_vals.extend(other_vals)
                unique_vals = ordered_vals

                # Labels with explanation + stats
                ticktext = []
                for code in unique_vals:
                    stats = code_2026_stats.get(code, {'count': 0, 'percentage': 0})
                    label = _format_code_label(code, "2026")
                    ticktext.append(f"{label} ({stats['count']:,}, {stats['percentage']:.1f}%)")
                dim['categoryarray'] = unique_vals
                dim['ticktext'] = ticktext
            elif "Actual" in dim.get('label', '') and "Code" in dim.get('label', ''):
                # Labels: just the code (explanation added by JavaScript in tooltip)
                dim['categoryarray'] = unique_vals
                dim['ticktext'] = unique_vals
            else:
                # Sort other dimensions
                unique_vals = sorted(unique_vals)
                dim['categoryarray'] = unique_vals
                dim['ticktext'] = unique_vals
            
            # Plotly parcats doesn't have a "label standoff" control
            if isinstance(dim.get('label'), str) and '<br>' not in dim['label']:
                dim['label'] = f"{dim['label']}"

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
                shape='hspline',
                hovertemplate='<b>Flow Count:</b> %{count:,}<br><b>Share of All Records:</b> %{probability:.1%}<extra></extra>'
            ),
            hoveron='color',
            hoverinfo='count+probability',
            hovertemplate=(
                "<b>%{category}</b><br>"
                "Count: %{bandcolorcount:,} (%{probability:.1%} of total)<br>"
                "Color share: %{bandcolorcount:,} of %{colorcount:,} (---.--%)<br>"
                "Category share: %{bandcolorcount:,} of %{categorycount:,} (---.--%)"
                "<extra></extra>"
            ),
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
            margin=dict(l=100, r=200, t=80, b=50),
            # Widen hover tooltip and improve formatting
            hoverlabel=dict(
                bgcolor='white',
                bordercolor='#888',
                font=dict(size=13, family='Arial'),
                namelength=-1,  # Show full text, don't truncate
                align='left'
            )
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
