"""Plotly chart helpers and default layout."""

import plotly.graph_objects as go
from config.settings import DEFAULT_LAYOUT, DEPARTMENT_COLORS, CHART_COLORWAY


def apply_default_layout(fig, **overrides):
    """Apply the default layout to a Plotly figure with optional overrides."""
    layout = {**DEFAULT_LAYOUT, **overrides}
    fig.update_layout(**layout)
    return fig


def empty_figure(message="No data for selected filters"):
    """Return a blank figure with a centered message."""
    fig = go.Figure()
    fig.add_annotation(
        text=message,
        xref="paper", yref="paper",
        x=0.5, y=0.5,
        showarrow=False,
        font=dict(size=14, color="#9CA3AF"),
    )
    fig.update_layout(
        xaxis=dict(visible=False),
        yaxis=dict(visible=False),
        plot_bgcolor="#FFFFFF",
        paper_bgcolor="#FFFFFF",
        margin=dict(l=0, r=0, t=0, b=0),
    )
    return fig


def dept_color(dept_name):
    """Get the department color, defaulting to primary."""
    return DEPARTMENT_COLORS.get(dept_name, CHART_COLORWAY[0])


def color_for_index(i):
    """Get a color from the chart colorway by index."""
    return CHART_COLORWAY[i % len(CHART_COLORWAY)]


def smooth_limits(range_days, current_value):
    """Scale smoothing slider max to the selected visible range.

    Args:
        range_days: String like "30", "90", "365", "0" (all), or "thisweek".
        current_value: Current slider value (clamped to new max).

    Returns:
        (max_val, clamped_value) tuple for slider max and value.
    """
    if range_days == "thisweek":
        return 3, min(current_value or 0, 3)
    days = int(range_days) if range_days else 90
    if days == 0:
        max_val = 180
    elif days <= 30:
        max_val = 12
    elif days <= 60:
        max_val = 20
    elif days <= 90:
        max_val = 30
    elif days <= 180:
        max_val = 60
    elif days <= 365:
        max_val = 120
    else:
        max_val = 180
    return max_val, min(current_value or 0, max_val)
