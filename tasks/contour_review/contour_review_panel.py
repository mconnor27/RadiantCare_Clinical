"""
Contour Review main panel layout
"""
from tasks.draw_volumes.draw_volumes_panel import create_main_panel_layout


def create_contour_review_panel():
    """
    Create main content panel layout for Contour Review task.
    Uses the same layout as Draw Volumes.

    Returns:
        Dash component for main panel
    """
    return create_main_panel_layout()
