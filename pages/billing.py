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
    DEFAULT_COLUMN_DEFS, DEFAULT_GRID_OPTIONS,
)
from components.filter_bar import department_chips
from components.kpi_card import kpi_card
from components.chart_card import chart_card, register_chart_callbacks
from utils.charts import apply_default_layout, empty_figure, dept_color, color_for_index
from utils.date_slider import (
    month_idx, idx_to_date, MAX_IDX, DEFAULT_SLIDER, SLIDER_MARKS,
    preset_to_slider_val,
)
from data.reviews_db import (
    get_all_insurance_rates, upsert_insurance_rate, delete_insurance_rate,
    seed_insurance_rates, get_rate_history, upsert_rate_history,
    delete_rate_history_entry,
)

dash.register_page(__name__, path="/billing", name="Billing", order=7)

PAGE_ID = "billing"
_DEFAULT_DATE_PRESET = "12mo"

# CMS Conversion Factor (Medicare PFS) — update annually
_CMS_CF = {2024: 33.29, 2025: 32.35, 2026: 32.35}
_CMS_CF_DEFAULT = 32.35
# Freestanding sites bill global; hospital-based bill pro only
_FREESTANDING_SITES = {"Aberdeen"}


# ---------------------------------------------------------------------------
# CPT Category Mapping
# ---------------------------------------------------------------------------

CPT_CATEGORIES = {
    "E&M": {
        "99202", "99203", "99204", "99205",
        "99211", "99212", "99213", "99214", "99215",
        "99221", "99222", "99223", "99231", "99232",
        "99241", "99242", "99243", "99244", "99245",
        "99251", "99252", "99253", "99254", "99255",
        "99261", "99262", "99263",
        "99271", "99272", "99273", "99274", "99275",
        "99354", "99355", "99356", "99357", "99417",
        "99441", "99442", "99443", "99459", "99499",
        "98003", "98004", "98006", "98007", "98015",
        "G2211", "G2212",
        "99406", "99407", "G0436", "G0437",  # smoking/tobacco cessation
    },
    "Simulation": {
        "77280", "77285", "77290", "77293", "77011", "76370",
    },
    "Treatment Planning": {
        "77261", "77263", "77295", "77300", "77301",
        "77305", "77306", "77307", "77310", "77315", "77316", "77318",
        "77320", "77321", "77328",
    },
    "Physics & Devices": {
        "77331", "77332", "77333", "77334", "77336", "77338", "77370", "77399",
        "77470",
    },
    "Treatment Delivery": {
        "77385", "77386", "77402", "77403", "77404",
        "77407", "77408", "77409", "77412", "77413", "77414", "77416",
        "77417", "77418", "77372", "77373",
        "G6002", "G6004", "G6005", "G6006", "G6009",
        "G6012", "G6013", "G6014", "G6015",
    },
    "Image Guidance": {
        "77014", "77387", "77421", "0197T", "G6017",
    },
    "Treatment Management": {
        "77427", "77431", "77432", "77435",
    },
    "Brachytherapy": {
        "77778", "77790", "76965",
    },
    "Procedures": {
        "55874", "55875", "55876", "76873", "76942", "A4646", "A4648",
    },
    "Drug Administration": {
        "96400", "J9217", "90782",
    },
    "Radiopharmaceutical": {
        "79101",
    },
}

# Build reverse lookup: code → category
_CODE_TO_CATEGORY = {}
for _cat, _codes in CPT_CATEGORIES.items():
    for _code in _codes:
        _CODE_TO_CATEGORY[_code] = _cat

CATEGORY_NAMES = list(CPT_CATEGORIES.keys()) + ["Other"]

CATEGORY_SLUGS = {
    "E&M": "em", "Simulation": "simulation", "Treatment Planning": "planning",
    "Physics & Devices": "physics", "Treatment Delivery": "delivery",
    "Image Guidance": "igrt", "Treatment Management": "management",
    "Brachytherapy": "brachy", "Procedures": "procedures",
    "Drug Administration": "drugs", "Radiopharmaceutical": "radiopharm",
    "Other": "other",
}
SLUG_TO_CATEGORY = {v: k for k, v in CATEGORY_SLUGS.items()}

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
    """Add wRVU, MP_RVU, Fac_PE_RVU, and Fac_Total_RVU columns to billing dataframe."""
    if df.empty:
        df["wRVU"] = 0.0
        df["MP_RVU"] = 0.0
        df["Fac_PE_RVU"] = 0.0
        df["Fac_Total_RVU"] = 0.0
        return df

    df = df.copy()
    df["_base"] = df["ProcedureCode"].apply(_strip_modifier)
    # Map CodeType → RVU modifier
    mod_map = {"Global": "", "Technical": "TC", "Professional": "26"}
    df["_mod"] = df["CodeType"].map(mod_map).fillna("")
    df["_yr"] = df["DateOfService"].dt.year

    # Build lookup dicts from RVU table
    rvu_key = rvu["HCPCS"] + "|" + rvu["MOD"] + "|" + rvu["Year"].astype(str)
    wrvu_dict = dict(zip(rvu_key, rvu["wRVU"]))
    total_dict = dict(zip(rvu_key, rvu["Fac_Total_RVU"]))
    mp_dict = dict(zip(rvu_key, rvu["MP_RVU"]))
    fac_pe_dict = dict(zip(rvu_key, rvu["Fac_PE_RVU"]))

    # Exact match
    exact_key = df["_base"] + "|" + df["_mod"] + "|" + df["_yr"].astype(str)
    df["wRVU"] = exact_key.map(wrvu_dict)
    df["Fac_Total_RVU"] = exact_key.map(total_dict)
    df["MP_RVU"] = exact_key.map(mp_dict)
    df["Fac_PE_RVU"] = exact_key.map(fac_pe_dict)

    # Fallback to Global for unmatched
    mask = df["wRVU"].isna()
    if mask.any():
        global_key = df.loc[mask, "_base"] + "||" + df.loc[mask, "_yr"].astype(str)
        df.loc[mask, "wRVU"] = global_key.map(wrvu_dict)
        df.loc[mask, "Fac_Total_RVU"] = global_key.map(total_dict)
        df.loc[mask, "MP_RVU"] = global_key.map(mp_dict)
        df.loc[mask, "Fac_PE_RVU"] = global_key.map(fac_pe_dict)

    df["wRVU"] = df["wRVU"].fillna(0)
    df["MP_RVU"] = df["MP_RVU"].fillna(0)
    df["Fac_PE_RVU"] = df["Fac_PE_RVU"].fillna(0)
    df["Fac_Total_RVU"] = df["Fac_Total_RVU"].fillna(0)

    df.drop(columns=["_base", "_mod", "_yr"], inplace=True)
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


