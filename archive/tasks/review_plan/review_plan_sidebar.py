"""
Review Plan sidebar - reuses Draw Volumes sidebar
"""
from tasks.draw_volumes.draw_volumes_sidebar import create_sidebar_layout as draw_volumes_sidebar


def create_sidebar_layout(task):
    """Create sidebar layout for Review Plan task (reuses Draw Volumes sidebar)"""
    return draw_volumes_sidebar(task)
