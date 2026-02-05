"""
Review Plan main panel - reuses Draw Volumes panel
"""
from tasks.draw_volumes.draw_volumes_panel import create_main_panel_layout as draw_volumes_panel
from tasks.draw_volumes.draw_volumes_panel import register_callbacks as draw_volumes_callbacks


def create_main_panel_layout():
    """Create main panel layout for Review Plan task (reuses Draw Volumes panel)"""
    return draw_volumes_panel()


def register_callbacks(app, task):
    """Register callbacks for Review Plan task (reuses Draw Volumes callbacks)"""
    # Use the same callbacks as Draw Volumes
    draw_volumes_callbacks(app, task)