def _count_spark_raw(df, date_col, start, end):
    """Return daily counts as sparkline data {labels, values}."""
    if df.empty or date_col not in df.columns:
        return {"labels": [], "values": []}
    sub = df[(df[date_col] >= start) & (df[date_col] <= end)]
    daily = sub.groupby(sub[date_col].dt.normalize()).size()
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
                      slice_by="department", slice_configs=None):
    """Build cumulative data for renderCumulative JS.

    mode: "prior" or "slice".
    period_type: "calendar" (shift by year) or "rolling" (shift by period length).
    slice_configs: dict {dim_key: (group_col, names, colors)}.
    """
    if df.empty or date_col not in df.columns:
        return None

    today = pd.Timestamp.now().normalize()
    end_norm = min(end.normalize(), today)
    start_norm = start.normalize()
    period_days = (end_norm - start_norm).days + 1
    if period_days < 2:
        return None

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
        for i in range(1, 6):
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
    for label, p_start, p_end in windows:
        vals = _cum_window(p_start, p_end)
        if vals and any(v > 0 for v in vals):
            if len(vals) < period_days:
                vals += [vals[-1] if vals else 0] * (period_days - len(vals))
            elif len(vals) > period_days:
                vals = vals[:period_days]
            prior.append({"label": label, "values": vals, "color": "#D1D5DB"})

    current_label = _plabel(start, end_norm)
    if len(current_vals) < period_days:
        current_vals += [None] * (period_days - len(current_vals))

    # Slice breakdown (for bar chart in both modes, and for slice line/area)
    slice_breakdown = {"periods": [], "slices": []}
    series = []  # For slice mode line/area
    dates = []

    if slice_configs and slice_by in slice_configs:
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

    return {
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
        "height": 350,
        "yTitle": y_title,
    }


def _build_payor_data(df, label_col, count_col=None, top_n=10):
    """Build payor distribution data.  Returns dict with actual + broad groupings."""
    if df.empty or label_col not in df.columns:
        return {"actual": {"labels": [], "values": [], "colors": []},
                "broad": {"labels": [], "values": [], "colors": []}}

    # Actual insurers
    if count_col:
        totals = df.groupby(label_col)[count_col].sum().sort_values(ascending=False)
    else:
        totals = df[label_col].value_counts()

    top = totals.head(top_n)
    other_val = totals.iloc[top_n:].sum() if len(totals) > top_n else 0
    actual_labels = top.index.tolist()
    actual_values = top.values.tolist()
    if other_val > 0:
        actual_labels.append("Other")
        actual_values.append(int(other_val))
    actual_colors = [color_for_index(i) for i in range(len(actual_labels))]

    # Broad categories
    df = df.copy()
    df["_broad"] = df[label_col].apply(_broad_payor)
    broad_order = [
        "Medicare", "Medicaid", "Private", "Military/VA",
        "Workers Comp", "Tribal/IHS", "Self Pay", "Other/Unknown",
    ]
    broad_colors_map = {
        "Medicare": "#2196F3", "Medicaid": "#4CAF50",
        "Private": "#FF9800", "Military/VA": "#7C2A83",
        "Workers Comp": "#00BCD4", "Tribal/IHS": "#795548",
        "Self Pay": "#F44336", "Other/Unknown": "#9CA3AF",
    }
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
# Cached enriched billing dataframe
# ---------------------------------------------------------------------------

_enriched_cache = {"key": None, "df": None}


