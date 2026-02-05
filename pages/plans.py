"""Plans page — placeholder for future implementation."""

import dash
import dash_mantine_components as dmc

dash.register_page(__name__, path="/plans", name="Plans", order=10)

layout = dmc.Stack(
    gap="md",
    children=[
        dmc.Title("Plans", order=2, c="#7C2A83", ta="center", fw=700, py="sm"),
        dmc.Paper(
            dmc.Text("Plans page — coming soon", c="#9CA3AF", ta="center", py="xl"),
            p="xl", radius="md", shadow="xs", withBorder=True,
        ),
    ],
)
