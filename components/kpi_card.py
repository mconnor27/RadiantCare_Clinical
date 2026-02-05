"""KPI card component with optional sparkline."""

import dash_mantine_components as dmc
from dash import dcc
import plotly.graph_objects as go

from config.settings import PRIMARY, NEUTRAL, SEMANTIC_COLORS


def create_sparkline(past_values=None, future_values=None,
                     past_labels=None, future_labels=None,
                     color=PRIMARY, hover_fmt=None):
    """Create a tiny sparkline figure for KPI cards.

    Args:
        past_values: list of numeric values for the solid past line
        future_values: list of numeric values for the dotted future line
        past_labels: list of date/label values for past x-axis
        future_labels: list of date/label values for future x-axis
        color: line color
        hover_fmt: custom hovertemplate format string
    """
    fig = go.Figure()
    has_labels = past_labels is not None and len(past_labels) > 0

    # Determine hover template
    if hover_fmt:
        hover = hover_fmt
    elif has_labels:
        hover = "%{x|%b %d}: %{y:,.0f}<extra></extra>"
    else:
        hover = "%{y:,.0f}<extra></extra>"

    if past_values:
        x_past = list(past_labels) if has_labels else list(range(len(past_values)))
        fig.add_trace(go.Scatter(
            x=x_past, y=past_values,
            mode="lines",
            line=dict(color=color, width=1.5),
            hovertemplate=hover,
        ))

    if future_values and past_values:
        if has_labels and future_labels is not None and len(future_labels) > 0:
            x_future = [past_labels[-1]] + list(future_labels)
        else:
            x_start = len(past_values) - 1
            combined_y = [past_values[-1]] + list(future_values)
            x_future = list(range(x_start, x_start + len(combined_y)))
        combined_y = [past_values[-1]] + list(future_values)
        fig.add_trace(go.Scatter(
            x=x_future, y=combined_y,
            mode="lines",
            line=dict(color=color, width=1.5, dash="dot"),
            hovertemplate=hover,
        ))

    fig.update_layout(
        margin=dict(l=0, r=0, t=0, b=0),
        height=34,
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(
            visible=False,
            showspikes=True,
            spikemode="across",
            spikethickness=1,
            spikecolor="#D1D5DB",
            spikedash="solid",
        ),
        yaxis=dict(visible=False),
        showlegend=False,
        dragmode=False,
        hovermode="x",
        hoverlabel=dict(
            bgcolor=color,
            font=dict(color="white", size=10, family="Inter, sans-serif"),
            bordercolor=color,
        ),
    )
    return fig


def kpi_card(
    label,
    value,
    trend_text=None,
    trend_direction=None,
    sparkline_past=None,
    sparkline_future=None,
    sparkline_past_labels=None,
    sparkline_future_labels=None,
    sparkline_hover_fmt=None,
    accent_color=None,
    card_id=None,
    value_detail=None,
    sparkline_id=None,
):
    """Create a KPI card.

    Args:
        label: KPI label text
        value: KPI display value (string)
        trend_text: e.g., "8.2% vs prior"
        trend_direction: "up" or "down" — determines color
        sparkline_past: list of values for past sparkline
        sparkline_future: list of values for future sparkline
        sparkline_past_labels: list of date labels for past x-axis
        sparkline_future_labels: list of date labels for future x-axis
        sparkline_hover_fmt: custom hover format for sparkline
        accent_color: optional left-border accent color
        card_id: optional component ID
        value_detail: optional sub-text displayed inline to the right of value
        sparkline_id: optional ID for the sparkline Graph (for clientside updates)
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
    ]

    # Value row: value + optional detail + optional trend, all inline
    value_row = [dmc.Text(str(value), size="xl", fw=700, c=NEUTRAL["text_primary"])]
    if value_detail:
        value_row.append(dmc.Text(value_detail, size="xs", c=NEUTRAL["text_muted"]))
    if trend_text:
        value_row.append(
            dmc.Text(
                f"{trend_icon}{trend_text}",
                size="xs",
                c=trend_color or NEUTRAL["text_muted"],
            )
        )
    children.append(dmc.Group(gap="xs", align="baseline", children=value_row))

    if sparkline_past or sparkline_id:
        children.append(
            dcc.Graph(
                id=sparkline_id or "",
                figure=create_sparkline(
                    sparkline_past, sparkline_future,
                    sparkline_past_labels, sparkline_future_labels,
                    accent_color or PRIMARY,
                    hover_fmt=sparkline_hover_fmt,
                ) if sparkline_past else {},
                config={"displayModeBar": False, "scrollZoom": False},
                style={"height": "34px", "marginTop": "4px"},
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