def _get_enriched_billing():
    """Return billing df with Category, ChargeStatus, wRVU columns added.

    Caches result — only recomputes when the underlying loader cache changes
    (i.e., new data loaded).
    """
    from data.loader import load_billing, load_rvu_lookup

    billing = load_billing()
    rvu = load_rvu_lookup()

    # Use object ids as cache key (lru_cache returns same object if unchanged)
    key = (id(billing), id(rvu))
    if _enriched_cache["key"] == key and _enriched_cache["df"] is not None:
        return _enriched_cache["df"]

    df = billing.copy()
    # Auto-exclude incomplete, credited, and waived charges
    if "Completed" in df.columns:
        df = df[df["Completed"] == "Yes"]
    if "Credited" in df.columns:
        df = df[df["Credited"] != "Yes"]
    if "Waived" in df.columns:
        df = df[df["Waived"] != "Yes"]

    df["_base_code"] = df["ProcedureCode"].apply(_strip_modifier)
    df["Category"] = df["_base_code"].apply(_assign_category)
    df["ChargeStatus"] = df["ProcedureCode"].apply(_derive_charge_status)
    if not rvu.empty:
        df = _merge_rvu(df, rvu)
    else:
        df["wRVU"] = 0.0
        df["MP_RVU"] = 0.0
        df["Fac_PE_RVU"] = 0.0
        df["Fac_Total_RVU"] = 0.0

    _enriched_cache["key"] = key
    _enriched_cache["df"] = df
    return df


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
                        dmc.ChipGroup(
                            children=[],
                            id=f"{PAGE_ID}-filter-physician",
                            multiple=False,
                        ),
                    ]),
                    dmc.SegmentedControl(
                        id=f"{PAGE_ID}-filter-physician-role",
                        data=[
                            {"value": "supervising", "label": "Supervising"},
                            {"value": "attending", "label": "Attending"},
                        ],
                        value="supervising",
                        size="xs",
                    ),
                    # Category dropdown with Select All / None
                    _chip_dropdown(PAGE_ID, "Category", "category", multiple=True, children=[
                        dmc.Group(
                            children=[
                                dmc.Button("All", id=f"{PAGE_ID}-category-all",
                                           variant="subtle", size="compact-xs", color="violet"),
                                dmc.Button("None", id=f"{PAGE_ID}-category-none",
                                           variant="subtle", size="compact-xs", color="gray"),
                            ],
                            gap="xs", mb=4,
                        ),
                        dmc.ChipGroup(
                            children=[
                                dmc.Chip(c, value=c, size="xs", variant="filled")
                                for c in CATEGORY_NAMES
                            ],
                            id=f"{PAGE_ID}-filter-category",
                            multiple=True,
                            value=[],
                        ),
                    ]),
                    dmc.SegmentedControl(
                        id=f"{PAGE_ID}-filter-codetype",
                        data=[
                            {"value": "all", "label": "All"},
                            {"value": "Professional", "label": "Professional"},
                            {"value": "Technical", "label": "Technical"},
                            {"value": "Global", "label": "Global"},
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
                        value="all",
                        size="xs",
                    ),
                    dmc.Button(
                        "Reviewed",
                        id=f"{PAGE_ID}-btn-reviewed",
                        variant="default", size="compact-sm",
                    ),
                    dcc.Store(id=f"{PAGE_ID}-filter-reviewed", data="all"),
                    dmc.Button(
                        "Exported",
                        id=f"{PAGE_ID}-btn-exported",
                        variant="default", size="compact-sm",
                    ),
                    dcc.Store(id=f"{PAGE_ID}-filter-exported", data="all"),
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
    {"value": "category", "label": "Category"},
    {"value": "department", "label": "Site"},
    {"value": "physician", "label": "MD"},
    {"value": "cpt", "label": "CPT"},
]
_AGG_TOGGLE = [
    {"value": "W", "label": "Weekly"},
    {"value": "M", "label": "Monthly"},
    {"value": "Y", "label": "Yearly"},
]
_PAYOR_TOGGLE = [
    {"value": "actual", "label": "Actual"},
    {"value": "broad", "label": "Broad"},
]
_CHART_TYPES = [
    {"value": "area", "label": "Area"},
    {"value": "line", "label": "Line"},
    {"value": "bar", "label": "Bar"},
]
_CUM_CHART_TYPES = [
    {"value": "line", "label": "Line"},
    {"value": "area", "label": "Area"},
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
                ),
                _build_filter_bar(),
            ],
        ),

        # KPI row — dynamic (zero-count categories hidden)
        dmc.Group(
            id=f"{PAGE_ID}-kpi-row",
            gap="sm",
            grow=True,
            wrap="nowrap",
            style={"overflow": "hidden"},
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
                        show_smooth=False,
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
                                data=_SLICE_TOGGLE, value="department", size="xs",
                            ),
                        ],
                    ),
                    span={"base": 12, "md": 6},
                ),
            ],
        ),

        # Row 2: wRVU Trend + Cumulative
        dmc.Grid(
            gutter="md",
            children=[
                dmc.GridCol(
                    chart_card(
                        f"{PAGE_ID}-chart-rvu-trend",
                        "wRVU Trend",
                        settings_id=f"{PAGE_ID}-rvu",
                        chart_types=_CHART_TYPES,
                        show_smooth=True,
                        smooth_max=50, smooth_default=15,
                        paper_padding="md",
                        extra_controls_left=[
                            dmc.SegmentedControl(
                                id=f"{PAGE_ID}-rvu-slice",
                                data=_SLICE_TOGGLE, value="category", size="xs",
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
                        show_smooth=False,
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
                                data=_SLICE_TOGGLE, value="department", size="xs",
                            ),
                        ],
                    ),
                    span={"base": 12, "md": 6},
                ),
            ],
        ),

        # Row 3: Payor Mix
        dmc.Grid(
            gutter="md",
            mb=0,
            children=[
                dmc.GridCol(
                    chart_card(
                        f"{PAGE_ID}-chart-payor-event",
                        "Payor Mix (Per Billing Event)",
                        settings_id=f"{PAGE_ID}-payevt",
                        show_smooth=False,
                        show_settings=False,
                        paper_padding="md",
                        extra_controls=[
                            dmc.SegmentedControl(
                                id=f"{PAGE_ID}-payor-event-mode",
                                data=_PAYOR_TOGGLE, value="actual", size="xs",
                            ),
                            dmc.SegmentedControl(
                                id=f"{PAGE_ID}-payor-event-unit",
                                data=[{"value": "count", "label": "Count"},
                                      {"value": "pct", "label": "%"}],
                                value="count", size="xs",
                            ),
                        ],
                    ),
                    span={"base": 12, "md": 6},
                ),
                dmc.GridCol(
                    chart_card(
                        f"{PAGE_ID}-chart-payor-patient",
                        "Payor Mix (Per Patient)",
                        settings_id=f"{PAGE_ID}-paypat",
                        show_smooth=False,
                        show_settings=False,
                        paper_padding="md",
                        extra_controls=[
                            dmc.SegmentedControl(
                                id=f"{PAGE_ID}-payor-patient-mode",
                                data=_PAYOR_TOGGLE, value="actual", size="xs",
                            ),
                            dmc.SegmentedControl(
                                id=f"{PAGE_ID}-payor-patient-unit",
                                data=[{"value": "count", "label": "Count"},
                                      {"value": "pct", "label": "%"}],
                                value="count", size="xs",
                            ),
                        ],
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
                    DashIconify(icon="tabler:receipt-2", width=22, color=PRIMARY),
                    dmc.Text("Insurance Rate Manager", fw=600, size="lg"),
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
                         "width": 40, "maxWidth": 40, "sortable": False,
                         "filter": False, "floatingFilter": False,
                         "cellStyle": {"color": "#F44336", "cursor": "pointer",
                                       "textAlign": "center", "fontWeight": 700},
                         "editable": False},
                    ],
                    defaultColDef={
                        "sortable": True,
                        "resizable": True,
                        "filter": "agTextColumnFilter",
                        "floatingFilter": True,
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
                                    defaultColDef={"sortable": True, "resizable": True},
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
                                    defaultColDef={"sortable": True, "resizable": True},
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
            ],
        ),

        # Stores
        dcc.Store(id=f"{PAGE_ID}-store-kpi-sparklines"),
        dcc.Store(id=f"{PAGE_ID}-store-volume"),
        dcc.Store(id=f"{PAGE_ID}-store-volume-cum"),
        dcc.Store(id=f"{PAGE_ID}-store-rvu"),
        dcc.Store(id=f"{PAGE_ID}-store-rvu-cum"),
        dcc.Store(id=f"{PAGE_ID}-store-payor-event"),
        dcc.Store(id=f"{PAGE_ID}-store-payor-patient"),

        dcc.Interval(id=f"{PAGE_ID}-interval", interval=300_000, n_intervals=0),
    ],
)


