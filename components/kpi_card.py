"""KPI card component with optional sparkline."""

import dash_mantine_components as dmc
from dash import dcc
import plotly.graph_objects as go

from config.settings import PRIMARY, NEUTRAL, SEMANTIC_COLORS


def create_sparkline(past_values=None, future_values=None, color=PRIMARY, height=30):
    """Create a tiny sparkline figure for KPI cards.

    Args:
        past_values: list of numeric values for the solid past line
        future_values: list of numeric values for the dotted future line
        color: line color
        height: sparkline height in px
    """
    fig = go.Figure()

    if past_values:
        x_past = list(range(len(past_values)))
        fig.add_trace(go.Scatter(
            x=x_past, y=past_values,
            mode="lines",
            line=dict(color=color, width=1.5),
            hoverinfo="skip",
        ))

    if future_values and past_values:
        x_start = len(past_values) - 1
        combined_y = [past_values[-1]] + list(future_values)
        x_future = list(range(x_start, x_start + len(combined_y)))
        fig.add_trace(go.Scatter(
            x=x_future, y=combined_y,
            mode="lines",
            line=dict(color=color, width=1.5, dash="dot"),
            hoverinfo="skip",
        ))

    fig.update_layout(
        margin=dict(l=0, r=0, t=0, b=0),
        height=height,
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(visible=False),
        yaxis=dict(visible=False),
        showlegend=False,
    )
    return fig


def kpi_card(
    label,
    value,
    trend_text=None,
    trend_direction=None,
    sparkline_past=None,
    sparkline_future=None,
    accent_color=None,
    card_id=None,
):
    """Create a KPI card.

    Args:
        label: KPI label text
        value: KPI display value (string)
        trend_text: e.g., "8.2% vs prior"
        trend_direction: "up" or "down" — determines color
        sparkline_past: list of values for past sparkline
        sparkline_future: list of values for future sparkline
        accent_color: optional left-border accent color
        card_id: optional component ID
    """
    trend_color = None
    trend_icon = ""
    if trend_direction == "up":
        trend_color = SEMANTIC_COLORS["success"]
        trend_icon = "\u25b2 "
    elif trend_direction == "down":
        trend_color = SEMANTIC_COLORS["error"]
        trend_icon = "\u25bc "

    children = [
        dmc.Text(label, size="xs", c=NEUTRAL["text_secondary"], fw=500),
        dmc.Text(str(value), size="xl", fw=700, c=NEUTRAL["text_primary"]),
    ]

    if trend_text:
        children.append(
            dmc.Text(
                f"{trend_icon}{trend_text}",
                size="xs",
                c=trend_color or NEUTRAL["text_muted"],
            )
        )

    if sparkline_past:
        children.append(
            dcc.Graph(
                figure=create_sparkline(sparkline_past, sparkline_future, accent_color or PRIMARY),
                config={"displayModeBar": False, "staticPlot": True},
                style={"height": "30px", "marginTop": "4px"},
            )
        )

    style = {
        "borderLeft": f"4px solid {accent_color}" if accent_color else "none",
    }

    return dmc.Paper(
        children=dmc.Stack(children=children, gap=4),
        p="md",
        radius="md",
        shadow="xs",
        withBorder=True,
        style=style,
        id=card_id or "",
    )
