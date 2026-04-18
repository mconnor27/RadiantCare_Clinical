"""Placeholder UI content for pages whose help page hasn't been written yet.

Rendered when a page's `ui_module` is set to "placeholder" in the registry.
The SQL tab still renders normally from sql_summaries.
"""

from __future__ import annotations

import dash_mantine_components as dmc
from dash_iconify import DashIconify

from config.settings import PRIMARY

UI_CONTENT = dmc.Stack(
    gap="md",
    align="center",
    style={"padding": "48px 16px"},
    children=[
        DashIconify(icon="tabler:book-off", width=48, color=PRIMARY),
        dmc.Text(
            "UI & processing documentation for this page is coming soon.",
            size="sm", c="dimmed", ta="center",
        ),
        dmc.Text(
            "The SQL Data Source tab above has full detail on the production "
            "SQL script(s) that feed this page.",
            size="xs", c="dimmed", ta="center",
            style={"maxWidth": 420},
        ),
    ],
)
