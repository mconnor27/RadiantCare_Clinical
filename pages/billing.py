"""Billing page — CPT category volumes, wRVU production, and payor mix."""

import threading

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
    DEFAULT_COLUMN_DEFS, DEFAULT_GRID_OPTIONS, DEFAULT_GRID_STYLE,
    DEFAULT_GRID_CLASS, PRIOR_PERIOD_COLORS,
)
from components.filter_bar import department_chips
from components.detail_table import detail_table
from components.phi import apply_phi_grid_rules
from utils.tables import sanitize_for_grid
from utils.permissions import (
    can_see_money,
    can_see_professional_rvu,
    can_see_manager_modals,
)
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
from components.ai_settings import ai_settings_panel, register_ai_settings_callbacks

dash.register_page(__name__, path="/billing", name="Billing", order=7)

PAGE_ID = "billing"
_DEFAULT_DATE_PRESET = "12mo"

# Enrichment helpers + revenue constants live in data/billing_enrichment so
# scripts/sanitize.py can rebuild the parquet cache without importing Dash.
from data.billing_enrichment import (
    _CMS_CF, _CMS_CF_DEFAULT,
    _strip_modifier, _assign_category, _derive_charge_status,
    _merge_rvu,
    _get_enriched_billing, _enriched_source_paths, _enriched_cache,
)
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
    # Round floats to 2 decimals before JSON serialization — saves 30-50%
    # of payload size and JSON.parse time on the client.
    return {
        "labels": [d.strftime("%Y-%m-%d") for d in daily.index],
        "values": np.round(daily.to_numpy(), 2).tolist(),
    }


def _build_census_data(df, date_col, start, end, group_col, group_names, group_colors,
                       value_col=None, y_title="Count", stacked=True, freq="M",
                       _wide=None):
    """Build census-format store data for smoothChartWithType.

    freq: 'W' (weekly), 'M' (monthly), 'Y' (yearly).

    Implementation: ONE groupby + pivot, then iterate the wide frame to
    build series.

    _wide (optional): pre-pivoted wide frame (period index × group_col cols)
    of the value already aggregated. When the caller has already done the
    groupby for multiple value_cols at once (see _build_multi_value_aggregates),
    pass it through to skip a redundant groupby — saves ~3× across the heavy
    /billing render path which builds 3 stores from the same group axes.
    """
    if df.empty or date_col not in df.columns:
        return None

    if _wide is not None:
        wide = _wide
        periods = list(wide.index)
    else:
        freq_map = {"W": "W-MON", "M": "M", "Y": "Y"}
        pd_freq = freq_map.get(freq, "M")
        period = df[date_col].dt.to_period(pd_freq).dt.to_timestamp()

        if group_col not in df.columns:
            # Fallback path: no group_col → treat the whole frame as one series.
            if value_col and value_col in df.columns:
                grouped = pd.Series(df[value_col].values).groupby(period.values).sum()
            else:
                grouped = period.value_counts().sort_index()
            periods = list(grouped.index)
            wide = pd.DataFrame({group_names[0] if group_names else "All": grouped.values},
                                index=periods)
        else:
            if value_col and value_col in df.columns:
                agg = df.groupby([period, df[group_col]])[value_col].sum()
            else:
                agg = df.groupby([period, df[group_col]]).size()
            wide = agg.unstack(level=1, fill_value=0).sort_index()
            periods = list(wide.index)

    dates = [pd.Timestamp(d).strftime("%Y-%m-%d") for d in periods]

    series = []
    for name in group_names:
        if name in wide.columns:
            values = wide[name].to_numpy()
        else:
            values = np.zeros(len(periods), dtype=float)
        series.append({
            "name": name,
            # Round to 2 decimals — cuts JSON payload size 30-50% with no
            # user-visible change (chart axes already format to 0-1 decimals).
            "values": np.round(values, 2).tolist(),
            "color": group_colors.get(name, CHART_COLORWAY[len(series) % len(CHART_COLORWAY)]),
        })

    return {
        "dates": dates,
        "series": series,
        "yTitle": y_title,
        "stacked": stacked,
        "height": 380,
    }


def _build_multi_value_aggregates(df, date_col, group_col, value_cols, freq="M"):
    """One multi-column groupby that produces a dict of pre-pivoted wide frames.

    Returns {value_col: wide_frame} where each wide_frame has period index +
    group_col-value columns. Used by the heavy /billing chart-store path so
    Volume / RVU / Dollar stores share a single groupby per (group_col, freq)
    instead of running it three separate times.

    Skipped value_cols (not present in df) are omitted from the returned dict.
    """
    if df.empty or date_col not in df.columns or group_col not in df.columns:
        return {}
    cols_present = [c for c in value_cols if c in df.columns]
    if not cols_present:
        return {}
    freq_map = {"W": "W-MON", "M": "M", "Y": "Y"}
    pd_freq = freq_map.get(freq, "M")
    period = df[date_col].dt.to_period(pd_freq).dt.to_timestamp()
    multi = df.groupby([period, df[group_col]])[cols_present].sum()
    out = {}
    for vc in cols_present:
        out[vc] = multi[vc].unstack(level=1, fill_value=0).sort_index()
    return out


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
        # Round to 2 decimals before JSON serialize — big payload savings.
        cum = daily.reindex(idx, fill_value=0).cumsum()
        return np.round(cum.to_numpy(), 2).tolist()

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
                updatemode="mouseup",
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


def _row_payor_groups(series, mode, mapping):
    """Return a Series mapping each PrimaryInsurance value to its group name
    under the given mode (actual/broad/phdsc). Used by the filter bar — no
    top-N rollup or 'Other' bucketing so every row keeps its true group."""
    s = series.fillna("Unknown")
    if mode == "broad":
        def _r(name):
            if name in mapping and mapping[name].get("broad_category"):
                return mapping[name]["broad_category"]
            return _broad_payor(name)
        return s.apply(_r)
    if mode == "phdsc":
        def _r(name):
            if name in mapping and mapping[name].get("phdsc_category"):
                cat = mapping[name]["phdsc_category"]
                for pc in _PHDSC_CATEGORIES:
                    if pc.startswith(f"{cat} "):
                        return pc
                return "9 - Other"
            return "9 - Other"
        return s.apply(_r)
    # actual — standardized payor name (fallback to raw)
    def _r(name):
        if name in mapping and mapping[name].get("standardized_payor"):
            return mapping[name]["standardized_payor"]
        return name
    return s.apply(_r)


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
# Filter result cache — shared between main and cumulative callbacks
# ---------------------------------------------------------------------------

_filter_cache = {"key": None, "result": None}

# Cache for the slow chart-store callback's full output (metrics_store +
# table). Single slot, keyed by filter state + rev_adj + grid_rows. The
# heavy work is ~1s on full-history data; same filters firing twice (e.g.
# user navigates away and back, or two browser tabs land on /billing with
# default filters) hit the cache instantly.
_charts_table_cache = {"key": None, "result": None}


def _filter_kwargs_key(kwargs):
    """Stable hashable key from filter kwargs (lists → tuples)."""
    parts = []
    for k in sorted(kwargs.keys()):
        v = kwargs[k]
        if isinstance(v, list):
            v = tuple(v) if v else ()
        parts.append((k, v))
    return tuple(parts)


