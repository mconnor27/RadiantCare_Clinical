"""Med-Onc Cross-Referrals page.

Analyzes referrals TO medical oncology (the five PRCS sites — Lacey,
Centralia, Aberdeen, Yelm, Shelton) and joins by MRN against RadiantCare
(rad-onc) referrals and treatment data to answer: of patients referred to
med-onc, how many are actually seen by med-onc, how many also reach
rad-onc, when, and for what diagnoses? Gaps between expected and observed
rad-onc conversion flag potential under-referral opportunities.
"""

import dash
import dash_mantine_components as dmc
import dash_ag_grid as dag
from dash import callback, clientside_callback, ClientsideFunction, dcc, html, Input, Output
from dash_iconify import DashIconify
import plotly.graph_objects as go
import pandas as pd
import numpy as np

from config.settings import (
    PRIMARY, NEUTRAL, SEMANTIC_COLORS,
    DEFAULT_GRAPH_CONFIG,
    DEFAULT_COLUMN_DEFS, DEFAULT_GRID_OPTIONS, DEFAULT_GRID_CLASS,
)
from components.kpi_card import kpi_card, kpi_placeholder
from components.chart_card import register_chart_callbacks
from components.chart_settings import chart_settings_popover
from components.diagnosis_filter import diagnosis_accordion, register_diagnosis_callbacks
from components.outlier_panel import outlier_panel, register_outlier_callbacks
from utils.charts import apply_default_layout, empty_figure
from utils.diagnosis_categories import (
    build_code_to_category, categorise_referral,
)


PAGE_ID = "medonc"
dash.register_page(__name__, path="/medonc-referrals", name="Referrals (MedOnc)", order=29)

_DEFAULT_PRE_DAYS = 60
_DEFAULT_POST_DAYS = 3650  # 10 years — widest available window

# Regex matching the five PRCS med-onc departments in the rad-onc referrals
# feed's "Referred by Department" — the same sites this page already tracks
# referrals TO. Used by the "Referred by Med-Onc" linkage mode so linkage
# counts only direct PRCS med-onc → rad-onc referrals (not external med-onc
# groups that happen to also be classified as Medical Oncology).
_PRCS_MEDONC_DEPT_RE = r"PRCS\s+(?:LACEY|CENTRALIA|ABERDEEN|YELM|SHELTON)(?:\s|$)"


_SITE_COLORS = {
    "Lacey":     "#2196F3",
    "Centralia": "#F44336",
    "Aberdeen":  "#4CAF50",
    "Yelm":      "#9C27B0",
    "Shelton":   "#FF9800",
}
_SITES = list(_SITE_COLORS.keys())


# ---------------------------------------------------------------------------
# Cohort computation
# ---------------------------------------------------------------------------

def _build_cohort(date_preset, site_filter, diag_cats, diag_mode,
                  pre_days, post_days, link_mode="any"):
    """Build the med-onc cohort joined with rad-onc signals (one row per MRN)."""
    from data.loader import (
        load_medonc_referrals, load_referrals, load_treatment_detail, load_diagnosis,
    )

    medonc = load_medonc_referrals()
    if medonc.empty:
        return medonc

    df = medonc.copy()

    # Referral-intent diagnosis: same cascade as the rad-onc Referrals page
    # (ICD of Diagnoses → Rfl Prim Dx text → Diagnoses text → Onc Dx text).
    # Keeping the two pages symmetric means an "X referrals to med-onc" row
    # and an "X referrals to rad-onc" row are counted the same way.
    try:
        c2c = build_code_to_category(load_diagnosis())
    except Exception:
        c2c = {}
    df["DxCategory"] = df.apply(
        lambda r: categorise_referral(
            diagnoses=r.get("Diagnoses"),
            rfl_prim_dx=r.get("Rfl Prim Dx"),
            onc_dx=r.get("Onc Dx"),
            c2c=c2c,
        ),
        axis=1,
    )

    # Date preset
    if "Created" in df.columns and date_preset and date_preset != "all":
        last = df["Created"].max()
        if pd.notna(last):
            offsets = {"12mo": 365, "24mo": 730, "3y": 1095, "5y": 1826}
            if date_preset in offsets:
                df = df[df["Created"] >= (last - pd.Timedelta(days=offsets[date_preset]))]
            elif date_preset == "ytd":
                df = df[df["Created"] >= pd.Timestamp(last.year, 1, 1)]

    if site_filter:
        df = df[df["ReferredToSite"].isin(site_filter)]

    # Diagnosis filter — match on the derived DxCategory (not the accordion's
    # default ICD-code path, since our category signal is from free text).
    if diag_cats:
        cat_set = set(diag_cats)
        df = df[df["DxCategory"].isin(cat_set)]

    if df.empty:
        return df

    # Collapse to one row per patient — earliest med-onc referral in window
    df = df.sort_values("Created")
    patients = df.drop_duplicates(subset=["MRN"], keep="first").copy()

    # Whether this med-onc referral itself has a First Appt recorded (i.e., the
    # patient was actually seen by med-onc). `Appt Attached == "Yes"` is a
    # secondary signal, but First Appt is the authoritative one.
    patients["SeenByMedOnc"] = patients.get("First Appt", pd.Series(pd.NaT, index=patients.index)).notna()

    # Join to rad-onc referrals. In "medonc" mode we restrict to rad-onc
    # referrals whose referring source is one of the five PRCS med-onc
    # departments (LACEY/CENTRALIA/ABERDEEN/YELM/SHELTON) — the specific
    # med-onc practice this page tracks. External med-onc groups are
    # intentionally excluded so the metric measures our own department's
    # referral flow, not Medical Oncology as a specialty.
    radref = load_referrals()
    if link_mode == "medonc" and not radref.empty and "Referred by Department" in radref.columns:
        radref = radref[
            radref["Referred by Department"].fillna("").str.contains(
                _PRCS_MEDONC_DEPT_RE, case=False, regex=True, na=False
            )
        ]
    if not radref.empty and "MRN" in radref.columns:
        r = radref[["MRN", "Created", "First Appt"]].copy()
        r.columns = ["MRN", "RadOncReferralCreated", "RadOncFirstAppt"]
        r = r.sort_values("RadOncReferralCreated").drop_duplicates("MRN", keep="first")
        patients = patients.merge(r, on="MRN", how="left")
    else:
        patients["RadOncReferralCreated"] = pd.NaT
        patients["RadOncFirstAppt"] = pd.NaT

    # Join to rad-onc treatment
    tx = load_treatment_detail()
    if not tx.empty and "PatientId" in tx.columns and "ScheduledDateTime" in tx.columns:
        tx_first = (
            tx[["PatientId", "ScheduledDateTime"]]
            .dropna()
            .groupby("PatientId", as_index=False)["ScheduledDateTime"].min()
            .rename(columns={"PatientId": "MRN", "ScheduledDateTime": "RadOncTreatmentStart"})
        )
        tx_first["MRN"] = pd.to_numeric(tx_first["MRN"], errors="coerce").astype("Int64")
        patients = patients.merge(tx_first, on="MRN", how="left")
    else:
        patients["RadOncTreatmentStart"] = pd.NaT

    # In direct-referral mode, only count treatment for patients who were
    # actually referred from med-onc — otherwise we'd credit the med-onc
    # pathway with treatments that came in through other referral sources.
    if link_mode == "medonc":
        patients.loc[patients["RadOncReferralCreated"].isna(), "RadOncTreatmentStart"] = pd.NaT

    # Linkage window
    pre = int(pre_days) if pre_days is not None else _DEFAULT_PRE_DAYS
    post = int(post_days) if post_days is not None else _DEFAULT_POST_DAYS
    medonc_dt = patients["Created"]

    contact_cols = ["RadOncReferralCreated", "RadOncFirstAppt", "RadOncTreatmentStart"]
    contact_dt = patients[contact_cols].min(axis=1)
    delta = (contact_dt - medonc_dt).dt.days
    linked = delta.between(-pre, post)
    patients["LinkedToRadOnc"] = linked.fillna(False)
    patients["DaysToRadOnc"] = delta.where(linked)

    for src, tgt in [
        ("RadOncReferralCreated", "LinkedRadRef"),
        ("RadOncFirstAppt",       "LinkedRadConsult"),
        ("RadOncTreatmentStart",  "LinkedRadTx"),
    ]:
        d = (patients[src] - medonc_dt).dt.days
        patients[tgt] = d.between(-pre, post).fillna(False)

    return patients


# ---------------------------------------------------------------------------
# Flow-gantt data builders — produce the dicts consumed by the shared
# flow_gantt.js clientside renderer (main gantt + companion charts).
# ---------------------------------------------------------------------------

