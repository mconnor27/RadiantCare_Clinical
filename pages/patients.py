"""Patients page — placeholder for future implementation."""

import dash
import dash_mantine_components as dmc

dash.register_page(__name__, path="/patients", name="Patients", order=11)

layout = dmc.Stack(
    gap=16,
    className="page-content",
    children=[
        dmc.Title("Patients", order=2, className="page-title"),
        dmc.Paper(
            dmc.Text("Patients page — coming soon (requires Mapbox token)", c="#9CA3AF", ta="center", py="xl"),
            p="xl", radius="md", shadow="xs", withBorder=True,
        ),
    ],
)
