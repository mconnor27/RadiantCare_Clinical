"""Billing page — CPT category volumes, wRVU production, and payor mix."""

import dash
import dash_mantine_components as dmc
import dash_ag_grid as dag
from dash import callback, Input, Output, State, dcc, html, clientside_callback, ClientsideFunction
from dash_iconify import DashIconify
import plotly.graph_objects as go
import pandas as pd
import numpy as np
from datetime import timedelta

from config.settings import (
    DEPARTMENTS, DEPARTMENT_COLORS, CHART_COLORWAY, PRIMARY,
    DEFAULT_LAYOUT, FONT_FAMILY, SEMANTIC_COLORS, NEUTRAL, CHART_PAPER_HEIGHT,
    DEFAULT_COLUMN_DEFS, DEFAULT_GRID_OPTIONS, PRIOR_PERIOD_COLORS,
)
from components.filter_bar import department_chips
from components.detail_table import detail_table
from components.phi import apply_phi_grid_rules
from utils.tables import sanitize_for_grid
from components.kpi_card import kpi_card, kpi_placeholder
from components.chart_card import chart_card, register_chart_callbacks
from components.chart_settings import chart_settings_popover
from utils.charts import apply_default_layout, empty_figure, dept_color, color_for_index
from utils.date_slider import (
    month_idx, idx_to_date, MAX_IDX, DEFAULT_SLIDER, SLIDER_MARKS,
    preset_to_slider_val, preset_to_exact_dates,
)
from data.reviews_db import (
    get_all_insurance_rates, upsert_insurance_rate, delete_insurance_rate,
    seed_insurance_rates, get_rate_history, upsert_rate_history,
    delete_rate_history_entry,
    seed_payor_mappings, get_all_payor_mappings, upsert_payor_mapping,
    get_payor_mapping_dict,
    rename_standardized_payor, delete_standardized_payor,
    get_standardized_payor_counts,
    get_revenue_adj_settings, save_revenue_adj_settings,
)

dash.register_page(__name__, path="/billing", name="Billing", order=7)

PAGE_ID = "billing"
_DEFAULT_DATE_PRESET = "12mo"

# CMS Conversion Factor (Medicare PFS) — update annually
_CMS_CF = {
    2015: 35.80, 2016: 35.80, 2017: 35.89, 2018: 36.00, 2019: 36.04,
    2020: 36.09, 2021: 34.89, 2022: 34.61, 2023: 33.89, 2024: 33.29,
    2025: 32.35, 2026: 33.40,
}
_CMS_CF_DEFAULT = 33.40
# All sites: physician group bills pro fees only (wRVU + MP_RVU)
# Aberdeen is freestanding but group still earns pro component only


# ---------------------------------------------------------------------------
# CPT Category Mapping (imported from shared module)
# ---------------------------------------------------------------------------

from utils.cpt_categories import (
    CPT_CATEGORIES, CPT_SUBCATEGORIES, CPT_DESCRIPTIONS,
    CODE_TO_CATEGORY as _CODE_TO_CATEGORY,
    CODE_TO_SUBCATEGORY as _CODE_TO_SUBCATEGORY,
    CATEGORY_NAMES, CATEGORY_SLUGS, SLUG_TO_CATEGORY,
)
from components.cpt_filter import cpt_accordion, register_cpt_callbacks

CATEGORY_COLORS = {}
for _i, _cat in enumerate(CATEGORY_NAMES):
    CATEGORY_COLORS[_cat] = CHART_COLORWAY[_i % len(CHART_COLORWAY)]


# ---------------------------------------------------------------------------
# Fee schedule file paths (for detail drill-down)
# ---------------------------------------------------------------------------
_FEE_SCHEDULE_FILES = {
    "Aetna": "insurance/AETNA/AETNA_fee-schedule 06.2022.csv",
    "Premera Blue Cross": "insurance/PREMERA/RadiantCare Physicians PLLC - Premera Fee Schedule.xlsx",
    "Premera HMO": "insurance/PREMERA/RadiantCare Physicians PLLC - Premera Fee Schedule.xlsx",
    "LifeWise Assurance": "insurance/PREMERA/RadiantCare Physicians PLLC - Premera Fee Schedule.xlsx",
    "LifeWise Health Plan WA": "insurance/PREMERA/RadiantCare Physicians PLLC - Premera Fee Schedule.xlsx",
    "Regence BCBS": "insurance/REGENCE/Regence Fee Schedule 12-01-2021.xlsx",
    "UnitedHealthcare Y1": "insurance/UHC/Radiantcare UHC Full Sched.xlsx",
    "UnitedHealthcare Y2": "insurance/UHC/Radiantcare UHC Full Sched.xlsx",
    "UnitedHealthcare Y3": "insurance/UHC/Radiantcare UHC Full Sched.xlsx",
    "UnitedHealthcare (prior)": "insurance/UHC/Radiantcare UHC Full Sched.xlsx",
}

# All CPT codes we actually bill
_OUR_CODES = set()
for _codes in CPT_CATEGORIES.values():
    _OUR_CODES.update(_codes)


def _load_fee_schedule_detail(payor: str) -> list[dict]:
    """Load per-code rates from a payor's fee schedule file, filtered to our codes."""
    from pathlib import Path
    from config.settings import PROJECT_ROOT

    file_key = payor
    filepath = _FEE_SCHEDULE_FILES.get(file_key)
    if not filepath:
        return []

    full_path = PROJECT_ROOT / filepath
    if not full_path.exists():
        return []

    # Load CMS 2026 rates for comparison
    from data.loader import load_rvu_lookup
    rvu = load_rvu_lookup()
    rvu26 = rvu[(rvu["Year"] == 2026) & (rvu["MOD"] == "")].set_index("HCPCS")

    rows = []

    if "AETNA" in filepath:
        df = pd.read_csv(full_path)
        df["Procedure Code"] = df["Procedure Code"].astype(str).str.strip()
        df["amount"] = pd.to_numeric(
            df["Max Amount"].str.replace(r"[\$,]", "", regex=True), errors="coerce"
        )
        df = df[df["Procedure Code"].isin(_OUR_CODES)]
        for _, r in df.iterrows():
            code = r["Procedure Code"]
            cms = rvu26.loc[code, "Fac_Total_RVU"] * _CMS_CF_DEFAULT if code in rvu26.index else None
            pct = (r["amount"] / cms * 100) if cms and cms > 0 else None
            rows.append({
                "code": code,
                "description": str(r.get("Description", ""))[:50],
                "category": _CODE_TO_CATEGORY.get(code, "Other"),
                "modifier": str(r.get("Modifier", "")),
                "rate": r["amount"],
                "cms_rate": round(cms, 2) if cms else None,
                "pct_cms": round(pct, 1) if pct else None,
                "site": str(r.get("Site Of Service", "")),
                "product": str(r.get("Product", "")),
            })

    elif "PREMERA" in filepath:
        df = pd.read_excel(full_path, header=None, skiprows=7)
        df.columns = ["Procedure", "Modifier", "Proc_Mod", "PaymentMethod", "NonFacility", "Facility"]
        df["Procedure"] = df["Procedure"].astype(str).str.strip()
        df["Modifier"] = df["Modifier"].astype(str).str.strip()
        df["Facility"] = pd.to_numeric(df["Facility"], errors="coerce")
        df = df[df["Procedure"].isin(_OUR_CODES)]
        for _, r in df.iterrows():
            code = r["Procedure"]
            mod = r["Modifier"] if r["Modifier"] not in ("", "nan", "None") else ""
            rvu_key = code
            cms = rvu26.loc[rvu_key, "Fac_Total_RVU"] * _CMS_CF_DEFAULT if rvu_key in rvu26.index else None
            rate = r["Facility"]
            pct = (rate / cms * 100) if cms and cms > 0 and pd.notna(rate) else None
            rows.append({
                "code": code,
                "description": "",
                "category": _CODE_TO_CATEGORY.get(code, "Other"),
                "modifier": mod,
                "rate": round(rate, 2) if pd.notna(rate) else None,
                "cms_rate": round(cms, 2) if cms else None,
                "pct_cms": round(pct, 1) if pct else None,
                "site": "Facility",
                "product": payor,
            })

    elif "REGENCE" in filepath:
        df = pd.read_excel(full_path, header=None, skiprows=8)
        df.columns = ["Procedure", "Modifier", "EffDate", "NonFacility", "Facility"]
        df["Procedure"] = df["Procedure"].astype(str).str.strip()
        df["Facility"] = pd.to_numeric(df["Facility"], errors="coerce")
        df = df[df["Procedure"].isin(_OUR_CODES)]
        for _, r in df.iterrows():
            code = r["Procedure"]
            mod = str(r["Modifier"]) if pd.notna(r["Modifier"]) else ""
            cms = rvu26.loc[code, "Fac_Total_RVU"] * _CMS_CF_DEFAULT if code in rvu26.index else None
            rate = r["Facility"]
            pct = (rate / cms * 100) if cms and cms > 0 and pd.notna(rate) else None
            rows.append({
                "code": code,
                "description": "",
                "category": _CODE_TO_CATEGORY.get(code, "Other"),
                "modifier": mod,
                "rate": round(rate, 2) if pd.notna(rate) else None,
                "cms_rate": round(cms, 2) if cms else None,
                "pct_cms": round(pct, 1) if pct else None,
                "site": "Facility",
                "product": "Regence",
            })

    elif "UHC" in filepath:
        df = pd.read_excel(full_path)
        df["CPT/HCPCS"] = df["CPT/HCPCS"].astype(str).str.strip()
        df["amount"] = pd.to_numeric(
            df["Fee Amount"].str.replace(r"[\$,]", "", regex=True), errors="coerce"
        )
        df = df[df["CPT/HCPCS"].isin(_OUR_CODES)]
        for _, r in df.iterrows():
            code = r["CPT/HCPCS"]
            mod = str(r.get("Modifier", ""))
            # For global (00) modifier, compare to global CMS
            rvu_key = code
            cms = rvu26.loc[rvu_key, "Fac_Total_RVU"] * _CMS_CF_DEFAULT if rvu_key in rvu26.index else None
            rate = r["amount"]
            pct = (rate / cms * 100) if cms and cms > 0 and pd.notna(rate) else None
            rows.append({
                "code": code,
                "description": str(r.get("CPT/HCPCS Description", ""))[:50],
                "category": _CODE_TO_CATEGORY.get(code, "Other"),
                "modifier": mod,
                "rate": round(rate, 2) if pd.notna(rate) else None,
                "cms_rate": round(cms, 2) if cms else None,
                "pct_cms": round(pct, 1) if pct else None,
                "site": str(r.get("Place of Service", "")),
                "product": "UHC",
            })

    return rows


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _strip_modifier(code):
    """Strip -TC, -26, NC suffixes to get the base HCPCS code."""
    if not isinstance(code, str):
        return str(code)
    code = code.strip()
    for suffix in ("-TC", "-26", " NC"):
        if code.endswith(suffix):
            code = code[: -len(suffix)].strip()
    return code


def _assign_category(base_code):
    """Return category name for a base HCPCS code, or 'Other'."""
    return _CODE_TO_CATEGORY.get(base_code, "Other")


def _derive_charge_status(code):
    """Return 'No Charge' if code has NC suffix, else 'Billable'."""
    if not isinstance(code, str):
        return "Billable"
    return "No Charge" if " NC" in code or code.endswith("NC") else "Billable"


def _broad_payor(name):
    """Map insurer name to broad category."""
    if not isinstance(name, str) or name in ("Unknown", ""):
        return "Other/Unknown"
    nl = name.lower()
    if "medicare" in nl:
        return "Medicare"
    if any(kw in nl for kw in (
        "medicaid", "apple health", "dshs",
        "molina medicaid", "molina healthcare",
        "amerigroup medicaid", "coordinated care medicaid",
        "community hlth plan chpw medicaid",
        "careoregon medicaid", "wellpoint wa medicaid",
        "united healthcare medicaid",
    )):
        return "Medicaid"
    if any(kw in nl for kw in (
        "tricare", "champva", "veterans admin", "veteran",
        "us family healthplan",
    )):
        return "Military/VA"
    if any(kw in nl for kw in (
        "labor and ind", "dept of labor", "workers comp", " wc",
        "corvel", "sedgwick",
    )):
        return "Workers Comp"
    if any(kw in nl for kw in (
        "indian health", "quinault", "chehalis", "nisqually",
        "tongas",
    )):
        return "Tribal/IHS"
    if any(kw in nl for kw in ("self pay",)):
        return "Self Pay"
    if any(kw in nl for kw in (
        "correction", "mcneil island", "stafford creek",
        "thurston county jail",
    )):
        return "Other/Unknown"
    return "Private"


def _merge_rvu(df, rvu):
    """Add individual RVU component columns for physician revenue estimation.

    Strategy: for codes with a 26/TC split, use the 26 row (physician group
    bills professional component only — does not own any facility).  For
    codes without a 26 row that have physician work (wRVU > 0), use the
    global row (e.g. E&M, management codes).

    PE selection by site:
      Lacey/Centralia (POS 22) → Fac_PE_RVU
      Aberdeen (POS 11)        → NonFac_PE_RVU
    For -26 rows these are identical; the distinction is negligible for
    non-split global codes (E&M etc.).

    Columns added (per billing row):
      wRVU, Fac_PE_RVU, NonFac_PE_RVU, MP_RVU, Pro_Total_RVU, Fac_Total_RVU
      TC_wRVU, TC_PE_RVU, TC_MP_RVU (for hospital revenue at Aberdeen)
    """
    _empty_cols = ["wRVU", "Fac_PE_RVU", "NonFac_PE_RVU", "MP_RVU",
                   "Pro_Total_RVU", "Fac_Total_RVU",
                   "TC_wRVU", "TC_PE_RVU", "TC_MP_RVU"]
    if df.empty:
        for c in _empty_cols:
            df[c] = 0.0
        return df

    df = df.copy()
    df["_base"] = df["ProcedureCode"].apply(_strip_modifier)
    df["_yr"] = df["DateOfService"].dt.year
    yr_str = df["_yr"].astype(str)

    # Build lookup dicts keyed by HCPCS|MOD|Year
    rvu_key = rvu["HCPCS"] + "|" + rvu["MOD"] + "|" + rvu["Year"].astype(str)
    wrvu_dict = dict(zip(rvu_key, rvu["wRVU"]))
    fac_pe_dict = dict(zip(rvu_key, rvu["Fac_PE_RVU"]))
    nonfac_pe_dict = dict(zip(rvu_key, rvu["NonFac_PE_RVU"]))
    mp_dict = dict(zip(rvu_key, rvu["MP_RVU"]))
    fac_total_dict = dict(zip(rvu_key, rvu["Fac_Total_RVU"]))

    pro_key = df["_base"] + "|26|" + yr_str
    global_key = df["_base"] + "||" + yr_str
    tc_key = df["_base"] + "|TC|" + yr_str

    # --- For each component: try 26 row first, fall back to global ---
    def _lookup(primary, fallback, lookup_dict):
        vals = primary.map(lookup_dict)
        miss = vals.isna()
        if miss.any():
            vals[miss] = fallback[miss].map(lookup_dict)
        return vals.fillna(0)

    df["wRVU"] = _lookup(pro_key, global_key, wrvu_dict)
    df["Fac_PE_RVU"] = _lookup(pro_key, global_key, fac_pe_dict)
    df["NonFac_PE_RVU"] = _lookup(pro_key, global_key, nonfac_pe_dict)
    df["MP_RVU"] = _lookup(pro_key, global_key, mp_dict)

    # For codes with no physician work (TC-only, e.g. delivery at hospital),
    # zero out the professional components — physician group doesn't bill these
    no_work = df["wRVU"] == 0
    for c in ["Fac_PE_RVU", "NonFac_PE_RVU", "MP_RVU"]:
        df.loc[no_work, c] = 0.0

    # Pro total (facility-site version) for quick reference
    df["Pro_Total_RVU"] = df["wRVU"] + df["Fac_PE_RVU"] + df["MP_RVU"]

    # Global total for reference
    df["Fac_Total_RVU"] = global_key.map(fac_total_dict).fillna(0)

    # --- TC components for Aberdeen hospital revenue (PFS TC rows) ---
    # For true split codes: use TC modifier row
    # For TC-only codes (PCTC=3, wRVU=0): use global row (entire code is technical)
    # For professional-only codes (wRVU>0, no TC row): hospital gets nothing
    df["TC_wRVU"] = tc_key.map(wrvu_dict)
    df["TC_PE_RVU"] = tc_key.map(fac_pe_dict)
    df["TC_MP_RVU"] = tc_key.map(mp_dict)
    # Fall back to global for TC-only codes (no TC row, no physician work)
    tc_miss = df["TC_PE_RVU"].isna()
    tc_only = tc_miss & no_work  # wRVU=0 → entire code is technical
    if tc_only.any():
        df.loc[tc_only, "TC_wRVU"] = global_key[tc_only].map(wrvu_dict).fillna(0)
        df.loc[tc_only, "TC_PE_RVU"] = global_key[tc_only].map(fac_pe_dict).fillna(0)
        df.loc[tc_only, "TC_MP_RVU"] = global_key[tc_only].map(mp_dict).fillna(0)
    df[["TC_wRVU", "TC_PE_RVU", "TC_MP_RVU"]] = df[["TC_wRVU", "TC_PE_RVU", "TC_MP_RVU"]].fillna(0)

    df.drop(columns=["_base", "_yr"], inplace=True)
    return df


def _preset_start(last_date, preset, earliest_date):
    """Calculate start date from a preset, relative to data."""
    lookbacks = {
        "12mo": 365, "6mo": 182, "3mo": 91, "30d": 30,
    }
    if preset == "ytd":
        return pd.Timestamp(last_date.year, 1, 1)
    if preset == "last_year":
        return pd.Timestamp(last_date.year - 1, 1, 1)
    if preset == "this_month":
        return pd.Timestamp(last_date.year, last_date.month, 1)
    if preset == "last_month":
        d = last_date - pd.DateOffset(months=1)
        return pd.Timestamp(d.year, d.month, 1)
    days = lookbacks.get(preset)
    if days is None:  # "all"
        return earliest_date
    return last_date - timedelta(days=days)


def _prior_range(start, end, preset):
    """Calculate prior comparison range for trend text."""
    days = (end - start).days
    if preset in ("ytd", "last_year"):
        try:
            p_start = start - pd.DateOffset(years=1)
            p_end = end - pd.DateOffset(years=1)
            return p_start, p_end
        except Exception:
            pass
    return start - timedelta(days=days + 1), start - timedelta(days=1)


def _trend_text(current, prior):
    """Build trend text and direction from current vs prior values."""
    if prior == 0:
        return None, None
    pct = (current - prior) / prior * 100
    direction = "up" if pct >= 0 else "down"
    return f"{abs(pct):.0f}% vs prior", direction


def _count_spark_raw(df, date_col, start, end, value_col=None):
    """Return daily counts as sparkline data {labels, values}."""
    if df.empty or date_col not in df.columns:
        return {"labels": [], "values": []}
    sub = df[(df[date_col] >= start) & (df[date_col] <= end)]
    grp = sub.groupby(sub[date_col].dt.normalize())
    daily = grp[value_col].sum() if value_col and value_col in sub.columns else grp.size()
    idx = pd.date_range(start, end, freq="D")
    daily = daily.reindex(idx, fill_value=0)
    return {
        "labels": [d.strftime("%Y-%m-%d") for d in daily.index],
        "values": daily.tolist(),
    }


def _build_census_data(df, date_col, start, end, group_col, group_names, group_colors,
                       value_col=None, y_title="Count", stacked=True, freq="M"):
    """Build census-format store data for smoothChartWithType.

    freq: 'W' (weekly), 'M' (monthly), 'Y' (yearly).
    """
    if df.empty or date_col not in df.columns:
        return None

    df = df.copy()
    freq_map = {"W": "W-MON", "M": "M", "Y": "Y"}
    pd_freq = freq_map.get(freq, "M")
    df["_period"] = df[date_col].dt.to_period(pd_freq).dt.to_timestamp()

    # Use actual unique periods from data (date_range can misalign for weekly)
    periods = sorted(df["_period"].unique())
    dates = [pd.Timestamp(d).strftime("%Y-%m-%d") for d in periods]

    series = []
    for name in group_names:
        sub = df[df[group_col] == name] if group_col in df.columns else df
        if value_col and value_col in sub.columns:
            grouped = sub.groupby("_period")[value_col].sum()
        else:
            grouped = sub.groupby("_period").size()
        grouped = grouped.reindex(periods, fill_value=0)
        series.append({
            "name": name,
            "values": grouped.tolist(),
            "color": group_colors.get(name, CHART_COLORWAY[len(series) % len(CHART_COLORWAY)]),
        })

    return {
        "dates": dates,
        "series": series,
        "yTitle": y_title,
        "stacked": stacked,
        "height": 380,
    }


def _build_cumulative(df, date_col, start, end, date_preset,
                      value_col=None, y_title="Cumulative",
                      mode="prior", period_type="calendar",
                      slice_by="department", slice_configs=None,
                      max_prior=5):
    """Build cumulative data for renderCumulative JS.

    mode: "prior" or "slice".
    period_type: "calendar" (shift by year) or "rolling" (shift by period length).
    slice_configs: dict {dim_key: (group_col, names, colors)}.
    """
    if df.empty or date_col not in df.columns:
        return None

    from utils.cumulative_current_year import setup_current_year_range, apply_current_year_projection
    today = pd.Timestamp.now().normalize()
    start, end, _cy_last_actual = setup_current_year_range(date_preset, mode, start, end)
    end_norm = end.normalize() if _cy_last_actual is not None else min(end.normalize(), today)
    start_norm = start.normalize()
    period_days = (end_norm - start_norm).days + 1
    if period_days < 2:
        return None

    # Force rolling when period exceeds 1 year (calendar shifts would overlap)
    if period_days > 365 and period_type == "calendar":
        period_type = "rolling"

    day_indices = list(range(period_days))

    def _daily(sub):
        if value_col and value_col in sub.columns:
            return sub.groupby(sub[date_col].dt.normalize())[value_col].sum()
        return sub.groupby(sub[date_col].dt.normalize()).size()

    def _cum_window(w_start, w_end):
        sub = df[(df[date_col] >= w_start) & (df[date_col] <= w_end)]
        daily = _daily(sub)
        idx = pd.date_range(w_start.normalize(), w_end.normalize(), freq="D")
        return daily.reindex(idx, fill_value=0).cumsum().tolist()

    current_vals = _cum_window(start, end_norm)

    # Tick labels
    tick_positions, tick_labels = [], []
    d = start_norm
    while d <= end_norm:
        if d.day == 1:
            tick_positions.append((d - start_norm).days)
            tick_labels.append(d.strftime("%b"))
        d += timedelta(days=1)

    def _plabel(s, e):
        same_yr = s.year == e.year
        if date_preset in ("ytd", "last_year") or (same_yr and s.month == 1 and e.month == 12):
            return str(s.year)
        if same_yr and s.month == e.month:
            return s.strftime("%b %Y")
        if same_yr:
            return f"{s.strftime('%b')} – {e.strftime('%b %Y')}"
        fmt = "%b '%y"
        return f"{s.strftime(fmt)} – {e.strftime(fmt)}"

    # Prior period windows
    data_min = df[date_col].min() if not df.empty else start
    windows = []
    if date_preset != "all":
        for i in range(1, max_prior + 1):
            if period_type == "calendar":
                try:
                    p_start = start - pd.DateOffset(years=i)
                    p_end = end_norm - pd.DateOffset(years=i)
                except Exception:
                    continue
            else:  # rolling
                shift = pd.Timedelta(days=period_days * i)
                p_start = start - shift
                p_end = end_norm - shift
            if p_end < data_min:
                break
            windows.append((_plabel(p_start, p_end), p_start, p_end))

    prior = []
    last_prior_start = None
    for pi, (label, p_start, p_end) in enumerate(windows):
        vals = _cum_window(p_start, p_end)
        if vals and any(v > 0 for v in vals):
            if len(vals) < period_days:
                vals += [vals[-1] if vals else 0] * (period_days - len(vals))
            elif len(vals) > period_days:
                vals = vals[:period_days]
            prior.append({"label": label, "values": vals, "color": PRIOR_PERIOD_COLORS[min(pi, len(PRIOR_PERIOD_COLORS) - 1)]})
            last_prior_start = p_start

    # Metadata for client-side control updates
    has_partial = (last_prior_start is not None
                   and last_prior_start.normalize() < data_min.normalize())
    _prior_meta = {
        "periodDays": period_days,
        "maxAvailablePriors": len(prior),
        "hasPartialPrior": has_partial,
    }

    current_label = _plabel(start, end_norm)
    if len(current_vals) < period_days:
        current_vals += [None] * (period_days - len(current_vals))

    # Slice breakdown (for bar chart in both modes, and for slice line/area)
    slice_breakdown = {"periods": [], "slices": []}
    series = []  # For slice mode line/area
    dates = []

    if slice_by == "total":
        # No grouping — single "Total" series
        all_windows = [(current_label, start, end_norm)] + \
                      [(l, s, e) for l, s, e in windows]
        periods_rev = [t[0] for t in reversed(all_windows)]
        total_vals = []
        for wlabel, ws, we in reversed(all_windows):
            sub = df[(df[date_col] >= ws) & (df[date_col] <= we)]
            if value_col and value_col in sub.columns:
                total_vals.append(float(sub[value_col].sum()))
            else:
                total_vals.append(len(sub))
        slice_breakdown = {
            "periods": periods_rev,
            "slices": [{"name": "Total", "values": total_vals, "color": PRIMARY}],
        }
        # Line/area series: single cumulative line
        current_sub = df[(df[date_col] >= start) & (df[date_col] <= end_norm)]
        date_range = pd.date_range(start_norm, end_norm, freq="D")
        dates = [d.strftime("%Y-%m-%d") for d in date_range]
        daily = _daily(current_sub).reindex(date_range, fill_value=0)
        series = [{
            "name": "Total",
            "values": daily.cumsum().tolist(),
            "color": PRIMARY,
        }]
    elif slice_configs and slice_by in slice_configs:
        group_col, names, colors = slice_configs[slice_by]

        # Bar breakdown: totals per period per slice
        all_windows = [(current_label, start, end_norm)] + \
                      [(l, s, e) for l, s, e in windows]
        all_totals, all_keys = [], set()
        for wlabel, ws, we in all_windows:
            sub = df[(df[date_col] >= ws) & (df[date_col] <= we)]
            if group_col in sub.columns:
                if value_col and value_col in sub.columns:
                    totals = sub.groupby(group_col)[value_col].sum().to_dict()
                else:
                    totals = sub.groupby(group_col).size().to_dict()
            else:
                totals = {}
            all_totals.append((wlabel, totals))
            all_keys.update(totals.keys())

        sorted_keys = [k for k in names if k in all_keys]
        periods_rev = [t[0] for t in reversed(all_totals)]
        slices = []
        for sk in sorted_keys:
            vals = [t[1].get(sk, 0) for t in reversed(all_totals)]
            slices.append({"name": sk, "values": vals,
                           "color": colors.get(sk, "#9CA3AF")})
        slice_breakdown = {"periods": periods_rev, "slices": slices}

        # Line/area series for slice mode: cumulative per group over current period
        current_sub = df[(df[date_col] >= start) & (df[date_col] <= end_norm)]
        date_range = pd.date_range(start_norm, end_norm, freq="D")
        dates = [d.strftime("%Y-%m-%d") for d in date_range]
        for sk in sorted_keys:
            if group_col in current_sub.columns:
                grp = current_sub[current_sub[group_col] == sk]
            else:
                grp = pd.DataFrame()
            daily = _daily(grp).reindex(date_range, fill_value=0)
            series.append({
                "name": sk,
                "values": daily.cumsum().tolist(),
                "color": colors.get(sk, "#9CA3AF"),
            })

    _result = {
        "mode": mode,
        "startDate": start_norm.isoformat(),
        "dayIndices": day_indices,
        "tickPositions": tick_positions,
        "tickLabels": tick_labels,
        "current": {
            "label": current_label,
            "values": current_vals,
            "color": PRIMARY,
            "endpoint": next((v for v in reversed(current_vals) if v is not None), 0),
        },
        "prior": prior,
        "sliceBreakdown": slice_breakdown,
        "series": series,
        "dates": dates,
        **_prior_meta,
        "height": 350,
        "yTitle": y_title,
    }
    if _cy_last_actual is not None:
        apply_current_year_projection(_result, _cy_last_actual, start)
    return _result


