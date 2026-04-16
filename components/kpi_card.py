"""KPI card component with optional sparkline."""

import dash_mantine_components as dmc
from dash import dcc, html
import plotly.graph_objects as go

from config.settings import PRIMARY, NEUTRAL, SEMANTIC_COLORS


def kpi_placeholder(accent_color=None):
    """Skeleton placeholder for a KPI card — shown before data loads."""
    return dmc.Paper(
        children=[
            dmc.Stack(gap=8, children=[
                dmc.Skeleton(height=12, width="60%", radius="sm"),
                dmc.Skeleton(height=24, width="40%", radius="sm"),
                dmc.Skeleton(height=10, width="50%", radius="sm"),
                dmc.Skeleton(height=44, radius="sm"),
            ]),
        ],
        pt="sm", px="md", pb=4,
        radius="md", shadow="xs", withBorder=True,
        style={
            "borderLeft": f"4px solid {accent_color}" if accent_color else "none",
        },
    )


def _hex_to_rgba(hex_color, alpha):
    """Convert hex color to rgba string."""
    r = int(hex_color[1:3], 16)
    g = int(hex_color[3:5], 16)
    b = int(hex_color[5:7], 16)
    return f"rgba({r},{g},{b},{alpha})"


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

    # Compute y range for gradient fill
    all_vals = list(past_values or []) + list(future_values or [])
    if all_vals:
        y_min = min(all_vals)
        y_max = max(all_vals)
        y_range = y_max - y_min or 1
    else:
        y_min, y_max, y_range = 0, 1, 1

    y_floor = y_min - y_range * 0.3

    if past_values:
        x_past = list(past_labels) if has_labels else list(range(len(past_values)))
        # Invisible baseline trace at y-axis bottom (fill anchor)
        fig.add_trace(go.Scatter(
            x=x_past, y=[y_floor] * len(x_past),
            mode="lines",
            line=dict(width=0, color="rgba(0,0,0,0)"),
            hoverinfo="skip",
            showlegend=False,
        ))
        # Sparkline trace fills down to baseline
        fig.add_trace(go.Scatter(
            x=x_past, y=past_values,
            mode="lines",
            line=dict(color=color, width=1.5),
            fill="tonexty",
            fillgradient=dict(
                type="vertical",
                start=y_floor,
                stop=y_max,
                colorscale=[
                    [0, _hex_to_rgba(color, 0)],
                    [1, _hex_to_rgba(color, 0.2)],
                ],
            ),
            fillcolor=_hex_to_rgba(color, 0),
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
        height=44,
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
        yaxis=dict(
            visible=False,
            range=[y_floor, y_max + y_range * 0.05],
        ),
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
    header_control=None,
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
        header_control: optional Dash component absolutely positioned top-right
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

    # Value row: value + optional detail inline
    value_row = [dmc.Text(str(value), size="xl", fw=700, c=NEUTRAL["text_primary"], lh=1.2)]
    if value_detail:
        value_row.append(dmc.Text(value_detail, size="sm", fw=500, c=NEUTRAL["text_muted"]))
    children.append(dmc.Group(gap="xs", align="baseline", children=value_row))

    # Trend on its own line (reserve space only when sparkline or trend present)
    has_sparkline = sparkline_past or sparkline_id
    if trend_text or has_sparkline:
        children.append(
            dmc.Text(
                f"{trend_icon}{trend_text}" if trend_text else "\u00a0",
                size="xs",
                c=trend_color or NEUTRAL["text_muted"],
                mb=4,
            )
        )

    if sparkline_past or sparkline_id:
        children.append(
            dcc.Graph(
                id=sparkline_id or "",
                figure=create_sparkline(
                    sparkline_past, sparkline_future,
                    sparkline_past_labels, sparkline_future_labels,
                    accent_color or PRIMARY,
                    hover_fmt=sparkline_hover_fmt,
                ) if sparkline_past else create_sparkline(),
                config={"displayModeBar": False, "scrollZoom": False},
                style={"height": "44px", "marginTop": "2px"},
            )
        )

    style = {
        "borderLeft": f"4px solid {accent_color}" if accent_color else "none",
        "position": "relative",
    }

    paper_children = [dmc.Stack(children=children, gap=2)]

    if header_control is not None:
        paper_children.append(
            html.Div(header_control, style={
                "position": "absolute",
                "top": "10px",
                "right": "14px",
                "zIndex": 2,
            })
        )

    return dmc.Paper(
        children=paper_children,
        pt="sm",
        px="sm",
        pb="sm" if not (sparkline_past or sparkline_id) else 4,
        radius="md",
        shadow="xs",
        withBorder=True,
        style=style,
        id=card_id or "",
    )
