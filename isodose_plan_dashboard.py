"""
Standalone Dash app for Isodose Plan completion time analysis
"""
import dash
import dash_bootstrap_components as dbc
from dash import html, Input, Output, State, dcc
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import numpy as np

# Load and prepare data
print("Loading data...")
df = pd.read_csv('data/Workflow.csv')

# Filter for completed Isodose Plan tasks
completed_tasks = df[
    df['IsodosePlanCompletingUser'].notna() & 
    (df['IsodosePlanCompletingUser'] != '') &
    df['IsodosePlanMinutesToComplete'].notna() &
    df['IsodosePlanCompletedDateTime'].notna()
].copy()

# Parse completion datetime
completed_tasks['IsodosePlanCompletedDateTime'] = pd.to_datetime(
    completed_tasks['IsodosePlanCompletedDateTime'], 
    errors='coerce'
)

# Filter out extreme outliers and negative values
outlier_threshold = 10000
completed_tasks_filtered = completed_tasks[
    (completed_tasks['IsodosePlanMinutesToComplete'] > 0) &
    (completed_tasks['IsodosePlanMinutesToComplete'] <= outlier_threshold) &
    (completed_tasks['IsodosePlanCompletedDateTime'].notna())
].copy()

# Filter out users with fewer than 10 completed tasks
min_tasks = 10
user_counts = completed_tasks_filtered.groupby('IsodosePlanCompletingUser').size()
valid_users = user_counts[user_counts >= min_tasks].index.tolist()
completed_tasks_filtered = completed_tasks_filtered[
    completed_tasks_filtered['IsodosePlanCompletingUser'].isin(valid_users)
].copy()

# Get sorted list of users
users_sorted = sorted(valid_users)

print(f"Loaded {len(completed_tasks_filtered)} tasks from {len(users_sorted)} users")

# Initialize Dash app
app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])
app.title = "Isodose Plan Completion Time Analysis"

# Define app layout
app.layout = dbc.Container([
    dbc.Row([
        dbc.Col([
            html.H2("Isodose Plan Completion Time Analysis", className="mb-4"),
            html.P("Select users to view density distribution of completion times", className="text-muted mb-4"),
        ])
    ]),
    dbc.Row([
        dbc.Col([
            dbc.Card([
                dbc.CardHeader("User Selection"),
                dbc.CardBody([
                    html.Label("Select Users:", className="fw-bold mb-2"),
                    dcc.Checklist(
                        id='user-checklist',
                        options=[{'label': user, 'value': user} for user in users_sorted],
                        value=users_sorted,  # All users selected by default
                        labelStyle={'display': 'block', 'margin-bottom': '8px'},
                        inputStyle={'margin-right': '8px'},
                        className="mb-3"
                    ),
                    html.Button(
                        "Select All",
                        id="select-all-btn",
                        className="btn btn-sm btn-outline-primary me-2",
                        n_clicks=0
                    ),
                    html.Button(
                        "Deselect All",
                        id="deselect-all-btn",
                        className="btn btn-sm btn-outline-secondary",
                        n_clicks=0
                    ),
                ])
            ], className="mb-4")
        ], width=3),
        dbc.Col([
            dbc.Card([
                dbc.CardBody([
                    dcc.Graph(id='density-plot')
                ])
            ])
        ], width=9)
    ]),
    dbc.Row([
        dbc.Col([
            html.Div(id='stats-summary', className="mt-3")
        ])
    ]),
    dbc.Row([
        dbc.Col([
            html.Hr(),
            html.H3("Task Completion Rankings", className="mb-4 mt-4"),
        ])
    ]),
    dbc.Row([
        dbc.Col([
            dbc.Card([
                dbc.CardBody([
                    dcc.Graph(id='task-ranking-plot')
                ])
            ])
        ], width=12)
    ]),
    dbc.Row([
        dbc.Col([
            html.Div(id='task-stats-summary', className="mt-3")
        ])
    ])
], fluid=True)


@app.callback(
    Output('user-checklist', 'value'),
    Input('select-all-btn', 'n_clicks'),
    Input('deselect-all-btn', 'n_clicks'),
    State('user-checklist', 'value'),
    prevent_initial_call=True
)
def update_checklist(select_all_clicks, deselect_all_clicks, current_value):
    ctx = dash.callback_context
    if not ctx.triggered:
        return dash.no_update
    
    button_id = ctx.triggered[0]['prop_id'].split('.')[0]
    if button_id == 'select-all-btn':
        return users_sorted
    elif button_id == 'deselect-all-btn':
        return []
    return dash.no_update


