import pandas as pd
import plotly.graph_objects as go

# Load data
df = pd.read_csv('Tasks Completed and Due Date Ryan.csv')
df['ActivityEndDateTime'] = pd.to_datetime(df['ActivityEndDateTime'], format='%m/%d/%Y', errors='coerce')
df = df.dropna(subset=['ActivityEndDateTime'])

# MD names to look for (using partial matching)
md_names = ['Allen', 'Connor', 'Deig', 'Hartman', 'Horton', 'Gruhl', 'Raymond', 'Reece', 'Suszko', 'Tinnel', 'Vera', 'Werner']

# Function to check if ResourceName contains any MD name
def is_md(resource_name):
    if pd.isna(resource_name):
        return False
    resource_str = str(resource_name)
    return any(md in resource_str for md in md_names)

# Mark each row as MD or not
df['is_md'] = df['ResourceName'].apply(is_md)

# Get non-MD entries
non_md = df[~df['is_md']].copy()
md_only = df[df['is_md']].copy()

# Count by year
non_md['year'] = non_md['ActivityEndDateTime'].dt.year
md_only['year'] = md_only['ActivityEndDateTime'].dt.year

yearly_counts_non_md = non_md.groupby('year').size().reset_index(name='non_md_count')
yearly_counts_md = md_only.groupby('year').size().reset_index(name='md_count')

# Merge the counts
yearly_counts = pd.merge(yearly_counts_non_md, yearly_counts_md, on='year', how='outer').fillna(0)
yearly_counts['total'] = yearly_counts['non_md_count'] + yearly_counts['md_count']
yearly_counts['non_md_percent'] = (yearly_counts['non_md_count'] / yearly_counts['total'] * 100).round(2)

print('=' * 80)
print('Non-MD ResourceName entries by year:')
print('=' * 80)
print(yearly_counts.to_string(index=False))

print(f'\n{"=" * 80}')
print('Summary:')
print('=' * 80)
print(f'Total non-MD entries: {len(non_md):,}')
print(f'Total MD entries: {len(md_only):,}')
print(f'Percentage non-MD: {len(non_md) / len(df) * 100:.2f}%')

print(f'\n{"=" * 80}')
print('Most common non-MD ResourceNames:')
print('=' * 80)
print(non_md['ResourceName'].value_counts().head(30).to_string())

print(f'\n{"=" * 80}')
print('Sample non-MD entries (first 20):')
print('=' * 80)
print(non_md[['ActivityEndDateTime', 'ResourceName', 'ActivityName']].head(20).to_string(index=False))

# Create visualization
fig = go.Figure()

fig.add_trace(go.Bar(
    x=yearly_counts['year'],
    y=yearly_counts['non_md_count'],
    name='Non-MD Entries',
    marker_color='#E74C3C'
))

fig.add_trace(go.Bar(
    x=yearly_counts['year'],
    y=yearly_counts['md_count'],
    name='MD Entries',
    marker_color='#3498DB'
))

fig.update_layout(
    title='MD vs Non-MD ResourceName Entries Over Time',
    xaxis_title='Year',
    yaxis_title='Count',
    barmode='stack',
    height=600,
    showlegend=True
)

fig.write_html('non_md_analysis.html')
print(f'\n{"=" * 80}')
print('Visualization saved to: non_md_analysis.html')
print('=' * 80)
