"""Shared renderers for help modal content.

Produces the SQL tab content from sql_summaries.SQL_SCRIPTS so every page
gets a consistent look without duplicating the DMC scaffolding.
"""

from __future__ import annotations

import dash_mantine_components as dmc
from dash_iconify import DashIconify

from config.settings import PRIMARY
from .sql_summaries import SHARED_CONVENTIONS, SQL_SCRIPTS


# ---------------------------------------------------------------------------
# SQL tab
# ---------------------------------------------------------------------------

def _script_card(key: str) -> dmc.Paper:
    """Render one SQL script summary as a paper card."""
    s = SQL_SCRIPTS[key]
    return dmc.Paper(
        p="md", radius="md", withBorder=True, mb="md",
        children=[
            dmc.Group(
                justify="space-between",
                align="center",
                mb="xs",
                children=[
                    dmc.Group(
                        gap="xs",
                        children=[
                            DashIconify(icon="tabler:file-code", width=20, color=PRIMARY),
                            dmc.Text(f"{key}.sql", fw=600, size="sm"),
                        ],
                    ),
                    dmc.Group(
                        gap=6,
                        children=[
                            dmc.Badge(
                                f"{s['sql']:,} SQL",
                                color="violet", variant="filled", size="sm",
                            ),
                            dmc.Badge(
                                f"{s['total']:,} total",
                                color="violet", variant="light", size="sm",
                            ),
                        ],
                    ),
                ],
            ),

            dmc.Text("Purpose", fw=600, size="xs", c=PRIMARY, mt="xs", mb=4),
            dmc.Text(s["purpose"], size="xs", style={"lineHeight": 1.55}),

            dmc.Text("Unique Logic", fw=600, size="xs", c=PRIMARY, mt="md", mb=4),
            dmc.List(
                size="xs",
                spacing=4,
                children=[dmc.ListItem(x) for x in s["unique_logic"]],
            ),

            dmc.Text("Output Columns", fw=600, size="xs", c=PRIMARY, mt="md", mb=4),
            dmc.Text(s["output_cols"], size="xs", c="dimmed", style={"lineHeight": 1.55}),

            dmc.Text("Default Date Range", fw=600, size="xs", c=PRIMARY, mt="md", mb=4),
            dmc.Text(s["date_range"], size="xs", c="dimmed"),
        ],
    )


def sql_tab(script_keys: list[str], intro: str | None = None) -> dmc.Stack:
    """Render a SQL tab containing the given SQL_SCRIPTS entries.

    Parameters
    ----------
    script_keys : list[str]
        Keys into SQL_SCRIPTS. Rendered in the order given.
    intro : str | None
        Optional intro paragraph shown above the scripts.
    """
    missing = [k for k in script_keys if k not in SQL_SCRIPTS]
    if missing:
        raise KeyError(f"Unknown SQL script keys: {missing}")

    children: list = []

    if intro:
        children.append(
            dmc.Text(intro, size="sm", c="dimmed", mb="md", style={"lineHeight": 1.55})
        )

    children.append(
        dmc.Paper(
            p="sm", radius="md", withBorder=False,
            style={"backgroundColor": "#F3E8F5"},
            mb="md",
            children=[
                dmc.Group(
                    gap="xs", mb="xs",
                    children=[
                        DashIconify(icon="tabler:info-circle", width=16, color=PRIMARY),
                        dmc.Text("Shared Conventions", fw=600, size="xs", c=PRIMARY),
                    ],
                ),
                dmc.List(
                    size="xs",
                    spacing=2,
                    children=[dmc.ListItem(x) for x in SHARED_CONVENTIONS],
                ),
            ],
        )
    )

    for key in script_keys:
        children.append(_script_card(key))

    return dmc.Stack(gap=0, children=children)


# ---------------------------------------------------------------------------
# Tabs container — used by every page's help content
# ---------------------------------------------------------------------------

def help_tabs(sql_content, ui_content) -> dmc.Tabs:
    """Standard two-tab layout: SQL Data Source | UI & Data Processing."""
    return dmc.Tabs(
        value="sql",
        children=[
            dmc.TabsList(
                children=[
                    dmc.TabsTab(
                        "SQL Data Source",
                        value="sql",
                        leftSection=DashIconify(icon="tabler:database", width=16),
                    ),
                    dmc.TabsTab(
                        "UI & Data Processing",
                        value="ui",
                        leftSection=DashIconify(icon="tabler:layout-dashboard", width=16),
                    ),
                ],
            ),
            dmc.TabsPanel(value="sql", pt="md", children=sql_content),
            dmc.TabsPanel(value="ui", pt="md", children=ui_content),
        ],
    )


# ---------------------------------------------------------------------------
# Section helpers — used by UI-tab content files
# ---------------------------------------------------------------------------

def section(title: str, icon: str, *children) -> dmc.Paper:
    """Standard bordered paper with an icon+title header, used by UI tabs."""
    return dmc.Paper(
        p="md", radius="md", withBorder=True, mb="md",
        children=[
            dmc.Group(
                gap="xs", mb="xs",
                children=[
                    DashIconify(icon=icon, width=20, color=PRIMARY),
                    dmc.Text(title, fw=600, size="sm"),
                ],
            ),
            *children,
        ],
    )


def subheading(text: str) -> dmc.Text:
    return dmc.Text(text, fw=600, size="xs", c=PRIMARY, mt="xs", mb=4)


def body(text: str, **kwargs) -> dmc.Text:
    defaults = {"size": "xs", "style": {"lineHeight": 1.55}}
    defaults.update(kwargs)
    return dmc.Text(text, **defaults)


def bullets(items: list[str], **kwargs) -> dmc.List:
    defaults = {"size": "xs", "spacing": 4}
    defaults.update(kwargs)
    return dmc.List(
        children=[dmc.ListItem(x) for x in items],
        **defaults,
    )