_BROAD_CATEGORIES = [
    "Medicare", "Medicaid", "Private", "Military/VA",
    "Workers Comp", "Tribal/IHS", "Self Pay", "Other/Unknown",
]

_BROAD_COLORS_MAP = {
    "Medicare": "#2196F3", "Medicaid": "#4CAF50",
    "Private": "#FF9800", "Military/VA": "#7C2A83",
    "Workers Comp": "#00BCD4", "Tribal/IHS": "#795548",
    "Self Pay": "#F44336", "Other/Unknown": "#9CA3AF",
}

from data.reviews_db import _REVENUE_ADJ_DEFAULTS


def _rev_adj_slider(category, color):
    """Build a labeled slider row for a payer category multiplier."""
    default = _REVENUE_ADJ_DEFAULTS.get(f"mult_{category}", 100)
    return dmc.Group(
        gap="xs", align="center", wrap="nowrap",
        children=[
            html.Div(
                style={"width": 8, "height": 8, "borderRadius": 4,
                       "backgroundColor": color, "flexShrink": 0},
            ),
            dmc.Text(category, size="xs", fw=500, style={"minWidth": 100, "flexShrink": 0}),
            dmc.Slider(
                id=f"{PAGE_ID}-rev-adj-mult-{category}",
                min=0, max=250, step=5, value=default,
                marks=[
                    {"value": 0, "label": "0%"},
                    {"value": 100, "label": "100%"},
                    {"value": 200, "label": "200%"},
                ],
                color="violet",
                style={"flex": 1},
            ),
            dmc.Text(
                id=f"{PAGE_ID}-rev-adj-mult-{category}-val",
                size="sm", fw=600, c=color,
                style={"minWidth": 45, "textAlign": "right"},
            ),
        ],
    )


def _build_payor_data(df, label_col, count_col=None, top_n=10):
    """Build payor distribution data.  Returns dict with actual + broad groupings.

    Uses DB payor mappings when available:
    - Actual chart: rolls up raw names into standardized_payor
    - Broad chart: uses broad_category from DB (falls back to _broad_payor())
    """
    if df.empty or label_col not in df.columns:
        return {"actual": {"labels": [], "values": [], "colors": []},
                "broad": {"labels": [], "values": [], "colors": []}}

    # Load DB mappings (small table, fast read)
    try:
        mapping = get_payor_mapping_dict()
    except Exception:
        mapping = {}

    df = df.copy()

    # Actual insurers — roll up via standardized_payor when mapped
    def _resolve_actual(name):
        if name in mapping and mapping[name]["standardized_payor"]:
            return mapping[name]["standardized_payor"]
        return name

    df["_actual"] = df[label_col].apply(_resolve_actual)

    if count_col:
        totals = df.groupby("_actual")[count_col].sum().sort_values(ascending=False)
    else:
        totals = df["_actual"].value_counts()

    top = totals.head(top_n)
    other_val = totals.iloc[top_n:].sum() if len(totals) > top_n else 0
    actual_labels = top.index.tolist()
    actual_values = top.values.tolist()
    if other_val > 0:
        actual_labels.append("Other")
        actual_values.append(int(other_val))
    actual_colors = [color_for_index(i) for i in range(len(actual_labels))]

    # Broad categories — use DB mapping with keyword fallback
    def _resolve_broad(name):
        if name in mapping and mapping[name]["broad_category"]:
            return mapping[name]["broad_category"]
        return _broad_payor(name)

    df["_broad"] = df[label_col].apply(_resolve_broad)
    broad_order = _BROAD_CATEGORIES
    broad_colors_map = _BROAD_COLORS_MAP
    if count_col:
        broad_totals = df.groupby("_broad")[count_col].sum()
    else:
        broad_totals = df["_broad"].value_counts()
    broad_labels = [b for b in broad_order if b in broad_totals.index]
    broad_values = [int(broad_totals[b]) for b in broad_labels]
    broad_colors = [broad_colors_map.get(b, "#9CA3AF") for b in broad_labels]

    return {
        "actual": {"labels": actual_labels, "values": actual_values, "colors": actual_colors},
        "broad": {"labels": broad_labels, "values": broad_values, "colors": broad_colors},
    }


# ---------------------------------------------------------------------------
# PHDSC category colors and helpers for payor trend / comparison charts
# ---------------------------------------------------------------------------

_PHDSC_CATEGORIES = [
    "1 - Medicare", "2 - Medicaid/CHIP", "3 - Other Govt",
    "4 - Corrections", "5 - Private", "6 - BCBS",
    "8 - No Payment", "9 - Other",
]

_PHDSC_COLORS_MAP = {
    "1 - Medicare": "#2196F3", "2 - Medicaid/CHIP": "#4CAF50",
    "3 - Other Govt": "#7C2A83", "4 - Corrections": "#795548",
    "5 - Private": "#FF9800", "6 - BCBS": "#00BCD4",
    "8 - No Payment": "#F44336", "9 - Other": "#9CA3AF",
}

_RIDGE_HEIGHT = 720


def _resolve_payer_group(df, label_col, mode, mapping):
    """Add ``_payer_group`` column based on *mode* (actual/broad/phdsc).

    Returns the modified dataframe (in-place) and an ordered list of group
    names + a color map.
    """
    df = df.copy()

    if mode == "broad":
        def _resolve(name):
            if name in mapping and mapping[name]["broad_category"]:
                return mapping[name]["broad_category"]
            return _broad_payor(name)
        df["_payer_group"] = df[label_col].apply(_resolve)
        ordered = [b for b in _BROAD_CATEGORIES if b in df["_payer_group"].unique()]
        cmap = {b: _BROAD_COLORS_MAP.get(b, "#9CA3AF") for b in ordered}
        return df, ordered, cmap

    if mode == "phdsc":
        def _resolve(name):
            if name in mapping and mapping[name].get("phdsc_category"):
                cat = mapping[name]["phdsc_category"]
                # Normalise bare digit → "N - Label"
                for pc in _PHDSC_CATEGORIES:
                    if pc.startswith(str(cat).split(" ")[0]):
                        return pc
                return cat
            return "9 - Other"
        df["_payer_group"] = df[label_col].apply(_resolve)
        ordered = [p for p in _PHDSC_CATEGORIES if p in df["_payer_group"].unique()]
        cmap = {p: _PHDSC_COLORS_MAP.get(p, "#9CA3AF") for p in ordered}
        return df, ordered, cmap

    # mode == "actual" — standardised payor names, top N + Other
    def _resolve(name):
        if name in mapping and mapping[name]["standardized_payor"]:
            return mapping[name]["standardized_payor"]
        return name
    df["_payer_group"] = df[label_col].apply(_resolve)
    totals = df["_payer_group"].value_counts()
    top_n = 12
    top_names = totals.head(top_n).index.tolist()
    if len(totals) > top_n:
        df["_payer_group"] = df["_payer_group"].where(
            df["_payer_group"].isin(top_names), "Other"
        )
        top_names.append("Other")
    ordered = top_names
    cmap = {g: color_for_index(i) for i, g in enumerate(ordered)}
    return df, ordered, cmap


def _sort_payor_groups(groups, sort_order, curr_counts, prior_counts=None):
    """Sort payer groups for ridgeline/comparison display (bottom→top)."""
    if sort_order == "alpha":
        return sorted(groups, reverse=True)
    if sort_order == "change" and prior_counts is not None:
        def _abs_change(g):
            c = curr_counts.get(g, 0)
            p = prior_counts.get(g, 0)
            if p > 0:
                return abs((c - p) / p)
            return float(c > 0)
        return sorted(groups, key=_abs_change)
    # volume: ascending for ridgeline (largest at top = last in list)
    return list(reversed(pd.Series(
        {g: curr_counts.get(g, 0) for g in groups}
    ).sort_values(ascending=False).index.tolist()))


def _assign_course_payer(bf, courses):
    """Attribute billing rows to treatment courses and assign majority-vote payer.

    Returns a DataFrame with one row per (PatientId, CourseId) pair:
    - ``_course_payer``: majority PrimaryInsurance for that course
    - ``_course_date``: CourseStartDate (for time-series trending)
    - ``_course_id``: unique key (PatientId + CourseId)

    Billing events not matching any course are grouped as one "no-course"
    episode per patient (using the patient's most common payer).
    """
    if bf.empty or courses.empty:
        return pd.DataFrame(columns=["_course_payer", "_course_date", "_course_id"])

    # Prepare courses with treatment date ranges
    needed = ["PatientId", "CourseId", "CourseStartDate",
              "FirstTreatmentDate", "LastTreatmentDate"]
    have = [c for c in needed if c in courses.columns]
    c = courses[have].dropna(subset=["PatientId"]).copy()
    if "CourseStartDate" not in c.columns:
        return pd.DataFrame(columns=["_course_payer", "_course_date", "_course_id"])

    c["_c_start"] = c.get("FirstTreatmentDate", c["CourseStartDate"]).fillna(c["CourseStartDate"])
    c["_c_end"] = c.get("LastTreatmentDate", pd.NaT)
    c["_c_end"] = c["_c_end"].fillna(c["CourseStartDate"] + pd.Timedelta(days=180))
    c = c.dropna(subset=["CourseStartDate"])

    # Join billing to courses on PatientId
    bf_cols = ["PatientId", "DateOfService", "PrimaryInsurance", "_payer_group"]
    bf_cols = [col for col in bf_cols if col in bf.columns]
    merged = bf[bf_cols].reset_index().merge(
        c[["PatientId", "CourseId", "CourseStartDate", "_c_start", "_c_end"]],
        on="PatientId", how="left",
    )

    # Keep only rows where DateOfService falls within course range
    in_range = merged[
        merged["CourseId"].notna() &
        (merged["DateOfService"] >= merged["_c_start"]) &
        (merged["DateOfService"] <= merged["_c_end"])
    ].copy()

    # For rows matching multiple courses, keep the one with nearest start
    if not in_range.empty:
        in_range["_dist"] = (in_range["DateOfService"] - in_range["_c_start"]).abs()
        in_range = in_range.sort_values("_dist").drop_duplicates(
            subset=["index"], keep="first",
        )

    # Majority-vote payer per course
    # Use first billing date in the period (not CourseStartDate) for trending,
    # so courses that started years ago don't create outlier data points.
    course_rows = []
    if not in_range.empty:
        for (pid, cid), grp in in_range.groupby(["PatientId", "CourseId"]):
            top_payer = grp["_payer_group"].mode()
            payer = top_payer.iloc[0] if len(top_payer) > 0 else "Other/Unknown"
            cdate = grp["DateOfService"].min()
            course_rows.append({
                "_course_payer": payer,
                "_course_date": cdate,
                "_course_id": f"{pid}_{cid}",
            })

    # Patients with no matching course → one "no-course" episode each
    matched_orig_idx = set(in_range["index"].tolist()) if not in_range.empty else set()
    unmatched = bf.loc[~bf.index.isin(matched_orig_idx)]
    if not unmatched.empty:
        for pid, grp in unmatched.groupby("PatientId"):
            top_payer = grp["_payer_group"].mode()
            payer = top_payer.iloc[0] if len(top_payer) > 0 else "Other/Unknown"
            cdate = grp["DateOfService"].min()
            course_rows.append({
                "_course_payer": payer,
                "_course_date": cdate,
                "_course_id": f"{pid}_nocourse",
            })

    if not course_rows:
        return pd.DataFrame(columns=["_course_payer", "_course_date", "_course_id"])

    result = pd.DataFrame(course_rows)
    result["_course_date"] = pd.to_datetime(result["_course_date"])
    return result


def _build_payor_trend_store(df, date_col, groups, cmap, count_by, sort_order,
                              prior_counts=None, value_col=None):
    """Build ridgeline trend store for payer groups — same format as diagRidge.

    Returns ``{combos: {W, M, Y}, groups, height}`` for the clientside JS.
    """
    if df.empty:
        return None

    group_col = "_payer_group"
    if value_col and value_col in df.columns:
        curr_counts = df.groupby(group_col)[value_col].sum()
    else:
        curr_counts = df[group_col].value_counts()
    sorted_groups = _sort_payor_groups(groups, sort_order, curr_counts, prior_counts)
    if not sorted_groups:
        return None

    combos = {}
    for agg in ("W", "M", "Y"):
        t = df[[date_col, group_col]].dropna(subset=[date_col]).copy()
        t["period"] = t[date_col].dt.to_period(agg).dt.to_timestamp()
        all_periods = sorted(t["period"].unique())
        dates = [d.isoformat() for d in all_periods]

        series = []
        for grp in sorted_groups:
            if count_by == "patient" and "PatientId" in df.columns:
                sub_full = df[df[group_col] == grp][[date_col, "PatientId"]].dropna(subset=[date_col]).copy()
                sub_full["period"] = sub_full[date_col].dt.to_period(agg).dt.to_timestamp()
                counts = sub_full.groupby("period")["PatientId"].nunique().reindex(all_periods, fill_value=0)
            elif value_col and value_col in df.columns:
                sub_full = df[df[group_col] == grp][[date_col, value_col]].dropna(subset=[date_col]).copy()
                sub_full["period"] = sub_full[date_col].dt.to_period(agg).dt.to_timestamp()
                counts = sub_full.groupby("period")[value_col].sum().reindex(all_periods, fill_value=0)
            else:
                sub = t[t[group_col] == grp]
                counts = sub.groupby("period").size().reindex(all_periods, fill_value=0)
            series.append({
                "name": grp,
                "values": [round(v, 2) if value_col else int(v) for v in counts.tolist()],
                "color": cmap.get(grp, CHART_COLORWAY[0]),
            })

        combos[agg] = {"dates": dates, "series": series}

    return {"combos": combos, "groups": sorted_groups, "height": _RIDGE_HEIGHT}


def _build_payor_comparison(df, date_col, groups, cmap, count_by, sort_order,
                             start, end, prior_windows, value_col=None,
                             unit="count"):
    """Horizontal grouped bar chart: current vs prior periods per payer group.

    *prior_windows*: list of (df_prior, prior_start, prior_end).
    *unit*: "count" for absolute values, "pct" for within-period percentages.
    Returns a Plotly go.Figure.
    """
    if df.empty:
        fig = empty_figure("No payer data available")
        fig.update_layout(height=_RIDGE_HEIGHT)
        return fig

    group_col = "_payer_group"
    is_dollar = value_col is not None
    is_pct = unit == "pct"

    def _count(sub):
        if sub.empty:
            return pd.Series(dtype=float if is_dollar else int)
        if is_dollar and value_col in sub.columns:
            return sub.groupby(group_col)[value_col].sum()
        if count_by == "patient" and "PatientId" in sub.columns:
            return sub.groupby(group_col)["PatientId"].nunique()
        return sub[group_col].value_counts()

    def _to_pct(series):
        """Convert a counts series to within-period percentages."""
        total = series.sum()
        if total > 0:
            return (series / total * 100).round(1)
        return series * 0

    curr_label = _plabel_payor(start, end)
    curr_counts_raw = _count(df)

    prior_data_raw = []
    for df_p, ps, pe in prior_windows:
        label = _plabel_payor(ps, pe)
        counts = _count(df_p) if df_p is not None and not df_p.empty else pd.Series(dtype=int)
        prior_data_raw.append((label, counts))

    # Collect all groups (use raw counts for sorting before pct conversion)
    all_group_set = set(curr_counts_raw.index)
    for _, pc in prior_data_raw:
        all_group_set.update(pc.index)
    all_group_set = all_group_set.intersection(set(groups) | {"Other"})

    first_prior_raw = prior_data_raw[0][1] if prior_data_raw else pd.Series(dtype=int)
    effective_sort = sort_order if prior_data_raw else "volume"
    all_groups = _sort_payor_groups(list(all_group_set), effective_sort, curr_counts_raw, first_prior_raw)

    # Convert to percentages if requested
    if is_pct:
        curr_counts = _to_pct(curr_counts_raw)
        prior_data = [(lbl, _to_pct(cnts)) for lbl, cnts in prior_data_raw]
    else:
        curr_counts = curr_counts_raw
        prior_data = prior_data_raw

    def _to_num(v):
        if is_pct:
            return round(float(v), 1)
        return round(float(v), 0) if is_dollar else int(v)

    def _fmt(v):
        if is_pct:
            return f"{v:.1f}%"
        return f"${v:,.0f}" if is_dollar else f"{v:,}"

    curr_vals = [_to_num(curr_counts.get(g, 0)) for g in all_groups]
    n_periods = 1 + len(prior_data)
    outside = n_periods >= 3

    fig = go.Figure()

    # Prior bars
    gray_alphas = [0.45, 0.30, 0.18]
    for idx in range(len(prior_data) - 1, -1, -1):
        plabel, pcounts = prior_data[idx]
        pvals = [_to_num(pcounts.get(g, 0)) for g in all_groups]
        alpha = gray_alphas[idx] if idx < len(gray_alphas) else 0.15
        fig.add_trace(go.Bar(
            x=pvals, y=all_groups, orientation="h",
            marker_color=f"rgba(156, 163, 175, {alpha})",
            name=plabel,
            text=[_fmt(v) for v in pvals],
            textposition="outside" if outside else "inside",
            insidetextanchor="end" if not outside else None,
            textangle=0,
            textfont=dict(size=11 if outside else 13,
                          color="#374151" if outside else "#6B7280"),
            hovertemplate=[
                f"<b>{g}</b><br>{plabel}: {_fmt(v)}<extra></extra>"
                for g, v in zip(all_groups, pvals)
            ],
        ))

    # Current bars (colored)
    bar_colors = [cmap.get(g, CHART_COLORWAY[0]) for g in all_groups]
    fig.add_trace(go.Bar(
        x=curr_vals, y=all_groups, orientation="h",
        marker_color=bar_colors,
        name=curr_label,
        text=[_fmt(v) for v in curr_vals],
        textposition="outside" if outside else "inside",
        insidetextanchor="end" if not outside else None,
        textangle=0,
        textfont=dict(size=11 if outside else 13,
                      color="#374151" if outside else "white"),
        hovertemplate=[
            f"<b>{g}</b><br>{curr_label}: {_fmt(v)}<extra></extra>"
            for g, v in zip(all_groups, curr_vals)
        ],
    ))

    # Delta annotations — always compute % change from raw counts, not pct values
    # Skip annotations entirely when no prior periods
    annotations = []
    if prior_data_raw:
        first_prior_display = prior_data[0][1] if prior_data else pd.Series(dtype=float)
        first_prior_vals = [_to_num(first_prior_display.get(g, 0)) for g in all_groups]
        all_vals = curr_vals + first_prior_vals
        for _, pc in prior_data:
            all_vals += [_to_num(pc.get(g, 0)) for g in all_groups]
        max_val = max(all_vals) if all_vals else 0
        annot_x = max_val * 1.05 if max_val > 0 else 1

        first_prior_raw_counts = prior_data_raw[0][1]
        for i, g in enumerate(all_groups):
            c_raw = float(curr_counts_raw.get(g, 0))
            p_raw = float(first_prior_raw_counts.get(g, 0))
            if p_raw > 0:
                pct = (c_raw - p_raw) / p_raw * 100
                if pct > 0:
                    txt = f"▲ {pct:.0f}%"
                    color = "#10B981"
                elif pct < 0:
                    txt = f"▼ {abs(pct):.0f}%"
                    color = "#EF4444"
                else:
                    txt = "—"
                    color = "#9CA3AF"
            elif c_raw > 0:
                txt = "● new"
                color = "#3B82F6"
            else:
                txt = ""
                color = "#9CA3AF"
            if txt:
                annotations.append(dict(
                    x=annot_x, y=g, text=txt, showarrow=False,
                    font=dict(size=13, color=color, family=FONT_FAMILY),
                    xanchor="left", yanchor="middle",
                ))
    else:
        max_val = max(curr_vals) if curr_vals else 0
        annot_x = max_val * 1.05 if max_val > 0 else 1

    apply_default_layout(fig, barmode="group")
    fig.update_layout(
        height=_RIDGE_HEIGHT,
        xaxis_title="", yaxis_title="",
        xaxis=dict(visible=False, range=[0, annot_x * 1.15]),
        yaxis=dict(automargin="left+top+bottom", ticklabelstandoff=0,
                   categoryorder="array", categoryarray=all_groups,
                   tickfont=dict(size=12)),
        margin=dict(l=0, r=60, t=24, b=12),
        showlegend=True,
        legend=dict(
            orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0,
            font=dict(size=11),
        ),
        bargroupgap=0.15,
        annotations=annotations,
    )
    return fig


def _plabel_payor(start, end):
    """Smart period label for date ranges."""
    same_year = start.year == end.year
    same_month = same_year and start.month == end.month
    if same_month:
        return start.strftime("%b %Y")
    if same_year:
        if start.month == 1 and end.month == 12:
            return str(start.year)
        return f"{start.strftime('%b')} – {end.strftime('%b %Y')}"
    return f"{start.strftime('%b %y')} – {end.strftime('%b %y')}"


# ---------------------------------------------------------------------------
# Cached enriched billing dataframe
# ---------------------------------------------------------------------------

_enriched_cache = {"key": None, "df": None}


