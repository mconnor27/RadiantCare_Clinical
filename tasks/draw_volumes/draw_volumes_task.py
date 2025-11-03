"""
Draw Volumes task implementation
"""
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from statsmodels.nonparametric.smoothers_lowess import lowess
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

    def get_max_smoothing(self, filtered_df, aggregation, year_range):
        """
        Calculate the maximum smoothing value based on data range.
        Limited to one-third of the time periods in the filtered data.

        Args:
            filtered_df: Filtered DataFrame
            aggregation: Time aggregation type
            year_range: Tuple of (min_year, max_year)

        Returns:
            Maximum smoothing value (integer)
        """
        if filtered_df.empty:
            return 30

        # Calculate number of periods
        if aggregation == 'Daily' or aggregation == 'Daily-NonCumulative':
            num_periods = (filtered_df['AppointmentTime'].max() - filtered_df['AppointmentTime'].min()).days
        elif aggregation == 'Weekly':
            num_periods = len(filtered_df['AppointmentTime'].dt.to_period('W').unique())
        elif aggregation == 'Monthly':
            num_periods = len(filtered_df['AppointmentTime'].dt.to_period('M').unique())
        elif aggregation == 'Quarterly':
            num_periods = len(filtered_df['AppointmentTime'].dt.to_period('Q').unique())
        elif aggregation == 'Yearly':
            num_periods = len(filtered_df['AppointmentTime'].dt.to_period('Y').unique())

        # Max smoothing is 1/3 of periods, rounded, minimum of 1
        max_smooth = max(1, round(num_periods / 3))
        return max_smooth

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

    def _create_previous_periods_chart(self, filtered_df, chart_type, smoothing, year_range, stats_options):
        """
        Create chart comparing YTD cumulative data across multiple years, normalized to start from same point.

        Args:
            filtered_df: Filtered DataFrame
            chart_type: 'line' or 'bar'
            smoothing: Smoothing value for LOWESS
            year_range: Tuple of (min_year, max_year)
            stats_options: Dict with keys show_mean, show_std_dev, show_median, show_ci

        Returns:
            Plotly Figure object
        """
        fig = go.Figure()

        # Get current year (max year in range)
        current_year = year_range[1]

        # Get all years in the range
        years = range(year_range[0], year_range[1] + 1)
        historical_years = [y for y in years if y < current_year]

        # Define colors - current year highlighted, others gray
        colors = ['#d3d3d3'] * (len(years) - 1) + ['#8B5CF6']  # Purple for current year

        # Store data for all years for statistics calculation
        all_year_data = {}

        # Check if we should hide historical traces (when mean or median is shown)
        hide_historical = stats_options.get('show_mean') or stats_options.get('show_median')

        for idx, year in enumerate(years):
            # Filter data for this year
            year_data = filtered_df[filtered_df['AppointmentTime'].dt.year == year].copy()

            if year_data.empty:
                continue

            # Get day of year
            year_data['day_of_year'] = year_data['AppointmentTime'].dt.dayofyear

            # Normalize leap years: combine Feb 29 (day 60) into Feb 28 (day 59)
            # and shift all subsequent days back by 1
            import datetime
            is_leap = datetime.date(year, 1, 1).year % 4 == 0 and (datetime.date(year, 1, 1).year % 100 != 0 or datetime.date(year, 1, 1).year % 400 == 0)

            if is_leap:
                # Shift days after Feb 29 (day 60) back by 1
                year_data.loc[year_data['day_of_year'] > 60, 'day_of_year'] -= 1

            # Count tasks per day
            daily_counts = year_data.groupby('day_of_year').size().reset_index(name='count')
            daily_counts = daily_counts.sort_values('day_of_year')

            # Calculate cumulative
            daily_counts['cumulative'] = daily_counts['count'].cumsum()

            # Create x-axis as day numbers (normalized starting point)
            x_values = daily_counts['day_of_year'].values
            y_values = daily_counts['cumulative'].values

            # Store for statistics
            all_year_data[year] = {'x': x_values, 'y': y_values}

            # Determine line properties
            is_current_year = (year == current_year)
            line_width = 3 if is_current_year else 1
            line_color = colors[idx]

            # Skip historical years if mean/median is being shown
            if hide_historical and not is_current_year:
                continue

            if chart_type == 'line':
                # Apply LOWESS smoothing if enabled
                if smoothing > 0 and len(y_values) > 2:
                    frac = 0.01 + (smoothing / 10) * 0.49
                    x_numeric = np.arange(len(y_values))
                    smoothed = lowess(y_values, x_numeric, frac=frac, return_sorted=False)
                    y_values = smoothed

                fig.add_trace(go.Scatter(
                    x=x_values,
                    y=y_values,
                    mode='lines',
                    name=str(year),
                    line=dict(width=line_width, color=line_color)
                ))

                # Add value annotation for the last point of current year
                if is_current_year and len(x_values) > 0:
                    last_x = x_values[-1]
                    last_y = y_values[-1]
                    fig.add_annotation(
                        x=last_x,
                        y=last_y,
                        text=f"<b>{int(last_y):,}</b>",
                        showarrow=False,
                        xanchor='right',
                        yanchor='bottom',
                        xshift=-10,
                        yshift=5,
                        font=dict(size=12, color=line_color)
                    )
            else:
                # Bar chart mode
                fig.add_trace(go.Bar(
                    x=x_values,
                    y=y_values,
                    name=str(year),
                    marker_color=line_color
                ))

        # Calculate and plot historical statistics (only for historical years, excluding current year)
        if historical_years and any([stats_options.get('show_mean'), stats_options.get('show_median'),
                                      stats_options.get('show_std_dev'), stats_options.get('show_ci')]):
            # Get data for historical years only
            historical_data = {year: data for year, data in all_year_data.items() if year in historical_years}

            if historical_data:
                # Find the maximum day across all historical years
                max_day = max(max(data['x']) for data in historical_data.values())

                # Create a continuous range of days from 1 to max_day
                all_days = np.arange(1, max_day + 1)

                # Create a matrix where rows are years and columns are days
                # We'll interpolate each year's data to fill all days
                data_matrix = np.full((len(historical_data), len(all_days)), np.nan)

                for i, year in enumerate(sorted(historical_data.keys())):
                    year_data = historical_data[year]
                    x_days = year_data['x']
                    y_values = year_data['y']

                    # Interpolate to fill all days from 1 to the last day of this year
                    last_day = x_days[-1]
                    # Create full range for this year
                    full_days = np.arange(1, last_day + 1)
                    # Interpolate cumulative values
                    interpolated_values = np.interp(full_days, x_days, y_values)

                    # Fill the matrix for this year
                    for j, day in enumerate(full_days):
                        if day <= len(all_days):
                            data_matrix[i, day - 1] = interpolated_values[j]

                # Calculate statistics across years for each day
                # Use nanmean/nanmedian/nanstd to handle missing values
                mean_values = np.nanmean(data_matrix, axis=0)
                median_values = np.nanmedian(data_matrix, axis=0)
                std_values = np.nanstd(data_matrix, axis=0, ddof=1)

                # Calculate 95% prediction interval (where ~95% of individual years fall)
                # Use ±1.96 * std for 95% prediction interval
                ci_95 = 1.96 * std_values

                # Add mean line
                if stats_options.get('show_mean'):
                    fig.add_trace(go.Scatter(
                        x=all_days,
                        y=mean_values,
                        mode='lines',
                        name='Mean (Historical)',
                        line=dict(width=2, color='#FF6B6B', dash='dash'),
                        showlegend=True
                    ))

                # Add median line
                if stats_options.get('show_median'):
                    fig.add_trace(go.Scatter(
                        x=all_days,
                        y=median_values,
                        mode='lines',
                        name='Median (Historical)',
                        line=dict(width=2, color='#4ECDC4', dash='dash'),
                        showlegend=True
                    ))

                # Add std dev band
                if stats_options.get('show_std_dev'):
                    upper_std = mean_values + std_values
                    lower_std = mean_values - std_values

                    fig.add_trace(go.Scatter(
                        x=all_days,
                        y=upper_std,
                        mode='lines',
                        line=dict(width=0),
                        showlegend=False,
                        hoverinfo='skip'
                    ))
                    fig.add_trace(go.Scatter(
                        x=all_days,
                        y=lower_std,
                        mode='lines',
                        line=dict(width=0),
                        fillcolor='rgba(255, 107, 107, 0.2)',
                        fill='tonexty',
                        name='±1 Std Dev',
                        showlegend=True,
                        hoverinfo='skip'
                    ))

                # Add 95% CI band
                if stats_options.get('show_ci'):
                    upper_ci = mean_values + ci_95
                    lower_ci = mean_values - ci_95

                    fig.add_trace(go.Scatter(
                        x=all_days,
                        y=upper_ci,
                        mode='lines',
                        line=dict(width=0),
                        showlegend=False,
                        hoverinfo='skip'
                    ))
                    fig.add_trace(go.Scatter(
                        x=all_days,
                        y=lower_ci,
                        mode='lines',
                        line=dict(width=0),
                        fillcolor='rgba(78, 205, 196, 0.2)',
                        fill='tonexty',
                        name='95% CI',
                        showlegend=True,
                        hoverinfo='skip'
                    ))

        # Add projection line for current year (dotted line extending to end of year)
        # Only show projection if year is incomplete
        if current_year in years:
            year_data = filtered_df[filtered_df['AppointmentTime'].dt.year == current_year].copy()
            if not year_data.empty:
                year_data['day_of_year'] = year_data['AppointmentTime'].dt.dayofyear
                daily_counts = year_data.groupby('day_of_year').size().reset_index(name='count')
                daily_counts = daily_counts.sort_values('day_of_year')
                daily_counts['cumulative'] = daily_counts['count'].cumsum()

                last_day = daily_counts['day_of_year'].iloc[-1]
                last_value = daily_counts['cumulative'].iloc[-1]

                # All years normalized to 365 days
                days_in_year = 365

                # Only show projection if year is incomplete (not at end of year)
                if last_day < days_in_year - 1:  # Allow 1 day buffer
                    # Project to end of year
                    projection_x = [last_day, days_in_year]
                    # Simple linear projection based on current rate
                    days_elapsed = last_day
                    projected_final = last_value * (days_in_year / days_elapsed) if days_elapsed > 0 else last_value
                    projection_y = [last_value, projected_final]

                    fig.add_trace(go.Scatter(
                        x=projection_x,
                        y=projection_y,
                        mode='lines',
                        name=f'{current_year} (Projected)',
                        line=dict(width=3, color='#8B5CF6', dash='dot'),
                        showlegend=True
                    ))

                    # Add projection annotation
                    fig.add_annotation(
                        x=days_in_year,
                        y=projected_final,
                        text=f"<b>{int(projected_final):,}</b>",
                        showarrow=False,
                        xanchor='right',
                        yanchor='bottom',
                        xshift=-10,
                        yshift=5,
                        font=dict(size=12, color='#8B5CF6')
                    )

        fig.update_layout(
            title="Year-to-Date Cumulative Comparison (Normalized by Day of Year)",
            xaxis_title="Day of Year",
            yaxis_title="Cumulative Task Count",
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

    def create_chart(self, filtered_df, aggregation, chart_type, comparison_mode, selected_phys, smoothing=1, year_range=None, stats_options=None, calendar_aligned=False):
        """
        Create the visualization chart.

        Args:
            filtered_df: Filtered DataFrame
            aggregation: Time aggregation ('Daily', 'Weekly', 'Monthly', 'Quarterly', 'Yearly')
            chart_type: 'line' or 'bar'
            comparison_mode: 'none', 'physician', or 'previous_periods'
            selected_phys: List of selected physicians
            smoothing: Moving average window size (1 = no smoothing)
            year_range: Tuple of (min_year, max_year) for previous_periods mode
            stats_options: Dict with keys show_mean, show_std_dev, show_median, show_ci
            calendar_aligned: If True and comparison_mode is 'physician', normalize physicians' timelines to elapsed time

        Returns:
            Plotly Figure object
        """
        if stats_options is None:
            stats_options = {'show_mean': False, 'show_std_dev': False, 'show_median': False, 'show_ci': False}
        if filtered_df.empty:
            empty_fig = go.Figure()
            empty_fig.update_layout(title="No data available for selected filters")
            return empty_fig

        # Handle previous_periods comparison mode for Daily (None Cumulative) aggregation
        if comparison_mode == 'previous_periods' and aggregation == 'Daily' and year_range:
            return self._create_previous_periods_chart(filtered_df, chart_type, smoothing, year_range, stats_options)

        fig = go.Figure()

        if aggregation == 'Daily' or aggregation == 'Daily-NonCumulative':
            is_cumulative = (aggregation == 'Daily')

            daily_counts = filtered_df.groupby([
                filtered_df['AppointmentTime'].dt.date,
                'FirstMD'
            ]).size().reset_index(name='count')
            daily_counts.columns = ['date', 'physician', 'count']
            daily_counts['date'] = pd.to_datetime(daily_counts['date'])
            daily_counts = daily_counts.sort_values('date')

            if is_cumulative:
                daily_counts['cumulative'] = daily_counts.groupby('physician')['count'].cumsum()
                y_column = 'cumulative'
            else:
                y_column = 'count'

            if comparison_mode == 'physician':
                if calendar_aligned:
                    # Calendar-aligned mode: normalize each physician's timeline to elapsed time
                    for physician in selected_phys:
                        physician_data = daily_counts[daily_counts['physician'] == physician].copy()
                        if physician_data.empty:
                            continue

                        # Calculate elapsed time from first appointment
                        first_date = physician_data['date'].min()
                        physician_data['elapsed_days'] = (physician_data['date'] - first_date).dt.days

                        if chart_type == 'line':
                            x_values = physician_data['elapsed_days'].values
                            y_values = physician_data[y_column].values
                            # Apply LOWESS smoothing if enabled (only for line charts)
                            if smoothing > 0 and len(y_values) > 2:
                                frac = 0.01 + (smoothing / 10) * 0.49
                                x_numeric = np.arange(len(y_values))
                                smoothed = lowess(y_values, x_numeric, frac=frac, return_sorted=False)
                                y_values = smoothed
                            fig.add_trace(go.Scatter(
                                x=x_values,
                                y=y_values,
                                mode='lines',
                                name=physician,
                                line=dict(width=2)
                            ))
                        else:
                            fig.add_trace(go.Bar(
                                x=physician_data['elapsed_days'],
                                y=physician_data[y_column],
                                name=physician
                            ))
                else:
                    # Regular mode: use actual dates
                    for physician in selected_phys:
                        physician_data = daily_counts[daily_counts['physician'] == physician]
                        if chart_type == 'line':
                            y_values = physician_data[y_column].values
                            # Apply LOWESS smoothing if enabled (only for line charts)
                            if smoothing > 0 and len(y_values) > 2:
                                # Convert 0-10 slider to fraction (0.01 to 0.5)
                                # 0 = no smoothing, 10 = maximum smoothing
                                frac = 0.01 + (smoothing / 10) * 0.49
                                x_numeric = np.arange(len(y_values))
                                smoothed = lowess(y_values, x_numeric, frac=frac, return_sorted=False)
                                y_values = smoothed
                            fig.add_trace(go.Scatter(
                                x=physician_data['date'],
                                y=y_values,
                                mode='lines',
                                name=physician,
                                line=dict(width=2)
                            ))
                        else:
                            fig.add_trace(go.Bar(
                                x=physician_data['date'],
                                y=physician_data[y_column],
                                name=physician
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
                    # Apply LOWESS smoothing if enabled (only for line charts)
                    if smoothing > 0 and len(y_values) > 2:
                        # Convert 0-10 slider to fraction (0.01 to 0.5)
                        frac = 0.01 + (smoothing / 10) * 0.49
                        x_numeric = np.arange(len(y_values))
                        smoothed = lowess(y_values, x_numeric, frac=frac, return_sorted=False)
                        y_values = smoothed
                    fig.add_trace(go.Scatter(
                        x=total_daily['date'],
                        y=y_values,
                        mode='lines',
                        name='Total Tasks',
                        line=dict(width=3, color='#3498DB')
                    ))
                else:
                    fig.add_trace(go.Bar(
                        x=total_daily['date'],
                        y=total_daily[y_column],
                        name='Total Tasks',
                        marker_color='#3498DB'
                    ))

            if is_cumulative:
                x_title = "Elapsed Days" if (comparison_mode == 'physician' and calendar_aligned) else "Date"
                fig.update_layout(
                    title="Cumulative Tasks Completed Over Time",
                    xaxis_title=x_title,
                    yaxis_title="Cumulative Task Count"
                )
            else:
                x_title = "Elapsed Days" if (comparison_mode == 'physician' and calendar_aligned) else "Date"
                fig.update_layout(
                    title="Daily Tasks Completed",
                    xaxis_title=x_title,
                    yaxis_title="Task Count"
                )

        else:
            freq_map = {"Weekly": "W", "Monthly": "M", "Quarterly": "Q", "Yearly": "Y"}
            freq = freq_map[aggregation]

            filtered_df['period'] = filtered_df['AppointmentTime'].dt.to_period(freq)
            period_counts = filtered_df.groupby(['period', 'FirstMD']).size().reset_index(name='count')
            period_counts['period_start'] = period_counts['period'].dt.to_timestamp()

            if comparison_mode == 'physician':
                if calendar_aligned:
                    # Calendar-aligned mode for periods
                    for physician in selected_phys:
                        physician_data = period_counts[period_counts['FirstMD'] == physician].copy()
                        if physician_data.empty:
                            continue

                        # Sort by period start
                        physician_data = physician_data.sort_values('period_start')

                        # Calculate elapsed periods (0-indexed)
                        physician_data['elapsed_periods'] = range(len(physician_data))

                        if chart_type == 'line':
                            x_values = physician_data['elapsed_periods'].values
                            y_values = physician_data['count'].values
                            # Apply LOWESS smoothing if enabled (only for line charts)
                            if smoothing > 0 and len(y_values) > 2:
                                frac = 0.01 + (smoothing / 10) * 0.49
                                x_numeric = np.arange(len(y_values))
                                smoothed = lowess(y_values, x_numeric, frac=frac, return_sorted=False)
                                y_values = smoothed
                            fig.add_trace(go.Scatter(
                                x=x_values,
                                y=y_values,
                                mode='lines',
                                name=physician,
                                line=dict(width=2)
                            ))
                        else:
                            fig.add_trace(go.Bar(
                                x=physician_data['elapsed_periods'],
                                y=physician_data['count'],
                                name=physician
                            ))
                else:
                    # Regular mode: use actual period timestamps
                    for physician in selected_phys:
                        physician_data = period_counts[period_counts['FirstMD'] == physician]
                        if chart_type == 'line':
                            y_values = physician_data['count'].values
                            # Apply LOWESS smoothing if enabled (only for line charts)
                            if smoothing > 0 and len(y_values) > 2:
                                # Convert 0-10 slider to fraction (0.01 to 0.5)
                                frac = 0.01 + (smoothing / 10) * 0.49
                                x_numeric = np.arange(len(y_values))
                                smoothed = lowess(y_values, x_numeric, frac=frac, return_sorted=False)
                                y_values = smoothed
                            fig.add_trace(go.Scatter(
                                x=physician_data['period_start'],
                                y=y_values,
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
                    y_values = total_period['count'].values
                    # Apply LOWESS smoothing if enabled (only for line charts)
                    if smoothing > 0 and len(y_values) > 2:
                        # Convert 0-10 slider to fraction (0.01 to 0.5)
                        frac = 0.01 + (smoothing / 10) * 0.49
                        x_numeric = np.arange(len(y_values))
                        smoothed = lowess(y_values, x_numeric, frac=frac, return_sorted=False)
                        y_values = smoothed
                    fig.add_trace(go.Scatter(
                        x=total_period['period_start'],
                        y=y_values,
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

            # Determine x-axis title based on calendar-aligned mode
            if comparison_mode == 'physician' and calendar_aligned:
                x_title = f"Elapsed {aggregation} Periods"
            else:
                x_title = "Time Period"

            fig.update_layout(
                title=f"Tasks Completed by {aggregation} Period",
                xaxis_title=x_title,
                yaxis_title="Task Count"
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
