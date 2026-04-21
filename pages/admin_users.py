"""Admin-only page: manage Clinical user roles.

Lists all rows in ``clinical.profiles`` with a role dropdown. Admins can
change role or delete a profile. New users are provisioned from the
radiantcare-landing app — this page is read/edit only. Non-admins who
somehow reach ``/admin/users`` see a 403 card instead of the table.
"""

from __future__ import annotations

import dash
import dash_mantine_components as dmc
import dash_ag_grid as dag
from dash import ALL, MATCH, callback, ctx, Input, Output, State, html, no_update
from dash_iconify import DashIconify

from config.settings import PRIMARY, NEUTRAL, SEMANTIC_COLORS, DEFAULT_GRID_CLASS
from data.profiles_db import (
    VALID_ROLES,
    delete_profile,
    get_profile,
    list_profiles,
    set_role,
    upsert_profile,
)
from utils.permissions import is_admin


dash.register_page(
    __name__,
    path="/admin/users",
    name="Users",
    order=99,
    icon="tabler:users",
)

PAGE_ID = "admin-users"


def _rows() -> list[dict]:
    return [
        {
            "email": p["email"],
            "display_name": p.get("display_name") or "",
            "role": p["role"],
            "clerk_user_id": p.get("clerk_user_id") or "",
            "updated_at": p.get("updated_at") or "",
        }
        for p in list_profiles()
    ]


_ROLE_DESCRIPTIONS = {
    "admin": "Full access — sees everything, can open manager modals.",
    "partner": "Can see professional revenue ($) and wRVU.",
    "user": "Access to most pages; dollar amounts and professional RVU hidden.",
}


def _access_denied():
    return dmc.Center(
        dmc.Paper(
            dmc.Stack(
                children=[
                    DashIconify(icon="tabler:lock", width=48, color=PRIMARY),
                    dmc.Title("Access denied", order=3, c=PRIMARY),
                    dmc.Text(
                        "User management is restricted to admins.",
                        c=NEUTRAL["text_secondary"],
                    ),
                ],
                align="center",
                gap="md",
            ),
            p=40, radius="md", shadow="sm", withBorder=True, maw=420,
        ),
        h="60vh",
    )


def _mobile_user_card(row):
    email = row["email"]
    return dmc.Paper(
        p="sm", radius="md", withBorder=True,
        children=dmc.Stack(gap=8, children=[
            dmc.Group(justify="space-between", align="flex-start", wrap="nowrap", children=[
                dmc.Stack(gap=2, style={"flex": 1, "minWidth": 0}, children=[
                    dmc.Text(
                        row.get("display_name") or email,
                        fw=600, size="sm",
                        style={"overflow": "hidden", "textOverflow": "ellipsis", "whiteSpace": "nowrap"},
                    ),
                    dmc.Text(
                        email, size="xs", c="dimmed",
                        style={"overflow": "hidden", "textOverflow": "ellipsis", "whiteSpace": "nowrap"},
                    ),
                ]),
                dmc.ActionIcon(
                    DashIconify(icon="tabler:trash", width=16),
                    id={"type": "admin-users-mobile-delete", "email": email},
                    color="red", variant="subtle", size="lg",
                ),
            ]),
            dmc.Select(
                id={"type": "admin-users-mobile-role", "email": email},
                data=[{"value": r, "label": r.capitalize()} for r in VALID_ROLES],
                value=row["role"],
                size="sm",
                label="Role",
                clearable=False,
                allowDeselect=False,
            ),
        ]),
    )


def _mobile_cards(rows):
    if not rows:
        return dmc.Text("No users.", c="dimmed", size="sm", ta="center", py="md")
    return dmc.Stack(gap=10, children=[_mobile_user_card(r) for r in rows])


def layout():
    if not is_admin():
        return _access_denied()

    rows = _rows()

    return dmc.Stack(
        gap=16,
        className="page-content",
        children=[
            dmc.Box(
                className="page-sticky-header",
                children=[
                    dmc.Group(
                        justify="center", align="center",
                        children=[
                            dmc.Title("User management", order=2, className="page-title"),
                        ],
                    ),
                    dmc.Group(
                        justify="flex-end",
                        align="center",
                        mt=12,
                        children=[
                            html.Div(id=f"{PAGE_ID}-status", style={"minHeight": 24}),
                        ],
                    ),
                ],
            ),
            # Desktop: AG Grid
            html.Div(
                className="hide-on-mobile",
                children=dmc.Paper(
                    p=0, radius="md", shadow="xs", withBorder=True,
                    children=dag.AgGrid(
                        id=f"{PAGE_ID}-grid",
                        rowData=rows,
                        columnDefs=[
                            {"field": "email", "headerName": "Email", "flex": 2},
                            {"field": "display_name", "headerName": "Name", "flex": 2, "editable": True},
                            {
                                "field": "role",
                                "headerName": "Role",
                                "flex": 1,
                                "editable": True,
                                "cellEditor": "agSelectCellEditor",
                                "cellEditorParams": {"values": list(VALID_ROLES)},
                            },
                            {"field": "clerk_user_id", "headerName": "Clerk ID", "flex": 2},
                            {"field": "updated_at", "headerName": "Updated", "flex": 2},
                            {
                                "colId": "_delete",
                                "headerName": "",
                                "width": 60,
                                "valueGetter": {"function": "'✖'"},
                                "cellStyle": {
                                    "color": SEMANTIC_COLORS["error"],
                                    "textAlign": "center",
                                    "cursor": "pointer",
                                },
                                "sortable": False,
                                "filter": False,
                            },
                        ],
                        defaultColDef={"sortable": True, "filter": True, "resizable": True},
                        dashGridOptions={"animateRows": True, "rowHeight": 36, "headerHeight": 36},
                        className=DEFAULT_GRID_CLASS,
                        style={"height": "60vh", "width": "100%"},
                    ),
                ),
            ),
            # Mobile: card list
            html.Div(
                id=f"{PAGE_ID}-mobile-list",
                className="show-only-mobile",
                children=_mobile_cards(rows),
            ),
            dmc.Stack(
                gap=4,
                mt=8,
                children=[
                    dmc.Text(
                        "Role definitions:",
                        size="sm",
                        fw=600,
                        c=NEUTRAL["text_secondary"],
                    ),
                    *[
                        dmc.Text(
                            f"• {role.capitalize()} — {desc}",
                            size="xs",
                            c=NEUTRAL["text_secondary"],
                        )
                        for role, desc in _ROLE_DESCRIPTIONS.items()
                    ],
                    dmc.Text(
                        "Note: new users are provisioned from the "
                        "radiantcare-landing app. This page edits roles "
                        "and deletes existing profiles only.",
                        size="xs",
                        c=NEUTRAL["text_secondary"],
                        mt=6,
                    ),
                ],
            ),
        ],
    )