_FLOW_STAGES = ["Created", "Scheduled", "Med-Onc Appt", "Rad-Onc Referral"]
_FLOW_COLORS_MED = ["#7C2A83", "#2196F3", "#4CAF50", "#F59E0B"]

# Per-transition outlier cap DEFAULTS (days) — user-adjustable via the
# outlier panel. Capping keeps a handful of extreme tail values from
# dragging medians around and compressing distribution plots.
_CAP_CREATED_TO_SCHED = 14        # 2 weeks — matches referrals-page default
_CAP_SCHED_TO_APPT    = 30        # 4 weeks
_CAP_APPT_TO_RADREF   = 180       # 6 months — captures most adjuvant-timing rad-onc refs
_OUTLIER_SLIDER_MAX   = 540       # 18 months — top of the slider range


def _simple_kde(values, n_points=200):
    """Gaussian-kernel KDE with Silverman bandwidth. Matches the helper
    in referrals.py so the clientside distribution chart gets the exact
    data shape it expects."""
    arr = np.asarray(values, dtype=float)
    if len(arr) < 2:
        return [0.0], [0.0]
    std = np.std(arr, ddof=1) or 1.0
    bw = 1.06 * std * len(arr) ** -0.2
    lo = max(0, arr.min() - 3 * bw)
    hi = arr.max() + 3 * bw
    x = np.linspace(lo, hi, n_points)
    density = np.zeros(n_points)
    for v in arr:
        density += np.exp(-0.5 * ((x - v) / bw) ** 2)
    density /= len(arr) * bw * np.sqrt(2 * np.pi)
    return [round(float(v), 3) for v in x], [round(float(v), 6) for v in density]


def _safe_stat(series, cap, func="median"):
    s = pd.to_numeric(series, errors="coerce").dropna()
    s = s[(s >= 0) & (s <= cap)]
    if s.empty:
        return 0.0
    return float(s.median()) if func == "median" else float(s.mean())


def _compute_medonc_flow_data(cohort, cap_0=_CAP_CREATED_TO_SCHED,
                               cap_1=_CAP_SCHED_TO_APPT,
                               cap_2=_CAP_APPT_TO_RADREF):
    """Main gantt rawData. Shape matches referrals page's flow-gantt dict
    so flow_gantt.js can render it unchanged.

    Stages:
        0  Referral Created (anchor)
        1  Scheduled                (Assigned On is not null)
        2  Med-Onc Appt             (First Appt is not null)
        3  Rad-Onc Referral         (LinkedRadRef flag from cohort)

    cap_0 / cap_1 / cap_2 are the outlier caps applied when computing
    median/mean durations between stages. Stage counts and dropoffs are
    NOT capped — those reflect the full cohort.
    """
    if cohort.empty:
        return None

    n = len(cohort)
    created_mask = pd.Series(True, index=cohort.index)
    # Stage masks are CUMULATIVE: reaching stage N requires having reached
    # every prior stage. Guarantees stageCount[i+1] <= stageCount[i] and
    # flow[i] == stageCount[i+1] exactly, so bar heights match their
    # incoming flow bands. Without this, a patient who got a rad-onc
    # referral but skipped their med-onc appt would inflate the
    # Rad-Onc Referral bar without inflating the Appt→RadRef flow.
    scheduled_raw = cohort["Assigned On"].notna() if "Assigned On" in cohort.columns else created_mask & False
    appt_raw = cohort["SeenByMedOnc"].astype(bool) if "SeenByMedOnc" in cohort.columns else created_mask & False
    radref_raw = cohort["LinkedRadRef"].astype(bool) if "LinkedRadRef" in cohort.columns else created_mask & False
    scheduled_mask = created_mask & scheduled_raw
    appt_mask      = scheduled_mask & appt_raw
    radref_mask    = appt_mask & radref_raw

    masks = [created_mask, scheduled_mask, appt_mask, radref_mask]
    stage_counts = [int(m.sum()) for m in masks]

    flow_values = [
        int((created_mask & scheduled_mask).sum()),
        int((scheduled_mask & appt_mask).sum()),
        int((appt_mask & radref_mask).sum()),
    ]
    dropoffs = [
        int((created_mask & ~scheduled_mask).sum()),
        int((scheduled_mask & ~appt_mask).sum()),
        int((appt_mask & ~radref_mask).sum()),
    ]

    # Pending vs cancelled categorization for the first two transitions
    # (Created → Scheduled, Scheduled → Appt). Classification is based on
    # the referral's Status:
    #   pending   = active (Pending Review, Authorized, Open, Auth Not Req)
    #   cancelled = terminal (Closed / Denied / Canceled)
    #
    # For the third transition (Med-Onc Appt → Rad-Onc Referral), this split
    # doesn't apply. The med-onc referral Status describes the lifecycle of
    # the med-onc visit itself, not whether a downstream rad-onc referral
    # exists. Whether a seen patient is "eventually referred to us or not"
    # is a separate clinical decision, not a status. Leave those counts at 0
    # so the band narrows cleanly into the Rad-Onc Referral stage without
    # routing through the pending/cancelled collectors.
    status = cohort["Status"].fillna("") if "Status" in cohort.columns else pd.Series("", index=cohort.index)
    is_terminal = status.isin(["Closed", "Denied", "Canceled"])
    pending_counts = []
    cancelled_counts = []
    for i, drop_mask in enumerate((
        created_mask & ~scheduled_mask,
        scheduled_mask & ~appt_mask,
        appt_mask & ~radref_mask,
    )):
        if i == 2:
            pending_counts.append(0)
            cancelled_counts.append(0)
        else:
            pending_counts.append(int((drop_mask & ~is_terminal).sum()))
            cancelled_counts.append(int((drop_mask & is_terminal).sum()))

    # --- Transition durations ---
    d0 = (cohort["Assigned On"] - cohort["Created"]).dt.days if "Assigned On" in cohort.columns else pd.Series(dtype=float)
    d1 = (cohort["First Appt"] - cohort["Assigned On"]).dt.days if ("First Appt" in cohort.columns and "Assigned On" in cohort.columns) else pd.Series(dtype=float)
    d2 = (cohort["RadOncReferralCreated"] - cohort["First Appt"]).dt.days if "RadOncReferralCreated" in cohort.columns else pd.Series(dtype=float)

    median_days = [
        _safe_stat(d0, cap_0, "median"),
        _safe_stat(d1, cap_1, "median"),
        _safe_stat(d2, cap_2, "median"),
    ]
    mean_days = [
        _safe_stat(d0, cap_0, "mean"),
        _safe_stat(d1, cap_1, "mean"),
        _safe_stat(d2, cap_2, "mean"),
    ]

    # Per-patient total (Created -> Rad-Onc Ref), using linked patients.
    # Capped by sum of per-transition caps so the total stays consistent
    # with the capped medians.
    cap_total = cap_0 + cap_1 + cap_2
    if "RadOncReferralCreated" in cohort.columns:
        per_patient = (cohort["RadOncReferralCreated"] - cohort["Created"]).dt.days
        per_patient = per_patient[(per_patient >= 0) & (per_patient <= cap_total)].dropna()
        total_median = float(per_patient.median()) if not per_patient.empty else sum(median_days)
    else:
        total_median = sum(median_days)

    # Time-proportional stage positions — same algorithm as the Workflow
    # page's flow gantt: each transition gets a minimum gap plus a bonus
    # proportional to its median duration. Short transitions compress,
    # long ones (e.g. Appt → Rad-Onc Ref, often a month+) expand, so the
    # horizontal axis roughly represents elapsed time.
    n_stages = len(_FLOW_STAGES)
    n_gaps = len(median_days)
    _min_gap = 0.07
    _total_min = _min_gap * n_gaps
    _remaining = max(1.0 - _total_min, 0.0)
    _total_dur = sum(median_days) or 1
    x_positions = [0.0]
    _cum = 0.0
    for d in median_days:
        bonus = (d / _total_dur) * _remaining
        _cum += _min_gap + bonus
        x_positions.append(min(_cum, 1.0))
    x_positions[-1] = 1.0

    return {
        "stages": _FLOW_STAGES,
        "stageKeys": _FLOW_STAGES,
        "stageCounts": stage_counts,
        "flowValues": flow_values,
        "dropoffs": dropoffs,
        "pendingCounts": pending_counts,
        "cancelledCounts": cancelled_counts,
        "medianDays": median_days,
        "meanDays": mean_days,
        "aggFunc": "median",
        "allottedDays": [None] * (n_stages - 1),
        "onTimePcts": [None] * (n_stages - 1),
        "xPositions": x_positions,
        "colors": _FLOW_COLORS_MED,
        "loopbacks": [0] * n_stages,
        "loopbackPairs": [],
        "totalMedianDays": total_median,
        "totalPatients": stage_counts[0],
        # Match the rad-onc referrals page's internal SVG height — same
        # renderer, same geometry constants, same downstream scaling.
        "height": 480,
    }


