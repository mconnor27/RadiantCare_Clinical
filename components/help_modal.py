"""Thin re-export for backwards compatibility.

The help modal has been split into a package under components/help/.
This module preserves the legacy import path `from components.help_modal
import create_help_modal` so existing callers don't have to change.
"""

from components.help import create_help_modal

__all__ = ["create_help_modal"]