def _get_enriched_billing():
    """Return billing df with Category, ChargeStatus, wRVU columns added.

    Caches result — only recomputes when the underlying loader cache changes
    (i.e., new data loaded).
    """
    from data.loader import load_billing, load_rvu_lookup, load_opps_lookup

    billing = load_billing()
    rvu = load_rvu_lookup()
    opps = load_opps_lookup()

    # Use object ids as cache key (lru_cache returns same object if unchanged)
    key = (id(billing), id(rvu), id(opps))
    if _enriched_cache["key"] == key and _enriched_cache["df"] is not None:
        return _enriched_cache["df"]

    df = billing.copy()
    # Ensure Quantity column exists and defaults to 1
    if "Quantity" not in df.columns:
        df["Quantity"] = 1
    else:
        df["Quantity"] = pd.to_numeric(df["Quantity"], errors="coerce").fillna(1).astype(int).clip(lower=1)
    # Auto-exclude incomplete charges (credited/waived now filter-controlled)
    if "Completed" in df.columns:
        df = df[df["Completed"] == "Yes"]

    # Vectorized: build lookup dicts from unique codes, then map
    unique_codes = df["ProcedureCode"].dropna().unique()
    strip_map = {c: _strip_modifier(c) for c in unique_codes}
    df["_base_code"] = df["ProcedureCode"].map(strip_map).fillna("")
    unique_base = df["_base_code"].unique()
    cat_map = {b: _assign_category(b) for b in unique_base}
    df["Category"] = df["_base_code"].map(cat_map)
    subcat_map = {b: _CODE_TO_SUBCATEGORY.get(b, "Other") for b in unique_base}
    df["Subcategory"] = df["_base_code"].map(subcat_map)
    status_map = {c: _derive_charge_status(c) for c in unique_codes}
    df["ChargeStatus"] = df["ProcedureCode"].map(status_map)
    if not rvu.empty:
        df = _merge_rvu(df, rvu)
    else:
        for _c in ["wRVU", "Fac_PE_RVU", "NonFac_PE_RVU", "MP_RVU",
                    "Pro_Total_RVU", "Fac_Total_RVU",
                    "TC_wRVU", "TC_PE_RVU", "TC_MP_RVU"]:
            df[_c] = 0.0

    # Merge OPPS payment rates for hospital revenue (keyed by base HCPCS + year)
    if not opps.empty and "DateOfService" in df.columns:
        df["_opps_yr"] = df["DateOfService"].dt.year
        opps_rates = opps[opps["PaymentRate"] > 0][["HCPCS", "Year", "PaymentRate"]].copy()
        opps_rates = opps_rates.drop_duplicates(subset=["HCPCS", "Year"], keep="last")
        opps_key = dict(zip(
            opps_rates["HCPCS"] + "|" + opps_rates["Year"].astype(str),
            opps_rates["PaymentRate"],
        ))
        df["OPPS_Rate"] = (df["_base_code"] + "|" + df["_opps_yr"].astype(str)).map(opps_key).fillna(0)
        df.drop(columns=["_opps_yr"], inplace=True)
    else:
        df["OPPS_Rate"] = 0.0

    # Scale RVU and rate columns by Quantity (per-unit → total for this line)
    qty = df["Quantity"]
    for _rc in ["wRVU", "Fac_PE_RVU", "NonFac_PE_RVU", "MP_RVU",
                "Pro_Total_RVU", "Fac_Total_RVU",
                "TC_wRVU", "TC_PE_RVU", "TC_MP_RVU", "OPPS_Rate"]:
        if _rc in df.columns:
            df[_rc] = df[_rc] * qty

    # Payor: use billing's own PayorName (81.6% populated), then fall back to
    # Referrals Payer (per-patient, covers 98% of the gap) for the rest.
    import re as _re_payor
    from data.loader import load_referrals

    if "PayorName" in df.columns:
        df["PrimaryInsurance"] = df["PayorName"].where(
            df["PayorName"].notna() & (df["PayorName"].str.strip() != "")
        )
    else:
        df["PrimaryInsurance"] = np.nan

    # Referral fallback for rows missing PayorName — match to the closest
    # referral by date so a 2024 billing row doesn't pick up a 2020 payer.
    mask = df["PrimaryInsurance"].isna()
    if mask.any() and "PatientId" in df.columns and "DateOfService" in df.columns:
        def _parse_ref_payer(v):
            if pd.isna(v):
                return None
            first_line = str(v).split("\n")[0].strip()
            return _re_payor.sub(r"\s*\[\d+\]\s*$", "", first_line).strip() or None

        try:
            referrals = load_referrals()
        except Exception:
            referrals = pd.DataFrame()
        if not referrals.empty and "Payer" in referrals.columns and "MRN" in referrals.columns:
            ref_payer = referrals[["MRN", "Created", "Payer"]].copy()
            ref_payer["RefPayer"] = ref_payer["Payer"].apply(_parse_ref_payer)
            ref_payer = ref_payer.dropna(subset=["RefPayer", "Created"])
            ref_payer = ref_payer.sort_values("Created")

            # Prepare billing rows that need filling
            need = df.loc[mask, ["PatientId", "DateOfService"]].copy()
            need["_MRN"] = pd.to_numeric(need["PatientId"], errors="coerce").astype("Int64")
            need = need.dropna(subset=["_MRN", "DateOfService"])
            need = need.sort_values("DateOfService")

            if not need.empty:
                matched = pd.merge_asof(
                    need[["_MRN", "DateOfService"]].rename(columns={"_MRN": "MRN"}),
                    ref_payer[["MRN", "Created", "RefPayer"]],
                    left_on="DateOfService", right_on="Created",
                    by="MRN", direction="backward",
                )
                # Map back by original index
                matched.index = need.index
                df.loc[matched.index, "PrimaryInsurance"] = matched["RefPayer"]

    df["PrimaryInsurance"] = df["PrimaryInsurance"].fillna("Unknown")

    # Pre-compute per-row revenue estimates for trend/cumulative charts
    # Professional: [(wRVU × W_GPCI) + (PE × PE_GPCI) + (MP × MP_GPCI)] × CF × HPSA
    # Hospital: OPPS wage-adjusted with SCH (Lacey/Centralia) or PFS TC (Aberdeen)
    from data.loader import load_gpci, load_opps_params
    gpci = load_gpci()
    opps_params = load_opps_params()
    if "DateOfService" in df.columns and not df.empty:
        yrs = df["DateOfService"].dt.year
        w_g = yrs.map({y: g[0] for y, g in gpci.items()}).fillna(1.0)
        pe_g = yrs.map({y: g[1] for y, g in gpci.items()}).fillna(1.0)
        mp_g = yrs.map({y: g[2] for y, g in gpci.items()}).fillna(1.0)
        cf = yrs.map(_CMS_CF).fillna(_CMS_CF_DEFAULT)

        # PE: For split codes (-26), Fac and NonFac PE are identical.
        # For non-split codes (E&M etc.), POS determines rate:
        #   POS 22 (Lacey/Centralia) → Fac_PE
        #   POS 11 (Aberdeen) → NonFac_PE
        is_ab = df["Department"] == "Aberdeen" if "Department" in df.columns else False
        pe = df["Fac_PE_RVU"].copy()
        if hasattr(is_ab, 'any') and is_ab.any():
            pe.loc[is_ab] = df.loc[is_ab, "NonFac_PE_RVU"]
        hpsa = pd.Series(1.0, index=df.index)
        if "Department" in df.columns:
            hpsa.loc[df["Department"].isin(["Centralia", "Aberdeen"])] = 1.10
        df["Pro_Revenue"] = (df["wRVU"] * w_g + pe * pe_g + df["MP_RVU"] * mp_g) * cf * hpsa

        # Hospital revenue per row
        is_ab = df["Department"] == "Aberdeen" if "Department" in df.columns else pd.Series(False, index=df.index)
        # OPPS wage-adjusted for Lacey/Centralia
        wi = yrs.map({y: p[1] for y, p in opps_params.items()}).fillna(1.0)
        labor = yrs.map({y: p[2] for y, p in opps_params.items()}).fillna(0.60)
        sch = yrs.map({y: p[3] for y, p in opps_params.items()}).fillna(1.071)
        opps_adj = df["OPPS_Rate"] * (labor * wi + (1 - labor)) * sch
        # PFS TC for Aberdeen (no HPSA)
        tc_adj = (df["TC_wRVU"] * w_g + df["TC_PE_RVU"] * pe_g + df["TC_MP_RVU"] * mp_g) * cf
        df["Hosp_Revenue"] = 0.0
        df.loc[~is_ab, "Hosp_Revenue"] = opps_adj[~is_ab]
        df.loc[is_ab, "Hosp_Revenue"] = tc_adj[is_ab]
        df["Total_Revenue"] = df["Pro_Revenue"] + df["Hosp_Revenue"]
    else:
        df["Pro_Revenue"] = 0.0
        df["Hosp_Revenue"] = 0.0
        df["Total_Revenue"] = 0.0

    _enriched_cache["key"] = key
    _enriched_cache["df"] = df
    return df


# ---------------------------------------------------------------------------
# Filter result cache — shared between main and cumulative callbacks
# ---------------------------------------------------------------------------

_filter_cache = {"key": None, "result": None}


def _load_and_filter_billing_cached(**kwargs):
    """Cached wrapper — avoids re-filtering when main and cumulative callbacks
    fire on the same filter state (sequential execution in single-threaded Dash)."""
    key_parts = []
    for k in sorted(kwargs.keys()):
        v = kwargs[k]
        if isinstance(v, list):
            v = tuple(v) if v else ()
        key_parts.append((k, v))
    key = tuple(key_parts)
    if _filter_cache["key"] == key and _filter_cache["result"] is not None:
        return _filter_cache["result"]
    result = _load_and_filter_billing(**kwargs)
    _filter_cache["key"] = key
    _filter_cache["result"] = result
    return result


# ---------------------------------------------------------------------------
# Filter Bar
# ---------------------------------------------------------------------------

def _chip_dropdown(page_id, name, chip_id, multiple=True, children=None):
    """Reusable chip-dropdown: button + clear + floating panel."""
    return html.Div(
        children=[
            html.Div(
                children=[
                    dmc.Button(
                        name,
                        id=f"{page_id}-{chip_id}-trigger",
                        variant="default",
                        size="sm",
                        rightSection=DashIconify(icon="mdi:chevron-down", width=14),
                    ),
                    dmc.ActionIcon(
                        DashIconify(icon="mdi:close-circle", width=18),
                        id=f"{page_id}-{chip_id}-clear",
                        variant="subtle",
                        color="gray",
                        size="sm",
                        className="wf-filter-clear-btn",
                    ),
                ],
                style={"position": "relative", "display": "inline-block"},
            ),
            dmc.Paper(
                id=f"{page_id}-{chip_id}-panel",
                children=children or [],
                p="xs",
                shadow="md",
                withBorder=True,
                radius="md",
                className="wf-chip-dropdown",
                style={"display": "none"},
            ),
        ],
        style={"position": "relative", "display": "inline-block"},
    )


def _build_filter_bar():
    """Two-row filter bar: dimension filters + date controls."""
    return dmc.Paper(
        children=[
            # Row 1: dimension filters
            dmc.Group(
                children=[
                    department_chips(PAGE_ID),
                    # Physician dropdown + role toggle
                    _chip_dropdown(PAGE_ID, "Physician", "physician", multiple=False, children=[
                        dmc.SegmentedControl(
                            id=f"{PAGE_ID}-filter-physician-role",
                            data=[
                                {"value": "supervising", "label": "Supervising"},
                                {"value": "attending", "label": "Attending"},
                            ],
                            value="supervising",
                            size="xs",
                            fullWidth=True,
                            mb="xs",
                        ),
                        dmc.ChipGroup(
                            children=[],
                            id=f"{PAGE_ID}-filter-physician",
                            multiple=False,
                        ),
                    ]),
                    cpt_accordion(PAGE_ID),
                    dmc.SegmentedControl(
                        id=f"{PAGE_ID}-filter-codetype",
                        data=[
                            {"value": "all", "label": "All"},
                            {"value": "pro", "label": "Professional"},
                            {"value": "hospital", "label": "Hospital"},
                        ],
                        value="all",
                        size="xs",
                    ),
                    dmc.SegmentedControl(
                        id=f"{PAGE_ID}-filter-charge-status",
                        data=[
                            {"value": "all", "label": "All"},
                            {"value": "Billable", "label": "Billable"},
                            {"value": "No Charge", "label": "No Charge"},
                        ],
                        value="Billable",
                        size="xs",
                    ),
                    # Charge status dropdown panel
                    _chip_dropdown(PAGE_ID, "Status", "status", children=[
                        # --- Professional section ---
                        dmc.Text("Professional", size="xs", fw=600, c=PRIMARY, mb=4),
                        dmc.Group(
                            children=[
                                dmc.Text("Reviewed", size="xs", c="dimmed", w=70),
                                dmc.SegmentedControl(
                                    id=f"{PAGE_ID}-filter-pro-reviewed",
                                    data=[
                                        {"value": "all", "label": "All"},
                                        {"value": "yes", "label": "Yes"},
                                        {"value": "no", "label": "No"},
                                    ],
                                    value="yes",
                                    size="xs",
                                ),
                            ],
                            gap="xs", align="center", mb=2,
                        ),
                        dmc.Group(
                            children=[
                                dmc.Text("Exported", size="xs", c="dimmed", w=70),
                                dmc.SegmentedControl(
                                    id=f"{PAGE_ID}-filter-pro-exported",
                                    data=[
                                        {"value": "all", "label": "All"},
                                        {"value": "yes", "label": "Yes"},
                                        {"value": "no", "label": "No"},
                                    ],
                                    value="all",
                                    size="xs",
                                ),
                            ],
                            gap="xs", align="center", mb=6,
                        ),
                        dmc.Group(
                            children=[
                                dmc.Switch(
                                    id=f"{PAGE_ID}-filter-excl-credited",
                                    label="Exclude Credited",
                                    size="xs",
                                    checked=True,
                                ),
                                dmc.Switch(
                                    id=f"{PAGE_ID}-filter-excl-waived",
                                    label="Exclude Waived",
                                    size="xs",
                                    checked=True,
                                ),
                            ],
                            gap="md", mb=8,
                        ),
                        dmc.Divider(mb=8),
                        # --- Hospital section ---
                        dmc.Text("Hospital", size="xs", fw=600, c=PRIMARY, mb=4),
                        dmc.Group(
                            children=[
                                dmc.Text("Reviewed", size="xs", c="dimmed", w=70),
                                dmc.SegmentedControl(
                                    id=f"{PAGE_ID}-filter-hosp-reviewed",
                                    data=[
                                        {"value": "all", "label": "All"},
                                        {"value": "yes", "label": "Yes"},
                                        {"value": "no", "label": "No"},
                                    ],
                                    value="yes",
                                    size="xs",
                                ),
                            ],
                            gap="xs", align="center", mb=2,
                        ),
                        dmc.Group(
                            children=[
                                dmc.Text("Exported", size="xs", c="dimmed", w=70),
                                dmc.SegmentedControl(
                                    id=f"{PAGE_ID}-filter-hosp-exported",
                                    data=[
                                        {"value": "all", "label": "All"},
                                        {"value": "yes", "label": "Yes"},
                                        {"value": "no", "label": "No"},
                                    ],
                                    value="yes",
                                    size="xs",
                                ),
                            ],
                            gap="xs", align="center", mb=6,
                        ),
                        dmc.Group(
                            children=[
                                dmc.Switch(
                                    id=f"{PAGE_ID}-filter-hosp-excl-credited",
                                    label="Exclude Credited",
                                    size="xs",
                                    checked=True,
                                ),
                                dmc.Switch(
                                    id=f"{PAGE_ID}-filter-hosp-excl-waived",
                                    label="Exclude Waived",
                                    size="xs",
                                    checked=True,
                                ),
                            ],
                            gap="md",
                        ),
                    ]),
                    dmc.Group(
                        children=[
                            dmc.Text("Smoothing", size="xs", c="#6B7280", fw=500),
                            dmc.Slider(
                                id=f"{PAGE_ID}-smooth-slider",
                                min=0, max=1, step=0.01, value=0.3,
                                size="xs", showLabelOnHover=False,
                                w=120, updatemode="drag",
                            ),
                        ],
                        gap=6, align="center",
                    ),
                ],
                gap="md", wrap="wrap", align="center",
            ),
            # Row 2: date controls
            dmc.Group(
                children=[
                    dmc.Select(
                        id=f"{PAGE_ID}-filter-date-preset",
                        data=[
                            {"value": "12mo", "label": "Prior 12 mo"},
                            {"value": "6mo", "label": "Prior 6 mo"},
                            {"value": "3mo", "label": "Prior 3 mo"},
                            {"value": "30d", "label": "Prior 30 days"},
                            {"value": "ytd", "label": "Year to Date"},
                            {"value": "current_year", "label": "Current Year"},
                            {"value": "last_year", "label": "Last Year"},
                            {"value": "this_month", "label": "This Month"},
                            {"value": "last_month", "label": "Last Month"},
                            {"value": "all", "label": "All Time"},
                            {"value": "custom", "label": "Custom Range"},
                        ],
                        value=_DEFAULT_DATE_PRESET,
                        size="xs", w=150, allowDeselect=False,
                        leftSection=DashIconify(icon="mdi:clock-outline", width=14),
                        comboboxProps={"zIndex": 500, "offset": 2},
                        maxDropdownHeight=400,
                    ),
                    dmc.Paper(
                        dcc.DatePickerRange(
                            id=f"{PAGE_ID}-filter-daterange",
                            display_format="MMM D, YYYY",
                            start_date_placeholder_text="Start",
                            end_date_placeholder_text="End",
                            clearable=True,
                            number_of_months_shown=2,
                            minimum_nights=0,
                            start_date=idx_to_date(
                                preset_to_slider_val(_DEFAULT_DATE_PRESET, MAX_IDX)[0]
                            ).strftime("%Y-%m-%d"),
                            end_date=idx_to_date(
                                preset_to_slider_val(_DEFAULT_DATE_PRESET, MAX_IDX)[1],
                                end_of_month=True,
                            ).strftime("%Y-%m-%d"),
                            className="wf-date-picker-range",
                        ),
                        px="xs", py=4, radius="sm", withBorder=True,
                        className="wf-datepicker-wrapper",
                    ),
                    dmc.Box(
                        children=[
                            html.Div(id=f"{PAGE_ID}-date-range-label", style={"display": "none"}),
                            dmc.RangeSlider(
                                id=f"{PAGE_ID}-date-slider",
                                min=0, max=MAX_IDX, step=1,
                                value=preset_to_slider_val(_DEFAULT_DATE_PRESET, MAX_IDX),
                                marks=SLIDER_MARKS,
                                color="violet", size="sm", minRange=0,
                            ),
                        ],
                        style={"flex": "1", "minWidth": "280px"},
                    ),
                ],
                gap="md", align="center", mt="xs",
            ),
        ],
        p="sm", px="md", radius="md", shadow="xs", withBorder=True,
    )


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------

_SLICE_TOGGLE = [
    {"value": "total", "label": "Total"},
    {"value": "category", "label": "Category"},
    {"value": "subcategory", "label": "Sub-Cat"},
    {"value": "department", "label": "Site"},
    {"value": "physician", "label": "MD"},
    {"value": "cpt", "label": "CPT"},
]
_AGG_TOGGLE = [
    {"value": "W", "label": "Weekly"},
    {"value": "M", "label": "Monthly"},
    {"value": "Y", "label": "Yearly"},
]
_PAYOR_MODE_TOGGLE = [
    {"value": "actual", "label": "Actual"},
    {"value": "broad", "label": "Broad"},
    {"value": "phdsc", "label": "PHDSC"},
]
_PAYOR_COUNT_BY = [
    {"value": "event", "label": "Per Event"},
    {"value": "patient", "label": "Per Patient"},
    {"value": "course", "label": "Per Course"},
    {"value": "dollar", "label": "Per $"},
]
_CHART_TYPES = [
    {"value": "area", "label": "Area"},
    {"value": "line", "label": "Line"},
    {"value": "bar", "label": "Bar"},
]
_CUM_CHART_TYPES = [
    {"value": "line", "label": "Line"},
    {"value": "area", "label": "Area"},
    {"value": "bar", "label": "Bar"},
]

