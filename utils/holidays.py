"""Holiday detection — physician schedule with static US federal fallback."""

import pandas as pd

# ---------------------------------------------------------------------------
# Static US federal holidays (fallback for years without schedule coverage)
# ---------------------------------------------------------------------------

def _us_federal_holidays(year):
    """Return a set of US federal holiday dates for a given year.

    Covers: New Year's Day, MLK Day, Presidents' Day, Memorial Day,
    Independence Day, Labor Day, Thanksgiving, Christmas.
    Applies the federal observed-date rule (Sat→Fri, Sun→Mon).
    """
    from datetime import date, timedelta

    def _nth_weekday(year, month, weekday, n):
        """Return the nth occurrence of weekday in month/year (1-indexed)."""
        first = date(year, month, 1)
        offset = (weekday - first.weekday()) % 7
        return first + timedelta(days=offset + 7 * (n - 1))

    def _last_weekday(year, month, weekday):
        """Return the last occurrence of weekday in month/year."""
        if month == 12:
            last = date(year, 12, 31)
        else:
            last = date(year, month + 1, 1) - timedelta(days=1)
        offset = (last.weekday() - weekday) % 7
        return last - timedelta(days=offset)

    def _observed(d):
        """Federal observed-date rule: Sat→Fri, Sun→Mon."""
        if d.weekday() == 5:
            return d - timedelta(days=1)
        if d.weekday() == 6:
            return d + timedelta(days=1)
        return d

    holidays = set()
    holidays.add(_observed(date(year, 1, 1)))                   # New Year's Day
    holidays.add(_nth_weekday(year, 1, 0, 3))                   # MLK Day (3rd Mon Jan)
    holidays.add(_nth_weekday(year, 2, 0, 3))                   # Presidents' Day (3rd Mon Feb)
    holidays.add(_last_weekday(year, 5, 0))                     # Memorial Day (last Mon May)
    holidays.add(_observed(date(year, 7, 4)))                   # Independence Day
    holidays.add(_nth_weekday(year, 9, 0, 1))                   # Labor Day (1st Mon Sep)
    holidays.add(_nth_weekday(year, 11, 3, 4))                  # Thanksgiving (4th Thu Nov)
    holidays.add(_observed(date(year, 12, 25)))                 # Christmas

    return {pd.Timestamp(d) for d in holidays}


# ---------------------------------------------------------------------------
# Physician-schedule-derived holidays
# ---------------------------------------------------------------------------

_HOLIDAY_OFF_STATUSES = frozenset({"OFF", "ON CALL", "WEEKEND CALL"})

# Minimum physician entries on a date to trust the schedule for holiday inference
_MIN_ENTRIES = 2


def _derive_holidays():
    """Derive holiday dates from physician schedule, with static fallback.

    A weekday is a holiday if every physician scheduled that day has
    OFF/ON CALL/WEEKEND CALL status and none have VACATION or SICK LEAVE.

    For years where the schedule has fewer than 100 unique dates (sparse
    coverage), falls back to static US federal holidays.
    """
    from data.loader import load_physician_schedule

    try:
        sched = load_physician_schedule()
    except Exception:
        sched = pd.DataFrame()

    schedule_holidays = set()
    covered_years = set()

    if not sched.empty and "Date" in sched.columns:
        sched = sched.copy()
        sched["_status_upper"] = sched["Status"].str.upper().str.strip()
        sched["_year"] = sched["Date"].dt.year

        # Determine which years have adequate schedule coverage
        dates_per_year = sched.groupby("_year")["Date"].apply(
            lambda s: s.dt.normalize().nunique()
        )
        covered_years = set(dates_per_year[dates_per_year >= 100].index)

        # Derive holidays from schedule for covered years
        schedule_years_with_holidays = set()
        covered = sched[sched["_year"].isin(covered_years)]
        for date, grp in covered.groupby(covered["Date"].dt.normalize()):
            if date.dayofweek >= 5:
                continue
            if len(grp) < _MIN_ENTRIES:
                continue
            statuses = set(grp["_status_upper"])
            if (not statuses - _HOLIDAY_OFF_STATUSES
                    and "VACATION" not in statuses
                    and "SICK LEAVE" not in statuses):
                schedule_holidays.add(date)
                schedule_years_with_holidays.add(date.year)

        # If a "covered" year detected zero holidays, the schedule has dates
        # but no holiday entries — demote it to uncovered so static kicks in
        covered_years = covered_years & schedule_years_with_holidays

    # Static fallback for all years not adequately covered by the schedule.
    # Cover the full span from earliest schedule year (or 2004) through
    # next year, so gaps like 2006 (no schedule rows at all) get holidays.
    current_year = pd.Timestamp.now().year
    if not sched.empty and "Date" in sched.columns:
        min_year = min(int(sched["_year"].min()), 2004)
        max_year = max(int(sched["_year"].max()), current_year) + 1
    else:
        min_year = 2004
        max_year = current_year + 2
    uncovered_years = set(range(min_year, max_year + 1)) - covered_years

    # Static fallback for uncovered years
    fallback_holidays = set()
    for year in uncovered_years:
        fallback_holidays |= _us_federal_holidays(year)
    # Only keep weekday fallback holidays (should already be, but defensive)
    fallback_holidays = {d for d in fallback_holidays if d.dayofweek < 5}

    return schedule_holidays | fallback_holidays


# ---------------------------------------------------------------------------
# Public API (cached)
# ---------------------------------------------------------------------------

_holidays_cache = None


def get_holidays():
    """Return the set of holiday Timestamps (cached after first call)."""
    global _holidays_cache
    if _holidays_cache is None:
        _holidays_cache = _derive_holidays()
    return _holidays_cache


def clear_holidays_cache():
    """Clear the holiday cache (call after data refresh)."""
    global _holidays_cache
    _holidays_cache = None
