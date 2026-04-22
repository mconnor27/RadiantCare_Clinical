"""Fetch actual therapy revenue from Supabase `qbo_cache` table.

Returns a daily cumulative YTD series that mirrors the RadiantCare main app's
definition of therapy revenue (Total Income + Total Other Income, with 2016
Other Income excluded as a one-time anomaly).

Connects to Supabase PostgREST via httpx using the service role key. The
anon key alone cannot read `qbo_cache` because RLS requires an authenticated
session. Callers should configure env vars:

    SUPABASE_URL               e.g. https://<ref>.supabase.co
    SUPABASE_SERVICE_ROLE_KEY  service role JWT (server-side only)

Results are cached in-memory per fiscal year, keyed on `last_sync_timestamp`
so a newer sync invalidates the cache automatically.
"""

from __future__ import annotations

import logging
import os
import threading
from datetime import date
from typing import Optional

import httpx
import pandas as pd

logger = logging.getLogger(__name__)

_REQUEST_TIMEOUT = 15.0

# per-year cache: {year: (last_sync_timestamp_str, DataFrame)}
_cache: dict[int, tuple[str, pd.DataFrame]] = {}
_cache_lock = threading.Lock()


def _supabase_config() -> Optional[tuple[str, str]]:
    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    key = (
        os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        or os.environ.get("SUPABASE_SERVICE_KEY")
        or os.environ.get("SUPABASE_ANON_KEY")
    )
    if not url or not key:
        return None
    return url, key


def _fetch_row(year: int) -> Optional[dict]:
    cfg = _supabase_config()
    if cfg is None:
        logger.warning("Supabase not configured — set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY")
        return None
    url, key = cfg
    endpoint = f"{url}/rest/v1/qbo_cache"
    params = {
        "select": "year,last_sync_timestamp,daily",
        "year": f"eq.{year}",
    }
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Accept": "application/json",
    }
    try:
        r = httpx.get(endpoint, params=params, headers=headers, timeout=_REQUEST_TIMEOUT)
        r.raise_for_status()
        rows = r.json()
    except Exception as e:
        logger.error("qbo_cache fetch failed for year=%s: %s", year, e)
        return None
    if not rows:
        return None
    return rows[0]


def _find_row_by_label(rows, label):
    for row in rows or []:
        summary = row.get("Summary") or {}
        coldata = summary.get("ColData") or []
        if coldata and coldata[0].get("value") == label:
            return row
        inner = (row.get("Rows") or {}).get("Row")
        if inner:
            found = _find_row_by_label(inner, label)
            if found:
                return found
    return None


def parse_therapy_income_from_report(report: dict, target_year: int) -> pd.DataFrame:
    """Port of the TS parser. Returns a DataFrame with columns:

        date (datetime64[ns]), cumulative_income (float),
        cumulative_net_income (float|NaN), month_day (str 'MM-DD')

    One row per day, ordered chronologically.
    """
    try:
        columns = (report.get("Columns") or {}).get("Column") or []
        all_columns = columns[1:]  # skip account-name column

        valid = []
        for idx, col in enumerate(all_columns):
            meta = col.get("MetaData") or []
            start_date = None
            for m in meta:
                if m.get("Name") == "StartDate":
                    start_date = m.get("Value")
                    break
            if not start_date:
                continue
            yr = int(start_date[:4])
            if target_year and yr != target_year:
                continue
            valid.append((idx, start_date))
        valid.sort(key=lambda x: x[1])

        top_rows = (report.get("Rows") or {}).get("Row") or []

        therapy_row = _find_row_by_label(top_rows, "Total Income")
        if therapy_row is None:
            return pd.DataFrame(columns=["date", "cumulative_income", "cumulative_net_income", "month_day"])

        other_row = None if target_year == 2016 else _find_row_by_label(top_rows, "Total Other Income")

        def daily_vals(row):
            if not row:
                return []
            cd = (row.get("Summary") or {}).get("ColData") or []
            return [float(c.get("value") or 0) for c in cd[1:]]

        therapy_daily = daily_vals(therapy_row)
        other_daily = daily_vals(other_row)
        all_daily = [
            (therapy_daily[i] if i < len(therapy_daily) else 0.0)
            + (other_daily[i] if i < len(other_daily) else 0.0)
            for i in range(max(len(therapy_daily), len(other_daily)))
        ]

        net_row = _find_row_by_label(top_rows, "Net Income")
        other_adjust_row = _find_row_by_label(top_rows, "Total Other Income") if target_year == 2016 else None
        other_adjust = daily_vals(other_adjust_row)
        net_raw = daily_vals(net_row)
        net_daily = [
            (net_raw[i] if i < len(net_raw) else 0.0)
            - (other_adjust[i] if i < len(other_adjust) else 0.0)
            for i in range(len(net_raw))
        ]
        has_net = len(net_daily) > 0

        records = []
        cum = 0.0
        cum_net = 0.0
        for original_index, start_date in valid:
            daily_income = all_daily[original_index] if original_index < len(all_daily) else 0.0
            daily_net = net_daily[original_index] if original_index < len(net_daily) else 0.0
            cum += daily_income
            cum_net += daily_net
            dt = pd.Timestamp(start_date)
            month = dt.month
            day = dt.day
            if month == 2 and day == 29:
                # fold into Feb 28 for YoY consistency
                for rec in records:
                    if rec["month_day"] == "02-28":
                        idx28 = records.index(rec)
                        for j in range(idx28, len(records)):
                            records[j]["cumulative_income"] += daily_income
                            if has_net:
                                records[j]["cumulative_net_income"] = (
                                    records[j].get("cumulative_net_income") or 0.0
                                ) + daily_net
                        break
                continue
            records.append({
                "date": dt,
                "cumulative_income": cum,
                "cumulative_net_income": cum_net if has_net else None,
                "month_day": f"{month:02d}-{day:02d}",
            })

        df = pd.DataFrame(records)
        if not df.empty:
            df["date"] = pd.to_datetime(df["date"])
        return df
    except Exception as e:
        logger.error("parse_therapy_income_from_report failed: %s", e)
        return pd.DataFrame(columns=["date", "cumulative_income", "cumulative_net_income", "month_day"])


