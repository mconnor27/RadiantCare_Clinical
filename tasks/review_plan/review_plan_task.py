"""
Review Plan task implementation - reuses Draw Volumes interface with review data
"""
from tasks.draw_volumes.draw_volumes_task import DrawVolumesTask


class ReviewPlanTask(DrawVolumesTask):
    """Task for analyzing review plan completion - inherits all functionality from DrawVolumesTask"""

    def __init__(self, df):
        """
        Initialize Review Plan task.

        Args:
            df: Pandas DataFrame with task data (already preprocessed)
        """
        super().__init__(df)

    def register_callbacks(self, app):
        """
        Review Plan task doesn't register its own callbacks.
        It shares the same UI components with Draw Volumes, so callbacks are already registered.
        """
        # Do nothing - callbacks are shared with Draw Volumes
        pass