@app.callback(
    Output('density-plot', 'figure'),
    Output('stats-summary', 'children'),
    Input('user-checklist', 'value')
)
def update_plot(selected_users):
    # Debug: print what we're receiving
    print(f"DEBUG: selected_users = {selected_users}, type = {type(selected_users)}")
    
    # Fallback to all users if None (shouldn't happen, but safety check)
    if selected_users is None:
        selected_users = users_sorted
        print(f"DEBUG: Using fallback users_sorted = {selected_users}")
    
    # Handle empty list
    if isinstance(selected_users, list) and len(selected_users) == 0:
        # Empty plot if no users selected
        fig = go.Figure()
        fig.update_layout(
            title="No users selected",
            xaxis_title="Completion Time (days)",
            yaxis_title="Density",
            height=500
        )
        return fig, html.P("Please select at least one user.", className="text-muted")
    
    # Filter data for selected users
    filtered_data = completed_tasks_filtered[
        completed_tasks_filtered['IsodosePlanCompletingUser'].isin(selected_users)
    ]
    
    if len(filtered_data) == 0:
        fig = go.Figure()
        fig.update_layout(
            title="No data available",
            xaxis_title="Completion Time (days)",
            yaxis_title="Density",
            height=500
        )
        return fig, html.Div()
    
    # Convert minutes to days (1440 minutes = 1 day)
    MINUTES_PER_DAY = 1440
    completion_times_days = filtered_data['IsodosePlanMinutesToComplete'] / MINUTES_PER_DAY
    
    # Create density plot using histogram with density normalization
    fig = go.Figure()
    
    # Create histogram for overall distribution
    fig.add_trace(go.Histogram(
        x=completion_times_days,
        histnorm='probability density',
        nbinsx=50,
        name='All Selected Users',
        marker_color='steelblue',
        opacity=0.7,
        hovertemplate='Time: %{x:.2f} days<br>Density: %{y:.4f}<extra></extra>'
    ))
    
    # Add KDE curve overlay
    try:
        from scipy import stats
        data_array = completion_times_days.values
        kde = stats.gaussian_kde(data_array)
        x_kde = np.linspace(data_array.min(), data_array.max(), 200)
        y_kde = kde(x_kde)
        
        fig.add_trace(go.Scatter(
            x=x_kde,
            y=y_kde,
            mode='lines',
            name='KDE Curve',
            line=dict(color='red', width=2),
            hovertemplate='Time: %{x:.2f} days<br>Density: %{y:.4f}<extra></extra>'
        ))
    except ImportError:
        pass  # Skip KDE if scipy not available
    except Exception:
        pass  # Skip KDE if there's an error
    
    # Calculate statistics (in days)
    median_time_days = completion_times_days.median()
    mean_time_days = completion_times_days.mean()
    std_time_days = completion_times_days.std()
    count = len(filtered_data)
    
    # Add vertical lines for median and mean
    fig.add_vline(
        x=median_time_days,
        line_dash="dash",
        line_color="green",
        annotation_text=f"Median: {median_time_days:.2f} days",
        annotation_position="top"
    )
    fig.add_vline(
        x=mean_time_days,
        line_dash="dot",
        line_color="orange",
        annotation_text=f"Mean: {mean_time_days:.2f} days",
        annotation_position="top"
    )
    
    fig.update_layout(
        title=f'Distribution of Isodose Plan Completion Times ({len(selected_users)} user{"s" if len(selected_users) != 1 else ""})',
        xaxis_title='Completion Time (days)',
        yaxis_title='Density',
        height=500,
        hovermode='x unified',
        showlegend=True,
        legend=dict(yanchor="top", y=0.99, xanchor="left", x=0.01)
    )
    
    # Create stats summary
    stats_html = dbc.Row([
        dbc.Col([
            dbc.Card([
                dbc.CardBody([
                    html.H5(f"{count:,}", className="mb-0"),
                    html.Small("Total Tasks", className="text-muted")
                ])
            ], className="text-center")
        ], width=3),
        dbc.Col([
            dbc.Card([
                dbc.CardBody([
                    html.H5(f"{median_time_days:.2f} days", className="mb-0"),
                    html.Small("Median Time", className="text-muted")
                ])
            ], className="text-center")
        ], width=3),
        dbc.Col([
            dbc.Card([
                dbc.CardBody([
                    html.H5(f"{mean_time_days:.2f} days", className="mb-0"),
                    html.Small("Mean Time", className="text-muted")
                ])
            ], className="text-center")
        ], width=3),
        dbc.Col([
            dbc.Card([
                dbc.CardBody([
                    html.H5(f"{std_time_days:.2f} days", className="mb-0"),
                    html.Small("Std Deviation", className="text-muted")
                ])
            ], className="text-center")
        ], width=3),
    ])
    
    return fig, stats_html