# ---------------------------------------------------------------------------
# Date Slider Sync Callbacks
# ---------------------------------------------------------------------------

# Preset → slider
@callback(
    Output(f"{PAGE_ID}-date-slider", "value"),
    Input(f"{PAGE_ID}-filter-date-preset", "value"),
    prevent_initial_call=True,
)
def _preset_to_slider(preset):
    if preset == "custom":
        return dash.no_update
    return preset_to_slider_val(preset, MAX_IDX)


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


# ---------------------------------------------------------------------------
# Main Server Callback
# ---------------------------------------------------------------------------

@callback(
    Output(f"{PAGE_ID}-kpi-row", "children"),
    Output(f"{PAGE_ID}-dollar-row", "children"),
    # Store outputs (5 — cumulative stores handled by separate callback)
    Output(f"{PAGE_ID}-store-kpi-sparklines", "data"),
    Output(f"{PAGE_ID}-store-volume", "data"),
    Output(f"{PAGE_ID}-store-rvu", "data"),
    Output(f"{PAGE_ID}-store-payor-event", "data"),
    Output(f"{PAGE_ID}-store-payor-patient", "data"),
    # Inputs
    Input(f"{PAGE_ID}-interval", "n_intervals"),
    Input(f"{PAGE_ID}-filter-daterange", "start_date"),
    Input(f"{PAGE_ID}-filter-daterange", "end_date"),
    Input(f"{PAGE_ID}-filter-department", "value"),
    Input(f"{PAGE_ID}-filter-physician", "value"),
    Input(f"{PAGE_ID}-filter-physician-role", "value"),
    Input(f"{PAGE_ID}-filter-codetype", "value"),
    Input(f"{PAGE_ID}-filter-charge-status", "value"),
    Input(f"{PAGE_ID}-filter-category", "value"),
    Input(f"{PAGE_ID}-filter-reviewed", "data"),
    Input(f"{PAGE_ID}-filter-exported", "data"),
    Input(f"{PAGE_ID}-filter-date-preset", "value"),
)
def update_billing(_n, start_date, end_date, departments, physician,
                   physician_role, codetype, charge_status, categories,
                   reviewed_filter, exported_filter, date_preset):
    """Master callback: KPIs, sparklines, volume, RVU, payor stores."""
    from data.loader import load_patients

    empty_stores = [None] * 5

    try:
        df = _get_enriched_billing()
    except Exception:
        return [], [], *empty_stores
    if df.empty or "DateOfService" not in df.columns:
        return [], [], *empty_stores

    try:
        patients = load_patients()
    except Exception:
        patients = pd.DataFrame()

    # Payor join
    if not patients.empty and "PatientId" in df.columns and "PatientId" in patients.columns:
        ins_cols = ["PatientId", "PrimaryInsurance"]
        ins_cols = [c for c in ins_cols if c in patients.columns]
        if "PrimaryInsurance" in patients.columns:
            df = df.merge(
                patients[ins_cols].drop_duplicates("PatientId"),
                on="PatientId", how="left",
            )
    if "PrimaryInsurance" not in df.columns:
        df["PrimaryInsurance"] = "Unknown"
    df["PrimaryInsurance"] = df["PrimaryInsurance"].fillna("Unknown")

    # ------------------------------------------------------------------
    # Date range
    # ------------------------------------------------------------------
    last_date = df["DateOfService"].dt.normalize().max()
    earliest_date = df["DateOfService"].dt.normalize().min()

    if start_date and end_date:
        start = pd.Timestamp(start_date)
        end = pd.Timestamp(end_date)
    else:
        start = _preset_start(last_date, date_preset or "12mo", earliest_date)
        end = last_date

    # ------------------------------------------------------------------
    # Apply filters
    # ------------------------------------------------------------------
    # Build a reusable non-date dimension mask
    def _dim_mask(base_mask):
        m = base_mask
        if departments and "Department" in df.columns:
            m = m & df["Department"].isin(departments)
        if physician:
            rc = "AttendingPhysician" if physician_role == "attending" else "SupervisingPhysician"
            if rc in df.columns:
                m = m & (df[rc] == physician)
        if codetype and codetype != "all" and "CodeType" in df.columns:
            m = m & (df["CodeType"] == codetype)
        if charge_status and charge_status != "all":
            m = m & (df["ChargeStatus"] == charge_status)
        if categories:
            m = m & df["Category"].isin(categories)
        if reviewed_filter and reviewed_filter != "all" and "Reviewed" in df.columns:
            m = m & (df["Reviewed"] == ("Yes" if reviewed_filter == "yes" else "No"))
        if exported_filter and exported_filter != "all" and "Exported" in df.columns:
            m = m & (df["Exported"] == ("Yes" if exported_filter == "yes" else "No"))
        return m

    mask = _dim_mask((df["DateOfService"] >= start) & (df["DateOfService"] <= end))
    bf = df.loc[mask].copy()

    # All-time data with non-date filters (for cumulative prior periods)
    df_all = df.loc[_dim_mask(pd.Series(True, index=df.index))]

    # Prior period for trend comparison
    p_start, p_end = _prior_range(start, end, date_preset or "12mo")
    prior_mask = _dim_mask((df["DateOfService"] >= p_start) & (df["DateOfService"] <= p_end))
    bf_prior = df.loc[prior_mask]

    # ------------------------------------------------------------------
    # KPIs + sparklines
    # ------------------------------------------------------------------
    sparkline_data = {}
    kpi_children = []  # GridCol-wrapped cards (only non-zero categories)
    active_cats = []

    for cat in CATEGORY_NAMES:
        slug = CATEGORY_SLUGS[cat]
        color = CATEGORY_COLORS[cat]
        curr_count = len(bf[bf["Category"] == cat])
        if curr_count == 0:
            continue
        active_cats.append(cat)
        prior_count = len(bf_prior[bf_prior["Category"] == cat])
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
        spark = _count_spark_raw(cat_df, "DateOfService", start, end)
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

    # ------------------------------------------------------------------
    # Volume + RVU stores (category × department × physician × W/M/Y)
    # ------------------------------------------------------------------
    dept_names = [d for d in DEPARTMENTS if d in bf["Department"].unique()] if "Department" in bf.columns else []

    # Physician names for MD slice (use the role column)
    _role_col = "AttendingPhysician" if physician_role == "attending" else "SupervisingPhysician"
    if _role_col in bf.columns:
        phys_names = sorted(bf[_role_col].dropna().unique())
        phys_colors = {p: CHART_COLORWAY[i % len(CHART_COLORWAY)] for i, p in enumerate(phys_names)}
    else:
        phys_names, phys_colors = [], {}

    active_cat_names = [c for c in CATEGORY_NAMES if c in bf["Category"].unique()]

    def _build_all_aggs(group_col, group_names, group_colors, value_col=None, y_title="Count"):
        """Build W/M/Y variants for one slice dimension."""
        out = {}
        for freq in ("W", "M", "Y"):
            out[freq] = _build_census_data(
                bf, "DateOfService", start, end,
                group_col, group_names, group_colors,
                value_col=value_col, y_title=y_title, freq=freq,
            )
        return out

    volume_store = {
        "category": _build_all_aggs("Category", active_cat_names, CATEGORY_COLORS,
                                     y_title="Billing Events"),
        "department": _build_all_aggs("Department", dept_names, DEPARTMENT_COLORS,
                                       y_title="Billing Events"),
        "physician": _build_all_aggs(_role_col, phys_names, phys_colors,
                                      y_title="Billing Events"),
    }

    rvu_store = {
        "category": _build_all_aggs("Category", active_cat_names, CATEGORY_COLORS,
                                     value_col="wRVU", y_title="wRVU"),
        "department": _build_all_aggs("Department", dept_names, DEPARTMENT_COLORS,
                                       value_col="wRVU", y_title="wRVU"),
        "physician": _build_all_aggs(_role_col, phys_names, phys_colors,
                                      value_col="wRVU", y_title="wRVU"),
    }

    # CPT-code breakdown (only meaningful when exactly 1 category is selected)
    if categories and len(categories) == 1:
        cpt_codes = sorted(bf["_base_code"].dropna().unique())
        cpt_colors = {c: CHART_COLORWAY[i % len(CHART_COLORWAY)] for i, c in enumerate(cpt_codes)}
        volume_store["cpt"] = _build_all_aggs("_base_code", cpt_codes, cpt_colors,
                                               y_title="Billing Events")
        rvu_store["cpt"] = _build_all_aggs("_base_code", cpt_codes, cpt_colors,
                                            value_col="wRVU", y_title="wRVU")

    # Cumulative stores
    # ------------------------------------------------------------------
    # Payor stores
    # ------------------------------------------------------------------
    payor_event = _build_payor_data(bf, "PrimaryInsurance")

    # Per-patient: unique patients in filtered billing data
    if not patients.empty and "PatientId" in bf.columns:
        pat_ids = bf["PatientId"].unique()
        pat_sub = patients[patients["PatientId"].isin(pat_ids)].copy()
        if "PrimaryInsurance" not in pat_sub.columns:
            pat_sub["PrimaryInsurance"] = "Unknown"
        pat_sub["PrimaryInsurance"] = pat_sub["PrimaryInsurance"].fillna("Unknown")
        pat_sub = pat_sub.drop_duplicates("PatientId")
        payor_patient = _build_payor_data(pat_sub, "PrimaryInsurance")
    else:
        payor_patient = _build_payor_data(pd.DataFrame(), "PrimaryInsurance")

    # ------------------------------------------------------------------
    # Dollar estimate row
    # ------------------------------------------------------------------
    # Professional: (wRVU + MP_RVU) × CF for all sites
    # Facility: Fac_PE_RVU × CF — hospital-based sites only (Lacey, Centralia)
    # For freestanding (Aberdeen): pro group gets full Fac_Total_RVU × CF
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

    cf = bf["DateOfService"].dt.year.map(_CMS_CF).fillna(_CMS_CF_DEFAULT)
    has_dept = "Department" in bf.columns
    has_ct = "CodeType" in bf.columns

    if has_dept:
        freestanding = bf["Department"].isin(_FREESTANDING_SITES)
    else:
        freestanding = pd.Series(False, index=bf.index)
    hosp_based = ~freestanding

    if has_ct:
        is_group = bf["CodeType"].isin(["Professional", "Global"])
        is_tech = bf["CodeType"] == "Technical"
    else:
        is_group = pd.Series(True, index=bf.index)
        is_tech = pd.Series(False, index=bf.index)

    # Group revenue:
    #   Hospital-based Pro/Global: (wRVU + MP) × CF (facility PE goes to hospital)
    #   Freestanding Pro/Global: Fac_Total × CF (group keeps everything)
    hb_group = is_group & hosp_based
    fs_group = is_group & freestanding
    group_dollars = (
        ((bf.loc[hb_group, "wRVU"] + bf.loc[hb_group, "MP_RVU"]) * cf.loc[hb_group]).sum()
        + (bf.loc[fs_group, "Fac_Total_RVU"] * cf.loc[fs_group]).sum()
    )

    # Hospital revenue:
    #   All Technical rows: Fac_Total × CF
    #   Hospital-based Pro/Global: Fac_PE × CF (hospital keeps facility component)
    hosp_dollars = (
        (bf.loc[is_tech, "Fac_Total_RVU"] * cf.loc[is_tech]).sum()
        + (bf.loc[hb_group, "Fac_PE_RVU"] * cf.loc[hb_group]).sum()
    )

    total_dollars = group_dollars + hosp_dollars

    dollar_children = [
        _dollar_card("Est. Group Revenue", group_dollars, PRIMARY),
        _dollar_card("Est. Hospital Revenue", hosp_dollars),
        _dollar_card("Est. All-In Total", total_dollars, SEMANTIC_COLORS["success"]),
    ]

    return (kpi_children, dollar_children, sparkline_data, volume_store,
            rvu_store, payor_event, payor_patient)


