"""Reusable collapsible detail table component.

Wraps an AG Grid inside a dmc.Accordion with consistent sizing, export button,
and optional extra controls in the header row.
"""

import dash_ag_grid as dag
import dash_mantine_components as dmc
from config.settings import DEFAULT_COLUMN_DEFS, DEFAULT_GRID_OPTIONS, DEFAULT_GRID_STYLE, DEFAULT_GRID_CLASS


def detail_table(
    grid_id: str,
    title: str = "Details",
    export_id: str | None = None,
    extra_controls: list | None = None,
    height: int | None = None,
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
    """
    header_children = [
        dmc.Text(title, size="sm", fw=500, c="#6B7280"),
    ]

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

    if right_children:
        header_content = dmc.Group(
            justify="space-between",
            style={"width": "100%"},
            children=[
                header_children[0],
                dmc.Group(gap="sm", align="center", children=right_children),
            ],
        )
    else:
        header_content = header_children[0]

    return dmc.Accordion(
        variant="contained",
        radius="md",
        chevronPosition="left",
        children=[
            dmc.AccordionItem(
                value="detail",
                children=[
                    dmc.AccordionControl(header_content),
                    dmc.AccordionPanel(
                        dag.AgGrid(
                            id=grid_id,
                            columnDefs=[],
                            rowData=[],
                            defaultColDef=DEFAULT_COLUMN_DEFS,
                            columnSize="responsiveSizeToFit",
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
