"""
Data loading and preprocessing utilities
"""
import pandas as pd
from pathlib import Path
from config.settings import TASK_FILE_PATTERNS, MIN_YEAR, MD_NAMES


def find_task_file(data_dir):
    """
    Searches for the task CSV file in the data directory.
    Looks for files matching common patterns.
    """
    data_path = Path(data_dir)

    # First, try exact matches
    for name in TASK_FILE_PATTERNS:
        file_path = data_path / name
        if file_path.exists():
            return str(file_path)

    # If no exact match, search for CSV files with "schedule" or "department" in the name
    csv_files = list(data_path.glob("*[Ss]chedule*.csv"))
    if not csv_files:
        csv_files = list(data_path.glob("*[Dd]epartment*.csv"))
    if csv_files:
        return str(csv_files[0])

    return None


def extract_first_md(resource_name):
    """
    Extract the first MD from ResourceName field.
    Returns cleaned MD name (e.g., "Hartman" instead of "Dr. Hartman (Profile Not Attached)").
    Returns None if no MD found.
    """
    if pd.isna(resource_name):
        return None

    resource_str = str(resource_name)

    # Split by comma to get individual resources
    resources = [r.strip() for r in resource_str.split(',')]

    # Find first resource that contains an MD name
    for resource in resources:
        for md in MD_NAMES:
            if md in resource:
                # Return just the MD name (cleaned up)
                return md

    return None


def consolidate_activity(activity_name):
    """
    Consolidate ActivityName: SRS stays as "Draw Volumes (SRS)",
    everything else with "Draw" becomes "Draw Volumes"
    """
    if pd.isna(activity_name):
        return activity_name
    activity_str = str(activity_name)
    if 'SRS' in activity_str:
        return 'Draw Volumes (SRS)'
    elif 'Draw' in activity_str:
        return 'Draw Volumes'
    else:
        return activity_str


def load_data(file_path):
    """
    Load and preprocess task data from CSV file.

    Args:
        file_path: Path to CSV file

    Returns:
        DataFrame with processed task data
    """
    df = pd.read_csv(file_path)
    df['AppointmentTime'] = pd.to_datetime(df['AppointmentTime'], errors='coerce')

    # Filter for completed tasks only
    df = df[df['AppointmentStatus'] == 'Completed'].copy()

    # Drop rows without appointment time
    df = df.dropna(subset=['AppointmentTime'])

    # Extract first MD for each row
    df['FirstMD'] = df['ResourceName'].apply(extract_first_md)

    # Filter out rows with no MD
    df = df[df['FirstMD'].notna()].copy()

    # Filter to MIN_YEAR onwards
    df = df[df['AppointmentTime'].dt.year >= MIN_YEAR].copy()

    # Consolidate activity names
    df['ActivityName'] = df['ActivityName'].apply(consolidate_activity)

    return df
