"""
Scheduling task implementation
"""
import pandas as pd
from datetime import datetime, timedelta
from tasks.base_task import BaseTask


class SchedulingTask(BaseTask):
    """Task for managing appointment scheduling"""

    def __init__(self, df):
        """
        Initialize Scheduling task.

        Args:
            df: Pandas DataFrame with appointment data
        """
        super().__init__(df)

        # Process the appointment data
        self.df = self._process_appointments(df)
        
        # Pre-filter to only include specific appointment types
        self.df = self.df[self.df['ActivityName'].isin(['HOLD CONSULT', 'HOLD RE EVAL/2 FOLLOW UPS'])]

        # Get unique values for filters (reverse alphabetical for departments)
        self.departments = sorted(self.df['DepartmentName'].dropna().unique(), reverse=True)
        self.physicians = sorted(self.df['ResourceName'].dropna().unique())
        self.activity_types = ['HOLD CONSULT', 'HOLD RE EVAL/2 FOLLOW UPS']  # Only these two types

        # Department color mapping (reverse alpha order: Lacey, Centralia, Aberdeen)
        self.department_colors = {
            'Lacey': {'bg': '#e3f2fd', 'border': '#2196f3'},        # Light blue
            'Centralia': {'bg': '#ffebee', 'border': '#f44336'},    # Light red
            'Aberdeen': {'bg': '#e8f5e9', 'border': '#4caf50'}      # Light green
        }

    def _process_appointments(self, df):
        """
        Process appointment data.

        Args:
            df: Original DataFrame

        Returns:
            DataFrame with processed appointment data
        """
        df = df.copy()

        # Clean up DepartmentName - remove leading asterisks
        df['DepartmentName'] = df['DepartmentName'].str.replace('*', '', regex=False)

        # Parse AppointmentDateTime column
        df['AppointmentDateTime'] = pd.to_datetime(df['AppointmentDateTime'], format='%m/%d/%Y %I:%M:%S %p')

        # Extract date and time components
        df['Date'] = df['AppointmentDateTime'].dt.date
        df['Time'] = df['AppointmentDateTime'].dt.time
        df['Hour'] = df['AppointmentDateTime'].dt.hour
        df['DayOfWeek'] = df['AppointmentDateTime'].dt.day_name()
        df['WeekStart'] = df['AppointmentDateTime'].dt.to_period('W').apply(lambda r: r.start_time)

        # Calculate appointment end time
        df['EndTime'] = df['AppointmentDateTime'] + pd.to_timedelta(df['ActivityPlannedLength'], unit='m')

        return df

    def filter_data(self, selected_departments, selected_physicians, selected_activity_types=None, time_range=None):
        """
        Filter dataframe based on user selections.

        Args:
            selected_departments: List of selected departments
            selected_physicians: List of selected physicians
            selected_activity_types: List of selected activity types
            time_range: Tuple of (start_hour, end_hour) for time filtering

        Returns:
            Filtered DataFrame
        """
        if selected_departments is None:
            selected_departments = self.departments
        if selected_physicians is None:
            selected_physicians = self.physicians
        if selected_activity_types is None:
            selected_activity_types = self.activity_types

        filtered_df = self.df[
            (self.df['DepartmentName'].isin(selected_departments)) &
            (self.df['ResourceName'].isin(selected_physicians)) &
            (self.df['ActivityName'].isin(selected_activity_types))
        ].copy()

        # Apply time range filter if provided
        if time_range is not None:
            start_hour, end_hour = time_range
            filtered_df = filtered_df[
                (filtered_df['Hour'] >= start_hour) &
                (filtered_df['Hour'] <= end_hour)
            ].copy()

        return filtered_df

    def get_paginated_appointments(self, filtered_df, page=1, page_size=10):
        """
        Get paginated list of appointments sorted chronologically.

        Args:
            filtered_df: Filtered DataFrame
            page: Page number (1-indexed)
            page_size: Number of appointments per page

        Returns:
            Tuple of (paginated DataFrame, total pages)
        """
        if filtered_df.empty:
            return filtered_df, 0

        # Sort by appointment date/time
        sorted_df = filtered_df.sort_values('AppointmentDateTime')

        # Calculate pagination
        total_records = len(sorted_df)
        total_pages = (total_records + page_size - 1) // page_size

        # Get the page slice
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        paginated_df = sorted_df.iloc[start_idx:end_idx]

        return paginated_df, total_pages

    def get_weekly_calendar_data(self, filtered_df, week_offset=0):
        """
        Get appointments for a specific week in calendar format.

        Args:
            filtered_df: Filtered DataFrame
            week_offset: Number of weeks from current week (0 = current week, 1 = next week, etc.)

        Returns:
            Tuple of (weekly DataFrame, week start date, week end date)
        """
        if filtered_df.empty:
            # Return current week dates even if no data
            today = datetime.now()
            week_start = today - timedelta(days=today.weekday())
            week_start = week_start + timedelta(weeks=week_offset)
            week_end = week_start + timedelta(days=4)  # M-F only
            return filtered_df, week_start, week_end

        # Calculate target week
        today = datetime.now()
        week_start = today - timedelta(days=today.weekday())
        week_start = week_start + timedelta(weeks=week_offset)
        week_end = week_start + timedelta(days=4)  # M-F only

        # Filter data for the target week (Monday to Friday only)
        weekly_df = filtered_df[
            (filtered_df['AppointmentDateTime'] >= week_start) &
            (filtered_df['AppointmentDateTime'] < week_end + timedelta(days=1)) &
            (filtered_df['AppointmentDateTime'].dt.dayofweek < 5)  # Monday=0, Friday=4
        ].copy()

        # Sort by date and time
        weekly_df = weekly_df.sort_values('AppointmentDateTime')

        return weekly_df, week_start, week_end

    def calculate_metrics(self, filtered_df):
        """
        Calculate summary metrics.

        Args:
            filtered_df: Filtered DataFrame

        Returns:
            Dict with metric values
        """
        if filtered_df.empty:
            return {
                'total_appointments': 0,
                'unique_physicians': 0,
                'unique_departments': 0,
                'avg_duration': 0
            }

        return {
            'total_appointments': len(filtered_df),
            'unique_physicians': filtered_df['ResourceName'].nunique(),
            'unique_departments': filtered_df['DepartmentName'].nunique(),
            'avg_duration': filtered_df['ActivityPlannedLength'].mean()
        }

    def get_sidebar_layout(self, state=None):
        """Implemented in scheduling_sidebar.py"""
        from tasks.scheduling.scheduling_sidebar import create_sidebar_layout
        return create_sidebar_layout(self, state=state)

    def get_main_panel_layout(self):
        """Implemented in scheduling_panel.py"""
        from tasks.scheduling.scheduling_panel import create_main_panel_layout
        return create_main_panel_layout()

    def register_callbacks(self, app):
        """Implemented in scheduling_panel.py"""
        from tasks.scheduling.scheduling_panel import register_callbacks
        register_callbacks(app, self)
