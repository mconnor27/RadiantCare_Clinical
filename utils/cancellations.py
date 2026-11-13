"""Shared cancellation analytics for the Simulations and Clinic Visits pages.

Both feeds carry the same slot-recovery columns on cancelled / no-show rows:

    CancelledDateTime   when the appointment was cancelled
    CancelLeadHours     hours of notice (scheduled start - cancelled time);
                        negative = cancelled after the slot started (no-show)
    SlotOutcome         what happened to the vacated slot (see below)
    SlotRefilledPct     % of the slot's minutes re-booked by another patient
    SlotIdleMinutes     minutes of the slot no patient used ("Lost" in the UI)
    Next*AfterCancel    the same patient's next appointment of that kind
                        (NextSimAfterCancel / NextVisitAfterCancel)

SlotOutcome groups:
    Vacated    — Refilled / Partially refilled / Not refilled. The only
                 outcomes where refill % is meaningful.
    No-show    — patient never arrived; slot is unrecoverable.
    No loss    — Same patient re-booked / Shared slot / Simmed|Seen same day.
                 The cancellation didn't actually vacate capacity.
    Upcoming   — Open - future slot: cancelled, slot date hasn't arrived yet.
"""

from __future__ import annotations

import re

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from config.settings import PRIMARY, SEMANTIC_COLORS
from utils.charts import apply_default_layout, empty_figure, full_period_range

CANCEL_METRICS = [
    {"value": "rate", "label": "Rate"},
    {"value": "notice", "label": "Notice"},
    {"value": "refill", "label": "Refill"},
    {"value": "rebook", "label": "Rebook"},
    {"value": "idle", "label": "Lost"},
]

_METRIC_META = {
    "rate":   {"yTitle": "Cancellation Rate (%)", "total": "Cancel Rate"},
    "notice": {"yTitle": "Median Notice (days)", "total": "Median Notice"},
    "refill": {"yTitle": "Slot Time Refilled (%)", "total": "Refilled"},
    "rebook": {"yTitle": "Patients Rebooked (%)", "total": "Rebooked"},
    "idle":   {"yTitle": "Lost Slot Hours", "total": "Lost Hours"},
}

LOST_OUTCOMES = frozenset({"Refilled", "Partially refilled", "Not refilled"})
NO_LOSS_OUTCOMES = frozenset({
    "Same patient re-booked", "Shared slot", "Simmed same day", "Seen same day",
})
PENDING_OUTCOME = "Open - future slot"
NO_SHOW_OUTCOME = "No-show"

# Notice buckets (x-axis of the breakdown chart). Edges are user-editable
# tags like "4h", "2d", "1w"; a bare number means hours.
NO_SHOW_BUCKET = "No-Show"
DEFAULT_NOTICE_EDGES = ("24h", "3d", "7d")
NOTICE_EDGE_SUGGESTIONS = ["1h", "2h", "4h", "8h", "12h", "24h", "48h",
                           "3d", "5d", "7d", "14d", "30d"]
# unit alias → (canonical unit, hours per unit)
_UNITS = {}
for _names, _canon, _hrs in [
    (("m", "min", "mins", "minute", "minutes"), "min", 1 / 60),
    (("", "h", "hr", "hrs", "hour", "hours"), "hr", 1),
    (("d", "day", "days"), "day", 24),
    (("w", "wk", "wks", "week", "weeks"), "week", 168),
]:
    for _n in _names:
        _UNITS[_n] = (_canon, _hrs)
_UNIT_HOURS = {u: h for u, h in _UNITS.values()}
_UNIT_LABEL = {"min": ("min", "min"), "hr": ("hr", "hrs"),
               "day": ("Day", "Days"), "week": ("Week", "Weeks")}
_EDGE_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*([a-z]*)\s*$")


def parse_notice_edges(tags):
    """Tags → (edges, unparseable tags). Edges are sorted (hours, unit) pairs,
    keeping the unit the user typed so labels read the way they were entered.
    Empty / all-invalid input falls back to DEFAULT_NOTICE_EDGES.
    """
    seen, bad = {}, []
    for t in tags or []:
        m = _EDGE_RE.match(str(t).lower())
        unit = _UNITS.get(m.group(2)) if m else None
        if unit is None or float(m.group(1)) <= 0:
            bad.append(str(t))
            continue
        hours = round(float(m.group(1)) * unit[1], 4)
        seen.setdefault(hours, unit[0])           # first spelling wins
    if not seen:
        return parse_notice_edges(DEFAULT_NOTICE_EDGES)[0], bad
    return sorted(seen.items()), bad


