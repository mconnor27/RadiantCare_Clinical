"""Reusable collapsible detail table component.

Wraps an AG Grid inside a dmc.Accordion with consistent sizing, export button,
and optional extra controls in the header row.

Controls (Export, Clear Filters, etc.) are positioned outside the
AccordionControl so clicks don't toggle the accordion.
"""

import dash_ag_grid as dag
import dash_mantine_components as dmc
from dash import html
from config.settings import DEFAULT_COLUMN_DEFS, DEFAULT_GRID_OPTIONS, DEFAULT_GRID_STYLE, DEFAULT_GRID_CLASS


def detail_table(
    grid_id: str,
    title: str = "Details",
    export_id: str | None = None,
    extra_controls: list | None = None,
    height: int | None = None,
    accordion_id: str | None = None,
    column_size: str = "responsiveSizeToFit",
    column_size_options: dict | None = None,
):
    """Return a collapsible Accordion containing an AG Grid detail table.

    Parameters
    ----------
    grid_id : str
        The Dash component ID for the AgGrid (e.g. ``"cv-detail-grid"``).
    title : str
        Title shown in the accordion header.
    export_id : str or None
        ID for the Export CSV button.  If None, no export button is rendered.
    extra_controls : list or None
        Additional Dash components to place in the header row (left of export).
    height : int or None
        Grid height in pixels.  If None, uses DEFAULT_GRID_STYLE.
    accordion_id : str or None
        Optional Dash ID for the Accordion wrapper (enables controlled open/close).
    """
    right_children = []
    if extra_controls:
        right_children.extend(extra_controls)
    if export_id:
        right_children.append(
            dmc.Button(
                "Export CSV",
                id=export_id,
                size="compact-xs",
                variant="light",
            ),
        )

    accordion_props = {}
    if accordion_id:
        accordion_props["id"] = accordion_id

    accordion = dmc.Accordion(
        variant="contained",
        radius="md",
        chevronPosition="left",
        **accordion_props,
        children=[
            dmc.AccordionItem(
                value="detail",
                children=[
                    dmc.AccordionControl(
                        dmc.Text(title, size="sm", fw=500, c="#6B7280"),
                    ),
                    dmc.AccordionPanel(
                        dag.AgGrid(
                            id=grid_id,
                            columnDefs=[],
                            rowData=[],
                            defaultColDef=DEFAULT_COLUMN_DEFS,
                            columnSize=column_size,
                            **({"columnSizeOptions": column_size_options} if column_size_options else {}),
                            dashGridOptions={
                                **DEFAULT_GRID_OPTIONS,
                                "domLayout": "normal",
                            },
                            style={**DEFAULT_GRID_STYLE, **({"height": f"{height}px"} if height else {})},
                            className=DEFAULT_GRID_CLASS,
                        ),
                    ),
                ],
            ),
        ],
    )

    if not right_children:
        return accordion

    # Overlay controls above the accordion header so clicks don't toggle it
    return html.Div(
        style={"position": "relative"},
        children=[
            accordion,
            html.Div(
                dmc.Group(gap="sm", align="center", children=right_children),
                className="detail-table-controls",
                style={
                    "position": "absolute",
                    "top": 0,
                    "right": 12,
                    "height": "42px",
                    "display": "flex",
                    "alignItems": "center",
                    "zIndex": 2,
                },
            ),
        ],
    )
