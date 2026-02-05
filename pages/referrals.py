"""Referrals page — placeholder for future implementation."""

import dash
import dash_mantine_components as dmc

dash.register_page(__name__, path="/referrals", name="Referrals", order=12)

layout = dmc.Stack(
    gap="md",
    children=[
        dmc.Title("Referrals", order=2, c="#7C2A83", ta="center", fw=700, py="sm"),
        dmc.Paper(
            dmc.Text("Referrals page — coming soon (requires Mapbox token)", c="#9CA3AF", ta="center", py="xl"),
            p="xl", radius="md", shadow="xs", withBorder=True,
        ),
    ],
)
