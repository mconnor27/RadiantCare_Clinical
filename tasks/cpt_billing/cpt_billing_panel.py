"""
CPT Billing main panel layout (summary table display)
"""
import dash
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
    "77417": "Port Films",
    "G6002": "IGRT",
    # SRS/SBRT
    "77372": "SRS",
    "77373": "SBRT",
    # With modifiers - Professional Component (26)
    "77402-26": "IMRT (Simple) - Professional",
    "77407-26": "IMRT (Intermediate) - Professional",
    "77412-26": "IMRT (Complex) - Professional",
    "77385-26": "IMRT (Simple) - Professional",
    "77386-26": "IMRT (Complex) - Professional",
    "77014-26": "CBCT - Professional",
    "77387-26": "IGRT - Professional",
    "77417-26": "Port Films - Professional",
    "77372-26": "SRS - Professional",
    "77373-26": "SBRT - Professional",
    # With modifiers - Technical Component (TC)
    "77402-TC": "IMRT (Simple) - Technical",
    "77407-TC": "IMRT (Intermediate) - Technical",
    "77412-TC": "IMRT (Complex) - Technical",
    "77385-TC": "IMRT (Simple) - Technical",
    "77386-TC": "IMRT (Complex) - Technical",
    "77014-TC": "CBCT - Technical",
    "77387-TC": "IGRT - Technical",
    "77417-TC": "Port Films - Technical",
    "77372-TC": "SRS - Technical",
    "77373-TC": "SBRT - Technical",
    # G-codes with modifiers
    "G6003-26": "IMRT (Simple) - Professional",
    "G6007-26": "IMRT (Intermediate) - Professional",
    "G6011-26": "IMRT (Complex) - Professional",
    "G6015-26": "IMRT (Simple) - Professional",
    "G6016-26": "IMRT (Complex) - Professional",
    "G6002-26": "IGRT - Professional",
    "G6003-TC": "IMRT (Simple) - Technical",
    "G6007-TC": "IMRT (Intermediate) - Technical",
    "G6011-TC": "IMRT (Complex) - Technical",
    "G6015-TC": "IMRT (Simple) - Technical",
    "G6016-TC": "IMRT (Complex) - Technical",
    "G6002-TC": "IGRT - Technical",
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
            html.Div([
                html.H5("2026 CPT Code Analysis", style={'marginBottom': '5px'}),
                html.Div(id="cpt-record-count", style={'fontSize': '14px', 'color': '#666', 'marginBottom': '10px'}),
            ], style={'display': 'inline-block'}),
            html.Div([
                dbc.Button("Export to CSV", id="cpt-export-csv", color="primary", size="sm", style={'marginRight': '10px'}),
                dbc.Button("Export to Excel", id="cpt-export-excel", color="success", size="sm"),
            ], style={'display': 'inline-block', 'float': 'right', 'marginTop': '20px'})
        ], style={'overflow': 'hidden', 'marginTop': '20px', 'marginBottom': '20px'}),

        # Sankey diagram
        html.Div([
            html.H6("Sankey Flow Analysis", style={'marginTop': '30px', 'marginBottom': '15px', 'textAlign': 'center'}),
            html.Div([
                html.Label("Select dimensions to include (flows from left to right, ending with 2026 Codes):", style={'fontWeight': 'bold', 'marginRight': '15px'}),
                dcc.Checklist(
                    id='cpt-sankey-dimensions',
                    options=[
                        {'label': ' Actual Billing Codes', 'value': 'actual_codes'},
                        {'label': ' Department', 'value': 'department'},
                        {'label': ' Machine', 'value': 'machine'},
                        {'label': ' Insurer Category', 'value': 'insurer_category'},
                        {'label': ' Technique', 'value': 'technique'},
                        {'label': ' Radiation Type', 'value': 'radiation_type'}
                    ],
                    value=['actual_codes'],
                    inline=True,
                    labelStyle={'marginRight': '15px'},
                    inputStyle={'marginRight': '5px'}
                )
            ], style={'textAlign': 'center', 'marginBottom': '15px'}),
            dcc.Graph(id='cpt-sankey-diagram', style={'height': '700px'}),
        ], style={'marginBottom': '40px'}),

        # Parallel categories diagram
        html.Div([
            html.H6("Treatment Flow Analysis", style={'marginTop': '30px', 'marginBottom': '15px', 'textAlign': 'center'}),
            html.Div([
                html.Label("Select dimensions to include (2026 Codes always shown on right):", style={'fontWeight': 'bold', 'marginRight': '15px'}),
                dcc.Checklist(
                    id='cpt-parallel-dimensions',
                    options=[
                        {'label': ' Actual Billing Codes', 'value': 'actual_codes'},
                        {'label': ' Department', 'value': 'department'},
                        {'label': ' Machine', 'value': 'machine'},
                        {'label': ' Insurer Category', 'value': 'insurer_category'},
                        {'label': ' Technique', 'value': 'technique'},
                        {'label': ' Radiation Type', 'value': 'radiation_type'}
                    ],
                    value=['actual_codes'],
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
        Output('cpt-record-count', 'children'),
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
    def update_record_count(selected_departments, selected_machines, selected_insurer_categories, selected_insurers,
                           start_date, end_date, selected_techniques, selected_codes_2026,
                           selected_radiation_types, selected_actual_codes):
        """Update the record count display."""
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
        return f"Showing {len(filtered_df):,} records"

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
        print(f"DEBUG PARALLEL CALLBACK: start_date={start_date}, end_date={end_date}")
        
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
        print(f"DEBUG PARALLEL: filtered_df has {len(filtered_df)} rows after filter_data")

        # Calculate parallel categories data with selected dimensions
        # Always append 2026_codes at the end (rightmost position)
        dimensions_with_2026 = [d for d in (parallel_dimensions or []) if d != '2026_codes'] + ['2026_codes']
        print(f"DEBUG CALLBACK: parallel_dimensions = {dimensions_with_2026}")
        dimensions, counts, df_valid, code_2026_stats = task.calculate_parallel_categories_data(filtered_df, dimensions_with_2026)

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
            total_actual = actual_counts.sum()
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

        # Build dynamic title based on selected dimensions (2026 Code always at end)
        dim_labels = []
        dim_map = {
            'actual_codes': 'Actual Billing Code',
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
        # Always append 2026 Code at the end
        dim_labels.append('2026 Code')

        title = "Treatment Flow: " + " → ".join(dim_labels)

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
        Output('cpt-sankey-diagram', 'figure'),
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
         Input('cpt-sankey-dimensions', 'value')]
    )
    def update_sankey_diagram(selected_departments, selected_machines, selected_insurer_categories, selected_insurers,
                             start_date, end_date, selected_techniques, selected_codes_2026,
                             selected_radiation_types, selected_actual_codes, selected_dimensions):
        """
        Update the Sankey diagram based on filter selections and dimensions.

        Args:
            selected_departments: List of selected departments
            selected_machines: List of selected machines
            selected_insurer_categories: List of selected insurer categories
            selected_insurers: List of selected insurers
            start_date: Start date string
            end_date: End date string
            selected_techniques: List of selected techniques
            selected_codes_2026: List of selected 2026 codes
            selected_radiation_types: List of selected radiation types
            selected_actual_codes: List of selected actual billing codes
            selected_dimensions: List of dimension keys for Sankey layers

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

        # Calculate Sankey data with selected dimensions
        source, target, value, labels, dimension_labels, original_treatment_count, dimension_totals, node_treatment_counts = task.calculate_sankey_data(filtered_df, selected_dimensions)

        # Create Sankey diagram
        if not source or not labels:
            # Empty diagram
            fig = go.Figure()
            fig.update_layout(
                title="No data available for selected filters",
                height=700
            )
            return fig

        # Add descriptions for actual billing codes
        labels_with_desc = []
        for i, label in enumerate(labels):
            # Check if this is a 2026 code (contains parentheses with count/percentage)
            if '(' in label and '%' in label:
                # Already has stats, keep as is
                labels_with_desc.append(label)
            else:
                # Check if it's an actual billing code (first dimension when actual_codes is selected)
                if dimension_labels and dimension_labels[i] == 0 and selected_dimensions and selected_dimensions[0] == 'actual_codes':
                    desc = _ACTUAL_CODE_EXPLANATIONS.get(label, "")
                    if desc:
                        labels_with_desc.append(f"{label}: {desc}")
                    else:
                        labels_with_desc.append(label)
                else:
                    labels_with_desc.append(label)

        # Sort links to influence Plotly's automatic ordering
        # Group links by their target node and sort by target index
        link_data = list(zip(source, target, value))
        link_data.sort(key=lambda x: (x[1], x[0]))  # Sort by target, then source
        source = [x[0] for x in link_data]
        target = [x[1] for x in link_data]
        value = [x[2] for x in link_data]

        # Generate default Plotly colors for nodes
        import plotly.express as px
        num_nodes = len(labels)
        default_colors = px.colors.qualitative.Plotly
        node_colors = [default_colors[i % len(default_colors)] for i in range(num_nodes)]

        # Color links based on their target node with some transparency
        link_colors = []
        for tgt in target:
            color = node_colors[tgt]
            # Add transparency to the color
            if color.startswith('#'):
                # Convert hex to rgba
                h = color.lstrip('#')
                r, g, b = tuple(int(h[i:i+2], 16) for i in (0, 2, 4))
                rgba = f'rgba({r},{g},{b},0.4)'
            elif color.startswith('rgb('):
                # Convert rgb to rgba
                rgba = color.replace('rgb(', 'rgba(').replace(')', ',0.4)')
            else:
                rgba = color
            link_colors.append(rgba)

        # Calculate statistics for hover templates
        # Use the original treatment count, not the sum of expanded flows
        total_count = original_treatment_count

        # We need to calculate actual treatment counts per node from the original filtered data
        # NOT from the expanded flow values which are inflated
        # For now, use the flow values but this needs to be fixed to count actual treatments
        # matching each node's criteria

        # Calculate flow-based node values (this is what flows through, not treatment count)
        node_values_incoming = {}
        node_values_outgoing = {}
        for src, tgt, val in zip(source, target, value):
            node_values_incoming[tgt] = node_values_incoming.get(tgt, 0) + val
            node_values_outgoing[src] = node_values_outgoing.get(src, 0) + val

        # For each node, use outgoing if available, otherwise incoming
        # NOTE: These are FLOW counts, not treatment counts - they will be inflated
        # when multiple dimensions with multi-values are selected
        node_flow_values = {}
        for i in range(len(labels)):
            if i in node_values_outgoing:
                node_flow_values[i] = node_values_outgoing[i]
            elif i in node_values_incoming:
                node_flow_values[i] = node_values_incoming[i]
            else:
                node_flow_values[i] = 0

        # Use the dimension_totals from the task (calculated from original data)
        # NOT the inflated flow-based category totals

        # Build custom hover text for nodes
        # For 2026 codes, extract the actual count from the label (which is correct)
        # For other nodes, use flow values
        node_customdata = []
        max_dim = max(dimension_labels) if dimension_labels else 0

        for i, label in enumerate(labels):
            dim = dimension_labels[i]
            # Get the correct total for this dimension from the task
            dim_total = dimension_totals.get(dim, 1)

            # Use actual treatment counts from the task calculation
            count = node_treatment_counts.get(i, 0)

            # Percentage within this category/dimension
            pct_of_category = (count / dim_total * 100) if dim_total > 0 else 0

            node_customdata.append({
                'count': count,
                'cat_total': dim_total,
                'pct_category': pct_of_category
            })

        # Create hover template for nodes - show count and percentage of category
        node_hovertemplate = (
            '<b>%{label}</b><br>'
            'Count: %{customdata[0]:,}<br>'
            'Category share: %{customdata[0]:,} of %{customdata[1]:,} (%{customdata[2]:.1f}%)'
            '<extra></extra>'
        )

        # Build custom hover for links - simplified to just show flow count
        link_hovertemplate = (
            '<b>%{source.label}</b> → <b>%{target.label}</b><br>'
            'Flow count: %{value:,}'
            '<extra></extra>'
        )

        fig = go.Figure(data=[go.Sankey(
            node=dict(
                pad=15,
                thickness=20,
                line=dict(color='black', width=0.5),
                label=labels_with_desc,
                color=node_colors,
                customdata=[[cd['count'], cd['cat_total'], cd['pct_category']] for cd in node_customdata],
                hovertemplate=node_hovertemplate
            ),
            link=dict(
                source=source,
                target=target,
                value=value,
                color=link_colors,
                hovertemplate=link_hovertemplate
            ),
            valueformat=',d',  # Format values as integers with commas
            valuesuffix=''  # Remove any suffix
        )])

        # Create dynamic title based on selected dimensions
        dimension_names = {
            'actual_codes': 'Actual Codes',
            'department': 'Department',
            'machine': 'Machine',
            'insurer_category': 'Insurer Category',
            'technique': 'Technique',
            'radiation_type': 'Radiation Type'
        }

        if selected_dimensions and len(selected_dimensions) > 0:
            dim_flow = ' → '.join([dimension_names.get(d, d) for d in selected_dimensions])
            title = f"Flow: {dim_flow} → 2026 Codes"
        else:
            title = "Flow to 2026 CPT Codes"

        fig.update_layout(
            title_text=title,
            font_size=11,
            height=700,
            margin=dict(l=20, r=20, t=80, b=20),
            hovermode='closest'
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

        return dcc.send_data_frame(summary_df.to_excel, "cpt_billing_summary.xlsx", index=False, engine='openpyxl')

    # Callbacks for Select All/None buttons
    @app.callback(
        Output('cpt-insurer-checklist', 'value'),
        [Input('cpt-insurer-select-all', 'n_clicks'),
         Input('cpt-insurer-select-none', 'n_clicks')],
        [State('cpt-insurer-checklist', 'options')]
    )
    def update_insurer_selection(select_all_clicks, select_none_clicks, options):
        """Handle Select All/None buttons for insurer filter."""
        ctx = dash.callback_context
        if not ctx.triggered:
            return [opt['value'] for opt in options]

        button_id = ctx.triggered[0]['prop_id'].split('.')[0]

        if button_id == 'cpt-insurer-select-all':
            return [opt['value'] for opt in options]
        elif button_id == 'cpt-insurer-select-none':
            return []

        return [opt['value'] for opt in options]

    @app.callback(
        Output('cpt-actual-code-checklist', 'value'),
        [Input('cpt-actual-code-select-all', 'n_clicks'),
         Input('cpt-actual-code-select-none', 'n_clicks')],
        [State('cpt-actual-code-checklist', 'options')]
    )
    def update_actual_code_selection(select_all_clicks, select_none_clicks, options):
        """Handle Select All/None buttons for actual code filter."""
        ctx = dash.callback_context
        if not ctx.triggered:
            return [opt['value'] for opt in options]

        button_id = ctx.triggered[0]['prop_id'].split('.')[0]

        if button_id == 'cpt-actual-code-select-all':
            return [opt['value'] for opt in options]
        elif button_id == 'cpt-actual-code-select-none':
            return []

        return [opt['value'] for opt in options]