@app.callback(
    Output('task-ranking-plot', 'figure'),
    Output('task-stats-summary', 'children'),
    Input('user-checklist', 'value')
)
def update_task_ranking(selected_users):
    # Use all valid users for ranking, regardless of selection
    # Filter data for valid users only
    ranking_data = completed_tasks_filtered[
        completed_tasks_filtered['IsodosePlanCompletingUser'].isin(valid_users)
    ].copy()
    
    # Remove rows with invalid dates
    ranking_data = ranking_data[ranking_data['IsodosePlanCompletedDateTime'].notna()].copy()
    
    if len(ranking_data) == 0:
        fig = go.Figure()
        fig.update_layout(
            title="No data available for ranking",
            height=500
        )
        return fig, html.Div()
    
    # Calculate date range
    min_date = ranking_data['IsodosePlanCompletedDateTime'].min()
    max_date = ranking_data['IsodosePlanCompletedDateTime'].max()
    date_range_days = (max_date - min_date).days + 1  # +1 to include both endpoints
    date_range_months = date_range_days / 30.44  # Average days per month
    date_range_weeks = date_range_days / 7
    
    # Calculate task counts per user
    user_task_counts = ranking_data.groupby('IsodosePlanCompletingUser').agg({
        'IsodosePlanCompletedDateTime': 'count'
    }).reset_index()
    user_task_counts.columns = ['User', 'TotalTasks']
    
    # Calculate monthly, weekly, daily rates
    user_task_counts['TasksPerMonth'] = user_task_counts['TotalTasks'] / date_range_months
    user_task_counts['TasksPerWeek'] = user_task_counts['TotalTasks'] / date_range_weeks
    user_task_counts['TasksPerDay'] = user_task_counts['TotalTasks'] / date_range_days
    
    # Sort by total tasks (descending)
    user_task_counts = user_task_counts.sort_values('TotalTasks', ascending=False)
    
    # Create bar plot
    fig = go.Figure()
    
    fig.add_trace(go.Bar(
        x=user_task_counts['User'],
        y=user_task_counts['TotalTasks'],
        text=[f"{int(total)}<br>({monthly:.1f}/mo, {weekly:.1f}/wk, {daily:.2f}/day)" 
              for total, monthly, weekly, daily in zip(
                  user_task_counts['TotalTasks'],
                  user_task_counts['TasksPerMonth'],
                  user_task_counts['TasksPerWeek'],
                  user_task_counts['TasksPerDay']
              )],
        textposition='outside',
        marker_color='steelblue',
        hovertemplate='<b>%{x}</b><br>Total: %{y} tasks<br>Monthly: %{customdata[0]:.2f}<br>Weekly: %{customdata[1]:.2f}<br>Daily: %{customdata[2]:.3f}<extra></extra>',
        customdata=user_task_counts[['TasksPerMonth', 'TasksPerWeek', 'TasksPerDay']].values
    ))
    
    fig.update_layout(
        title=f'Task Completion Rankings (Data from {min_date.strftime("%Y-%m-%d")} to {max_date.strftime("%Y-%m-%d")}, {date_range_days:.0f} days)',
        xaxis_title='User',
        yaxis_title='Total Tasks Completed',
        xaxis={'tickangle': -45, 'tickfont': {'size': 10}},
        yaxis={'tickformat': ',.0f'},
        height=600,
        showlegend=False,
        hovermode='closest',
        margin=dict(b=150)
    )
    
    # Create summary stats
    total_tasks_all = user_task_counts['TotalTasks'].sum()
    avg_per_user = user_task_counts['TotalTasks'].mean()
    top_user = user_task_counts.iloc[0]
    
    stats_html = dbc.Row([
        dbc.Col([
            dbc.Card([
                dbc.CardBody([
                    html.H5(f"{date_range_days:.0f}", className="mb-0"),
                    html.Small("Days in Dataset", className="text-muted")
                ])
            ], className="text-center")
        ], width=2),
        dbc.Col([
            dbc.Card([
                dbc.CardBody([
                    html.H5(f"{total_tasks_all:,}", className="mb-0"),
                    html.Small("Total Tasks (All Users)", className="text-muted")
                ])
            ], className="text-center")
        ], width=2),
        dbc.Col([
            dbc.Card([
                dbc.CardBody([
                    html.H5(f"{avg_per_user:.1f}", className="mb-0"),
                    html.Small("Avg Tasks per User", className="text-muted")
                ])
            ], className="text-center")
        ], width=2),
        dbc.Col([
            dbc.Card([
                dbc.CardBody([
                    html.H5(f"{top_user['User']}", className="mb-0"),
                    html.Small("Top User", className="text-muted")
                ])
            ], className="text-center")
        ], width=2),
        dbc.Col([
            dbc.Card([
                dbc.CardBody([
                    html.H5(f"{int(top_user['TotalTasks'])}", className="mb-0"),
                    html.Small("Top User Tasks", className="text-muted")
                ])
            ], className="text-center")
        ], width=2),
        dbc.Col([
            dbc.Card([
                dbc.CardBody([
                    html.H5(f"{top_user['TasksPerMonth']:.1f}/mo", className="mb-0"),
                    html.Small("Top User Rate", className="text-muted")
                ])
            ], className="text-center")
        ], width=2),
    ])
    
    return fig, stats_html


if __name__ == '__main__':
    app.run(debug=True, port=8051)