layout = dmc.Stack(
    gap=16,
    className="page-content",
    children=[
        # Sticky header
        dmc.Box(
            className="page-sticky-header",
            children=[
                dmc.Group(
                    children=[
                        dmc.Title("Billing", order=2, className="page-title"),
                        dmc.ActionIcon(
                            DashIconify(icon="tabler:receipt-2", width=20),
                            id=f"{PAGE_ID}-irm-btn",
                            variant="subtle", color="violet", size="lg",
                        ),
                    ],
                    justify="center",
                    gap="xs",
                ),
                html.Div(
                    style={"position": "relative"},
                    children=[
                        _build_filter_bar(),
                        html.Div(
                            id=f"{PAGE_ID}-grid-filter-badge",
                            children=dmc.Tooltip(
                                label="Table column filters are active — charts reflect the filtered subset",
                                position="left", withArrow=True, multiline=True, w=220,
                                children=dmc.Badge(
                                    "Table Filtered",
                                    color="red", variant="filled", size="md",
                                    leftSection=DashIconify(icon="mdi:filter", width=14),
                                ),
                            ),
                            style={
                                "position": "absolute", "top": -12, "right": 8,
                                "zIndex": 10, "display": "none", "cursor": "pointer",
                            },
                        ),
                    ],
                ),
            ],
        ),

        # KPI row — dynamic (zero-count categories hidden)
        dmc.Group(
            id=f"{PAGE_ID}-kpi-row",
            gap="sm",
            grow=True,
            wrap="nowrap",
            style={"overflow": "hidden"},
            children=[kpi_placeholder() for _ in range(5)],
        ),

        # Dollar estimate row — thin summary bar
        dmc.Group(
            id=f"{PAGE_ID}-dollar-row",
            gap="md",
            grow=True,
        ),

        # Row 1: Volume Trend + Cumulative
        dmc.Grid(
            gutter="md",
            children=[
                dmc.GridCol(
                    chart_card(
                        f"{PAGE_ID}-chart-vol-trend",
                        "Billing Volume Trend",
                        settings_id=f"{PAGE_ID}-vol",
                        chart_types=_CHART_TYPES,
                        chart_type_default="bar",
                        show_smooth=True,
                        smooth_max=50, smooth_default=15,
                        paper_padding="md",
                        extra_controls_left=[
                            dmc.SegmentedControl(
                                id=f"{PAGE_ID}-vol-slice",
                                data=_SLICE_TOGGLE, value="category", size="xs",
                            ),
                        ],
                        extra_controls=[
                            dmc.SegmentedControl(
                                id=f"{PAGE_ID}-vol-agg",
                                data=_AGG_TOGGLE, value="M", size="xs",
                            ),
                        ],
                    ),
                    span={"base": 12, "md": 6},
                ),
                dmc.GridCol(
                    chart_card(
                        f"{PAGE_ID}-chart-vol-cum",
                        "Cumulative Volume",
                        settings_id=f"{PAGE_ID}-volcum",
                        chart_types=_CUM_CHART_TYPES,
                        show_smooth=True,
                        smooth_min=0, smooth_max=1,
                        smooth_step=0.05, smooth_default=0.1,
                        show_prior_periods=True,
                        show_project_toggle=True,
                        prior_periods_default=3,
                        paper_padding="md",
                        extra_controls=[
                            dmc.SegmentedControl(
                                id=f"{PAGE_ID}-volcum-mode",
                                data=[{"value": "prior", "label": "Prior Periods"},
                                      {"value": "slice", "label": "Slice By"}],
                                value="prior", size="xs",
                            ),
                            dmc.SegmentedControl(
                                id=f"{PAGE_ID}-volcum-period-type",
                                data=[{"value": "calendar", "label": "Calendar"},
                                      {"value": "rolling", "label": "Rolling"}],
                                value="calendar", size="xs",
                            ),
                            dmc.SegmentedControl(
                                id=f"{PAGE_ID}-volcum-slice",
                                data=_SLICE_TOGGLE, value="total", size="xs",
                            ),
                        ],
                    ),
                    span={"base": 12, "md": 6},
                ),
            ],
        ),

        # Row 2: wRVU Trend + Cumulative (hidden when Hospital component selected)
        dmc.Grid(
            id=f"{PAGE_ID}-rvu-row",
            gutter="md",
            children=[
                dmc.GridCol(
                    chart_card(
                        f"{PAGE_ID}-chart-rvu-trend",
                        "wRVU Trend",
                        settings_id=f"{PAGE_ID}-rvu",
                        chart_types=_CHART_TYPES,
                        chart_type_default="bar",
                        show_smooth=True,
                        smooth_max=50, smooth_default=15,
                        paper_padding="md",
                        extra_controls_left=[
                            dmc.SegmentedControl(
                                id=f"{PAGE_ID}-rvu-slice",
                                data=_SLICE_TOGGLE, value="physician", size="xs",
                            ),
                        ],
                        extra_controls=[
                            dmc.SegmentedControl(
                                id=f"{PAGE_ID}-rvu-agg",
                                data=_AGG_TOGGLE, value="M", size="xs",
                            ),
                        ],
                    ),
                    span={"base": 12, "md": 6},
                ),
                dmc.GridCol(
                    chart_card(
                        f"{PAGE_ID}-chart-rvu-cum",
                        "Cumulative wRVU",
                        settings_id=f"{PAGE_ID}-rvucum",
                        chart_types=_CUM_CHART_TYPES,
                        show_smooth=True,
                        smooth_min=0, smooth_max=1,
                        smooth_step=0.05, smooth_default=0.1,
                        show_prior_periods=True,
                        show_project_toggle=True,
                        prior_periods_default=3,
                        paper_padding="md",
                        extra_controls=[
                            dmc.SegmentedControl(
                                id=f"{PAGE_ID}-rvucum-mode",
                                data=[{"value": "prior", "label": "Prior Periods"},
                                      {"value": "slice", "label": "Slice By"}],
                                value="prior", size="xs",
                            ),
                            dmc.SegmentedControl(
                                id=f"{PAGE_ID}-rvucum-period-type",
                                data=[{"value": "calendar", "label": "Calendar"},
                                      {"value": "rolling", "label": "Rolling"}],
                                value="calendar", size="xs",
                            ),
                            dmc.SegmentedControl(
                                id=f"{PAGE_ID}-rvucum-slice",
                                data=_SLICE_TOGGLE, value="total", size="xs",
                            ),
                        ],
                    ),
                    span={"base": 12, "md": 6},
                ),
            ],
        ),

        # Row 3: Revenue ($) Trend + Cumulative
        dmc.Grid(
            id=f"{PAGE_ID}-revenue-chart-row",
            gutter="md",
            children=[
                dmc.GridCol(
                    chart_card(
                        f"{PAGE_ID}-chart-dollar-trend",
                        "Revenue Trend ($)",
                        settings_id=f"{PAGE_ID}-dollar",
                        chart_types=_CHART_TYPES,
                        show_smooth=True,
                        smooth_max=50, smooth_default=15,
                        paper_padding="md",
                        extra_controls_left=[
                            dmc.SegmentedControl(
                                id=f"{PAGE_ID}-dollar-slice",
                                data=_SLICE_TOGGLE, value="department", size="xs",
                            ),
                        ],
                        extra_controls=[
                            dmc.SegmentedControl(
                                id=f"{PAGE_ID}-dollar-agg",
                                data=_AGG_TOGGLE, value="W", size="xs",
                            ),
                        ],
                    ),
                    span={"base": 12, "md": 6},
                ),
                dmc.GridCol(
                    chart_card(
                        f"{PAGE_ID}-chart-dollar-cum",
                        "Cumulative Revenue ($)",
                        settings_id=f"{PAGE_ID}-dollarcum",
                        chart_types=_CUM_CHART_TYPES,
                        show_smooth=True,
                        smooth_min=0, smooth_max=1,
                        smooth_step=0.05, smooth_default=0.1,
                        show_prior_periods=True,
                        show_project_toggle=True,
                        prior_periods_default=3,
                        paper_padding="md",
                        extra_controls=[
                            dmc.SegmentedControl(
                                id=f"{PAGE_ID}-dollarcum-mode",
                                data=[{"value": "prior", "label": "Prior Periods"},
                                      {"value": "slice", "label": "Slice By"}],
                                value="prior", size="xs",
                            ),
                            dmc.SegmentedControl(
                                id=f"{PAGE_ID}-dollarcum-period-type",
                                data=[{"value": "calendar", "label": "Calendar"},
                                      {"value": "rolling", "label": "Rolling"}],
                                value="calendar", size="xs",
                            ),
                            dmc.SegmentedControl(
                                id=f"{PAGE_ID}-dollarcum-slice",
                                data=_SLICE_TOGGLE, value="total", size="xs",
                            ),
                        ],
                    ),
                    span={"base": 12, "md": 6},
                ),
            ],
        ),

        # Row 4: Payor Trend + Comparison
        # Shared controls row (above the two charts)
        dmc.Paper(
            p="xs", px="sm", radius="md", withBorder=True, mt="md", mb=8,
            children=[
                dmc.Group(
                    gap="md", align="center",
                    children=[
                        dmc.Group(
                            gap=6, align="center",
                            children=[
                                DashIconify(icon="tabler:building-bank", width=16, color=PRIMARY),
                                dmc.Text("Payor Analysis", size="sm", fw=600, c=PRIMARY),
                            ],
                        ),
                        dmc.SegmentedControl(
                            id=f"{PAGE_ID}-payor-mode",
                            data=_PAYOR_MODE_TOGGLE, value="broad", size="xs",
                        ),
                        dmc.SegmentedControl(
                            id=f"{PAGE_ID}-payor-count-by",
                            data=_PAYOR_COUNT_BY, value="event", size="xs",
                        ),
                    ],
                ),
            ],
        ),
        dmc.Grid(
            gutter="md",
            mb=0,
            children=[
                # Left: Payor Trend (ridgeline)
                dmc.GridCol(
                    chart_card(
                        f"{PAGE_ID}-chart-payor-trend",
                        "Trend",
                        chart_types=_CHART_TYPES,
                        show_smooth=True,
                        smooth_max=30,
                        smooth_default=3,
                        show_grouping=False,
                        graph_height="100%",
                        paper_height=f"{_RIDGE_HEIGHT + 60}px",
                        store_data=True,
                        extra_controls_left=[
                            dmc.Group(
                                gap=4, align="center",
                                children=[
                                    DashIconify(icon="mdi:sort", width=14, color="#6B7280"),
                                    dmc.SegmentedControl(
                                        id=f"{PAGE_ID}-payor-trend-sort",
                                        data=[
                                            {"value": "volume", "label": "Volume"},
                                            {"value": "change", "label": "Change"},
                                            {"value": "alpha", "label": "A–Z"},
                                        ],
                                        value="volume", size="xs",
                                    ),
                                ],
                            ),
                        ],
                        extra_controls=[
                            dmc.SegmentedControl(
                                id=f"{PAGE_ID}-payor-trend-agg",
                                data=_AGG_TOGGLE,
                                value="W", size="xs",
                            ),
                        ],
                    ),
                    span={"base": 12, "md": 6},
                ),
                # Right: Current vs Prior Period (comparison bars)
                dmc.GridCol(
                    dmc.Paper(
                        children=[
                            dmc.LoadingOverlay(
                                id=f"{PAGE_ID}-chart-payor-comparison-loading",
                                visible=False,
                                loaderProps={"type": "dots", "color": PRIMARY},
                                overlayProps={"radius": "sm", "blur": 2},
                                zIndex=10,
                            ),
                            dmc.Group(
                                justify="space-between", mb=8,
                                children=[
                                    dmc.Group(
                                        gap="xs",
                                        children=[
                                            dmc.Text("Current vs Prior Period", size="sm",
                                                     fw=500, c=NEUTRAL["text_secondary"],
                                                     id=f"{PAGE_ID}-payor-compare-title"),
                                            dmc.Group(
                                                gap=4, align="center",
                                                children=[
                                                    DashIconify(icon="mdi:sort", width=14,
                                                                color="#6B7280"),
                                                    dmc.SegmentedControl(
                                                        id=f"{PAGE_ID}-payor-compare-sort",
                                                        data=[
                                                            {"value": "volume", "label": "Volume"},
                                                            {"value": "change", "label": "Change"},
                                                            {"value": "alpha", "label": "A–Z"},
                                                        ],
                                                        value="volume", size="xs",
                                                    ),
                                                ],
                                            ),
                                            dmc.SegmentedControl(
                                                id=f"{PAGE_ID}-payor-compare-unit",
                                                data=[
                                                    {"value": "count", "label": "Count"},
                                                    {"value": "pct", "label": "%"},
                                                ],
                                                value="pct", size="xs",
                                            ),
                                        ],
                                    ),
                                    dmc.Group(
                                        gap="xs",
                                        children=[
                                            dmc.SegmentedControl(
                                                id=f"{PAGE_ID}-payor-compare-period-type",
                                                data=[
                                                    {"value": "calendar", "label": "Calendar"},
                                                    {"value": "rolling", "label": "Rolling"},
                                                ],
                                                value="calendar", size="xs",
                                            ),
                                            chart_settings_popover(
                                                f"{PAGE_ID}-payor-compare",
                                                chart_types=None,
                                                show_smooth=False,
                                                show_grouping=False,
                                                show_prior_periods=True,
                                                prior_periods_default=1,
                                            ),
                                        ],
                                    ),
                                ],
                            ),
                            dmc.Box(
                                pos="relative",
                                style={"flex": "1", "minHeight": 0},
                                children=[
                                    dmc.Box(
                                        style={"position": "absolute", "top": 0, "left": 0,
                                               "right": 0, "bottom": 0},
                                        children=[
                                            dcc.Graph(
                                                id=f"{PAGE_ID}-chart-payor-comparison",
                                                config={"displayModeBar": False},
                                                responsive=True,
                                                style={"height": "100%", "width": "100%"},
                                            ),
                                        ],
                                    ),
                                ],
                            ),
                        ],
                        p="sm", pb=8, radius="md", shadow="xs", withBorder=True,
                        h=f"{_RIDGE_HEIGHT + 60}px",
                        style={"display": "flex", "flexDirection": "column"},
                    ),
                    span={"base": 12, "md": 6},
                ),
            ],
        ),

        # ---------------------------------------------------------------
        # Insurance Rate Manager Modal
        # ---------------------------------------------------------------
        dmc.Modal(
            id=f"{PAGE_ID}-irm-modal",
            opened=False,
            title=dmc.Group(
                children=[
                    DashIconify(icon="tabler:building-bank", width=22, color=PRIMARY),
                    dmc.Text("Payor Manager", fw=600, size="lg"),
                ],
                gap="xs",
            ),
            size="95%",
            centered=True,
            zIndex=1000,
            styles={
                "header": {"padding": "6px 16px"},
                "content": {"height": "95vh", "display": "flex", "flexDirection": "column"},
                "body": {"padding": "0px 16px 4px 16px", "flex": 1, "overflow": "hidden",
                         "display": "flex", "flexDirection": "column"},
            },
            children=[
                dmc.Tabs(
                    id=f"{PAGE_ID}-irm-tabs",
                    value="mapping",
                    style={"display": "flex", "flexDirection": "column", "flex": 1, "minHeight": 0},
                    styles={"panel": {"flex": 1, "display": "flex", "flexDirection": "column", "minHeight": 0, "overflow": "hidden"}},
                    children=[
                        dmc.TabsList(
                            [
                                dmc.TabsTab(
                                    "Payor Mapping",
                                    value="mapping",
                                    leftSection=DashIconify(icon="tabler:map-pin", width=16),
                                ),
                                dmc.TabsTab(
                                    "Payor Entities",
                                    value="entities",
                                    leftSection=DashIconify(icon="tabler:building-bank", width=16),
                                ),
                                dmc.TabsTab(
                                    "Revenue Adjustments",
                                    value="rev_adj",
                                    leftSection=DashIconify(icon="tabler:adjustments-dollar", width=16),
                                ),
                            ],
                            mb=6,
                        ),

                        # ---- Hidden: Rate Manager (code preserved, removed from UI) ----
                        dmc.TabsPanel(
                            value="rates",
                            style={"display": "none"},
                            children=[
                dmc.Group(
                    justify="space-between", align="center", mb=4,
                    style={"borderBottom": "1px solid #dee2e6"},
                    children=[
                        dmc.Group(
                            gap="sm",
                            children=[
                                dmc.Text(
                                    "Edit payor rates for income projections. Changes persist across sessions.",
                                    size="xs", c="dimmed",
                                ),
                                dmc.Text(id=f"{PAGE_ID}-irm-count", size="xs", c="dimmed"),
                            ],
                        ),
                        dmc.Button(
                            "Add Payor",
                            id=f"{PAGE_ID}-irm-add-btn",
                            leftSection=DashIconify(icon="mdi:plus", width=16),
                            variant="light", color="violet", size="compact-xs",
                        ),
                    ],
                ),
                dag.AgGrid(
                    id=f"{PAGE_ID}-irm-grid",
                    rowData=[],
                    columnDefs=[
                        {"field": "payor", "headerName": "Payor",
                         "editable": False, "flex": 2, "minWidth": 180,
                         "cellRenderer": "PayorDrilldown",
                         "floatingFilter": True},
                        {"field": "rate_method", "headerName": "Method",
                         "editable": True, "flex": 0.8, "minWidth": 110,
                         "cellEditor": "agSelectCellEditor",
                         "cellEditorParams": {"values": [
                             "pct_medicare", "rbrvs_cf", "fee_schedule", "cms_cf",
                         ]},
                         "floatingFilter": True},
                        {"field": "pct_medicare", "headerName": "% of MCR",
                         "editable": True, "flex": 0.7, "minWidth": 95,
                         "type": "numericColumn",
                         "filter": "agNumberColumnFilter",
                         "valueFormatter": {"function": "params.value != null ? params.value.toFixed(1) + '%' : ''"}},
                        {"field": "em_cf", "headerName": "E&M CF",
                         "editable": True, "flex": 0.6, "minWidth": 85,
                         "type": "numericColumn",
                         "filter": "agNumberColumnFilter",
                         "valueFormatter": {"function": "params.value != null ? '$' + params.value.toFixed(2) : ''"}},
                        {"field": "other_cf", "headerName": "Other CF",
                         "editable": True, "flex": 0.6, "minWidth": 85,
                         "type": "numericColumn",
                         "filter": "agNumberColumnFilter",
                         "valueFormatter": {"function": "params.value != null ? '$' + params.value.toFixed(2) : ''"}},
                        {"field": "effective_date", "headerName": "Eff. Date",
                         "editable": True, "flex": 0.7, "minWidth": 95,
                         "floatingFilter": True},
                        {"field": "source", "headerName": "Source",
                         "editable": True, "flex": 0.6, "minWidth": 80,
                         "cellEditor": "agSelectCellEditor",
                         "cellEditorParams": {"values": [
                             "contract", "fee_schedule", "manual", "estimate",
                             "cms", "state", "government", "csv", "na",
                         ]},
                         "cellStyle": {"fontStyle": "italic", "color": "#868e96"},
                         "floatingFilter": True},
                        {"field": "notes", "headerName": "Notes",
                         "editable": True, "flex": 3, "minWidth": 250,
                         "tooltipField": "notes",
                         "floatingFilter": True},
                        {"field": "_delete", "headerName": "",
                         "width": 50, "maxWidth": 50, "sortable": False,
                         "filter": False, "floatingFilter": False,
                         "cellStyle": {"color": "#F44336", "cursor": "pointer",
                                       "textAlign": "center", "fontWeight": 700,
                                       "overflow": "visible"},
                         "editable": False, "suppressSizeToFit": True},
                    ],
                    defaultColDef={
                        "sortable": True,
                        "resizable": True,
                        "filter": "agTextColumnFilter",
                        "floatingFilter": True,
                        "valueFormatter": {"function": "params.value == null || params.value === '' ? '–' : params.value"},
                    },
                    dashGridOptions={
                        "animateRows": True,
                        "singleClickEdit": True,
                        "stopEditingWhenCellsLoseFocus": True,
                        "rowHeight": 36,
                        "headerHeight": 36,
                        "floatingFiltersHeight": 32,
                        "domLayout": "normal",
                    },
                    style={"flex": 1, "minHeight": 0},
                    className="ag-theme-alpine",
                ),
                # Detail panel — fee schedule per-code rates OR rate history
                dmc.Paper(
                    id=f"{PAGE_ID}-irm-detail-panel",
                    style={"display": "none"},
                    p="sm", radius="md", withBorder=True, mt=4,
                    children=[
                        dmc.Group(
                            justify="space-between", mb=4,
                            children=[
                                dmc.Group(
                                    gap="sm",
                                    children=[
                                        dmc.Text(
                                            id=f"{PAGE_ID}-irm-detail-title",
                                            size="sm", fw=600, c=PRIMARY,
                                        ),
                                        dmc.SegmentedControl(
                                            id=f"{PAGE_ID}-irm-detail-mode",
                                            data=[
                                                {"value": "history", "label": "Rate History"},
                                                {"value": "codes", "label": "Fee Schedule"},
                                            ],
                                            value="history",
                                            size="xs",
                                        ),
                                    ],
                                ),
                                dmc.ActionIcon(
                                    DashIconify(icon="tabler:x", width=14),
                                    id=f"{PAGE_ID}-irm-detail-close",
                                    variant="subtle", color="gray", size="sm",
                                ),
                            ],
                        ),
                        # Rate History grid
                        html.Div(
                            id=f"{PAGE_ID}-irm-history-container",
                            children=[
                                dag.AgGrid(
                                    id=f"{PAGE_ID}-irm-history-grid",
                                    columnDefs=[
                                        {"field": "effective_date", "headerName": "Effective",
                                         "flex": 0.8, "sort": "desc"},
                                        {"field": "end_date", "headerName": "End Date",
                                         "flex": 0.8, "editable": True},
                                        {"field": "pct_medicare", "headerName": "% of MCR",
                                         "flex": 0.6, "type": "numericColumn", "editable": True,
                                         "valueFormatter": {"function":
                                             "params.value != null ? params.value.toFixed(1) + '%' : ''"}},
                                        {"field": "em_cf", "headerName": "E&M CF",
                                         "flex": 0.5, "type": "numericColumn", "editable": True,
                                         "valueFormatter": {"function":
                                             "params.value != null ? '$' + params.value.toFixed(2) : ''"}},
                                        {"field": "other_cf", "headerName": "Other CF",
                                         "flex": 0.5, "type": "numericColumn", "editable": True,
                                         "valueFormatter": {"function":
                                             "params.value != null ? '$' + params.value.toFixed(2) : ''"}},
                                        {"field": "rate_method", "headerName": "Method",
                                         "flex": 0.6, "editable": True,
                                         "cellEditor": "agSelectCellEditor",
                                         "cellEditorParams": {"values": [
                                             "pct_medicare", "rbrvs_cf", "fee_schedule", "cms_cf",
                                         ]}},
                                        {"field": "source", "headerName": "Source",
                                         "flex": 0.5, "editable": True,
                                         "cellStyle": {"fontStyle": "italic", "color": "#868e96"}},
                                        {"field": "notes", "headerName": "Notes",
                                         "flex": 2, "editable": True, "tooltipField": "notes"},
                                    ],
                                    defaultColDef={"sortable": True, "resizable": True,
                                                   "valueFormatter": {"function": "params.value == null || params.value === '' ? '–' : params.value"}},
                                    dashGridOptions={
                                        "rowHeight": 32,
                                        "headerHeight": 32,
                                        "singleClickEdit": True,
                                        "stopEditingWhenCellsLoseFocus": True,
                                    },
                                    style={"height": "200px"},
                                    className="ag-theme-alpine",
                                ),
                                # Add history entry row
                                dmc.Group(
                                    gap="xs", mt=4,
                                    children=[
                                        dmc.TextInput(
                                            id=f"{PAGE_ID}-irm-hist-eff",
                                            placeholder="YYYY-MM-DD",
                                            size="xs", style={"width": 110},
                                        ),
                                        dmc.NumberInput(
                                            id=f"{PAGE_ID}-irm-hist-pct",
                                            placeholder="% MCR",
                                            size="xs", style={"width": 90},
                                            value=100, min=0, max=1000, step=0.1,
                                        ),
                                        dmc.TextInput(
                                            id=f"{PAGE_ID}-irm-hist-notes",
                                            placeholder="Notes",
                                            size="xs", style={"flex": 1},
                                        ),
                                        dmc.Button(
                                            "Add",
                                            id=f"{PAGE_ID}-irm-hist-add",
                                            size="xs", color="violet", variant="light",
                                        ),
                                    ],
                                ),
                            ],
                        ),
                        # Fee Schedule grid (hidden by default)
                        html.Div(
                            id=f"{PAGE_ID}-irm-codes-container",
                            style={"display": "none"},
                            children=[
                                dag.AgGrid(
                                    id=f"{PAGE_ID}-irm-detail-grid",
                                    columnDefs=[
                                        {"field": "code", "headerName": "CPT/HCPCS", "flex": 0.6,
                                         "filter": "agTextColumnFilter", "floatingFilter": True},
                                        {"field": "description", "headerName": "Description", "flex": 1.8,
                                         "filter": "agTextColumnFilter", "floatingFilter": True},
                                        {"field": "category", "headerName": "Category", "flex": 0.8,
                                         "filter": "agTextColumnFilter", "floatingFilter": True},
                                        {"field": "modifier", "headerName": "Mod", "flex": 0.3},
                                        {"field": "rate", "headerName": "Rate ($)", "flex": 0.6,
                                         "type": "numericColumn", "sort": "desc",
                                         "valueFormatter": {"function":
                                             "params.value != null ? '$' + params.value.toFixed(2) : ''"}},
                                        {"field": "cms_rate", "headerName": "CMS 2026 ($)", "flex": 0.6,
                                         "type": "numericColumn",
                                         "valueFormatter": {"function":
                                             "params.value != null ? '$' + params.value.toFixed(2) : ''"}},
                                        {"field": "pct_cms", "headerName": "% of CMS", "flex": 0.5,
                                         "type": "numericColumn",
                                         "valueFormatter": {"function":
                                             "params.value != null ? params.value.toFixed(1) + '%' : ''"},
                                         "cellStyle": {"function":
                                             "params.value > 100 ? {color: '#4CAF50'} "
                                             ": params.value < 100 ? {color: '#F44336'} : {}"}},
                                        {"field": "site", "headerName": "Site", "flex": 0.4},
                                        {"field": "product", "headerName": "Product", "flex": 0.5,
                                         "filter": "agTextColumnFilter", "floatingFilter": True},
                                    ],
                                    defaultColDef={"sortable": True, "resizable": True,
                                                   "valueFormatter": {"function": "params.value == null || params.value === '' ? '–' : params.value"}},
                                    dashGridOptions={
                                        "rowHeight": 30, "headerHeight": 30,
                                        "floatingFiltersHeight": 28,
                                        "pagination": True, "paginationPageSize": 25,
                                    },
                                    style={"height": "280px"},
                                    className="ag-theme-alpine",
                                ),
                            ],
                        ),
                        # Store for the current detail payor name
                        dcc.Store(id=f"{PAGE_ID}-irm-detail-payor", data=""),
                        dcc.Store(id=f"{PAGE_ID}-irm-drill-store", data=None),
                    ],
                ),
                # Add-payor input row (hidden until needed)
                dmc.Group(
                    id=f"{PAGE_ID}-irm-add-row",
                    children=[
                        dmc.TextInput(
                            id=f"{PAGE_ID}-irm-new-payor",
                            placeholder="New payor name",
                            size="xs", style={"flex": 1},
                        ),
                        dmc.NumberInput(
                            id=f"{PAGE_ID}-irm-new-pct",
                            placeholder="% of Medicare",
                            size="xs", style={"width": 120},
                            value=100, min=0, max=1000, step=0.1,
                        ),
                        dmc.Button(
                            "Save",
                            id=f"{PAGE_ID}-irm-save-new",
                            size="xs", color="violet",
                        ),
                    ],
                    gap="xs", mt="xs",
                    style={"display": "none"},
                ),
                            ],  # end TabsPanel "rates" children
                        ),  # end TabsPanel "rates"

                        # ---- Tab 2: Payor Mapping ----
                        dmc.TabsPanel(
                            value="mapping",
                            children=[
                                dmc.Group(
                                    justify="space-between", align="center", mb=4,
                                    style={"borderBottom": "1px solid #dee2e6"},
                                    children=[
                                        dmc.Group(
                                            gap="sm",
                                            children=[
                                                dmc.Text(
                                                    "Map raw insurance names to standardized payors and broad categories.",
                                                    size="xs", c="dimmed",
                                                ),
                                                dmc.Text(id=f"{PAGE_ID}-pm-count", size="xs", c="dimmed"),
                                            ],
                                        ),
                                        dmc.SegmentedControl(
                                            id=f"{PAGE_ID}-pm-filter",
                                            data=[
                                                {"value": "all", "label": "All"},
                                                {"value": "unreviewed", "label": "Unreviewed"},
                                                {"value": "unmapped", "label": "Unmapped"},
                                            ],
                                            value="all",
                                            size="xs",
                                        ),
                                    ],
                                ),
                                dag.AgGrid(
                                    id=f"{PAGE_ID}-pm-grid",
                                    rowData=[],
                                    columnDefs=[
                                        {"field": "raw_name", "headerName": "Raw Insurance Name",
                                         "editable": False, "flex": 2, "minWidth": 250,
                                         "cellRenderer": "RawInsuranceSearch",
                                         "filter": "agTextColumnFilter", "floatingFilter": True,
                                         "cellStyle": {"fontSize": "12px"}},
                                        {"field": "event_count", "headerName": "Events",
                                         "editable": False, "flex": 0.4, "minWidth": 70,
                                         "type": "numericColumn", "sort": "desc",
                                         "filter": "agNumberColumnFilter"},
                                        {"field": "standardized_payor", "headerName": "Standardized Payor",
                                         "editable": True, "flex": 1.3, "minWidth": 180,
                                         "cellEditor": "PayorMappingEditor",
                                         "cellEditorPopup": True,
                                         "cellEditorPopupPosition": "under",
                                         "cellRenderer": "PayorBadge",
                                         "cellStyle": {"cursor": "pointer"},
                                         "filter": "agTextColumnFilter", "floatingFilter": True},
                                        {"field": "broad_category", "headerName": "Category",
                                         "editable": True, "flex": 0.7, "minWidth": 130,
                                         "cellEditor": "agSelectCellEditor",
                                         "cellEditorParams": {"values": [
                                             "Medicare", "Medicaid", "Private", "Military/VA",
                                             "Workers Comp", "Tribal/IHS", "Self Pay", "Other/Unknown",
                                         ]},
                                         "cellRenderer": "BroadCategoryBadge",
                                         "filter": "agTextColumnFilter", "floatingFilter": True},
                                        {"field": "phdsc_category", "headerName": "PHDSC",
                                         "editable": True, "flex": 0.5, "minWidth": 100,
                                         "cellEditor": "agSelectCellEditor",
                                         "cellEditorParams": {"values": [
                                             "1 - Medicare", "2 - Medicaid/CHIP",
                                             "3 - Other Govt", "4 - Corrections",
                                             "5 - Private", "6 - BCBS",
                                             "8 - No Payment", "9 - Other",
                                         ]},
                                         "filter": "agTextColumnFilter", "floatingFilter": True},
                                        {"field": "reviewed", "headerName": "Reviewed",
                                         "editable": True, "flex": 0.3, "minWidth": 80,
                                         "cellDataType": "boolean",
                                         "cellStyle": {"textAlign": "center"}},
                                    ],
                                    defaultColDef={
                                        "sortable": True,
                                        "resizable": True,
                                        "filter": "agTextColumnFilter",
                                        "floatingFilter": True,
                                        "valueFormatter": {"function": "params.value == null || params.value === '' ? '\u2013' : params.value"},
                                    },
                                    dashGridOptions={
                                        "animateRows": True,
                                        "singleClickEdit": True,
                                        "stopEditingWhenCellsLoseFocus": True,
                                        "rowHeight": 36,
                                        "headerHeight": 36,
                                        "floatingFiltersHeight": 32,
                                        "domLayout": "normal",
                                    },
                                    style={"flex": 1, "minHeight": 0},
                                    className="ag-theme-alpine",
                                ),
                                # Store for the full (unfiltered) mapping data
                                dcc.Store(id=f"{PAGE_ID}-pm-full-store", data=[]),
                            ],  # end TabsPanel "mapping" children
                        ),  # end TabsPanel "mapping"

                        # ---- Tab: Payor Entities ----
                        dmc.TabsPanel(
                            value="entities",
                            pt=4,
                            style={"flex": 1, "display": "flex", "flexDirection": "column", "overflow": "hidden"},
                            children=[
                                dmc.Group(
                                    justify="space-between", mb=6,
                                    children=[
                                        dmc.Text(
                                            "Edit a payor name to rename it across all mappings. "
                                            "Delete removes the assignment from all mappings. "
                                            "Rename one payor to another to merge them.",
                                            size="xs", c="dimmed",
                                        ),
                                        dmc.Text(id=f"{PAGE_ID}-pe-count", size="xs", c="dimmed"),
                                    ],
                                ),
                                dmc.Group(
                                    gap="xs", mb=6,
                                    children=[
                                        dmc.TextInput(
                                            id=f"{PAGE_ID}-pe-new-name",
                                            placeholder="New payor name",
                                            size="xs", style={"flex": 1},
                                        ),
                                        dmc.Button(
                                            "Add Payor",
                                            id=f"{PAGE_ID}-pe-add-btn",
                                            leftSection=DashIconify(icon="mdi:plus", width=16),
                                            variant="light", color="violet", size="compact-sm",
                                        ),
                                    ],
                                ),
                                dag.AgGrid(
                                    id=f"{PAGE_ID}-pe-grid",
                                    rowData=[],
                                    columnDefs=[
                                        {"field": "name", "headerName": "Standardized Payor Name",
                                         "editable": True, "flex": 2,
                                         "cellEditor": "agTextCellEditor",
                                         "filter": "agTextColumnFilter", "floatingFilter": True},
                                        {"field": "mapping_count", "headerName": "Mapped Raw Names",
                                         "flex": 0.5, "type": "numericColumn", "sort": "desc",
                                         "filter": "agNumberColumnFilter"},
                                        {"field": "delete", "headerName": "", "flex": 0.3,
                                         "cellRenderer": "PayorEntityDelete",
                                         "cellStyle": {"textAlign": "center"},
                                         "sortable": False, "filter": False},
                                    ],
                                    defaultColDef={
                                        "sortable": True, "resizable": True,
                                        "valueFormatter": {"function": "params.value == null || params.value === '' ? '\u2013' : params.value"},
                                    },
                                    dashGridOptions={
                                        "pagination": True,
                                        "paginationPageSize": 25,
                                        "rowHeight": 36,
                                        "headerHeight": 36,
                                        "floatingFiltersHeight": 32,
                                        "animateRows": True,
                                        "singleClickEdit": True,
                                        "stopEditingWhenCellsLoseFocus": True,
                                    },
                                    style={"flex": 1, "minHeight": 0},
                                    className="ag-theme-alpine",
                                ),
                            ],  # end TabsPanel "entities" children
                        ),  # end TabsPanel "entities"

                        # ---- Revenue Adjustments ----
                        dmc.TabsPanel(
                            value="rev_adj",
                            style={"display": "flex", "flexDirection": "column",
                                   "overflow": "auto", "padding": "4px 0"},
                            children=[
                                dmc.Text(
                                    "The realization factor is always applied. The toggle below "
                                    "controls whether per-category payer-mix multipliers are "
                                    "also applied to revenue estimates.",
                                    size="xs", c="dimmed", mb="sm",
                                ),

                                # Enable/disable toggle
                                dmc.Switch(
                                    id=f"{PAGE_ID}-rev-adj-enabled",
                                    label="Enable per-category payer-mix multipliers",
                                    size="md",
                                    checked=False,
                                    color="violet",
                                    mb="md",
                                ),

                                # Category multiplier sliders
                                dmc.Paper(
                                    p="md", radius="md", withBorder=True, mb="md",
                                    style={"maxWidth": "50%"},
                                    id=f"{PAGE_ID}-rev-adj-cat-paper",
                                    children=[
                                        dmc.Group(
                                            gap="xs", mb="sm",
                                            children=[
                                                DashIconify(icon="tabler:percentage", width=18, color=PRIMARY),
                                                dmc.Text("Category Multipliers (% of Medicare)", fw=600, size="sm"),
                                            ],
                                        ),
                                        dmc.Text(
                                            "Estimate how each broad payer category reimburses "
                                            "relative to Medicare allowed amounts.",
                                            size="xs", c="dimmed", mb="md",
                                        ),
                                        dmc.SimpleGrid(
                                            cols=1,
                                            spacing="sm",
                                            children=[
                                                _rev_adj_slider("Medicare", "#2196F3"),
                                                _rev_adj_slider("Medicaid", "#4CAF50"),
                                                _rev_adj_slider("Private", "#FF9800"),
                                                _rev_adj_slider("Military/VA", "#7C2A83"),
                                                _rev_adj_slider("Workers Comp", "#00BCD4"),
                                                _rev_adj_slider("Tribal/IHS", "#795548"),
                                                _rev_adj_slider("Self Pay", "#F44336"),
                                                _rev_adj_slider("Other/Unknown", "#9CA3AF"),
                                            ],
                                        ),
                                    ],
                                ),

                                # Realization factor
                                dmc.Paper(
                                    p="md", radius="md", withBorder=True, mb="md",
                                    style={"maxWidth": "50%"},
                                    children=[
                                        dmc.Group(
                                            gap="xs", mb="sm",
                                            children=[
                                                DashIconify(icon="tabler:receipt-off", width=18, color=PRIMARY),
                                                dmc.Text("Realization Factor", fw=600, size="sm"),
                                            ],
                                        ),
                                        dmc.Text(
                                            "Discount applied to all revenue estimates to account for "
                                            "denials, adjustments, underpayments, and write-offs.",
                                            size="xs", c="dimmed", mb="md",
                                        ),
                                        dmc.Group(
                                            gap="md", align="center",
                                            children=[
                                                dmc.Slider(
                                                    id=f"{PAGE_ID}-rev-adj-realization",
                                                    min=0, max=100, step=1, value=90,
                                                    marks=[
                                                        {"value": 0, "label": "0%"},
                                                        {"value": 25, "label": "25%"},
                                                        {"value": 50, "label": "50%"},
                                                        {"value": 75, "label": "75%"},
                                                        {"value": 100, "label": "100%"},
                                                    ],
                                                    color="violet",
                                                    style={"flex": 1},
                                                ),
                                                dmc.Text(
                                                    id=f"{PAGE_ID}-rev-adj-realization-val",
                                                    size="lg", fw=700, c=PRIMARY,
                                                    style={"minWidth": "55px", "textAlign": "right"},
                                                ),
                                            ],
                                        ),
                                    ],
                                ),

                                # Save button
                                dmc.Group(
                                    justify="flex-end",
                                    style={"maxWidth": "50%"},
                                    children=[
                                        dmc.Text(
                                            id=f"{PAGE_ID}-rev-adj-status",
                                            size="xs", c="dimmed",
                                        ),
                                        dmc.Button(
                                            "Save Settings",
                                            id=f"{PAGE_ID}-rev-adj-save",
                                            leftSection=DashIconify(icon="tabler:device-floppy", width=16),
                                            variant="filled", color="violet", size="compact-sm",
                                        ),
                                    ],
                                ),
                            ],
                        ),  # end TabsPanel "rev_adj"

                    ],  # end Tabs children
                ),  # end Tabs
            ],
        ),

        # Detail table
        detail_table(
            f"{PAGE_ID}-detail-grid",
            title="Billing Detail",
            export_id=f"{PAGE_ID}-table-export",
            column_size="autoSize",
            extra_controls=[
                dmc.Button(
                    "Clear Filters",
                    id=f"{PAGE_ID}-table-clear-filters",
                    size="compact-xs",
                    variant="light",
                    color="red",
                    leftSection=DashIconify(icon="mdi:filter-remove", width=14),
                    style={"display": "none"},
                ),
            ],
        ),

        # Stores
        dcc.Store(id=f"{PAGE_ID}-store-kpi-sparklines"),
        dcc.Store(id=f"{PAGE_ID}-store-volume"),
        dcc.Store(id=f"{PAGE_ID}-store-volume-cum"),
        dcc.Store(id=f"{PAGE_ID}-store-rvu"),
        dcc.Store(id=f"{PAGE_ID}-store-rvu-cum"),
        dcc.Store(id=f"{PAGE_ID}-store-dollar"),
        dcc.Store(id=f"{PAGE_ID}-store-dollar-cum"),
        dcc.Store(id=f"{PAGE_ID}-store-rev-adj", data=get_revenue_adj_settings()),
        dcc.Store(id=f"{PAGE_ID}-table-filter-rows"),

        dcc.Interval(id=f"{PAGE_ID}-interval", interval=300_000, n_intervals=0),
    ],
)


