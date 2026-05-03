"""Billing enrichment — RVU/OPPS merges, payor fallback, per-row revenue.

Extracted from pages/billing.py so it can be imported from non-Dash contexts
(e.g., scripts/sanitize.py) without triggering dash.register_page().

Two-tier cache:
  1. In-memory dict — hits when underlying loader caches are unchanged.
  2. Parquet sidecar (`BillingEnriched.parquet`) — survives restarts;
     invalidated by any source file change OR a change to this module.
"""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pandas as pd

from utils.cpt_categories import (
    CODE_TO_CATEGORY as _CODE_TO_CATEGORY,
    CODE_TO_SUBCATEGORY as _CODE_TO_SUBCATEGORY,
)


# CMS Conversion Factor (Medicare PFS) — update annually
_CMS_CF = {
    2015: 35.80, 2016: 35.80, 2017: 35.89, 2018: 36.00, 2019: 36.04,
    2020: 36.09, 2021: 34.89, 2022: 34.61, 2023: 33.89, 2024: 33.29,
    2025: 32.35, 2026: 33.40,
}
_CMS_CF_DEFAULT = 33.40


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
    # Reuse caller-supplied `_base_code` (vectorized dict map) when present —
    # avoids a duplicate per-row .apply over the full billing frame.
    if "_base_code" in df.columns:
        df["_base"] = df["_base_code"]
    else:
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

    df["Pro_Total_RVU"] = df["wRVU"] + df["Fac_PE_RVU"] + df["MP_RVU"]
    df["Fac_Total_RVU"] = global_key.map(fac_total_dict).fillna(0)

    # TC components for Aberdeen hospital revenue (PFS TC rows)
    df["TC_wRVU"] = tc_key.map(wrvu_dict)
    df["TC_PE_RVU"] = tc_key.map(fac_pe_dict)
    df["TC_MP_RVU"] = tc_key.map(mp_dict)
    tc_miss = df["TC_PE_RVU"].isna()
    tc_only = tc_miss & no_work  # wRVU=0 → entire code is technical
    if tc_only.any():
        df.loc[tc_only, "TC_wRVU"] = global_key[tc_only].map(wrvu_dict).fillna(0)
        df.loc[tc_only, "TC_PE_RVU"] = global_key[tc_only].map(fac_pe_dict).fillna(0)
        df.loc[tc_only, "TC_MP_RVU"] = global_key[tc_only].map(mp_dict).fillna(0)
    df[["TC_wRVU", "TC_PE_RVU", "TC_MP_RVU"]] = df[["TC_wRVU", "TC_PE_RVU", "TC_MP_RVU"]].fillna(0)

    df.drop(columns=["_base", "_yr"], inplace=True)
    return df


# ---------------------------------------------------------------------------
# Cached enriched billing dataframe (TTL-evicted to free RAM during idle)
# ---------------------------------------------------------------------------

_enriched_cache = {"key": None, "df": None}

# Register the cache for TTL eviction by the loader-sweeper. After the TTL
# expires the sweeper resets both keys to None; the next call rebuilds from
# the parquet sidecar (~2-3s) instead of holding the 100+MB enriched frame
# in RAM 24/7.
from data.loader import register_ttl_dict as _register_ttl_dict
_enriched_ttl = _register_ttl_dict(_enriched_cache)


def _enriched_source_paths():
    """Source files whose changes invalidate the enriched parquet cache.

    Includes raw billing CSVs, referrals exports, RVU/OPPS reference tables,
    and this module itself — so any change to enrichment logic invalidates
    the cache and forces a rebuild on next startup.
    """
    from config.settings import DATA_DIR, DATA_INCREMENTAL
    from data.loader import _source_files_for_incremental

    paths = list(_source_files_for_incremental(DATA_INCREMENTAL / "Billing", "Billing"))
    paths += sorted(Path(DATA_DIR).glob("Referrals_Report_RadiantCare_All_*.xlsx"))
    loader_dir = Path(__file__).resolve().parent
    for rel in (
        "rvu_files/rvu_lookup.csv",
        "rvu_files/gpci_rest_of_wa.csv",
        "opps_files/opps_lookup.csv",
        "opps_files/opps_params.csv",
    ):
        p = loader_dir / rel
        if p.exists():
            paths.append(p)
    paths.append(Path(__file__).resolve())
    return paths


