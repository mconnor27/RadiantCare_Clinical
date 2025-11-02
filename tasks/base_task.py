"""
Abstract base class for task implementations
"""
from abc import ABC, abstractmethod


class BaseTask(ABC):
    """
    Base class that all task implementations must inherit from.

    Each task should implement:
    - Sidebar layout (filters, controls)
    - Main panel layout (visualizations, metrics)
    - Callback registration (interactivity)
    """

    def __init__(self, df):
        """
        Initialize task with data.

        Args:
            df: Pandas DataFrame with task data
        """
        self.df = df

    @abstractmethod
    def get_sidebar_layout(self):
        """
        Get the sidebar layout for this task.

        Returns:
            Dash component(s) for the sidebar
        """
        pass

    @abstractmethod
    def get_main_panel_layout(self):
        """
        Get the main content panel layout for this task.

        Returns:
            Dash component(s) for the main panel
        """
        pass

    @abstractmethod
    def register_callbacks(self, app):
        """
        Register all Dash callbacks for this task.

        Args:
            app: Dash application instance
        """
        pass