# ---------------------------------------------------------------------------
# Date Slider Sync Callbacks
# ---------------------------------------------------------------------------

# Preset → slider
@callback(
    Output(f"{PAGE_ID}-date-slider", "value"),
    Output(f"{PAGE_ID}-filter-daterange", "start_date", allow_duplicate=True),
    Output(f"{PAGE_ID}-filter-daterange", "end_date", allow_duplicate=True),
    Input(f"{PAGE_ID}-filter-date-preset", "value"),
    prevent_initial_call=True,
)
def _preset_to_slider(preset):
    if preset == "custom":
        return (dash.no_update,) * 3
    sv = preset_to_slider_val(preset, MAX_IDX)
    s, e = preset_to_exact_dates(preset)
    return sv, s, e


# Slider → datepicker + label (clientside)
clientside_callback(
    ClientsideFunction(namespace="billingDateSlider", function_name="syncSlider"),
    Output(f"{PAGE_ID}-filter-daterange", "start_date"),
    Output(f"{PAGE_ID}-filter-daterange", "end_date"),
    Output(f"{PAGE_ID}-date-range-label", "children"),
    Input(f"{PAGE_ID}-date-slider", "value"),
    State(f"{PAGE_ID}-filter-daterange", "start_date"),
    State(f"{PAGE_ID}-filter-daterange", "end_date"),
)


# D) Slider → auto-set preset to "Custom" when it doesn't match
@callback(
    Output(f"{PAGE_ID}-filter-date-preset", "value", allow_duplicate=True),
    Input(f"{PAGE_ID}-date-slider", "value"),
    State(f"{PAGE_ID}-filter-date-preset", "value"),
    prevent_initial_call=True,
)
def _maybe_clear_preset(slider_val, current_preset):
    if not current_preset or current_preset == "custom":
        return dash.no_update
    expected = preset_to_slider_val(current_preset, MAX_IDX)
    if slider_val == expected:
        return dash.no_update
    return "custom"


# ---------------------------------------------------------------------------
# Shared filter helper + input list
# ---------------------------------------------------------------------------

_BILLING_FILTER_INPUTS = [
    Input(f"{PAGE_ID}-interval", "n_intervals"),
    Input(f"{PAGE_ID}-filter-daterange", "start_date"),
    Input(f"{PAGE_ID}-filter-daterange", "end_date"),
    Input(f"{PAGE_ID}-filter-department", "value"),
    Input(f"{PAGE_ID}-filter-physician", "value"),
    Input(f"{PAGE_ID}-filter-physician-role", "value"),
    Input(f"{PAGE_ID}-filter-codetype", "value"),
    Input(f"{PAGE_ID}-filter-charge-status", "value"),
    Input(f"{PAGE_ID}-cpt-store", "data"),
    Input(f"{PAGE_ID}-cpt-code-store", "data"),
    Input(f"{PAGE_ID}-filter-pro-reviewed", "value"),
    Input(f"{PAGE_ID}-filter-pro-exported", "value"),
    Input(f"{PAGE_ID}-filter-excl-credited", "checked"),
    Input(f"{PAGE_ID}-filter-excl-waived", "checked"),
    Input(f"{PAGE_ID}-filter-hosp-reviewed", "value"),
    Input(f"{PAGE_ID}-filter-hosp-exported", "value"),
    Input(f"{PAGE_ID}-filter-hosp-excl-credited", "checked"),
    Input(f"{PAGE_ID}-filter-hosp-excl-waived", "checked"),
    Input(f"{PAGE_ID}-filter-date-preset", "value"),
]


def _unpack_billing_filter_args(args):
    """Unpack the 19 common filter args into kwargs for _load_and_filter_billing."""
    (_n, start_date, end_date, departments, physician,
     physician_role, codetype, charge_status, categories, cpt_codes,
     pro_reviewed, pro_exported, excl_credited, excl_waived,
     hosp_reviewed, hosp_exported, hosp_excl_credited, hosp_excl_waived,
     date_preset) = args[:19]
    return dict(
        start_date=start_date, end_date=end_date, departments=departments,
        physician=physician, physician_role=physician_role, codetype=codetype,
        charge_status=charge_status, categories=categories, cpt_codes=cpt_codes,
        pro_reviewed=pro_reviewed, pro_exported=pro_exported,
        excl_credited=excl_credited, excl_waived=excl_waived,
        hosp_reviewed=hosp_reviewed, hosp_exported=hosp_exported,
        hosp_excl_credited=hosp_excl_credited, hosp_excl_waived=hosp_excl_waived,
        date_preset=date_preset,
    )


def _apply_revenue_adjustments(df, rev_adj):
    """Apply realization factor (always) and per-category multipliers (when enabled).

    rev_adj is a dict from the store: {enabled, realization, mult_Medicare, ...}.
    Realization factor is always applied. Category multipliers only when enabled.
    """
    if not rev_adj:
        return df

    realization = (rev_adj.get("realization", 90) or 90) / 100.0
    enabled = rev_adj.get("enabled")

    # Nothing to do if realization is 100% and category multipliers are off
    if realization == 1.0 and not enabled:
        return df

    df = df.copy()

    if enabled:
        # Resolve broad category for each row
        try:
            mapping = get_payor_mapping_dict()
        except Exception:
            mapping = {}

        def _resolve(name):
            if name in mapping and mapping[name]["broad_category"]:
                return mapping[name]["broad_category"]
            return _broad_payor(name)

        broad = df["PrimaryInsurance"].apply(_resolve) if "PrimaryInsurance" in df.columns else pd.Series("Other/Unknown", index=df.index)
        mult_map = {cat: rev_adj.get(f"mult_{cat}", 100) / 100.0 for cat in _BROAD_CATEGORIES}
        cat_mult = broad.map(mult_map).fillna(1.0)
    else:
        cat_mult = 1.0

    for col in ("Pro_Revenue", "Hosp_Revenue", "Total_Revenue"):
        if col in df.columns:
            df[col] = df[col] * cat_mult * realization

    return df


def _load_and_filter_billing(start_date=None, end_date=None, departments=None,
                             physician=None, physician_role=None, codetype=None,
                             charge_status=None, categories=None, cpt_codes=None,
                             pro_reviewed=None, pro_exported=None,
                             excl_credited=True, excl_waived=True,
                             hosp_reviewed=None, hosp_exported=None,
                             hosp_excl_credited=True, hosp_excl_waived=True,
                             date_preset=None):
    """Load enriched billing, apply date range + dimension filters.

    Returns dict with keys: df, bf, bf_prior, start, end, date_preset, df_all,
    physician_role. Returns None if data is empty.
    """
    try:
        df = _get_enriched_billing()
    except Exception:
        return None
    if df.empty or "DateOfService" not in df.columns:
        return None

    # Date range
    last_date = df["DateOfService"].dt.normalize().max()
    earliest_date = df["DateOfService"].dt.normalize().min()

    if start_date and end_date:
        start = pd.Timestamp(start_date)
        end = pd.Timestamp(end_date)
    else:
        start = _preset_start(last_date, date_preset or "12mo", earliest_date)
        end = last_date

    # Non-date dimension mask builder (closes over df and filter args)
    def _dim_mask(base_mask):
        m = base_mask
        if departments and "Department" in df.columns:
            m = m & df["Department"].isin(departments)
        if physician:
            rc = "AttendingPhysician" if physician_role == "attending" else "SupervisingPhysician"
            if rc in df.columns:
                m = m & (df[rc] == physician)
        # Component filter (pro/hospital/all) does NOT filter rows — it controls
        # which revenue column the dollar charts use. Revenue columns already
        # have $0 for non-applicable rows. Row filtering would miscount volume
        # (e.g., bundled G-codes in 2025 have OPPS_Rate=0 but are real events).
        if charge_status and charge_status != "all":
            m = m & (df["ChargeStatus"] == charge_status)
        if cpt_codes:
            m = m & df["_base_code"].isin(cpt_codes)
        elif categories:
            m = m & df["Category"].isin(categories)
        # Per-component reviewed/exported/exclusion filters
        # Professional = rows with physician work (wRVU > 0)
        # Hospital = rows without physician work (pure technical charges)
        has_rev = "Reviewed" in df.columns
        has_exp = "Exported" in df.columns
        has_cred = "Credited" in df.columns
        has_waived = "Waived" in df.columns
        has_wrvu = "wRVU" in df.columns
        is_pro = df["wRVU"] > 0 if has_wrvu else pd.Series(True, index=df.index)
        is_hosp = ~is_pro

        # Professional: reviewed, exported, exclusions
        if has_rev and pro_reviewed and pro_reviewed != "all":
            m = m & (~is_pro | (df["Reviewed"] == ("Yes" if pro_reviewed == "yes" else "No")))
        if has_exp and pro_exported and pro_exported != "all":
            m = m & (~is_pro | (df["Exported"] == ("Yes" if pro_exported == "yes" else "No")))
        if excl_credited and has_cred:
            m = m & (~is_pro | (df["Credited"] != "Yes"))
        if excl_waived and has_waived:
            m = m & (~is_pro | (df["Waived"] != "Yes"))

        # Hospital: reviewed, exported, exclusions
        if has_rev and hosp_reviewed and hosp_reviewed != "all":
            m = m & (~is_hosp | (df["Reviewed"] == ("Yes" if hosp_reviewed == "yes" else "No")))
        if has_exp and hosp_exported and hosp_exported != "all":
            m = m & (~is_hosp | (df["Exported"] == ("Yes" if hosp_exported == "yes" else "No")))
        if hosp_excl_credited and has_cred:
            m = m & (~is_hosp | (df["Credited"] != "Yes"))
        if hosp_excl_waived and has_waived:
            m = m & (~is_hosp | (df["Waived"] != "Yes"))
        return m

    mask = _dim_mask((df["DateOfService"] >= start) & (df["DateOfService"] <= end))
    bf = df.loc[mask].copy()

    # All-time data with non-date filters (for cumulative prior periods)
    df_all = df.loc[_dim_mask(pd.Series(True, index=df.index))]

    # Prior period for trend comparison
    _dp = date_preset or "12mo"
    p_start, p_end = _prior_range(start, end, _dp)
    prior_mask = _dim_mask((df["DateOfService"] >= p_start) & (df["DateOfService"] <= p_end))
    bf_prior = df.loc[prior_mask]

    return {
        "df": df,
        "bf": bf,
        "bf_prior": bf_prior,
        "df_all": df_all,
        "start": start,
        "end": end,
        "date_preset": _dp,
        "physician_role": physician_role,
        "categories": categories,
        "component": codetype or "all",
    }


# ---------------------------------------------------------------------------
# Detail Table helpers
# ---------------------------------------------------------------------------

_BILLING_TABLE_COLS = [
    {"field": "DateOfService", "headerName": "Date", "sort": "desc"},
    {"field": "PatientFullName", "headerName": "Patient"},
    {"field": "PatientId", "headerName": "MRN"},
    {"field": "Department", "headerName": "Dept"},
    {"field": "ProcedureCode", "headerName": "CPT"},
    {"field": "ProcedureCodeDescription", "headerName": "Description"},
    {"field": "Category", "headerName": "Category"},
    {"field": "Quantity", "headerName": "Qty"},
    {"field": "SupervisingPhysician", "headerName": "Supervising MD"},
    {"field": "AttendingPhysician", "headerName": "Attending MD"},
    {"field": "wRVU", "headerName": "wRVU"},
    {"field": "Pro_Revenue", "headerName": "Pro Rev",
     "valueFormatter": {"function": "d3.format('$,.0f')(params.value)"}},
    {"field": "Hosp_Revenue", "headerName": "Hosp Rev",
     "valueFormatter": {"function": "d3.format('$,.0f')(params.value)"}},
    {"field": "Total_Revenue", "headerName": "Total Rev",
     "valueFormatter": {"function": "d3.format('$,.0f')(params.value)"}},
    {"field": "ChargeStatus", "headerName": "Status"},
    {"field": "Reviewed", "headerName": "Reviewed"},
    {"field": "Exported", "headerName": "Exported"},
    {"field": "Credited", "headerName": "Credited"},
    {"field": "PrimaryInsurance", "headerName": "Payor"},
]


def _build_billing_table(bf):
    """Return (rowData, columnDefs) for the billing detail grid."""
    if bf is None or bf.empty:
        return [], []

    existing_cols = [c for c in _BILLING_TABLE_COLS if c["field"] in bf.columns]
    existing_cols = apply_phi_grid_rules(existing_cols)

    table_df = bf.head(1000).copy()
    table_df["_row_idx"] = range(len(table_df))
    if "DateOfService" in table_df.columns and pd.api.types.is_datetime64_any_dtype(table_df["DateOfService"]):
        table_df["DateOfService"] = table_df["DateOfService"].dt.strftime("%m/%d/%Y")
    # Round numeric columns
    for c in ["wRVU", "Pro_Revenue", "Hosp_Revenue", "Total_Revenue"]:
        if c in table_df.columns:
            table_df[c] = pd.to_numeric(table_df[c], errors="coerce").round(2)
    table_df = sanitize_for_grid(table_df)
    return table_df.to_dict("records"), existing_cols


def _apply_grid_row_filter(dff, grid_rows):
    """Filter dff to only rows matching the grid's visible row indices."""
    if grid_rows is None or dff is None or dff.empty:
        return dff
    idx_set = set(int(i) for i in grid_rows)
    return dff.loc[dff.index.isin(idx_set)].reset_index(drop=True)


