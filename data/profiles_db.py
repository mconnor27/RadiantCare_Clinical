"""Clinical profile & role CRUD.

Lives on the same dual-dialect wrapper as ``reviews_db`` — SQLite for local
dev, Postgres (``clinical.profiles``) in production.

Role tiers (hierarchical, higher inherits lower):
  - ``admin``    — full access, sees manager modals
  - ``partner``  — can see professional revenue / wRVU data
  - ``user``     — everything except dollar amounts and professional RVUs
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from data.reviews_db import _connect  # shared dialect-aware connection


# Hierarchy: higher-role list includes itself and all lower.
_ROLE_RANK = {"user": 0, "partner": 1, "admin": 2}
VALID_ROLES = tuple(_ROLE_RANK.keys())


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_table() -> None:
    """Create the profiles table on first import (SQLite fallback)."""
    with _connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS profiles (
                email          TEXT PRIMARY KEY,
                clerk_user_id  TEXT,
                display_name   TEXT,
                role           TEXT NOT NULL DEFAULT 'user',
                created_at     TEXT NOT NULL,
                updated_at     TEXT NOT NULL
            );
            """
        )


_ensure_table()


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------

def get_profile(email: str) -> Optional[dict]:
    """Return the profile row for ``email`` (case-insensitive), or None."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT email, clerk_user_id, display_name, role, "
            "created_at, updated_at FROM profiles WHERE lower(email) = ?",
            (email.strip().lower(),),
        ).fetchone()
    return dict(row) if row else None


def list_profiles() -> list[dict]:
    """Return all profiles, ordered by role (admins first) then email."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT email, clerk_user_id, display_name, role, "
            "created_at, updated_at FROM profiles ORDER BY "
            "CASE role WHEN 'admin' THEN 0 WHEN 'partner' THEN 1 ELSE 2 END, email"
        ).fetchall()
    return [dict(r) for r in rows]


def role_allows(user_role: Optional[str], required: str) -> bool:
    """True if ``user_role`` ranks at or above ``required``."""
    if not user_role or required not in _ROLE_RANK:
        return False
    return _ROLE_RANK.get(user_role, -1) >= _ROLE_RANK[required]


# ---------------------------------------------------------------------------
# Writes (admin-only caller is responsible for enforcing)
# ---------------------------------------------------------------------------

def upsert_profile(
    email: str,
    *,
    role: str = "user",
    display_name: Optional[str] = None,
    clerk_user_id: Optional[str] = None,
) -> None:
    """Insert or update a profile by email."""
    if role not in VALID_ROLES:
        raise ValueError(f"invalid role: {role!r} (expected one of {VALID_ROLES})")
    now = _now()
    with _connect() as conn:
        conn.execute(
            """INSERT INTO profiles
                 (email, clerk_user_id, display_name, role, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(email) DO UPDATE SET
                   clerk_user_id = COALESCE(excluded.clerk_user_id, profiles.clerk_user_id),
                   display_name  = COALESCE(excluded.display_name,  profiles.display_name),
                   role          = excluded.role,
                   updated_at    = excluded.updated_at""",
            (email.strip().lower(), clerk_user_id, display_name, role, now, now),
        )


def set_role(email: str, role: str) -> None:
    """Shortcut: change just the role for an existing profile."""
    if role not in VALID_ROLES:
        raise ValueError(f"invalid role: {role!r}")
    with _connect() as conn:
        conn.execute(
            "UPDATE profiles SET role = ?, updated_at = ? WHERE lower(email) = ?",
            (role, _now(), email.strip().lower()),
        )


def delete_profile(email: str) -> None:
    """Remove a profile row. (Does not touch Clerk — use the Clerk dashboard
    if you also want to revoke the underlying Clerk account.)"""
    with _connect() as conn:
        conn.execute("DELETE FROM profiles WHERE lower(email) = ?", (email.strip().lower(),))
