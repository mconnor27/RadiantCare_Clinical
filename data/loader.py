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


def classify_appointment_type(row):
    """
    Classify appointment as 'Consult' (new patient) or 'Follow-Up' based on duration and notes.

    Rules:
    1. >60 minutes → Consult
    2. ≤60 minutes:
       - ActivityName in ["Consult", "Consult - Special request", "Consult- ADD ON"]:
         → Consult (default), unless notes mention follow-up/re-eval
       - ActivityName = "Virtual Consult/Follow Up":
         → If <60min: Follow-Up
         → If =60min: Check notes (follow-up indicators → Follow-Up, else → Consult)

    Args:
        row: DataFrame row with ActivityPlannedLength, ActivityName, ActivityNote

    Returns:
        str: 'Consult' or 'Follow-Up'
    """
    import re

    # Get duration (convert to numeric)
    duration = pd.to_numeric(row.get('ActivityPlannedLength'), errors='coerce')
    activity_name = str(row.get('ActivityName', '')).strip()
    activity_note = str(row.get('ActivityNote', ''))

    # Pattern matching for follow-up indicators (case-insensitive)
    followup_pattern = re.compile(r'follow[\s-]?up|re[\s-]?eval|followup|reeval', re.IGNORECASE)
    new_pattern = re.compile(r'\bnew\b', re.IGNORECASE)

    # Rule 1: >60 minutes → Consult
    if pd.notna(duration) and duration > 60:
        return 'Consult'

    # Rule 2: ≤60 minutes or duration unknown
    # Check if it's a standard consult type
    standard_consult_types = ['Consult', 'Consult - Special request', 'Consult- ADD ON']

    if activity_name in standard_consult_types:
        # Default to Consult, unless notes indicate follow-up
        if followup_pattern.search(activity_note):
            return 'Follow-Up'
        else:
            return 'Consult'

    # Virtual Consult/Follow Up type
    elif 'Virtual Consult/Follow Up' in activity_name:
        if pd.notna(duration) and duration < 60:
            # <60 minutes → Follow-Up
            return 'Follow-Up'
        elif pd.notna(duration) and duration == 60:
            # =60 minutes: check notes
            if followup_pattern.search(activity_note):
                return 'Follow-Up'
            else:
                # No follow-up indicator or mentions "new" → Consult
                return 'Consult'
        else:
            # Duration unknown, check notes
            if followup_pattern.search(activity_note):
                return 'Follow-Up'
            else:
                return 'Consult'

    # Default fallback for any other type
    return 'Consult'


def load_consults_data(file_path):
    """
    Load and preprocess consults data from exam CSV file.

    Args:
        file_path: Path to exam CSV file

    Returns:
        DataFrame with processed consults data
    """
    # Read CSV with error handling - on_bad_lines='skip' will skip problematic rows
    df = pd.read_csv(file_path, encoding='utf-8-sig', on_bad_lines='skip', engine='python')

    # Filter out cancelled appointments
    df = df[df['AppointmentStatus'] != 'Cancelled'].copy()

    # Parse date columns - use ScheduledEndTime or ActivityStartDateTime as AppointmentTime
    df['ScheduledEndTime'] = pd.to_datetime(df['ScheduledEndTime'], errors='coerce')
    df['ActivityStartDateTime'] = pd.to_datetime(df['ActivityStartDateTime'], errors='coerce')
    df['ActivityEndDateTime'] = pd.to_datetime(df['ActivityEndDateTime'], errors='coerce')

    # Use ScheduledEndTime if available, otherwise ActivityStartDateTime
    df['AppointmentTime'] = df['ScheduledEndTime'].fillna(df['ActivityStartDateTime'])

    # Drop rows without appointment time
    df = df.dropna(subset=['AppointmentTime'])

    # Filter for activities containing "Consult" (case-insensitive)
    df = df[df['ActivityName'].str.contains('Consult', case=False, na=False)].copy()

    # Extract first MD for each row
    df['FirstMD'] = df['ResourceName'].apply(extract_first_md)

    # Filter out rows with no MD
    df = df[df['FirstMD'].notna()].copy()

    # Filter to MIN_YEAR onwards
    df = df[df['AppointmentTime'].dt.year >= MIN_YEAR].copy()

    # Classify appointment type (Consult vs Follow-Up)
    df['AppointmentType'] = df.apply(classify_appointment_type, axis=1)

    return df