def _compute_medonc_flow_details(cohort, cap_0=_CAP_CREATED_TO_SCHED,
                                  cap_1=_CAP_SCHED_TO_APPT,
                                  cap_2=_CAP_APPT_TO_RADREF):
    """Per-transition details consumed by the clientside distribution,
    trend, and conversion charts. Shape matches referrals-page contract.
    cap_0/1/2 are the per-transition outlier caps (days)."""
    if cohort.empty:
        return None

    transitions = []

    def _build(days_series, ref_dates, label, color, cap):
        arr = pd.to_numeric(days_series, errors="coerce").dropna().values
        arr = arr[(arr >= 0) & (arr <= cap)]
        if len(arr) == 0:
            return None
        kde_x, kde_y = _simple_kde(arr)
        temp = pd.DataFrame({"_days": days_series, "_ref": ref_dates}).dropna()
        temp = temp[(temp["_days"] >= 0) & (temp["_days"] <= cap)]
        trend_by_agg = {}
        for agg_key in ("W", "M", "Y"):
            temp["_period"] = temp["_ref"].dt.to_period(agg_key).dt.to_timestamp()
            gmed = temp.groupby("_period")["_days"].median()
            gmean = temp.groupby("_period")["_days"].mean()
            gcnt = temp.groupby("_period")["_days"].size()
            periods = sorted(gmed.index)
            trend_by_agg[agg_key] = {
                "dates": [d.isoformat() for d in periods],
                "medians": [round(float(gmed[d]), 1) for d in periods],
                "means":   [round(float(gmean[d]), 1) for d in periods],
                "kmMedians": [None] * len(periods),
                "counts":  [int(gcnt.get(d, 0)) for d in periods],
                "completionRates": [1.0] * len(periods),
            }
        return {
            "label": label,
            "color": color,
            "days": [round(float(d), 3) for d in arr],
            "density": {"x": kde_x, "y": kde_y},
            "trendByAgg": trend_by_agg,
            "n": int(len(arr)),
            "nCensored": 0,
            "median": round(float(np.median(arr)), 3),
            "mean":   round(float(np.mean(arr)), 3),
            "kmMedian": None,
            "p25": round(float(np.percentile(arr, 25)), 3),
            "p75": round(float(np.percentile(arr, 75)), 3),
        }

    # Transition labels feed the distribution / trend / conversion chart
    # titles via the shared JS. Keep them tight — "Med-Onc Appt → Rad-Onc
    # Referral Rate (monthly)" was wrapping and clipping.
    d0 = (cohort["Assigned On"] - cohort["Created"]).dt.days if "Assigned On" in cohort.columns else pd.Series(dtype=float)
    ref0 = cohort["Created"] if "Created" in cohort.columns else pd.Series(dtype="datetime64[ns]")
    transitions.append(_build(d0, ref0, "Created → Scheduled", _FLOW_COLORS_MED[0], cap_0))

    d1 = (cohort["First Appt"] - cohort["Assigned On"]).dt.days if ("First Appt" in cohort.columns and "Assigned On" in cohort.columns) else pd.Series(dtype=float)
    ref1 = cohort["Assigned On"] if "Assigned On" in cohort.columns else pd.Series(dtype="datetime64[ns]")
    transitions.append(_build(d1, ref1, "Scheduled → Appt", _FLOW_COLORS_MED[1], cap_1))

    d2 = (cohort["RadOncReferralCreated"] - cohort["First Appt"]).dt.days if "RadOncReferralCreated" in cohort.columns else pd.Series(dtype=float)
    ref2 = cohort["First Appt"] if "First Appt" in cohort.columns else pd.Series(dtype="datetime64[ns]")
    transitions.append(_build(d2, ref2, "Appt → Rad-Onc Ref", _FLOW_COLORS_MED[2], cap_2))

    # Total: Created → Rad-Onc Referral
    if "RadOncReferralCreated" in cohort.columns and "Created" in cohort.columns:
        d_total = (cohort["RadOncReferralCreated"] - cohort["Created"]).dt.days
    else:
        d_total = pd.Series(dtype=float)
    total = _build(d_total, ref0, "Total: Created → Rad-Onc Ref", PRIMARY, cap_0 + cap_1 + cap_2)

    # --- Conversion rate trend data ---
    # The shared JS renders two series on this chart, keyed as `schedPct`
    # and `completePct`. It labels them "Created → Scheduled Rate" and
    # "Scheduled → Completed Rate" — but on the referrals page its
    # `completePct` is actually computed server-side as completed/created
    # (so its label is slightly misleading). Here we supply TRUE inter-stage
    # rates so the labels match the numbers:
    #   schedPct    = scheduled/created         (Created → Scheduled)
    #   completePct = seen-by-medonc/scheduled  (Scheduled → Completed/Seen)
    # "Completed" is mapped to Seen By Med-Onc — the natural med-onc
    # endpoint. Rad-onc referral is the 4th stage and shows up on the
    # Diagnosis/Site conversion charts below.
    conv_by_agg = {}
    if "Created" in cohort.columns:
        for agg_key in ("W", "M", "Y"):
            periods = cohort["Created"].dt.to_period(agg_key).dt.to_timestamp()
            grp = cohort.groupby(periods)
            created = grp.size()
            scheduled = grp.apply(
                lambda g: int(g["Assigned On"].notna().sum()) if "Assigned On" in g.columns else 0,
                include_groups=False,
            )
            seen = grp.apply(
                lambda g: int(g["SeenByMedOnc"].astype(bool).sum()),
                include_groups=False,
            )
            radref = grp.apply(
                lambda g: int(g["LinkedRadRef"].astype(bool).sum()),
                include_groups=False,
            )
            all_periods = sorted(created.index)
            conv_by_agg[agg_key] = {
                "dates": [d.isoformat() for d in all_periods],
                "created":   created.reindex(all_periods, fill_value=0).tolist(),
                "scheduled": scheduled.reindex(all_periods, fill_value=0).tolist(),
                "completed": seen.reindex(all_periods, fill_value=0).tolist(),
                "schedPct": [
                    round(scheduled.get(d, 0) / created.get(d, 1) * 100, 1) for d in all_periods
                ],
                # True inter-stage rate: of those scheduled, what fraction were seen
                "completePct": [
                    round(seen.get(d, 0) / scheduled.get(d, 1) * 100, 1)
                    if scheduled.get(d, 0) > 0 else 0.0
                    for d in all_periods
                ],
                # Overall Created → Completed rate, for the default (no band
                # selected) view. The proxy in medonc_flow_gantt.js swaps this
                # in when no band is active so the "Created → Completed"
                # title shows the right numbers.
                "completePctOverall": [
                    round(seen.get(d, 0) / created.get(d, 1) * 100, 1) for d in all_periods
                ],
                # Med-Onc Appt → Rad-Onc Referral inter-stage rate — the shared
                # flow_gantt.js conversion renderer only knows about 3 stages,
                # so our 4th-stage conversion is handled by a custom branch in
                # the medoncFlowGantt.renderConv proxy.
                "radref": radref.reindex(all_periods, fill_value=0).tolist(),
                "radrefPct": [
                    round(radref.get(d, 0) / seen.get(d, 1) * 100, 1)
                    if seen.get(d, 0) > 0 else 0.0
                    for d in all_periods
                ],
            }

    return {
        "transitions": transitions,
        "total": total,
        "aggFunc": "median",
        "convByAgg": conv_by_agg,
    }


# ---------------------------------------------------------------------------
# Filter bar
# ---------------------------------------------------------------------------

_DATE_PRESETS = [
    {"value": "12mo", "label": "12 Mo"},
    {"value": "24mo", "label": "24 Mo"},
    {"value": "3y",   "label": "3 Yr"},
    {"value": "5y",   "label": "5 Yr"},
    {"value": "ytd",  "label": "YTD"},
    {"value": "all",  "label": "All"},
]

# Linkage modes:
#   any    — any rad-onc contact within the window counts (default — measures
#            total rad-onc penetration among med-onc patients, including
#            co-referrals from PCP, pre-existing rad-onc patients, etc.)
#   medonc — only rad-onc referrals whose source is Medical Oncology count
#            (measures actual med-onc → rad-onc referral flow; stricter).
_LINK_MODES = [
    {"value": "any",    "label": "Any Rad-Onc Contact"},
    {"value": "medonc", "label": "Referred by Med-Onc"},
]


