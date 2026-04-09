"""Reusable diagnosis accordion filter component.

Provides a dropdown panel with:
- Checkbox per category (for filtering selection)
- Accordion expand per category (for browsing subcategories)
- Optional subcategory chip selection within expanded panels

Usage:
    from components.diagnosis_filter import diagnosis_accordion, register_diagnosis_callbacks

    # In layout:
    diagnosis_accordion("cv")

    # After layout:
    register_diagnosis_callbacks("cv")

    # In main callback, read selected categories from the store:
    Input("cv-diag-store", "data")

Generated IDs (all prefixed with page_id):
    {page_id}-diag-trigger      Button (trigger)
    {page_id}-diag-clear        ActionIcon (clear)
    {page_id}-diag-store        dcc.Store (selected categories list)
    {page_id}-diag-mode         dcc.Store ("primary" or "all")
    {page_id}-diag-mode-ctrl    SegmentedControl (Primary / All toggle)
    {page_id}-diag-panel        Paper (dropdown panel)
    {page_id}-diag-accordion    Accordion (expand/collapse)
    {page_id}-diag-subcategory  ChipGroup (subcategory selection)
    {"type": "diag-cat-{page_id}", "index": i}  Checkboxes
"""

from __future__ import annotations

import dash
import dash_mantine_components as dmc
from dash import ALL, Input, Output, State, callback, clientside_callback, dcc, html
from dash_iconify import DashIconify

from utils.diagnosis_categories import CATEGORIES, SUBCATEGORIES


def diagnosis_accordion(page_id: str) -> html.Div:
    """Return the diagnosis accordion filter widget for a page."""
    cat_type = f"diag-cat-{page_id}"

    return html.Div(
        children=[
            html.Div(
                children=[
                    dmc.Button(
                        "Diagnosis",
                        id=f"{page_id}-diag-trigger",
                        variant="default",
                        size="sm",
                        rightSection=DashIconify(icon="mdi:chevron-down", width=14),
                    ),
                    dmc.ActionIcon(
                        DashIconify(icon="mdi:close-circle", width=18),
                        id=f"{page_id}-diag-clear",
                        variant="subtle",
                        color="gray",
                        size="sm",
                        className="wf-filter-clear-btn",
                    ),
                ],
                style={"position": "relative", "display": "inline-block"},
            ),
            # Hidden stores for selected categories and mode
            dcc.Store(id=f"{page_id}-diag-store", data=[]),
            dcc.Store(id=f"{page_id}-diag-mode", data="primary"),
            dmc.Paper(
                children=[
                    # Primary / All toggle
                    dmc.SegmentedControl(
                        id=f"{page_id}-diag-mode-ctrl",
                        data=[
                            {"value": "primary", "label": "Primary"},
                            {"value": "all", "label": "All"},
                        ],
                        value="primary",
                        size="xs",
                        fullWidth=True,
                        mb="xs",
                    ),
                    html.Div(
                        children=[
                            dmc.ChipGroup(
                                children=[
                                    dmc.Accordion(
                                        children=[
                                            dmc.AccordionItem(
                                                children=[
                                                    html.Div(
                                                        children=[
                                                            dmc.Checkbox(
                                                                id={"type": cat_type, "index": i},
                                                                size="xs",
                                                                className="wf-diag-cat-check",
                                                            ),
                                                            dmc.AccordionControl(cat),
                                                        ],
                                                        className="wf-diag-cat-row",
                                                    ),
                                                    dmc.AccordionPanel(
                                                        html.Div(
                                                            [dmc.Chip(s, value=s, size="xs", variant="outline")
                                                             for s in SUBCATEGORIES.get(cat, [])],
                                                            className="wf-subcat-chip-list",
                                                        ),
                                                    ),
                                                ],
                                                value=cat,
                                            )
                                            for i, cat in enumerate(CATEGORIES)
                                        ],
                                        multiple=True,
                                        id=f"{page_id}-diag-accordion",
                                        value=[],
                                        variant="contained",
                                        chevronPosition="right",
                                    ),
                                ],
                                id=f"{page_id}-diag-subcategory",
                                multiple=True,
                                value=[],
                            ),
                        ],
                        className="wf-diag-scroll",
                    ),
                ],
                id=f"{page_id}-diag-panel",
                p="xs",
                shadow="md",
                withBorder=True,
                radius="md",
                className="wf-chip-dropdown wf-diag-panel",
                style={"display": "none"},
            ),
        ],
        style={"position": "relative", "display": "inline-block"},
    )


