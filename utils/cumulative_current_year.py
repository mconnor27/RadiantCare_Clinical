"""Current-year preset support for cumulative-comparison charts.

When `date_preset == "current_year"` the filter-bar's data window is identical
to YTD, but the chart axis should span the *entire* calendar year with the
current-year trace stopping at the latest real data date. Prior-year traces
fill the full year so the comparison is apples-to-apples.

Each page's `_prepare_cumulative_data(df, start, end, date_preset, ..., mode)`
follows a shared pattern:
    today = pd.Timestamp.now().normalize()
    if end.normalize() > today:
        end = today
    period_days = (end - start).days + 1
    ...

For current_year + prior mode we widen (start, end) to (Jan 1, Dec 31) of the
display year BEFORE that block so period_days = 365/366 and prior calendar
shifts produce full prior years. After the builder returns, we call
`apply_current_year_projection` to null out the current-year trace past the
actual last data date and attach a linear year-end projection descriptor the
clientside can render as a dashed tail (line/area) or transparent overlay bar.
"""

from __future__ import annotations

import pandas as pd


def setup_current_year_range(date_preset, mode, start, end):
    """Return (new_start, new_end, last_actual_date) for current_year mode.

    Call once at the top of `_prepare_cumulative_data`:

        today = pd.Timestamp.now().normalize()
        start, end, _cy_last_actual = setup_current_year_range(
            date_preset, mode, start, end
        )
        if _cy_last_actual is None and end.normalize() > today:
            end = today

    `_cy_last_actual` is None for every preset except `current_year` + prior
    mode; pass it plus the widened `start` to `apply_current_year_projection`
    right before returning the prior-mode data dict.
    """
    if date_preset != "current_year" or mode != "prior":
        return start, end, None
    today = pd.Timestamp.now().normalize()
    last_actual = min(end.normalize(), today)
    year = start.year if start is not None else today.year
    return (
        pd.Timestamp(year, 1, 1),
        pd.Timestamp(year, 12, 31),
        last_actual,
    )


def apply_current_year_projection(data, last_actual_date, year_start):
    """Null out the current-year trace after `last_actual_date` and attach a
    linear year-end projection descriptor (mutates `data` in place).

    Expects the dict produced by the `mode="prior"` branch of
    `_prepare_cumulative_data` (keys: current, dayIndices, sliceBreakdown, …).
    """
    if not data or data.get("mode") != "prior":
        return data
    current = data.get("current") or {}
    values = current.get("values")
    if not values:
        return data
    n_days = len(values)
    last_idx = (last_actual_date.normalize() - year_start.normalize()).days
    if last_idx < 0 or last_idx >= n_days:
        return data

    # Walk back to the last day with a real positive cum value (handles
    # trimmed cumulatives that null out the head of the series).
    last_val = None
    i = min(last_idx, n_days - 1)
    while i >= 0:
        v = values[i]
        if v is not None and v > 0:
            last_val = v
            last_idx = i
            break
        i -= 1
    if last_val is None:
        return data

    for j in range(last_idx + 1, n_days):
        values[j] = None

    days_elapsed = last_idx + 1
    rate = (last_val / days_elapsed) if days_elapsed > 0 else 0.0
    projected_end = last_val + rate * (n_days - days_elapsed)
    current["projection"] = {
        "startIdx": last_idx,
        "startVal": float(last_val),
        "endIdx": n_days - 1,
        "endVal": float(projected_end),
    }
    current["values"] = values
    data["current"] = current

    # Bar-mode: store one projection-remainder descriptor so the renderer can
    # overlay a transparent bar on the current period's stack.
    sb = data.get("sliceBreakdown", {})
    periods = sb.get("periods", []) if sb else []
    cur_label = current.get("label")
    if periods and cur_label and cur_label in periods:
        data["projectionTotal"] = {
            "periodIdx": periods.index(cur_label),
            "remainder": float(projected_end - last_val),
            "endVal": float(projected_end),
        }
    return data
