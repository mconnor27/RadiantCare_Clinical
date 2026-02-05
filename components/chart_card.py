"""Chart card component — wraps a Plotly figure with title and optional inline controls."""

import dash_mantine_components as dmc
from dash import dcc

from config.settings import NEUTRAL


def chart_card(
    title,
    figure,
    card_id=None,
    controls=None,
    height=380,
):
    """Create a chart card.

    Args:
        title: chart title text
        figure: plotly Figure object
        card_id: component ID for the graph
        controls: optional list of DMC components for inline controls (right side of title bar)
        height: chart height in px
    """
    title_row_children = [
        dmc.Text(title, size="sm", fw=500, c=NEUTRAL["text_secondary"]),
    ]
    if controls:
        title_row_children.append(
            dmc.Group(children=controls, gap="xs"),
        )

    return dmc.Paper(
        children=[
            dmc.Group(
                children=title_row_children,
                justify="space-between",
                mb="sm",
            ),
            dcc.Graph(
                id=card_id or "",
                figure=figure,
                config={
                    "displayModeBar": False,
                    "responsive": True,
                },
                style={"height": f"{height}px"},
            ),
        ],
        p="md",
        radius="md",
        shadow="xs",
        withBorder=True,
    )
