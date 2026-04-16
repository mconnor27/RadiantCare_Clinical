"""Reusable CPT code accordion filter component for the billing page.

Provides a dropdown panel with:
- Checkbox per category (selects/deselects all codes in category)
- Accordion expand per category to reveal subcategories
- Subcategory headings that select all codes within the subcategory
- Individual CPT code chips (display code, tooltip shows description)

Usage:
    from components.cpt_filter import cpt_accordion, register_cpt_callbacks

    # In layout:
    cpt_accordion("billing")

    # After layout:
    register_cpt_callbacks("billing")

    # In main callback, read selected categories:
    Input("billing-cpt-store", "data")        # list of selected category names
    Input("billing-cpt-code-store", "data")   # list of selected individual codes

Generated IDs (all prefixed with page_id):
    {page_id}-cpt-trigger       Button (trigger)
    {page_id}-cpt-clear         ActionIcon (clear)
    {page_id}-cpt-store         dcc.Store (selected category names)
    {page_id}-cpt-code-store    dcc.Store (selected individual CPT codes)
    {page_id}-cpt-panel         Paper (dropdown panel)
    {page_id}-cpt-accordion     Accordion (expand/collapse)
    {"type": "cpt-cat-{page_id}", "index": i}    Category checkboxes
    {"type": "cpt-sub-{page_id}", "index": "cat|sub"}  Subcategory checkboxes
"""

from __future__ import annotations

import dash
import dash_mantine_components as dmc
from dash import ALL, Input, Output, State, callback, clientside_callback, dcc, html
from dash_iconify import DashIconify

from utils.cpt_categories import (
    CPT_SUBCATEGORIES, CPT_DESCRIPTIONS, CATEGORY_NAMES,
    CPT_CATEGORIES, codes_for_categories,
)

# Categories that appear in the accordion (exclude "Other" — it's a catch-all)
_ACCORDION_CATS = [c for c in CATEGORY_NAMES if c != "Other"]


def cpt_accordion(page_id: str) -> html.Div:
    """Return the CPT accordion filter widget for a page."""
    cat_type = f"cpt-cat-{page_id}"
    sub_type = f"cpt-sub-{page_id}"

    accordion_items = []
    for i, cat in enumerate(_ACCORDION_CATS):
        subs = CPT_SUBCATEGORIES.get(cat, {})
        # Build subcategory sections
        sub_sections = []
        for sub_name, codes in subs.items():
            sub_key = f"{cat}|{sub_name}"
            # Subcategory heading with checkbox
            heading = html.Div(
                children=[
                    dmc.Checkbox(
                        id={"type": sub_type, "index": sub_key},
                        label=sub_name,
                        size="xs",
                        className="wf-cpt-sub-check",
                    ),
                ],
                className="wf-cpt-sub-heading",
            )
            # Individual code chips with tooltips
            code_chips = html.Div(
                children=[
                    dmc.Tooltip(
                        label=CPT_DESCRIPTIONS.get(code, code),
                        position="top",
                        withArrow=True,
                        children=dmc.Chip(
                            code, value=f"{cat}|{sub_name}|{code}",
                            size="xs", variant="outline",
                        ),
                    )
                    for code in codes
                ],
                className="wf-cpt-code-chip-list",
            )
            sub_sections.append(html.Div([heading, code_chips], className="wf-cpt-sub-section"))

        accordion_items.append(
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
                        dmc.ChipGroup(
                            children=sub_sections,
                            id={"type": f"cpt-chips-{page_id}", "index": i},
                            multiple=True,
                            value=[],
                        ),
                    ),
                ],
                value=cat,
            )
        )

    return html.Div(
        children=[
            html.Div(
                children=[
                    dmc.Button(
                        "Category",
                        id=f"{page_id}-cpt-trigger",
                        variant="default",
                        size="sm",
                        rightSection=DashIconify(icon="mdi:chevron-down", width=14),
                    ),
                    dmc.ActionIcon(
                        DashIconify(icon="mdi:close-circle", width=18),
                        id=f"{page_id}-cpt-clear",
                        variant="subtle",
                        color="gray",
                        size="sm",
                        className="wf-filter-clear-btn",
                    ),
                ],
                style={"position": "relative", "display": "inline-block"},
            ),
            # Stores
            dcc.Store(id=f"{page_id}-cpt-store", data=[]),          # selected category names
            dcc.Store(id=f"{page_id}-cpt-code-store", data=[]),     # selected individual codes
            dmc.Paper(
                children=[
                    html.Div(
                        children=[
                            dmc.Accordion(
                                children=accordion_items,
                                multiple=True,
                                id=f"{page_id}-cpt-accordion",
                                value=[],
                                variant="contained",
                                chevronPosition="right",
                            ),
                        ],
                        className="wf-diag-scroll",
                    ),
                ],
                id=f"{page_id}-cpt-panel",
                p="xs",
                shadow="md",
                withBorder=True,
                radius="md",
                className="wf-chip-dropdown wf-cpt-panel",
                style={"display": "none"},
            ),
        ],
        style={"position": "relative", "display": "inline-block"},
    )