def _num(x):
    return f"{round(x, 2):g}"


def _in_unit(hours, unit):
    """Value of `hours` in `unit` if it's a whole number, else None."""
    v = hours / _UNIT_HOURS[unit]
    return v if abs(round(v) - v) < 1e-9 and v >= 1 else None


def _edge_text(hours, unit):
    v = hours / _UNIT_HOURS[unit]
    one, many = _UNIT_LABEL[unit]
    return f"{_num(v)} {one if v == 1 else many}"


def notice_bucket_labels(edges):
    """Display labels for buckets: < e0, e0–e1, …, > eN."""
    labels = [f"< {_edge_text(*edges[0])}"]
    for (ha, ua), (hb, ub) in zip(edges, edges[1:]):
        va = _in_unit(ha, ub)
        if va is not None:                         # "4–8 hrs", "1–3 Days"
            labels.append(f"{_num(va)}–{_num(hb / _UNIT_HOURS[ub])} {_UNIT_LABEL[ub][1]}")
        else:                                      # "30 min–2 hrs"
            labels.append(f"{_edge_text(ha, ua)}–{_edge_text(hb, ub)}")
    labels.append(f"> {_edge_text(*edges[-1])}")
    return labels


# Outcome stack (bottom → top) for the breakdown chart
_OUTCOME_STACK = [
    ("Refilled", SEMANTIC_COLORS["success"]),
    ("Partially Refilled", "#86EFAC"),
    ("Not Refilled", SEMANTIC_COLORS["error"]),
    ("No-Show", SEMANTIC_COLORS["warning"]),
    ("No Slot Lost", "#9CA3AF"),
    ("Upcoming", "#D1D5DB"),
]
_OUTCOME_LABEL = {
    "Refilled": "Refilled",
    "Partially refilled": "Partially Refilled",
    "Not refilled": "Not Refilled",
    NO_SHOW_OUTCOME: "No-Show",
    PENDING_OUTCOME: "Upcoming",
    **{o: "No Slot Lost" for o in NO_LOSS_OUTCOMES},
}


def cancelled_mask(df):
    """True for cancelled / no-show rows (case-insensitive Status match)."""
    if "Status" not in df.columns:
        return pd.Series(False, index=df.index)
    return df["Status"].astype(str).str.lower().str.contains(
        "cancel|no-show|no show", na=False)


def _no_show_mask(c):
    outcome = c["SlotOutcome"] if "SlotOutcome" in c.columns else pd.Series(index=c.index, dtype=object)
    status = c["Status"].astype(str).str.lower() if "Status" in c.columns else pd.Series("", index=c.index)
    return (outcome == NO_SHOW_OUTCOME) | status.str.contains("no-show|no show", na=False)


def _rebooked_mask(c, next_col):
    nxt = c[next_col].notna() if next_col in c.columns else pd.Series(False, index=c.index)
    if "SlotOutcome" in c.columns:
        nxt = nxt | c["SlotOutcome"].isin(NO_LOSS_OUTCOMES - {"Shared slot"})
    return nxt


def _period_metric(sub, metric, periods, next_col):
    """One metric value per period for a (date-filtered, period-tagged) subset."""
    is_c = sub["_cancelled"]
    c = sub[is_c]
    if metric == "rate":
        totals = sub.groupby("period").size().reindex(periods, fill_value=0)
        cancels = c.groupby("period").size().reindex(periods, fill_value=0)
        return ((cancels / totals.replace(0, np.nan)) * 100).fillna(0)
    if metric == "idle":
        if "SlotIdleMinutes" not in c.columns:
            return pd.Series(0.0, index=periods)
        return (c.groupby("period")["SlotIdleMinutes"].sum() / 60).reindex(periods, fill_value=0)
    if metric == "notice":
        if "CancelLeadHours" not in c.columns:
            return pd.Series(np.nan, index=periods)
        cc = c[~_no_show_mask(c) & c["CancelLeadHours"].notna()]
        return (cc.groupby("period")["CancelLeadHours"].median() / 24).reindex(periods)
    if metric == "refill":
        if "SlotOutcome" not in c.columns or "SlotRefilledPct" not in c.columns:
            return pd.Series(np.nan, index=periods)
        cc = c[c["SlotOutcome"].isin(LOST_OUTCOMES)]
        return cc.groupby("period")["SlotRefilledPct"].mean().reindex(periods)
    if metric == "rebook":
        if c.empty:
            return pd.Series(np.nan, index=periods)
        rb = _rebooked_mask(c, next_col).astype(float) * 100
        return rb.groupby(c["period"]).mean().reindex(periods)
    return pd.Series(np.nan, index=periods)