# ---------------------------------------------------------------------------
# Grid filter → chart sync (clientside)
# ---------------------------------------------------------------------------

# Extract _row_idx from virtualRowData, toggle badge + clear button
clientside_callback(
    """function(virtual, rowData, prev) {
        var nu = window.dash_clientside.no_update;
        var base = {"position": "absolute", "top": -12, "right": 8, "zIndex": 10, "cursor": "pointer"};
        var hidden = Object.assign({}, base, {"display": "none"});
        var btnHide = {"display": "none"};
        if (!rowData || !rowData.length || !virtual) {
            return prev == null ? [nu, nu, nu] : [null, hidden, btnHide];
        }
        if (virtual.length >= rowData.length) {
            return prev == null ? [nu, nu, nu] : [null, hidden, btnHide];
        }
        var idxs = [];
        for (var i = 0; i < virtual.length; i++) {
            if (virtual[i]._row_idx != null) idxs.push(virtual[i]._row_idx);
        }
        idxs.sort(function(a, b) { return a - b; });
        if (!idxs.length) {
            return prev == null ? [nu, nu, nu] : [null, hidden, btnHide];
        }
        if (prev && prev.length === idxs.length) {
            var same = true;
            for (var j = 0; j < idxs.length; j++) {
                if (prev[j] !== idxs[j]) { same = false; break; }
            }
            if (same) return [nu, nu, nu];
        }
        return [idxs, base, {}];
    }""",
    Output(f"{PAGE_ID}-table-filter-rows", "data"),
    Output(f"{PAGE_ID}-grid-filter-badge", "style"),
    Output(f"{PAGE_ID}-table-clear-filters", "style"),
    Input(f"{PAGE_ID}-detail-grid", "virtualRowData"),
    State(f"{PAGE_ID}-detail-grid", "rowData"),
    State(f"{PAGE_ID}-table-filter-rows", "data"),
    prevent_initial_call=True,
)

# Clear filters → reset grid filterModel
clientside_callback(
    """function(n) {
        if (!n) return window.dash_clientside.no_update;
        return {};
    }""",
    Output(f"{PAGE_ID}-detail-grid", "filterModel"),
    Input(f"{PAGE_ID}-table-clear-filters", "n_clicks"),
    prevent_initial_call=True,
)

# Badge click → scroll to grid
clientside_callback(
    """function(n) {
        if (!n) return window.dash_clientside.no_update;
        var el = document.getElementById('billing-detail-grid');
        if (el) el.scrollIntoView({behavior: 'smooth', block: 'start'});
        return window.dash_clientside.no_update;
    }""",
    Output(f"{PAGE_ID}-grid-filter-badge", "n_clicks"),
    Input(f"{PAGE_ID}-grid-filter-badge", "n_clicks"),
    prevent_initial_call=True,
)


# ---------------------------------------------------------------------------
# Callback 1: KPIs + Sparklines + Dollar Row + Detail Table
# ---------------------------------------------------------------------------

@callback(
    Output(f"{PAGE_ID}-kpi-row", "children"),
    Output(f"{PAGE_ID}-dollar-row", "children"),
    Output(f"{PAGE_ID}-store-kpi-sparklines", "data"),
    Output(f"{PAGE_ID}-store-volume", "data"),
    Output(f"{PAGE_ID}-store-rvu", "data"),
    Output(f"{PAGE_ID}-store-dollar", "data"),
    Output(f"{PAGE_ID}-detail-grid", "rowData"),
    Output(f"{PAGE_ID}-detail-grid", "columnDefs"),
    *_BILLING_FILTER_INPUTS,
    Input(f"{PAGE_ID}-store-rev-adj", "data"),
    Input(f"{PAGE_ID}-table-filter-rows", "data"),
    running=[
        (Output(f"{PAGE_ID}-chart-vol-trend-loading", "visible"), True, False),
        (Output(f"{PAGE_ID}-chart-rvu-trend-loading", "visible"), True, False),
        (Output(f"{PAGE_ID}-chart-dollar-trend-loading", "visible"), True, False),
    ],
)
def _update_billing_main(*args):
    """Single consolidated callback — loads and filters data once for all stores."""
    filt = _unpack_billing_filter_args(args)
    rev_adj = args[19]  # store-rev-adj data (after 19 filter inputs)
    grid_rows = args[20]  # table-filter-rows data
    data = _load_and_filter_billing_cached(**filt)
    if data is None:
        return [], [], {}, None, None, None, [], []

    # Table: built from full bf before grid filter
    triggered_by_grid = (
        dash.callback_context.triggered
        and len(dash.callback_context.triggered) == 1
        and dash.callback_context.triggered[0]["prop_id"] == f"{PAGE_ID}-table-filter-rows.data"
    )

    bf_raw = _apply_revenue_adjustments(data["bf"], rev_adj)

    if triggered_by_grid:
        table_rows = dash.no_update
        table_cols = dash.no_update
    else:
        table_rows, table_cols = _build_billing_table(bf_raw)

    # Apply grid row filter for KPIs/charts
    bf = _apply_grid_row_filter(bf_raw, grid_rows) if grid_rows else bf_raw
    bf_prior = _apply_revenue_adjustments(data["bf_prior"], rev_adj)
    start, end = data["start"], data["end"]
    physician_role = data["physician_role"]
    categories = data["categories"]
    component = data["component"]

    # KPIs + sparklines
    sparkline_data = {}
    kpi_children = []

    for cat in CATEGORY_NAMES:
        slug = CATEGORY_SLUGS[cat]
        color = CATEGORY_COLORS[cat]
        curr_count = int(bf.loc[bf["Category"] == cat, "Quantity"].sum())
        if curr_count == 0:
            continue
        prior_count = int(bf_prior.loc[bf_prior["Category"] == cat, "Quantity"].sum())
        trend, direction = _trend_text(curr_count, prior_count)
        card = kpi_card(
            cat,
            f"{curr_count:,}",
            trend_text=trend,
            trend_direction=direction,
            accent_color=color,
            sparkline_id=f"{PAGE_ID}-spark-{slug}",
        )
        kpi_children.append(card)

        # Sparkline raw data
        cat_df = bf[bf["Category"] == cat]
        spark = _count_spark_raw(cat_df, "DateOfService", start, end, value_col="Quantity")
        spark["color"] = color
        sparkline_data[slug] = spark

    # Wrap cards as flex items — equal width, max 20% each
    if kpi_children:
        wrapped = []
        for card in kpi_children:
            card.style = {**(card.style or {}), "width": "100%", "minHeight": 0}
            wrapped.append(
                html.Div(
                    card,
                    style={
                        "flex": "1 1 0",
                        "minWidth": "120px",
                        "maxWidth": "20%",
                        "display": "flex",
                    },
                )
            )
        kpi_children = wrapped

    # Dollar estimate row
    def _dollar_card(label, amount, color=NEUTRAL["text_primary"]):
        return dmc.Paper(
            dmc.Group(
                gap="xs", align="center",
                children=[
                    dmc.Text(label, size="xs", c=NEUTRAL["text_secondary"], fw=500),
                    dmc.Text(
                        f"${amount:,.0f}",
                        size="sm", fw=700, c=color,
                    ),
                ],
            ),
            px="md", py=6, radius="md", shadow="xs", withBorder=True,
            style={"flex": "1 1 0", "minWidth": "140px"},
        )

    # Use pre-computed per-row revenue (from _get_enriched_billing)
    group_dollars = bf["Pro_Revenue"].sum() if not bf.empty else 0
    hosp_dollars = bf["Hosp_Revenue"].sum() if not bf.empty else 0
    total_dollars = group_dollars + hosp_dollars

    if component == "pro":
        dollar_children = [_dollar_card("Est. Professional Revenue", group_dollars, PRIMARY)]
    elif component == "hospital":
        dollar_children = [_dollar_card("Est. Hospital Revenue", hosp_dollars, PRIMARY)]
    else:
        dollar_children = [
            _dollar_card("Est. Professional Revenue", group_dollars, PRIMARY),
            _dollar_card("Est. Hospital Revenue", hosp_dollars),
            _dollar_card("Est. All-In Total", total_dollars, SEMANTIC_COLORS["success"]),
        ]

    # ---- Shared dimension setup (computed once for all stores) ----
    dept_names = [d for d in DEPARTMENTS if d in bf["Department"].unique()] if "Department" in bf.columns else []
    _role_col = "AttendingPhysician" if physician_role == "attending" else "SupervisingPhysician"
    if _role_col in bf.columns:
        phys_names = sorted(bf[_role_col].dropna().unique())
        phys_colors = {p: CHART_COLORWAY[i % len(CHART_COLORWAY)] for i, p in enumerate(phys_names)}
    else:
        phys_names, phys_colors = [], {}
    active_cat_names = [c for c in CATEGORY_NAMES if c in bf["Category"].unique()]

    subcat_names, subcat_colors = [], {}
    cpt_codes_list, cpt_colors = [], {}
    if categories and len(categories) >= 1:
        subcat_names = sorted(bf["Subcategory"].dropna().unique())
        subcat_colors = {s: CHART_COLORWAY[i % len(CHART_COLORWAY)] for i, s in enumerate(subcat_names)}
    if categories and len(categories) == 1:
        cpt_codes_list = sorted(bf["_base_code"].dropna().unique())
        cpt_colors = {c: CHART_COLORWAY[i % len(CHART_COLORWAY)] for i, c in enumerate(cpt_codes_list)}

    def _build_all_aggs(group_col, group_names, group_colors, value_col=None, y_title="Count"):
        out = {}
        for freq in ("W", "M", "Y"):
            out[freq] = _build_census_data(
                bf, "DateOfService", start, end,
                group_col, group_names, group_colors,
                value_col=value_col, y_title=y_title, freq=freq,
            )
        return out

    def _build_store(value_col, y_title):
        store = {
            "category": _build_all_aggs("Category", active_cat_names, CATEGORY_COLORS,
                                         value_col=value_col, y_title=y_title),
            "department": _build_all_aggs("Department", dept_names, DEPARTMENT_COLORS,
                                           value_col=value_col, y_title=y_title),
            "physician": _build_all_aggs(_role_col, phys_names, phys_colors,
                                          value_col=value_col, y_title=y_title),
        }
        if subcat_names:
            store["subcategory"] = _build_all_aggs("Subcategory", subcat_names, subcat_colors,
                                                    value_col=value_col, y_title=y_title)
        if cpt_codes_list:
            store["cpt"] = _build_all_aggs("_base_code", cpt_codes_list, cpt_colors,
                                            value_col=value_col, y_title=y_title)
        return store

    # ---- Volume Store ----
    volume_store = _build_store("Quantity", "Billing Units")

    # ---- RVU Store (skip when hospital-only — RVUs don't apply to OPPS) ----
    rvu_store = None if component == "hospital" else _build_store("wRVU", "wRVU")

    # ---- Dollar Store ----
    if component == "pro":
        dollar_col, dollar_label = "Pro_Revenue", "Professional Revenue ($)"
    elif component == "hospital":
        dollar_col, dollar_label = "Hosp_Revenue", "Hospital Revenue ($)"
    else:
        dollar_col, dollar_label = "Total_Revenue", "Total Revenue ($)"
    dollar_store = _build_store(dollar_col, dollar_label)

    return (kpi_children, dollar_children, sparkline_data,
            volume_store, rvu_store, dollar_store,
            table_rows, table_cols)


# ---------------------------------------------------------------------------
# Cumulative Callback (separate for performance — toggles don't recompute KPIs)
# ---------------------------------------------------------------------------

@callback(
    Output(f"{PAGE_ID}-store-volume-cum", "data"),
    Output(f"{PAGE_ID}-store-rvu-cum", "data"),
    Output(f"{PAGE_ID}-store-dollar-cum", "data"),
    *_BILLING_FILTER_INPUTS,
    Input(f"{PAGE_ID}-store-rev-adj", "data"),
    Input(f"{PAGE_ID}-volcum-mode", "value"),
    Input(f"{PAGE_ID}-volcum-period-type", "value"),
    Input(f"{PAGE_ID}-volcum-slice", "value"),
    Input(f"{PAGE_ID}-rvucum-mode", "value"),
    Input(f"{PAGE_ID}-rvucum-period-type", "value"),
    Input(f"{PAGE_ID}-rvucum-slice", "value"),
    Input(f"{PAGE_ID}-dollarcum-mode", "value"),
    Input(f"{PAGE_ID}-dollarcum-period-type", "value"),
    Input(f"{PAGE_ID}-dollarcum-slice", "value"),
    running=[
        (Output(f"{PAGE_ID}-chart-vol-cum-loading", "visible"), True, False),
        (Output(f"{PAGE_ID}-chart-rvu-cum-loading", "visible"), True, False),
        (Output(f"{PAGE_ID}-chart-dollar-cum-loading", "visible"), True, False),
    ],
)
def update_cumulative(*args):
    """Cumulative stores only — separate callback so toggle changes are fast."""
    filt = _unpack_billing_filter_args(args)
    rev_adj = args[19]  # store-rev-adj data
    (volcum_mode, volcum_period_type, volcum_slice,
     rvucum_mode, rvucum_period_type, rvucum_slice,
     dollarcum_mode, dollarcum_period_type,
     dollarcum_slice) = args[20:29]

    data = _load_and_filter_billing_cached(**filt)
    if data is None:
        return None, None, None

    df_all = _apply_revenue_adjustments(data["df_all"], rev_adj)
    start, end = data["start"], data["end"]
    physician_role = data["physician_role"]
    categories = data["categories"]
    _dp = data["date_preset"]
    component = data["component"]

    # RVU cumulative always wRVU (professional only)
    rvu_col, rvu_label = "wRVU", "Cumulative wRVU"

    # Dollar cumulative: component-aware
    if component == "pro":
        dollar_col, dollar_label = "Pro_Revenue", "Cumulative Professional Revenue ($)"
    elif component == "hospital":
        dollar_col, dollar_label = "Hosp_Revenue", "Cumulative Hospital Revenue ($)"
    else:
        dollar_col, dollar_label = "Total_Revenue", "Cumulative Total Revenue ($)"

    # Slice configs
    _role_col = "AttendingPhysician" if physician_role == "attending" else "SupervisingPhysician"
    dept_names = [d for d in DEPARTMENTS if "Department" in df_all.columns and d in df_all["Department"].unique()]
    active_cat_names = [c for c in CATEGORY_NAMES if c in df_all["Category"].unique()]
    if _role_col in df_all.columns:
        phys_names = sorted(df_all[_role_col].dropna().unique())
        phys_colors = {p: CHART_COLORWAY[i % len(CHART_COLORWAY)] for i, p in enumerate(phys_names)}
    else:
        phys_names, phys_colors = [], {}

    _slice_cfgs = {
        "category": ("Category", active_cat_names, CATEGORY_COLORS),
        "department": ("Department", dept_names, DEPARTMENT_COLORS),
        "physician": (_role_col, phys_names, phys_colors),
    }

    # Subcategory slice (when >= 1 category selected)
    if categories and len(categories) >= 1:
        subcat_names = sorted(df_all["Subcategory"].dropna().unique())
        subcat_colors = {s: CHART_COLORWAY[i % len(CHART_COLORWAY)] for i, s in enumerate(subcat_names)}
        _slice_cfgs["subcategory"] = ("Subcategory", subcat_names, subcat_colors)

    # CPT-code slice for cumulative (only when exactly 1 category selected)
    if categories and len(categories) == 1:
        cpt_codes = sorted(df_all["_base_code"].dropna().unique())
        cpt_colors = {c: CHART_COLORWAY[i % len(CHART_COLORWAY)] for i, c in enumerate(cpt_codes)}
        _slice_cfgs["cpt"] = ("_base_code", cpt_codes, cpt_colors)

    vol_cum = _build_cumulative(
        df_all, "DateOfService", start, end, _dp,
        value_col="Quantity", y_title="Cumulative Units",
        mode=volcum_mode or "prior",
        period_type=volcum_period_type or "calendar",
        slice_by=volcum_slice or "total",
        slice_configs=_slice_cfgs,
        max_prior=10,
    )
    rvu_cum = _build_cumulative(
        df_all, "DateOfService", start, end, _dp,
        value_col=rvu_col, y_title=rvu_label,
        mode=rvucum_mode or "prior",
        period_type=rvucum_period_type or "calendar",
        slice_by=rvucum_slice or "total",
        slice_configs=_slice_cfgs,
        max_prior=10,
    )
    dollar_cum = _build_cumulative(
        df_all, "DateOfService", start, end, _dp,
        value_col=dollar_col, y_title=dollar_label,
        mode=dollarcum_mode or "prior",
        period_type=dollarcum_period_type or "calendar",
        slice_by=dollarcum_slice or "total",
        slice_configs=_slice_cfgs,
        max_prior=10,
    )
    return vol_cum, rvu_cum, dollar_cum


# ---------------------------------------------------------------------------
# Payor Trend + Comparison Callback
# ---------------------------------------------------------------------------

@callback(
    Output(f"{PAGE_ID}-chart-payor-trend-store", "data"),
    Output(f"{PAGE_ID}-chart-payor-comparison", "figure"),
    Output(f"{PAGE_ID}-payor-compare-settings-prior-periods", "max"),
    Output(f"{PAGE_ID}-payor-compare-settings-prior-periods", "marks"),
    Output(f"{PAGE_ID}-payor-compare-title", "children"),
    *_BILLING_FILTER_INPUTS,
    Input(f"{PAGE_ID}-store-rev-adj", "data"),
    Input(f"{PAGE_ID}-payor-mode", "value"),
    Input(f"{PAGE_ID}-payor-count-by", "value"),
    Input(f"{PAGE_ID}-payor-trend-sort", "value"),
    Input(f"{PAGE_ID}-payor-compare-sort", "value"),
    Input(f"{PAGE_ID}-payor-compare-period-type", "value"),
    Input(f"{PAGE_ID}-payor-compare-settings-prior-periods", "value"),
    Input(f"{PAGE_ID}-payor-compare-unit", "value"),
    running=[
        (Output(f"{PAGE_ID}-chart-payor-trend-loading", "visible"), True, False),
        (Output(f"{PAGE_ID}-chart-payor-comparison-loading", "visible"), True, False),
    ],
)
def _update_payor_charts(*args):
    """Payor trend ridgeline + comparison bars — separate callback for fast toggles."""
    filt = _unpack_billing_filter_args(args)
    rev_adj = args[19]
    payor_mode = args[20] or "broad"
    count_by = args[21] or "event"
    trend_sort = args[22] or "volume"
    compare_sort = args[23] or "volume"
    period_type = args[24] or "calendar"
    max_prior = args[25] if args[25] is not None else 1
    compare_unit = args[26] or "count"

    _empty_fig = empty_figure("No data")
    _empty_fig.update_layout(height=_RIDGE_HEIGHT)
    _default_marks = [{"value": i, "label": str(i)} for i in range(0, 6)]
    _compare_title = "Current Period" if max_prior == 0 else "Current vs Prior Period"

    data = _load_and_filter_billing_cached(**filt)
    if data is None:
        return None, _empty_fig, 5, _default_marks, _compare_title

    bf = _apply_revenue_adjustments(data["bf"], rev_adj)
    df_all = _apply_revenue_adjustments(data["df_all"], rev_adj)
    start, end = data["start"], data["end"]
    component = data.get("component", "global")

    # Determine revenue column for dollar mode
    if count_by == "dollar":
        if component == "pro":
            dollar_col = "Pro_Revenue"
        elif component == "hospital":
            dollar_col = "Hosp_Revenue"
        else:
            dollar_col = "Total_Revenue"
    else:
        dollar_col = None

    # Load payor mapping
    try:
        mapping = get_payor_mapping_dict()
    except Exception:
        mapping = {}

    # Resolve payer groups on the filtered data
    bf, groups, cmap = _resolve_payer_group(bf, "PrimaryInsurance", payor_mode, mapping)
    df_all, _, _ = _resolve_payer_group(df_all, "PrimaryInsurance", payor_mode, mapping)

    # Handle "per course" count mode
    if count_by == "course":
        from data.loader import load_courses
        try:
            courses = load_courses()
        except Exception:
            courses = pd.DataFrame()

        # Build course-level data for current period
        course_curr = _assign_course_payer(bf, courses)
        # Build prior windows from course data too
        today = pd.Timestamp.now().normalize()
        end_norm = min(end.normalize(), today)
        start_norm = start.normalize()
        period_days = max((end_norm - start_norm).days + 1, 2)

        if period_days > 365 and period_type == "calendar":
            period_type = "rolling"

        data_min = df_all["DateOfService"].min() if not df_all.empty else start
        _MAX_PROBE = 3
        all_prior_windows = []
        for i in range(1, _MAX_PROBE + 1):
            if period_type == "calendar":
                try:
                    p_start = start - pd.DateOffset(years=i)
                    p_end = end_norm - pd.DateOffset(years=i)
                except Exception:
                    continue
            else:
                shift = pd.Timedelta(days=period_days * i)
                p_start = start - shift
                p_end = end_norm - shift
            if p_end < data_min:
                break
            bf_p = df_all[(df_all["DateOfService"] >= p_start) & (df_all["DateOfService"] <= p_end)]
            course_p = _assign_course_payer(bf_p, courses)
            all_prior_windows.append((course_p, p_start, p_end))

        n_avail = max(len(all_prior_windows), 1)
        prior_windows = all_prior_windows[:max_prior]

        # Trend store from course data
        if not course_curr.empty:
            course_curr["_payer_group"] = course_curr["_course_payer"]
            trend_store = _build_payor_trend_store(
                course_curr, "_course_date", groups, cmap, "event", trend_sort,
            )
        else:
            trend_store = None

        # Comparison figure from course data
        if not course_curr.empty:
            comp_windows = []
            for course_p, ps, pe in prior_windows:
                if not course_p.empty:
                    course_p = course_p.copy()
                    course_p["_payer_group"] = course_p["_course_payer"]
                comp_windows.append((course_p, ps, pe))
            comp_fig = _build_payor_comparison(
                course_curr, "_course_date", groups, cmap, "event",
                compare_sort, start, end, comp_windows,
                unit=compare_unit,
            )
        else:
            comp_fig = _empty_fig

        marks = [{"value": i, "label": str(i)} for i in range(0, n_avail + 1)]
        return trend_store, comp_fig, n_avail, marks, _compare_title

    # ---- Non-course modes (event or patient) ----
    today = pd.Timestamp.now().normalize()
    end_norm = min(end.normalize(), today)
    start_norm = start.normalize()
    period_days = max((end_norm - start_norm).days + 1, 2)

    if period_days > 365 and period_type == "calendar":
        period_type = "rolling"

    data_min = df_all["DateOfService"].min() if not df_all.empty else start
    _MAX_PROBE = 3
    all_prior_windows = []
    for i in range(1, _MAX_PROBE + 1):
        if period_type == "calendar":
            try:
                p_start = start - pd.DateOffset(years=i)
                p_end = end_norm - pd.DateOffset(years=i)
            except Exception:
                continue
        else:
            shift = pd.Timedelta(days=period_days * i)
            p_start = start - shift
            p_end = end_norm - shift
        if p_end < data_min:
            break
        bf_p = df_all[(df_all["DateOfService"] >= p_start) & (df_all["DateOfService"] <= p_end)]
        bf_p, _, _ = _resolve_payer_group(bf_p, "PrimaryInsurance", payor_mode, mapping)
        all_prior_windows.append((bf_p, p_start, p_end))

    n_avail = max(len(all_prior_windows), 1)
    prior_windows = all_prior_windows[:max_prior]

    # Compute prior counts for sort-by-change
    first_prior_counts = None
    if prior_windows:
        pw0 = prior_windows[0][0]
        if pw0 is not None and not pw0.empty:
            if dollar_col and dollar_col in pw0.columns:
                first_prior_counts = pw0.groupby("_payer_group")[dollar_col].sum()
            else:
                first_prior_counts = pw0["_payer_group"].value_counts()

    # Trend store
    trend_store = _build_payor_trend_store(
        bf, "DateOfService", groups, cmap, count_by, trend_sort,
        prior_counts=first_prior_counts,
        value_col=dollar_col,
    )

    # Comparison figure
    comp_fig = _build_payor_comparison(
        bf, "DateOfService", groups, cmap, count_by, compare_sort,
        start, end, prior_windows,
        value_col=dollar_col,
        unit=compare_unit,
    )

    marks = [{"value": i, "label": str(i)} for i in range(0, n_avail + 1)]
    return trend_store, comp_fig, n_avail, marks, _compare_title


# ---------------------------------------------------------------------------
# Clientside: Deferred chart rendering (staggered rAF + IntersectionObserver)
# ---------------------------------------------------------------------------
# See assets/billing_deferred.js — each callback pushes to a render queue
# instead of returning figures directly. This prevents 8 simultaneous
# Plotly.react calls from blocking the main thread on page load.

