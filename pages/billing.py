"""Billing page — placeholder for future implementation."""

import dash
import dash_mantine_components as dmc

dash.register_page(__name__, path="/billing", name="Billing", order=7)

layout = dmc.Stack(
    gap=16,
    className="page-content",
    children=[
        dmc.Title("Billing", order=2, className="page-title"),
        dmc.Paper(
            dmc.Text("Billing page — coming soon", c="#9CA3AF", ta="center", py="xl"),
            p="xl", radius="md", shadow="xs", withBorder=True,
        ),
    ],
)
