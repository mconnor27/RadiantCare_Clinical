"""Utilities for preparing DataFrames for AG Grid display."""

import pandas as pd

BLANK_PLACEHOLDER = "--"


def sanitize_for_grid(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize blanks to '--' and prevent AG Grid 'Invalid Number'.

    Converts float columns to string so AG Grid won't auto-detect them
    as numeric and fail on missing values.  All NaN, empty strings, and
    em-dashes become '--' for display.
    """
    df = _coerce_floats(df)
    df = df.fillna(BLANK_PLACEHOLDER)
    df = df.replace({"": BLANK_PLACEHOLDER, "—": BLANK_PLACEHOLDER})
    return df


def _coerce_floats(df: pd.DataFrame) -> pd.DataFrame:
    """Convert float columns to string, preserving NaN as NaN."""
    df = df.copy()
    for c in df.columns:
        if pd.api.types.is_float_dtype(df[c]):
            df[c] = df[c].apply(
                lambda v: str(int(v)) if pd.notna(v) and v == int(v)
                else (str(round(v, 1)) if pd.notna(v) else pd.NA)
            )
    return df
