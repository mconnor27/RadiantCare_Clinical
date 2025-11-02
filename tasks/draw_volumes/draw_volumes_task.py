"""
Draw Volumes task implementation
"""
import pandas as pd
import plotly.graph_objects as go
from tasks.base_task import BaseTask


class DrawVolumesTask(BaseTask):
    """Task for analyzing draw volumes (treatment planning) completion"""

    def __init__(self, df):
        """
        Initialize Draw Volumes task.

        Args:
            df: Pandas DataFrame with task data (already preprocessed)
        """
        super().__init__(df)

        # Get unique values for filters
        self.physicians = sorted(df['FirstMD'].dropna().unique())
        self.activity_names = sorted(df['ActivityName'].dropna().unique())

        # Get year range for slider
        self.min_year = int(df['AppointmentTime'].dt.year.min())
        self.max_year = int(df['AppointmentTime'].dt.year.max())

    def get_physicians_for_year_range(self, year_range):
        """
        Get list of physicians who have data in the specified year range.

        Args:
            year_range: Tuple of (min_year, max_year)

        Returns:
            Sorted list of physician names
        """
        filtered_df = self.df[
            (self.df['AppointmentTime'].dt.year >= year_range[0]) &
            (self.df['AppointmentTime'].dt.year <= year_range[1])
        ]
        return sorted(filtered_df['FirstMD'].dropna().unique())

    def filter_data(self, selected_phys, selected_acts, year_range):
        """
        Filter dataframe based on user selections.

        Args:
            selected_phys: List of selected physician names
            selected_acts: List of selected activity names
            year_range: Tuple of (min_year, max_year)

        Returns:
            Filtered DataFrame
        """
        if selected_phys is None:
            selected_phys = self.physicians
        if selected_acts is None:
            selected_acts = self.activity_names

        filtered_df = self.df[
            (self.df['FirstMD'].isin(selected_phys)) &
            (self.df['ActivityName'].isin(selected_acts)) &
            (self.df['AppointmentTime'].dt.year >= year_range[0]) &
            (self.df['AppointmentTime'].dt.year <= year_range[1])
        ].copy()

        return filtered_df

    def calculate_metrics(self, filtered_df, selected_phys):
        """
        Calculate summary metrics.

        Args:
            filtered_df: Filtered DataFrame
            selected_phys: List of selected physicians

        Returns:
            Dict with metric values
        """
        if filtered_df.empty:
            return {
                'total_tasks': 0,
                'date_range': 0,
                'avg_per_physician': 0,
                'avg_per_day': 0
            }

        total_tasks = len(filtered_df)
        date_range = (filtered_df['AppointmentTime'].max() - filtered_df['AppointmentTime'].min()).days
        avg_per_physician = total_tasks / len(selected_phys) if selected_phys else 0
        avg_per_day = total_tasks / date_range if date_range > 0 else 0

        return {
            'total_tasks': total_tasks,
            'date_range': date_range,
            'avg_per_physician': avg_per_physician,
            'avg_per_day': avg_per_day
        }

    def create_chart(self, filtered_df, aggregation, chart_type, comparison_mode, selected_phys):
        """
        Create the visualization chart.

        Args:
            filtered_df: Filtered DataFrame
            aggregation: Time aggregation ('Daily', 'Weekly', 'Monthly', 'Quarterly', 'Yearly')
            chart_type: 'line' or 'bar'
            comparison_mode: 'none' or 'physician'
            selected_phys: List of selected physicians

        Returns:
            Plotly Figure object
        """
        if filtered_df.empty:
            empty_fig = go.Figure()
            empty_fig.update_layout(title="No data available for selected filters")
            return empty_fig

        fig = go.Figure()

        if aggregation == 'Daily':
            daily_counts = filtered_df.groupby([
                filtered_df['AppointmentTime'].dt.date,
                'FirstMD'
            ]).size().reset_index(name='count')
            daily_counts.columns = ['date', 'physician', 'count']
            daily_counts['date'] = pd.to_datetime(daily_counts['date'])
            daily_counts = daily_counts.sort_values('date')
            daily_counts['cumulative'] = daily_counts.groupby('physician')['count'].cumsum()

            if comparison_mode == 'physician':
                for physician in selected_phys:
                    physician_data = daily_counts[daily_counts['physician'] == physician]
                    if chart_type == 'line':
                        fig.add_trace(go.Scatter(
                            x=physician_data['date'],
                            y=physician_data['cumulative'],
                            mode='lines',
                            name=physician,
                            line=dict(width=2)
                        ))
                    else:
                        fig.add_trace(go.Bar(
                            x=physician_data['date'],
                            y=physician_data['cumulative'],
                            name=physician
                        ))
            else:
                total_daily = daily_counts.groupby('date')['count'].sum().cumsum().reset_index()
                total_daily.columns = ['date', 'cumulative']

                if chart_type == 'line':
                    fig.add_trace(go.Scatter(
                        x=total_daily['date'],
                        y=total_daily['cumulative'],
                        mode='lines',
                        name='Total Tasks',
                        line=dict(width=3, color='#3498DB')
                    ))
                else:
                    fig.add_trace(go.Bar(
                        x=total_daily['date'],
                        y=total_daily['cumulative'],
                        name='Total Tasks',
                        marker_color='#3498DB'
                    ))

            fig.update_layout(
                title="Cumulative Tasks Completed Over Time",
                xaxis_title="Date",
                yaxis_title="Cumulative Task Count"
            )

        else:
            freq_map = {"Weekly": "W", "Monthly": "M", "Quarterly": "Q", "Yearly": "Y"}
            freq = freq_map[aggregation]

            filtered_df['period'] = filtered_df['AppointmentTime'].dt.to_period(freq)
            period_counts = filtered_df.groupby(['period', 'FirstMD']).size().reset_index(name='count')
            period_counts['period_start'] = period_counts['period'].dt.to_timestamp()

            if comparison_mode == 'physician':
                for physician in selected_phys:
                    physician_data = period_counts[period_counts['FirstMD'] == physician]
                    if chart_type == 'line':
                        fig.add_trace(go.Scatter(
                            x=physician_data['period_start'],
                            y=physician_data['count'],
                            mode='lines',
                            name=physician,
                            line=dict(width=2)
                        ))
                    else:
                        fig.add_trace(go.Bar(
                            x=physician_data['period_start'],
                            y=physician_data['count'],
                            name=physician
                        ))
            else:
                total_period = period_counts.groupby('period_start')['count'].sum().reset_index()
                total_period.columns = ['period_start', 'count']

                if chart_type == 'line':
                    fig.add_trace(go.Scatter(
                        x=total_period['period_start'],
                        y=total_period['count'],
                        mode='lines',
                        name='Total Tasks',
                        line=dict(width=3, color='#3498DB')
                    ))
                else:
                    fig.add_trace(go.Bar(
                        x=total_period['period_start'],
                        y=total_period['count'],
                        name='Total Tasks',
                        marker_color='#3498DB'
                    ))

            fig.update_layout(
                title=f"Tasks Completed by {aggregation} Period",
                xaxis_title="Time Period",
                yaxis_title="Task Count"
            )

        fig.update_layout(
            hovermode='x unified',
            plot_bgcolor='white',
            paper_bgcolor='white',
            font=dict(color='#2C3E50', size=12),
            xaxis=dict(showgrid=True, gridcolor='#ECF0F1'),
            yaxis=dict(showgrid=True, gridcolor='#ECF0F1'),
            height=500
        )

        return fig

    def get_sidebar_layout(self):
        """Implemented in draw_volumes_sidebar.py"""
        from tasks.draw_volumes.draw_volumes_sidebar import create_sidebar_layout
        return create_sidebar_layout(self)

    def get_main_panel_layout(self):
        """Implemented in draw_volumes_panel.py"""
        from tasks.draw_volumes.draw_volumes_panel import create_main_panel_layout
        return create_main_panel_layout()

    def register_callbacks(self, app):
        """Implemented in draw_volumes_panel.py"""
        from tasks.draw_volumes.draw_volumes_panel import register_callbacks
        register_callbacks(app, self)
