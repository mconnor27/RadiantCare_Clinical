import pandas as pd
import plotly.graph_objects as go
import plotly.express as px

# Read the CSV file
print("Loading data...")
df = pd.read_csv('data/Workflow.csv')

# Filter for rows where IsodosePlanCompletingUser is not empty/null
print("Filtering completed Isodose Plan tasks...")
completed_tasks = df[
    df['IsodosePlanCompletingUser'].notna() & 
    (df['IsodosePlanCompletingUser'] != '') &
    df['IsodosePlanMinutesToComplete'].notna()
].copy()

print(f"Found {len(completed_tasks)} completed Isodose Plan tasks")

# Show some statistics about the completion times
print(f"\nCompletion time statistics:")
print(f"  Min: {completed_tasks['IsodosePlanMinutesToComplete'].min():.2f} minutes")
print(f"  Max: {completed_tasks['IsodosePlanMinutesToComplete'].max():.2f} minutes")
print(f"  Mean: {completed_tasks['IsodosePlanMinutesToComplete'].mean():.2f} minutes")
print(f"  Median: {completed_tasks['IsodosePlanMinutesToComplete'].median():.2f} minutes")
print(f"  95th percentile: {completed_tasks['IsodosePlanMinutesToComplete'].quantile(0.95):.2f} minutes")

# Filter out extreme outliers and negative values
# This helps focus on realistic completion times
outlier_threshold = 10000
before_filter = len(completed_tasks)
completed_tasks_filtered = completed_tasks[
    (completed_tasks['IsodosePlanMinutesToComplete'] > 0) &
    (completed_tasks['IsodosePlanMinutesToComplete'] <= outlier_threshold)
].copy()
print(f"\nFiltered out {before_filter - len(completed_tasks_filtered)} tasks (negative values or > {outlier_threshold} minutes)")
print(f"Remaining tasks: {len(completed_tasks_filtered)}")

# Calculate median completion time per user
print("Calculating medians...")
avg_times = completed_tasks_filtered.groupby('IsodosePlanCompletingUser')['IsodosePlanMinutesToComplete'].agg([
    'median',
    'count'
]).reset_index()

avg_times.columns = ['User', 'MedianMinutes', 'TaskCount']

# Filter out users with fewer than 10 completed tasks
min_tasks = 10
before_user_filter = len(avg_times)
avg_times = avg_times[avg_times['TaskCount'] >= min_tasks].copy()
print(f"\nFiltered out {before_user_filter - len(avg_times)} users with fewer than {min_tasks} completed tasks")

# Sort by median minutes (descending)
avg_times = avg_times.sort_values('MedianMinutes', ascending=False)

print(f"\nFound {len(avg_times)} unique users (with >= {min_tasks} tasks)")
print("\nTop users by median completion time:")
print(avg_times.head(10))

# Format text labels - show hours if > 60 minutes
def format_time(minutes):
    if minutes >= 60:
        hours = minutes / 60
        return f"{hours:.1f} hrs<br>({int(minutes):.0f} min)"
    else:
        return f"{minutes:.1f} min"

# Create bar plot
fig = go.Figure(data=[
    go.Bar(
        x=avg_times['User'],
        y=avg_times['MedianMinutes'],
        text=[f"{format_time(val)}<br>({count} tasks)" for val, count in zip(avg_times['MedianMinutes'], avg_times['TaskCount'])],
        textposition='outside',
        marker_color='steelblue',
        hovertemplate='<b>%{x}</b><br>Median: %{y:.2f} minutes (%{customdata[0]:.2f} hours)<br>Tasks: %{customdata[1]}<extra></extra>',
        customdata=[[m/60, c] for m, c in zip(avg_times['MedianMinutes'], avg_times['TaskCount'])]
    )
])

fig.update_layout(
    title={
        'text': 'Median Isodose Plan Completion Time by User',
        'x': 0.5,
        'xanchor': 'center'
    },
    xaxis_title='Completing User',
    yaxis_title='Median Completion Time (minutes)',
    xaxis={'tickangle': -45, 'tickfont': {'size': 10}},
    yaxis={'tickformat': ',.0f'},
    height=700,
    showlegend=False,
    hovermode='closest',
    margin=dict(b=150)  # Extra bottom margin for rotated labels
)

# Save as HTML
output_file = 'isodose_plan_analysis.html'
fig.write_html(output_file)
print(f"\nPlot saved to {output_file}")

# Also show the plot
fig.show()