def _trend_js(chart_id):
    return f"""
function(storeData, sliceMode, agg, smoothPct, chartType, stackVal) {{
    return window.dash_clientside.billingDeferred.renderTrend(
        '{chart_id}', storeData, sliceMode, agg, smoothPct, chartType, stackVal
    );
}}
"""

def _cum_js(chart_id):
    return f"""
function(rawData, smoothPct, chartType, stackVal, maxPrior, projectOn) {{
    return window.dash_clientside.billingDeferred.renderCum(
        '{chart_id}', rawData, smoothPct, chartType, stackVal, maxPrior, projectOn
    );
}}
"""

# Volume trend
clientside_callback(
    _trend_js(f"{PAGE_ID}-chart-vol-trend"),
    Output(f"{PAGE_ID}-chart-vol-trend", "figure"),
    Input(f"{PAGE_ID}-store-volume", "data"),
    Input(f"{PAGE_ID}-vol-slice", "value"),
    Input(f"{PAGE_ID}-vol-agg", "value"),
    Input(f"{PAGE_ID}-vol-settings-smooth", "value"),
    Input(f"{PAGE_ID}-vol-settings-type", "value"),
    Input(f"{PAGE_ID}-vol-settings-stack", "value"),
)

# RVU trend
clientside_callback(
    _trend_js(f"{PAGE_ID}-chart-rvu-trend"),
    Output(f"{PAGE_ID}-chart-rvu-trend", "figure"),
    Input(f"{PAGE_ID}-store-rvu", "data"),
    Input(f"{PAGE_ID}-rvu-slice", "value"),
    Input(f"{PAGE_ID}-rvu-agg", "value"),
    Input(f"{PAGE_ID}-rvu-settings-smooth", "value"),
    Input(f"{PAGE_ID}-rvu-settings-type", "value"),
    Input(f"{PAGE_ID}-rvu-settings-stack", "value"),
)

# Volume cumulative
clientside_callback(
    _cum_js(f"{PAGE_ID}-chart-vol-cum"),
    Output(f"{PAGE_ID}-chart-vol-cum", "figure"),
    Input(f"{PAGE_ID}-store-volume-cum", "data"),
    Input(f"{PAGE_ID}-volcum-settings-smooth", "value"),
    Input(f"{PAGE_ID}-volcum-settings-type", "value"),
    Input(f"{PAGE_ID}-volcum-settings-stack", "value"),
    Input(f"{PAGE_ID}-volcum-settings-prior-periods", "value"),
    Input(f"{PAGE_ID}-volcum-project", "checked"),
)

# RVU cumulative
clientside_callback(
    _cum_js(f"{PAGE_ID}-chart-rvu-cum"),
    Output(f"{PAGE_ID}-chart-rvu-cum", "figure"),
    Input(f"{PAGE_ID}-store-rvu-cum", "data"),
    Input(f"{PAGE_ID}-rvucum-settings-smooth", "value"),
    Input(f"{PAGE_ID}-rvucum-settings-type", "value"),
    Input(f"{PAGE_ID}-rvucum-settings-stack", "value"),
    Input(f"{PAGE_ID}-rvucum-settings-prior-periods", "value"),
    Input(f"{PAGE_ID}-rvucum-project", "checked"),
)

# Dollar trend
clientside_callback(
    _trend_js(f"{PAGE_ID}-chart-dollar-trend"),
    Output(f"{PAGE_ID}-chart-dollar-trend", "figure"),
    Input(f"{PAGE_ID}-store-dollar", "data"),
    Input(f"{PAGE_ID}-dollar-slice", "value"),
    Input(f"{PAGE_ID}-dollar-agg", "value"),
    Input(f"{PAGE_ID}-dollar-settings-smooth", "value"),
    Input(f"{PAGE_ID}-dollar-settings-type", "value"),
    Input(f"{PAGE_ID}-dollar-settings-stack", "value"),
)

# Dollar cumulative
clientside_callback(
    _cum_js(f"{PAGE_ID}-chart-dollar-cum"),
    Output(f"{PAGE_ID}-chart-dollar-cum", "figure"),
    Input(f"{PAGE_ID}-store-dollar-cum", "data"),
    Input(f"{PAGE_ID}-dollarcum-settings-smooth", "value"),
    Input(f"{PAGE_ID}-dollarcum-settings-type", "value"),
    Input(f"{PAGE_ID}-dollarcum-settings-stack", "value"),
    Input(f"{PAGE_ID}-dollarcum-settings-prior-periods", "value"),
    Input(f"{PAGE_ID}-dollarcum-project", "checked"),
)

# Payor trend ridgeline (reuse diagRidge JS renderer)
clientside_callback(
    ClientsideFunction(namespace="diagRidge", function_name="renderTrend"),
    Output(f"{PAGE_ID}-chart-payor-trend", "figure"),
    Input(f"{PAGE_ID}-chart-payor-trend-store", "data"),
    Input(f"{PAGE_ID}-chart-payor-trend-settings-smooth", "value"),
    Input(f"{PAGE_ID}-chart-payor-trend-settings-type", "value"),
    Input(f"{PAGE_ID}-payor-trend-agg", "value"),
)

# Sync sort controls between trend and comparison
clientside_callback(
    """function(val) { return val; }""",
    Output(f"{PAGE_ID}-payor-compare-sort", "value"),
    Input(f"{PAGE_ID}-payor-trend-sort", "value"),
)
clientside_callback(
    """function(val) { return val; }""",
    Output(f"{PAGE_ID}-payor-trend-sort", "value", allow_duplicate=True),
    Input(f"{PAGE_ID}-payor-compare-sort", "value"),
    prevent_initial_call=True,
)


# ---------------------------------------------------------------------------
# Slice toggle dimming
# ---------------------------------------------------------------------------
_SLICE_CLASS_JS = """function(val) {
    return (val && val !== "total") ? "slice-group-active" : "slice-total-active";
}"""

for _sid in [f"{PAGE_ID}-vol-slice", f"{PAGE_ID}-volcum-slice",
              f"{PAGE_ID}-rvu-slice", f"{PAGE_ID}-rvucum-slice"]:
    clientside_callback(
        _SLICE_CLASS_JS,
        Output(_sid, "className"),
        Input(_sid, "value"),
    )

_HIDE_STACK_JS = """function(sliceVal, chartType) {
    var single = !sliceVal || sliceVal === "total" || sliceVal === "";
    var noStack = chartType === "line";
    return (single || noStack) ? {"display": "none"} : {};
}"""

for _slice_id, _settings_id in [
    (f"{PAGE_ID}-vol-slice", f"{PAGE_ID}-vol"),
    (f"{PAGE_ID}-rvu-slice", f"{PAGE_ID}-rvu"),
    (f"{PAGE_ID}-dollar-slice", f"{PAGE_ID}-dollar"),
]:
    clientside_callback(
        _HIDE_STACK_JS,
        Output(f"{_settings_id}-settings-stack-wrap", "style", allow_duplicate=True),
        Input(_slice_id, "value"),
        Input(f"{_settings_id}-settings-type", "value"),
        prevent_initial_call="initial_duplicate",
    )

# Cumulative charts: hide stacked/grouped when Total or Prior Periods mode
for _cum_mode, _cum_slice, _cum_settings in [
    (f"{PAGE_ID}-volcum-mode", f"{PAGE_ID}-volcum-slice", f"{PAGE_ID}-volcum"),
    (f"{PAGE_ID}-rvucum-mode", f"{PAGE_ID}-rvucum-slice", f"{PAGE_ID}-rvucum"),
    (f"{PAGE_ID}-dollarcum-mode", f"{PAGE_ID}-dollarcum-slice", f"{PAGE_ID}-dollarcum"),
]:
    clientside_callback(
        """function(mode, sliceVal, chartType) {
            var single = !sliceVal || sliceVal === "total" || sliceVal === "";
            if (single) return {"display": "none"};
            var isPrior = mode === "prior";
            var noStack = chartType === "line";
            return (isPrior || noStack) ? {"display": "none"} : {};
        }""",
        Output(f"{_cum_settings}-settings-stack-wrap", "style"),
        Input(_cum_mode, "value"),
        Input(_cum_slice, "value"),
        Input(f"{_cum_settings}-settings-type", "value"),
    )


# ---------------------------------------------------------------------------
# Clientside: KPI Sparklines
# ---------------------------------------------------------------------------

_SPARKLINE_IDS = [f"{PAGE_ID}-spark-{slug}" for slug in CATEGORY_SLUGS.values()]

for _spark_id in _SPARKLINE_IDS:
    clientside_callback(
        ClientsideFunction(namespace="sparklines", function_name="updateFromStore"),
        Output(_spark_id, "figure"),
        Input(f"{PAGE_ID}-store-kpi-sparklines", "data"),
        Input(_spark_id, "id"),
        Input(f"{PAGE_ID}-smooth-slider", "value"),
    )


# ---------------------------------------------------------------------------
# Register chart settings callbacks (gear toggle + export)
# ---------------------------------------------------------------------------

register_chart_callbacks([
    (f"{PAGE_ID}-vol", f"{PAGE_ID}-chart-vol-trend"),
    (f"{PAGE_ID}-volcum", f"{PAGE_ID}-chart-vol-cum"),
    (f"{PAGE_ID}-rvu", f"{PAGE_ID}-chart-rvu-trend"),
    (f"{PAGE_ID}-rvucum", f"{PAGE_ID}-chart-rvu-cum"),
    (f"{PAGE_ID}-dollar", f"{PAGE_ID}-chart-dollar-trend"),
    (f"{PAGE_ID}-dollarcum", f"{PAGE_ID}-chart-dollar-cum"),
    (f"{PAGE_ID}-chart-payor-trend", f"{PAGE_ID}-chart-payor-trend"),
    (f"{PAGE_ID}-payor-compare", f"{PAGE_ID}-chart-payor-comparison"),
])

# Cumulative control visibility: hide slice toggle when "prior", show when "slice".
# When switching to slice mode, auto-select "category" if currently on "total".
_CUM_VIS_JS = """function(mode, sliceVal) {
    if (mode === "prior") {
        return [{}, {"display": "none"}, "total"];
    }
    var newSlice = (!sliceVal || sliceVal === "total") ? "category" : window.dash_clientside.no_update;
    return [{"display": "none"}, {}, newSlice];
}"""

clientside_callback(
    _CUM_VIS_JS,
    Output(f"{PAGE_ID}-volcum-period-type", "style"),
    Output(f"{PAGE_ID}-volcum-slice", "style"),
    Output(f"{PAGE_ID}-volcum-slice", "value", allow_duplicate=True),
    Input(f"{PAGE_ID}-volcum-mode", "value"),
    State(f"{PAGE_ID}-volcum-slice", "value"),
    prevent_initial_call="initial_duplicate",
)
clientside_callback(
    _CUM_VIS_JS,
    Output(f"{PAGE_ID}-rvucum-period-type", "style"),
    Output(f"{PAGE_ID}-rvucum-slice", "style"),
    Output(f"{PAGE_ID}-rvucum-slice", "value", allow_duplicate=True),
    Input(f"{PAGE_ID}-rvucum-mode", "value"),
    State(f"{PAGE_ID}-rvucum-slice", "value"),
    prevent_initial_call="initial_duplicate",
)

# Disable Calendar when period > 1 year; cap prior-periods slider to available data (Volume)
clientside_callback(
    """function(storeData, currentPtValue) {
        return window.dash_clientside.cumulative.updatePriorControls(storeData, currentPtValue);
    }""",
    Output(f"{PAGE_ID}-volcum-period-type", "data"),
    Output(f"{PAGE_ID}-volcum-period-type", "value", allow_duplicate=True),
    Output(f"{PAGE_ID}-volcum-settings-prior-periods", "max"),
    Output(f"{PAGE_ID}-volcum-settings-prior-periods", "marks"),
    Input(f"{PAGE_ID}-store-volume-cum", "data"),
    State(f"{PAGE_ID}-volcum-period-type", "value"),
    prevent_initial_call=True,
)

# Disable Calendar when period > 1 year; cap prior-periods slider to available data (RVU)
clientside_callback(
    """function(storeData, currentPtValue) {
        return window.dash_clientside.cumulative.updatePriorControls(storeData, currentPtValue);
    }""",
    Output(f"{PAGE_ID}-rvucum-period-type", "data"),
    Output(f"{PAGE_ID}-rvucum-period-type", "value", allow_duplicate=True),
    Output(f"{PAGE_ID}-rvucum-settings-prior-periods", "max"),
    Output(f"{PAGE_ID}-rvucum-settings-prior-periods", "marks"),
    Input(f"{PAGE_ID}-store-rvu-cum", "data"),
    State(f"{PAGE_ID}-rvucum-period-type", "value"),
    prevent_initial_call=True,
)

# Dollar cumulative control visibility
clientside_callback(
    _CUM_VIS_JS,
    Output(f"{PAGE_ID}-dollarcum-period-type", "style"),
    Output(f"{PAGE_ID}-dollarcum-slice", "style"),
    Output(f"{PAGE_ID}-dollarcum-slice", "value", allow_duplicate=True),
    Input(f"{PAGE_ID}-dollarcum-mode", "value"),
    State(f"{PAGE_ID}-dollarcum-slice", "value"),
    prevent_initial_call="initial_duplicate",
)

# Dollar cumulative prior controls
clientside_callback(
    """function(storeData, currentPtValue) {
        return window.dash_clientside.cumulative.updatePriorControls(storeData, currentPtValue);
    }""",
    Output(f"{PAGE_ID}-dollarcum-period-type", "data"),
    Output(f"{PAGE_ID}-dollarcum-period-type", "value", allow_duplicate=True),
    Output(f"{PAGE_ID}-dollarcum-settings-prior-periods", "max"),
    Output(f"{PAGE_ID}-dollarcum-settings-prior-periods", "marks"),
    Input(f"{PAGE_ID}-store-dollar-cum", "data"),
    State(f"{PAGE_ID}-dollarcum-period-type", "value"),
    prevent_initial_call=True,
)


# ---------------------------------------------------------------------------
# CPT slice option: show only when exactly 1 category is selected
# ---------------------------------------------------------------------------

def _make_slice_vis_js(include_total=False):
    total_entry = '{value: "total", label: "Total"},' if include_total else ''
    default_val = '"total"' if include_total else '"category"'
    return f"""
function(categories, currentVal) {{
    var base = [
        {total_entry}
        {{value: "category", label: "Category"}}
    ];
    var hasCats = categories && categories.length >= 1;
    var exactlyOne = categories && categories.length === 1;
    if (hasCats) {{
        base.push({{value: "subcategory", label: "Sub-Cat"}});
    }}
    base.push({{value: "department", label: "Site"}});
    base.push({{value: "physician", label: "MD"}});
    if (exactlyOne) {{
        base.push({{value: "cpt", label: "CPT"}});
    }}
    var validValues = base.map(function(b) {{ return b.value; }});
    var newVal = validValues.indexOf(currentVal) >= 0 ? currentVal : {default_val};
    return [base, newVal];
}}
"""

_CPT_SLICE_VIS_JS = _make_slice_vis_js(include_total=False)
_CPT_SLICE_VIS_CUM_JS = _make_slice_vis_js(include_total=True)

clientside_callback(
    _CPT_SLICE_VIS_JS,
    Output(f"{PAGE_ID}-vol-slice", "data"),
    Output(f"{PAGE_ID}-vol-slice", "value"),
    Input(f"{PAGE_ID}-cpt-store", "data"),
    State(f"{PAGE_ID}-vol-slice", "value"),
)

clientside_callback(
    _CPT_SLICE_VIS_JS,
    Output(f"{PAGE_ID}-rvu-slice", "data"),
    Output(f"{PAGE_ID}-rvu-slice", "value"),
    Input(f"{PAGE_ID}-cpt-store", "data"),
    State(f"{PAGE_ID}-rvu-slice", "value"),
)

clientside_callback(
    _CPT_SLICE_VIS_CUM_JS,
    Output(f"{PAGE_ID}-volcum-slice", "data"),
    Output(f"{PAGE_ID}-volcum-slice", "value"),
    Input(f"{PAGE_ID}-cpt-store", "data"),
    State(f"{PAGE_ID}-volcum-slice", "value"),
)

clientside_callback(
    _CPT_SLICE_VIS_CUM_JS,
    Output(f"{PAGE_ID}-rvucum-slice", "data"),
    Output(f"{PAGE_ID}-rvucum-slice", "value"),
    Input(f"{PAGE_ID}-cpt-store", "data"),
    State(f"{PAGE_ID}-rvucum-slice", "value"),
)

clientside_callback(
    _CPT_SLICE_VIS_JS,
    Output(f"{PAGE_ID}-dollar-slice", "data"),
    Output(f"{PAGE_ID}-dollar-slice", "value"),
    Input(f"{PAGE_ID}-cpt-store", "data"),
    State(f"{PAGE_ID}-dollar-slice", "value"),
)

clientside_callback(
    _CPT_SLICE_VIS_CUM_JS,
    Output(f"{PAGE_ID}-dollarcum-slice", "data"),
    Output(f"{PAGE_ID}-dollarcum-slice", "value"),
    Input(f"{PAGE_ID}-cpt-store", "data"),
    State(f"{PAGE_ID}-dollarcum-slice", "value"),
)


# ---------------------------------------------------------------------------
# Chip Dropdown: Physician (trigger label, clear, dynamic population)
# ---------------------------------------------------------------------------

# Trigger label
clientside_callback(
    """function(val) {
        if (!val) return "Physician";
        return val.split(", ")[0];
    }""",
    Output(f"{PAGE_ID}-physician-trigger", "children"),
    Input(f"{PAGE_ID}-filter-physician", "value"),
)

# Clear button visibility
clientside_callback(
    """function(val) { return val ? {"display": "inline-flex"} : {"display": "none"}; }""",
    Output(f"{PAGE_ID}-physician-clear", "style"),
    Input(f"{PAGE_ID}-filter-physician", "value"),
)

# Clear button action
clientside_callback(
    """function(n) { return null; }""",
    Output(f"{PAGE_ID}-filter-physician", "value", allow_duplicate=True),
    Input(f"{PAGE_ID}-physician-clear", "n_clicks"),
    prevent_initial_call=True,
)


# Populate physician chips dynamically from filtered billing data + role
@callback(
    Output(f"{PAGE_ID}-filter-physician", "children"),
    Input(f"{PAGE_ID}-filter-daterange", "start_date"),
    Input(f"{PAGE_ID}-filter-daterange", "end_date"),
    Input(f"{PAGE_ID}-filter-department", "value"),
    Input(f"{PAGE_ID}-filter-physician-role", "value"),
    Input(f"{PAGE_ID}-filter-codetype", "value"),
    Input(f"{PAGE_ID}-filter-charge-status", "value"),
    Input(f"{PAGE_ID}-cpt-store", "data"),
)
def _populate_physicians(start_date, end_date, departments, role,
                         _component, charge_status, categories):
    try:
        billing = _get_enriched_billing()
    except Exception:
        return []

    if billing.empty:
        return []

    # Date filter
    if start_date and end_date:
        mask = (billing["DateOfService"] >= pd.Timestamp(start_date)) & \
               (billing["DateOfService"] <= pd.Timestamp(end_date))
        billing = billing.loc[mask]

    # Department
    if departments and "Department" in billing.columns:
        billing = billing[billing["Department"].isin(departments)]

    # Charge status
    if charge_status and charge_status != "all" and "ChargeStatus" in billing.columns:
        billing = billing[billing["ChargeStatus"] == charge_status]

    # Categories
    if categories and "Category" in billing.columns:
        billing = billing[billing["Category"].isin(categories)]

    # Use the selected role column
    col = "AttendingPhysician" if role == "attending" else "SupervisingPhysician"
    if col not in billing.columns:
        return []

    physicians = sorted(billing[col].dropna().unique())
    return [dmc.Chip(p, value=p, size="xs", variant="filled") for p in physicians]


# ---------------------------------------------------------------------------
# CPT Accordion filter callbacks
# ---------------------------------------------------------------------------
register_cpt_callbacks(PAGE_ID)


# ---------------------------------------------------------------------------
# Hide RVU row when Hospital component selected (RVUs don't apply to OPPS)
# ---------------------------------------------------------------------------
clientside_callback(
    """function(component) {
        return component === "hospital" ? {"display": "none"} : {};
    }""",
    Output(f"{PAGE_ID}-rvu-row", "style"),
    Input(f"{PAGE_ID}-filter-codetype", "value"),
)


# ---------------------------------------------------------------------------
# Chip Dropdown: Status (trigger label, clear)
# ---------------------------------------------------------------------------

# Trigger label — show "Status" normally, count non-default filters
clientside_callback(
    """function(pr, pe, ec, ew, hr, he, hec, hew) {
        var active = 0;
        if (pr && pr !== "yes") active++;
        if (pe && pe !== "all") active++;
        if (!ec) active++;
        if (!ew) active++;
        if (hr && hr !== "yes") active++;
        if (he && he !== "yes") active++;
        if (!hec) active++;
        if (!hew) active++;
        return active > 0 ? "Status (" + active + ")" : "Status";
    }""",
    Output(f"{PAGE_ID}-status-trigger", "children"),
    Input(f"{PAGE_ID}-filter-pro-reviewed", "value"),
    Input(f"{PAGE_ID}-filter-pro-exported", "value"),
    Input(f"{PAGE_ID}-filter-excl-credited", "checked"),
    Input(f"{PAGE_ID}-filter-excl-waived", "checked"),
    Input(f"{PAGE_ID}-filter-hosp-reviewed", "value"),
    Input(f"{PAGE_ID}-filter-hosp-exported", "value"),
    Input(f"{PAGE_ID}-filter-hosp-excl-credited", "checked"),
    Input(f"{PAGE_ID}-filter-hosp-excl-waived", "checked"),
)

# Clear button visibility
clientside_callback(
    """function(pr, pe, ec, ew, hr, he, hec, hew) {
        var active = (pr !== "yes") || (pe !== "all") || !ec || !ew ||
                     (hr !== "yes") || (he !== "yes") || !hec || !hew;
        return active ? {"display": "inline-flex"} : {"display": "none"};
    }""",
    Output(f"{PAGE_ID}-status-clear", "style"),
    Input(f"{PAGE_ID}-filter-pro-reviewed", "value"),
    Input(f"{PAGE_ID}-filter-pro-exported", "value"),
    Input(f"{PAGE_ID}-filter-excl-credited", "checked"),
    Input(f"{PAGE_ID}-filter-excl-waived", "checked"),
    Input(f"{PAGE_ID}-filter-hosp-reviewed", "value"),
    Input(f"{PAGE_ID}-filter-hosp-exported", "value"),
    Input(f"{PAGE_ID}-filter-hosp-excl-credited", "checked"),
    Input(f"{PAGE_ID}-filter-hosp-excl-waived", "checked"),
)

# Clear button action — reset all status filters to defaults
clientside_callback(
    """function(n) { return ["yes", "all", true, true, "yes", "yes", true, true]; }""",
    Output(f"{PAGE_ID}-filter-pro-reviewed", "value", allow_duplicate=True),
    Output(f"{PAGE_ID}-filter-pro-exported", "value", allow_duplicate=True),
    Output(f"{PAGE_ID}-filter-excl-credited", "checked", allow_duplicate=True),
    Output(f"{PAGE_ID}-filter-excl-waived", "checked", allow_duplicate=True),
    Output(f"{PAGE_ID}-filter-hosp-reviewed", "value", allow_duplicate=True),
    Output(f"{PAGE_ID}-filter-hosp-exported", "value", allow_duplicate=True),
    Output(f"{PAGE_ID}-filter-hosp-excl-credited", "checked", allow_duplicate=True),
    Output(f"{PAGE_ID}-filter-hosp-excl-waived", "checked", allow_duplicate=True),
    Input(f"{PAGE_ID}-status-clear", "n_clicks"),
    prevent_initial_call=True,
)


# ---------------------------------------------------------------------------
# Insurance Rate Manager (IRM) Callbacks
# ---------------------------------------------------------------------------

# Seed rates on first import
seed_insurance_rates()


@callback(
    Output(f"{PAGE_ID}-irm-modal", "opened"),
    Output(f"{PAGE_ID}-irm-grid", "rowData"),
    Output(f"{PAGE_ID}-irm-count", "children"),
    Input(f"{PAGE_ID}-irm-btn", "n_clicks"),
    prevent_initial_call=True,
)
def _irm_open(n):
    if not n:
        return (dash.no_update,) * 3
    rows = get_all_insurance_rates()
    for r in rows:
        r["_delete"] = "\u2716"  # ✖ symbol for delete
    return True, rows, f"{len(rows)} payors"