def _clean(values, trim):
    out = [None if (v is None or pd.isna(v)) else float(v) for v in values]
    return trim(out) if trim else out


def prepare_cancel_trend(dff, agg, metric, groups, next_col, trim_edges=None):
    """Store payload for the clientside cancellation trend chart.

    dff:    all-status rows (already filtered to page filters + date range)
    groups: list of (name, boolean mask over dff, color); empty → single total
    """
    if dff is None or dff.empty or "ScheduledDateTime" not in dff.columns:
        return None
    metric = metric if metric in _METRIC_META else "rate"
    meta = _METRIC_META[metric]

    dff = dff.copy()
    period_code = "Y" if agg == "Y" else (agg or "M")
    dff["period"] = dff["ScheduledDateTime"].dt.to_period(period_code).dt.to_timestamp()
    dff["_cancelled"] = cancelled_mask(dff)
    periods = full_period_range(dff["period"], period_code)

    # Rate/idle are zero-filled counts → trim leading/trailing zeros.
    # Notice/refill/rebook are NaN where there were no eligible cancellations.
    trim = trim_edges if metric in ("rate", "idle") else None

    series = []
    if not groups:
        vals = _period_metric(dff, metric, periods, next_col)
        series.append({"name": meta["total"], "values": _clean(vals.tolist(), trim), "color": PRIMARY})
    else:
        for name, mask, color in groups:
            sub = dff[mask.reindex(dff.index, fill_value=False)]
            if sub.empty:
                continue
            vals = _period_metric(sub, metric, periods, next_col)
            series.append({"name": name, "values": _clean(vals.tolist(), trim), "color": color})

    if not series:
        return None
    payload = {
        "dates": [d.isoformat() for d in periods],
        "series": series,
        "height": 350,
        "yTitle": meta["yTitle"],
        "stacked": metric == "idle",
        "hideLegend": len(series) <= 1,
        "compactX": True,  # short, sparse date ticks — avoids label collisions
    }
    if metric == "idle":
        payload["hoverDecimals"] = 1
    if metric in ("refill", "rebook"):
        payload["yRange"] = [0, 100]
    return payload


def _notice_bucket(c, edges, labels):
    lead = c["CancelLeadHours"] if "CancelLeadHours" in c.columns else pd.Series(np.nan, index=c.index)
    # Same-day saves with slightly negative lead (cancelled after start, then
    # seen anyway) belong in the shortest bucket, not "No-Show" — clip at 0.
    bins = [-np.inf, *(h for h, _ in edges), np.inf]
    b = pd.cut(lead.clip(lower=0), bins=bins, labels=labels, right=False).astype(object)
    b[_no_show_mask(c)] = NO_SHOW_BUCKET
    return b