def get_actual_revenue_year(year: int) -> pd.DataFrame:
    """Return daily cumulative therapy revenue for a single fiscal year.

    Uses per-year in-memory cache keyed on last_sync_timestamp.
    """
    row = _fetch_row(year)
    if row is None:
        return pd.DataFrame(columns=["date", "cumulative_income", "cumulative_net_income", "month_day"])
    sync_ts = row.get("last_sync_timestamp") or ""
    with _cache_lock:
        cached = _cache.get(year)
        if cached and cached[0] == sync_ts:
            return cached[1]
    daily = row.get("daily") or {}
    df = parse_therapy_income_from_report(daily, year)
    with _cache_lock:
        _cache[year] = (sync_ts, df)
    return df


def get_actual_revenue_range(start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    """Return daily *non-cumulative* therapy revenue across one or more years.

    Columns: date, daily_income. Rebuild cumulative outside as needed.
    """
    if start is None or end is None:
        return pd.DataFrame(columns=["date", "daily_income"])
    start = pd.Timestamp(start).normalize()
    end = pd.Timestamp(end).normalize()
    frames = []
    for yr in range(start.year, end.year + 1):
        yr_df = get_actual_revenue_year(yr)
        if yr_df.empty:
            continue
        # Convert cumulative to daily
        daily = yr_df[["date", "cumulative_income"]].copy()
        daily["daily_income"] = daily["cumulative_income"].diff().fillna(daily["cumulative_income"])
        frames.append(daily[["date", "daily_income"]])
    if not frames:
        return pd.DataFrame(columns=["date", "daily_income"])
    out = pd.concat(frames, ignore_index=True)
    out = out[(out["date"] >= start) & (out["date"] <= end)]
    return out.sort_values("date").reset_index(drop=True)


def get_actual_data_bounds() -> Optional[tuple[pd.Timestamp, pd.Timestamp]]:
    """Return (earliest, latest) date available across all years with synced data.

    Cheap: only checks which years have rows, not their full content.
    """
    cfg = _supabase_config()
    if cfg is None:
        return None
    url, key = cfg
    try:
        r = httpx.get(
            f"{url}/rest/v1/qbo_cache",
            params={"select": "year,last_sync_timestamp", "order": "year.asc"},
            headers={"apikey": key, "Authorization": f"Bearer {key}"},
            timeout=_REQUEST_TIMEOUT,
        )
        r.raise_for_status()
        rows = r.json()
    except Exception as e:
        logger.error("qbo_cache bounds fetch failed: %s", e)
        return None
    if not rows:
        return None
    years = [int(row["year"]) for row in rows]
    min_year = min(years)
    max_year = max(years)
    # Latest date inside max_year: pull that year and inspect
    latest_df = get_actual_revenue_year(max_year)
    if latest_df.empty:
        return pd.Timestamp(date(min_year, 1, 1)), pd.Timestamp(date(max_year, 12, 31))
    return pd.Timestamp(date(min_year, 1, 1)), pd.Timestamp(latest_df["date"].max())
