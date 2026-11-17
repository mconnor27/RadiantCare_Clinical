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

    # In main callback, read the selection from the store and pass it to
    # utils.diagnosis_categories.filter_by_diagnosis (which decodes it):
    Input("cv-diag-store", "data")

The store holds checked category names plus "Category::Subcategory" entries
for selected subcategory chips. A subcategory pick implies its category and
narrows that category to the picked subcategories; categories with no picks
match whole. Use split_diagnosis_selection() to decode it elsewhere.

Generated IDs (all prefixed with page_id):
    {page_id}-diag-trigger      Button (trigger)
    {page_id}-diag-clear        ActionIcon (clear)
    {page_id}-diag-store        dcc.Store (selection: categories + Cat::Sub pairs)
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

from utils.diagnosis_categories import CATEGORIES, SUBCATEGORIES, SUBCAT_SEP


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
                                                            [dmc.Chip(s, value=f"{cat}{SUBCAT_SEP}{s}",
                                                                      size="xs", variant="outline")
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

    # Mode toggle → store sync. Only propagate when a diagnosis selection is
    # active — with nothing selected the mode has no effect on filtering, and
    # writing the store would needlessly rerun every page callback. Categories/
    # subcategories are Inputs so the store re-syncs when a selection is made.
    clientside_callback(
        """function(val, cats, subs) {
            var has = (cats && cats.length > 0) || (subs && subs.length > 0);
            if (!has) return window.dash_clientside.no_update;
            return val;
        }""",
        Output(mode_store_id, "data"),
        Input(mode_ctrl_id, "value"),
        Input(store_id, "data"),
        Input(subcat_id, "value"),
    )

    # Checkboxes + subcategory chips → Store sync. Unchecking a category also
    # drops its subcategory picks (same callback, so no circular chain).
    @callback(
        Output(store_id, "data"),
        Output(subcat_id, "value", allow_duplicate=True),
        Input({"type": cat_type, "index": ALL}, "checked"),
        Input(subcat_id, "value"),
        State(store_id, "data"),
        prevent_initial_call=True,
    )
    def _sync_selection(checked_list, subs, prev):
        checked = [cat for cat, c in zip(CATEGORIES, checked_list) if c]
        subs = list(subs or [])
        subs_out = dash.no_update
        if isinstance(dash.ctx.triggered_id, dict):
            prev_checked = {v for v in (prev or []) if SUBCAT_SEP not in v}
            unchecked = prev_checked - set(checked)
            if unchecked:
                kept = [s for s in subs if s.split(SUBCAT_SEP, 1)[0] not in unchecked]
                if kept != subs:
                    subs, subs_out = kept, kept
        selection = checked + subs
        if selection == (prev or []):
            return dash.no_update, subs_out
        return selection, subs_out

    # Trigger label
    clientside_callback(
        """function(sel, subs) {
            var sep = "%s";
            var items = sel || [];
            var picks = items.filter(function (v) { return v.indexOf(sep) >= 0; });
            var cats = items.filter(function (v) { return v.indexOf(sep) < 0; });
            if (items.length === 0) return "Diagnosis";
            // A category with subcategory picks is narrowed to those picks,
            // so it isn't counted on its own.
            var narrowed = {};
            picks.forEach(function (p) { narrowed[p.split(sep)[0]] = true; });
            var whole = cats.filter(function (c) { return !narrowed[c]; });
            var n = picks.length + whole.length;
            if (n === 1) return picks.length ? picks[0].split(sep)[1] : whole[0];
            return n + " selected";
        }""" % SUBCAT_SEP,
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
