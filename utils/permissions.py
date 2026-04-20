"""Role-based UI/API gating for the Clinical app.

These helpers read the current user's role from the Flask session (which is
populated by ``auth.py`` at login from ``clinical.profiles.role``).

Usage:
    from utils.permissions import is_admin, can_see_money

    if not can_see_money():
        return html.Div("—")

In a Dash callback, ``flask.has_request_context()`` is True and we can read
the session. Outside of a request (module import time, startup), these
helpers return False so defaults are conservative.
"""

from __future__ import annotations

from typing import Optional

from flask import has_request_context, session

from data.profiles_db import role_allows


def current_role() -> Optional[str]:
    """Role of the current authenticated user, or None when unauthenticated."""
    if not has_request_context():
        return None
    return session.get("role")


def is_admin() -> bool:
    """Admin: full access — sees dollar amounts, wRVU, manager modals."""
    return role_allows(current_role(), "admin")


def is_partner_or_above() -> bool:
    """Partner+: can see professional dollar amounts and wRVU."""
    return role_allows(current_role(), "partner")


def can_see_money() -> bool:
    """All dollar amounts (professional, hospital, total) — partners+ only."""
    return is_partner_or_above()


def can_see_professional_rvu() -> bool:
    """Professional (work) RVUs — partners+ only."""
    return is_partner_or_above()


def can_see_manager_modals() -> bool:
    """Manager modals (insurance rates, referring physicians, diagnosis
    taxonomy) — admins only."""
    return is_admin()