def register_diagnosis_callbacks(page_id: str) -> None:
    """Register all callbacks for the diagnosis accordion filter."""
    cat_type = f"diag-cat-{page_id}"
    store_id = f"{page_id}-diag-store"
    mode_store_id = f"{page_id}-diag-mode"
    mode_ctrl_id = f"{page_id}-diag-mode-ctrl"
    subcat_id = f"{page_id}-diag-subcategory"
    accordion_id = f"{page_id}-diag-accordion"
    trigger_id = f"{page_id}-diag-trigger"
    clear_id = f"{page_id}-diag-clear"
    n_cats = len(CATEGORIES)

    # Mode toggle → store sync
    clientside_callback(
        """function(val) { return val; }""",
        Output(mode_store_id, "data"),
        Input(mode_ctrl_id, "value"),
    )

    # Checkbox → Store sync
    @callback(
        Output(store_id, "data"),
        Input({"type": cat_type, "index": ALL}, "checked"),
        prevent_initial_call=True,
    )
    def _sync_cat_checkboxes(checked_list):
        return [cat for cat, c in zip(CATEGORIES, checked_list) if c]

    # Trigger label
    clientside_callback(
        """function(cats, subs) {
            var total = (cats ? cats.length : 0) + (subs ? subs.length : 0);
            if (total === 0) return "Diagnosis";
            if (subs && subs.length > 0) {
                if (subs.length === 1) return subs[0];
                return subs.length + " subsites";
            }
            if (cats.length === 1) return cats[0];
            return cats.length + " selected";
        }""",
        Output(trigger_id, "children"),
        Input(store_id, "data"),
        Input(subcat_id, "value"),
    )

    # Clear-button visibility
    clientside_callback(
        """function(cats, subs) {
            var has = (cats && cats.length > 0) || (subs && subs.length > 0);
            return has ? {"display": "inline-flex"} : {"display": "none"};
        }""",
        Output(clear_id, "style"),
        Input(store_id, "data"),
        Input(subcat_id, "value"),
    )

    # Clear-button action: reset store + mode + subcategories + accordion + all checkboxes
    cat_check_outputs = [
        Output({"type": cat_type, "index": i}, "checked", allow_duplicate=True)
        for i in range(n_cats)
    ]
    clientside_callback(
        f"""function(n) {{
            var r = [[], "primary", "primary", [], []];
            for (var i = 0; i < {n_cats}; i++) r.push(false);
            return r;
        }}""",
        Output(store_id, "data", allow_duplicate=True),
        Output(mode_store_id, "data", allow_duplicate=True),
        Output(mode_ctrl_id, "value", allow_duplicate=True),
        Output(subcat_id, "value", allow_duplicate=True),
        Output(accordion_id, "value", allow_duplicate=True),
        *cat_check_outputs,
        Input(clear_id, "n_clicks"),
        prevent_initial_call=True,
    )

    # Prune subcategory selections when categories change
    @callback(
        Output(subcat_id, "value", allow_duplicate=True),
        Input(store_id, "data"),
        State(subcat_id, "value"),
        prevent_initial_call=True,
    )
    def _prune_subcategories(selected_cats, current_subs):
        if not selected_cats:
            return []
        valid = set()
        for cat in selected_cats:
            valid.update(SUBCATEGORIES.get(cat, []))
        kept = [s for s in (current_subs or []) if s in valid]
        if kept == (current_subs or []):
            return dash.no_update
        return kept
