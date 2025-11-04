"""
Contour Review sidebar layout (filters and controls)
"""
from tasks.draw_volumes.draw_volumes_sidebar import create_sidebar_layout


def create_contour_review_sidebar(task, state=None):
    """
    Create sidebar layout for Contour Review task.
    Uses the same layout as Draw Volumes.

    Args:
        task: ContourReviewTask instance
        state: Optional dict with persisted state values (from sidebar-state-store)

    Returns:
        Dash component for sidebar
    """
    return create_sidebar_layout(task, state)