def _load_and_filter_billing_cached(**kwargs):
    """Cached wrapper — avoids re-filtering when main and cumulative callbacks
    fire on the same filter state (sequential execution in single-threaded Dash)."""
    key = _filter_kwargs_key(kwargs)
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
                    _chip_dropdown(PAGE_ID, "Payor", "payor-filter", children=[
                        dmc.SegmentedControl(
                            id=f"{PAGE_ID}-filter-payor-mode",
                            data=_PAYOR_MODE_TOGGLE,
                            value="broad",
                            size="xs",
                            fullWidth=True,
                            mb="xs",
                        ),
                        html.Div(
                            dmc.ChipGroup(
                                children=[],
                                id=f"{PAGE_ID}-filter-payor",
                                multiple=True,
                                value=[],
                            ),
                            style={"maxHeight": 280, "overflowY": "auto",
                                   "minWidth": 240},
                        ),
                    ]),
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
                    # A/R lag toggle — shifts every row's DateOfService forward
                    # by the saved lag so dollar metrics/charts on the page
                    # read as cash-arriving rather than billing-date.
                    dmc.Tooltip(
                        label=("Shift every DateOfService forward by the saved "
                               "A/R lag so dollar metrics reflect cash-arriving "
                               "timing. Totals that aren't date-filtered are "
                               "unchanged."),
                        multiline=True, w=260, position="bottom-end", withArrow=True,
                        children=dmc.Switch(
                            id=f"{PAGE_ID}-filter-ar-lag-apply",
                            label=html.Span(id=f"{PAGE_ID}-filter-ar-lag-label",
                                            children="A/R lag"),
                            size="sm", color="violet", checked=False,
                        ),
                    ),
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
        # Plain-HTML overlay (always in the DOM, no React portal). A
        # clientside className toggle lets it appear instantly on click,
        # giving the user feedback while the heavy DMC Modal behind it
        # does its first layout pass.
        html.Div(
            id=f"{PAGE_ID}-irm-overlay",
            className="heavy-modal-overlay hidden",
            children=[
                html.Div(
                    className="heavy-modal-overlay-card",
                    children=[
                        html.Div(className="heavy-modal-spinner"),
                        html.Div("Loading Payor Manager…",
                                 className="heavy-modal-overlay-text"),
                    ],
                ),
            ],
        ),

        # Hidden interval: armed by the click, fires once to open the
        # heavy modal after the overlay has painted.
        dcc.Interval(
            id=f"{PAGE_ID}-irm-delay",
            interval=60,
            disabled=True,
            max_intervals=1,
            n_intervals=0,
        ),

        dmc.Modal(
            id=f"{PAGE_ID}-irm-modal",
            opened=False,
            # keepMounted=False so the modal's heavy internals (AG Grid, Rev-Adj
            # plot, multi-slider trees) don't live in the DOM on page load.
            # Trade-off: first open remounts from scratch (already masked by the
            # heavy-modal-overlay shown via irm-btn click).
            keepMounted=False,
            transitionProps={"transition": "fade", "duration": 120},
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
                                        dmc.Group(
                                            gap="xs",
                                            children=[
                                                dmc.Button(
                                                    "Classify (AI)",
                                                    id=f"{PAGE_ID}-pm-ai-btn",
                                                    leftSection=DashIconify(icon="tabler:brain", width=14),
                                                    variant="light", color="grape", size="xs",
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
                                    ],
                                ),
                                html.Div(ai_settings_panel("bill", compact=True),
                                         style={"marginBottom": "6px"}),
                                dmc.Progress(
                                    id=f"{PAGE_ID}-pm-ai-progress",
                                    value=0, size="sm", color="grape",
                                    style={"display": "none"}, mb=4,
                                ),
                                dmc.Text(
                                    id=f"{PAGE_ID}-pm-ai-progress-text", size="xs",
                                    c="dimmed", style={"display": "none"}, mb=4,
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
                                dcc.Interval(id=f"{PAGE_ID}-pm-ai-poll", interval=2000, disabled=True),
                                dmc.Modal(
                                    id=f"{PAGE_ID}-pm-ai-review",
                                    opened=False,
                                    title=dmc.Group(
                                        children=[
                                            DashIconify(icon="tabler:brain", width=22, color="grape"),
                                            dmc.Text("AI Payor Classification — Review before applying",
                                                     fw=600, size="lg"),
                                        ],
                                        gap="xs",
                                    ),
                                    size="95%",
                                    centered=True,
                                    zIndex=2100,
                                    styles={
                                        "content": {"height": "85vh", "display": "flex",
                                                    "flexDirection": "column"},
                                        "body": {"flex": 1, "overflow": "hidden",
                                                 "display": "flex", "flexDirection": "column"},
                                    },
                                    children=[
                                        dmc.Group(
                                            justify="flex-end", mb=8,
                                            children=[
                                                dmc.Button(
                                                    "Accept All",
                                                    id=f"{PAGE_ID}-pm-ai-accept-all",
                                                    leftSection=DashIconify(icon="tabler:checks", width=14),
                                                    variant="light", color="green", size="sm",
                                                ),
                                                dmc.Button(
                                                    "Reject All",
                                                    id=f"{PAGE_ID}-pm-ai-reject-all",
                                                    leftSection=DashIconify(icon="tabler:x", width=14),
                                                    variant="light", color="red", size="sm",
                                                ),
                                                dmc.Button(
                                                    "Apply Selected",
                                                    id=f"{PAGE_ID}-pm-ai-apply",
                                                    leftSection=DashIconify(icon="tabler:check", width=14),
                                                    variant="filled", color="green", size="sm",
                                                ),
                                            ],
                                        ),
                                        dag.AgGrid(
                                            id=f"{PAGE_ID}-pm-ai-review-grid",
                                            columnDefs=[
                                                {"field": "accept", "headerName": "Accept",
                                                 "width": 90, "cellDataType": "boolean",
                                                 "editable": True},
                                                {"field": "raw_name", "headerName": "Raw Name",
                                                 "flex": 1.4, "minWidth": 200,
                                                 "cellStyle": {"fontSize": "12px"}},
                                                {"field": "event_count", "headerName": "Events",
                                                 "flex": 0.35, "type": "numericColumn"},
                                                {"field": "current_standardized",
                                                 "headerName": "Current Std",
                                                 "flex": 0.9,
                                                 "cellStyle": {"color": "#9CA3AF"}},
                                                {"field": "ai_standardized", "headerName": "AI Standardized",
                                                 "flex": 1, "editable": True,
                                                 "cellStyle": {"fontWeight": 600}},
                                                {"field": "ai_broad", "headerName": "AI Category",
                                                 "flex": 0.7, "editable": True,
                                                 "cellEditor": "agSelectCellEditor",
                                                 "cellEditorParams": {"values": [
                                                     "Medicare", "Medicaid", "Private", "Military/VA",
                                                     "Workers Comp", "Tribal/IHS", "Self Pay",
                                                     "Other/Unknown",
                                                 ]},
                                                 "cellStyle": {"fontWeight": 600,
                                                               "cursor": "pointer"}},
                                                {"field": "ai_phdsc", "headerName": "AI PHDSC",
                                                 "flex": 0.6, "editable": True,
                                                 "cellEditor": "agSelectCellEditor",
                                                 "cellEditorParams": {"values": [
                                                     "1 - Medicare", "2 - Medicaid/CHIP",
                                                     "3 - Other Govt", "4 - Corrections",
                                                     "5 - Private", "6 - BCBS",
                                                     "8 - No Payment", "9 - Other",
                                                 ]},
                                                 "cellStyle": {"fontWeight": 600,
                                                               "cursor": "pointer"}},
                                                {"field": "explanation", "headerName": "Explanation",
                                                 "flex": 2, "wrapText": True, "autoHeight": True,
                                                 "cellStyle": {"fontSize": "11px",
                                                               "lineHeight": "1.35",
                                                               "color": "#374151"}},
                                            ],
                                            defaultColDef={"sortable": True, "resizable": True,
                                                           "valueFormatter": {"function":
                                                               "params.value == null || params.value === '' ? '–' : params.value"}},
                                            dashGridOptions={
                                                "rowHeight": 48,
                                                "headerHeight": 36,
                                                "pagination": True,
                                                "paginationPageSize": 25,
                                                "singleClickEdit": True,
                                            },
                                            style={"flex": 1, "minHeight": 0},
                                            className="ag-theme-alpine",
                                        ),
                                    ],
                                ),
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
                                # Two-column layout: controls on left (~33%), plot on right (~67%)
                                html.Div(
                                    style={
                                        "display": "flex",
                                        "gap": "16px",
                                        "alignItems": "stretch",
                                        "flex": 1,
                                        "minHeight": 0,
                                    },
                                    children=[
                                        # LEFT: controls column
                                        html.Div(
                                            style={
                                                "flex": "0 0 34%",
                                                "display": "flex",
                                                "flexDirection": "column",
                                                "gap": "12px",
                                                "minWidth": 0,
                                            },
                                            children=[
                                                # Top blurb + enable toggle
                                                dmc.Paper(
                                                    p="sm", radius="md", withBorder=True,
                                                    children=[
                                                        dmc.Text(
                                                            "The realization factor is always applied. "
                                                            "The toggle below controls whether per-category "
                                                            "payer-mix multipliers are also applied.",
                                                            size="xs", c="dimmed", mb="xs",
                                                        ),
                                                        dmc.Switch(
                                                            id=f"{PAGE_ID}-rev-adj-enabled",
                                                            label="Enable per-category payer-mix multipliers",
                                                            size="sm",
                                                            checked=False,
                                                            color="violet",
                                                        ),
                                                    ],
                                                ),

                                                # Category multipliers
                                                dmc.Paper(
                                                    p="md", pb=28, radius="md", withBorder=True,
                                                    id=f"{PAGE_ID}-rev-adj-cat-paper",
                                                    children=[
                                                        dmc.Group(
                                                            gap="xs", mb="xs", justify="space-between", wrap="nowrap",
                                                            children=[
                                                                dmc.Group(
                                                                    gap="xs",
                                                                    children=[
                                                                        DashIconify(icon="tabler:percentage", width=18, color=PRIMARY),
                                                                        dmc.Text("Category Multipliers (% of Medicare)", fw=600, size="sm"),
                                                                    ],
                                                                ),
                                                                dmc.Button(
                                                                    "Reset",
                                                                    id=f"{PAGE_ID}-rev-adj-reset-mults",
                                                                    variant="subtle", color="gray", size="compact-xs",
                                                                    leftSection=DashIconify(icon="tabler:refresh", width=12),
                                                                ),
                                                            ],
                                                        ),
                                                        dmc.Text(
                                                            "Estimate how each broad payer category reimburses "
                                                            "relative to Medicare allowed amounts.",
                                                            size="xs", c="dimmed", mb="sm",
                                                        ),
                                                        dmc.Stack(
                                                            gap=22,
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
                                                    p="md", pb=28, radius="md", withBorder=True,
                                                    children=[
                                                        dmc.Group(
                                                            gap="xs", mb="xs",
                                                            children=[
                                                                DashIconify(icon="tabler:receipt-off", width=18, color=PRIMARY),
                                                                dmc.Text("Realization Factor", fw=600, size="sm"),
                                                            ],
                                                        ),
                                                        dmc.Text(
                                                            "Discount applied to all revenue estimates to account for "
                                                            "denials, adjustments, underpayments, and write-offs.",
                                                            size="xs", c="dimmed", mb="sm",
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
                                                                    updatemode="mouseup",  # native rAF loop handles live drag
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
                                        ),

                                        # RIGHT: plot column
                                        html.Div(
                                            style={
                                                "flex": 1,
                                                "display": "flex",
                                                "flexDirection": "column",
                                                "gap": "10px",
                                                "minWidth": 0,
                                            },
                                            children=[
                                                # Date presets + date range picker
                                                dmc.Paper(
                                                    p="sm", radius="md", withBorder=True,
                                                    children=[
                                                        dmc.Group(
                                                            gap="sm", align="center", wrap="wrap",
                                                            children=[
                                                                dmc.SegmentedControl(
                                                                    id=f"{PAGE_ID}-rev-adj-date-preset",
                                                                    data=[
                                                                        {"value": "ytd", "label": "YTD"},
                                                                        {"value": "last_year", "label": "Last Yr"},
                                                                        {"value": "12mo", "label": "12 mo"},
                                                                        {"value": "24mo", "label": "24 mo"},
                                                                        {"value": "5yr", "label": "5 yr"},
                                                                        {"value": "all", "label": "All"},
                                                                        {"value": "custom", "label": "Custom"},
                                                                    ],
                                                                    value="ytd",
                                                                    size="xs",
                                                                ),
                                                                dcc.DatePickerRange(
                                                                    id=f"{PAGE_ID}-rev-adj-daterange",
                                                                    display_format="YYYY-MM-DD",
                                                                    minimum_nights=0,
                                                                    clearable=False,
                                                                    className="rev-adj-daterange-compact",
                                                                ),
                                                                dmc.Menu(
                                                                    position="bottom-end",
                                                                    withinPortal=True,
                                                                    zIndex=1100,
                                                                    children=[
                                                                        dmc.MenuTarget(
                                                                            dmc.Button(
                                                                                "Auto-fit",
                                                                                id=f"{PAGE_ID}-rev-adj-auto-realization",
                                                                                variant="light", color="violet",
                                                                                size="compact-xs",
                                                                                leftSection=DashIconify(icon="tabler:wand", width=12),
                                                                                rightSection=DashIconify(icon="tabler:chevron-down", width=12),
                                                                            ),
                                                                        ),
                                                                        dmc.MenuDropdown([
                                                                            dmc.MenuLabel("Least-squares fit over selected range"),
                                                                            dmc.MenuItem(
                                                                                "Realization only",
                                                                                id=f"{PAGE_ID}-rev-adj-auto-r-only",
                                                                                leftSection=DashIconify(icon="tabler:percentage", width=14),
                                                                            ),
                                                                            dmc.MenuItem(
                                                                                "A/R Lag only",
                                                                                id=f"{PAGE_ID}-rev-adj-auto-lag-only",
                                                                                leftSection=DashIconify(icon="tabler:clock-hour-4", width=14),
                                                                            ),
                                                                            dmc.MenuItem(
                                                                                "Realization + A/R Lag",
                                                                                id=f"{PAGE_ID}-rev-adj-auto-both",
                                                                                leftSection=DashIconify(icon="tabler:wand", width=14),
                                                                            ),
                                                                            dmc.MenuDivider(),
                                                                            dmc.MenuItem(
                                                                                "Detect drift (segments)",
                                                                                id=f"{PAGE_ID}-rev-adj-auto-segments",
                                                                                leftSection=DashIconify(icon="tabler:chart-dots", width=14),
                                                                            ),
                                                                            dmc.MenuItem(
                                                                                "Clear drift markers",
                                                                                id=f"{PAGE_ID}-rev-adj-auto-clear",
                                                                                leftSection=DashIconify(icon="tabler:eraser", width=14),
                                                                            ),
                                                                        ]),
                                                                    ],
                                                                ),
                                                                # Drift thresholds — in a portaled popover so it
                                                                # never affects the plot's layout container.
                                                                dmc.Popover(
                                                                    position="bottom-end",
                                                                    withArrow=True,
                                                                    withinPortal=True,
                                                                    zIndex=1400,
                                                                    shadow="md",
                                                                    children=[
                                                                        dmc.PopoverTarget(
                                                                            dmc.ActionIcon(
                                                                                DashIconify(icon="tabler:adjustments-horizontal", width=14),
                                                                                variant="subtle", color="gray", size="sm",
                                                                            ),
                                                                        ),
                                                                        dmc.PopoverDropdown(
                                                                            style={"width": 280, "padding": 12},
                                                                            children=[
                                                                                dmc.Text("Drift detection",
                                                                                         fw=600, size="xs", mb=8),
                                                                                dmc.Group(
                                                                                    gap="xs", align="center", wrap="nowrap", mb=14,
                                                                                    children=[
                                                                                        dmc.Text("Sensitivity", size="xs",
                                                                                                 style={"minWidth": 74}),
                                                                                        dmc.Slider(
                                                                                            id=f"{PAGE_ID}-rev-adj-drift-sens",
                                                                                            min=5, max=40, step=1, value=15,
                                                                                            marks=[
                                                                                                {"value": 5, "label": "5"},
                                                                                                {"value": 20, "label": "20"},
                                                                                                {"value": 40, "label": "40"},
                                                                                            ],
                                                                                            color="orange", size="xs",
                                                                                            updatemode="mouseup",
                                                                                            style={"flex": 1},
                                                                                        ),
                                                                                        dmc.Text(
                                                                                            id=f"{PAGE_ID}-rev-adj-drift-sens-val",
                                                                                            size="xs", fw=600, c="#F97316",
                                                                                            style={"minWidth": 28, "textAlign": "right"},
                                                                                        ),
                                                                                    ],
                                                                                ),
                                                                                dmc.Text(
                                                                                    "Min SSR improvement (%) to place a split. "
                                                                                    "Higher = fewer segments.",
                                                                                    size="xs", c="dimmed", mb=12,
                                                                                ),
                                                                                dmc.Group(
                                                                                    gap="xs", align="center", wrap="nowrap",
                                                                                    children=[
                                                                                        dmc.Text("Flag ≥", size="xs",
                                                                                                 style={"minWidth": 74}),
                                                                                        dmc.Slider(
                                                                                            id=f"{PAGE_ID}-rev-adj-drift-hl",
                                                                                            min=1, max=15, step=1, value=3,
                                                                                            marks=[
                                                                                                {"value": 1, "label": "1"},
                                                                                                {"value": 5, "label": "5"},
                                                                                                {"value": 15, "label": "15"},
                                                                                            ],
                                                                                            color="orange", size="xs",
                                                                                            updatemode="mouseup",
                                                                                            style={"flex": 1},
                                                                                        ),
                                                                                        dmc.Text(
                                                                                            id=f"{PAGE_ID}-rev-adj-drift-hl-val",
                                                                                            size="xs", fw=600, c="#F97316",
                                                                                            style={"minWidth": 28, "textAlign": "right"},
                                                                                        ),
                                                                                    ],
                                                                                ),
                                                                                dmc.Text(
                                                                                    "Drift magnitude (pp) that flags a "
                                                                                    "segment orange.",
                                                                                    size="xs", c="dimmed",
                                                                                ),
                                                                            ],
                                                                        ),
                                                                    ],
                                                                ),
                                                            ],
                                                        ),
                                                        dmc.Group(
                                                            gap="lg", align="center", wrap="nowrap", mt=16,
                                                            children=[
                                                                # A/R Lag (compact)
                                                                dmc.Group(
                                                                    gap="xs", align="center", wrap="nowrap",
                                                                    style={"flex": 1, "minWidth": 0},
                                                                    children=[
                                                                        dmc.Text("A/R Lag", size="xs", fw=600,
                                                                                 style={"flexShrink": 0}),
                                                                        dmc.Slider(
                                                                            id=f"{PAGE_ID}-rev-adj-ar-lag",
                                                                            min=0, max=90, step=1, value=30,
                                                                            marks=[
                                                                                {"value": 0, "label": "0"},
                                                                                {"value": 30, "label": "30"},
                                                                                {"value": 60, "label": "60"},
                                                                                {"value": 90, "label": "90"},
                                                                            ],
                                                                            color="violet",
                                                                            size="xs",
                                                                            updatemode="mouseup",
                                                                            style={"flex": 1, "minWidth": 120},
                                                                        ),
                                                                        dmc.Text(
                                                                            id=f"{PAGE_ID}-rev-adj-ar-lag-val",
                                                                            size="xs", fw=600, c=PRIMARY,
                                                                            style={"minWidth": 34, "textAlign": "right"},
                                                                        ),
                                                                    ],
                                                                ),
                                                                # Smoothing (compact)
                                                                dmc.Group(
                                                                    gap="xs", align="center", wrap="nowrap",
                                                                    style={"flex": 1, "minWidth": 0},
                                                                    children=[
                                                                        dmc.Text("Smoothing", size="xs", fw=600,
                                                                                 style={"flexShrink": 0}),
                                                                        dmc.Slider(
                                                                            id=f"{PAGE_ID}-rev-adj-smooth",
                                                                            min=0, max=30, step=1, value=7,
                                                                            marks=[
                                                                                {"value": 0, "label": "0"},
                                                                                {"value": 7, "label": "7"},
                                                                                {"value": 14, "label": "14"},
                                                                                {"value": 30, "label": "30"},
                                                                            ],
                                                                            color="violet",
                                                                            size="xs",
                                                                            updatemode="mouseup",
                                                                            style={"flex": 1, "minWidth": 120},
                                                                        ),
                                                                        dmc.Text(
                                                                            id=f"{PAGE_ID}-rev-adj-smooth-val",
                                                                            size="xs", fw=600, c=PRIMARY,
                                                                            style={"minWidth": 34, "textAlign": "right"},
                                                                        ),
                                                                    ],
                                                                ),
                                                            ],
                                                        ),
                                                        dmc.Text(
                                                            "A/R lag rebuilds the estimated curve from billings "
                                                            "that occurred this many days earlier, to account "
                                                            "for claims processing delay. Smoothing applies a "
                                                            "centered moving average (days).",
                                                            size="xs", c="dimmed", mt=22,
                                                        ),
                                                    ],
                                                ),

                                                # Dummy output for the fast-path restyle callback
                                                dcc.Store(id=f"{PAGE_ID}-rev-adj-restyle-sink"),
                                                # Store remembering which (start,end) were set by a preset
                                                dcc.Store(id=f"{PAGE_ID}-store-rev-adj-preset-dates"),

                                                # Plot
                                                dmc.Paper(
                                                    id=f"{PAGE_ID}-rev-adj-plot-paper",
                                                    p="sm", radius="md", withBorder=True,
                                                    style={"flex": 1, "minHeight": 360, "display": "flex", "flexDirection": "column",
                                                           "position": "relative"},
                                                    children=[
                                                        dcc.Loading(
                                                            type="circle",
                                                            color=PRIMARY,
                                                            delay_show=120,  # avoid flicker for fast callbacks
                                                            # Wrap BOTH the data store and the Graph so the store
                                                            # callback activity also shows the spinner.
                                                            children=[
                                                                dcc.Store(id=f"{PAGE_ID}-store-rev-adj-plot"),
                                                                dcc.Graph(
                                                                    id=f"{PAGE_ID}-rev-adj-plot",
                                                                    config={"displayModeBar": False, "responsive": False},
                                                                    style={"height": "100%", "flex": 1},
                                                                    figure={
                                                                        "data": [],
                                                                        "layout": {
                                                                            "xaxis": {"visible": False},
                                                                            "yaxis": {"visible": False},
                                                                            "margin": {"l": 0, "r": 0, "t": 0, "b": 0},
                                                                            "plot_bgcolor": "rgba(0,0,0,0)",
                                                                            "paper_bgcolor": "rgba(0,0,0,0)",
                                                                            "annotations": [{
                                                                                "text": "Loading revenue data…",
                                                                                "xref": "paper", "yref": "paper",
                                                                                "x": 0.5, "y": 0.5,
                                                                                "showarrow": False,
                                                                                "font": {"size": 13, "color": "#9CA3AF"},
                                                                            }],
                                                                        },
                                                                    },
                                                                ),
                                                            ],
                                                            parent_style={"flex": 1, "display": "flex", "flexDirection": "column"},
                                                        ),
                                                    ],
                                                ),
                                            ],
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
        # Unified metrics stores: {"volume": {...}, "rvu": {...}|null, "dollar": {...}}
        # One store per family cuts the number of selector passes Dash fires
        # per filter change from 6 to 2.
        dcc.Store(id=f"{PAGE_ID}-store-metrics"),
        dcc.Store(id=f"{PAGE_ID}-store-metrics-cum"),
        dcc.Store(id=f"{PAGE_ID}-store-rev-adj", data=get_revenue_adj_settings()),
        dcc.Store(id=f"{PAGE_ID}-table-filter-rows"),

        dcc.Interval(id=f"{PAGE_ID}-interval", interval=300_000, n_intervals=0),
    ],
)


# ---------------------------------------------------------------------------
# A/R lag apply-switch: initialize from saved settings + persist on change
# ---------------------------------------------------------------------------

@callback(
    Output(f"{PAGE_ID}-filter-ar-lag-apply", "checked"),
    Output(f"{PAGE_ID}-filter-ar-lag-label", "children"),
    Input(f"{PAGE_ID}-filter-ar-lag-apply", "id"),  # fire-once on mount
    Input(f"{PAGE_ID}-store-rev-adj", "data"),      # refresh when modal saves
)
def _init_ar_lag_switch(_id, store):
    s = store or get_revenue_adj_settings()
    lag = int(s.get("ar_lag", 30) or 0)
    return bool(s.get("ar_lag_enabled", 0)), f"A/R lag ({lag}d)"


@callback(
    Output(f"{PAGE_ID}-store-rev-adj", "data", allow_duplicate=True),
    Input(f"{PAGE_ID}-filter-ar-lag-apply", "checked"),
    State(f"{PAGE_ID}-store-rev-adj", "data"),
    prevent_initial_call=True,
)
def _toggle_ar_lag(checked, current):
    prior = dict(current or get_revenue_adj_settings())
    prior["ar_lag_enabled"] = 1.0 if checked else 0.0
    save_revenue_adj_settings(prior)
    return prior


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
    Input(f"{PAGE_ID}-filter-payor-mode", "value"),
    Input(f"{PAGE_ID}-filter-payor", "value"),
]

_N_BILLING_FILTER_INPUTS = len(_BILLING_FILTER_INPUTS)


def _unpack_billing_filter_args(args):
    """Unpack the common filter args into kwargs for _load_and_filter_billing.

    Also reads rev_adj (args[_N_BILLING_FILTER_INPUTS] if present) to derive
    `ar_lag_days`: the saved A/R lag value if the filter-bar toggle is on,
    otherwise 0.
    """
    (_n, start_date, end_date, departments, physician,
     physician_role, codetype, charge_status, categories, cpt_codes,
     pro_reviewed, pro_exported, excl_credited, excl_waived,
     hosp_reviewed, hosp_exported, hosp_excl_credited, hosp_excl_waived,
     date_preset, payor_mode, payor_selected) = args[:_N_BILLING_FILTER_INPUTS]
    rev_adj = args[_N_BILLING_FILTER_INPUTS] if len(args) > _N_BILLING_FILTER_INPUTS else None
    ar_lag_days = 0
    if rev_adj and rev_adj.get("ar_lag_enabled"):
        ar_lag_days = int(rev_adj.get("ar_lag", 0) or 0)
    return dict(
        start_date=start_date, end_date=end_date, departments=departments,
        physician=physician, physician_role=physician_role, codetype=codetype,
        charge_status=charge_status, categories=categories, cpt_codes=cpt_codes,
        pro_reviewed=pro_reviewed, pro_exported=pro_exported,
        excl_credited=excl_credited, excl_waived=excl_waived,
        hosp_reviewed=hosp_reviewed, hosp_exported=hosp_exported,
        hosp_excl_credited=hosp_excl_credited, hosp_excl_waived=hosp_excl_waived,
        date_preset=date_preset, ar_lag_days=ar_lag_days,
        payor_mode=payor_mode, payor_selected=payor_selected,
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
                             date_preset=None, ar_lag_days=0,
                             payor_mode=None, payor_selected=None):
    """Load enriched billing, apply date range + dimension filters.

    `ar_lag_days` shifts every row's DateOfService forward by that many days
    before any date-based filtering or grouping — effectively re-interprets
    the data as cash-arriving (DOS + lag) rather than billed-on (DOS).
    Pass 0 (default) to disable.

    Returns dict with keys: df, bf, bf_prior, start, end, date_preset, df_all,
    physician_role. Returns None if data is empty.
    """
    try:
        df = _get_enriched_billing()
    except Exception:
        return None
    if df.empty or "DateOfService" not in df.columns:
        return None

    # Apply A/R lag by shifting DateOfService forward before any filtering.
    # Work on a copy so the underlying cached frame is untouched.
    if ar_lag_days and ar_lag_days > 0:
        df = df.copy()
        df["DateOfService"] = df["DateOfService"] + pd.Timedelta(days=int(ar_lag_days))

    # Date range
    last_date = df["DateOfService"].dt.normalize().max()
    earliest_date = df["DateOfService"].dt.normalize().min()

    if start_date and end_date:
        start = pd.Timestamp(start_date)
        end = pd.Timestamp(end_date)
    else:
        start = _preset_start(last_date, date_preset or "12mo", earliest_date)
        end = last_date

    # Pre-compute per-row payor group for the chosen mode (used in _dim_mask).
    _payor_row_groups = None
    if payor_selected and "PrimaryInsurance" in df.columns:
        try:
            _payor_mapping = get_payor_mapping_dict()
        except Exception:
            _payor_mapping = {}
        _payor_row_groups = _row_payor_groups(
            df["PrimaryInsurance"], payor_mode or "broad", _payor_mapping,
        )

    # Non-date dimension mask builder (closes over df and filter args)
    def _dim_mask(base_mask):
        m = base_mask
        if departments and "Department" in df.columns:
            m = m & df["Department"].isin(departments)
        if _payor_row_groups is not None:
            m = m & _payor_row_groups.isin(payor_selected)
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

    # Role-based column filtering: hide dollar columns from non-partners and
    # the wRVU (professional RVU) column from non-partners as well. Hospital
    # revenue stays visible — user-facing requirement.
    _hide_money = not can_see_money()
    _hide_pro_rvu = not can_see_professional_rvu()
    _gated_fields = set()
    if _hide_money:
        _gated_fields |= {"Pro_Revenue", "Total_Revenue", "Hosp_Revenue"}
    if _hide_pro_rvu:
        _gated_fields.add("wRVU")
    existing_cols = [
        c for c in _BILLING_TABLE_COLS
        if c["field"] in bf.columns and c["field"] not in _gated_fields
    ]
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
# Callback 1 (FAST): KPIs + Sparklines + Dollar Row
#
# Split out from the old monolithic callback so the KPI row paints 1-2s
# before the detail grid / chart stores finish. `_load_and_filter_billing_cached`
# is memoized, so callback 2 hits the cache for the same filter args.
# ---------------------------------------------------------------------------

@callback(
    Output(f"{PAGE_ID}-kpi-row", "children"),
    Output(f"{PAGE_ID}-dollar-row", "children"),
    Output(f"{PAGE_ID}-store-kpi-sparklines", "data"),
    *_BILLING_FILTER_INPUTS,
    Input(f"{PAGE_ID}-store-rev-adj", "data"),
    Input(f"{PAGE_ID}-table-filter-rows", "data"),
)
def _update_billing_kpis(*args):
    """Fast path: KPIs + dollar row + sparklines only. Paints first."""
    filt = _unpack_billing_filter_args(args)
    rev_adj = args[_N_BILLING_FILTER_INPUTS]
    grid_rows = args[_N_BILLING_FILTER_INPUTS + 1]
    data = _load_and_filter_billing_cached(**filt)
    if data is None:
        return [], [], {}

    bf_raw = _apply_revenue_adjustments(data["bf"], rev_adj)
    bf = _apply_grid_row_filter(bf_raw, grid_rows) if grid_rows else bf_raw
    bf_prior = _apply_revenue_adjustments(data["bf_prior"], rev_adj)
    start, end = data["start"], data["end"]
    component = data["component"]
    kpi_children, dollar_children, sparkline_data = _build_billing_kpis(
        bf, bf_prior, start, end, component,
    )
    return kpi_children, dollar_children, sparkline_data


# ---------------------------------------------------------------------------
# Callback 2 (SLOW): store-metrics + detail grid
# ---------------------------------------------------------------------------

@callback(
    Output(f"{PAGE_ID}-store-metrics", "data"),
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
def _update_billing_charts_and_table(*args):
    """Slow path: chart data store + detail grid rows. Paints second."""
    filt = _unpack_billing_filter_args(args)
    rev_adj = args[_N_BILLING_FILTER_INPUTS]
    grid_rows = args[_N_BILLING_FILTER_INPUTS + 1]

    # Single-slot result cache — same filter state firing twice (e.g. two
    # browser tabs land with default filters, or user navigates away and
    # back) hits this and skips ~1s of compute. Key includes rev_adj and
    # grid_rows because the table output depends on both.
    _cache_key = (
        _filter_kwargs_key(filt),
        tuple(sorted(rev_adj.items())) if isinstance(rev_adj, dict) else rev_adj,
        tuple(grid_rows) if isinstance(grid_rows, list) else grid_rows,
    )
    if _charts_table_cache["key"] == _cache_key and _charts_table_cache["result"] is not None:
        return _charts_table_cache["result"]

    data = _load_and_filter_billing_cached(**filt)
    if data is None:
        return None, [], []

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

    # Apply grid row filter for charts
    bf = _apply_grid_row_filter(bf_raw, grid_rows) if grid_rows else bf_raw
    start, end = data["start"], data["end"]
    physician_role = data["physician_role"]
    categories = data["categories"]
    component = data["component"]

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

    # Pick which dollar column / label is in scope for this render.
    if component == "pro":
        dollar_col, dollar_label = "Pro_Revenue", "Professional Revenue ($)"
    elif component == "hospital":
        dollar_col, dollar_label = "Hosp_Revenue", "Hospital Revenue ($)"
    else:
        dollar_col, dollar_label = "Total_Revenue", "Total Revenue ($)"

    # RVU is gated separately (skip for hospital-only and non-partner viewers).
    rvu_active = (component != "hospital") and can_see_professional_rvu()

    # Build the list of (store_label, value_col, y_title) to compute. All
    # active stores are computed from a SHARED multi-column groupby per
    # (group_col, freq) — _build_multi_value_aggregates does it once and
    # _build_census_data reads the pre-pivoted wide frame, so we go from
    # 45 separate groupbys to 15 combined ones (3× faster on the chart path).
    _store_specs = [("volume", "Quantity", "Billing Units")]
    if rvu_active:
        _store_specs.append(("rvu", "wRVU", "wRVU"))
    _store_specs.append(("dollar", dollar_col, dollar_label))

    _value_cols = [vc for _, vc, _ in _store_specs]

    # Group axes that the page may render. (label, group_col, group_names, group_colors)
    _axes = [
        ("category", "Category", active_cat_names, CATEGORY_COLORS),
        ("department", "Department", dept_names, DEPARTMENT_COLORS),
        ("physician", _role_col, phys_names, phys_colors),
    ]
    if subcat_names:
        _axes.append(("subcategory", "Subcategory", subcat_names, subcat_colors))
    if cpt_codes_list:
        _axes.append(("cpt", "_base_code", cpt_codes_list, cpt_colors))

    # store_label → axis_label → freq → census struct
    _stores_acc = {label: {} for label, _, _ in _store_specs}

    for axis_label, group_col, group_names, group_colors in _axes:
        for freq in ("W", "M", "Y"):
            wides = _build_multi_value_aggregates(
                bf, "DateOfService", group_col, _value_cols, freq=freq,
            )
            for store_label, value_col, y_title in _store_specs:
                _stores_acc[store_label].setdefault(axis_label, {})[freq] = (
                    _build_census_data(
                        bf, "DateOfService", start, end,
                        group_col, group_names, group_colors,
                        value_col=value_col, y_title=y_title, freq=freq,
                        _wide=wides.get(value_col),
                    )
                )

    volume_store = _stores_acc["volume"]
    rvu_store = _stores_acc.get("rvu")
    dollar_store = _stores_acc["dollar"]

    metrics_store = {
        "volume": volume_store,
        "rvu": rvu_store,
        "dollar": dollar_store,
    }
    result = (metrics_store, table_rows, table_cols)
    # Only cache when we built the full table (not a grid-filter passthrough
    # where table_rows/cols are dash.no_update) — caching no_update would
    # poison subsequent renders.
    if not triggered_by_grid:
        _charts_table_cache["key"] = _cache_key
        _charts_table_cache["result"] = result
    return result


# ---------------------------------------------------------------------------
# Helper: build KPI cards + dollar row + sparkline data
# ---------------------------------------------------------------------------

def _build_billing_kpis(bf, bf_prior, start, end, component):
    """Extracted from the old monolithic callback so the KPI row can paint
    before the slow store-metrics / detail-table callback finishes."""
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

        cat_df = bf[bf["Category"] == cat]
        spark = _count_spark_raw(cat_df, "DateOfService", start, end, value_col="Quantity")
        spark["color"] = color
        sparkline_data[slug] = spark

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

    group_dollars = bf["Pro_Revenue"].sum() if not bf.empty else 0
    hosp_dollars = bf["Hosp_Revenue"].sum() if not bf.empty else 0
    total_dollars = group_dollars + hosp_dollars

    _money_ok = can_see_money()
    if component == "pro":
        dollar_children = [_dollar_card("Est. Professional Revenue", group_dollars, PRIMARY)] if _money_ok else []
    elif component == "hospital":
        dollar_children = [_dollar_card("Est. Hospital Revenue", hosp_dollars, PRIMARY)]
    else:
        if _money_ok:
            dollar_children = [
                _dollar_card("Est. Professional Revenue", group_dollars, PRIMARY),
                _dollar_card("Est. Hospital Revenue", hosp_dollars),
                _dollar_card("Est. All-In Total", total_dollars, SEMANTIC_COLORS["success"]),
            ]
        else:
            dollar_children = [_dollar_card("Est. Hospital Revenue", hosp_dollars, PRIMARY)]

    return kpi_children, dollar_children, sparkline_data


# ---------------------------------------------------------------------------
# Cumulative Callback (separate for performance — toggles don't recompute KPIs)
# ---------------------------------------------------------------------------

@callback(
    Output(f"{PAGE_ID}-store-metrics-cum", "data"),
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
    rev_adj = args[_N_BILLING_FILTER_INPUTS]  # store-rev-adj data
    _base = _N_BILLING_FILTER_INPUTS + 1
    (volcum_mode, volcum_period_type, volcum_slice,
     rvucum_mode, rvucum_period_type, rvucum_slice,
     dollarcum_mode, dollarcum_period_type,
     dollarcum_slice) = args[_base:_base + 9]

    data = _load_and_filter_billing_cached(**filt)
    if data is None:
        return None

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
    return {"volume": vol_cum, "rvu": rvu_cum, "dollar": dollar_cum}


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
    rev_adj = args[_N_BILLING_FILTER_INPUTS]
    _base = _N_BILLING_FILTER_INPUTS + 1
    payor_mode = args[_base] or "broad"
    count_by = args[_base + 1] or "event"
    trend_sort = args[_base + 2] or "volume"
    compare_sort = args[_base + 3] or "volume"
    period_type = args[_base + 4] or "calendar"
    max_prior = args[_base + 5] if args[_base + 5] is not None else 1
    compare_unit = args[_base + 6] or "count"

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

def _trend_js(chart_id, metric_key):
    return f"""
function(allMetrics, sliceMode, agg, smoothPct, chartType, stackVal) {{
    var storeData = allMetrics ? allMetrics['{metric_key}'] : null;
    return window.dash_clientside.billingDeferred.renderTrend(
        '{chart_id}', storeData, sliceMode, agg, smoothPct, chartType, stackVal
    );
}}
"""

def _cum_js(chart_id, metric_key):
    return f"""
function(allMetrics, smoothPct, chartType, stackVal, maxPrior, projectOn) {{
    var rawData = allMetrics ? allMetrics['{metric_key}'] : null;
    return window.dash_clientside.billingDeferred.renderCum(
        '{chart_id}', rawData, smoothPct, chartType, stackVal, maxPrior, projectOn
    );
}}
"""

# Volume trend
clientside_callback(
    _trend_js(f"{PAGE_ID}-chart-vol-trend", "volume"),
    Output(f"{PAGE_ID}-chart-vol-trend", "figure"),
    Input(f"{PAGE_ID}-store-metrics", "data"),
    Input(f"{PAGE_ID}-vol-slice", "value"),
    Input(f"{PAGE_ID}-vol-agg", "value"),
    Input(f"{PAGE_ID}-vol-settings-smooth", "value"),
    Input(f"{PAGE_ID}-vol-settings-type", "value"),
    Input(f"{PAGE_ID}-vol-settings-stack", "value"),
    prevent_initial_call=True,
)

# RVU trend
clientside_callback(
    _trend_js(f"{PAGE_ID}-chart-rvu-trend", "rvu"),
    Output(f"{PAGE_ID}-chart-rvu-trend", "figure"),
    Input(f"{PAGE_ID}-store-metrics", "data"),
    Input(f"{PAGE_ID}-rvu-slice", "value"),
    Input(f"{PAGE_ID}-rvu-agg", "value"),
    Input(f"{PAGE_ID}-rvu-settings-smooth", "value"),
    Input(f"{PAGE_ID}-rvu-settings-type", "value"),
    Input(f"{PAGE_ID}-rvu-settings-stack", "value"),
    prevent_initial_call=True,
)

# Volume cumulative
clientside_callback(
    _cum_js(f"{PAGE_ID}-chart-vol-cum", "volume"),
    Output(f"{PAGE_ID}-chart-vol-cum", "figure"),
    Input(f"{PAGE_ID}-store-metrics-cum", "data"),
    Input(f"{PAGE_ID}-volcum-settings-smooth", "value"),
    Input(f"{PAGE_ID}-volcum-settings-type", "value"),
    Input(f"{PAGE_ID}-volcum-settings-stack", "value"),
    Input(f"{PAGE_ID}-volcum-settings-prior-periods", "value"),
    Input(f"{PAGE_ID}-volcum-project", "checked"),
    prevent_initial_call=True,
)

# RVU cumulative
clientside_callback(
    _cum_js(f"{PAGE_ID}-chart-rvu-cum", "rvu"),
    Output(f"{PAGE_ID}-chart-rvu-cum", "figure"),
    Input(f"{PAGE_ID}-store-metrics-cum", "data"),
    Input(f"{PAGE_ID}-rvucum-settings-smooth", "value"),
    Input(f"{PAGE_ID}-rvucum-settings-type", "value"),
    Input(f"{PAGE_ID}-rvucum-settings-stack", "value"),
    Input(f"{PAGE_ID}-rvucum-settings-prior-periods", "value"),
    Input(f"{PAGE_ID}-rvucum-project", "checked"),
    prevent_initial_call=True,
)

# Dollar trend
clientside_callback(
    _trend_js(f"{PAGE_ID}-chart-dollar-trend", "dollar"),
    Output(f"{PAGE_ID}-chart-dollar-trend", "figure"),
    Input(f"{PAGE_ID}-store-metrics", "data"),
    Input(f"{PAGE_ID}-dollar-slice", "value"),
    Input(f"{PAGE_ID}-dollar-agg", "value"),
    Input(f"{PAGE_ID}-dollar-settings-smooth", "value"),
    Input(f"{PAGE_ID}-dollar-settings-type", "value"),
    Input(f"{PAGE_ID}-dollar-settings-stack", "value"),
    prevent_initial_call=True,
)

# Dollar cumulative
clientside_callback(
    _cum_js(f"{PAGE_ID}-chart-dollar-cum", "dollar"),
    Output(f"{PAGE_ID}-chart-dollar-cum", "figure"),
    Input(f"{PAGE_ID}-store-metrics-cum", "data"),
    Input(f"{PAGE_ID}-dollarcum-settings-smooth", "value"),
    Input(f"{PAGE_ID}-dollarcum-settings-type", "value"),
    Input(f"{PAGE_ID}-dollarcum-settings-stack", "value"),
    Input(f"{PAGE_ID}-dollarcum-settings-prior-periods", "value"),
    Input(f"{PAGE_ID}-dollarcum-project", "checked"),
    prevent_initial_call=True,
)

# Payor trend ridgeline (reuse diagRidge JS renderer)
clientside_callback(f"""function() {{
        var fig = window.dash_clientside.diagRidge.renderTrend.apply(null, arguments);
        return window.dash_clientside.chartDeferred.wrap("{PAGE_ID}-chart-payor-trend", fig);
    }}""",
    Output(f"{PAGE_ID}-chart-payor-trend", "figure"),
    Input(f"{PAGE_ID}-chart-payor-trend-store", "data"),
    Input(f"{PAGE_ID}-chart-payor-trend-settings-smooth", "value"),
    Input(f"{PAGE_ID}-chart-payor-trend-settings-type", "value"),
    Input(f"{PAGE_ID}-payor-trend-agg", "value"),
    prevent_initial_call=True,
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
# Slice toggle dimming + stack-wrap visibility (consolidated)
# ---------------------------------------------------------------------------

# Single callback replaces 4 per-slider class callbacks: all 4 slice chips
# classed in one pass whenever any of them changes.
clientside_callback(
    """function(vol, volcum, rvu, rvucum) {
        function cls(v) {
            return (v && v !== "total") ? "slice-group-active" : "slice-total-active";
        }
        return [cls(vol), cls(volcum), cls(rvu), cls(rvucum)];
    }""",
    Output(f"{PAGE_ID}-vol-slice", "className"),
    Output(f"{PAGE_ID}-volcum-slice", "className"),
    Output(f"{PAGE_ID}-rvu-slice", "className"),
    Output(f"{PAGE_ID}-rvucum-slice", "className"),
    Input(f"{PAGE_ID}-vol-slice", "value"),
    Input(f"{PAGE_ID}-volcum-slice", "value"),
    Input(f"{PAGE_ID}-rvu-slice", "value"),
    Input(f"{PAGE_ID}-rvucum-slice", "value"),
)

# Single callback replaces 3 non-cumulative stack-wrap visibility callbacks.
clientside_callback(
    """function(volSlice, volType, rvuSlice, rvuType, dollarSlice, dollarType) {
        function hide(sliceVal, chartType) {
            var single = !sliceVal || sliceVal === "total" || sliceVal === "";
            var noStack = chartType === "line";
            return (single || noStack) ? {"display": "none"} : {};
        }
        return [
            hide(volSlice, volType),
            hide(rvuSlice, rvuType),
            hide(dollarSlice, dollarType),
        ];
    }""",
    Output(f"{PAGE_ID}-vol-settings-stack-wrap", "style", allow_duplicate=True),
    Output(f"{PAGE_ID}-rvu-settings-stack-wrap", "style", allow_duplicate=True),
    Output(f"{PAGE_ID}-dollar-settings-stack-wrap", "style", allow_duplicate=True),
    Input(f"{PAGE_ID}-vol-slice", "value"),
    Input(f"{PAGE_ID}-vol-settings-type", "value"),
    Input(f"{PAGE_ID}-rvu-slice", "value"),
    Input(f"{PAGE_ID}-rvu-settings-type", "value"),
    Input(f"{PAGE_ID}-dollar-slice", "value"),
    Input(f"{PAGE_ID}-dollar-settings-type", "value"),
    prevent_initial_call="initial_duplicate",
)

# Single callback replaces 3 cumulative stack-wrap visibility callbacks.
clientside_callback(
    """function(volMode, volSlice, volType, rvuMode, rvuSlice, rvuType, dollarMode, dollarSlice, dollarType) {
        function hide(mode, sliceVal, chartType) {
            var single = !sliceVal || sliceVal === "total" || sliceVal === "";
            if (single) return {"display": "none"};
            var isPrior = mode === "prior";
            var noStack = chartType === "line";
            return (isPrior || noStack) ? {"display": "none"} : {};
        }
        return [
            hide(volMode, volSlice, volType),
            hide(rvuMode, rvuSlice, rvuType),
            hide(dollarMode, dollarSlice, dollarType),
        ];
    }""",
    Output(f"{PAGE_ID}-volcum-settings-stack-wrap", "style"),
    Output(f"{PAGE_ID}-rvucum-settings-stack-wrap", "style"),
    Output(f"{PAGE_ID}-dollarcum-settings-stack-wrap", "style"),
    Input(f"{PAGE_ID}-volcum-mode", "value"),
    Input(f"{PAGE_ID}-volcum-slice", "value"),
    Input(f"{PAGE_ID}-volcum-settings-type", "value"),
    Input(f"{PAGE_ID}-rvucum-mode", "value"),
    Input(f"{PAGE_ID}-rvucum-slice", "value"),
    Input(f"{PAGE_ID}-rvucum-settings-type", "value"),
    Input(f"{PAGE_ID}-dollarcum-mode", "value"),
    Input(f"{PAGE_ID}-dollarcum-slice", "value"),
    Input(f"{PAGE_ID}-dollarcum-settings-type", "value"),
)


# ---------------------------------------------------------------------------
# Clientside: KPI Sparklines
# ---------------------------------------------------------------------------

_SPARKLINE_IDS = [f"{PAGE_ID}-spark-{slug}" for slug in CATEGORY_SLUGS.values()]

# One callback per sparkline — multi-output batch fails when Dash tries to
# fire against sparkline targets that weren't rendered (empty categories).
# The per-target form tolerates missing targets under
# suppress_callback_exceptions=True.
for _spark_id in _SPARKLINE_IDS:
    clientside_callback(f"""function() {{
        var fig = window.dash_clientside.sparklines.updateFromStore.apply(null, arguments);
        return window.dash_clientside.chartDeferred.wrap("{_spark_id}", fig);
    }}""",
        Output(_spark_id, "figure"),
        Input(f"{PAGE_ID}-store-kpi-sparklines", "data"),
        Input(_spark_id, "id"),
        Input(f"{PAGE_ID}-smooth-slider", "value"),
        prevent_initial_call=True,
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
# Single callback replaces 3 per-chart cum-vis callbacks.
clientside_callback(
    """function(volMode, rvuMode, dollarMode, volSlice, rvuSlice, dollarSlice) {
        function vis(mode, sliceVal) {
            if (mode === "prior") {
                return [{}, {"display": "none"}, "total"];
            }
            var newSlice = (!sliceVal || sliceVal === "total") ? "category" : window.dash_clientside.no_update;
            return [{"display": "none"}, {}, newSlice];
        }
        var v = vis(volMode, volSlice);
        var r = vis(rvuMode, rvuSlice);
        var d = vis(dollarMode, dollarSlice);
        return [v[0], v[1], v[2], r[0], r[1], r[2], d[0], d[1], d[2]];
    }""",
    Output(f"{PAGE_ID}-volcum-period-type", "style"),
    Output(f"{PAGE_ID}-volcum-slice", "style"),
    Output(f"{PAGE_ID}-volcum-slice", "value", allow_duplicate=True),
    Output(f"{PAGE_ID}-rvucum-period-type", "style"),
    Output(f"{PAGE_ID}-rvucum-slice", "style"),
    Output(f"{PAGE_ID}-rvucum-slice", "value", allow_duplicate=True),
    Output(f"{PAGE_ID}-dollarcum-period-type", "style"),
    Output(f"{PAGE_ID}-dollarcum-slice", "style"),
    Output(f"{PAGE_ID}-dollarcum-slice", "value", allow_duplicate=True),
    Input(f"{PAGE_ID}-volcum-mode", "value"),
    Input(f"{PAGE_ID}-rvucum-mode", "value"),
    Input(f"{PAGE_ID}-dollarcum-mode", "value"),
    State(f"{PAGE_ID}-volcum-slice", "value"),
    State(f"{PAGE_ID}-rvucum-slice", "value"),
    State(f"{PAGE_ID}-dollarcum-slice", "value"),
    prevent_initial_call="initial_duplicate",
)

# Disable Calendar when period > 1 year; cap prior-periods slider to
# available data. Single callback replaces 3 per-chart prior-controls
# callbacks and now reads from the unified cum store. The three metric
# blocks are always refreshed together because the unified store writes
# them together — preserving prior behavior where each chart's max/marks
# updated alongside its own store change.
clientside_callback(
    """function(cumStore, volPt, rvuPt, dollarPt) {
        var upd = window.dash_clientside.cumulative.updatePriorControls;
        var nu = window.dash_clientside.no_update;
        function pack(metric, pt) {
            if (!metric) return [nu, nu, nu, nu];
            return upd(metric, pt);
        }
        var v = pack(cumStore && cumStore.volume, volPt);
        var r = pack(cumStore && cumStore.rvu, rvuPt);
        var d = pack(cumStore && cumStore.dollar, dollarPt);
        return [
            v[0], v[1], v[2], v[3],
            r[0], r[1], r[2], r[3],
            d[0], d[1], d[2], d[3],
        ];
    }""",
    Output(f"{PAGE_ID}-volcum-period-type", "data"),
    Output(f"{PAGE_ID}-volcum-period-type", "value", allow_duplicate=True),
    Output(f"{PAGE_ID}-volcum-settings-prior-periods", "max"),
    Output(f"{PAGE_ID}-volcum-settings-prior-periods", "marks"),
    Output(f"{PAGE_ID}-rvucum-period-type", "data"),
    Output(f"{PAGE_ID}-rvucum-period-type", "value", allow_duplicate=True),
    Output(f"{PAGE_ID}-rvucum-settings-prior-periods", "max"),
    Output(f"{PAGE_ID}-rvucum-settings-prior-periods", "marks"),
    Output(f"{PAGE_ID}-dollarcum-period-type", "data"),
    Output(f"{PAGE_ID}-dollarcum-period-type", "value", allow_duplicate=True),
    Output(f"{PAGE_ID}-dollarcum-settings-prior-periods", "max"),
    Output(f"{PAGE_ID}-dollarcum-settings-prior-periods", "marks"),
    Input(f"{PAGE_ID}-store-metrics-cum", "data"),
    State(f"{PAGE_ID}-volcum-period-type", "value"),
    State(f"{PAGE_ID}-rvucum-period-type", "value"),
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

_CPT_SLICE_BATCH_JS = f"""
function(cats, volCur, rvuCur, dollarCur, volcumCur, rvucumCur, dollarcumCur) {{
    var nc = {_CPT_SLICE_VIS_JS};
    var cm = {_CPT_SLICE_VIS_CUM_JS};
    var r1 = nc(cats, volCur);
    var r2 = nc(cats, rvuCur);
    var r3 = nc(cats, dollarCur);
    var r4 = cm(cats, volcumCur);
    var r5 = cm(cats, rvucumCur);
    var r6 = cm(cats, dollarcumCur);
    return [
        r1[0], r1[1], r2[0], r2[1], r3[0], r3[1],
        r4[0], r4[1], r5[0], r5[1], r6[0], r6[1],
    ];
}}
"""

clientside_callback(
    _CPT_SLICE_BATCH_JS,
    Output(f"{PAGE_ID}-vol-slice", "data"),
    Output(f"{PAGE_ID}-vol-slice", "value"),
    Output(f"{PAGE_ID}-rvu-slice", "data"),
    Output(f"{PAGE_ID}-rvu-slice", "value"),
    Output(f"{PAGE_ID}-dollar-slice", "data"),
    Output(f"{PAGE_ID}-dollar-slice", "value"),
    Output(f"{PAGE_ID}-volcum-slice", "data"),
    Output(f"{PAGE_ID}-volcum-slice", "value", allow_duplicate=True),
    Output(f"{PAGE_ID}-rvucum-slice", "data"),
    Output(f"{PAGE_ID}-rvucum-slice", "value", allow_duplicate=True),
    Output(f"{PAGE_ID}-dollarcum-slice", "data"),
    Output(f"{PAGE_ID}-dollarcum-slice", "value", allow_duplicate=True),
    Input(f"{PAGE_ID}-cpt-store", "data"),
    State(f"{PAGE_ID}-vol-slice", "value"),
    State(f"{PAGE_ID}-rvu-slice", "value"),
    State(f"{PAGE_ID}-dollar-slice", "value"),
    State(f"{PAGE_ID}-volcum-slice", "value"),
    State(f"{PAGE_ID}-rvucum-slice", "value"),
    State(f"{PAGE_ID}-dollarcum-slice", "value"),
    prevent_initial_call="initial_duplicate",
)


# ---------------------------------------------------------------------------
# Chip Dropdown: Physician (trigger label, clear, dynamic population)
# ---------------------------------------------------------------------------

# Trigger label
# Trigger label + clear-button visibility in one pass (shared input).
clientside_callback(
    """function(val) {
        var lbl = !val ? "Physician" : val.split(", ")[0];
        var sty = val ? {"display": "inline-flex"} : {"display": "none"};
        return [lbl, sty];
    }""",
    Output(f"{PAGE_ID}-physician-trigger", "children"),
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
# Payor filter: populate chips based on mode (actual/broad/phdsc)
# ---------------------------------------------------------------------------
@callback(
    Output(f"{PAGE_ID}-filter-payor", "children"),
    Output(f"{PAGE_ID}-filter-payor", "value"),
    Input(f"{PAGE_ID}-filter-payor-mode", "value"),
)
def _populate_payor_chips(mode):
    mode = mode or "broad"
    try:
        mapping = get_payor_mapping_dict()
    except Exception:
        mapping = {}

    if mode == "broad":
        options = list(_BROAD_CATEGORIES)
    elif mode == "phdsc":
        options = list(_PHDSC_CATEGORIES)
    else:
        # actual — standardized payor names observed in the data, by frequency
        try:
            bdf = _get_enriched_billing()
        except Exception:
            bdf = pd.DataFrame()
        if bdf.empty or "PrimaryInsurance" not in bdf.columns:
            options = []
        else:
            groups = _row_payor_groups(bdf["PrimaryInsurance"], "actual", mapping)
            options = groups.value_counts().index.tolist()

    chips = [dmc.Chip(opt, value=opt, size="xs", variant="filled") for opt in options]
    return chips, []


# Trigger label + clear-button visibility
clientside_callback(
    """function(vals) {
        var n = (vals && vals.length) || 0;
        var lbl = n > 0 ? "Payor (" + n + ")" : "Payor";
        var sty = n > 0 ? {"display": "inline-flex"} : {"display": "none"};
        return [lbl, sty];
    }""",
    Output(f"{PAGE_ID}-payor-filter-trigger", "children"),
    Output(f"{PAGE_ID}-payor-filter-clear", "style"),
    Input(f"{PAGE_ID}-filter-payor", "value"),
)

# Clear button action
clientside_callback(
    """function(n) { return []; }""",
    Output(f"{PAGE_ID}-filter-payor", "value", allow_duplicate=True),
    Input(f"{PAGE_ID}-payor-filter-clear", "n_clicks"),
    prevent_initial_call=True,
)


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

# Trigger label + clear-button visibility in one pass (shared 8 inputs).
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
        var lbl = active > 0 ? "Status (" + active + ")" : "Status";
        var sty = active > 0 ? {"display": "inline-flex"} : {"display": "none"};
        return [lbl, sty];
    }""",
    Output(f"{PAGE_ID}-status-trigger", "children"),
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


# On click: reveal the overlay (CSS class swap) and arm the delay interval.
clientside_callback(
    """function(n) {
        if (!n) return [window.dash_clientside.no_update,
                         window.dash_clientside.no_update,
                         window.dash_clientside.no_update];
        console.log('[IRM] overlay shown @', performance.now().toFixed(0), 'ms');
        return ['heavy-modal-overlay', 0, false];
    }""",
    Output(f"{PAGE_ID}-irm-overlay", "className"),
    Output(f"{PAGE_ID}-irm-delay", "n_intervals"),
    Output(f"{PAGE_ID}-irm-delay", "disabled"),
    Input(f"{PAGE_ID}-irm-btn", "n_clicks"),
    prevent_initial_call=True,
)


# Interval fires ~60ms later (after the browser has painted the overlay).
# Open the real DMC Modal. Its React render will block the main thread for a
# few seconds; the overlay stays visible throughout because the hide-overlay
# callback below only runs after the modal paint commits.
clientside_callback(
    """function(n) {
        if (!n) return [window.dash_clientside.no_update,
                         window.dash_clientside.no_update];
        console.log('[IRM] real modal open @', performance.now().toFixed(0), 'ms');
        return [true, true];
    }""",
    Output(f"{PAGE_ID}-irm-modal", "opened"),
    Output(f"{PAGE_ID}-irm-delay", "disabled", allow_duplicate=True),
    Input(f"{PAGE_ID}-irm-delay", "n_intervals"),
    prevent_initial_call=True,
)


# Hide the overlay after the real modal has finished rendering. We defer
# via rAF + a small timeout so the overlay paints over the modal's layout
# work instead of disappearing the instant state flips.
clientside_callback(
    """function(opened) {
        if (!opened) return window.dash_clientside.no_update;
        requestAnimationFrame(function() {
            setTimeout(function() {
                var el = document.getElementById('billing-irm-overlay');
                if (el) el.className = 'heavy-modal-overlay hidden';
                console.log('[IRM] overlay hidden @', performance.now().toFixed(0), 'ms');
            }, 50);
        });
        return window.dash_clientside.no_update;
    }""",
    Output(f"{PAGE_ID}-irm-overlay", "className", allow_duplicate=True),
    Input(f"{PAGE_ID}-irm-modal", "opened"),
    prevent_initial_call=True,
)


# Populate modal contents.  Listens on the button n_clicks directly (NOT on
# modal.opened) so the clientside open-callback has no server dependency
# downstream — Dash applies the clientside "opened=True" instantly without
# waiting for this server work to complete.
@callback(
    Output(f"{PAGE_ID}-irm-grid", "rowData"),
    Output(f"{PAGE_ID}-irm-count", "children"),
    Input(f"{PAGE_ID}-irm-btn", "n_clicks"),
    prevent_initial_call=True,
)
def _irm_open(n):
    import time as _t
    _t0 = _t.time()
    print(f"[IRM] _irm_open START n={n}", flush=True)
    if not n:
        return (dash.no_update,) * 2
    if not can_see_manager_modals():
        return (dash.no_update,) * 2
    rows = get_all_insurance_rates()
    for r in rows:
        r["_delete"] = "\u2716"
    print(f"[IRM] _irm_open DONE in {(_t.time()-_t0)*1000:.0f}ms", flush=True)
    return rows, f"{len(rows)} payors"


# ---------------------------------------------------------------------------
# Role-gate: hide the IRM button and the "Professional" codetype option
# from users who shouldn't see them. Fires once on page mount.
# ---------------------------------------------------------------------------
@callback(
    Output(f"{PAGE_ID}-irm-btn", "style"),
    Output(f"{PAGE_ID}-filter-codetype", "data"),
    Output(f"{PAGE_ID}-filter-codetype", "value"),
    Input(f"{PAGE_ID}-irm-btn", "id"),  # dummy, fires once on mount
    State(f"{PAGE_ID}-filter-codetype", "value"),
)
def _role_gate(_id, current_code):
    admin = can_see_manager_modals()
    partner = can_see_professional_rvu()

    btn_style = dash.no_update if admin else {"display": "none"}

    data = [{"value": "all", "label": "All"}]
    if partner:
        data.append({"value": "pro", "label": "Professional"})
    data.append({"value": "hospital", "label": "Hospital"})

    # If a non-partner had "pro" selected (defensive), fall back to "all".
    new_value = dash.no_update
    if current_code == "pro" and not partner:
        new_value = "all"

    return btn_style, data, new_value


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
    Input(f"{PAGE_ID}-irm-btn", "n_clicks"),
    State(f"{PAGE_ID}-pm-filter", "value"),
    prevent_initial_call=True,
)
def _pm_load(tab, n_clicks, active_filter):
    """Load payor mapping grid when tab is selected or button clicked."""
    import time as _t
    _t0 = _t.time()
    print(f"[IRM] _pm_load START tab={tab} n={n_clicks}", flush=True)
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
            "ai_explanation": m.get("ai_explanation", ""),
        })

    # Sort by event_count desc by default
    rows.sort(key=lambda r: r["event_count"], reverse=True)

    # Get canonical payors for the editor dropdown — mirror the Payor Entities
    # tab (names actually referenced by at least one mapping) so the dropdown
    # stays in sync when entities are renamed/deleted.
    canonical = sorted({e["name"] for e in get_standardized_payor_counts() if e.get("name")})

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
        {"field": "ai_explanation", "headerName": "AI Note",
         "editable": False, "flex": 1, "minWidth": 200,
         "tooltipField": "ai_explanation",
         "cellStyle": {"fontSize": "11px", "color": "#6B7280",
                       "fontStyle": "italic", "lineHeight": "1.3"},
         "filter": "agTextColumnFilter", "floatingFilter": True},
    ]

    mapped = sum(1 for r in rows if r["standardized_payor"])
    count_text = f"{mapped} mapped / {len(rows)} total"
    print(f"[IRM] _pm_load DONE in {(_t.time()-_t0)*1000:.0f}ms", flush=True)
    # Respect the active filter toggle so that switching tabs / reopening the
    # modal doesn't silently reset the view to "all".
    visible = _apply_pm_filter(rows, active_filter)
    return visible, col_defs, count_text, rows


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
    Input(f"{PAGE_ID}-irm-btn", "n_clicks"),
    prevent_initial_call=True,
)
def _pe_load(tab, n_clicks):
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
    Output(f"{PAGE_ID}-rev-adj-ar-lag", "value", allow_duplicate=True),
    *[Output(f"{PAGE_ID}-rev-adj-mult-{cat}", "value") for cat in _BROAD_CATEGORIES],
    Input(f"{PAGE_ID}-irm-tabs", "value"),
    Input(f"{PAGE_ID}-irm-btn", "n_clicks"),
    prevent_initial_call=True,
)
def _rev_adj_load(tab, n_clicks):
    """Load saved revenue adjustment settings when tab is selected."""
    if tab != "rev_adj" and not n_clicks:
        raise dash.exceptions.PreventUpdate
    s = get_revenue_adj_settings()
    return (
        bool(s.get("enabled", 0)),
        s.get("realization", 90),
        s.get("ar_lag", 30),
        *[s.get(f"mult_{cat}", 100) for cat in _BROAD_CATEGORIES],
    )


@callback(
    Output(f"{PAGE_ID}-rev-adj-status", "children"),
    Output(f"{PAGE_ID}-store-rev-adj", "data"),
    Input(f"{PAGE_ID}-rev-adj-save", "n_clicks"),
    State(f"{PAGE_ID}-rev-adj-enabled", "checked"),
    State(f"{PAGE_ID}-rev-adj-realization", "value"),
    State(f"{PAGE_ID}-rev-adj-ar-lag", "value"),
    *[State(f"{PAGE_ID}-rev-adj-mult-{cat}", "value") for cat in _BROAD_CATEGORIES],
    prevent_initial_call=True,
)
def _rev_adj_save(n, enabled, realization, ar_lag, *mult_values):
    """Save revenue adjustment settings to DB and push to store.

    Note: `ar_lag_enabled` is toggled from the page filter bar (not here),
    so we preserve whatever's currently saved for that flag.
    """
    if not n:
        raise dash.exceptions.PreventUpdate
    prior = get_revenue_adj_settings()
    settings = {
        "enabled": 1.0 if enabled else 0.0,
        "realization": float(realization or 90),
        "ar_lag": float(ar_lag if ar_lag is not None else 30),
        "ar_lag_enabled": float(prior.get("ar_lag_enabled", 0)),
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
        prevent_initial_call=True,
    )

clientside_callback(
    "function(v) { return (v != null ? v : 90) + '%'; }",
    Output(f"{PAGE_ID}-rev-adj-realization-val", "children"),
    Input(f"{PAGE_ID}-rev-adj-realization", "value"),
    prevent_initial_call=True,
)

clientside_callback(
    "function(v) { return (v != null ? v : 0) + 'd'; }",
    Output(f"{PAGE_ID}-rev-adj-ar-lag-val", "children"),
    Input(f"{PAGE_ID}-rev-adj-ar-lag", "value"),
    prevent_initial_call=True,
)


# ---------------------------------------------------------------------------
# Revenue Adjustments — estimated vs actual plot
# ---------------------------------------------------------------------------

def _rev_adj_data_bounds():
    """Return (min_date, max_date) intersection of billing and QBO data."""
    from data.qbo_revenue import get_actual_data_bounds
    try:
        df = _get_enriched_billing()
        if df.empty or "DateOfService" not in df.columns:
            return None
        b_min = df["DateOfService"].dt.normalize().min()
        b_max = df["DateOfService"].dt.normalize().max()
    except Exception:
        return None
    qbo_bounds = get_actual_data_bounds()
    if qbo_bounds is None:
        return b_min, b_max
    q_min, q_max = qbo_bounds
    lo = max(pd.Timestamp(b_min), pd.Timestamp(q_min))
    hi = min(pd.Timestamp(b_max), pd.Timestamp(q_max))
    if lo > hi:
        return None
    return lo, hi


@callback(
    Output(f"{PAGE_ID}-rev-adj-daterange", "min_date_allowed"),
    Output(f"{PAGE_ID}-rev-adj-daterange", "max_date_allowed"),
    Output(f"{PAGE_ID}-rev-adj-daterange", "start_date"),
    Output(f"{PAGE_ID}-rev-adj-daterange", "end_date"),
    Output(f"{PAGE_ID}-store-rev-adj-preset-dates", "data"),
    Input(f"{PAGE_ID}-irm-tabs", "value"),
    Input(f"{PAGE_ID}-rev-adj-date-preset", "value"),
    State(f"{PAGE_ID}-rev-adj-daterange", "start_date"),
    State(f"{PAGE_ID}-rev-adj-daterange", "end_date"),
    prevent_initial_call=False,
)
def _rev_adj_daterange_from_preset(tab, preset, cur_start, cur_end):
    if tab != "rev_adj":
        raise dash.exceptions.PreventUpdate
    bounds = _rev_adj_data_bounds()
    if bounds is None:
        today = pd.Timestamp.today().normalize()
        bounds = (today - pd.Timedelta(days=365), today)
    lo, hi = bounds
    lo_s = lo.date().isoformat()
    hi_s = hi.date().isoformat()

    if preset == "custom":
        start_s = cur_start or lo_s
        end_s = cur_end or hi_s
        return lo_s, hi_s, start_s, end_s, {"start": start_s, "end": end_s}

    if preset == "ytd":
        start = pd.Timestamp(hi.year, 1, 1)
        end = hi
    elif preset == "last_year":
        last_yr = hi.year - 1
        start = pd.Timestamp(last_yr, 1, 1)
        end = pd.Timestamp(last_yr, 12, 31)
    elif preset == "12mo":
        start = hi - pd.DateOffset(months=12)
        end = hi
    elif preset == "24mo":
        start = hi - pd.DateOffset(months=24)
        end = hi
    elif preset == "5yr":
        start = hi - pd.DateOffset(years=5)
        end = hi
    else:  # "all"
        start = lo
        end = hi
    start = max(start, lo)
    end = min(end, hi)
    start_s = start.date().isoformat()
    end_s = end.date().isoformat()
    return lo_s, hi_s, start_s, end_s, {"start": start_s, "end": end_s}


# When the user manually edits the picker (values diverge from the last
# preset-applied pair), flip the preset selector to "custom".
clientside_callback(
    """
    function(start, end, applied, preset) {
        if (preset === 'custom') return window.dash_clientside.no_update;
        if (!applied) return window.dash_clientside.no_update;
        if (start === applied.start && end === applied.end) {
            return window.dash_clientside.no_update;
        }
        return 'custom';
    }
    """,
    Output(f"{PAGE_ID}-rev-adj-date-preset", "value", allow_duplicate=True),
    Input(f"{PAGE_ID}-rev-adj-daterange", "start_date"),
    Input(f"{PAGE_ID}-rev-adj-daterange", "end_date"),
    State(f"{PAGE_ID}-store-rev-adj-preset-dates", "data"),
    State(f"{PAGE_ID}-rev-adj-date-preset", "value"),
    prevent_initial_call=True,
)


# Maximum A/R lag supported. Server pulls this many days of billings
# to the left of start_date so clientside can apply any lag 0..MAX.
_REV_ADJ_MAX_LAG = 90


@callback(
    Output(f"{PAGE_ID}-store-rev-adj-plot", "data"),
    Input(f"{PAGE_ID}-rev-adj-daterange", "start_date"),
    Input(f"{PAGE_ID}-rev-adj-daterange", "end_date"),
    Input(f"{PAGE_ID}-irm-tabs", "value"),
)
def _rev_adj_build_plot_data(start_date, end_date, tab):
    """Build daily billing data split by broad payer category, with a 90-day
    left buffer so clientside can apply any A/R lag.

    This callback only re-runs when the date range or tab changes.
    Realization, smoothing, A/R lag, the enable toggle, and category
    multipliers are all applied clientside for instant dragging.
    """
    if tab != "rev_adj":
        raise dash.exceptions.PreventUpdate
    if not start_date or not end_date:
        return {"est": None, "act": None, "error": "no_range"}

    start = pd.Timestamp(start_date).normalize()
    end = pd.Timestamp(end_date).normalize()
    if end < start:
        return {"est": None, "act": None, "error": "invalid_range"}

    src_start = start - pd.Timedelta(days=_REV_ADJ_MAX_LAG)
    src_end = end  # lag=0 needs DOS up through `end`

    # ---- Estimated: daily Pro_Revenue split by broad_category ----
    try:
        bdf = _get_enriched_billing()
    except Exception:
        bdf = pd.DataFrame()

    est_payload = None
    if not bdf.empty and "DateOfService" in bdf.columns and "Pro_Revenue" in bdf.columns:
        bdf = bdf[(bdf["DateOfService"] >= src_start) & (bdf["DateOfService"] <= src_end)].copy()
        if not bdf.empty:
            try:
                mapping = get_payor_mapping_dict()
            except Exception:
                mapping = {}

            def _resolve(name):
                if name in mapping and mapping[name].get("broad_category"):
                    return mapping[name]["broad_category"]
                return _broad_payor(name)

            if "PrimaryInsurance" in bdf.columns:
                bdf["_bcat"] = bdf["PrimaryInsurance"].apply(_resolve).fillna("Other/Unknown")
            else:
                bdf["_bcat"] = "Other/Unknown"

            bdf["_d"] = bdf["DateOfService"].dt.normalize()
            pivot = bdf.pivot_table(
                index="_d", columns="_bcat", values="Pro_Revenue",
                aggfunc="sum", fill_value=0.0,
            )
            full_idx = pd.date_range(src_start, src_end, freq="D")
            pivot = pivot.reindex(full_idx, fill_value=0.0)

            by_cat = {}
            for cat in _BROAD_CATEGORIES:
                if cat in pivot.columns:
                    by_cat[cat] = [round(v, 2) for v in pivot[cat].tolist()]
                else:
                    by_cat[cat] = [0.0] * len(full_idx)

            est_payload = {
                "dates": [d.strftime("%Y-%m-%d") for d in full_idx],
                "by_category": by_cat,
                "start": start.date().isoformat(),
                "end": end.date().isoformat(),
                "max_lag": _REV_ADJ_MAX_LAG,
            }

    # ---- Actual trace (QBO, independent of billing settings) ----
    from data.qbo_revenue import get_actual_revenue_range
    try:
        act_daily = get_actual_revenue_range(start, end)
    except Exception:
        act_daily = pd.DataFrame(columns=["date", "daily_income"])

    act_payload = None
    if not act_daily.empty:
        act_daily = act_daily.sort_values("date").reset_index(drop=True)
        act_payload = {
            "dates": act_daily["date"].dt.strftime("%Y-%m-%d").tolist(),
            "daily": [round(v, 2) for v in act_daily["daily_income"].tolist()],
        }

    return {"est": est_payload, "act": act_payload}


# Shared compute helper is registered as window._revAdjCompute by
# assets/rev_adj_compute.js (auto-loaded by Dash on page render).


# Store-driven full rebuild: fires when date range / tab changes.
# Slider drags use a separate debounced path (see next callback) so they
# stay buttery-smooth.
clientside_callback(
    r"""
    function(store, realization, smooth, ar_lag, enabled,
             m_medicare, m_medicaid, m_private, m_military,
             m_workers, m_tribal, m_self, m_other) {
        if (!store) return window.dash_clientside.no_update;
        var emptyLayout = function(msg) {
            return {data: [], layout: {
                xaxis: {visible: false}, yaxis: {visible: false},
                margin: {l:0, r:0, t:0, b:0},
                annotations: [{
                    text: msg, xref:"paper", yref:"paper",
                    x:0.5, y:0.5, showarrow:false,
                    font:{size:14, color:"#9CA3AF"}
                }]
            }};
        };
        if (store.error) {
            return emptyLayout(store.error === "no_range"
                ? "Select a date range" : "Invalid date range");
        }
        if (!window._revAdjCompute) return window.dash_clientside.no_update;
        var mults = {
            "Medicare": m_medicare, "Medicaid": m_medicaid,
            "Private": m_private, "Military/VA": m_military,
            "Workers Comp": m_workers, "Tribal/IHS": m_tribal,
            "Self Pay": m_self, "Other/Unknown": m_other,
        };
        var c = window._revAdjCompute(store, realization, smooth, ar_lag, enabled, mults);
        if (!c) return emptyLayout("No revenue data for selected range");
        var traces = [];
        if (c.est_x.length) traces.push({
            x: c.est_x, y: c.est_y, mode:"lines", name:"Estimated (Pro)",
            line:{color:"#7C2A83", width:2.5}, type:"scattergl",
            hovertemplate:"%{x|%b %d, %Y}<br>Est: $%{y:,.0f}<extra></extra>",
        });
        if (c.act_x.length) traces.push({
            x: c.act_x, y: c.act_y, mode:"lines", name:"Actual (QBO)",
            line:{color:"#4CAF50", width:2.5}, type:"scattergl",
            hovertemplate:"%{x|%b %d, %Y}<br>Actual: $%{y:,.0f}<extra></extra>",
        });
        if (!traces.length) return emptyLayout("No revenue data for selected range");
        return {
            data: traces,
            layout: {
                margin: {l:60, r:10, t:30, b:40},
                hovermode: "x unified",
                legend: {orientation:"h", yanchor:"bottom", y:1.02, xanchor:"left", x:0},
                xaxis: {showgrid:false},
                yaxis: {title:"Cumulative $", tickformat:"$,.0f",
                        gridcolor:"rgba(0,0,0,0.08)"},
                plot_bgcolor:"rgba(0,0,0,0)", paper_bgcolor:"rgba(0,0,0,0)",
                font: {family:"Inter, system-ui, sans-serif"},
                uirevision: "rev-adj",
                transition: {duration: 0, easing: "linear"},
            }
        };
    }
    """,
    Output(f"{PAGE_ID}-rev-adj-plot", "figure"),
    Input(f"{PAGE_ID}-store-rev-adj-plot", "data"),
    State(f"{PAGE_ID}-rev-adj-realization", "value"),
    State(f"{PAGE_ID}-rev-adj-smooth", "value"),
    State(f"{PAGE_ID}-rev-adj-ar-lag", "value"),
    State(f"{PAGE_ID}-rev-adj-enabled", "checked"),
    *[State(f"{PAGE_ID}-rev-adj-mult-{cat}", "value") for cat in _BROAD_CATEGORIES],
    prevent_initial_call=True,
)


# Debounced slider path: returns no_update (never touches the figure
# prop) but schedules a Plotly.react on the plot DOM element ~140 ms
# after the last slider change. Lets users drag freely without the plot
# redrawing on every tick.
clientside_callback(
    r"""
    function(realization, smooth, ar_lag, enabled,
             m_medicare, m_medicaid, m_private, m_military,
             m_workers, m_tribal, m_self, m_other, store) {
        if (!store || store.error) return window.dash_clientside.no_update;
        if (!window._revAdjCompute || !window.Plotly) {
            return window.dash_clientside.no_update;
        }
        var args = {
            store: store, realization: realization, smooth: smooth,
            ar_lag: ar_lag, enabled: enabled,
            mults: {
                "Medicare": m_medicare, "Medicaid": m_medicaid,
                "Private": m_private, "Military/VA": m_military,
                "Workers Comp": m_workers, "Tribal/IHS": m_tribal,
                "Self Pay": m_self, "Other/Unknown": m_other,
            }
        };
        if (window._revAdjUpdateTimer) clearTimeout(window._revAdjUpdateTimer);
        window._revAdjUpdateTimer = setTimeout(function() {
            var a = args;
            var c = window._revAdjCompute(
                a.store, a.realization, a.smooth, a.ar_lag, a.enabled, a.mults
            );
            if (!c) return;
            var wrap = document.getElementById('billing-rev-adj-plot');
            if (!wrap) return;
            var el = wrap.classList && wrap.classList.contains('js-plotly-plot')
                ? wrap
                : wrap.querySelector('.js-plotly-plot');
            if (!el || !el.data) return;
            var newData = el.data.map(function(tr) {
                var nm = tr.name || '';
                if (nm.indexOf('Estimated') === 0) {
                    return Object.assign({}, tr, {x: c.est_x, y: c.est_y});
                }
                if (nm.indexOf('Actual') === 0) {
                    return Object.assign({}, tr, {x: c.act_x, y: c.act_y});
                }
                return tr;
            });
            try {
                window.Plotly.react(el, newData, el.layout || {}, el.config || {});
            } catch (e) { console.warn('[rev-adj] Plotly.react failed', e); }
        }, 140);
        return window.dash_clientside.no_update;
    }
    """,
    Output(f"{PAGE_ID}-rev-adj-restyle-sink", "data"),
    Input(f"{PAGE_ID}-rev-adj-realization", "value"),
    Input(f"{PAGE_ID}-rev-adj-smooth", "value"),
    Input(f"{PAGE_ID}-rev-adj-ar-lag", "value"),
    Input(f"{PAGE_ID}-rev-adj-enabled", "checked"),
    *[Input(f"{PAGE_ID}-rev-adj-mult-{cat}", "value") for cat in _BROAD_CATEGORIES],
    State(f"{PAGE_ID}-store-rev-adj-plot", "data"),
    prevent_initial_call=True,
)


clientside_callback(
    "function(v) { return (v != null ? v : 0) + 'd'; }",
    Output(f"{PAGE_ID}-rev-adj-smooth-val", "children"),
    Input(f"{PAGE_ID}-rev-adj-smooth", "value"),
    prevent_initial_call=True,
)


# Mirror relevant state to window._revAdjCache so the native rAF loop in
# assets/rev_adj_live.js can read them during a drag without going
# through Dash. Fires on any of its inputs changing.
clientside_callback(
    r"""
    function(store, realization, smooth, ar_lag, enabled,
             m_medicare, m_medicaid, m_private, m_military,
             m_workers, m_tribal, m_self, m_other) {
        window._revAdjCache = {
            store: store,
            realization: realization,
            smooth: smooth,
            ar_lag: ar_lag,
            enabled: enabled,
            mults: {
                "Medicare": m_medicare, "Medicaid": m_medicaid,
                "Private": m_private, "Military/VA": m_military,
                "Workers Comp": m_workers, "Tribal/IHS": m_tribal,
                "Self Pay": m_self, "Other/Unknown": m_other,
            }
        };
        return window.dash_clientside.no_update;
    }
    """,
    Output(f"{PAGE_ID}-rev-adj-restyle-sink", "data", allow_duplicate=True),
    Input(f"{PAGE_ID}-store-rev-adj-plot", "data"),
    Input(f"{PAGE_ID}-rev-adj-realization", "value"),
    Input(f"{PAGE_ID}-rev-adj-smooth", "value"),
    Input(f"{PAGE_ID}-rev-adj-ar-lag", "value"),
    Input(f"{PAGE_ID}-rev-adj-enabled", "checked"),
    *[Input(f"{PAGE_ID}-rev-adj-mult-{cat}", "value") for cat in _BROAD_CATEGORIES],
    prevent_initial_call="initial_duplicate",
)


# Reset category multipliers to their saved defaults (preserves the
# enable toggle — user asked to leave that alone).
clientside_callback(
    f"""
    function(n) {{
        if (!n) return Array(8).fill(window.dash_clientside.no_update);
        return [
            {_REVENUE_ADJ_DEFAULTS.get("mult_Medicare", 100)},
            {_REVENUE_ADJ_DEFAULTS.get("mult_Medicaid", 90)},
            {_REVENUE_ADJ_DEFAULTS.get("mult_Private", 130)},
            {_REVENUE_ADJ_DEFAULTS.get("mult_Military/VA", 100)},
            {_REVENUE_ADJ_DEFAULTS.get("mult_Workers Comp", 125)},
            {_REVENUE_ADJ_DEFAULTS.get("mult_Tribal/IHS", 100)},
            {_REVENUE_ADJ_DEFAULTS.get("mult_Self Pay", 50)},
            {_REVENUE_ADJ_DEFAULTS.get("mult_Other/Unknown", 100)}
        ];
    }}
    """,
    *[Output(f"{PAGE_ID}-rev-adj-mult-{cat}", "value", allow_duplicate=True)
      for cat in _BROAD_CATEGORIES],
    Input(f"{PAGE_ID}-rev-adj-reset-mults", "n_clicks"),
    prevent_initial_call=True,
)


# Auto-fit helpers (_revAdjFitBestR, _revAdjSsrAtR, _revAdjClampPct,
# _revAdjFlashAuto) are defined in assets/rev_adj_compute.js.


# --- Fit Realization only (lag held at current) ---
clientside_callback(
    r"""
    function(n, store, smooth, ar_lag, enabled,
             m_medicare, m_medicaid, m_private, m_military,
             m_workers, m_tribal, m_self, m_other) {
        if (!n || !store || store.error) {
            return window.dash_clientside.no_update;
        }
        var mults = {
            "Medicare": m_medicare, "Medicaid": m_medicaid,
            "Private": m_private, "Military/VA": m_military,
            "Workers Comp": m_workers, "Tribal/IHS": m_tribal,
            "Self Pay": m_self, "Other/Unknown": m_other,
        };
        var c = window._revAdjCompute(store, 100, smooth, ar_lag, enabled, mults);
        if (!c || !c.est_x.length || !c.act_x.length) {
            return window.dash_clientside.no_update;
        }
        var fit = window._revAdjFitBestR(c.est_x, c.est_y, c.act_x, c.act_y);
        if (!fit) return window.dash_clientside.no_update;
        var r_pct = window._revAdjClampPct(fit.r);
        window._revAdjFlashAuto('Fit: ' + r_pct + '%');
        return r_pct;
    }
    """,
    Output(f"{PAGE_ID}-rev-adj-realization", "value", allow_duplicate=True),
    Input(f"{PAGE_ID}-rev-adj-auto-r-only", "n_clicks"),
    State(f"{PAGE_ID}-store-rev-adj-plot", "data"),
    State(f"{PAGE_ID}-rev-adj-smooth", "value"),
    State(f"{PAGE_ID}-rev-adj-ar-lag", "value"),
    State(f"{PAGE_ID}-rev-adj-enabled", "checked"),
    *[State(f"{PAGE_ID}-rev-adj-mult-{cat}", "value") for cat in _BROAD_CATEGORIES],
    prevent_initial_call=True,
)


# --- Fit A/R Lag only (realization held at current) ---
clientside_callback(
    r"""
    function(n, store, realization, smooth, enabled,
             m_medicare, m_medicaid, m_private, m_military,
             m_workers, m_tribal, m_self, m_other) {
        if (!n || !store || store.error) {
            return window.dash_clientside.no_update;
        }
        var mults = {
            "Medicare": m_medicare, "Medicaid": m_medicaid,
            "Private": m_private, "Military/VA": m_military,
            "Workers Comp": m_workers, "Tribal/IHS": m_tribal,
            "Self Pay": m_self, "Other/Unknown": m_other,
        };
        var r = (realization == null ? 90 : realization) / 100;
        var MAX_LAG = 90;
        var bestSSR = Infinity, bestLag = 0;
        for (var lag = 0; lag <= MAX_LAG; lag++) {
            var c = window._revAdjCompute(store, 100, smooth, lag, enabled, mults);
            if (!c || !c.est_x.length || !c.act_x.length) continue;
            var ssr = window._revAdjSsrAtR(c.est_x, c.est_y, c.act_x, c.act_y, r);
            if (ssr != null && ssr < bestSSR) {
                bestSSR = ssr;
                bestLag = lag;
            }
        }
        if (!isFinite(bestSSR)) return window.dash_clientside.no_update;
        window._revAdjFlashAuto('Fit: ' + bestLag + 'd');
        return bestLag;
    }
    """,
    Output(f"{PAGE_ID}-rev-adj-ar-lag", "value", allow_duplicate=True),
    Input(f"{PAGE_ID}-rev-adj-auto-lag-only", "n_clicks"),
    State(f"{PAGE_ID}-store-rev-adj-plot", "data"),
    State(f"{PAGE_ID}-rev-adj-realization", "value"),
    State(f"{PAGE_ID}-rev-adj-smooth", "value"),
    State(f"{PAGE_ID}-rev-adj-enabled", "checked"),
    *[State(f"{PAGE_ID}-rev-adj-mult-{cat}", "value") for cat in _BROAD_CATEGORIES],
    prevent_initial_call=True,
)


# --- Fit Both (joint) ---
clientside_callback(
    r"""
    function(n, store, smooth, enabled,
             m_medicare, m_medicaid, m_private, m_military,
             m_workers, m_tribal, m_self, m_other) {
        if (!n || !store || store.error) {
            return [window.dash_clientside.no_update, window.dash_clientside.no_update];
        }
        var mults = {
            "Medicare": m_medicare, "Medicaid": m_medicaid,
            "Private": m_private, "Military/VA": m_military,
            "Workers Comp": m_workers, "Tribal/IHS": m_tribal,
            "Self Pay": m_self, "Other/Unknown": m_other,
        };
        var MAX_LAG = 90;
        var bestSSR = Infinity, bestLag = 0, bestR = 0.9;
        for (var lag = 0; lag <= MAX_LAG; lag++) {
            var c = window._revAdjCompute(store, 100, smooth, lag, enabled, mults);
            if (!c || !c.est_x.length || !c.act_x.length) continue;
            var fit = window._revAdjFitBestR(c.est_x, c.est_y, c.act_x, c.act_y);
            if (fit && fit.ssr < bestSSR) {
                bestSSR = fit.ssr;
                bestLag = lag;
                bestR = fit.r;
            }
        }
        if (!isFinite(bestSSR)) {
            return [window.dash_clientside.no_update, window.dash_clientside.no_update];
        }
        var r_pct = window._revAdjClampPct(bestR);
        window._revAdjFlashAuto('Fit: ' + r_pct + '% @ ' + bestLag + 'd');
        return [r_pct, bestLag];
    }
    """,
    Output(f"{PAGE_ID}-rev-adj-realization", "value", allow_duplicate=True),
    Output(f"{PAGE_ID}-rev-adj-ar-lag", "value", allow_duplicate=True),
    Input(f"{PAGE_ID}-rev-adj-auto-both", "n_clicks"),
    State(f"{PAGE_ID}-store-rev-adj-plot", "data"),
    State(f"{PAGE_ID}-rev-adj-smooth", "value"),
    State(f"{PAGE_ID}-rev-adj-enabled", "checked"),
    *[State(f"{PAGE_ID}-rev-adj-mult-{cat}", "value") for cat in _BROAD_CATEGORIES],
    prevent_initial_call=True,
)


# --- Segment drift detection: splits the range into N segments, fits each,
# and overlays drift markers on the plot when any segment deviates from the
# global realization by more than the threshold. Does NOT update any slider.
clientside_callback(
    r"""
    function(n, store, smooth, ar_lag, enabled,
             m_medicare, m_medicaid, m_private, m_military,
             m_workers, m_tribal, m_self, m_other) {
        if (!n || !store || store.error) return window.dash_clientside.no_update;
        var mults = {
            "Medicare": m_medicare, "Medicaid": m_medicaid,
            "Private": m_private, "Military/VA": m_military,
            "Workers Comp": m_workers, "Tribal/IHS": m_tribal,
            "Self Pay": m_self, "Other/Unknown": m_other,
        };
        var sens = window._revAdjDriftSens != null ? window._revAdjDriftSens : 15;
        var hl   = window._revAdjDriftHl   != null ? window._revAdjDriftHl   : 3;
        var analysis = window._revAdjSegmentFit(
            store, smooth, ar_lag, enabled, mults, sens, hl
        );
        window._revAdjDriftActive = true;
        if (!analysis) {
            window._revAdjFlashAuto('Drift: no data');
            return window.dash_clientside.no_update;
        }
        var nSplits = (analysis.split_dates || []).length;
        if (nSplits === 0) {
            window._revAdjOverlaySegments(null);
            window._revAdjFlashAuto('Stable: no drift');
        } else {
            window._revAdjOverlaySegments(analysis);
            window._revAdjFlashAuto(nSplits + ' shift' + (nSplits > 1 ? 's' : '') + ' detected');
        }
        return window.dash_clientside.no_update;
    }
    """,
    Output(f"{PAGE_ID}-rev-adj-restyle-sink", "data", allow_duplicate=True),
    Input(f"{PAGE_ID}-rev-adj-auto-segments", "n_clicks"),
    State(f"{PAGE_ID}-store-rev-adj-plot", "data"),
    State(f"{PAGE_ID}-rev-adj-smooth", "value"),
    State(f"{PAGE_ID}-rev-adj-ar-lag", "value"),
    State(f"{PAGE_ID}-rev-adj-enabled", "checked"),
    *[State(f"{PAGE_ID}-rev-adj-mult-{cat}", "value") for cat in _BROAD_CATEGORIES],
    prevent_initial_call=True,
)


# --- Clear drift markers from the plot (menu "Clear" only; no bar to hide) ---
clientside_callback(
    r"""
    function(n) {
        if (!n) return window.dash_clientside.no_update;
        window._revAdjDriftActive = false;
        if (window._revAdjOverlaySegments) {
            window._revAdjOverlaySegments(null);
        }
        return window.dash_clientside.no_update;
    }
    """,
    Output(f"{PAGE_ID}-rev-adj-restyle-sink", "data", allow_duplicate=True),
    Input(f"{PAGE_ID}-rev-adj-auto-clear", "n_clicks"),
    prevent_initial_call=True,
)


# --- Drift threshold slider value displays ---
clientside_callback(
    "function(v) { return (v != null ? v : 15) + '%'; }",
    Output(f"{PAGE_ID}-rev-adj-drift-sens-val", "children"),
    Input(f"{PAGE_ID}-rev-adj-drift-sens", "value"),
    prevent_initial_call=True,
)
clientside_callback(
    "function(v) { return (v != null ? v : 3) + 'pp'; }",
    Output(f"{PAGE_ID}-rev-adj-drift-hl-val", "children"),
    Input(f"{PAGE_ID}-rev-adj-drift-hl", "value"),
    prevent_initial_call=True,
)


# --- Mirror threshold sliders onto window + re-run drift detection if active ---
clientside_callback(
    r"""
    function(sens, hl, store, smooth, ar_lag, enabled,
             m_medicare, m_medicaid, m_private, m_military,
             m_workers, m_tribal, m_self, m_other) {
        window._revAdjDriftSens = sens;
        window._revAdjDriftHl = hl;
        if (!window._revAdjDriftActive) return window.dash_clientside.no_update;
        if (!store || store.error) return window.dash_clientside.no_update;
        var mults = {
            "Medicare": m_medicare, "Medicaid": m_medicaid,
            "Private": m_private, "Military/VA": m_military,
            "Workers Comp": m_workers, "Tribal/IHS": m_tribal,
            "Self Pay": m_self, "Other/Unknown": m_other,
        };
        var analysis = window._revAdjSegmentFit(
            store, smooth, ar_lag, enabled, mults, sens, hl
        );
        if (!analysis) return window.dash_clientside.no_update;
        var nSplits = (analysis.split_dates || []).length;
        if (nSplits === 0) window._revAdjOverlaySegments(null);
        else window._revAdjOverlaySegments(analysis);
        return window.dash_clientside.no_update;
    }
    """,
    Output(f"{PAGE_ID}-rev-adj-restyle-sink", "data", allow_duplicate=True),
    Input(f"{PAGE_ID}-rev-adj-drift-sens", "value"),
    Input(f"{PAGE_ID}-rev-adj-drift-hl", "value"),
    State(f"{PAGE_ID}-store-rev-adj-plot", "data"),
    State(f"{PAGE_ID}-rev-adj-smooth", "value"),
    State(f"{PAGE_ID}-rev-adj-ar-lag", "value"),
    State(f"{PAGE_ID}-rev-adj-enabled", "checked"),
    *[State(f"{PAGE_ID}-rev-adj-mult-{cat}", "value") for cat in _BROAD_CATEGORIES],
    prevent_initial_call=True,
)


# Project-to-year-end toggle visibility across all 3 cumulative charts
# (shown only for current_year preset).
clientside_callback(
    """function(preset) {
        var sty = preset === "current_year" ? {} : {"display": "none"};
        return [sty, sty, sty];
    }""",
    Output(f"{PAGE_ID}-volcum-project-wrap", "style"),
    Output(f"{PAGE_ID}-rvucum-project-wrap", "style"),
    Output(f"{PAGE_ID}-dollarcum-project-wrap", "style"),
    Input(f"{PAGE_ID}-filter-date-preset", "value"),
)


# ==========================================================================
# Payor Mapping AI Classification
# ==========================================================================

_pm_ai_progress = {"done": 0, "total": 0, "running": False, "message": ""}
_pm_ai_results: list[dict] = []
_pm_ai_lock = threading.Lock()


@callback(
    Output(f"{PAGE_ID}-pm-ai-poll", "disabled"),
    Output(f"{PAGE_ID}-pm-ai-progress", "style"),
    Output(f"{PAGE_ID}-pm-ai-progress-text", "style"),
    Output(f"{PAGE_ID}-pm-ai-progress-text", "children"),
    Input(f"{PAGE_ID}-pm-ai-btn", "n_clicks"),
    State(f"{PAGE_ID}-pm-grid", "rowData"),
    State(f"{PAGE_ID}-pm-full-store", "data"),
    State(f"{PAGE_ID}-pm-filter", "value"),
    prevent_initial_call=True,
)
def _pm_start_ai(n, visible_rows, full_data, active_filter):
    """Kick off background AI classification.

    Scope: if the active filter is "unreviewed" or "unmapped", classify only
    those rows; otherwise classify everything currently in the grid (so the
    user can pre-filter via floatingFilter and target a subset).
    """
    if not n:
        return dash.no_update, dash.no_update, dash.no_update, dash.no_update

    rows = visible_rows or full_data or []
    if not rows:
        return True, {"display": "none"}, {"display": "block"}, "No payors to classify."

    with _pm_ai_lock:
        if _pm_ai_progress["running"]:
            return dash.no_update, dash.no_update, dash.no_update, "Already running…"

    entries = []
    for r in rows:
        raw = (r.get("raw_name") or "").strip()
        if not raw:
            continue
        entries.append({
            "raw_name": raw,
            "event_count": int(r.get("event_count") or 0),
            "current_standardized": r.get("standardized_payor", "") or "",
            "current_broad": r.get("broad_category", "") or "",
            "current_phdsc": r.get("phdsc_category", "") or "",
        })

    if not entries:
        return True, {"display": "none"}, {"display": "block"}, "No valid entries."

    # Existing standardized names — pulled from current data so Claude reuses them.
    existing_std = sorted({
        (r.get("standardized_payor") or "").strip()
        for r in (full_data or [])
        if (r.get("standardized_payor") or "").strip()
    })

    with _pm_ai_lock:
        _pm_ai_progress.update(done=0, total=len(entries), running=True,
                               message="Starting AI classification…")
        _pm_ai_results.clear()

    def _bg():
        from utils.payor_inference import infer_payor_classifications

        all_results: dict[str, dict] = {}
        chunk_size = 25
        for i in range(0, len(entries), chunk_size):
            chunk = entries[i : i + chunk_size]
            chunk_results = infer_payor_classifications(chunk, existing_std)
            all_results.update(chunk_results)
            with _pm_ai_lock:
                _pm_ai_progress["done"] = min(i + chunk_size, len(entries))
                _pm_ai_progress["message"] = (
                    f"Classifying… {_pm_ai_progress['done']}/{len(entries)}"
                )

        review = []
        for e in entries:
            raw = e["raw_name"]
            ai = all_results.get(raw)
            review.append({
                "raw_name": raw,
                "event_count": e["event_count"],
                "current_standardized": e["current_standardized"],
                "ai_standardized": ai["standardized_payor"] if ai else "",
                "ai_broad": ai["broad_category"] if ai else "",
                "ai_phdsc": ai["phdsc_category"] if ai else "",
                "explanation": ai["explanation"] if ai else "",
                "accept": bool(ai),
            })

        with _pm_ai_lock:
            _pm_ai_results.clear()
            _pm_ai_results.extend(review)
            _pm_ai_progress["running"] = False
            classified = sum(1 for r in review if r["ai_standardized"])
            _pm_ai_progress["message"] = (
                f"Done. {classified:,} classified of {len(review)}."
            )

    threading.Thread(target=_bg, daemon=True).start()

    return (
        False,
        {"display": "block"},
        {"display": "block"},
        f"Classifying {len(entries)} entries…",
    )


@callback(
    Output(f"{PAGE_ID}-pm-ai-poll", "disabled", allow_duplicate=True),
    Output(f"{PAGE_ID}-pm-ai-progress", "value"),
    Output(f"{PAGE_ID}-pm-ai-progress", "style", allow_duplicate=True),
    Output(f"{PAGE_ID}-pm-ai-progress-text", "children", allow_duplicate=True),
    Output(f"{PAGE_ID}-pm-ai-progress-text", "style", allow_duplicate=True),
    Output(f"{PAGE_ID}-pm-ai-review", "opened"),
    Output(f"{PAGE_ID}-pm-ai-review-grid", "rowData"),
    Input(f"{PAGE_ID}-pm-ai-poll", "n_intervals"),
    prevent_initial_call=True,
)
def _pm_ai_poll(n):
    """Poll background AI classification progress."""
    no = dash.no_update
    with _pm_ai_lock:
        done = _pm_ai_progress["done"]
        total = _pm_ai_progress["total"]
        running = _pm_ai_progress["running"]
        msg = _pm_ai_progress["message"]
        review = list(_pm_ai_results) if not running and _pm_ai_results else None

    pct = int(done * 100 / total) if total > 0 else 0
    if running:
        return False, pct, {"display": "block"}, msg, {"display": "block"}, no, no
    if review:
        return (
            True, 100, {"display": "none"}, msg, {"display": "block"},
            True, review,
        )
    return True, 100, {"display": "none"}, msg, {"display": "block"}, no, no


@callback(
    Output(f"{PAGE_ID}-pm-ai-review-grid", "rowData", allow_duplicate=True),
    Input(f"{PAGE_ID}-pm-ai-accept-all", "n_clicks"),
    State(f"{PAGE_ID}-pm-ai-review-grid", "rowData"),
    prevent_initial_call=True,
)
def _pm_ai_accept_all(n, data):
    if not n or not data:
        return dash.no_update
    for r in data:
        if r.get("ai_standardized") or r.get("ai_broad"):
            r["accept"] = True
    return data


@callback(
    Output(f"{PAGE_ID}-pm-ai-review", "opened", allow_duplicate=True),
    Output(f"{PAGE_ID}-pm-ai-progress-text", "children", allow_duplicate=True),
    Input(f"{PAGE_ID}-pm-ai-reject-all", "n_clicks"),
    prevent_initial_call=True,
)
def _pm_ai_reject_all(n):
    if not n:
        return dash.no_update, dash.no_update
    with _pm_ai_lock:
        _pm_ai_results.clear()
    return False, "Rejected all — no changes applied."


@callback(
    Output(f"{PAGE_ID}-pm-grid", "rowData", allow_duplicate=True),
    Output(f"{PAGE_ID}-pm-full-store", "data", allow_duplicate=True),
    Output(f"{PAGE_ID}-pm-count", "children", allow_duplicate=True),
    Output(f"{PAGE_ID}-pm-ai-review", "opened", allow_duplicate=True),
    Output(f"{PAGE_ID}-pm-ai-progress-text", "children", allow_duplicate=True),
    Input(f"{PAGE_ID}-pm-ai-apply", "n_clicks"),
    State(f"{PAGE_ID}-pm-ai-review-grid", "rowData"),
    State(f"{PAGE_ID}-pm-full-store", "data"),
    State(f"{PAGE_ID}-pm-filter", "value"),
    prevent_initial_call=True,
)
def _pm_ai_apply(n, review_data, full_data, active_filter):
    if not n or not review_data or not full_data:
        return (dash.no_update,) * 5

    accepted = [r for r in review_data
                if r.get("accept") and (r.get("ai_standardized") or r.get("ai_broad"))]
    if not accepted:
        return (dash.no_update, dash.no_update, dash.no_update,
                False, "No rows accepted — no changes applied.")

    # Persist + auto-mark reviewed (the explicit accept IS the review).
    for r in accepted:
        raw = (r.get("raw_name") or "").strip()
        if not raw:
            continue
        upsert_payor_mapping(
            raw_name=raw,
            standardized_payor=r.get("ai_standardized", "") or "",
            broad_category=r.get("ai_broad") or "Other/Unknown",
            phdsc_category=r.get("ai_phdsc") or "9 - Other",
            reviewed=1,
            ai_explanation=r.get("explanation", "") or "",
        )

    accepted_map = {r["raw_name"]: r for r in accepted}
    for row in full_data:
        a = accepted_map.get(row.get("raw_name"))
        if a:
            row["standardized_payor"] = a.get("ai_standardized", "") or ""
            row["broad_category"] = a.get("ai_broad") or "Other/Unknown"
            row["phdsc_category"] = a.get("ai_phdsc") or "9 - Other"
            row["reviewed"] = True
            row["ai_explanation"] = a.get("explanation", "") or ""

    mapped = sum(1 for r in full_data if r.get("standardized_payor"))
    count_text = f"{mapped} mapped / {len(full_data)} total"
    visible = _apply_pm_filter(full_data, active_filter)

    with _pm_ai_lock:
        _pm_ai_results.clear()

    return visible, full_data, count_text, False, (
        f"Applied {len(accepted)} AI classifications."
    )


# Wire AI settings persistence (desktop billing prefix "bill")
register_ai_settings_callbacks("bill")