def _linkage_window_panel():
    """Dropdown panel with two sliders for the rad-onc linkage window."""
    return html.Div(
        style={"position": "relative", "display": "inline-block"},
        children=[
            dmc.Button(
                id=f"{PAGE_ID}-linkwin-trigger",
                children=[
                    "Linkage Window:  ",
                    dmc.Text(
                        id=f"{PAGE_ID}-linkwin-label",
                        span=True, fw=600, c=PRIMARY, size="xs",
                        children=f"-{_DEFAULT_PRE_DAYS}d / +10yr",
                    ),
                ],
                variant="default", size="sm",
                rightSection=DashIconify(icon="mdi:chevron-down", width=14),
            ),
            dmc.Paper(
                id=f"{PAGE_ID}-linkwin-panel",
                p="sm", shadow="md", withBorder=True, radius="md",
                className="wf-chip-dropdown",
                style={"display": "none", "minWidth": "320px"},
                children=[
                    dmc.Text(
                        "Rad-Onc contact is \"linked\" to a med-onc referral if it falls "
                        "within this window around the med-onc referral date.",
                        size="xs", c=NEUTRAL["text_muted"], mb="xs",
                    ),
                    dmc.Box(mb=32, children=[
                        dmc.Group(justify="space-between", children=[
                            dmc.Text("Days Before Med-Onc Referral", size="xs", c="#6B7280"),
                            dmc.Text(
                                f"{_DEFAULT_PRE_DAYS}d",
                                id=f"{PAGE_ID}-linkwin-pre-val",
                                size="xs", fw=600, c=PRIMARY,
                            ),
                        ]),
                        dmc.Slider(
                            id=f"{PAGE_ID}-linkwin-pre",
                            min=0, max=180, step=10,
                            value=_DEFAULT_PRE_DAYS,
                            size="xs", color="violet",
                            marks=[{"value": v, "label": f"{v}d"} for v in (0, 60, 120, 180)],
                            styles={"markLabel": {"fontSize": "11px", "color": "#9CA3AF", "marginTop": "4px"}},
                        ),
                    ]),
                    dmc.Box(mb=24, children=[
                        dmc.Group(justify="space-between", children=[
                            dmc.Text("Days After Med-Onc Referral", size="xs", c="#6B7280"),
                            dmc.Text(
                                "10yr",
                                id=f"{PAGE_ID}-linkwin-post-val",
                                size="xs", fw=600, c=PRIMARY,
                            ),
                        ]),
                        dmc.Slider(
                            id=f"{PAGE_ID}-linkwin-post",
                            min=90, max=3650, step=30,
                            value=_DEFAULT_POST_DAYS,
                            size="xs", color="violet",
                            marks=[
                                {"value": 365,  "label": "1yr"},
                                {"value": 1095, "label": "3yr"},
                                {"value": 1825, "label": "5yr"},
                                {"value": 3650, "label": "10yr"},
                            ],
                            styles={"markLabel": {"fontSize": "11px", "color": "#9CA3AF", "marginTop": "4px"}},
                        ),
                    ]),
                ],
            ),
        ],
    )


def _build_filter_bar():
    return dmc.Paper(
        children=[
            dmc.Group(
                gap="lg", wrap="wrap", align="center",
                children=[
                    dmc.Group(gap=8, align="center", children=[
                        dmc.Text("Cohort Period", size="xs", c=NEUTRAL["text_secondary"], fw=500),
                        dmc.SegmentedControl(
                            id=f"{PAGE_ID}-filter-date",
                            data=_DATE_PRESETS,
                            value="24mo", size="sm",
                        ),
                    ]),
                    dmc.Group(gap=8, align="center", children=[
                        dmc.Text("Linkage", size="xs", c=NEUTRAL["text_secondary"], fw=500),
                        dmc.SegmentedControl(
                            id=f"{PAGE_ID}-filter-linkmode",
                            data=_LINK_MODES,
                            value="any", size="sm",
                        ),
                    ]),
                    # Med-Onc Site: compact button + chip popover so multiple
                    # selections collapse to "N sites" instead of growing the
                    # control width. Same pattern as the OTV-audit physician
                    # filter — opens via the shared wf-chip-dropdown CSS/JS.
                    dmc.Group(gap=8, align="center", children=[
                        dmc.Text("Med-Onc Site", size="xs", c=NEUTRAL["text_secondary"], fw=500),
                        html.Div(
                            style={"position": "relative", "display": "inline-block"},
                            children=[
                                html.Div(
                                    style={"position": "relative", "display": "inline-block"},
                                    children=[
                                        dmc.Button(
                                            "All Sites",
                                            id=f"{PAGE_ID}-site-trigger",
                                            variant="default", size="sm",
                                            rightSection=DashIconify(icon="mdi:chevron-down", width=14),
                                        ),
                                        dmc.ActionIcon(
                                            DashIconify(icon="mdi:close-circle", width=18),
                                            id=f"{PAGE_ID}-site-clear",
                                            variant="subtle", color="gray", size="sm",
                                            className="wf-filter-clear-btn",
                                            style={"display": "none"},
                                        ),
                                    ],
                                ),
                                dmc.Paper(
                                    children=[
                                        dmc.CheckboxGroup(
                                            id=f"{PAGE_ID}-filter-site",
                                            value=[],
                                            children=dmc.Stack(
                                                gap=4,
                                                children=[
                                                    dmc.Checkbox(
                                                        label=s, value=s,
                                                        size="sm",
                                                        color="violet",
                                                    )
                                                    for s in _SITES
                                                ],
                                            ),
                                        ),
                                    ],
                                    p="sm", shadow="md", withBorder=True, radius="md",
                                    className="wf-chip-dropdown",
                                    style={"display": "none", "minWidth": "180px"},
                                ),
                            ],
                        ),
                    ]),
                    diagnosis_accordion(PAGE_ID),
                    # Note: outlier panel covers only the scheduling-workflow
                    # transitions. The Appt → Rad-Onc Ref window is owned by
                    # the Linkage Window panel (post-days), which already
                    # serves as the effective upper bound there.
                    outlier_panel(PAGE_ID, transitions=[
                        ("Created → Scheduled",              _CAP_CREATED_TO_SCHED),
                        ("Scheduled → Med-Onc Appt",         _CAP_SCHED_TO_APPT),
                    ], slider_max=_OUTLIER_SLIDER_MAX),
                    _linkage_window_panel(),
                ],
            ),
        ],
        p="sm", px="md", radius="md", shadow="xs", withBorder=True,
    )


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------