def _get_enriched_billing():
    """Return billing df with Category, ChargeStatus, wRVU columns added.

    Two-tier cache:
      1. In-memory dict — hits when underlying loader caches are unchanged.
      2. Parquet sidecar (`BillingEnriched.parquet`) — survives restarts;
         invalidated by source file or enrichment-logic changes.
    """
    from data.loader import (
        load_billing, load_rvu_lookup, load_opps_lookup,
        _read_parquet_cache, _write_parquet_cache,
    )

    billing = load_billing()
    rvu = load_rvu_lookup()
    opps = load_opps_lookup()

    key = (id(billing), id(rvu), id(opps))
    if _enriched_cache["key"] == key and _enriched_cache["df"] is not None:
        _enriched_ttl.touch()
        return _enriched_cache["df"]

    src_paths = _enriched_source_paths()
    cached_pq = _read_parquet_cache("BillingEnriched", src_paths)
    if cached_pq is not None:
        _enriched_cache["key"] = key
        _enriched_cache["df"] = cached_pq
        _enriched_ttl.touch()
        return cached_pq

    df = billing.copy()
    if "Quantity" not in df.columns:
        df["Quantity"] = 1
    else:
        df["Quantity"] = pd.to_numeric(df["Quantity"], errors="coerce").fillna(1).astype(int).clip(lower=1)
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
    from data.loader import load_referrals

    if "PayorName" in df.columns:
        df["PrimaryInsurance"] = df["PayorName"].where(
            df["PayorName"].notna() & (df["PayorName"].str.strip() != "")
        )
    else:
        df["PrimaryInsurance"] = np.nan
    # PayorName/PrimaryInsurance are Categorical from the loader (memory
    # optimisation). The fallback below assigns RefPayer values that aren't
    # in the existing categories, and then fillna("Unknown") would also fail.
    # Cast to object once, here, before any mutation.
    if isinstance(df["PrimaryInsurance"].dtype, pd.CategoricalDtype):
        df["PrimaryInsurance"] = df["PrimaryInsurance"].astype("object")

    # Referral fallback: match to closest referral by date so a 2024 billing
    # row doesn't pick up a 2020 payer.
    mask = df["PrimaryInsurance"].isna()
    if mask.any() and "PatientId" in df.columns and "DateOfService" in df.columns:
        def _parse_ref_payer(v):
            if pd.isna(v):
                return None
            first_line = str(v).split("\n")[0].strip()
            return re.sub(r"\s*\[\d+\]\s*$", "", first_line).strip() or None

        try:
            referrals = load_referrals()
        except Exception:
            referrals = pd.DataFrame()
        if not referrals.empty and "Payer" in referrals.columns and "MRN" in referrals.columns:
            ref_payer = referrals[["MRN", "Created", "Payer"]].copy()
            ref_payer["RefPayer"] = ref_payer["Payer"].apply(_parse_ref_payer)
            ref_payer = ref_payer.dropna(subset=["RefPayer", "Created"])
            ref_payer = ref_payer.sort_values("Created")

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

        is_ab = df["Department"] == "Aberdeen" if "Department" in df.columns else pd.Series(False, index=df.index)
        wi = yrs.map({y: p[1] for y, p in opps_params.items()}).fillna(1.0)
        labor = yrs.map({y: p[2] for y, p in opps_params.items()}).fillna(0.60)
        sch = yrs.map({y: p[3] for y, p in opps_params.items()}).fillna(1.071)
        opps_adj = df["OPPS_Rate"] * (labor * wi + (1 - labor)) * sch
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
    _enriched_ttl.touch()
    try:
        _write_parquet_cache("BillingEnriched", df, src_paths)
    except Exception:
        pass  # Cache write failure is non-fatal — in-memory cache still serves
    return df