# ---------------------------------------------------------------------------
# Cumulative Callback (separate for performance — toggles don't recompute KPIs)
# ---------------------------------------------------------------------------

@callback(
    Output(f"{PAGE_ID}-store-volume-cum", "data"),
    Output(f"{PAGE_ID}-store-rvu-cum", "data"),
    Input(f"{PAGE_ID}-interval", "n_intervals"),
    Input(f"{PAGE_ID}-filter-daterange", "start_date"),
    Input(f"{PAGE_ID}-filter-daterange", "end_date"),
    Input(f"{PAGE_ID}-filter-department", "value"),
    Input(f"{PAGE_ID}-filter-physician", "value"),
    Input(f"{PAGE_ID}-filter-physician-role", "value"),
    Input(f"{PAGE_ID}-filter-codetype", "value"),
    Input(f"{PAGE_ID}-filter-charge-status", "value"),
    Input(f"{PAGE_ID}-filter-category", "value"),
    Input(f"{PAGE_ID}-filter-reviewed", "data"),
    Input(f"{PAGE_ID}-filter-exported", "data"),
    Input(f"{PAGE_ID}-filter-date-preset", "value"),
    Input(f"{PAGE_ID}-volcum-mode", "value"),
    Input(f"{PAGE_ID}-volcum-period-type", "value"),
    Input(f"{PAGE_ID}-volcum-slice", "value"),
    Input(f"{PAGE_ID}-rvucum-mode", "value"),
    Input(f"{PAGE_ID}-rvucum-period-type", "value"),
    Input(f"{PAGE_ID}-rvucum-slice", "value"),
)
def update_cumulative(_n, start_date, end_date, departments, physician,
                      physician_role, codetype, charge_status, categories,
                      reviewed_filter, exported_filter, date_preset,
                      volcum_mode, volcum_period_type, volcum_slice,
                      rvucum_mode, rvucum_period_type, rvucum_slice):
    """Cumulative stores only — separate callback so toggle changes are fast."""
    try:
        df = _get_enriched_billing()
    except Exception:
        return None, None
    if df.empty or "DateOfService" not in df.columns:
        return None, None

    # Date range
    last_date = df["DateOfService"].dt.normalize().max()
    earliest_date = df["DateOfService"].dt.normalize().min()
    if start_date and end_date:
        start = pd.Timestamp(start_date)
        end = pd.Timestamp(end_date)
    else:
        start = _preset_start(last_date, date_preset or "12mo", earliest_date)
        end = last_date

    # Non-date filters (all-time dataset for prior period lookback)
    mask = pd.Series(True, index=df.index)
    if departments and "Department" in df.columns:
        mask &= df["Department"].isin(departments)
    if physician:
        rc = "AttendingPhysician" if physician_role == "attending" else "SupervisingPhysician"
        if rc in df.columns:
            mask &= df[rc] == physician
    if codetype and codetype != "all" and "CodeType" in df.columns:
        mask &= df["CodeType"] == codetype
    if charge_status and charge_status != "all":
        mask &= df["ChargeStatus"] == charge_status
    if categories:
        mask &= df["Category"].isin(categories)
    if reviewed_filter and reviewed_filter != "all" and "Reviewed" in df.columns:
        mask &= df["Reviewed"] == ("Yes" if reviewed_filter == "yes" else "No")
    if exported_filter and exported_filter != "all" and "Exported" in df.columns:
        mask &= df["Exported"] == ("Yes" if exported_filter == "yes" else "No")
    df_all = df.loc[mask]

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

    # CPT-code slice for cumulative (only when exactly 1 category selected)
    if categories and len(categories) == 1:
        cpt_codes = sorted(df_all["_base_code"].dropna().unique())
        cpt_colors = {c: CHART_COLORWAY[i % len(CHART_COLORWAY)] for i, c in enumerate(cpt_codes)}
        _slice_cfgs["cpt"] = ("_base_code", cpt_codes, cpt_colors)

    _dp = date_preset or "12mo"

    vol_cum = _build_cumulative(
        df_all, "DateOfService", start, end, _dp,
        y_title="Cumulative Events",
        mode=volcum_mode or "prior",
        period_type=volcum_period_type or "calendar",
        slice_by=volcum_slice or "department",
        slice_configs=_slice_cfgs,
    )
    rvu_cum = _build_cumulative(
        df_all, "DateOfService", start, end, _dp,
        value_col="wRVU", y_title="Cumulative wRVU",
        mode=rvucum_mode or "prior",
        period_type=rvucum_period_type or "calendar",
        slice_by=rvucum_slice or "department",
        slice_configs=_slice_cfgs,
    )
    return vol_cum, rvu_cum