# ---------------------------------------------------------------------------
# Callbacks
# ---------------------------------------------------------------------------

@callback(
    Output(f"{PAGE_ID}-grid", "rowData", allow_duplicate=True),
    Output(f"{PAGE_ID}-status", "children", allow_duplicate=True),
    Input(f"{PAGE_ID}-grid", "cellValueChanged"),
    prevent_initial_call=True,
)
def _edit_cell(change):
    if not change or not is_admin():
        return no_update, no_update
    # change is a list of events; take the first
    ev = change[0] if isinstance(change, list) else change
    data = ev.get("data") or {}
    field = ev.get("colId") or ev.get("column")
    email = data.get("email")
    if not email:
        return no_update, no_update
    try:
        if field == "role":
            set_role(email, data.get("role"))
        elif field == "display_name":
            existing = get_profile(email) or {}
            upsert_profile(
                email,
                role=existing.get("role", "user"),
                display_name=data.get("display_name") or None,
                clerk_user_id=existing.get("clerk_user_id"),
            )
    except Exception as exc:
        return _rows(), dmc.Text(f"Error: {exc}", c="red", size="xs")
    return _rows(), dmc.Text(f"Saved {email}", c="green", size="xs")


@callback(
    Output(f"{PAGE_ID}-grid", "rowData", allow_duplicate=True),
    Output(f"{PAGE_ID}-status", "children", allow_duplicate=True),
    Input(f"{PAGE_ID}-grid", "cellClicked"),
    prevent_initial_call=True,
)
def _click_cell(click):
    if not click or not is_admin():
        return no_update, no_update
    if click.get("colId") != "_delete":
        return no_update, no_update
    email = (click.get("data") or {}).get("email")
    if not email:
        return no_update, no_update
    try:
        delete_profile(email)
    except Exception as exc:
        return no_update, dmc.Text(f"Error: {exc}", c="red", size="xs")
    return _rows(), dmc.Text(f"Deleted {email}", c="orange", size="xs")


# ---------------------------------------------------------------------------
# Mobile callbacks — pattern-matched per-email card controls
# ---------------------------------------------------------------------------

@callback(
    Output(f"{PAGE_ID}-mobile-list", "children", allow_duplicate=True),
    Output(f"{PAGE_ID}-grid", "rowData", allow_duplicate=True),
    Output(f"{PAGE_ID}-status", "children", allow_duplicate=True),
    Input({"type": "admin-users-mobile-role", "email": ALL}, "value"),
    State({"type": "admin-users-mobile-role", "email": ALL}, "id"),
    prevent_initial_call=True,
)
def _mobile_role_change(values, ids):
    if not is_admin() or not ctx.triggered_id:
        return no_update, no_update, no_update
    email = ctx.triggered_id.get("email")
    # Find the new value for this email
    new_role = None
    for v, i in zip(values, ids):
        if i.get("email") == email:
            new_role = v
            break
    if not email or not new_role or new_role not in VALID_ROLES:
        return no_update, no_update, no_update
    try:
        set_role(email, new_role)
    except Exception as exc:
        return no_update, no_update, dmc.Text(f"Error: {exc}", c="red", size="xs")
    rows = _rows()
    return _mobile_cards(rows), rows, dmc.Text(f"Saved {email}", c="green", size="xs")


@callback(
    Output(f"{PAGE_ID}-mobile-list", "children", allow_duplicate=True),
    Output(f"{PAGE_ID}-grid", "rowData", allow_duplicate=True),
    Output(f"{PAGE_ID}-status", "children", allow_duplicate=True),
    Input({"type": "admin-users-mobile-delete", "email": ALL}, "n_clicks"),
    prevent_initial_call=True,
)
def _mobile_delete(n_clicks_list):
    if not is_admin() or not ctx.triggered_id:
        return no_update, no_update, no_update
    # Ignore if triggered with no actual click (initial render of new components)
    if not any(n_clicks_list or []):
        return no_update, no_update, no_update
    email = ctx.triggered_id.get("email")
    if not email:
        return no_update, no_update, no_update
    try:
        delete_profile(email)
    except Exception as exc:
        return no_update, no_update, dmc.Text(f"Error: {exc}", c="red", size="xs")
    rows = _rows()
    return _mobile_cards(rows), rows, dmc.Text(f"Deleted {email}", c="orange", size="xs")
