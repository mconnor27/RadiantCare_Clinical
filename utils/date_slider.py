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
    if preset == "current_year":
        # Slider follows YTD — the "full calendar year" framing is a display
        # decision in cumulative-comparison charts, not a slider range change.
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


def preset_to_exact_dates(preset):
    """Return (start_str, end_str) with exact dates for a preset.

    Unlike the slider (month-granularity), these use the actual calendar
    offset from today so "Prior 12 mo" returns today − 12 months, not
    the 1st of that month.
    """
    today = pd.Timestamp.today().normalize()
    if preset == "12mo":
        start = today - pd.DateOffset(months=12)
    elif preset == "6mo":
        start = today - pd.DateOffset(months=6)
    elif preset == "3mo":
        start = today - pd.DateOffset(months=3)
    elif preset == "30d":
        start = today - pd.Timedelta(days=30)
    elif preset == "ytd":
        start = pd.Timestamp(today.year, 1, 1)
    elif preset == "current_year":
        # Data range is identical to YTD; the "full calendar year" framing
        # lives in cumulative-comparison chart logic, not in the data filter.
        start = pd.Timestamp(today.year, 1, 1)
    elif preset == "last_year":
        start = pd.Timestamp(today.year - 1, 1, 1)
        today = pd.Timestamp(today.year - 1, 12, 31)
    elif preset == "this_month":
        start = today.replace(day=1)
    elif preset == "last_month":
        last_month_end = today.replace(day=1) - pd.Timedelta(days=1)
        start = last_month_end.replace(day=1)
        today = last_month_end
    elif preset == "all":
        start = idx_to_date(0)
    else:
        start = today - pd.DateOffset(months=12)
    return start.strftime("%Y-%m-%d"), today.strftime("%Y-%m-%d")
