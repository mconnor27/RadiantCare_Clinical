"""Shared date-slider helpers used by workflow of and clinic-visits pages."""

import datetime as _dt
import pandas as pd

BASE_YEAR = 2004


def month_idx(year, month):
    """Convert year/month to integer index (0 = Jan 2004)."""
    return (year - BASE_YEAR) * 12 + (month - 1)


def idx_to_date(idx, end_of_month=False):
    """Convert integer index back to pd.Timestamp.

    When *end_of_month* is True the result is capped at today so that
    the current month never extends into the future (e.g. "YTD" shows
    Apr 8 instead of Apr 30).
    """
    year = BASE_YEAR + idx // 12
    month = idx % 12 + 1
    ts = pd.Timestamp(year, month, 1)
    if end_of_month:
        ts = min(ts + pd.offsets.MonthEnd(0), pd.Timestamp.today().normalize())
    return ts


_today = _dt.date.today()
MAX_IDX = month_idx(_today.year, _today.month)
DEFAULT_SLIDER = [max(0, MAX_IDX - 11), MAX_IDX]
SLIDER_MARKS = [
    {"value": month_idx(y, 1), "label": f"'{y % 100:02d}"}
    for y in range(BASE_YEAR, _today.year + 1)
    if y % 2 == 0  # every other year to avoid crowding
]


def preset_to_slider_val(preset, max_idx):
    """Convert a preset string to [start_idx, end_idx] for the slider."""
    end = max_idx
    if preset == "12mo":
        return [max(0, end - 11), end]
    if preset == "6mo":
        return [max(0, end - 5), end]
    if preset == "3mo":
        return [max(0, end - 2), end]
    if preset == "30d":
        return [max(0, end - 1), end]
    if preset == "ytd":
        d = idx_to_date(end)
        return [month_idx(d.year, 1), end]
    if preset == "last_year":
        d = idx_to_date(end)
        return [month_idx(d.year - 1, 1), month_idx(d.year - 1, 12)]
    if preset == "this_month":
        return [end, end]
    if preset == "last_month":
        return [max(0, end - 1), max(0, end - 1)]
    if preset == "all":
        return [0, end]
    return [max(0, end - 11), end]
