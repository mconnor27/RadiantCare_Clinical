"""Shared primitives for PHI sanitization.

Used by data/sanitize/rules.py (build-time), scripts/sanitize.py (entry point),
and scripts/lookup_patient.py (reverse lookup from PatientCode to real MRN).

Hashing is deterministic given the same PHI_SALT, so a given PatientId always
produces the same hashed output across datasets — preserving join integrity.
The salt must never be committed or deployed to the cloud host.
"""

from __future__ import annotations

import hashlib
import os
from typing import Iterable

import pandas as pd


def load_salt() -> str:
    """Return PHI_SALT from the environment. Fails loudly if missing."""
    salt = os.environ.get("PHI_SALT", "").strip()
    if not salt:
        raise RuntimeError(
            "PHI_SALT environment variable is not set. "
            "Set it to a long random string (e.g., `openssl rand -hex 32`) "
            "before running sanitization or reverse-lookup."
        )
    if len(salt) < 16:
        raise RuntimeError(
            "PHI_SALT is too short (<16 chars). Use at least 32 hex chars "
            "for meaningful protection."
        )
    return salt


def _hash_hex(value: str, salt: str) -> str:
    """Return SHA256(value + salt) as lowercase hex."""
    h = hashlib.sha256()
    h.update(value.encode("utf-8"))
    h.update(b"|")
    h.update(salt.encode("utf-8"))
    return h.hexdigest()


def hash_patient_id(pid, salt: str) -> str | float:
    """Return 'PAT_' + 16 hex chars. Deterministic; stable across datasets.

    Returns pandas NA for null/empty input so joins remain correct.
    """
    if pid is None or (isinstance(pid, float) and pd.isna(pid)):
        return pd.NA
    s = str(pid).strip()
    if not s or s.lower() in ("nan", "none", "<na>"):
        return pd.NA
    return "PAT_" + _hash_hex(s, salt)[:16].upper()


def short_patient_code(pid, salt: str) -> str | float:
    """Return a 6-char hex pseudonym (uppercase). Used in CPT Audit / OTV Audit
    grids where the user needs to trace audit rows back to real patients via
    scripts/lookup_patient.py.
    """
    if pid is None or (isinstance(pid, float) and pd.isna(pid)):
        return pd.NA
    s = str(pid).strip()
    if not s or s.lower() in ("nan", "none", "<na>"):
        return pd.NA
    return _hash_hex(s, salt)[:6].upper()


def hash_column(df: pd.DataFrame, col: str, salt: str) -> None:
    """In-place: replace a PatientId column with its hashed equivalent."""
    if col not in df.columns:
        return
    df[col] = df[col].map(lambda v: hash_patient_id(v, salt))


def add_short_code(df: pd.DataFrame, source_col: str, salt: str,
                   new_col: str = "PatientCode") -> None:
    """In-place: add a 6-char pseudonym column derived from source_col.

    Call this BEFORE hash_column(source_col) if both are needed, since the
    short code is computed from the raw MRN.
    """
    if source_col not in df.columns:
        return
    df[new_col] = df[source_col].map(lambda v: short_patient_code(v, salt))


def drop_columns(df: pd.DataFrame, cols: Iterable[str]) -> list[str]:
    """In-place: drop columns that exist. Returns the list actually dropped."""
    present = [c for c in cols if c in df.columns]
    if present:
        df.drop(columns=present, inplace=True)
    return present


# Safe Harbor §164.514(b)(2)(i)(B): ZIP3 prefixes whose region contains <20,000
# people per the 2000 Census must be reported as "000". This list is static
# per the HIPAA rule.
_ZIP3_RESTRICTED = {
    "036", "059", "063", "102", "203", "556", "692", "790", "821",
    "823", "830", "831", "878", "879", "884", "890", "893",
}


def truncate_zip3(zip_value) -> str | float:
    """Truncate a ZIP code to 3 digits, returning '000' for restricted prefixes.

    Accepts int, str, or NaN. Returns pandas NA for null input.
    """
    if zip_value is None or (isinstance(zip_value, float) and pd.isna(zip_value)):
        return pd.NA
    s = str(zip_value).strip()
    # Strip ZIP+4 extension
    s = s.split("-")[0]
    # Pad with leading zeros if truncated during int conversion upstream
    s = s.zfill(5) if s.isdigit() and len(s) < 5 else s
    prefix = s[:3] if len(s) >= 3 else ""
    if not prefix.isdigit() or len(prefix) != 3:
        return pd.NA
    if prefix in _ZIP3_RESTRICTED:
        return "000"
    return prefix


def bucket_age_over_89(age) -> int | float:
    """Cap ages over 89 at 90 per Safe Harbor §164.514(b)(2)(i)(C).

    Returns pandas NA for null input.
    """
    if age is None or (isinstance(age, float) and pd.isna(age)):
        return pd.NA
    try:
        a = int(age)
    except (TypeError, ValueError):
        return pd.NA
    if a < 0:
        return pd.NA
    return min(a, 90)


def derive_age_from_dob(dob_series: pd.Series, reference: pd.Timestamp | None = None) -> pd.Series:
    """Compute age (in years) at a reference date from a DOB series.

    Returns a Series of Int (with pd.NA for nulls). Ages >89 capped to 90.
    """
    if reference is None:
        reference = pd.Timestamp.today()
    dob = pd.to_datetime(dob_series, errors="coerce")
    years = ((reference - dob).dt.days // 365).astype("Int64")
    return years.map(bucket_age_over_89)
