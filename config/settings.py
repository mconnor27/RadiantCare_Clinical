"""
Application configuration and constants
"""
import os
from pathlib import Path

# App metadata
APP_TITLE = "Radiant Care Clinical Dashboard"
APP_ICON = "🏥"

# MD names for identification
MD_NAMES = [
    'Allen', 'Connor', 'Deig', 'Hartman', 'Horton', 'Gruhl',
    'Raymond', 'Reece', 'Suszko', 'Tinnel', 'Vera', 'Werner'
]

# Data directory configuration
def get_data_directory():
    """
    Gets the data directory from multiple sources in priority order:
    1. Environment variable DATA_DIR
    2. config.txt file in app directory
    3. data/ subdirectory (default)
    """
    # Check environment variable
    if 'DATA_DIR' in os.environ:
        data_dir = os.environ['DATA_DIR']
        if os.path.isdir(data_dir):
            return data_dir

    # Check config file
    config_file = Path(__file__).parent.parent / 'config.txt'
    if config_file.exists():
        with open(config_file, 'r') as f:
            data_dir = f.read().strip()
            if os.path.isdir(data_dir):
                return data_dir

    # Default to data subdirectory
    return str(Path(__file__).parent.parent / 'data')

# File search patterns
TASK_FILE_PATTERNS = [
    "Department Schedule No Grouping All.csv",
    "department_schedule.csv",
    "schedule.csv"
]

# Date filtering
MIN_YEAR = 2015
