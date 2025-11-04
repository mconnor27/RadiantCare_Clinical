"""
Simulations task implementation
"""
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from statsmodels.nonparametric.smoothers_lowess import lowess
from tasks.base_task import BaseTask


class SimulationsTask(BaseTask):
    """Task for analyzing simulation appointments"""

    def __init__(self, df):
        """
        Initialize Simulations task.

        Args:
            df: Pandas DataFrame with simulation data (already preprocessed)
        """
        super().__init__(df)

        # Process locations - expand comma-separated ResourceName values
        self.df = self._process_locations(df)

        # Get unique values for filters
        self.locations = sorted(self.df['Location'].dropna().unique())
        self.simulation_types = sorted(self.df['SimulationType'].dropna().unique())

        # Get year range for slider
        if not self.df.empty:
            self.min_year = int(self.df['AppointmentTime'].dt.year.min())
            self.max_year = int(self.df['AppointmentTime'].dt.year.max())
        else:
            # Default values if no data
            import datetime
            current_year = datetime.datetime.now().year
            self.min_year = current_year - 10
            self.max_year = current_year

    def _process_locations(self, df):
        """
        Process ResourceName column to extract and map locations.
        Expands comma-separated values and maps to friendly names.

        Args:
            df: Original DataFrame

        Returns:
            DataFrame with processed Location and SimulationType columns
        """
        # Create a copy to avoid modifying original
        df = df.copy()

        # Rename ActivityName to SimulationType
        df['SimulationType'] = df['ActivityName']

        # Process ResourceName to Location
        # Map CT_RC_LACEY to "Lacey" and CT_CENTRALIA to "Centralia"
        def map_location(resource_name):
            if pd.isna(resource_name):
                return None
            if 'CT_RC_LACEY' in resource_name:
                return 'Lacey'
            elif 'CT_CENTRALIA' in resource_name:
                return 'Centralia'
            return None

        df['Location'] = df['ResourceName'].apply(map_location)

        # Drop rows with no valid location
        df = df[df['Location'].notna()]

        return df

    def filter_data(self, selected_locations, selected_sim_types, year_range):
        """
        Filter dataframe based on user selections.

        Args:
            selected_locations: List of selected locations
            selected_sim_types: List of selected simulation types
            year_range: Tuple of (min_year, max_year)

        Returns:
            Filtered DataFrame
        """
        if selected_locations is None:
            selected_locations = self.locations
        if selected_sim_types is None:
            selected_sim_types = self.simulation_types

        filtered_df = self.df[
            (self.df['Location'].isin(selected_locations)) &
            (self.df['SimulationType'].isin(selected_sim_types)) &
            (self.df['AppointmentTime'].dt.year >= year_range[0]) &
            (self.df['AppointmentTime'].dt.year <= year_range[1])
        ].copy()

        return filtered_df

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
                'total_simulations': 0,
                'date_range': 0,
                'avg_per_location': 0,
                'avg_per_day': 0
            }

        total_simulations = len(filtered_df)
        date_range = (filtered_df['AppointmentTime'].max() - filtered_df['AppointmentTime'].min()).days

        # Count unique locations in filtered data
        unique_locations = filtered_df['Location'].nunique()
        avg_per_location = total_simulations / unique_locations if unique_locations > 0 else 0
        avg_per_day = total_simulations / date_range if date_range > 0 else 0

        return {
            'total_simulations': total_simulations,
            'date_range': date_range,
            'avg_per_location': avg_per_location,
            'avg_per_day': avg_per_day
        }

    def create_chart(self, filtered_df, aggregation, chart_type, comparison_mode, smoothing=1, year_range=None, stats_options=None, calendar_aligned=False, period_type='year'):
        """
        Create the visualization chart.

        Args:
            filtered_df: Filtered DataFrame
            aggregation: Time aggregation ('Daily', 'Weekly', 'Monthly', 'Quarterly', 'Yearly')
            chart_type: 'line' or 'bar'
            comparison_mode: 'none' or 'location'
            smoothing: Moving average window size (1 = no smoothing)
            year_range: Tuple of (min_year, max_year)
            stats_options: Dict with keys show_mean, show_std_dev, show_median, show_ci
            calendar_aligned: If True and comparison_mode is 'location', normalize timelines
            period_type: For comparison mode: 'year', 'month', or 'quarter'

        Returns:
            Plotly Figure object
        """
        if stats_options is None:
            stats_options = {'show_mean': False, 'show_std_dev': False, 'show_median': False, 'show_ci': False}

        if filtered_df.empty:
            empty_fig = go.Figure()
            empty_fig.update_layout(title="No data available for selected filters")
            return empty_fig

        fig = go.Figure()

        if aggregation == 'Daily' or aggregation == 'Daily-NonCumulative':
            is_cumulative = (aggregation == 'Daily')

            daily_counts = filtered_df.groupby([
                filtered_df['AppointmentTime'].dt.date,
                'Location'
            ]).size().reset_index(name='count')
            daily_counts.columns = ['date', 'location', 'count']
            daily_counts['date'] = pd.to_datetime(daily_counts['date'])
            daily_counts = daily_counts.sort_values('date')

            if is_cumulative:
                daily_counts['cumulative'] = daily_counts.groupby('location')['count'].cumsum()
                y_column = 'cumulative'
            else:
                y_column = 'count'

            if comparison_mode == 'location':
                selected_locations = filtered_df['Location'].unique()
                for location in selected_locations:
                    location_data = daily_counts[daily_counts['location'] == location]

                    if chart_type == 'line':
                        y_values = location_data[y_column].values
                        # Apply LOWESS smoothing if enabled
                        if smoothing > 0 and len(y_values) > 2:
                            frac = 0.01 + (smoothing / 10) * 0.49
                            x_numeric = np.arange(len(y_values))
                            smoothed = lowess(y_values, x_numeric, frac=frac, return_sorted=False)
                            y_values = smoothed
                        fig.add_trace(go.Scatter(
                            x=location_data['date'],
                            y=y_values,
                            mode='lines',
                            name=location,
                            line=dict(width=2)
                        ))
                    else:
                        fig.add_trace(go.Bar(
                            x=location_data['date'],
                            y=location_data[y_column],
                            name=location
                        ))
            else:
                if is_cumulative:
                    total_daily = daily_counts.groupby('date')['count'].sum().cumsum().reset_index()
                    total_daily.columns = ['date', y_column]
                else:
                    total_daily = daily_counts.groupby('date')['count'].sum().reset_index()
                    total_daily.columns = ['date', y_column]

                if chart_type == 'line':
                    y_values = total_daily[y_column].values
                    # Apply LOWESS smoothing if enabled
                    if smoothing > 0 and len(y_values) > 2:
                        frac = 0.01 + (smoothing / 10) * 0.49
                        x_numeric = np.arange(len(y_values))
                        smoothed = lowess(y_values, x_numeric, frac=frac, return_sorted=False)
                        y_values = smoothed
                    fig.add_trace(go.Scatter(
                        x=total_daily['date'],
                        y=y_values,
                        mode='lines',
                        name='Total Simulations',
                        line=dict(width=3, color='#3498DB')
                    ))
                else:
                    fig.add_trace(go.Bar(
                        x=total_daily['date'],
                        y=total_daily[y_column],
                        name='Total Simulations',
                        marker_color='#3498DB'
                    ))

            if is_cumulative:
                fig.update_layout(
                    title="Cumulative Simulations Over Time",
                    xaxis_title="Date",
                    yaxis_title="Cumulative Simulation Count"
                )
            else:
                fig.update_layout(
                    title="Daily Simulations",
                    xaxis_title="Date",
                    yaxis_title="Simulation Count"
                )

        else:
            freq_map = {"Weekly": "W", "Monthly": "M", "Quarterly": "Q", "Yearly": "Y"}
            freq = freq_map[aggregation]

            filtered_df['period'] = filtered_df['AppointmentTime'].dt.to_period(freq)
            period_counts = filtered_df.groupby(['period', 'Location']).size().reset_index(name='count')
            period_counts['period_start'] = period_counts['period'].dt.to_timestamp()

            if comparison_mode == 'location':
                selected_locations = filtered_df['Location'].unique()
                for location in selected_locations:
                    location_data = period_counts[period_counts['Location'] == location]

                    if chart_type == 'line':
                        y_values = location_data['count'].values
                        # Apply LOWESS smoothing if enabled
                        if smoothing > 0 and len(y_values) > 2:
                            frac = 0.01 + (smoothing / 10) * 0.49
                            x_numeric = np.arange(len(y_values))
                            smoothed = lowess(y_values, x_numeric, frac=frac, return_sorted=False)
                            y_values = smoothed
                        fig.add_trace(go.Scatter(
                            x=location_data['period_start'],
                            y=y_values,
                            mode='lines',
                            name=location,
                            line=dict(width=2)
                        ))
                    else:
                        fig.add_trace(go.Bar(
                            x=location_data['period_start'],
                            y=location_data['count'],
                            name=location
                        ))
            else:
                total_period = period_counts.groupby('period_start')['count'].sum().reset_index()
                total_period.columns = ['period_start', 'count']

                if chart_type == 'line':
                    y_values = total_period['count'].values
                    # Apply LOWESS smoothing if enabled
                    if smoothing > 0 and len(y_values) > 2:
                        frac = 0.01 + (smoothing / 10) * 0.49
                        x_numeric = np.arange(len(y_values))
                        smoothed = lowess(y_values, x_numeric, frac=frac, return_sorted=False)
                        y_values = smoothed
                    fig.add_trace(go.Scatter(
                        x=total_period['period_start'],
                        y=y_values,
                        mode='lines',
                        name='Total Simulations',
                        line=dict(width=3, color='#3498DB')
                    ))
                else:
                    fig.add_trace(go.Bar(
                        x=total_period['period_start'],
                        y=total_period['count'],
                        name='Total Simulations',
                        marker_color='#3498DB'
                    ))

            fig.update_layout(
                title=f"Simulations by {aggregation} Period",
                xaxis_title="Time Period",
                yaxis_title="Simulation Count"
            )

        fig.update_layout(
            hovermode='x unified',
            plot_bgcolor='white',
            paper_bgcolor='white',
            font=dict(color='#2C3E50', size=12),
            xaxis=dict(
                showgrid=True,
                gridcolor='#ECF0F1',
                zeroline=True,
                zerolinewidth=1,
                zerolinecolor='#6c757d'
            ),
            yaxis=dict(
                showgrid=True,
                gridcolor='#ECF0F1',
                showline=True,
                linewidth=1,
                linecolor='#6c757d',
                zeroline=True,
                zerolinewidth=1,
                zerolinecolor='#6c757d',
                rangemode='tozero'
            ),
            height=500
        )

        return fig

    def get_sidebar_layout(self, state=None):
        """Implemented in simulations_sidebar.py"""
        from tasks.simulations.simulations_sidebar import create_sidebar_layout
        return create_sidebar_layout(self, state=state)

    def get_main_panel_layout(self):
        """Implemented in simulations_panel.py"""
        from tasks.simulations.simulations_panel import create_main_panel_layout
        return create_main_panel_layout()

    def register_callbacks(self, app):
        """Implemented in simulations_panel.py"""
        from tasks.simulations.simulations_panel import register_callbacks
        register_callbacks(app, self)
