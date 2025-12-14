"""
Quick script to compare simulations vs completed isodose tasks
"""
import pandas as pd

# Read the CSV file
print("Loading data...")
df = pd.read_csv('data/Workflow.csv')

print(f"\nTotal rows in dataset: {len(df):,}")

# Count simulations (rows with SimulationDateTime)
simulations = df[df['SimulationDateTime'].notna()].copy()
print(f"\nRows with SimulationDateTime: {len(simulations):,}")

# Count completed isodose tasks (rows with IsodosePlanCompletedDateTime)
isodose_completed = df[df['IsodosePlanCompletedDateTime'].notna()].copy()
print(f"Rows with IsodosePlanCompletedDateTime: {len(isodose_completed):,}")

# Count rows with both
both = df[
    df['SimulationDateTime'].notna() & 
    df['IsodosePlanCompletedDateTime'].notna()
].copy()
print(f"Rows with BOTH simulation and completed isodose: {len(both):,}")

# Count unique simulations (by SimulationDateTime)
unique_simulations = simulations['SimulationDateTime'].nunique()
print(f"\nUnique simulation dates/times: {unique_simulations:,}")

# Count unique completed isodose tasks
unique_isodose = isodose_completed['IsodosePlanCompletedDateTime'].nunique()
print(f"Unique completed isodose dates/times: {unique_isodose:,}")

# Check if simulations are unique per patient or can have multiple
print(f"\nUnique patients with simulations: {simulations['PatientId'].nunique():,}")
print(f"Unique patients with completed isodose: {isodose_completed['PatientId'].nunique():,}")

# Count completed draw volumes tasks
draw_completed = df[df['DrawCompletedDateTime'].notna()].copy()
print(f"\nRows with DrawCompletedDateTime: {len(draw_completed):,}")

# Count by patient - how many patients have both
patients_with_sim = set(simulations['PatientId'].dropna().unique())
patients_with_isodose = set(isodose_completed['PatientId'].dropna().unique())
patients_with_draw = set(draw_completed['PatientId'].dropna().unique())
patients_with_both = patients_with_sim & patients_with_isodose
patients_with_sim_and_draw = patients_with_sim & patients_with_draw

print(f"\nPatients with simulation: {len(patients_with_sim):,}")
print(f"Patients with completed isodose: {len(patients_with_isodose):,}")
print(f"Patients with completed draw volumes: {len(patients_with_draw):,}")
print(f"Patients with BOTH simulation and isodose: {len(patients_with_both):,}")
print(f"Patients with BOTH simulation and draw volumes: {len(patients_with_sim_and_draw):,}")

# Calculate percentage
pct_sim_with_draw = (len(patients_with_sim_and_draw) / len(patients_with_sim) * 100) if len(patients_with_sim) > 0 else 0

# Show some statistics
print("\n" + "="*60)
print("SUMMARY:")
print("="*60)
print(f"Total Simulations: {len(simulations):,}")
print(f"Total Completed Isodose Tasks: {len(isodose_completed):,}")
print(f"Total Completed Draw Volumes Tasks: {len(draw_completed):,}")
print(f"\nRatio (Isodose/Simulations): {len(isodose_completed)/len(simulations):.2f}" if len(simulations) > 0 else "Ratio: N/A")
print(f"Ratio (Draw/Simulations): {len(draw_completed)/len(simulations):.2f}" if len(simulations) > 0 else "Ratio: N/A")
print(f"\nUnique Simulation Events: {unique_simulations:,}")
print(f"Unique Isodose Completion Events: {unique_isodose:,}")
print(f"Unique Draw Completion Events: {draw_completed['DrawCompletedDateTime'].nunique():,}")
print(f"\n{'='*60}")
print(f"PATIENTS WITH SIMULATIONS:")
print(f"{'='*60}")
print(f"Total patients with simulations: {len(patients_with_sim):,}")
print(f"Patients with completed draw volumes: {len(patients_with_sim_and_draw):,}")
print(f"Percentage: {pct_sim_with_draw:.2f}%")