layout = dmc.Stack(
    gap=16,
    className="page-content",
    children=[
        dmc.Box(
            className="page-sticky-header",
            children=[
                dmc.Title("Referrals (MedOnc)", order=2, className="page-title"),
                _build_filter_bar(),
            ],
        ),

        # KPI row
        dmc.Grid(
            id=f"{PAGE_ID}-kpi-row",
            gutter=16,
            children=[
                dmc.GridCol(kpi_placeholder(), span={"base": 12, "sm": 6, "md": 2.4}) for _ in range(5)
            ],
        ),

        # Flow Gantt — full-width pathway visualization
        dcc.Store(id=f"{PAGE_ID}-store-flow-gantt"),
        dcc.Store(id=f"{PAGE_ID}-store-flow-details"),
        dcc.Store(id=f"{PAGE_ID}-store-selected-flow", data=None),
        dcc.Store(id=f"{PAGE_ID}-flow-gantt-trigger"),
        dmc.Paper(
            children=[
                dmc.Text("Med-Onc → Rad-Onc Pathway", size="sm", fw=500,
                         c=NEUTRAL["text_secondary"], mb="sm"),
                html.Div(
                    id=f"{PAGE_ID}-flow-gantt",
                    style={
                        "width": "100%",
                        "aspectRatio": "2.45 / 1",
                        "minHeight": "340px",
                        "maxHeight": "480px",
                    },
                ),
            ],
            p="md", radius="md", shadow="xs", withBorder=True,
        ),

        # Companion charts driven by selected gantt band
        dmc.Grid(gutter="md", children=[
            dmc.GridCol(
                span={"base": 12, "md": 4},
                children=dmc.Paper(
                    p="sm", radius="md", shadow="xs", withBorder=True,
                    children=[
                        dmc.Group(justify="space-between", mb=8, children=[
                            dmc.Text(
                                id=f"{PAGE_ID}-dist-title",
                                children="Duration Distribution",
                                size="sm", fw=500, c=NEUTRAL["text_secondary"],
                            ),
                            dmc.Group(gap="xs", align="center", wrap="nowrap", children=[
                                dmc.SegmentedControl(
                                    id=f"{PAGE_ID}-dist-type",
                                    data=[
                                        {"value": "density", "label": "Density"},
                                        {"value": "histogram", "label": "Histogram"},
                                    ],
                                    value="density", size="xs",
                                ),
                                chart_settings_popover(
                                    f"{PAGE_ID}-dist",
                                    chart_types=None,
                                    show_smooth=True,
                                    smooth_min=0, smooth_max=10, smooth_step=0.5,
                                    smooth_default=1.5,
                                    slider_label="Bandwidth",
                                    show_grouping=False,
                                ),
                            ]),
                        ]),
                        dcc.Graph(
                            id=f"{PAGE_ID}-flow-dist",
                            config={"displayModeBar": False, "responsive": True},
                            style={"height": "340px"},
                        ),
                    ],
                ),
            ),
            dmc.GridCol(
                span={"base": 12, "md": 4},
                children=dmc.Paper(
                    p="sm", radius="md", shadow="xs", withBorder=True,
                    children=[
                        dmc.Group(justify="space-between", mb=8, children=[
                            dmc.Text(
                                id=f"{PAGE_ID}-trend-title",
                                children="Duration Trend",
                                size="sm", fw=500, c=NEUTRAL["text_secondary"],
                            ),
                            dmc.Group(gap="xs", align="center", wrap="nowrap", children=[
                                dmc.SegmentedControl(
                                    id=f"{PAGE_ID}-trend-agg",
                                    data=[
                                        {"value": "W", "label": "Weekly"},
                                        {"value": "M", "label": "Monthly"},
                                        {"value": "Y", "label": "Yearly"},
                                    ],
                                    value="M", size="xs",
                                ),
                                chart_settings_popover(
                                    f"{PAGE_ID}-trend",
                                    chart_types=[
                                        {"value": "line", "label": "Line"},
                                        {"value": "area", "label": "Area"},
                                        {"value": "bar", "label": "Bar"},
                                    ],
                                    chart_type_default="bar",
                                    show_smooth=True, smooth_max=12, smooth_default=2,
                                    slider_label="Smoothing",
                                    show_grouping=False,
                                ),
                            ]),
                        ]),
                        dcc.Graph(
                            id=f"{PAGE_ID}-flow-trend",
                            config={"displayModeBar": False, "responsive": True},
                            style={"height": "340px"},
                        ),
                    ],
                ),
            ),
            dmc.GridCol(
                span={"base": 12, "md": 4},
                children=dmc.Paper(
                    p="sm", radius="md", shadow="xs", withBorder=True,
                    children=[
                        dmc.Group(justify="space-between", mb=8, children=[
                            dmc.Text(
                                id=f"{PAGE_ID}-conv-title",
                                children="Conversion Rate Trend",
                                size="sm", fw=500, c=NEUTRAL["text_secondary"],
                            ),
                            dmc.Group(gap="xs", align="center", wrap="nowrap", children=[
                                dmc.SegmentedControl(
                                    id=f"{PAGE_ID}-conv-agg",
                                    data=[
                                        {"value": "W", "label": "Weekly"},
                                        {"value": "M", "label": "Monthly"},
                                        {"value": "Y", "label": "Yearly"},
                                    ],
                                    value="M", size="xs",
                                ),
                                chart_settings_popover(
                                    f"{PAGE_ID}-conv",
                                    chart_types=[
                                        {"value": "line", "label": "Line"},
                                        {"value": "area", "label": "Area"},
                                        {"value": "bar", "label": "Bar"},
                                    ],
                                    chart_type_default="line",
                                    show_smooth=True, smooth_max=12, smooth_default=0,
                                    slider_label="Smoothing",
                                    show_grouping=False,
                                ),
                            ]),
                        ]),
                        dcc.Graph(
                            id=f"{PAGE_ID}-flow-conv",
                            config={"displayModeBar": False, "responsive": True},
                            style={"height": "340px"},
                        ),
                    ],
                ),
            ),
        ]),

        # Diagnosis (tall, left) + Site conversion / KM curve stacked on right.
        # Dx graph is exactly 2x the right-column card height so the two
        # columns align; right column stacks Site on top of KM with the
        # same 16px gutter.
        dmc.Grid(gutter=16, align="flex-start", children=[
            dmc.GridCol(
                span={"base": 12, "md": 6},
                children=dmc.Paper(
                    children=[
                        dmc.Text("Rad-Onc Conversion by Diagnosis", size="sm", fw=500,
                                 c=NEUTRAL["text_secondary"], mb=6),
                        # Graph height = 2 × right-side graph (400px) + 16px
                        # stack gutter + one-card-chrome delta so the Dx
                        # chart visually spans both right-column cards.
                        dcc.Graph(id=f"{PAGE_ID}-dx-conversion", config=DEFAULT_GRAPH_CONFIG,
                                  style={"height": "852px"}),
                    ],
                    pt="sm", px="md", pb=4, radius="md", shadow="xs", withBorder=True,
                    style={"height": "896px"},
                ),
            ),
            dmc.GridCol(
                span={"base": 12, "md": 6},
                children=dmc.Stack(gap=16, children=[
                    dmc.Paper(
                        children=[
                            dmc.Text("Conversion by Med-Onc Site", size="sm", fw=500,
                                     c=NEUTRAL["text_secondary"], mb=6),
                            dcc.Graph(id=f"{PAGE_ID}-site-conversion", config=DEFAULT_GRAPH_CONFIG,
                                      style={"height": "415px"}),
                        ],
                        pt="sm", px="md", pb=4, radius="md", shadow="xs", withBorder=True,
                        style={"height": "440px"},
                    ),
                    dmc.Paper(
                        children=[
                            dmc.Text("Cumulative Rad-Onc Contact Over Time (by Diagnosis)",
                                     size="sm", fw=500, c=NEUTRAL["text_secondary"], mb=6),
                            dcc.Graph(id=f"{PAGE_ID}-km-curve", config=DEFAULT_GRAPH_CONFIG,
                                      style={"height": "396px"}),
                        ],
                        pt="sm", px="md", pb=8, radius="md", shadow="xs", withBorder=True,
                        style={"height": "440px"},
                    ),
                ]),
            ),
        ]),

        # Referring source cross-tab
        dmc.Paper(
            children=[
                dmc.Group(justify="space-between", align="center", mb=6, children=[
                    dmc.Text("Referring Source Cross-Tab — of Patients Seen by Med-Onc, "
                             "What Fraction Reached Rad-Onc",
                             size="sm", fw=500, c=NEUTRAL["text_secondary"]),
                    dmc.Text("Ordered by Volume, Minimum 5 Patients Seen",
                             size="xs", c=NEUTRAL["text_muted"]),
                ]),
                html.Div(id=f"{PAGE_ID}-source-table"),
            ],
            p="sm", px="md", radius="md", shadow="xs", withBorder=True,
        ),

        # Patient-level detail table
        dmc.Paper(
            children=[
                dmc.Text("Patient Detail (One Row per MRN)",
                         size="sm", fw=500, c=NEUTRAL["text_secondary"], mb=6),
                html.Div(id=f"{PAGE_ID}-detail-table"),
            ],
            p="sm", px="md", radius="md", shadow="xs", withBorder=True,
        ),
    ],
)


# Register diagnosis accordion callbacks (must follow layout)
register_diagnosis_callbacks(PAGE_ID)


# --- Med-Onc Site filter: trigger label & clear-button wiring ---------------
clientside_callback(
    """function(val) {
        if (!val || val.length === 0) return "All Sites";
        if (val.length === 1) return val[0];
        return val.length + " sites";
    }""",
    Output(f"{PAGE_ID}-site-trigger", "children"),
    Input(f"{PAGE_ID}-filter-site", "value"),
)

clientside_callback(
    """function(val) {
        return (val && val.length > 0) ? {"display": "inline-flex"} : {"display": "none"};
    }""",
    Output(f"{PAGE_ID}-site-clear", "style"),
    Input(f"{PAGE_ID}-filter-site", "value"),
)

clientside_callback(
    """function(n) { return []; }""",
    Output(f"{PAGE_ID}-filter-site", "value", allow_duplicate=True),
    Input(f"{PAGE_ID}-site-clear", "n_clicks"),
    prevent_initial_call=True,
)


register_outlier_callbacks(
    PAGE_ID, n_transitions=2,
    defaults=[_CAP_CREATED_TO_SCHED, _CAP_SCHED_TO_APPT],
)

