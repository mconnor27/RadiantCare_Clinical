import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# Load Department Schedule data
df = pd.read_csv('Department Schedule No Grouping All.csv')
df['AppointmentTime'] = pd.to_datetime(df['AppointmentTime'], errors='coerce')
df = df[df['AppointmentStatus'] == 'Completed'].copy()
df = df.dropna(subset=['AppointmentTime'])

# MD names to identify
md_names = ['Allen', 'Connor', 'Deig', 'Hartman', 'Horton', 'Gruhl', 'Raymond', 'Reece', 'Suszko', 'Tinnel', 'Vera', 'Werner']

# Function to check if ResourceName contains any MD name
def has_md_name(resource_name):
    if pd.isna(resource_name):
        return False
    resource_str = str(resource_name)
    return any(md in resource_str for md in md_names)

# Categorize each entry
df['has_md'] = df['ResourceName'].apply(has_md_name)

# Split ResourceNames by comma to count how many resources are listed
df['resource_count'] = df['ResourceName'].astype(str).str.split(',').str.len()

# Categorize entries
df['category'] = 'Unknown'
df.loc[df['has_md'], 'category'] = 'Has MD'
df.loc[~df['has_md'], 'category'] = 'No MD'

# Extract year
df['year'] = df['AppointmentTime'].dt.year

# Analysis by year
yearly_analysis = df.groupby(['year', 'category']).size().reset_index(name='count')
yearly_analysis_pivot = yearly_analysis.pivot(index='year', columns='category', values='count').fillna(0)
yearly_analysis_pivot['total'] = yearly_analysis_pivot.sum(axis=1)
yearly_analysis_pivot['no_md_percent'] = (yearly_analysis_pivot['No MD'] / yearly_analysis_pivot['total'] * 100).round(2)

print('=' * 80)
print('Department Schedule Analysis: MD vs No MD in ResourceName')
print('=' * 80)
print(yearly_analysis_pivot.to_string())

print('\n' + '=' * 80)
print('Summary Statistics:')
print('=' * 80)
has_md_count = df['has_md'].sum()
no_md_count = len(df) - has_md_count
print(f'Total entries with at least one MD: {has_md_count:,}')
print(f'Total entries with NO MD: {no_md_count:,}')
print(f'Percentage with NO MD: {no_md_count / len(df) * 100:.2f}%')

print('\n' + '=' * 80)
print('Resource Count Distribution:')
print('=' * 80)
print(df['resource_count'].value_counts().sort_index().to_string())

print('\n' + '=' * 80)
print('Most common NO MD ResourceName combinations (top 30):')
print('=' * 80)
no_md_df = df[~df['has_md']]
print(no_md_df['ResourceName'].value_counts().head(30).to_string())

print('\n' + '=' * 80)
print('Most common WITH MD ResourceName values (top 30):')
print('=' * 80)
has_md_df = df[df['has_md']]
print(has_md_df['ResourceName'].value_counts().head(30).to_string())

print('\n' + '=' * 80)
print('Multiple Resources Analysis:')
print('=' * 80)
multiple_resources = df[df['resource_count'] > 1]
print(f'Entries with multiple resources: {len(multiple_resources):,} ({len(multiple_resources) / len(df) * 100:.2f}%)')
print(f'Of these, how many have at least one MD: {multiple_resources["has_md"].sum():,}')
print(f'Of these, how many have NO MD: {len(multiple_resources) - multiple_resources["has_md"].sum():,}')

print('\n' + '=' * 80)
print('Sample multiple resource entries with NO MD:')
print('=' * 80)
multi_no_md = multiple_resources[~multiple_resources['has_md']]
for idx, row in multi_no_md.head(10).iterrows():
    print(f"\nDate: {row['AppointmentTime']}")
    print(f"ResourceName: {row['ResourceName']}")
    print(f"Activity: {row['ActivityName']}")
    print(f"Resource Count: {row['resource_count']}")

# Create visualization
fig = make_subplots(
    rows=2, cols=1,
    subplot_titles=('MD vs No MD Entries Over Time', 'Percentage with No MD Over Time'),
    vertical_spacing=0.12
)

# Stacked bar chart
fig.add_trace(
    go.Bar(
        x=yearly_analysis_pivot.index,
        y=yearly_analysis_pivot['No MD'],
        name='No MD',
        marker_color='#E74C3C'
    ),
    row=1, col=1
)

fig.add_trace(
    go.Bar(
        x=yearly_analysis_pivot.index,
        y=yearly_analysis_pivot['Has MD'],
        name='Has MD',
        marker_color='#3498DB'
    ),
    row=1, col=1
)

# Percentage line chart
fig.add_trace(
    go.Scatter(
        x=yearly_analysis_pivot.index,
        y=yearly_analysis_pivot['no_md_percent'],
        mode='lines+markers',
        name='% No MD',
        marker=dict(size=8),
        line=dict(width=3, color='#E74C3C'),
        showlegend=False
    ),
    row=2, col=1
)

fig.update_xaxes(title_text="Year", row=1, col=1)
fig.update_xaxes(title_text="Year", row=2, col=1)
fig.update_yaxes(title_text="Count", row=1, col=1)
fig.update_yaxes(title_text="Percentage (%)", row=2, col=1)

fig.update_layout(
    height=800,
    barmode='stack',
    title_text='Department Schedule: MD vs No MD Analysis',
    showlegend=True
)

fig.write_html('dept_schedule_md_analysis.html')
print(f'\n{"=" * 80}')
print('Visualization saved to: dept_schedule_md_analysis.html')
print('=' * 80)