# ---------------------------------------------------------------------------
# Clientside: Volume & RVU Charts (with slice toggle)
# ---------------------------------------------------------------------------

# Wrapper JS: store[sliceMode][agg] → census renderer
_SLICE_AGG_JS = """
function(storeData, sliceMode, agg, smoothPct, chartType, currentFig) {
    if (!storeData) return window.dash_clientside.no_update;
    var sliceData = storeData[sliceMode || "category"];
    if (!sliceData) return window.dash_clientside.no_update;
    var rawData = sliceData[agg || "M"];
    if (!rawData) return window.dash_clientside.no_update;
    return window.dash_clientside.census.smoothChartWithType(rawData, smoothPct, chartType, currentFig);
}
"""

clientside_callback(
    _SLICE_AGG_JS,
    Output(f"{PAGE_ID}-chart-vol-trend", "figure"),
    Input(f"{PAGE_ID}-store-volume", "data"),
    Input(f"{PAGE_ID}-vol-slice", "value"),
    Input(f"{PAGE_ID}-vol-agg", "value"),
    Input(f"{PAGE_ID}-vol-settings-smooth", "value"),
    Input(f"{PAGE_ID}-vol-settings-type", "value"),
    State(f"{PAGE_ID}-chart-vol-trend", "figure"),
)