# Wire gear-icon panel toggle + PNG export for the three companion charts
# under the Flow Gantt (same wiring the rad-onc Referrals page uses).
register_chart_callbacks([
    (f"{PAGE_ID}-dist",  f"{PAGE_ID}-flow-dist"),
    {"sid": f"{PAGE_ID}-trend", "gid": f"{PAGE_ID}-flow-trend",
     "store_id": True, "show_grouping": False},
    {"sid": f"{PAGE_ID}-conv",  "gid": f"{PAGE_ID}-flow-conv",
     "store_id": True, "show_grouping": False},
])


# ---------------------------------------------------------------------------
# Linkage window label updaters
# ---------------------------------------------------------------------------

@callback(
    Output(f"{PAGE_ID}-linkwin-pre-val", "children"),
    Input(f"{PAGE_ID}-linkwin-pre", "value"),
)
def _update_pre_label(v):
    return f"{v}d"


@callback(
    Output(f"{PAGE_ID}-linkwin-post-val", "children"),
    Input(f"{PAGE_ID}-linkwin-post", "value"),
)
def _update_post_label(v):
    return _fmt_days(v)


def _fmt_days(d):
    """Render day counts compactly — use years for long windows."""
    if d is None:
        return ""
    if d >= 365:
        yrs = d / 365
        return f"{yrs:.1f}yr".replace(".0yr", "yr")
    return f"{d}d"


@callback(
    Output(f"{PAGE_ID}-linkwin-label", "children"),
    Input(f"{PAGE_ID}-linkwin-pre", "value"),
    Input(f"{PAGE_ID}-linkwin-post", "value"),
)
def _update_linkwin_button(pre, post):
    return f"-{_fmt_days(pre)} / +{_fmt_days(post)}"


# ---------------------------------------------------------------------------
# Main update callback
# ---------------------------------------------------------------------------

@callback(
    Output(f"{PAGE_ID}-kpi-row", "children"),
    Output(f"{PAGE_ID}-store-flow-gantt", "data"),
    Output(f"{PAGE_ID}-store-flow-details", "data"),
    Output(f"{PAGE_ID}-dx-conversion", "figure"),
    Output(f"{PAGE_ID}-site-conversion", "figure"),
    Output(f"{PAGE_ID}-km-curve", "figure"),
    Output(f"{PAGE_ID}-source-table", "children"),
    Output(f"{PAGE_ID}-detail-table", "children"),
    Input(f"{PAGE_ID}-filter-date", "value"),
    Input(f"{PAGE_ID}-filter-site", "value"),
    Input(f"{PAGE_ID}-diag-store", "data"),
    Input(f"{PAGE_ID}-diag-mode", "data"),
    Input(f"{PAGE_ID}-linkwin-pre", "value"),
    Input(f"{PAGE_ID}-linkwin-post", "value"),
    Input(f"{PAGE_ID}-outlier-cap-0", "value"),
    Input(f"{PAGE_ID}-outlier-cap-1", "value"),
    Input(f"{PAGE_ID}-outlier-enabled", "data"),
    Input(f"{PAGE_ID}-filter-linkmode", "value"),
)
def _update_all(date_preset, site_filter, diag_cats, diag_mode, pre_days, post_days,
                cap_0, cap_1, outliers_enabled, link_mode):
    cohort = _build_cohort(
        date_preset, site_filter or [],
        diag_cats or [], diag_mode or "primary",
        pre_days, post_days,
        link_mode or "any",
    )

    if cohort.empty:
        placeholders = [
            dmc.GridCol(kpi_placeholder(), span={"base": 12, "sm": 6, "md": 2.4}) for _ in range(5)
        ]
        empty = empty_figure("No Data for Current Filters")
        return (placeholders, None, None, empty, empty, empty,
                html.Div(), html.Div())

    # When outlier filtering is disabled, use very permissive caps so
    # effectively no values are clipped. The Appt → Rad-Onc Ref cap is
    # the linkage-window post-days value — that's the bound we already
    # use elsewhere to decide whether a rad-onc contact counts as linked,
    # so it doubles as the duration cap here.
    if outliers_enabled is False:
        cap_0, cap_1 = 10_000, 10_000
    else:
        cap_0 = cap_0 or _CAP_CREATED_TO_SCHED
        cap_1 = cap_1 or _CAP_SCHED_TO_APPT
    cap_2 = int(post_days) if post_days is not None else _CAP_APPT_TO_RADREF

    return (
        _build_kpis(cohort),
        _compute_medonc_flow_data(cohort, cap_0, cap_1, cap_2),
        _compute_medonc_flow_details(cohort, cap_0, cap_1, cap_2),
        _build_dx_conversion(cohort),
        _build_site_conversion(cohort),
        _build_km_curve(cohort, post_days),
        _build_source_table(cohort),
        _build_detail_table(cohort),
    )


# ---------------------------------------------------------------------------
# KPI builders
# ---------------------------------------------------------------------------

def _build_kpis(cohort):
    """KPIs. Rad-onc conversion percentages are denominated by "Seen By
    Med-Onc" — the clinically meaningful base (patients never seen by
    med-onc couldn't realistically be referred on to us).
    """
    n = len(cohort)
    n_seen = int(cohort["SeenByMedOnc"].sum())
    seen_mask = cohort["SeenByMedOnc"].astype(bool)
    n_linked = int((cohort["LinkedToRadOnc"] & seen_mask).sum())
    n_tx = int((cohort["LinkedRadTx"] & seen_mask).sum())
    pct_seen = (n_seen / n * 100) if n else 0.0
    pct_linked = (n_linked / n_seen * 100) if n_seen else 0.0
    pct_tx = (n_tx / n_seen * 100) if n_seen else 0.0
    median_days = cohort.loc[seen_mask, "DaysToRadOnc"].dropna().median()
    median_str = f"{median_days:+.0f} d" if pd.notna(median_days) else "—"

    cohort = cohort.copy()
    cohort["_month"] = cohort["Created"].dt.to_period("M").dt.to_timestamp()
    grp = cohort.groupby("_month")
    by_month = grp.size().sort_index().tail(12)
    spark_labels = by_month.index.tolist()
    spark_vals = by_month.values.tolist()

    seen_by_month = grp["SeenByMedOnc"].apply(lambda s: int(s.astype(bool).sum())).reindex(spark_labels, fill_value=0)
    linked_by_month = (
        grp.apply(lambda g: int((g["LinkedToRadOnc"] & g["SeenByMedOnc"].astype(bool)).sum()), include_groups=False)
        .reindex(spark_labels, fill_value=0)
    )
    tx_by_month = (
        grp.apply(lambda g: int((g["LinkedRadTx"] & g["SeenByMedOnc"].astype(bool)).sum()), include_groups=False)
        .reindex(spark_labels, fill_value=0)
    )
    median_by_month = (
        grp.apply(
            lambda g: float(g.loc[g["SeenByMedOnc"].astype(bool), "DaysToRadOnc"].dropna().median()),
            include_groups=False,
        )
        .reindex(spark_labels)
    )
    median_spark = [float(v) if pd.notna(v) else 0.0 for v in median_by_month.tolist()]

    cards = [
        kpi_card("Unique Patients", f"{n:,}",
                 sparkline_past=spark_vals, sparkline_past_labels=spark_labels,
                 accent_color=PRIMARY),
        kpi_card("Seen by Med-Onc", f"{n_seen:,}",
                 value_detail=f"{pct_seen:.0f}% of Referred",
                 sparkline_past=seen_by_month.values.tolist(),
                 sparkline_past_labels=spark_labels),
        kpi_card("Reached Rad-Onc (Any Stage)", f"{n_linked:,}",
                 value_detail=f"{pct_linked:.0f}% of Seen",
                 sparkline_past=linked_by_month.values.tolist(),
                 sparkline_past_labels=spark_labels,
                 accent_color=SEMANTIC_COLORS.get("info", PRIMARY)),
        kpi_card("Treated by Rad-Onc", f"{n_tx:,}",
                 value_detail=f"{pct_tx:.0f}% of Seen",
                 sparkline_past=tx_by_month.values.tolist(),
                 sparkline_past_labels=spark_labels,
                 accent_color=SEMANTIC_COLORS.get("success", "#2ECC71")),
        kpi_card("Median Days → Rad-Onc", median_str,
                 value_detail="(Seen Patients)",
                 sparkline_past=median_spark,
                 sparkline_past_labels=spark_labels),
    ]
    return [dmc.GridCol(c, span={"base": 12, "sm": 6, "md": 2.4}) for c in cards]


# ---------------------------------------------------------------------------
# Chart builders
# ---------------------------------------------------------------------------

