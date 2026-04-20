"""Admin-only page: manage Clinical user roles.

Lists all rows in ``clinical.profiles`` with a role dropdown. Admins can
change role, add a new user (by email), or delete a profile. Non-admins
who somehow reach ``/admin/users`` see a 403 card instead of the table.
"""

from __future__ import annotations

import dash
import dash_mantine_components as dmc
import dash_ag_grid as dag
from dash import callback, Input, Output, State, html, no_update
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


def layout():
    if not is_admin():
        return _access_denied()

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
                        justify="space-between",
                        align="center",
                        mt=12,
                        children=[
                            dmc.Group(
                                gap="xs",
                                children=[
                                    dmc.TextInput(
                                        id=f"{PAGE_ID}-new-email",
                                        placeholder="email@radiantcare.com",
                                        w=260,
                                    ),
                                    dmc.TextInput(
                                        id=f"{PAGE_ID}-new-name",
                                        placeholder="Display name (optional)",
                                        w=220,
                                    ),
                                    dmc.Select(
                                        id=f"{PAGE_ID}-new-role",
                                        data=[
                                            {"value": r, "label": r.capitalize()}
                                            for r in VALID_ROLES
                                        ],
                                        value="user",
                                        w=140,
                                    ),
                                    dmc.Button(
                                        "Add user",
                                        id=f"{PAGE_ID}-add-btn",
                                        leftSection=DashIconify(icon="tabler:user-plus", width=16),
                                        color="violet",
                                    ),
                                ],
                            ),
                            html.Div(id=f"{PAGE_ID}-status", style={"minHeight": 24}),
                        ],
                    ),
                ],
            ),
            dmc.Paper(
                p=0, radius="md", shadow="xs", withBorder=True,
                children=dag.AgGrid(
                    id=f"{PAGE_ID}-grid",
                    rowData=_rows(),
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
                        "Note: adding a profile here doesn't create a Clerk "
                        "account — invite the user via the Clerk dashboard "
                        "first. Clerk ID auto-populates on their first login.",
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
    Output(f"{PAGE_ID}-grid", "rowData"),
    Output(f"{PAGE_ID}-status", "children"),
    Output(f"{PAGE_ID}-new-email", "value"),
    Output(f"{PAGE_ID}-new-name", "value"),
    Input(f"{PAGE_ID}-add-btn", "n_clicks"),
    State(f"{PAGE_ID}-new-email", "value"),
    State(f"{PAGE_ID}-new-name", "value"),
    State(f"{PAGE_ID}-new-role", "value"),
    prevent_initial_call=True,
)
def _add_user(n, email, name, role):
    if not n or not is_admin():
        return no_update, no_update, no_update, no_update
    email = (email or "").strip().lower()
    if not email or "@" not in email:
        return no_update, dmc.Text("Enter a valid email", c="red", size="xs"), no_update, no_update
    if role not in VALID_ROLES:
        return no_update, dmc.Text("Invalid role", c="red", size="xs"), no_update, no_update
    try:
        upsert_profile(email, role=role, display_name=(name or None))
    except Exception as exc:
        return no_update, dmc.Text(f"Error: {exc}", c="red", size="xs"), no_update, no_update
    return (
        _rows(),
        dmc.Text(f"Added {email} as {role}", c="green", size="xs"),
        "",
        "",
    )


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