clientside_callback(
    _SLICE_AGG_JS,
    Output(f"{PAGE_ID}-chart-rvu-trend", "figure"),
    Input(f"{PAGE_ID}-store-rvu", "data"),
    Input(f"{PAGE_ID}-rvu-slice", "value"),
    Input(f"{PAGE_ID}-rvu-agg", "value"),
    Input(f"{PAGE_ID}-rvu-settings-smooth", "value"),
    Input(f"{PAGE_ID}-rvu-settings-type", "value"),
    State(f"{PAGE_ID}-chart-rvu-trend", "figure"),
)

# Cumulative charts (mode/slice handled server-side in store data)
_CUM_JS = """
function(rawData, chartType, currentFig) {
    if (!rawData) return window.dash_clientside.no_update;
    return window.dash_clientside.cumulative.renderCumulative(rawData, 0, chartType, currentFig);
}
"""

clientside_callback(
    _CUM_JS,
    Output(f"{PAGE_ID}-chart-vol-cum", "figure"),
    Input(f"{PAGE_ID}-store-volume-cum", "data"),
    Input(f"{PAGE_ID}-volcum-settings-type", "value"),
    State(f"{PAGE_ID}-chart-vol-cum", "figure"),
)

clientside_callback(
    _CUM_JS,
    Output(f"{PAGE_ID}-chart-rvu-cum", "figure"),
    Input(f"{PAGE_ID}-store-rvu-cum", "data"),
    Input(f"{PAGE_ID}-rvucum-settings-type", "value"),
    State(f"{PAGE_ID}-chart-rvu-cum", "figure"),
)


# ---------------------------------------------------------------------------
# Clientside: Payor Charts
# ---------------------------------------------------------------------------

_PAYOR_BAR_JS = """
function(storeData, mode, unit) {
    if (!storeData) return window.dash_clientside.no_update;
    var d = storeData[mode] || storeData["actual"];
    if (!d || !d.labels || d.labels.length === 0) {
        return {data: [], layout: Object.assign({}, window.dmc_default_layout || {}, {
            xaxis: {visible: false}, yaxis: {visible: false},
            annotations: [{text: "No payor data", xref: "paper", yref: "paper",
                x: 0.5, y: 0.5, showarrow: false, font: {size: 14, color: "#9CA3AF"}}],
            height: 300, margin: {l: 40, r: 20, t: 8, b: 2}
        })};
    }
    var labels = d.labels.slice().reverse();
    var rawValues = d.values.slice().reverse();
    var colors = d.colors.slice().reverse();
    var isPct = unit === "pct";
    var total = 0;
    for (var i = 0; i < rawValues.length; i++) total += rawValues[i];
    var values = isPct ? rawValues.map(function(v) { return total > 0 ? (v / total * 100) : 0; }) : rawValues;
    var hoverFmt = isPct
        ? "%{y}: %{x:.1f}%<extra></extra>"
        : "%{y}: %{x:,}<extra></extra>";
    var textVals = isPct
        ? values.map(function(v) { return v.toFixed(1) + "%"; })
        : null;
    return {
        data: [{
            y: labels, x: values, orientation: "h", type: "bar",
            marker: {color: colors},
            text: textVals,
            textposition: isPct ? "outside" : "none",
            cliponaxis: false,
            hovertemplate: hoverFmt
        }],
        layout: Object.assign({}, window.dmc_default_layout || {}, {
            height: 380,
            margin: {l: 160, r: 16, t: 8, b: 18},
            xaxis: {
                title: {text: ""},
                showgrid: true,
                gridcolor: "#F0F0F0",
                ticksuffix: isPct ? "%" : ""
            },
            yaxis: {showgrid: false, automargin: true},
        })
    };
}
"""

clientside_callback(
    _PAYOR_BAR_JS,
    Output(f"{PAGE_ID}-chart-payor-event", "figure"),
    Input(f"{PAGE_ID}-store-payor-event", "data"),
    Input(f"{PAGE_ID}-payor-event-mode", "value"),
    Input(f"{PAGE_ID}-payor-event-unit", "value"),
)

clientside_callback(
    _PAYOR_BAR_JS,
    Output(f"{PAGE_ID}-chart-payor-patient", "figure"),
    Input(f"{PAGE_ID}-store-payor-patient", "data"),
    Input(f"{PAGE_ID}-payor-patient-mode", "value"),
    Input(f"{PAGE_ID}-payor-patient-unit", "value"),
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
])

# Cumulative control visibility: hide slice toggle when "prior", show when "slice"
_CUM_VIS_JS = """function(mode) {
    if (mode === "prior") {
        return [{}, {"display": "none"}];
    }
    return [{"display": "none"}, {}];
}"""