def _build_dx_conversion(cohort):
    """Conversion rates by diagnosis — denominator is patients Seen By
    Med-Onc (not total referred) so under-referral by med-onc physicians
    is the thing being measured, not med-onc's own show-rate.

    Shows every diagnosis category present in the cohort (minus Unknown).
    """
    seen = cohort[cohort["SeenByMedOnc"].astype(bool)]
    if seen.empty:
        return empty_figure()
    agg = (
        seen.groupby("DxCategory")
        .agg(n=("MRN", "size"), linked=("LinkedToRadOnc", "sum"),
             treated=("LinkedRadTx", "sum"))
        .reset_index()
    )
    agg = agg[agg["DxCategory"].astype(str) != "Unknown"].sort_values("n", ascending=True)
    if agg.empty:
        return empty_figure("No Diagnosis Data")

    agg["pct_linked"] = agg["linked"] / agg["n"] * 100
    agg["pct_treated"] = agg["treated"] / agg["n"] * 100

    fig = go.Figure()
    # Traces rendered in reverse order: last-added is top of each group, so
    # we add Treated first → Reached sits on top of each bar group. Legend
    # order is controlled separately via legendrank so Reached reads first.
    fig.add_bar(
        y=agg["DxCategory"], x=agg["pct_treated"],
        name="Treated by Rad-Onc",
        orientation="h",
        marker=dict(color=SEMANTIC_COLORS.get("success", "#2ECC71")),
        text=[f"{v:.0f}%" for v in agg["pct_treated"]],
        textposition="outside",
        hovertemplate="%{y}<br>%{x:.1f}%% treated<extra></extra>",
        legendrank=2,
    )
    fig.add_bar(
        y=agg["DxCategory"], x=agg["pct_linked"],
        name="Reached Rad-Onc (Any)",
        orientation="h",
        marker=dict(color=PRIMARY),
        text=[f"{v:.0f}% (n={n})" for v, n in zip(agg["pct_linked"], agg["n"])],
        textposition="outside",
        hovertemplate="%{y}<br>%{x:.1f}%% linked (n=%{customdata})<extra></extra>",
        customdata=agg["n"],
        legendrank=1,
    )
    apply_default_layout(fig)
    fig.update_layout(
        barmode="group",
        xaxis=dict(title="% of Patients Seen by Med-Onc", ticksuffix="%", range=[0, 100]),
        yaxis=dict(title=""),
        margin=dict(l=140, r=40, t=10, b=30),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
    )
    fig.update_xaxes(hoverformat="")
    return fig


def _build_site_conversion(cohort):
    seen = cohort[cohort["SeenByMedOnc"].astype(bool)]
    if seen.empty:
        return empty_figure()
    agg = (
        seen.groupby("ReferredToSite")
        .agg(n=("MRN", "size"), linked=("LinkedToRadOnc", "sum"),
             treated=("LinkedRadTx", "sum"))
        .reset_index()
    )
    agg = agg[agg["ReferredToSite"].isin(_SITES)]
    if agg.empty:
        return empty_figure()
    agg["pct_linked"] = agg["linked"] / agg["n"] * 100
    agg["pct_treated"] = agg["treated"] / agg["n"] * 100
    order = {s: i for i, s in enumerate(_SITES)}
    agg = agg.sort_values("ReferredToSite", key=lambda s: s.map(order))

    fig = go.Figure()
    fig.add_bar(
        x=agg["ReferredToSite"], y=agg["pct_linked"],
        name="Reached Rad-Onc (Any)",
        marker=dict(color=[_SITE_COLORS[s] for s in agg["ReferredToSite"]]),
        text=[f"{v:.0f}%<br><span style='font-size:10px;color:#94a3b8'>n={n}</span>"
              for v, n in zip(agg["pct_linked"], agg["n"])],
        textposition="outside",
        hovertemplate="%{x}<br>%{y:.1f}%% Linked (n=%{customdata})<extra></extra>",
        customdata=agg["n"],
    )
    fig.add_bar(
        x=agg["ReferredToSite"], y=agg["pct_treated"],
        name="Treated by Rad-Onc",
        marker=dict(color=[_SITE_COLORS[s] for s in agg["ReferredToSite"]], pattern=dict(shape="/")),
        opacity=0.55,
        text=[f"{v:.0f}%" for v in agg["pct_treated"]],
        textposition="outside",
        hovertemplate="%{x}<br>%{y:.1f}%% Treated<extra></extra>",
    )
    apply_default_layout(fig)
    fig.update_layout(
        barmode="group",
        xaxis=dict(title=""),
        yaxis=dict(title="% of Patients Seen by Med-Onc", ticksuffix="%", range=[0, 100]),
        margin=dict(l=50, r=20, t=10, b=20),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
    )
    fig.update_xaxes(hoverformat="")
    return fig


# ---------------------------------------------------------------------------
# Kaplan-Meier cumulative-incidence curve
# ---------------------------------------------------------------------------

def _km_estimator(times, events):
    """Simple Kaplan-Meier survival estimator. Returns (t, S) arrays with a
    step at each event time, starting from (0, 1). Cumulative incidence is
    1 - S. No confidence intervals — this is a compact descriptive view."""
    times = np.asarray(times, dtype=float)
    events = np.asarray(events, dtype=int)
    order = np.argsort(times)
    times = times[order]
    events = events[order]
    if len(times) == 0:
        return np.array([0.0]), np.array([1.0])

    unique_event_times = np.unique(times[events == 1])
    t_out = [0.0]
    S_out = [1.0]
    S = 1.0
    for t in unique_event_times:
        at_risk = int(np.sum(times >= t))
        d = int(np.sum((times == t) & (events == 1)))
        if at_risk > 0:
            S *= (1.0 - d / at_risk)
        t_out.append(float(t))
        S_out.append(S)
    # Extend the last step out to max observed time so the line doesn't
    # terminate early just because the final event happened before the
    # longest-followed patient's censor time.
    if times.max() > t_out[-1]:
        t_out.append(float(times.max()))
        S_out.append(S)
    return np.array(t_out), np.array(S_out)


def _build_km_curve(cohort, post_days):
    """Kaplan-Meier cumulative-incidence curves of rad-onc contact by
    diagnosis. X axis is days from med-onc referral, Y is cumulative % of
    patients who reached rad-onc. Non-linked patients are censored at
    min(data_max - their referral date, post_days window).
    """
    if cohort.empty:
        return empty_figure()
    seen = cohort[cohort["SeenByMedOnc"].astype(bool)].copy()
    if seen.empty:
        return empty_figure()

    cap_days = int(post_days) if post_days is not None else _DEFAULT_POST_DAYS
    data_max = seen["Created"].max()
    censor_days = (data_max - seen["Created"]).dt.days.clip(lower=0, upper=cap_days)

    event = seen["LinkedToRadOnc"].astype(bool).astype(int)
    # Use days-to-event for linked patients (clipped to window), censor time
    # otherwise. DaysToRadOnc can be negative (rad-onc preceded med-onc) —
    # treat those as event-at-day-0 for this cumulative view.
    days_event = pd.to_numeric(seen["DaysToRadOnc"], errors="coerce").clip(lower=0, upper=cap_days)
    days = days_event.where(event == 1, censor_days)

    mask = days.notna() & (days >= 0)
    seen = seen.loc[mask]
    days = days.loc[mask]
    event = event.loc[mask]
    if seen.empty:
        return empty_figure()

    # Top diagnoses with enough N for a meaningful curve.
    MIN_DX_N = 20
    dx_counts = seen["DxCategory"].value_counts()
    top_dx = [d for d in dx_counts.index
              if str(d) not in ("Unknown", "nan") and dx_counts[d] >= MIN_DX_N][:6]

    fig = go.Figure()
    palette = ["#7C2A83", "#2196F3", "#F44336", "#4CAF50", "#F59E0B", "#0891B2"]
    for i, dx in enumerate(top_dx):
        m = (seen["DxCategory"] == dx).values
        t, S = _km_estimator(days[m].values, event[m].values)
        n = int(m.sum())
        fig.add_scatter(
            x=t, y=(1 - S) * 100,
            mode="lines", name=f"{dx} (n={n})",
            line=dict(color=palette[i % len(palette)], width=2, shape="hv"),
            hovertemplate="Day %{x:.0f}<br>%{y:.1f}% Reached Rad-Onc<extra></extra>",
        )

    t, S = _km_estimator(days.values, event.values)
    fig.add_scatter(
        x=t, y=(1 - S) * 100,
        mode="lines", name=f"All (n={len(seen)})",
        line=dict(color=NEUTRAL["text_muted"], width=1.5, dash="dash", shape="hv"),
        hovertemplate="Day %{x:.0f}<br>%{y:.1f}% Reached Rad-Onc<extra></extra>",
    )

    apply_default_layout(fig)
    fig.update_layout(
        xaxis=dict(title="Days From Med-Onc Referral", range=[0, cap_days]),
        yaxis=dict(title="% Reached Rad-Onc (Cumulative)", ticksuffix="%", range=[0, 100]),
        margin=dict(l=50, r=20, t=10, b=40),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        hovermode="x unified",
    )
    fig.update_xaxes(hoverformat="")
    return fig


