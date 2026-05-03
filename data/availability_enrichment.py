"""Pre-sanitization enrichment for the Availability dataset.

The scheduling page only ever consults AppointmentNotes as a boolean
(is the slot reserved/blocked by a front-desk note?) — never reads the
text. Derive a HasNote boolean here so the sanitized CSV carries the
signal without the free-text PHI.

The Availability live-feed (R2 → loader) performs the same derivation
at fetch time in data/loader.py:_availability_inner; this module keeps
the PHI-mode local-dev path consistent with that behavior.
"""

from __future__ import annotations

import pandas as pd


def enrich(df: pd.DataFrame, salt: str) -> pd.DataFrame:
    """Sanitize-time hook: add HasNote before AppointmentNotes is dropped."""
    if "HasNote" in df.columns:
        return df
    if "AppointmentNotes" in df.columns:
        df["HasNote"] = (
            df["AppointmentNotes"].fillna("").astype(str).str.strip() != ""
        )
    else:
        df["HasNote"] = False
    return df