def build_notice_figure(dff, mode="count", next_col="", edge_tags=None):
    """Stacked bars: cancellations by notice bucket, stacked by slot outcome.

    edge_tags: bucket edges as tags ("4h", "2d", …); None → defaults.
    Returns (figure, summary_text).
    """
    edges, bad = parse_notice_edges(edge_tags if edge_tags else DEFAULT_NOTICE_EDGES)
    labels = notice_bucket_labels(edges)
    buckets = [NO_SHOW_BUCKET, *labels]
    if dff is None or dff.empty:
        return empty_figure(), ""
    c = dff[cancelled_mask(dff)].copy()
    if c.empty:
        return empty_figure("No cancellations for selected filters"), ""

    c["_bucket"] = _notice_bucket(c, edges, labels)
    c = c[c["_bucket"].notna()]
    if c.empty:
        return empty_figure("No cancellation timing data for selected filters"), ""
    outcome = c["SlotOutcome"] if "SlotOutcome" in c.columns else pd.Series(np.nan, index=c.index)
    c["_outcome"] = outcome.map(_OUTCOME_LABEL)
    # No-show bucket rows are no-shows regardless of the slot-outcome label
    c.loc[c["_bucket"] == NO_SHOW_BUCKET, "_outcome"] = "No-Show"
    c["_outcome"] = c["_outcome"].fillna("No Slot Lost")

    counts = (c.groupby(["_bucket", "_outcome"]).size()
                .unstack(fill_value=0)
                .reindex(index=buckets, fill_value=0))
    bucket_n = counts.sum(axis=1)
    pct = counts.div(bucket_n.replace(0, np.nan), axis=0).fillna(0) * 100

    fig = go.Figure()
    for label, color in _OUTCOME_STACK:
        if label not in counts.columns or counts[label].sum() == 0:
            continue
        n = counts[label]
        p = pct[label]
        y = p if mode == "pct" else n
        fig.add_trace(go.Bar(
            x=buckets, y=y.tolist(), name=label,
            marker=dict(color=color),
            customdata=np.column_stack([n.values, p.values]),
            hovertemplate=f"<b>%{{x}}</b><br>{label}: %{{customdata[0]:,.0f}} "
                          f"(%{{customdata[1]:.0f}}%)<extra></extra>",
        ))

    # Refill % of vacated slots per bucket, annotated above each bar
    lost = c[outcome.reindex(c.index).isin(LOST_OUTCOMES)]
    refill = (lost.groupby("_bucket")["SlotRefilledPct"].mean()
              if "SlotRefilledPct" in lost.columns and not lost.empty
              else pd.Series(dtype=float))
    tops = (pct.sum(axis=1) if mode == "pct" else bucket_n)
    many = len(buckets) > 6   # narrow bars: stack the label on two lines
    for b in buckets:
        if bucket_n.get(b, 0) == 0:
            continue
        r = refill.get(b, np.nan)
        txt = f"n={int(bucket_n[b])}"
        if pd.notna(r) and b != NO_SHOW_BUCKET:
            txt += f"<br>{r:.0f}% refilled" if many else f" · {r:.0f}% refilled"
        fig.add_annotation(x=b, y=float(tops[b]), text=txt, showarrow=False,
                           yanchor="bottom", yshift=2,
                           font=dict(size=10 if many else 11, color="#6B7280"))
    ymax = float(tops.max()) if len(tops) else 0
    headroom = 1.22 if many else 1.12

    apply_default_layout(fig, barmode="stack")
    fig.update_layout(
        margin=dict(l=8, r=8, t=24, b=8),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, xanchor="left",
                    font=dict(size=11), traceorder="normal"),
        yaxis=dict(title=("% of Cancellations" if mode == "pct" else "Cancellations"),
                   ticksuffix=("%" if mode == "pct" else ""),
                   range=[0, ymax * headroom] if ymax > 0 else None,
                   tickvals=([0, 20, 40, 60, 80, 100] if mode == "pct" else None)),
        xaxis=dict(title=None),
        bargap=0.25 if many else 0.35,
        hovermode="closest",
    )
    summary = _summary_text(c, outcome, next_col)
    if bad:
        summary += f" · ignored: {', '.join(bad)}"
    return fig, summary


def _summary_text(c, outcome, next_col):
    n = len(c)
    parts = [f"{n:,} cancellations"]
    lead = c["CancelLeadHours"] if "CancelLeadHours" in c.columns else None
    if lead is not None:
        nl = lead[~_no_show_mask(c)].dropna()
        if not nl.empty:
            med = nl.median()
            parts.append(f"median notice {med:.0f} hrs" if med < 48 else f"median notice {med / 24:.1f} days")
    ns = int(_no_show_mask(c).sum())
    if ns:
        parts.append(f"{ns / n * 100:.0f}% no-show")
    lost = c[outcome.reindex(c.index).isin(LOST_OUTCOMES)]
    if not lost.empty and "SlotRefilledPct" in lost.columns:
        parts.append(f"{lost['SlotRefilledPct'].mean():.0f}% refilled")
    if next_col:
        parts.append(f"{_rebooked_mask(c, next_col).mean() * 100:.0f}% rebooked")
    if "SlotIdleMinutes" in c.columns:
        parts.append(f"{c['SlotIdleMinutes'].sum() / 60:,.0f} hrs lost")
    return " · ".join(parts)