# ---------------------------------------------------------------------------
# Tables
# ---------------------------------------------------------------------------

def _build_source_table(cohort):
    """Referring-department cross-tab. Denominator is patients seen by
    med-onc (not total referrals) to align with the page's primary
    denominator convention — isolates rad-onc referral rate from
    med-onc's show-rate per source."""
    if cohort.empty or "Referred by Department" not in cohort.columns:
        return html.Div()
    seen = cohort[cohort["SeenByMedOnc"].astype(bool)]
    if seen.empty:
        return html.Div()
    MIN_N = 5
    agg = (
        seen.groupby("Referred by Department", dropna=True)
        .agg(n=("MRN", "size"), linked=("LinkedToRadOnc", "sum"),
             treated=("LinkedRadTx", "sum"))
        .reset_index()
    )
    agg = agg[agg["n"] >= MIN_N].copy()
    if agg.empty:
        return html.Div(dmc.Text("No Referring Departments Meet the Minimum Threshold.",
                                 size="sm", c=NEUTRAL["text_muted"]))
    agg["pct_linked"] = (agg["linked"] / agg["n"] * 100).round(1)
    agg["pct_treated"] = (agg["treated"] / agg["n"] * 100).round(1)
    agg = agg.sort_values("n", ascending=False).rename(columns={
        "Referred by Department": "Referring Department",
        "n": "Patients",
        "linked": "Reached Rad-Onc",
        "treated": "Treated",
        "pct_linked": "% Linked",
        "pct_treated": "% Treated",
    })
    column_defs = [
        {"field": "Referring Department", "flex": 2, "minWidth": 220},
        {"field": "Patients", "type": "numericColumn", "width": 110},
        {"field": "Reached Rad-Onc", "type": "numericColumn", "width": 140},
        {"field": "% Linked", "type": "numericColumn", "width": 110,
         "valueFormatter": {"function": "params.value != null ? params.value.toFixed(0) + '%' : '–'"}},
        {"field": "Treated", "type": "numericColumn", "width": 110},
        {"field": "% Treated", "type": "numericColumn", "width": 110,
         "valueFormatter": {"function": "params.value != null ? params.value.toFixed(0) + '%' : '–'"}},
    ]
    return dag.AgGrid(
        id=f"{PAGE_ID}-source-grid",
        rowData=agg.to_dict("records"),
        columnDefs=column_defs,
        defaultColDef=DEFAULT_COLUMN_DEFS,
        dashGridOptions={**DEFAULT_GRID_OPTIONS, "pagination": True, "paginationPageSize": 15,
                         "domLayout": "autoHeight"},
        className=DEFAULT_GRID_CLASS,
        style={"width": "100%"},
    )


def _build_detail_table(cohort):
    if cohort.empty:
        return html.Div()
    cols = ["MRN", "Patient Name", "Created", "ReferredToSite", "DxCategory",
            "Onc Dx", "Referred by Department", "Referred by Provider",
            "SeenByMedOnc",
            "RadOncReferralCreated", "RadOncFirstAppt", "RadOncTreatmentStart",
            "DaysToRadOnc", "LinkedToRadOnc"]
    cols = [c for c in cols if c in cohort.columns]
    view = cohort[cols].copy()

    for c in ["Created", "RadOncReferralCreated", "RadOncFirstAppt", "RadOncTreatmentStart"]:
        if c in view.columns:
            view[c] = pd.to_datetime(view[c], errors="coerce").dt.strftime("%Y-%m-%d")
    if "DaysToRadOnc" in view.columns:
        view["DaysToRadOnc"] = view["DaysToRadOnc"].round(0)
    view = view.sort_values("Created", ascending=False)

    rename = {
        "Patient Name": "Patient",
        "Created": "Med-Onc Ref",
        "ReferredToSite": "Site",
        "DxCategory": "Dx Cat",
        "Onc Dx": "Onc Diagnosis",
        "Referred by Department": "Referred by Dept",
        "Referred by Provider": "Referred by Provider",
        "SeenByMedOnc": "Seen by Med-Onc",
        "RadOncReferralCreated": "Rad-Onc Ref",
        "RadOncFirstAppt": "Rad-Onc Consult",
        "RadOncTreatmentStart": "Rad-Onc Tx Start",
        "DaysToRadOnc": "Days → Rad-Onc",
        "LinkedToRadOnc": "Linked",
    }
    view = view.rename(columns=rename)

    column_defs = []
    for field in view.columns:
        col = {"field": field, "minWidth": 110}
        if field in ("MRN", "Days → Rad-Onc"):
            col["type"] = "numericColumn"
            col["width"] = 130
        elif field in ("Linked", "Seen by Med-Onc"):
            col["width"] = 120
            col["cellRenderer"] = "CheckBool"
        elif field == "Patient":
            col["minWidth"] = 180
        elif field == "Onc Diagnosis":
            col["minWidth"] = 260
        elif field == "Referred by Dept":
            col["minWidth"] = 200
        column_defs.append(col)

    return dag.AgGrid(
        id=f"{PAGE_ID}-detail-grid",
        rowData=view.to_dict("records"),
        columnDefs=column_defs,
        defaultColDef=DEFAULT_COLUMN_DEFS,
        dashGridOptions={**DEFAULT_GRID_OPTIONS, "pagination": True, "paginationPageSize": 25,
                         "domLayout": "autoHeight"},
        className=DEFAULT_GRID_CLASS,
        style={"width": "100%"},
    )




# ---------------------------------------------------------------------------
# Flow-Gantt clientside callbacks — reuse the shared flow_gantt.js renderers
# via thin wrappers defined in medonc_flow_gantt.js that supply defaults for
# compare-mode / KM args this page doesn't use.
# ---------------------------------------------------------------------------

# Hidden div to absorb the trend renderer's third "maturity style" output.
layout.children.append(html.Div(id=f"{PAGE_ID}-trend-maturity", style={"display": "none"}))

# Main gantt
clientside_callback(
    ClientsideFunction(namespace="medoncFlowGantt", function_name="render"),
    Output(f"{PAGE_ID}-flow-gantt-trigger", "data"),
    Input(f"{PAGE_ID}-store-flow-gantt", "data"),
)

# Distribution
clientside_callback(
    ClientsideFunction(namespace="medoncFlowGantt", function_name="renderDist"),
    Output(f"{PAGE_ID}-flow-dist", "figure"),
    Output(f"{PAGE_ID}-dist-title", "children"),
    Input(f"{PAGE_ID}-store-flow-details", "data"),
    Input(f"{PAGE_ID}-store-selected-flow", "data"),
    Input(f"{PAGE_ID}-dist-type", "value"),
    Input(f"{PAGE_ID}-dist-settings-smooth", "value"),
    prevent_initial_call=True,
)

# Duration trend
clientside_callback(
    ClientsideFunction(namespace="medoncFlowGantt", function_name="renderTrend"),
    Output(f"{PAGE_ID}-flow-trend", "figure"),
    Output(f"{PAGE_ID}-trend-title", "children"),
    Output(f"{PAGE_ID}-trend-maturity", "style"),
    Input(f"{PAGE_ID}-store-flow-details", "data"),
    Input(f"{PAGE_ID}-store-selected-flow", "data"),
    Input(f"{PAGE_ID}-trend-settings-smooth", "value"),
    Input(f"{PAGE_ID}-trend-settings-type", "value"),
    Input(f"{PAGE_ID}-trend-agg", "value"),
    prevent_initial_call=True,
)

# Conversion rate trend
clientside_callback(
    ClientsideFunction(namespace="medoncFlowGantt", function_name="renderConv"),
    Output(f"{PAGE_ID}-flow-conv", "figure"),
    Output(f"{PAGE_ID}-conv-title", "children"),
    Input(f"{PAGE_ID}-store-flow-details", "data"),
    Input(f"{PAGE_ID}-store-selected-flow", "data"),
    Input(f"{PAGE_ID}-conv-agg", "value"),
    Input(f"{PAGE_ID}-conv-settings-type", "value"),
    Input(f"{PAGE_ID}-conv-settings-smooth", "value"),
    prevent_initial_call=True,
)
