#!/usr/bin/env python3
"""Rebuild the parquet data cache from source CSV/Excel files.

Run this after new data arrives (e.g., via cron at 3 AM Tue-Sat)
so the app starts instantly without a cold CSV parse.

Usage:
    python scripts/rebuild_cache.py
"""
import sys
import time
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from data.loader import (
    clear_cache,
    load_treatment_detail, load_billing, load_workflow,
    load_referrals, load_daily_volume, load_clinic_visits,
    load_simulations, load_tasks, load_courses, load_plans,
    load_weekly_visits, load_rvu_lookup,
)


def main():
    print("Clearing existing caches...")
    clear_cache()

    loaders = [
        ("treatment_detail", load_treatment_detail),
        ("billing",          load_billing),
        ("workflow",         load_workflow),
        ("referrals",        load_referrals),
        ("daily_volume",     load_daily_volume),
        ("clinic_visits",    load_clinic_visits),
        ("simulations",      load_simulations),
        ("tasks",            load_tasks),
        ("courses",          load_courses),
        ("plans",            load_plans),
        ("weekly_visits",    load_weekly_visits),
        ("rvu_lookup",       load_rvu_lookup),
    ]

    total_start = time.time()
    for name, fn in loaders:
        t0 = time.time()
        try:
            df = fn()
            elapsed = time.time() - t0
            print(f"  {name:25s} {elapsed:5.2f}s  {len(df):>10,} rows")
        except Exception as e:
            print(f"  {name:25s} ERROR: {e}")

    total = time.time() - total_start
    print(f"\nCache rebuild complete in {total:.1f}s")
    print(f"Cache dir: {Path('.data_cache').resolve()}")


if __name__ == "__main__":
    main()
