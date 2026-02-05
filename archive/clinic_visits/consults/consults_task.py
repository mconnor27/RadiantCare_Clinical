"""
Consults task implementation
"""
import pandas as pd
from tasks.draw_volumes.draw_volumes_task import DrawVolumesTask


class ConsultsTask(DrawVolumesTask):
    """Task for analyzing consult completion"""

    def __init__(self, df):
        """
        Initialize Consults task.

        Args:
            df: Pandas DataFrame with consults data (already preprocessed)
        """
        # Initialize base task with df
        self.df = df

        # Get unique values for filters
        self.physicians = sorted(df['FirstMD'].dropna().unique())
        # Placeholder for departments (empty list for now since DepartmentName doesn't exist)
        self.departments = []
        # Get unique activity names
        self.activity_names = sorted(df['ActivityName'].dropna().unique())
        # Get unique appointment types
        self.appointment_types = sorted(df['AppointmentType'].dropna().unique())

        # Get year range for slider
        self.min_year = int(df['AppointmentTime'].dt.year.min())
        self.max_year = int(df['AppointmentTime'].dt.year.max())

    def filter_data(self, selected_phys, selected_depts, selected_acts, selected_types, year_range):
        """
        Filter dataframe based on user selections.

        Args:
            selected_phys: List of selected physician names
            selected_depts: List of selected department names (placeholder for now)
            selected_acts: List of selected activity names
            selected_types: List of selected appointment types
            year_range: Tuple of (min_year, max_year)

        Returns:
            Filtered DataFrame
        """
        if selected_phys is None:
            selected_phys = self.physicians
        # Department filter is placeholder - ignore for now
        if selected_depts is None:
            selected_depts = self.departments
        if selected_acts is None:
            selected_acts = self.activity_names
        if selected_types is None:
            selected_types = self.appointment_types

        filtered_df = self.df[
            (self.df['FirstMD'].isin(selected_phys)) &
            (self.df['ActivityName'].isin(selected_acts)) &
            (self.df['AppointmentType'].isin(selected_types)) &
            (self.df['AppointmentTime'].dt.year >= year_range[0]) &
            (self.df['AppointmentTime'].dt.year <= year_range[1])
        ].copy()

        return filtered_df

    def get_sidebar_layout(self, state=None):
        """Implemented in consults_sidebar.py"""
        from clinic_visits.consults.consults_sidebar import create_sidebar_layout
        return create_sidebar_layout(self, state=state)

    def get_main_panel_layout(self):
        """Implemented in consults_panel.py"""
        from clinic_visits.consults.consults_panel import create_main_panel_layout
        return create_main_panel_layout()

    def register_callbacks(self, app):
        """Implemented in consults_panel.py"""
        from clinic_visits.consults.consults_panel import register_callbacks
        register_callbacks(app, self)
