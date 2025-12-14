"""
Find patients with completed draw volumes but no completed isodose task
"""
import pandas as pd

# Read the CSV file
print("Loading data...")
df = pd.read_csv('data/Workflow.csv')

# Find patients with completed draw volumes
draw_completed = df[df['DrawCompletedDateTime'].notna()].copy()
print(f"\nPatients with completed draw volumes: {draw_completed['PatientId'].nunique():,}")

# Find patients with completed isodose
isodose_completed = df[df['IsodosePlanCompletedDateTime'].notna()].copy()
print(f"Patients with completed isodose: {isodose_completed['PatientId'].nunique():,}")

# Find patients with draw but NOT isodose
patients_with_draw = set(draw_completed['PatientId'].dropna().unique())
patients_with_isodose = set(isodose_completed['PatientId'].dropna().unique())
patients_draw_no_isodose = patients_with_draw - patients_with_isodose

print(f"\nPatients with draw but NO isodose: {len(patients_draw_no_isodose):,}")

# Get sample of these patients
sample_patients = list(patients_draw_no_isodose)[:20]  # First 20

# Filter data for these sample patients
sample_data = draw_completed[
    draw_completed['PatientId'].isin(sample_patients)
].copy()

# Select relevant columns for display
display_cols = [
    'PatientId',
    'PatientFullName',
    'DrawCompletedDateTime',
    'DrawCompletingMD',
    'DrawMinutesToComplete',
    'IsodosePlanStartDateTime',
    'IsodosePlanDueDateTime',
    'IsodosePlanCompletedDateTime',
    'IsodosePlanCompletingUser',
    'SimulationDateTime'
]

# Only show columns that exist
available_cols = [col for col in display_cols if col in sample_data.columns]
sample_display = sample_data[available_cols].copy()

# Sort by DrawCompletedDateTime (most recent first)
if 'DrawCompletedDateTime' in sample_display.columns:
    sample_display['DrawCompletedDateTime'] = pd.to_datetime(
        sample_display['DrawCompletedDateTime'], 
        errors='coerce'
    )
    sample_display = sample_display.sort_values('DrawCompletedDateTime', ascending=False)

# Remove duplicates per patient (show one row per patient)
sample_display = sample_display.drop_duplicates(subset=['PatientId'], keep='first')

# Also get some recent cases
recent_draw = draw_completed[
    (draw_completed['PatientId'].isin(patients_draw_no_isodose)) &
    (pd.to_datetime(draw_completed['DrawCompletedDateTime'], errors='coerce') >= pd.Timestamp('2020-01-01'))
].copy()

if len(recent_draw) > 0:
    recent_cols = [col for col in display_cols if col in recent_draw.columns]
    recent_display = recent_draw[recent_cols].copy()
    if 'DrawCompletedDateTime' in recent_display.columns:
        recent_display['DrawCompletedDateTime'] = pd.to_datetime(
            recent_display['DrawCompletedDateTime'], 
            errors='coerce'
        )
        recent_display = recent_display.sort_values('DrawCompletedDateTime', ascending=False)
    recent_display = recent_display.drop_duplicates(subset=['PatientId'], keep='first').head(10)

print(f"\n{'='*80}")
print(f"SAMPLE OF {len(sample_display)} PATIENTS WITH DRAW BUT NO ISODOSE (OLDEST CASES):")
print(f"{'='*80}\n")

# Display the sample
pd.set_option('display.max_columns', None)
pd.set_option('display.width', None)
pd.set_option('display.max_colwidth', 30)

print(sample_display.to_string(index=False))

# Also save to CSV
output_file = 'patients_draw_no_isodose_sample.csv'
sample_display.to_csv(output_file, index=False)
print(f"\n\nSample saved to: {output_file}")

# Show some statistics
print(f"\n{'='*80}")
print("STATISTICS:")
print(f"{'='*80}")
print(f"Total patients with draw but no isodose: {len(patients_draw_no_isodose):,}")

# Check for patients with isodose started but not completed (across all data)
all_draw_no_isodose = draw_completed[
    draw_completed['PatientId'].isin(patients_draw_no_isodose)
].copy()
isodose_started_not_completed = all_draw_no_isodose[
    all_draw_no_isodose['IsodosePlanStartDateTime'].notna() &
    all_draw_no_isodose['IsodosePlanCompletedDateTime'].isna()
].copy()

print(f"\n{'='*80}")
print("ADDITIONAL ANALYSIS:")
print(f"{'='*80}")
print(f"Total patients with draw but no isodose: {len(patients_draw_no_isodose):,}")
print(f"Patients with isodose STARTED but not completed: {isodose_started_not_completed['PatientId'].nunique():,}")

if len(recent_display) > 0:
    print(f"\n{'='*80}")
    print(f"RECENT CASES (2020+): {len(recent_display)} PATIENTS")
    print(f"{'='*80}\n")
    print(recent_display.to_string(index=False))

if len(isodose_started_not_completed) > 0:
    print(f"\n{'='*80}")
    print(f"SAMPLE OF PATIENTS WITH ISODOSE STARTED BUT NOT COMPLETED:")
    print(f"{'='*80}\n")
    started_cols = [col for col in display_cols if col in isodose_started_not_completed.columns]
    started_display = isodose_started_not_completed[started_cols].copy()
    if 'IsodosePlanStartDateTime' in started_display.columns:
        started_display['IsodosePlanStartDateTime'] = pd.to_datetime(
            started_display['IsodosePlanStartDateTime'], 
            errors='coerce'
        )
        started_display = started_display.sort_values('IsodosePlanStartDateTime', ascending=False)
    started_display = started_display.drop_duplicates(subset=['PatientId'], keep='first').head(10)
    print(started_display.to_string(index=False))