def register_cpt_callbacks(page_id: str) -> None:
    """Register all callbacks for the CPT accordion filter."""
    cat_type = f"cpt-cat-{page_id}"
    sub_type = f"cpt-sub-{page_id}"
    chips_type = f"cpt-chips-{page_id}"
    store_id = f"{page_id}-cpt-store"
    code_store_id = f"{page_id}-cpt-code-store"
    accordion_id = f"{page_id}-cpt-accordion"
    trigger_id = f"{page_id}-cpt-trigger"
    clear_id = f"{page_id}-cpt-clear"
    n_cats = len(_ACCORDION_CATS)

    # Build subcategory index for callbacks
    all_sub_keys = []  # "Cat|Sub" keys in order
    sub_to_codes: dict[str, list[str]] = {}  # "Cat|Sub" → [codes]
    for cat in _ACCORDION_CATS:
        for sub_name, codes in CPT_SUBCATEGORIES.get(cat, {}).items():
            key = f"{cat}|{sub_name}"
            all_sub_keys.append(key)
            sub_to_codes[key] = codes

    # -----------------------------------------------------------------------
    # 1. Category checkbox → select all subcategories + codes in that category
    # -----------------------------------------------------------------------
    @callback(
        Output(store_id, "data"),
        Output(code_store_id, "data"),
        Output({"type": sub_type, "index": ALL}, "checked"),
        Output({"type": chips_type, "index": ALL}, "value"),
        Input({"type": cat_type, "index": ALL}, "checked"),
        State(store_id, "data"),
        State(code_store_id, "data"),
        State({"type": sub_type, "index": ALL}, "checked"),
        State({"type": sub_type, "index": ALL}, "id"),
        State({"type": chips_type, "index": ALL}, "value"),
        State({"type": chips_type, "index": ALL}, "id"),
        prevent_initial_call=True,
    )
    def _sync_cat_checkboxes(
        cat_checked_list,
        current_cats, current_codes,
        sub_checked_list, sub_ids,
        chip_values_list, chip_ids,
    ):
        from dash import ctx
        triggered = ctx.triggered_id
        if not triggered or not isinstance(triggered, dict):
            return dash.no_update, dash.no_update, \
                [dash.no_update] * len(sub_ids), [dash.no_update] * len(chip_ids)

        cat_idx = triggered["index"]
        cat_name = _ACCORDION_CATS[cat_idx]
        is_checked = cat_checked_list[cat_idx]

        # Update categories list
        new_cats = list(current_cats or [])
        if is_checked and cat_name not in new_cats:
            new_cats.append(cat_name)
        elif not is_checked and cat_name in new_cats:
            new_cats.remove(cat_name)

        # Update individual codes
        new_codes = set(current_codes or [])
        cat_codes = CPT_CATEGORIES.get(cat_name, set())
        if is_checked:
            new_codes.update(cat_codes)
        else:
            new_codes -= cat_codes

        # Update subcategory checkboxes for this category
        new_sub_checked = list(sub_checked_list)
        for j, sid in enumerate(sub_ids):
            sub_key = sid["index"]
            if sub_key.startswith(f"{cat_name}|"):
                new_sub_checked[j] = is_checked

        # Update chip group values for this category
        new_chip_values = [list(v) for v in chip_values_list]
        for j, cid in enumerate(chip_ids):
            if cid["index"] == cat_idx:
                if is_checked:
                    # Select all chip values in this category
                    all_vals = []
                    for sub_name, codes in CPT_SUBCATEGORIES.get(cat_name, {}).items():
                        for code in codes:
                            all_vals.append(f"{cat_name}|{sub_name}|{code}")
                    new_chip_values[j] = all_vals
                else:
                    new_chip_values[j] = []

        return new_cats, sorted(new_codes), new_sub_checked, new_chip_values

    # -----------------------------------------------------------------------
    # 2. Subcategory checkbox → select all codes in that subcategory
    # -----------------------------------------------------------------------
    @callback(
        Output(code_store_id, "data", allow_duplicate=True),
        Output({"type": chips_type, "index": ALL}, "value", allow_duplicate=True),
        Input({"type": sub_type, "index": ALL}, "checked"),
        State({"type": sub_type, "index": ALL}, "id"),
        State(code_store_id, "data"),
        State({"type": chips_type, "index": ALL}, "value"),
        State({"type": chips_type, "index": ALL}, "id"),
        prevent_initial_call=True,
    )
    def _sync_sub_checkboxes(
        sub_checked_list, sub_ids,
        current_codes,
        chip_values_list, chip_ids,
    ):
        from dash import ctx
        triggered = ctx.triggered_id
        if not triggered or not isinstance(triggered, dict):
            return dash.no_update, [dash.no_update] * len(chip_ids)

        sub_key = triggered["index"]  # "Cat|Sub"
        parts = sub_key.split("|", 1)
        if len(parts) != 2:
            return dash.no_update, [dash.no_update] * len(chip_ids)
        cat_name, sub_name = parts

        # Find which subcategory was toggled
        is_checked = None
        for j, sid in enumerate(sub_ids):
            if sid["index"] == sub_key:
                is_checked = sub_checked_list[j]
                break
        if is_checked is None:
            return dash.no_update, [dash.no_update] * len(chip_ids)

        codes_in_sub = sub_to_codes.get(sub_key, [])
        new_codes = set(current_codes or [])
        if is_checked:
            new_codes.update(codes_in_sub)
        else:
            new_codes -= set(codes_in_sub)

        # Update chip group values for the category containing this subcategory
        cat_idx = _ACCORDION_CATS.index(cat_name) if cat_name in _ACCORDION_CATS else -1
        new_chip_values = [dash.no_update] * len(chip_ids)
        for j, cid in enumerate(chip_ids):
            if cid["index"] == cat_idx:
                current_vals = set(chip_values_list[j] or [])
                chip_vals_for_sub = {f"{cat_name}|{sub_name}|{c}" for c in codes_in_sub}
                if is_checked:
                    current_vals.update(chip_vals_for_sub)
                else:
                    current_vals -= chip_vals_for_sub
                new_chip_values[j] = sorted(current_vals)

        return sorted(new_codes), new_chip_values

    # -----------------------------------------------------------------------
    # 3. Individual code chip toggle → update code store + sync sub checkbox
    # -----------------------------------------------------------------------
    @callback(
        Output(code_store_id, "data", allow_duplicate=True),
        Output({"type": sub_type, "index": ALL}, "checked", allow_duplicate=True),
        Output(store_id, "data", allow_duplicate=True),
        Output({"type": cat_type, "index": ALL}, "checked", allow_duplicate=True),
        Input({"type": chips_type, "index": ALL}, "value"),
        State({"type": chips_type, "index": ALL}, "id"),
        State({"type": sub_type, "index": ALL}, "id"),
        prevent_initial_call=True,
    )
    def _sync_code_chips(chip_values_list, chip_ids, sub_ids):
        # Collect all selected code values across all chip groups
        all_selected_codes = set()
        for vals in chip_values_list:
            for v in (vals or []):
                # Value format: "Cat|Sub|Code"
                parts = v.split("|", 2)
                if len(parts) == 3:
                    all_selected_codes.add(parts[2])

        # Determine which subcategories are fully selected
        new_sub_checked = []
        for sid in sub_ids:
            sub_key = sid["index"]  # "Cat|Sub"
            codes_in_sub = sub_to_codes.get(sub_key, [])
            all_selected = len(codes_in_sub) > 0 and all(c in all_selected_codes for c in codes_in_sub)
            new_sub_checked.append(all_selected)

        # Determine which categories are fully selected
        new_cats = []
        new_cat_checked = []
        for i, cat in enumerate(_ACCORDION_CATS):
            cat_codes = CPT_CATEGORIES.get(cat, set())
            all_selected = len(cat_codes) > 0 and all(c in all_selected_codes for c in cat_codes)
            new_cat_checked.append(all_selected)
            if all_selected:
                new_cats.append(cat)

        return sorted(all_selected_codes), new_sub_checked, new_cats, new_cat_checked

    # -----------------------------------------------------------------------
    # 4. Trigger label update
    # -----------------------------------------------------------------------
    clientside_callback(
        """function(cats, codes) {
            var nc = cats ? cats.length : 0;
            var nk = codes ? codes.length : 0;
            if (nc === 0 && nk === 0) return "Category";
            if (nc > 0 && nk === 0) {
                return nc === 1 ? cats[0] : nc + " categories";
            }
            if (nc === 1 && nk > 0) return cats[0];
            if (nc > 1) return nc + " categories";
            return nk + " codes";
        }""",
        Output(trigger_id, "children"),
        Input(store_id, "data"),
        Input(code_store_id, "data"),
    )

    # -----------------------------------------------------------------------
    # 5. Clear-button visibility
    # -----------------------------------------------------------------------
    clientside_callback(
        """function(cats, codes) {
            var has = (cats && cats.length > 0) || (codes && codes.length > 0);
            return has ? {"display": "inline-flex"} : {"display": "none"};
        }""",
        Output(clear_id, "style"),
        Input(store_id, "data"),
        Input(code_store_id, "data"),
    )

    # -----------------------------------------------------------------------
    # 6. Clear-button action
    # -----------------------------------------------------------------------
    cat_check_outputs = [
        Output({"type": cat_type, "index": i}, "checked", allow_duplicate=True)
        for i in range(n_cats)
    ]
    sub_check_outputs = [
        Output({"type": sub_type, "index": key}, "checked", allow_duplicate=True)
        for key in all_sub_keys
    ]
    chip_group_outputs = [
        Output({"type": chips_type, "index": i}, "value", allow_duplicate=True)
        for i in range(n_cats)
    ]

    n_subs = len(all_sub_keys)
    clientside_callback(
        f"""function(n) {{
            var r = [[], [], []];
            for (var i = 0; i < {n_cats}; i++) r.push(false);
            for (var i = 0; i < {n_subs}; i++) r.push(false);
            for (var i = 0; i < {n_cats}; i++) r.push([]);
            return r;
        }}""",
        Output(store_id, "data", allow_duplicate=True),
        Output(code_store_id, "data", allow_duplicate=True),
        Output(accordion_id, "value", allow_duplicate=True),
        *cat_check_outputs,
        *sub_check_outputs,
        *chip_group_outputs,
        Input(clear_id, "n_clicks"),
        prevent_initial_call=True,
    )
