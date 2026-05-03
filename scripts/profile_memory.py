"""Per-dataset RSS profiler for data/loader.py.

Loads each dataset in a fresh-ish process state, measures resident memory
delta, and prints a sorted table. Goal: identify which loaders dominate
the steady-state RAM footprint that drives Railway memory cost.
"""
from __future__ import annotations

import gc
import os
import sys
import time
from pathlib import Path

import psutil

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Match production: PHI_MODE so the loader reads sanitized data.
os.environ.setdefault("PHI_MODE", "true")

import data.loader as L

LOADERS = [
    ("treatment",            L.load_treatment),
    ("treatment_detail",     L.load_treatment_detail),
    ("daily_volume",         L.load_daily_volume),
    ("daily_volume_future",  L.load_daily_volume_future),
    ("availability",         L.load_availability),
    ("clinic_visits",        L.load_clinic_visits),
    ("simulations",          L.load_simulations),
    ("workflow",             L.load_workflow),
    ("tasks",                L.load_tasks),
    ("otvs",                 L.load_otvs),
    ("weekly_visits",        L.load_weekly_visits),
    ("courses",              L.load_courses),
    ("plans",                L.load_plans),
    ("machines",             L.load_machines),
    ("downtime_gaps",        L.load_downtime_gaps),
    ("machine_downtime",     L.load_machine_downtime),
    ("machine_statistics",   L.load_machine_statistics),
    ("billing",              L.load_billing),
    ("procedures",           L.load_procedures),
    ("cpt_audit",            L.load_cpt_audit),
    ("patients",             L.load_patients),
    ("referrals",            L.load_referrals),
    ("medonc_referrals",     L.load_medonc_referrals),
    ("referring",            L.load_referring),
    ("diagnosis",            L.load_diagnosis),
    ("physician_schedule",   L.load_physician_schedule),
]

proc = psutil.Process(os.getpid())

def rss_mb() -> float:
    return proc.memory_info().rss / (1024 * 1024)

baseline = rss_mb()
print(f"Baseline RSS after imports: {baseline:.1f} MB\n")

results = []
for name, fn in LOADERS:
    gc.collect()
    before = rss_mb()
    t0 = time.perf_counter()
    try:
        df = fn()
        ok = True
        rows = len(df) if hasattr(df, "__len__") else 0
        cols = len(df.columns) if hasattr(df, "columns") else 0
        # in-pandas size estimate (deep)
        try:
            mem_pd = df.memory_usage(deep=True).sum() / (1024 * 1024)
        except Exception:
            mem_pd = float("nan")
    except Exception as exc:
        ok = False
        rows = cols = 0
        mem_pd = float("nan")
        print(f"  [skip] {name}: {exc}")
    elapsed = time.perf_counter() - t0
    after = rss_mb()
    delta = after - before
    results.append((name, rows, cols, mem_pd, delta, after, elapsed, ok))
    print(f"  {name:24s}  rows={rows:>9,d}  cols={cols:>3d}  pd={mem_pd:>7.1f}MB  ΔRSS={delta:>+7.1f}MB  RSS={after:>7.1f}MB  in {elapsed:>5.2f}s")

print("\n" + "=" * 90)
print(f"Final RSS: {rss_mb():.1f} MB  (started at {baseline:.1f} MB, grew by {rss_mb() - baseline:+.1f} MB)")

print("\nTop 10 by ΔRSS (single-load attribution; cached calls show 0):")
for name, rows, cols, mem_pd, delta, _, _, ok in sorted(results, key=lambda r: -r[4])[:10]:
    print(f"  {name:24s}  ΔRSS={delta:>+7.1f}MB   pd={mem_pd:>7.1f}MB   rows={rows:,}")

print("\nTop 10 by pandas deep memory_usage (true cost held in RAM):")
for name, rows, cols, mem_pd, delta, _, _, ok in sorted(results, key=lambda r: -(r[3] or 0))[:10]:
    print(f"  {name:24s}  pd={mem_pd:>7.1f}MB   rows={rows:,}   cols={cols}")
