"""
CPT Billing sidebar layout (filters and controls)
"""
from dash import html, dcc
import dash_bootstrap_components as dbc


def create_sidebar_layout(task, state=None):
    """
    Create sidebar layout for CPT Billing task.

    Args:
        task: CPTBillingTask instance
        state: Optional dict with persisted state values

    Returns:
        Dash component for sidebar
    """
    # Use persisted state if available, otherwise use defaults
    if state is None:
        state = {}

    # Get values from state or defaults
    department_value = state.get('departments') if state.get('departments') is not None else task.departments
    machine_value = state.get('machines') if state.get('machines') is not None else task.machines
    insurer_category_value = state.get('insurer_categories') if state.get('insurer_categories') is not None else task.insurer_categories
    insurer_value = state.get('insurers') if state.get('insurers') is not None else task.insurers
    technique_value = state.get('techniques') if state.get('techniques') is not None else task.techniques
    code_2026_value = state.get('codes_2026') if state.get('codes_2026') is not None else task.codes_2026
    radiation_type_value = state.get('radiation_types') if state.get('radiation_types') is not None else task.radiation_types
    actual_code_value = state.get('actual_codes') if state.get('actual_codes') is not None else task.actual_codes

    return html.Div([
        html.H5("Filters", style={'marginBottom': '20px', 'marginTop': '20px'}),

        # Department Filter
        html.Div([
            html.Label("Department", style={'fontWeight': 'bold', 'marginBottom': '10px'}),
            dcc.Checklist(
                id='cpt-department-checklist',
                options=[{'label': dept, 'value': dept} for dept in task.departments],
                value=department_value,
                labelStyle={'display': 'block', 'marginBottom': '8px'},
                inputStyle={'marginRight': '8px'}
            )
        ], className='filter-section'),

        html.Hr(),

        # Machine Filter
        html.Div([
            html.Label("Machine", style={'fontWeight': 'bold', 'marginBottom': '10px'}),
            dcc.Checklist(
                id='cpt-machine-checklist',
                options=[{'label': machine, 'value': machine} for machine in task.machines],
                value=machine_value,
                labelStyle={'display': 'block', 'marginBottom': '8px'},
                inputStyle={'marginRight': '8px'},
                style={'maxHeight': '200px', 'overflowY': 'auto'}
            )
        ], className='filter-section'),

        html.Hr(),

        # Insurer Category Filter (Broad categories)
        html.Div([
            html.Label("Insurer Category", style={'fontWeight': 'bold', 'marginBottom': '10px'}),
            dcc.Checklist(
                id='cpt-insurer-category-checklist',
                options=[{'label': cat, 'value': cat} for cat in task.insurer_categories],
                value=insurer_category_value,
                labelStyle={'display': 'block', 'marginBottom': '8px'},
                inputStyle={'marginRight': '8px'}
            )
        ], className='filter-section'),

        html.Hr(),

        # Insurer Filter (Specific insurers)
        html.Div([
            html.Label("Specific Insurer", style={'fontWeight': 'bold', 'marginBottom': '10px'}),
            dcc.Checklist(
                id='cpt-insurer-checklist',
                options=[{'label': insurer, 'value': insurer} for insurer in task.insurers],
                value=insurer_value,
                labelStyle={'display': 'block', 'marginBottom': '8px'},
                inputStyle={'marginRight': '8px'},
                style={'maxHeight': '300px', 'overflowY': 'auto'}
            )
        ], className='filter-section'),

        html.Hr(),

        # Technique Filter
        html.Div([
            html.Label("Technique", style={'fontWeight': 'bold', 'marginBottom': '10px'}),
            dcc.Checklist(
                id='cpt-technique-checklist',
                options=[{'label': tech, 'value': tech} for tech in task.techniques],
                value=technique_value,
                labelStyle={'display': 'block', 'marginBottom': '8px'},
                inputStyle={'marginRight': '8px'}
            )
        ], className='filter-section'),

        html.Hr(),

        # 2026 Code Filter
        html.Div([
            html.Label("2026 Code", style={'fontWeight': 'bold', 'marginBottom': '10px'}),
            dcc.Checklist(
                id='cpt-2026code-checklist',
                options=[{'label': code, 'value': code} for code in task.codes_2026],
                value=code_2026_value,
                labelStyle={'display': 'block', 'marginBottom': '8px'},
                inputStyle={'marginRight': '8px'},
                style={'maxHeight': '200px', 'overflowY': 'auto'}
            )
        ], className='filter-section'),

        html.Hr(),

        # Radiation Type Filter
        html.Div([
            html.Label("Radiation Type", style={'fontWeight': 'bold', 'marginBottom': '10px'}),
            dcc.Checklist(
                id='cpt-radiation-type-checklist',
                options=[{'label': rt, 'value': rt} for rt in task.radiation_types],
                value=radiation_type_value,
                labelStyle={'display': 'block', 'marginBottom': '8px'},
                inputStyle={'marginRight': '8px'}
            )
        ], className='filter-section'),

        html.Hr(),

        # Actual Billing Code Filter
        html.Div([
            html.Label("Actual Billing Code", style={'fontWeight': 'bold', 'marginBottom': '10px'}),
            dcc.Checklist(
                id='cpt-actual-code-checklist',
                options=[{'label': code, 'value': code} for code in task.actual_codes],
                value=actual_code_value,
                labelStyle={'display': 'block', 'marginBottom': '8px'},
                inputStyle={'marginRight': '8px'},
                style={'maxHeight': '300px', 'overflowY': 'auto'}
            )
        ], className='filter-section'),

        html.Hr(),

        # Time Frame Filter
        html.Div([
            html.Label("Time Frame", style={'fontWeight': 'bold', 'marginBottom': '10px'}),
            html.Label("Start Date", style={'fontSize': '12px', 'marginBottom': '5px', 'marginTop': '10px'}),
            dcc.DatePickerSingle(
                id='cpt-start-date',
                min_date_allowed=task.min_date,
                max_date_allowed=task.max_date,
                initial_visible_month=task.min_date,
                date=task.min_date,
                display_format='MM/DD/YYYY',
                style={'width': '100%'}
            ),
            html.Label("End Date", style={'fontSize': '12px', 'marginBottom': '5px', 'marginTop': '15px'}),
            dcc.DatePickerSingle(
                id='cpt-end-date',
                min_date_allowed=task.min_date,
                max_date_allowed=task.max_date,
                initial_visible_month=task.max_date,
                date=task.max_date,
                display_format='MM/DD/YYYY',
                style={'width': '100%'}
            )
        ], className='filter-section'),

    ], className='cpt-sidebar')