clientside_callback(
    _CUM_VIS_JS,
    Output(f"{PAGE_ID}-volcum-period-type", "style"),
    Output(f"{PAGE_ID}-volcum-slice", "style"),
    Input(f"{PAGE_ID}-volcum-mode", "value"),
)
clientside_callback(
    _CUM_VIS_JS,
    Output(f"{PAGE_ID}-rvucum-period-type", "style"),
    Output(f"{PAGE_ID}-rvucum-slice", "style"),
    Input(f"{PAGE_ID}-rvucum-mode", "value"),
)


# ---------------------------------------------------------------------------
# CPT slice option: show only when exactly 1 category is selected
# ---------------------------------------------------------------------------

_CPT_SLICE_VIS_JS = """
function(categories, currentVal) {
    var base = [
        {value: "category", label: "Category"},
        {value: "department", label: "Site"},
        {value: "physician", label: "MD"}
    ];
    var show = categories && categories.length === 1;
    if (show) {
        base.push({value: "cpt", label: "CPT"});
        return [base, currentVal];
    }
    // Hide CPT — if currently selected, reset to category
    return [base, currentVal === "cpt" ? "category" : currentVal];
}
"""

clientside_callback(
    _CPT_SLICE_VIS_JS,
    Output(f"{PAGE_ID}-vol-slice", "data"),
    Output(f"{PAGE_ID}-vol-slice", "value"),
    Input(f"{PAGE_ID}-filter-category", "value"),
    State(f"{PAGE_ID}-vol-slice", "value"),
)

clientside_callback(
    _CPT_SLICE_VIS_JS,
    Output(f"{PAGE_ID}-rvu-slice", "data"),
    Output(f"{PAGE_ID}-rvu-slice", "value"),
    Input(f"{PAGE_ID}-filter-category", "value"),
    State(f"{PAGE_ID}-rvu-slice", "value"),
)

clientside_callback(
    _CPT_SLICE_VIS_JS,
    Output(f"{PAGE_ID}-volcum-slice", "data"),
    Output(f"{PAGE_ID}-volcum-slice", "value"),
    Input(f"{PAGE_ID}-filter-category", "value"),
    State(f"{PAGE_ID}-volcum-slice", "value"),
)

clientside_callback(
    _CPT_SLICE_VIS_JS,
    Output(f"{PAGE_ID}-rvucum-slice", "data"),
    Output(f"{PAGE_ID}-rvucum-slice", "value"),
    Input(f"{PAGE_ID}-filter-category", "value"),
    State(f"{PAGE_ID}-rvucum-slice", "value"),
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
)
def _populate_physicians(start_date, end_date, departments, role):
    from data.loader import load_billing
    try:
        billing = load_billing()
    except Exception:
        return []

    if billing.empty:
        return []

    # Apply date + department filters
    if start_date and end_date:
        mask = (billing["DateOfService"] >= pd.Timestamp(start_date)) & \
               (billing["DateOfService"] <= pd.Timestamp(end_date))
        billing = billing.loc[mask]

    if departments and "Department" in billing.columns:
        billing = billing[billing["Department"].isin(departments)]

    # Use the selected role column
    col = "AttendingPhysician" if role == "attending" else "SupervisingPhysician"
    if col not in billing.columns:
        return []

    physicians = sorted(billing[col].dropna().unique())
    return [dmc.Chip(p, value=p, size="xs", variant="filled") for p in physicians]


# ---------------------------------------------------------------------------
# Chip Dropdown: Category (trigger label, clear, select all/none)
# ---------------------------------------------------------------------------

# Trigger label
clientside_callback(
    """function(vals) {
        if (!vals || vals.length === 0) return "Category";
        return vals.length + " selected";
    }""",
    Output(f"{PAGE_ID}-category-trigger", "children"),
    Input(f"{PAGE_ID}-filter-category", "value"),
)

# Clear button visibility
clientside_callback(
    """function(vals) { return vals && vals.length > 0 ? {"display": "inline-flex"} : {"display": "none"}; }""",
    Output(f"{PAGE_ID}-category-clear", "style"),
    Input(f"{PAGE_ID}-filter-category", "value"),
)

# Clear button action
clientside_callback(
    """function(n) { return []; }""",
    Output(f"{PAGE_ID}-filter-category", "value", allow_duplicate=True),
    Input(f"{PAGE_ID}-category-clear", "n_clicks"),
    prevent_initial_call=True,
)

# Select All
_ALL_CATS = [c for c in CATEGORY_NAMES]
clientside_callback(
    "function(n) { return " + str(_ALL_CATS).replace("'", '"') + "; }",
    Output(f"{PAGE_ID}-filter-category", "value", allow_duplicate=True),
    Input(f"{PAGE_ID}-category-all", "n_clicks"),
    prevent_initial_call=True,
)

# Select None
clientside_callback(
    """function(n) { return []; }""",
    Output(f"{PAGE_ID}-filter-category", "value", allow_duplicate=True),
    Input(f"{PAGE_ID}-category-none", "n_clicks"),
    prevent_initial_call=True,
)


# ---------------------------------------------------------------------------
# Reviewed / Exported cycling buttons
# ---------------------------------------------------------------------------
_CYCLE_JS = """
function(n, current) {
    var cycle = {"all": "yes", "yes": "no", "no": "all"};
    var next = cycle[current || "all"];
    var labels = {"all": "%s", "yes": "%s: Yes", "no": "%s: No"};
    var variants = {"all": "default", "yes": "filled", "no": "light"};
    var colors = {"all": "gray", "yes": "green", "no": "red"};
    return [next, labels[next], variants[next], colors[next]];
}
"""

for _col in ("Reviewed", "Exported"):
    _btn_id = f"{PAGE_ID}-btn-{_col.lower()}"
    _store_id = f"{PAGE_ID}-filter-{_col.lower()}"
    clientside_callback(
        _CYCLE_JS % (_col, _col, _col),
        Output(_store_id, "data"),
        Output(_btn_id, "children"),
        Output(_btn_id, "variant"),
        Output(_btn_id, "color"),
        Input(_btn_id, "n_clicks"),
        State(_store_id, "data"),
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
