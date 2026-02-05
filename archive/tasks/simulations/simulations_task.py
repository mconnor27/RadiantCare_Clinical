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
        Apply simulation type filters and consolidations.

        Data Processing Notes (displayed to user via help icon):
        - Location Mapping: CT_RC_LACEY → "Lacey", CT_CENTRALIA → "Centralia", 21iX_AB → "Aberdeen"
        - Filtered Out: Any simulation type containing "Bite Block"
        - Combined Types: "Treatment Device Fabrication" + "initial simulation on PET/CT table" → "PET/CT Sim"
        - Rows with unmapped locations are excluded from analysis

        Args:
            df: Original DataFrame

        Returns:
            DataFrame with processed Location and SimulationType columns
        """
        # Create a copy to avoid modifying original
        df = df.copy()

        # Rename ActivityName to SimulationType
        df['SimulationType'] = df['ActivityName']

        # FILTER: Exclude any simulation type containing "Bite Block"
        df = df[~df['SimulationType'].str.contains('Bite Block', case=False, na=False)]

        # CONSOLIDATE: Combine PET/CT related simulation types
        pet_ct_types = ['Treatment Device Fabrication', 'initial simulation on PET/CT table']
        df.loc[df['SimulationType'].isin(pet_ct_types), 'SimulationType'] = 'PET/CT Sim'

        # MAP: Process ResourceName to Location
        # CT_RC_LACEY → "Lacey", CT_CENTRALIA → "Centralia", 21iX_AB → "Aberdeen"
        def map_location(resource_name):
            if pd.isna(resource_name):
                return None
            resource_str = str(resource_name).upper()  # Convert to uppercase for case-insensitive matching
            if 'CT_RC_LACEY' in resource_str:
                return 'Lacey'
            elif 'CT_CENTRALIA' in resource_str:
                return 'Centralia'
            elif '21IX_AB' in resource_str:
                return 'Aberdeen'
            return None

        df['Location'] = df['ResourceName'].apply(map_location)

        # FILTER: Drop rows with no valid location
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

    def _create_previous_periods_chart(self, filtered_df, chart_type, smoothing, year_range, stats_options):
        """Create chart comparing YTD cumulative data across multiple years."""
        fig = go.Figure()
        current_year = year_range[1]
        years = range(year_range[0], year_range[1] + 1)
        historical_years = [y for y in years if y < current_year]
        colors = ['#d3d3d3'] * (len(years) - 1) + ['#8B5CF6']
        all_year_data = {}
        hide_historical = stats_options.get('show_mean') or stats_options.get('show_median')

        for idx, year in enumerate(years):
            year_data = filtered_df[filtered_df['AppointmentTime'].dt.year == year].copy()
            if year_data.empty:
                continue

            year_data['day_of_year'] = year_data['AppointmentTime'].dt.dayofyear
            import datetime
            is_leap = datetime.date(year, 1, 1).year % 4 == 0 and (datetime.date(year, 1, 1).year % 100 != 0 or datetime.date(year, 1, 1).year % 400 == 0)
            if is_leap:
                year_data.loc[year_data['day_of_year'] > 60, 'day_of_year'] -= 1

            daily_counts = year_data.groupby('day_of_year').size().reset_index(name='count')
            daily_counts = daily_counts.sort_values('day_of_year')
            daily_counts['cumulative'] = daily_counts['count'].cumsum()
            x_values = daily_counts['day_of_year'].values
            y_values = daily_counts['cumulative'].values
            all_year_data[year] = {'x': x_values, 'y': y_values}

            is_current_year = (year == current_year)
            line_width = 3 if is_current_year else 1
            line_color = colors[idx]

            if hide_historical and not is_current_year:
                continue

            if chart_type == 'line':
                if smoothing > 0 and len(y_values) > 2:
                    frac = 0.01 + (smoothing / 10) * 0.49
                    x_numeric = np.arange(len(y_values))
                    smoothed = lowess(y_values, x_numeric, frac=frac, return_sorted=False)
                    y_values = smoothed

                fig.add_trace(go.Scatter(
                    x=x_values, y=y_values, mode='lines', name=str(year),
                    line=dict(width=line_width, color=line_color)
                ))

                if is_current_year and len(x_values) > 0:
                    fig.add_annotation(
                        x=x_values[-1], y=y_values[-1],
                        text=f"<b>{int(y_values[-1]):,}</b>",
                        showarrow=False, xanchor='right', yanchor='bottom',
                        xshift=-10, yshift=5,
                        font=dict(size=12, color=line_color)
                    )
            else:
                fig.add_trace(go.Bar(x=x_values, y=y_values, name=str(year), marker_color=line_color))

        # Calculate historical statistics
        if historical_years and any([stats_options.get('show_mean'), stats_options.get('show_median'),
                                      stats_options.get('show_std_dev'), stats_options.get('show_ci')]):
            historical_data = {year: data for year, data in all_year_data.items() if year in historical_years}
            if historical_data:
                max_day = max(max(data['x']) for data in historical_data.values())
                all_days = np.arange(1, max_day + 1)
                data_matrix = np.full((len(historical_data), len(all_days)), np.nan)

                for i, year in enumerate(sorted(historical_data.keys())):
                    year_data = historical_data[year]
                    x_days, y_values = year_data['x'], year_data['y']
                    last_day = x_days[-1]
                    full_days = np.arange(1, last_day + 1)
                    interpolated_values = np.interp(full_days, x_days, y_values)
                    for j, day in enumerate(full_days):
                        if day <= len(all_days):
                            data_matrix[i, day - 1] = interpolated_values[j]

                mean_values = np.nanmean(data_matrix, axis=0)
                median_values = np.nanmedian(data_matrix, axis=0)
                std_values = np.nanstd(data_matrix, axis=0, ddof=1)
                ci_95 = 1.96 * std_values

                if stats_options.get('show_mean'):
                    fig.add_trace(go.Scatter(x=all_days, y=mean_values, mode='lines',
                        name='Mean (Historical)', line=dict(width=2, color='#FF6B6B', dash='dash')))

                if stats_options.get('show_median'):
                    fig.add_trace(go.Scatter(x=all_days, y=median_values, mode='lines',
                        name='Median (Historical)', line=dict(width=2, color='#4ECDC4', dash='dash')))

                if stats_options.get('show_std_dev'):
                    fig.add_trace(go.Scatter(x=all_days, y=mean_values + std_values, mode='lines',
                        line=dict(width=0), showlegend=False, hoverinfo='skip'))
                    fig.add_trace(go.Scatter(x=all_days, y=mean_values - std_values, mode='lines',
                        line=dict(width=0), fillcolor='rgba(255, 107, 107, 0.2)', fill='tonexty',
                        name='±1 Std Dev', hoverinfo='skip'))

                if stats_options.get('show_ci'):
                    fig.add_trace(go.Scatter(x=all_days, y=mean_values + ci_95, mode='lines',
                        line=dict(width=0), showlegend=False, hoverinfo='skip'))
                    fig.add_trace(go.Scatter(x=all_days, y=mean_values - ci_95, mode='lines',
                        line=dict(width=0), fillcolor='rgba(78, 205, 196, 0.2)', fill='tonexty',
                        name='95% CI', hoverinfo='skip'))

        # Projection for current year
        if current_year in years:
            year_data = filtered_df[filtered_df['AppointmentTime'].dt.year == current_year].copy()
            if not year_data.empty:
                year_data['day_of_year'] = year_data['AppointmentTime'].dt.dayofyear
                daily_counts = year_data.groupby('day_of_year').size().reset_index(name='count')
                daily_counts = daily_counts.sort_values('day_of_year')
                daily_counts['cumulative'] = daily_counts['count'].cumsum()
                last_day = daily_counts['day_of_year'].iloc[-1]
                last_value = daily_counts['cumulative'].iloc[-1]
                days_in_year = 365

                if last_day < days_in_year - 1:
                    projected_final = last_value * (days_in_year / last_day) if last_day > 0 else last_value
                    fig.add_trace(go.Scatter(x=[last_day, days_in_year], y=[last_value, projected_final],
                        mode='lines', name=f'{current_year} (Projected)',
                        line=dict(width=3, color='#8B5CF6', dash='dot')))
                    fig.add_annotation(x=days_in_year, y=projected_final,
                        text=f"<b>{int(projected_final):,}</b>", showarrow=False,
                        xanchor='right', yanchor='bottom', xshift=-10, yshift=5,
                        font=dict(size=12, color='#8B5CF6'))

        fig.update_layout(title="Year-to-Date Cumulative Comparison (Normalized by Day of Year)",
            xaxis_title="Day of Year", yaxis_title="Cumulative Simulation Count",
            hovermode='x unified', plot_bgcolor='white', paper_bgcolor='white',
            font=dict(color='#2C3E50', size=12),
            xaxis=dict(showgrid=True, gridcolor='#ECF0F1', zeroline=True, zerolinewidth=1, zerolinecolor='#6c757d'),
            yaxis=dict(showgrid=True, gridcolor='#ECF0F1', showline=True, linewidth=1, linecolor='#6c757d',
                zeroline=True, zerolinewidth=1, zerolinecolor='#6c757d', rangemode='tozero'),
            height=500)
        return fig

    def _create_month_comparison_chart(self, filtered_df, chart_type, smoothing, year_range, stats_options):
        """Create chart comparing current month against historical months."""
        import datetime, calendar
        fig = go.Figure()
        current_date = filtered_df['AppointmentTime'].max()
        current_month, current_year = current_date.month, current_date.year

        filtered_df['year'] = filtered_df['AppointmentTime'].dt.year
        filtered_df['month'] = filtered_df['AppointmentTime'].dt.month
        filtered_df['day_of_month'] = filtered_df['AppointmentTime'].dt.day
        month_data = filtered_df[filtered_df['month'] == current_month].copy()

        if month_data.empty:
            return go.Figure().update_layout(title=f"No data for {datetime.date(1900, current_month, 1).strftime('%B')}")

        years = sorted(month_data['year'].unique())
        historical_years = [y for y in years if y < current_year]
        colors = ['#d3d3d3'] * (len(years) - 1) + ['#8B5CF6']
        all_year_data = {}
        hide_historical = stats_options.get('show_mean') or stats_options.get('show_median')

        for idx, year in enumerate(years):
            year_month_data = month_data[month_data['year'] == year].copy()
            if year_month_data.empty:
                continue

            daily_counts = year_month_data.groupby('day_of_month').size().reset_index(name='count')
            daily_counts = daily_counts.sort_values('day_of_month')
            daily_counts['cumulative'] = daily_counts['count'].cumsum()
            x_values, y_values = daily_counts['day_of_month'].values, daily_counts['cumulative'].values
            all_year_data[year] = {'x': x_values, 'y': y_values}

            is_current_year = (year == current_year)
            line_width, line_color = (3, colors[idx]) if is_current_year else (1, colors[idx])

            if hide_historical and not is_current_year:
                continue

            if chart_type == 'line':
                if smoothing > 0 and len(y_values) > 2:
                    frac = 0.01 + (smoothing / 10) * 0.49
                    smoothed = lowess(y_values, np.arange(len(y_values)), frac=frac, return_sorted=False)
                    y_values = smoothed
                fig.add_trace(go.Scatter(x=x_values, y=y_values, mode='lines', name=str(year),
                    line=dict(width=line_width, color=line_color)))
            else:
                fig.add_trace(go.Bar(x=x_values, y=y_values, name=str(year), marker_color=line_color))

        fig.update_layout(title=f"{datetime.date(1900, current_month, 1).strftime('%B')} Comparison Across Years",
            xaxis_title="Day of Month", yaxis_title="Cumulative Simulation Count",
            hovermode='x unified', plot_bgcolor='white', paper_bgcolor='white',
            font=dict(color='#2C3E50', size=12),
            xaxis=dict(showgrid=True, gridcolor='#ECF0F1'), yaxis=dict(showgrid=True, gridcolor='#ECF0F1', rangemode='tozero'),
            height=500)
        return fig

    def _create_quarter_comparison_chart(self, filtered_df, chart_type, smoothing, year_range, stats_options):
        """Create chart comparing current quarter against historical quarters."""
        import datetime
        fig = go.Figure()
        current_date = filtered_df['AppointmentTime'].max()
        current_quarter = (current_date.month - 1) // 3 + 1
        current_year = current_date.year

        filtered_df['year'] = filtered_df['AppointmentTime'].dt.year
        filtered_df['quarter'] = filtered_df['AppointmentTime'].dt.quarter
        filtered_df['day_of_year'] = filtered_df['AppointmentTime'].dt.dayofyear
        quarter_data = filtered_df[filtered_df['quarter'] == current_quarter].copy()

        if quarter_data.empty:
            return go.Figure().update_layout(title=f"No data for Q{current_quarter}")

        quarter_start_doy = {1: 1, 2: 91, 3: 182, 4: 274}
        start_doy = quarter_start_doy[current_quarter]
        quarter_data['day_of_quarter'] = quarter_data['day_of_year'] - start_doy + 1

        years = sorted(quarter_data['year'].unique())
        historical_years = [y for y in years if y < current_year]
        colors = ['#d3d3d3'] * (len(years) - 1) + ['#8B5CF6']
        all_year_data = {}
        hide_historical = stats_options.get('show_mean') or stats_options.get('show_median')

        for idx, year in enumerate(years):
            year_quarter_data = quarter_data[quarter_data['year'] == year].copy()
            if year_quarter_data.empty:
                continue

            daily_counts = year_quarter_data.groupby('day_of_quarter').size().reset_index(name='count')
            daily_counts = daily_counts.sort_values('day_of_quarter')
            daily_counts['cumulative'] = daily_counts['count'].cumsum()
            x_values, y_values = daily_counts['day_of_quarter'].values, daily_counts['cumulative'].values
            all_year_data[year] = {'x': x_values, 'y': y_values}

            is_current_year = (year == current_year)
            line_width, line_color = (3, colors[idx]) if is_current_year else (1, colors[idx])

            if hide_historical and not is_current_year:
                continue

            if chart_type == 'line':
                if smoothing > 0 and len(y_values) > 2:
                    frac = 0.01 + (smoothing / 10) * 0.49
                    smoothed = lowess(y_values, np.arange(len(y_values)), frac=frac, return_sorted=False)
                    y_values = smoothed
                fig.add_trace(go.Scatter(x=x_values, y=y_values, mode='lines', name=str(year),
                    line=dict(width=line_width, color=line_color)))
            else:
                fig.add_trace(go.Bar(x=x_values, y=y_values, name=str(year), marker_color=line_color))

        fig.update_layout(title=f"Q{current_quarter} Comparison Across Years",
            xaxis_title="Day of Quarter", yaxis_title="Cumulative Simulation Count",
            hovermode='x unified', plot_bgcolor='white', paper_bgcolor='white',
            font=dict(color='#2C3E50', size=12),
            xaxis=dict(showgrid=True, gridcolor='#ECF0F1'), yaxis=dict(showgrid=True, gridcolor='#ECF0F1', rangemode='tozero'),
            height=500)
        return fig

    def create_chart(self, filtered_df, aggregation, chart_type, comparison_mode, smoothing=1, year_range=None, stats_options=None, calendar_aligned=False, period_type='year'):
        """
        Create the visualization chart.

        Args:
            filtered_df: Filtered DataFrame
            aggregation: Time aggregation ('Daily', 'Weekly', 'Monthly', 'Quarterly', 'Yearly')
            chart_type: 'line' or 'bar'
            comparison_mode: 'none', 'location', or 'previous_periods'
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

        # Handle previous_periods comparison mode for Daily aggregation
        if comparison_mode == 'previous_periods' and aggregation == 'Daily' and year_range:
            if period_type == 'year':
                return self._create_previous_periods_chart(filtered_df, chart_type, smoothing, year_range, stats_options)
            elif period_type == 'month':
                return self._create_month_comparison_chart(filtered_df, chart_type, smoothing, year_range, stats_options)
            elif period_type == 'quarter':
                return self._create_quarter_comparison_chart(filtered_df, chart_type, smoothing, year_range, stats_options)

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