@callback(
    Output(f"{PAGE_ID}-irm-grid", "rowData", allow_duplicate=True),
    Output(f"{PAGE_ID}-irm-count", "children", allow_duplicate=True),
    Input(f"{PAGE_ID}-irm-grid", "cellValueChanged"),
    State(f"{PAGE_ID}-irm-grid", "rowData"),
    prevent_initial_call=True,
)
def _irm_save_edit(changed, row_data):
    """Persist cell edits to SQLite."""
    if not changed:
        return dash.no_update, dash.no_update

    row = changed[0].get("data", {}) if isinstance(changed, list) else changed.get("data", {})

    # Save the edited row
    payor = row.get("payor", "").strip()
    if not payor:
        return dash.no_update, dash.no_update

    upsert_insurance_rate(
        payor=payor,
        rate_method=row.get("rate_method", "pct_medicare"),
        em_cf=float(row["em_cf"]) if row.get("em_cf") else None,
        other_cf=float(row["other_cf"]) if row.get("other_cf") else None,
        pct_medicare=float(row.get("pct_medicare") or 100),
        effective_date=row.get("effective_date", ""),
        source=row.get("source", "manual"),
        notes=row.get("notes", ""),
    )
    return dash.no_update, dash.no_update


@callback(
    Output(f"{PAGE_ID}-irm-grid", "rowData", allow_duplicate=True),
    Output(f"{PAGE_ID}-irm-count", "children", allow_duplicate=True),
    Input(f"{PAGE_ID}-irm-grid", "cellClicked"),
    State(f"{PAGE_ID}-irm-grid", "rowData"),
    prevent_initial_call=True,
)
def _irm_cell_delete(cell, row_data):
    """Handle delete clicks on the ✖ column."""
    if not cell:
        return dash.no_update, dash.no_update
    col = cell.get("colId", "")
    row = cell.get("data", {})
    payor = row.get("payor", "")
    if col == "_delete" and payor:
        delete_insurance_rate(payor)
        row_data = [r for r in row_data if r.get("payor") != payor]
        return row_data, f"{len(row_data)} payors"
    return dash.no_update, dash.no_update


@callback(
    Output(f"{PAGE_ID}-irm-detail-panel", "style", allow_duplicate=True),
    Output(f"{PAGE_ID}-irm-detail-title", "children", allow_duplicate=True),
    Output(f"{PAGE_ID}-irm-detail-payor", "data"),
    Output(f"{PAGE_ID}-irm-history-grid", "rowData"),
    Output(f"{PAGE_ID}-irm-detail-grid", "rowData", allow_duplicate=True),
    Output(f"{PAGE_ID}-irm-detail-mode", "value", allow_duplicate=True),
    Output(f"{PAGE_ID}-irm-detail-mode", "data", allow_duplicate=True),
    Input(f"{PAGE_ID}-irm-drill-store", "data"),
    prevent_initial_call=True,
)
def _irm_drilldown(drill_data):
    """Open detail panel when a payor name is clicked via PayorDrilldown renderer."""
    no = dash.no_update
    if not drill_data:
        return (no,) * 7

    payor = drill_data.get("payor", "")
    if not payor:
        return (no,) * 7

    # Load history for this payor
    history = get_rate_history(payor)

    # Load fee schedule if available
    has_codes = payor in _FEE_SCHEDULE_FILES
    codes_data = _load_fee_schedule_detail(payor) if has_codes else []

    # Build title
    parts = [payor]
    if history:
        parts.append(f"{len(history)} rate periods")
    if codes_data:
        n_codes = len(set(r["code"] for r in codes_data))
        parts.append(f"{n_codes} codes on file")
    title = " — ".join(parts)

    # Build mode toggle options based on what's available
    mode_data = [{"value": "history", "label": "Rate History"}]
    if has_codes:
        mode_data.append({"value": "codes", "label": "Fee Schedule"})

    # Default to history view, but if no history and codes exist, show codes
    default_mode = "history" if history else ("codes" if codes_data else "history")

    return (
        {"display": "block"},  # show panel
        title,
        payor,  # store payor name for add-history callback
        history,
        codes_data,
        default_mode,
        mode_data,
    )


# Toggle add-payor row visibility
clientside_callback(
    """function(n) {
        if (!n) return window.dash_clientside.no_update;
        return {"display": "flex"};
    }""",
    Output(f"{PAGE_ID}-irm-add-row", "style"),
    Input(f"{PAGE_ID}-irm-add-btn", "n_clicks"),
    prevent_initial_call=True,
)


@callback(
    Output(f"{PAGE_ID}-irm-grid", "rowData", allow_duplicate=True),
    Output(f"{PAGE_ID}-irm-count", "children", allow_duplicate=True),
    Output(f"{PAGE_ID}-irm-add-row", "style", allow_duplicate=True),
    Output(f"{PAGE_ID}-irm-new-payor", "value"),
    Output(f"{PAGE_ID}-irm-new-pct", "value"),
    Input(f"{PAGE_ID}-irm-save-new", "n_clicks"),
    State(f"{PAGE_ID}-irm-new-payor", "value"),
    State(f"{PAGE_ID}-irm-new-pct", "value"),
    State(f"{PAGE_ID}-irm-grid", "rowData"),
    prevent_initial_call=True,
)
def _irm_add_payor(n, payor_name, pct, row_data):
    """Add a new payor to the rate table."""
    if not n or not payor_name or not payor_name.strip():
        return (dash.no_update,) * 5

    payor_name = payor_name.strip()
    pct = float(pct) if pct else 100.0

    upsert_insurance_rate(
        payor=payor_name,
        pct_medicare=pct,
        source="manual",
    )

    # Reload all rates
    rows = get_all_insurance_rates()
    return rows, f"{len(rows)} payors", {"display": "none"}, "", 100


# Close detail panel
clientside_callback(
    """function(n) {
        if (!n) return window.dash_clientside.no_update;
        return {"display": "none"};
    }""",
    Output(f"{PAGE_ID}-irm-detail-panel", "style"),
    Input(f"{PAGE_ID}-irm-detail-close", "n_clicks"),
    prevent_initial_call=True,
)


# Toggle between history and codes views
clientside_callback(
    """function(mode) {
        if (mode === 'codes') {
            return [{"display": "none"}, {"display": "block"}];
        }
        return [{"display": "block"}, {"display": "none"}];
    }""",
    Output(f"{PAGE_ID}-irm-history-container", "style"),
    Output(f"{PAGE_ID}-irm-codes-container", "style"),
    Input(f"{PAGE_ID}-irm-detail-mode", "value"),
    prevent_initial_call=True,
)


# Save history cell edits
@callback(
    Output(f"{PAGE_ID}-irm-history-grid", "rowData", allow_duplicate=True),
    Input(f"{PAGE_ID}-irm-history-grid", "cellValueChanged"),
    State(f"{PAGE_ID}-irm-detail-payor", "data"),
    prevent_initial_call=True,
)
def _irm_history_save(changed, payor):
    """Persist edits to a rate history entry."""
    if not changed or not payor:
        return dash.no_update
    row = changed[0].get("data", {}) if isinstance(changed, list) else changed.get("data", {})
    eff = row.get("effective_date", "")
    if not eff:
        return dash.no_update
    upsert_rate_history(
        payor=payor,
        effective_date=eff,
        end_date=row.get("end_date", "") or "",
        rate_method=row.get("rate_method", "pct_medicare"),
        em_cf=float(row["em_cf"]) if row.get("em_cf") else None,
        other_cf=float(row["other_cf"]) if row.get("other_cf") else None,
        pct_medicare=float(row.get("pct_medicare") or 100),
        source=row.get("source", "manual"),
        notes=row.get("notes", ""),
    )
    return dash.no_update


# Add new history entry
@callback(
    Output(f"{PAGE_ID}-irm-history-grid", "rowData", allow_duplicate=True),
    Output(f"{PAGE_ID}-irm-hist-eff", "value"),
    Output(f"{PAGE_ID}-irm-hist-pct", "value"),
    Output(f"{PAGE_ID}-irm-hist-notes", "value"),
    Input(f"{PAGE_ID}-irm-hist-add", "n_clicks"),
    State(f"{PAGE_ID}-irm-detail-payor", "data"),
    State(f"{PAGE_ID}-irm-hist-eff", "value"),
    State(f"{PAGE_ID}-irm-hist-pct", "value"),
    State(f"{PAGE_ID}-irm-hist-notes", "value"),
    prevent_initial_call=True,
)
def _irm_history_add(n, payor, eff_date, pct, notes):
    """Add a new rate history entry."""
    if not n or not payor or not eff_date:
        return (dash.no_update,) * 4
    pct = float(pct) if pct else 100.0
    upsert_rate_history(
        payor=payor,
        effective_date=eff_date.strip(),
        pct_medicare=pct,
        source="manual",
        notes=notes or "",
    )
    # Reload history
    history = get_rate_history(payor)
    return history, "", 100, ""


# ---------------------------------------------------------------------------
# Payor Mapping (PM) Callbacks
# ---------------------------------------------------------------------------

def _seed_payor_mappings_if_needed():
    """Auto-populate payor_mappings for any raw names not yet in the DB.

    Uses existing _broad_payor() for category and difflib for standardized name.
    """
    import difflib

    try:
        df = _get_enriched_billing()
    except Exception:
        return

    if df.empty or "PrimaryInsurance" not in df.columns:
        return

    raw_names = df["PrimaryInsurance"].dropna().unique().tolist()
    raw_names = [n for n in raw_names if isinstance(n, str) and n.strip() and n != "Unknown"]

    # Get existing mappings to skip them
    existing = {r["raw_name"] for r in get_all_payor_mappings()}
    new_names = [n for n in raw_names if n not in existing]
    if not new_names:
        return

    # Get canonical payor names for fuzzy matching
    canonical = [r["payor"] for r in get_all_insurance_rates()]
    canonical_lower = {p.lower(): p for p in canonical}

    rows = []
    for raw in new_names:
        broad = _broad_payor(raw)
        # Fuzzy-match to canonical payor
        matches = difflib.get_close_matches(
            raw.lower(), canonical_lower.keys(), n=1, cutoff=0.4,
        )
        std = canonical_lower[matches[0]] if matches else ""
        rows.append({
            "raw_name": raw,
            "standardized_payor": std,
            "broad_category": broad,
        })

    seed_payor_mappings(rows)


@callback(
    Output(f"{PAGE_ID}-pm-grid", "rowData"),
    Output(f"{PAGE_ID}-pm-grid", "columnDefs"),
    Output(f"{PAGE_ID}-pm-count", "children"),
    Output(f"{PAGE_ID}-pm-full-store", "data"),
    Input(f"{PAGE_ID}-irm-tabs", "value"),
    Input(f"{PAGE_ID}-irm-modal", "opened"),
    prevent_initial_call=True,
)
def _pm_load(tab, modal_opened):
    """Load payor mapping grid when tab is selected or modal opens."""
    if tab != "mapping" and not modal_opened:
        return (dash.no_update,) * 4
    # Only load when on the mapping tab
    if tab != "mapping":
        return (dash.no_update,) * 4

    # Seed any new raw names
    _seed_payor_mappings_if_needed()

    # Load all mappings
    mappings = get_all_payor_mappings()
    mapping_dict = {m["raw_name"]: m for m in mappings}

    # Get event counts from billing data
    try:
        df = _get_enriched_billing()
        if not df.empty and "PrimaryInsurance" in df.columns:
            counts = df["PrimaryInsurance"].value_counts().to_dict()
        else:
            counts = {}
    except Exception:
        counts = {}

    # Build grid rows
    rows = []
    for m in mappings:
        rows.append({
            "raw_name": m["raw_name"],
            "event_count": counts.get(m["raw_name"], 0),
            "standardized_payor": m["standardized_payor"],
            "broad_category": m["broad_category"],
            "phdsc_category": m.get("phdsc_category", "9"),
            "reviewed": bool(m["reviewed"]),
        })

    # Sort by event_count desc by default
    rows.sort(key=lambda r: r["event_count"], reverse=True)

    # Get canonical payors for the editor dropdown
    canonical = sorted([r["payor"] for r in get_all_insurance_rates()])

    # Build column defs with dynamic cellEditorParams
    col_defs = [
        {"field": "raw_name", "headerName": "Raw Insurance Name",
         "editable": False, "flex": 2, "minWidth": 250,
         "cellRenderer": "RawInsuranceSearch",
         "filter": "agTextColumnFilter", "floatingFilter": True,
         "cellStyle": {"fontSize": "12px"}},
        {"field": "event_count", "headerName": "Events",
         "editable": False, "flex": 0.4, "minWidth": 70,
         "type": "numericColumn", "sort": "desc",
         "filter": "agNumberColumnFilter"},
        {"field": "standardized_payor", "headerName": "Standardized Payor",
         "editable": True, "flex": 1.3, "minWidth": 180,
         "cellEditor": "PayorMappingEditor",
         "cellEditorPopup": True,
         "cellEditorPopupPosition": "under",
         "cellEditorParams": {"values": canonical},
         "cellRenderer": "PayorBadge",
         "cellStyle": {"cursor": "pointer"},
         "filter": "agTextColumnFilter", "floatingFilter": True},
        {"field": "broad_category", "headerName": "Category",
         "editable": True, "flex": 0.7, "minWidth": 130,
         "cellEditor": "agSelectCellEditor",
         "cellEditorParams": {"values": [
             "Medicare", "Medicaid", "Private", "Military/VA",
             "Workers Comp", "Tribal/IHS", "Self Pay", "Other/Unknown",
         ]},
         "cellRenderer": "BroadCategoryBadge",
         "filter": "agTextColumnFilter", "floatingFilter": True},
        {"field": "phdsc_category", "headerName": "PHDSC",
         "editable": True, "flex": 0.5, "minWidth": 100,
         "cellEditor": "agSelectCellEditor",
         "cellEditorParams": {"values": [
             "1 - Medicare", "2 - Medicaid/CHIP",
             "3 - Other Govt", "4 - Corrections",
             "5 - Private", "6 - BCBS",
             "8 - No Payment", "9 - Other",
         ]},
         "filter": "agTextColumnFilter", "floatingFilter": True},
        {"field": "reviewed", "headerName": "Reviewed",
         "editable": True, "flex": 0.3, "minWidth": 80,
         "cellDataType": "boolean",
         "cellStyle": {"textAlign": "center"}},
    ]

    mapped = sum(1 for r in rows if r["standardized_payor"])
    count_text = f"{mapped} mapped / {len(rows)} total"
    return rows, col_defs, count_text, rows


def _apply_pm_filter(full_data, filter_val):
    """Apply the active filter to the full mapping data."""
    if not full_data:
        return full_data
    if filter_val == "unreviewed":
        return [r for r in full_data if not r.get("reviewed")]
    elif filter_val == "unmapped":
        return [r for r in full_data if not r.get("standardized_payor")]
    return full_data


@callback(
    Output(f"{PAGE_ID}-pm-grid", "rowData", allow_duplicate=True),
    Output(f"{PAGE_ID}-pm-count", "children", allow_duplicate=True),
    Output(f"{PAGE_ID}-pm-full-store", "data", allow_duplicate=True),
    Input(f"{PAGE_ID}-pm-grid", "cellValueChanged"),
    State(f"{PAGE_ID}-pm-full-store", "data"),
    State(f"{PAGE_ID}-pm-filter", "value"),
    prevent_initial_call=True,
)
def _pm_save_edit(changed, full_data, active_filter):
    """Persist cell edits to SQLite and re-apply active filter."""
    if not changed:
        return (dash.no_update,) * 3

    row = changed[0].get("data", {}) if isinstance(changed, list) else changed.get("data", {})
    raw = row.get("raw_name", "").strip()
    if not raw:
        return (dash.no_update,) * 3

    upsert_payor_mapping(
        raw_name=raw,
        standardized_payor=row.get("standardized_payor", ""),
        broad_category=row.get("broad_category", "Other/Unknown"),
        phdsc_category=row.get("phdsc_category", "9"),
        reviewed=1 if row.get("reviewed") else 0,
    )

    # Update the full store
    if full_data:
        for r in full_data:
            if r["raw_name"] == raw:
                r["standardized_payor"] = row.get("standardized_payor", "")
                r["broad_category"] = row.get("broad_category", "Other/Unknown")
                r["phdsc_category"] = row.get("phdsc_category", "9")
                r["reviewed"] = bool(row.get("reviewed"))
                break

    mapped = sum(1 for r in (full_data or []) if r.get("standardized_payor"))
    count_text = f"{mapped} mapped / {len(full_data or [])} total"
    visible = _apply_pm_filter(full_data, active_filter)
    return visible, count_text, full_data


# Filter toggle: All / Unreviewed / Unmapped
@callback(
    Output(f"{PAGE_ID}-pm-grid", "rowData", allow_duplicate=True),
    Input(f"{PAGE_ID}-pm-filter", "value"),
    State(f"{PAGE_ID}-pm-full-store", "data"),
    prevent_initial_call=True,
)
def _pm_filter(filter_val, full_data):
    """Filter the mapping grid."""
    if not full_data:
        return dash.no_update
    return _apply_pm_filter(full_data, filter_val)


# ---------------------------------------------------------------------------
# Payor Entity (PE) Callbacks
# ---------------------------------------------------------------------------

def _build_pe_grid_data():
    """Build entity grid rows from DB."""
    rows = get_standardized_payor_counts()
    for r in rows:
        r["original_name"] = r["name"]
    return rows


@callback(
    Output(f"{PAGE_ID}-pe-grid", "rowData"),
    Output(f"{PAGE_ID}-pe-count", "children"),
    Input(f"{PAGE_ID}-irm-tabs", "value"),
    Input(f"{PAGE_ID}-irm-modal", "opened"),
    prevent_initial_call=True,
)
def _pe_load(tab, modal_opened):
    """Load payor entities grid when tab is selected."""
    if tab != "entities":
        return (dash.no_update,) * 2
    rows = _build_pe_grid_data()
    return rows, f"{len(rows)} payors"


@callback(
    Output(f"{PAGE_ID}-pe-grid", "rowData", allow_duplicate=True),
    Output(f"{PAGE_ID}-pe-count", "children", allow_duplicate=True),
    Output(f"{PAGE_ID}-pm-full-store", "data", allow_duplicate=True),
    Input(f"{PAGE_ID}-pe-grid", "cellValueChanged"),
    State(f"{PAGE_ID}-pm-full-store", "data"),
    prevent_initial_call=True,
)
def _pe_rename(changed, full_data):
    """Rename a standardized payor — propagates to all mappings."""
    if not changed:
        return (dash.no_update,) * 3

    row = changed[0].get("data", {}) if isinstance(changed, list) else changed.get("data", {})
    old_name = row.get("original_name", "")
    new_name = (row.get("name", "") or "").strip()

    if not old_name or not new_name or old_name == new_name:
        return (dash.no_update,) * 3

    rename_standardized_payor(old_name, new_name)

    # Update the mapping store so the mapping grid reflects the rename
    if full_data:
        for r in full_data:
            if r.get("standardized_payor") == old_name:
                r["standardized_payor"] = new_name

    # Rebuild entity grid from DB
    pe_rows = _build_pe_grid_data()
    return pe_rows, f"{len(pe_rows)} payors", full_data or dash.no_update


@callback(
    Output(f"{PAGE_ID}-pe-grid", "rowData", allow_duplicate=True),
    Output(f"{PAGE_ID}-pe-count", "children", allow_duplicate=True),
    Output(f"{PAGE_ID}-pm-full-store", "data", allow_duplicate=True),
    Input(f"{PAGE_ID}-pe-grid", "cellRendererData"),
    State(f"{PAGE_ID}-pm-full-store", "data"),
    prevent_initial_call=True,
)
def _pe_delete(renderer_data, full_data):
    """Delete a standardized payor — clears from all mappings."""
    if not renderer_data:
        return (dash.no_update,) * 3

    data = renderer_data.get("value", renderer_data) if isinstance(renderer_data, dict) else {}
    # cellRendererData from setData comes through differently
    action = ""
    name = ""
    if isinstance(renderer_data, dict):
        action = renderer_data.get("_action", "")
        name = renderer_data.get("name", "")

    if action != "delete" or not name:
        return (dash.no_update,) * 3

    delete_standardized_payor(name)

    # Update the mapping store
    if full_data:
        for r in full_data:
            if r.get("standardized_payor") == name:
                r["standardized_payor"] = ""

    pe_rows = _build_pe_grid_data()
    return pe_rows, f"{len(pe_rows)} payors", full_data or dash.no_update


@callback(
    Output(f"{PAGE_ID}-pe-grid", "rowData", allow_duplicate=True),
    Output(f"{PAGE_ID}-pe-count", "children", allow_duplicate=True),
    Output(f"{PAGE_ID}-pe-new-name", "value"),
    Input(f"{PAGE_ID}-pe-add-btn", "n_clicks"),
    State(f"{PAGE_ID}-pe-new-name", "value"),
    prevent_initial_call=True,
)
def _pe_add(n, new_name):
    """Add a new standardized payor entity."""
    if not n or not new_name or not new_name.strip():
        return (dash.no_update,) * 3

    new_name = new_name.strip()
    # Add to the insurance_rates table so it shows up in the dropdown
    # (only if it doesn't already exist)
    existing = {r["payor"] for r in get_all_insurance_rates()}
    if new_name not in existing:
        upsert_insurance_rate(payor=new_name, pct_medicare=100.0, source="manual")

    # Also create a dummy mapping entry so it shows up in entity counts
    # (it will appear in the dropdown for the mapping grid)
    pe_rows = _build_pe_grid_data()
    return pe_rows, f"{len(pe_rows)} payors", ""


# ---------------------------------------------------------------------------
# Revenue Adjustment callbacks
# ---------------------------------------------------------------------------

@callback(
    Output(f"{PAGE_ID}-rev-adj-enabled", "checked"),
    Output(f"{PAGE_ID}-rev-adj-realization", "value"),
    *[Output(f"{PAGE_ID}-rev-adj-mult-{cat}", "value") for cat in _BROAD_CATEGORIES],
    Input(f"{PAGE_ID}-irm-tabs", "value"),
    Input(f"{PAGE_ID}-irm-modal", "opened"),
    prevent_initial_call=True,
)
def _rev_adj_load(tab, modal_opened):
    """Load saved revenue adjustment settings when tab is selected."""
    if tab != "rev_adj" and not modal_opened:
        raise dash.exceptions.PreventUpdate
    s = get_revenue_adj_settings()
    return (
        bool(s.get("enabled", 0)),
        s.get("realization", 90),
        *[s.get(f"mult_{cat}", 100) for cat in _BROAD_CATEGORIES],
    )


@callback(
    Output(f"{PAGE_ID}-rev-adj-status", "children"),
    Output(f"{PAGE_ID}-store-rev-adj", "data"),
    Input(f"{PAGE_ID}-rev-adj-save", "n_clicks"),
    State(f"{PAGE_ID}-rev-adj-enabled", "checked"),
    State(f"{PAGE_ID}-rev-adj-realization", "value"),
    *[State(f"{PAGE_ID}-rev-adj-mult-{cat}", "value") for cat in _BROAD_CATEGORIES],
    prevent_initial_call=True,
)
def _rev_adj_save(n, enabled, realization, *mult_values):
    """Save revenue adjustment settings to DB and push to store."""
    if not n:
        raise dash.exceptions.PreventUpdate
    settings = {
        "enabled": 1.0 if enabled else 0.0,
        "realization": float(realization or 90),
    }
    for cat, val in zip(_BROAD_CATEGORIES, mult_values):
        settings[f"mult_{cat}"] = float(val if val is not None else 100)
    save_revenue_adj_settings(settings)
    return "Saved", settings


# Clientside callbacks to display slider values
for _cat in _BROAD_CATEGORIES:
    clientside_callback(
        "function(v) { return (v != null ? v : 100) + '%'; }",
        Output(f"{PAGE_ID}-rev-adj-mult-{_cat}-val", "children"),
        Input(f"{PAGE_ID}-rev-adj-mult-{_cat}", "value"),
    )

clientside_callback(
    "function(v) { return (v != null ? v : 90) + '%'; }",
    Output(f"{PAGE_ID}-rev-adj-realization-val", "children"),
    Input(f"{PAGE_ID}-rev-adj-realization", "value"),
)


# Project-to-year-end toggle visibility (shown only for current_year preset)
clientside_callback(
    """function(preset) {
        return preset === "current_year" ? {} : {"display": "none"};
    }""",
    Output(f"{PAGE_ID}-volcum" + "-project-wrap", "style"),
    Input(f"{PAGE_ID}-filter-date-preset", "value"),
)

clientside_callback(
    """function(preset) {
        return preset === "current_year" ? {} : {"display": "none"};
    }""",
    Output(f"{PAGE_ID}-rvucum" + "-project-wrap", "style"),
    Input(f"{PAGE_ID}-filter-date-preset", "value"),
)

clientside_callback(
    """function(preset) {
        return preset === "current_year" ? {} : {"display": "none"};
    }""",
    Output(f"{PAGE_ID}-dollarcum" + "-project-wrap", "style"),
    Input(f"{PAGE_ID}-filter-date-preset", "value"),
)

