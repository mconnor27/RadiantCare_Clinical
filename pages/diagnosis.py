"""Diagnosis page — ridgeline trend and current-vs-prior comparison by diagnosis group."""

import dash
import dash_ag_grid as dag
import dash_mantine_components as dmc
from dash import callback, Input, Output, State, dcc, html, clientside_callback, ClientsideFunction
from dash_iconify import DashIconify
import plotly.graph_objects as go
import pandas as pd
import numpy as np

from config.settings import (
    DEPARTMENTS, DEPARTMENT_COLORS, CHART_COLORWAY,
    PRIMARY, DEFAULT_LAYOUT, FONT_FAMILY, NEUTRAL,
)
from components.filter_bar import department_chips, physician_short_name
from components.chart_card import chart_card, register_chart_callbacks
from components.chart_settings import chart_settings_popover
from components.phi import apply_phi_grid_rules
from utils.diagnosis_categories import SUBCATEGORIES as DIAG_SUBCATEGORIES
from utils.charts import apply_default_layout, empty_figure
from utils.permissions import can_see_manager_modals
from utils.date_slider import (
    month_idx, idx_to_date, MAX_IDX, DEFAULT_SLIDER, SLIDER_MARKS,
    preset_to_slider_val, preset_to_exact_dates,
)
from utils.diagnosis_categories import (
    CATEGORIES as BODY_SYSTEMS,
    build_code_to_category,
    invalidate_code_map_cache,
    primary_category,
)

dash.register_page(__name__, path="/diagnosis", name="Diagnosis", order=6)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_DEFAULT_DATE_PRESET = "ytd" if pd.Timestamp.now().month > 1 else "12mo"
_DEFAULT_MODE = "consults"

# Consistent colors for each diagnosis group (13 categories)
_DIAG_COLORS = [
    "#7C2A83", "#2196F3", "#F44336", "#4CAF50", "#FF9800",
    "#00BCD4", "#9C27B0", "#795548", "#E91E63", "#3F51B5",
    "#8BC34A", "#FF5722", "#607D8B",
]

_RIDGE_HEIGHT = 840


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_date_range(slider_val):
    """Calculate start/end from slider, capped to today."""
    today = pd.Timestamp.now().normalize()
    if slider_val and len(slider_val) == 2:
        start = idx_to_date(slider_val[0])
        end = min(idx_to_date(slider_val[1], end_of_month=True), today)
        return start, end
    return pd.Timestamp("2020-01-01"), today


# Per-mode floor dates — DiagnosisCodes not reliably populated before these
_MODE_FLOOR = {
    "consults":    pd.Timestamp("2021-08-01"),
    "followups":   pd.Timestamp("2021-08-01"),
    "virtual":     pd.Timestamp("2021-08-01"),
    "otvs":        pd.Timestamp("2021-08-01"),
}
_DEFAULT_FLOOR_IDX = month_idx(
    _MODE_FLOOR[_DEFAULT_MODE].year, _MODE_FLOOR[_DEFAULT_MODE].month
) if _DEFAULT_MODE in _MODE_FLOOR else 0


_MODE_CACHE: dict = {}


def _classified_clinic_visits():
    """Return clinic-visits df with a cached ``_visit_type`` column.

    Runs ``_classify_visit_type`` (a slow row-wise classifier) exactly once
    per process so consults / followups / virtual modes can slice with a
    cheap boolean comparison.
    """
    cache_key = "__clinic_visits_classified__"
    cached = _MODE_CACHE.get(cache_key)
    if cached is not None:
        return cached

    from data.loader import load_clinic_visits
    df = load_clinic_visits()
    if df.empty or "ActivityName" not in df.columns:
        df = df.assign(_visit_type=pd.Series(dtype="object"))
    else:
        from pages.clinic_visits import _classify_visit_type
        df = df.copy()
        df["_visit_type"] = df.apply(_classify_visit_type, axis=1)
    _MODE_CACHE[cache_key] = df
    return df


def _load_for_mode(mode):
    """Load the dataset for *mode* and return ``(df, date_col, phys_col)``.

    Results are cached per-mode at module scope — the underlying loaders are
    already ``@lru_cache``'d, and the per-mode post-processing (consult
    classification, OTV status filter, floor-date clamp) is deterministic.

    Modes
    -----
    consults   – Clinic Visits classified as new-patient consults
    followups  – Clinic Visits classified as follow-ups
    virtual    – Clinic Visits where ActivityName contains "virtual"
    simulations – Simulation appointments
    treatments – Treatment Detail records
    courses    – Treatment Courses
    otvs       – OTV Audit records
    """
    cached = _MODE_CACHE.get(mode)
    if cached is not None:
        return cached

    from data.loader import (
        load_courses, load_simulations,
        load_treatment_detail, load_weekly_visits,
    )

    if mode in ("consults", "followups", "virtual"):
        df = _classified_clinic_visits()
        date_col = "ScheduledDateTime"
        phys_col = "AppointmentPhysician"
        if not df.empty and "_visit_type" in df.columns:
            if mode == "consults":
                df = df[df["_visit_type"] == "Consult"]
            elif mode == "followups":
                df = df[df["_visit_type"] == "Follow-Up"]
            else:
                df = df[df["_visit_type"] == "Virtual"]

    elif mode == "simulations":
        df, date_col, phys_col = load_simulations(), "ScheduledDateTime", "SupervisingPhysician"

    elif mode == "treatments":
        df, date_col, phys_col = load_treatment_detail(), "ScheduledDateTime", "TreatingPhysician"

    elif mode == "otvs":
        df = load_weekly_visits()
        if not df.empty and "ActivityStatus" in df.columns:
            df = df[df["ActivityStatus"].isin(["Completed", "Manually Completed"])]
        date_col, phys_col = "AppointmentDateTime", "TreatingPhysician"

    else:
        # courses (default)
        df, date_col, phys_col = load_courses(), "CourseStartDate", "TreatingPhysician"

    # Apply floor date
    floor = _MODE_FLOOR.get(mode)
    if floor is not None and not df.empty and date_col in df.columns:
        df = df[df[date_col] >= floor]

    result = (df, date_col, phys_col)
    _MODE_CACHE[mode] = result
    return result


_C2B_CACHE: dict = {}


def _cached_c2b():
    """Cache build_code_to_category(load_diagnosis()) per process."""
    if "c2b" in _C2B_CACHE:
        return _C2B_CACHE["c2b"]
    from data.loader import load_diagnosis
    try:
        diag_df = load_diagnosis()
    except Exception:
        diag_df = None
    c2b = build_code_to_category(diag_df)
    _C2B_CACHE["c2b"] = c2b
    _C2B_CACHE["diag_df"] = diag_df
    return c2b


def _cached_diag_df():
    if "diag_df" not in _C2B_CACHE:
        _cached_c2b()
    return _C2B_CACHE.get("diag_df")


def _invalidate_c2b_cache():
    """Drop cached code→category maps after a Classification Manager edit."""
    _C2B_CACHE.clear()
    invalidate_code_map_cache()
    try:
        from data.loader import load_diagnosis
        load_diagnosis.cache_clear()
    except Exception:
        pass


def _assign_diagnosis(df, c2b):
    """Add _diag_group column from DiagnosisCodes (body system level)."""
    if "DiagnosisCodes" not in df.columns or not c2b:
        return df
    df = df.copy()
    df["_diag_group"] = df["DiagnosisCodes"].apply(lambda v: primary_category(v, c2b))
    df = df[df["_diag_group"] != "Unknown"]
    return df


def _assign_subcategory(df, c2s, category):
    """Add _diag_group column using subcategory within *category*.

    Falls back to 'Other' for codes without a subcategory assignment.
    """
    if "DiagnosisCodes" not in df.columns:
        return df
    from utils.diagnosis_categories import get_subcategories_for_codes
    df = df.copy()

    def _primary_sub(codes_str):
        if pd.isna(codes_str):
            return None
        subs = get_subcategories_for_codes(codes_str, c2s)
        # Only keep subcategories that belong to the selected category
        valid = DIAG_SUBCATEGORIES.get(category, [])
        matched = [s for s in valid if s in subs]
        return matched[0] if matched else "Other"

    df["_diag_group"] = df["DiagnosisCodes"].apply(_primary_sub)
    df = df[df["_diag_group"].notna() & (df["_diag_group"] != "")]
    return df


def _color_map():
    """Return a stable {group_name: hex_color} dict for all BODY_SYSTEMS."""
    return {g: _DIAG_COLORS[i % len(_DIAG_COLORS)] for i, g in enumerate(BODY_SYSTEMS)}


def _hex_to_rgba(hex_color, alpha=0.15):
    """Convert hex like '#7C2A83' to 'rgba(124,42,131,0.35)'."""
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


# ---------------------------------------------------------------------------
# Diagnosis distribution data builder (top N + Other)
# ---------------------------------------------------------------------------

_TOP_N = 5  # show top N groups, bundle rest into "Other"


def _prepare_diag_dist_data(df, date_col):
    """Build diagnosis distribution over time for all agg levels.

    Groups by _diag_group, keeps the top N by total count, bundles
    the rest into "Other". Returns JSON-serialisable dict keyed by agg.
    """
    if df.empty or "_diag_group" not in df.columns or date_col not in df.columns:
        return None

    tmp = df[[date_col, "_diag_group"]].dropna(subset=[date_col]).copy()

    # Determine top N groups by total count
    total_counts = tmp["_diag_group"].value_counts()
    top_groups = total_counts.head(_TOP_N).index.tolist()

    # Assign: keep top groups, everything else → "Other"
    tmp["_grp"] = tmp["_diag_group"].where(
        tmp["_diag_group"].isin(top_groups), "Other"
    )

    # Stacked-area-friendly palette (high contrast, distinct hues)
    _DIST_PALETTE = ["#2196F3", "#F44336", "#FF9800", "#4CAF50", "#9C27B0"]
    cmap = {g: _DIST_PALETTE[i] for i, g in enumerate(top_groups)}
    cmap["Other"] = "#BDBDBD"

    # Order: top groups by count descending, Other last
    ordered = top_groups + ["Other"]

    combos = {}
    for agg in ("W", "M", "Y"):
        period_code = "Y" if agg == "Y" else agg
        t = tmp.copy()
        t["period"] = t[date_col].dt.to_period(period_code).dt.to_timestamp()
        all_periods = sorted(t["period"].unique())
        dates = [d.isoformat() for d in all_periods]

        pivot = t.groupby(["period", "_grp"]).size().unstack(fill_value=0)
        pivot = pivot.reindex(all_periods, fill_value=0)

        series = []
        for grp in ordered:
            vals = pivot[grp].tolist() if grp in pivot.columns else [0] * len(all_periods)
            series.append({
                "name": grp,
                "values": vals,
                "color": cmap.get(grp, CHART_COLORWAY[0]),
            })

        combos[agg] = {"dates": dates, "series": series}

    return combos


def _apply_moving_avg(values, window):
    """Apply simple moving average to a list of values."""
    if window <= 1:
        return values
    result = []
    for i in range(len(values)):
        start = max(0, i - window + 1)
        chunk = [v for v in values[start:i + 1] if v is not None]
        result.append(round(sum(chunk) / len(chunk), 2) if chunk else None)
    return result


# ---------------------------------------------------------------------------
# Trend store data builder (server → store, rendered clientside)
# ---------------------------------------------------------------------------

def _sort_groups(groups_by_count, sort_order, curr_counts=None, prior_counts=None):
    """Return groups list sorted per *sort_order* (bottom→top for ridgeline).

    sort_order: "volume" (by current count), "change" (by abs delta %),
                "alpha" (alphabetical).
    """
    if sort_order == "alpha":
        return sorted(groups_by_count, reverse=True)
    if sort_order == "change" and curr_counts is not None and prior_counts is not None:
        def _abs_change(g):
            c = curr_counts.get(g, 0)
            p = prior_counts.get(g, 0)
            if p > 0:
                return abs((c - p) / p)
            return float(c > 0)  # new items sort above zero-change
        return sorted(groups_by_count, key=_abs_change)
    # default: volume (ascending for ridgeline bottom→top)
    return list(reversed(pd.Series(
        {g: curr_counts.get(g, 0) if curr_counts is not None else 0
         for g in groups_by_count}
    ).sort_values(ascending=False).index.tolist()))


def _prepare_trend_store(df, date_col, sort_order="volume", prior_windows=None):
    """Build per-group time-series data for all agg levels (W/M/Y).

    Returns a JSON-serialisable dict consumed by the clientside renderer.
    """
    if df.empty or "_diag_group" not in df.columns or date_col not in df.columns:
        return None

    tmp = df[[date_col, "_diag_group"]].dropna(subset=[date_col]).copy()
    body_cmap = _color_map()

    curr_counts = tmp["_diag_group"].value_counts()
    # Build prior counts from first prior window for change sorting
    prior_counts = pd.Series(dtype=int)
    if prior_windows:
        pw0 = prior_windows[0][0]
        if pw0 is not None and not pw0.empty and "_diag_group" in pw0.columns:
            prior_counts = pw0["_diag_group"].value_counts()

    all_groups = list(curr_counts.index)
    groups = _sort_groups(all_groups, sort_order, curr_counts, prior_counts)
    if not groups:
        return None

    # Dynamic color map: use body system colors if they match, else cycle CHART_COLORWAY
    cmap = {}
    ci = 0
    for g in groups:
        if g in body_cmap:
            cmap[g] = body_cmap[g]
        else:
            cmap[g] = CHART_COLORWAY[ci % len(CHART_COLORWAY)]
            ci += 1

    combos = {}
    for agg in ("W", "M", "Y"):
        period_code = "Y" if agg == "Y" else agg
        t = tmp.copy()
        t["period"] = t[date_col].dt.to_period(period_code).dt.to_timestamp()
        all_periods = sorted(t["period"].unique())
        dates = [d.isoformat() for d in all_periods]

        series = []
        for grp in groups:
            sub = t[t["_diag_group"] == grp]
            counts = sub.groupby("period").size().reindex(all_periods, fill_value=0)
            series.append({
                "name": grp,
                "values": counts.tolist(),
                "color": cmap.get(grp, CHART_COLORWAY[0]),
            })

        combos[agg] = {"dates": dates, "series": series}

    return {"combos": combos, "groups": groups, "height": _RIDGE_HEIGHT}


# ---------------------------------------------------------------------------
# Current vs Prior comparison bar chart
# ---------------------------------------------------------------------------

def _period_label(start, end):
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


def _build_comparison_bars(dff_curr, prior_windows, start, end, sort_order="volume"):
    """Horizontal grouped bar chart: current vs N prior periods per diagnosis group.

    Args:
        dff_curr: Current period dataframe (with _diag_group column)
        prior_windows: list of (dff_prior, prior_start, prior_end) tuples
        start, end: Current period boundaries
        sort_order: "volume", "change", or "alpha"
    """
    if dff_curr.empty or "_diag_group" not in dff_curr.columns:
        fig = empty_figure("No diagnosis data available")
        fig.update_layout(height=_RIDGE_HEIGHT)
        return fig

    body_cmap = _color_map()
    curr_label = _period_label(start, end)
    curr_counts = dff_curr["_diag_group"].value_counts()

    # Build prior count series + labels
    prior_data = []  # list of (label, counts_series)
    for dff_p, ps, pe in prior_windows:
        label = _period_label(ps, pe)
        counts = (
            dff_p["_diag_group"].value_counts()
            if dff_p is not None and not dff_p.empty and "_diag_group" in dff_p.columns
            else pd.Series(dtype=int)
        )
        prior_data.append((label, counts))

    # Collect all groups across current + all priors
    all_group_set = set(curr_counts.index)
    for _, pc in prior_data:
        all_group_set.update(pc.index)

    # Sort for horizontal bar (Plotly renders last item at top)
    first_prior = prior_data[0][1] if prior_data else pd.Series(dtype=int)
    effective_sort = sort_order if prior_data else "volume"
    all_groups = _sort_groups(list(all_group_set), effective_sort, curr_counts, first_prior)

    # Dynamic color map
    cmap = {}
    ci = 0
    for g in all_groups:
        if g in body_cmap:
            cmap[g] = body_cmap[g]
        else:
            cmap[g] = CHART_COLORWAY[ci % len(CHART_COLORWAY)]
            ci += 1

    curr_vals = [int(curr_counts.get(g, 0)) for g in all_groups]
    n_periods = 1 + len(prior_data)  # current + priors
    # When bars are narrow (2-3 periods), put labels outside in black
    outside = n_periods >= 3

    fig = go.Figure()

    # Prior bars (furthest back first, progressively lighter)
    gray_alphas = [0.45, 0.30, 0.18]
    for idx in range(len(prior_data) - 1, -1, -1):
        plabel, pcounts = prior_data[idx]
        pvals = [int(pcounts.get(g, 0)) for g in all_groups]
        alpha = gray_alphas[idx] if idx < len(gray_alphas) else 0.15
        fig.add_trace(go.Bar(
            x=pvals,
            y=all_groups,
            orientation="h",
            marker_color=f"rgba(156, 163, 175, {alpha})",
            name=plabel,
            text=[f"{v:,}" for v in pvals],
            textposition="outside" if outside else "inside",
            insidetextanchor="end" if not outside else None,
            textangle=0,
            textfont=dict(size=11 if outside else 13,
                          color="#374151" if outside else "#6B7280"),
            hovertemplate=[
                f"<b>{g}</b><br>{plabel}: {v:,}<extra></extra>"
                for g, v in zip(all_groups, pvals)
            ],
        ))

    # Current bars (front, colored per group)
    bar_colors = [cmap.get(g, CHART_COLORWAY[0]) for g in all_groups]
    fig.add_trace(go.Bar(
        x=curr_vals,
        y=all_groups,
        orientation="h",
        marker_color=bar_colors,
        name=curr_label,
        text=[f"{v:,}" for v in curr_vals],
        textposition="outside" if outside else "inside",
        insidetextanchor="end" if not outside else None,
        textangle=0,
        textfont=dict(size=11 if outside else 13,
                      color="#374151" if outside else "white"),
        hovertemplate=[
            f"<b>{g}</b><br>{curr_label}: {v:,}<extra></extra>"
            for g, v in zip(all_groups, curr_vals)
        ],
    ))

    # Delta annotations: compare current vs most recent prior (skip if no priors)
    annotations = []
    if prior_data:
        first_prior_counts = prior_data[0][1] if prior_data else pd.Series(dtype=int)
        first_prior_vals = [int(first_prior_counts.get(g, 0)) for g in all_groups]
        all_vals = curr_vals + first_prior_vals
        for _, pc in prior_data:
            all_vals += [int(pc.get(g, 0)) for g in all_groups]
        max_val = max(all_vals) if all_vals else 0
        annot_x = max_val * 1.05 if max_val > 0 else 1

        for i, g in enumerate(all_groups):
            c, p = curr_vals[i], first_prior_vals[i]
            if p > 0:
                pct = (c - p) / p * 100
                if pct > 0:
                    txt = f"▲ {pct:.0f}%"
                    color = "#10B981"
                elif pct < 0:
                    txt = f"▼ {abs(pct):.0f}%"
                    color = "#EF4444"
                else:
                    txt = "—"
                    color = "#9CA3AF"
            elif c > 0:
                txt = "● new"
                color = "#3B82F6"
            else:
                txt = ""
                color = "#9CA3AF"

            if txt:
                annotations.append(dict(
                    x=annot_x,
                    y=g,
                    text=txt,
                    showarrow=False,
                    font=dict(size=13, color=color, family=FONT_FAMILY),
                    xanchor="left",
                    yanchor="middle",
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


# ---------------------------------------------------------------------------
# Filter Bar
# ---------------------------------------------------------------------------

def _build_filter_bar():
    """Two-row filter: data filters + date slider."""
    return dmc.Paper(
        children=[
            dmc.Group(
                children=[
                    department_chips("diag"),
                    # Physician chip dropdown (multi-select)
                    html.Div(
                        children=[
                            html.Div(
                                children=[
                                    dmc.Button(
                                        "Physician",
                                        id="diag-physician-trigger",
                                        variant="default",
                                        size="sm",
                                        rightSection=DashIconify(icon="mdi:chevron-down", width=14),
                                    ),
                                    dmc.ActionIcon(
                                        DashIconify(icon="mdi:close-circle", width=18),
                                        id="diag-physician-clear",
                                        variant="subtle",
                                        color="gray",
                                        size="sm",
                                        className="wf-filter-clear-btn",
                                    ),
                                ],
                                style={"position": "relative", "display": "inline-block"},
                            ),
                            dmc.Paper(
                                children=[
                                    dmc.ChipGroup(
                                        children=[],
                                        id="diag-filter-physician",
                                        multiple=True,
                                        value=[],
                                    ),
                                ],
                                p="xs",
                                shadow="md",
                                withBorder=True,
                                radius="md",
                                className="wf-chip-dropdown",
                                style={"display": "none"},
                            ),
                        ],
                        style={"position": "relative", "display": "inline-block"},
                    ),
                    # Diagnosis category selector (single-select, expand = select)
                    html.Div(
                        children=[
                            html.Div(
                                children=[
                                    dmc.Button(
                                        "Diagnosis",
                                        id="diag-diag-trigger",
                                        variant="default",
                                        size="sm",
                                        rightSection=DashIconify(icon="mdi:chevron-down", width=14),
                                    ),
                                    dmc.ActionIcon(
                                        DashIconify(icon="mdi:close-circle", width=18),
                                        id="diag-diag-clear",
                                        variant="subtle",
                                        color="gray",
                                        size="sm",
                                        className="wf-filter-clear-btn",
                                    ),
                                ],
                                style={"position": "relative", "display": "inline-block"},
                            ),
                            dcc.Store(id="diag-diag-store", data=None),
                            dcc.Store(id="diag-diag-mode", data="primary"),
                            dmc.Paper(
                                children=[
                                    dmc.SegmentedControl(
                                        id="diag-diag-mode-ctrl",
                                        data=[
                                            {"value": "primary", "label": "Primary"},
                                            {"value": "all", "label": "All"},
                                        ],
                                        value="primary",
                                        size="xs",
                                        fullWidth=True,
                                        mb="xs",
                                    ),
                                    dmc.Accordion(
                                        children=[
                                            dmc.AccordionItem(
                                                children=[
                                                    dmc.AccordionControl(cat),
                                                    dmc.AccordionPanel(
                                                        dmc.Text(
                                                            ", ".join(DIAG_SUBCATEGORIES.get(cat, [])),
                                                            size="xs", c=NEUTRAL["text_muted"],
                                                        ) if DIAG_SUBCATEGORIES.get(cat) else
                                                        dmc.Text("No subsites", size="xs", c=NEUTRAL["text_muted"]),
                                                    ),
                                                ],
                                                value=cat,
                                            )
                                            for cat in BODY_SYSTEMS
                                        ],
                                        id="diag-diag-accordion",
                                        value=None,
                                        variant="contained",
                                        chevronPosition="right",
                                    ),
                                ],
                                p="xs",
                                shadow="md",
                                withBorder=True,
                                radius="md",
                                className="wf-chip-dropdown wf-diag-panel",
                                style={"display": "none"},
                            ),
                        ],
                        style={"position": "relative", "display": "inline-block"},
                    ),
                    dmc.SegmentedControl(
                        id="diag-mode-toggle",
                        data=[
                            {"value": "consults", "label": "Consults"},
                            {"value": "followups", "label": "Follow-ups"},
                            {"value": "virtual", "label": "Virtual"},
                            {"value": "simulations", "label": "Simulations"},
                            {"value": "treatments", "label": "Treatments"},
                            {"value": "courses", "label": "Courses"},
                            {"value": "otvs", "label": "OTVs"},
                        ],
                        value="consults",
                        size="xs",
                        color="violet",
                    ),
                ],
                gap="md",
                align="center",
                wrap="wrap",
            ),
            dmc.Group(
                children=[
                    dmc.Select(
                        id="diag-filter-date-preset",
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
                        size="xs",
                        w=150,
                        allowDeselect=False,
                        leftSection=DashIconify(icon="mdi:clock-outline", width=14),
                        comboboxProps={"zIndex": 500, "offset": 2},
                        maxDropdownHeight=400,
                    ),
                    dmc.Paper(
                        dcc.DatePickerRange(
                            id="diag-filter-daterange",
                            display_format="MMM D, YYYY",
                            start_date_placeholder_text="Start",
                            end_date_placeholder_text="End",
                            clearable=True,
                            number_of_months_shown=2,
                            minimum_nights=0,
                            min_date_allowed=idx_to_date(_DEFAULT_FLOOR_IDX).strftime("%Y-%m-%d"),
                            start_date=idx_to_date(max(preset_to_slider_val(_DEFAULT_DATE_PRESET, MAX_IDX)[0], _DEFAULT_FLOOR_IDX)).strftime("%Y-%m-%d"),
                            end_date=idx_to_date(preset_to_slider_val(_DEFAULT_DATE_PRESET, MAX_IDX)[1], end_of_month=True).strftime("%Y-%m-%d"),
                            className="wf-date-picker-range",
                        ),
                        px="xs",
                        py=4,
                        radius="sm",
                        withBorder=True,
                        className="wf-datepicker-wrapper",
                    ),
                    dmc.Box(
                        children=[
                            html.Div(id="diag-date-range-label", style={"display": "none"}),
                            dmc.RangeSlider(
                                id="diag-date-slider",
                                min=_DEFAULT_FLOOR_IDX,
                                max=MAX_IDX,
                                step=1,
                                value=[max(v, _DEFAULT_FLOOR_IDX) for v in preset_to_slider_val(_DEFAULT_DATE_PRESET, MAX_IDX)],
                                marks=[m for m in SLIDER_MARKS if m["value"] >= _DEFAULT_FLOOR_IDX],
                                color="violet",
                                size="sm",
                                minRange=0,
                            ),
                        ],
                        style={"flex": "1", "minWidth": "280px"},
                    ),
                ],
                gap="md",
                align="center",
                mt="xs",
            ),
        ],
        p="sm",
        px="md",
        radius="md",
        shadow="xs",
        withBorder=True,
    )


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------

_TREND_CHART_TYPES = [
    {"value": "area", "label": "Area"},
    {"value": "line", "label": "Line"},
    {"value": "bar", "label": "Bar"},
]

layout = dmc.Stack(
    gap=16,
    className="page-content",
    children=[
        dmc.Box(
            className="page-sticky-header",
            children=[
                dmc.Group(
                    justify="center", align="center", gap="sm",
                    children=[
                        dmc.Title("Diagnosis", order=2, className="page-title",
                                  style={"margin": 0}),
                        dmc.ActionIcon(
                            DashIconify(icon="tabler:dna", width=20),
                            id="diag-mgr-btn",
                            variant="subtle", color="violet", size="lg",
                        ),
                    ],
                ),
                _build_filter_bar(),
            ],
        ),
        # Charts row: trend ridgeline + comparison bars
        dmc.Grid(
            gutter="md",
            children=[
                dmc.GridCol(
                    chart_card(
                        "diag-chart-trend",
                        "Trend",
                        chart_types=_TREND_CHART_TYPES,
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
                                        id="diag-trend-sort",
                                        data=[
                                            {"value": "volume", "label": "Volume"},
                                            {"value": "change", "label": "Change"},
                                            {"value": "alpha", "label": "A–Z"},
                                        ],
                                        value="volume",
                                        size="xs",
                                    ),
                                ],
                            ),
                        ],
                        extra_controls=[
                            dmc.SegmentedControl(
                                id="diag-trend-agg",
                                data=[
                                    {"value": "W", "label": "Weekly"},
                                    {"value": "M", "label": "Monthly"},
                                    {"value": "Y", "label": "Yearly"},
                                ],
                                value="W",
                                size="xs",
                            ),
                        ],
                    ),
                    span=6,
                ),
                dmc.GridCol(
                    dmc.Paper(
                        children=[
                            dmc.LoadingOverlay(
                                id="diag-chart-comparison-loading",
                                visible=False,
                                loaderProps={"type": "dots", "color": PRIMARY},
                                overlayProps={"radius": "sm", "blur": 2},
                                zIndex=10,
                            ),
                            dmc.Group(
                                justify="space-between",
                                mb=8,
                                children=[
                                    dmc.Group(
                                        gap="xs",
                                        children=[
                                            dmc.Text("Current vs Prior Period", size="sm", fw=500,
                                                     c=NEUTRAL["text_secondary"],
                                                     id="diag-compare-title"),
                                            dmc.Group(
                                                gap=4, align="center",
                                                children=[
                                                    DashIconify(icon="mdi:sort", width=14, color="#6B7280"),
                                                    dmc.SegmentedControl(
                                                        id="diag-compare-sort",
                                                        data=[
                                                            {"value": "volume", "label": "Volume"},
                                                            {"value": "change", "label": "Change"},
                                                            {"value": "alpha", "label": "A–Z"},
                                                        ],
                                                        value="volume",
                                                        size="xs",
                                                    ),
                                                ],
                                            ),
                                        ],
                                    ),
                                    dmc.Group(
                                        gap="xs",
                                        children=[
                                            dmc.SegmentedControl(
                                                id="diag-compare-period-type",
                                                data=[
                                                    {"value": "calendar", "label": "Calendar"},
                                                    {"value": "rolling", "label": "Rolling"},
                                                ],
                                                value="calendar",
                                                size="xs",
                                            ),
                                            chart_settings_popover(
                                                "diag-compare",
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
                                                id="diag-chart-comparison",
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
                    span=6,
                ),
            ],
        ),
        # Distribution chart (full-width, top N + Other)
        chart_card(
            "diag-chart-dist",
            "Diagnosis Distribution",
            settings_id="diag-dist",
            chart_types=[
                {"value": "area", "label": "Area"},
                {"value": "line", "label": "Line"},
                {"value": "bar", "label": "Bar"},
            ],
            show_smooth=True,
            smooth_max=24,
            smooth_default=3,
            show_grouping=False,
            paper_padding="md",
            paper_height="500px",
            graph_height="420px",
            store_data=True,
            extra_controls_left=[
                dmc.SegmentedControl(
                    id="diag-dist-mode",
                    data=[
                        {"value": "count", "label": "Count"},
                        {"value": "pct", "label": "%"},
                    ],
                    value="pct",
                    size="xs",
                ),
            ],
            extra_controls=[
                dmc.SegmentedControl(
                    id="diag-dist-agg",
                    data=[
                        {"value": "W", "label": "Weekly"},
                        {"value": "M", "label": "Monthly"},
                        {"value": "Y", "label": "Yearly"},
                    ],
                    value="W",
                    size="xs",
                ),
            ],
        ),
        # ---------------------------------------------------------------
        # Diagnosis Classification Manager Modal
        # ---------------------------------------------------------------
        # Instant-feedback overlay (plain HTML + CSS). Shows the moment the
        # manager button is clicked so the user doesn't stare at an empty
        # screen while the heavy DMC Modal renders.
        html.Div(
            id="diag-mgr-overlay",
            className="heavy-modal-overlay hidden",
            children=[
                html.Div(
                    className="heavy-modal-overlay-card",
                    children=[
                        html.Div(className="heavy-modal-spinner"),
                        html.Div("Loading Diagnosis Classification Manager…",
                                 className="heavy-modal-overlay-text"),
                    ],
                ),
            ],
        ),
        dcc.Interval(
            id="diag-mgr-delay",
            interval=60,
            disabled=True,
            max_intervals=1,
            n_intervals=0,
        ),

        dmc.Modal(
            id="diag-mgr-modal",
            opened=False,
            # keepMounted=False: modal internals are heavy; don't keep them in
            # the DOM on initial page load. First open re-mounts from scratch.
            keepMounted=False,
            transitionProps={"transition": "fade", "duration": 120},
            title=dmc.Group(
                children=[
                    DashIconify(icon="tabler:dna", width=22, color=PRIMARY),
                    dmc.Text("Diagnosis Classification Manager", fw=600, size="lg"),
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
                    justify="space-between", mb=6,
                    children=[
                        dmc.Text(
                            "ARIA Lookup diagnoses — edit category / subcategory assignments. "
                            "Overrides persist to the database.",
                            size="sm", c=NEUTRAL["text_secondary"],
                        ),
                        dmc.Group(
                            gap="sm",
                            children=[
                                dmc.Text(id="diag-mgr-stats", size="xs",
                                         c=NEUTRAL["text_muted"]),
                                dmc.Switch(
                                    id="diag-mgr-unreviewed-toggle",
                                    label="Unreviewed only",
                                    size="xs",
                                    checked=False,
                                ),
                                dmc.Button(
                                    "Mark Reviewed",
                                    id="diag-mgr-reviewed-btn",
                                    leftSection=DashIconify(icon="tabler:check", width=14),
                                    variant="light", color="green", size="xs",
                                ),
                                dmc.Button(
                                    "Delete Selected",
                                    id="diag-mgr-delete-btn",
                                    leftSection=DashIconify(icon="tabler:trash", width=14),
                                    variant="light", color="red", size="xs",
                                ),
                                dmc.Button(
                                    "Export CSV",
                                    id="diag-mgr-export-btn",
                                    leftSection=DashIconify(icon="tabler:download", width=14),
                                    variant="light", color="gray", size="xs",
                                ),
                            ],
                        ),
                    ],
                ),
                dag.AgGrid(
                    id="diag-mgr-grid",
                    columnDefs=[
                        {"field": "icd_code", "headerName": "ICD Code", "flex": 0.6,
                         "filter": "agTextColumnFilter", "floatingFilter": True},
                        {"field": "description", "headerName": "Description", "flex": 2,
                         "filter": "agTextColumnFilter", "floatingFilter": True},
                        {"field": "category", "headerName": "Category", "flex": 1,
                         "editable": True,
                         "cellEditor": "agSelectCellEditor",
                         "cellEditorParams": {"values": [""] + BODY_SYSTEMS + ["Unknown"]},
                         "cellStyle": {"cursor": "pointer"},
                         "filter": "agTextColumnFilter", "floatingFilter": True},
                        {"field": "subcategory", "headerName": "Subcategory", "flex": 1,
                         "editable": True,
                         "cellEditor": "agSelectCellEditor",
                         "cellEditorParams": {"function": "getSubcategoryValues(params)"},
                         "cellStyle": {"cursor": "pointer"},
                         "filter": "agTextColumnFilter", "floatingFilter": True},
                        {"field": "patients", "headerName": "Patients", "flex": 0.4,
                         "cellRenderer": "DiagCountLink",
                         "cellRendererParams": {"storeId": "diag-mgr-detail-store"},
                         "type": "numericColumn", "sort": "desc",
                         "filter": "agNumberColumnFilter"},
                        {"field": "source", "headerName": "Source", "flex": 0.4,
                         "filter": "agTextColumnFilter", "floatingFilter": True,
                         "cellStyle": {"fontStyle": "italic", "color": NEUTRAL["text_muted"]}},
                        {"field": "reviewed", "headerName": "Reviewed", "flex": 0.3,
                         "cellDataType": "boolean", "editable": True,
                         "cellStyle": {"textAlign": "center"}},
                    ],
                    defaultColDef={"sortable": True, "resizable": True,
                                   "valueFormatter": {"function": "params.value == null || params.value === '' ? '–' : params.value"}},
                    dashGridOptions={
                        "pagination": True,
                        "paginationPageSize": 50,
                        "animateRows": True,
                        "singleClickEdit": True,
                        "rowHeight": 36,
                        "headerHeight": 36,
                        "floatingFiltersHeight": 32,
                        "rowSelection": {"mode": "multiRow", "selectAll": "filtered"},
                    },
                    style={"flex": 1, "minHeight": 0},
                    className="ag-theme-alpine",
                ),
                # Detail panel
                dmc.Paper(
                    id="diag-mgr-detail-panel",
                    style={"display": "none"},
                    p="sm", radius="md", withBorder=True,
                    children=[
                        dmc.Group(
                            justify="space-between", mb=4,
                            children=[
                                dmc.Text(id="diag-mgr-detail-title",
                                         size="sm", fw=600, c=PRIMARY),
                                dmc.ActionIcon(
                                    DashIconify(icon="tabler:x", width=14),
                                    id="diag-mgr-detail-close",
                                    variant="subtle", color="gray", size="sm",
                                ),
                            ],
                        ),
                        dag.AgGrid(
                            id="diag-mgr-detail-grid",
                            columnDefs=apply_phi_grid_rules([
                                {"field": "ScheduledDateTime", "headerName": "Date", "flex": 0.6, "sort": "desc"},
                                {"field": "PatientId", "headerName": "MRN", "flex": 0.5},
                                {"field": "PatientFullName", "headerName": "Patient", "flex": 1},
                                {"field": "ActivityName", "headerName": "Activity", "flex": 1},
                                {"field": "DiagnosisCodes", "headerName": "Diagnosis Codes", "flex": 1.5},
                                {"field": "Department", "headerName": "Dept", "flex": 0.5},
                            ]),
                            defaultColDef={"sortable": True, "resizable": True,
                                           "filter": True, "floatingFilter": True,
                                           "valueFormatter": {"function": "params.value == null || params.value === '' ? '–' : params.value"}},
                            dashGridOptions={
                                "rowHeight": 30, "headerHeight": 30,
                                "floatingFiltersHeight": 28,
                                "pagination": True, "paginationPageSize": 10,
                            },
                            style={"height": "250px"},
                            className="ag-theme-alpine",
                        ),
                    ],
                ),
                dcc.Download(id="diag-mgr-download"),
                dcc.Store(id="diag-mgr-detail-store", data=None),
                dcc.Store(id="diag-mgr-full-store", data=None),
            ],
        ),

        dcc.Interval(id="diag-interval", interval=5 * 60 * 1000, n_intervals=0),
    ],
)

# Register gear-icon toggle + export callbacks
register_chart_callbacks([
    "diag-chart-trend",
    ("diag-compare", "diag-chart-comparison"),
    ("diag-dist", "diag-chart-dist"),
])

# --- Diagnosis single-select: expand = select ---
# Accordion expand → store (expanding a category selects it)
clientside_callback(
    """function(val) { return val || null; }""",
    Output("diag-diag-store", "data"),
    Input("diag-diag-accordion", "value"),
)

# Mode toggle → store sync
clientside_callback(
    """function(val) { return val; }""",
    Output("diag-diag-mode", "data"),
    Input("diag-diag-mode-ctrl", "value"),
)

# Trigger label
clientside_callback(
    """function(cat) {
        return cat ? cat : "Diagnosis";
    }""",
    Output("diag-diag-trigger", "children"),
    Input("diag-diag-store", "data"),
)

# Clear-button visibility
clientside_callback(
    """function(cat) {
        return cat ? {"display": "inline-flex"} : {"display": "none"};
    }""",
    Output("diag-diag-clear", "style"),
    Input("diag-diag-store", "data"),
)

# Clear-button action (reset category + mode)
clientside_callback(
    """function(n) { return [null, null, "primary", "primary"]; }""",
    Output("diag-diag-store", "data", allow_duplicate=True),
    Output("diag-diag-accordion", "value", allow_duplicate=True),
    Output("diag-diag-mode", "data", allow_duplicate=True),
    Output("diag-diag-mode-ctrl", "value", allow_duplicate=True),
    Input("diag-diag-clear", "n_clicks"),
    prevent_initial_call=True,
)

# ---------------------------------------------------------------------------
# Sync sort toggles between trend and comparison charts
# ---------------------------------------------------------------------------
clientside_callback(
    """function(trendVal, compareVal) {
        var ctx = window.dash_clientside.callback_context;
        if (!ctx || !ctx.triggered || ctx.triggered.length === 0) {
            return [window.dash_clientside.no_update, window.dash_clientside.no_update];
        }
        var tid = ctx.triggered[0].prop_id;
        if (tid.indexOf("trend") >= 0) return [window.dash_clientside.no_update, trendVal];
        return [compareVal, window.dash_clientside.no_update];
    }""",
    Output("diag-trend-sort", "value", allow_duplicate=True),
    Output("diag-compare-sort", "value", allow_duplicate=True),
    Input("diag-trend-sort", "value"),
    Input("diag-compare-sort", "value"),
    prevent_initial_call=True,
)

# ---------------------------------------------------------------------------
# Physician chip dropdown: trigger label, clear visibility, clear action
# ---------------------------------------------------------------------------
clientside_callback(
    """function(vals) {
        if (!vals || vals.length === 0) return "Physician";
        if (vals.length === 1) return vals[0].split(", ")[0];
        return vals.length + " selected";
    }""",
    Output("diag-physician-trigger", "children"),
    Input("diag-filter-physician", "value"),
)
clientside_callback(
    """function(vals) { return vals && vals.length > 0 ? {"display": "inline-flex"} : {"display": "none"}; }""",
    Output("diag-physician-clear", "style"),
    Input("diag-filter-physician", "value"),
)
clientside_callback(
    """function(n) { return []; }""",
    Output("diag-filter-physician", "value", allow_duplicate=True),
    Input("diag-physician-clear", "n_clicks"),
    prevent_initial_call=True,
)


# ---------------------------------------------------------------------------
# Mode → clamp date slider min to floor date
# ---------------------------------------------------------------------------
@callback(
    Output("diag-date-slider", "min"),
    Output("diag-date-slider", "value", allow_duplicate=True),
    Output("diag-date-slider", "marks"),
    Output("diag-filter-daterange", "min_date_allowed"),
    Input("diag-mode-toggle", "value"),
    State("diag-date-slider", "value"),
    prevent_initial_call=True,
)
def _clamp_slider_to_mode(mode, current_val):
    floor = _MODE_FLOOR.get(mode)
    floor_idx = month_idx(floor.year, floor.month) if floor else 0
    # Clamp current slider value
    new_val = current_val
    if current_val and len(current_val) == 2:
        lo = max(current_val[0], floor_idx)
        hi = max(current_val[1], floor_idx)
        new_val = [lo, hi]
        if new_val == current_val:
            new_val = dash.no_update
    marks = [m for m in SLIDER_MARKS if m["value"] >= floor_idx]
    floor_date = idx_to_date(floor_idx).strftime("%Y-%m-%d")
    return floor_idx, new_val, marks, floor_date


# ---------------------------------------------------------------------------
# Date filter sync: Preset ↔ Slider ↔ DatePicker
# ---------------------------------------------------------------------------

# A) Preset → Slider + DatePicker (clamped to slider min)
@callback(
    Output("diag-date-slider", "value"),
    Output("diag-filter-daterange", "start_date", allow_duplicate=True),
    Output("diag-filter-daterange", "end_date", allow_duplicate=True),
    Input("diag-filter-date-preset", "value"),
    State("diag-date-slider", "min"),
    prevent_initial_call=True,
)
def _sync_preset(preset, slider_min):
    if not preset or preset == "custom":
        return (dash.no_update,) * 3
    slider_min = slider_min or 0
    sv = preset_to_slider_val(preset, MAX_IDX)
    sv = [max(sv[0], slider_min), max(sv[1], slider_min)]
    s, e = preset_to_exact_dates(preset)
    return sv, s, e

# B) Slider → DatePicker + Label (clientside for speed)
clientside_callback(
    ClientsideFunction(namespace="diagDateSlider", function_name="syncSlider"),
    Output("diag-filter-daterange", "start_date", allow_duplicate=True),
    Output("diag-filter-daterange", "end_date", allow_duplicate=True),
    Output("diag-date-range-label", "children"),
    Input("diag-date-slider", "value"),
    State("diag-filter-daterange", "start_date"),
    State("diag-filter-daterange", "end_date"),
    prevent_initial_call=True,
)

# C) DatePicker → Slider
@callback(
    Output("diag-date-slider", "value", allow_duplicate=True),
    Input("diag-filter-daterange", "start_date"),
    Input("diag-filter-daterange", "end_date"),
    State("diag-date-slider", "value"),
    prevent_initial_call=True,
)
def _sync_picker_to_slider(start, end, current_slider):
    if not start or not end:
        return dash.no_update
    s = pd.Timestamp(start)
    e = pd.Timestamp(end)
    new_val = [month_idx(s.year, s.month), month_idx(e.year, e.month)]
    if new_val == current_slider:
        return dash.no_update
    return new_val

# D) Slider → auto-set preset to "Custom" when it doesn't match
@callback(
    Output("diag-filter-date-preset", "value", allow_duplicate=True),
    Input("diag-date-slider", "value"),
    prevent_initial_call=True,
)
def _slider_to_preset(slider_val):
    for preset_key in ("12mo", "6mo", "3mo", "30d", "ytd", "last_year", "this_month", "last_month", "all"):
        if slider_val == preset_to_slider_val(preset_key, MAX_IDX):
            return preset_key
    return "custom"


# ---------------------------------------------------------------------------
# Dynamic physician chip population
# ---------------------------------------------------------------------------
@callback(
    Output("diag-filter-physician", "children"),
    Input("diag-interval", "n_intervals"),
    Input("diag-date-slider", "value"),
    Input("diag-filter-department", "value"),
    Input("diag-diag-store", "data"),
    Input("diag-diag-mode", "data"),
    Input("diag-mode-toggle", "value"),
)
def _populate_physician_chips(_n, slider_val, departments, diag_filter,
                              diag_mode, mode):
    """Populate physician chips from the active dataset, applying all filters."""
    try:
        df, date_col, phys_col = _load_for_mode(mode or "consults")
    except Exception:
        return []

    if df.empty or phys_col not in df.columns:
        return []

    # Date filter
    start, end = _get_date_range(slider_val)
    if date_col in df.columns:
        df = df[(df[date_col] >= start) & (df[date_col] <= end)]

    # Department filter
    if departments and "Department" in df.columns:
        df = df[df["Department"].isin(departments)]

    # Diagnosis filter
    diag_mode = diag_mode or "primary"
    if diag_filter:
        try:
            c2b = _cached_c2b()
            if c2b:
                from utils.diagnosis_categories import filter_by_diagnosis
                df = filter_by_diagnosis(df, [diag_filter], c2b, mode=diag_mode)
        except Exception:
            pass

    mds = sorted(df[phys_col].dropna().unique())

    return [
        dmc.Chip(
            physician_short_name(md),
            value=md,
            size="xs",
            variant="filled",
        )
        for md in mds
    ]


# ---------------------------------------------------------------------------
# Main callback — outputs store data (trend) + figure (comparison bars)
# ---------------------------------------------------------------------------
@callback(
    Output("diag-chart-trend-store", "data"),
    Output("diag-chart-comparison", "figure"),
    Output("diag-chart-dist-store", "data"),
    Output("diag-compare-period-type", "data"),
    Output("diag-compare-period-type", "value", allow_duplicate=True),
    Output("diag-compare-settings-prior-periods", "max"),
    Output("diag-compare-settings-prior-periods", "marks"),
    Output("diag-compare-title", "children"),
    Input("diag-interval", "n_intervals"),
    Input("diag-date-slider", "value"),
    Input("diag-filter-department", "value"),
    Input("diag-filter-physician", "value"),
    Input("diag-diag-store", "data"),
    Input("diag-diag-mode", "data"),
    Input("diag-mode-toggle", "value"),
    Input("diag-compare-period-type", "value"),
    Input("diag-compare-settings-prior-periods", "value"),
    Input("diag-compare-sort", "value"),
    running=[
        (Output("diag-chart-trend-loading", "visible"), True, False),
        (Output("diag-chart-comparison-loading", "visible"), True, False),
    ],
    prevent_initial_call=True,
)
def update_diagnosis(_n, slider_val, departments, physicians, diag_filter,
                     diag_mode, mode, period_type, max_prior, sort_order):
    max_prior = max_prior if max_prior is not None else 1
    empty_bar = empty_figure("No data for selected filters")
    empty_bar.update_layout(height=_RIDGE_HEIGHT)
    # Default control outputs (no change)
    no_ctrl = (dash.no_update,) * 5

    c2b = _cached_c2b()
    diag_df = _cached_diag_df()

    start, end = _get_date_range(slider_val)

    try:
        df_all, date_col, phys_col = _load_for_mode(mode or "consults")
    except Exception:
        return (None, empty_bar, None) + no_ctrl

    if df_all.empty:
        return (None, empty_bar, None) + no_ctrl

    # Department filter
    if departments and "Department" in df_all.columns:
        df_all = df_all[df_all["Department"].isin(departments)]

    # Physician filter (multi-select)
    if physicians and phys_col in df_all.columns:
        df_all = df_all[df_all[phys_col].isin(physicians)]

    # Diagnosis filter + dimension assignment
    # diag_filter is a single category string (or None)
    diag_mode = diag_mode or "primary"
    if diag_filter and c2b:
        from utils.diagnosis_categories import filter_by_diagnosis, build_code_to_subcategory
        # Filter to selected category
        df_all = filter_by_diagnosis(df_all, [diag_filter], c2b, mode=diag_mode)
        if df_all.empty:
            return (None, empty_bar, None) + no_ctrl
        # Assign subcategory as the chart dimension
        c2s = build_code_to_subcategory(diag_df)
        df_all = _assign_subcategory(df_all, c2s, diag_filter)
    else:
        # No category selected — show body system level
        from utils.diagnosis_categories import assign_diagnosis_column
        df_all = assign_diagnosis_column(df_all, c2b, mode=diag_mode)
        if "_bs" in df_all.columns:
            df_all = df_all.rename(columns={"_bs": "_diag_group"})
        else:
            df_all = _assign_diagnosis(df_all, c2b)

    if df_all.empty or "_diag_group" not in df_all.columns:
        return (None, empty_bar, None) + no_ctrl

    # Current period
    if date_col in df_all.columns:
        dff = df_all[(df_all[date_col] >= start) & (df_all[date_col] <= end)]
    else:
        dff = df_all

    if dff.empty:
        return (None, empty_bar, None) + no_ctrl

    # --- Prior periods ---
    period_type = period_type or "calendar"
    period_days = (end - start).days
    # Force rolling when range > 1 year
    cal_disabled = period_days > 365
    if cal_disabled and period_type == "calendar":
        period_type = "rolling"

    data_min = df_all[date_col].min() if date_col in df_all.columns else start

    # Probe up to 3 prior periods to discover availability
    _MAX_PROBE = 3
    all_prior_windows = []
    for i in range(1, _MAX_PROBE + 1):
        if period_type == "calendar":
            try:
                ps = start - pd.DateOffset(years=i)
                pe = end - pd.DateOffset(years=i)
            except Exception:
                break
        else:
            shift = pd.Timedelta(days=period_days * i)
            ps = start - shift
            pe = end - shift
        if pe < data_min:
            break
        if date_col in df_all.columns:
            pw = df_all[(df_all[date_col] >= ps) & (df_all[date_col] <= pe)]
        else:
            pw = pd.DataFrame()
        all_prior_windows.append((pw, ps, pe))

    avail_priors = max(len(all_prior_windows), 1)
    # Slice to user's selected count
    prior_windows = all_prior_windows[:max_prior]

    # Control outputs: calendar disable + slider cap
    pt_data = [
        {"value": "calendar", "label": "Calendar", "disabled": cal_disabled},
        {"value": "rolling", "label": "Rolling"},
    ]
    pt_value = "rolling" if cal_disabled and period_type == "calendar" else dash.no_update
    slider_max = avail_priors
    slider_marks = [{"value": i, "label": str(i)} for i in range(0, slider_max + 1)]

    # Build outputs
    sort_order = sort_order or "volume"
    trend_store = _prepare_trend_store(dff, date_col, sort_order=sort_order,
                                       prior_windows=prior_windows)
    fig_bars = _build_comparison_bars(dff, prior_windows, start, end,
                                      sort_order=sort_order)
    dist_store = _prepare_diag_dist_data(dff, date_col)

    compare_title = "Current Period" if max_prior == 0 else "Current vs Prior Period"
    return (trend_store, fig_bars, dist_store, pt_data, pt_value, slider_max, slider_marks, compare_title)


# --- Unreviewed-only toggle for Diagnosis manager grid ---
clientside_callback(
    """function(checked, fullData) {
        if (!fullData) return window.dash_clientside.no_update;
        if (checked) {
            return fullData.filter(function(r) { return !r.reviewed; });
        }
        return fullData;
    }""",
    Output("diag-mgr-grid", "rowData", allow_duplicate=True),
    Input("diag-mgr-unreviewed-toggle", "checked"),
    State("diag-mgr-full-store", "data"),
    prevent_initial_call=True,
)


# ---------------------------------------------------------------------------
# Clientside callback — renders trend ridgeline from store + settings
# ---------------------------------------------------------------------------
clientside_callback("""function() {
        var fig = window.dash_clientside.diagRidge.renderTrend.apply(null, arguments);
        return window.dash_clientside.chartDeferred.wrap("diag-chart-trend", fig, true);
    }""",
    Output("diag-chart-trend", "figure"),
    Input("diag-chart-trend-store", "data"),
    Input("diag-chart-trend-settings-smooth", "value"),
    Input("diag-chart-trend-settings-type", "value"),
    Input("diag-trend-agg", "value"),
    prevent_initial_call=True,
)


# ---------------------------------------------------------------------------
# Diagnosis distribution chart callback
# ---------------------------------------------------------------------------
@callback(
    Output("diag-chart-dist", "figure"),
    Input("diag-chart-dist-store", "data"),
    Input("diag-dist-mode", "value"),
    Input("diag-dist-agg", "value"),
    Input("diag-dist-settings-smooth", "value"),
    Input("diag-dist-settings-type", "value"),
)
def _update_diag_dist(data, mode, agg, smooth, chart_type):
    if not data:
        return empty_figure("No diagnosis data")

    agg = agg or "M"
    combo = data.get(agg)
    if not combo or not combo.get("series"):
        return empty_figure("No data for selection")

    dates = combo["dates"]
    mode = mode or "pct"
    chart_type = chart_type or "area"
    smooth = smooth or 0

    # Stack order: least common at bottom, most common on top
    raw_series = list(reversed(combo["series"]))

    # Convert to proportions if needed
    n_periods = len(dates)
    if mode == "pct":
        totals = [0.0] * n_periods
        for s in raw_series:
            for i in range(n_periods):
                totals[i] += s["values"][i]
        proc_series = []
        for s in raw_series:
            pct_vals = [
                round(s["values"][i] / totals[i] * 100, 1) if totals[i] > 0 else 0
                for i in range(n_periods)
            ]
            proc_series.append({**s, "values": pct_vals})
    else:
        proc_series = raw_series

    # Apply smoothing
    if smooth > 1:
        proc_series = [
            {**s, "values": _apply_moving_avg(s["values"], smooth)}
            for s in proc_series
        ]

    fig = go.Figure()

    if chart_type == "bar":
        for s in proc_series:
            fig.add_trace(go.Bar(
                x=dates,
                y=s["values"],
                name=s["name"],
                marker_color=s["color"],
                marker_opacity=0.7,
                hovertemplate=(
                    "<b>%{x|%b %Y}</b><br>"
                    + s["name"] + ": %{y:.0f}" + ("%" if mode == "pct" else "")
                    + "<extra></extra>"
                ),
            ))
        fig.update_layout(barmode="stack")
    else:
        stackgroup = "diag" if chart_type == "area" else None
        for s in proc_series:
            fig.add_trace(go.Scatter(
                x=dates,
                y=s["values"],
                name=s["name"],
                mode="lines",
                line=dict(color=s["color"], width=0.5 if chart_type == "area" else 2),
                stackgroup=stackgroup,
                fillcolor=_hex_to_rgba(s["color"], 0.75) if chart_type == "area" else None,
                opacity=0.85,
                hovertemplate=(
                    "<b>%{x|%b %Y}</b><br>"
                    + s["name"] + ": %{y:.0f}" + ("%" if mode == "pct" else "")
                    + "<extra></extra>"
                ),
            ))

    apply_default_layout(fig)
    fig.update_layout(
        height=420,
        yaxis_title="Proportion (%)" if mode == "pct" else "Count",
        showlegend=True,
        legend=dict(
            orientation="h", y=1.02, x=0.5, xanchor="center", yanchor="bottom",
            traceorder="normal",
        ),
        margin=dict(l=48, r=16, t=56, b=40),
        hovermode="x unified",
    )
    if mode == "pct" and chart_type != "line":
        fig.update_yaxes(range=[0, 100])

    return fig


# ==========================================================================
# Diagnosis Classification Manager Callbacks
# ==========================================================================

def _build_diag_mgr_data():
    """Build grid data from ARIA lookup CSV mapping + DB overrides.

    This is the Diagnosis page version — shows the 991 curated ICD codes
    from diagnosis_subcategories.csv (the ARIA lookup mapping), not the
    raw referral extraction.
    """
    import csv as csv_mod
    from pathlib import Path
    from data.reviews_db import get_all_diagnosis_overrides

    overrides = get_all_diagnosis_overrides()

    # Load directly from the curated CSV
    csv_path = Path(__file__).resolve().parent.parent / "data" / "diagnosis_subcategories.csv"
    rows = []
    if csv_path.exists():
        with open(csv_path, newline="", encoding="utf-8") as f:
            for row in csv_mod.DictReader(f):
                code = row["icd_code"].strip()
                if not code:
                    continue
                desc = row.get("description", "").strip()
                cat = row.get("category", "").strip()
                sub = row.get("subcategory", "").strip()

                source = "csv"
                reviewed = False
                if code in overrides:
                    ov = overrides[code]
                    cat = ov["category"]
                    sub = ov["subcategory"]
                    source = ov["source"]
                    reviewed = ov.get("reviewed", False)

                rows.append({
                    "icd_code": code,
                    "description": desc,
                    "category": cat,
                    "subcategory": sub,
                    "patients": 0,  # populated below
                    "source": source,
                    "reviewed": reviewed,
                })

    # Enrich with unique patient counts across ALL datasets carrying DiagnosisCodes
    try:
        from data.loader import (
            load_clinic_visits, load_courses, load_simulations,
            load_treatment_detail, load_weekly_visits, load_billing,
            load_tasks, load_plans, load_workflow, load_procedures, load_otvs,
        )
        code_patients: dict[str, set] = {}

        def _tally(df):
            if df.empty or "DiagnosisCodes" not in df.columns or "PatientId" not in df.columns:
                return
            for pid, codes_str in zip(df["PatientId"], df["DiagnosisCodes"]):
                if pd.isna(codes_str) or pd.isna(pid):
                    continue
                for code in str(codes_str).split(","):
                    c = code.strip()
                    if c:
                        code_patients.setdefault(c, set()).add(pid)

        for loader in (load_clinic_visits, load_courses, load_simulations,
                       load_treatment_detail, load_weekly_visits, load_billing,
                       load_tasks, load_plans, load_workflow, load_procedures,
                       load_otvs):
            try:
                _tally(loader())
            except Exception:
                pass

        for r in rows:
            pts = code_patients.get(r["icd_code"])
            r["patients"] = len(pts) if pts else 0
    except Exception:
        pass

    rows.sort(key=lambda r: r["patients"], reverse=True)

    total = len(rows)
    categorized = sum(1 for r in rows if r["category"])
    with_sub = sum(1 for r in rows if r["subcategory"])
    overridden = sum(1 for r in rows if r["source"] != "csv")
    stats = (
        f"{total:,} codes  |  {categorized:,} categorized  |  "
        f"{with_sub:,} with subcategory  |  {overridden:,} overrides"
    )
    return rows, stats


# Click: reveal overlay + arm the delay interval.
clientside_callback(
    """function(n) {
        if (!n) return [window.dash_clientside.no_update,
                         window.dash_clientside.no_update,
                         window.dash_clientside.no_update];
        return ['heavy-modal-overlay', 0, false];
    }""",
    Output("diag-mgr-overlay", "className"),
    Output("diag-mgr-delay", "n_intervals"),
    Output("diag-mgr-delay", "disabled"),
    Input("diag-mgr-btn", "n_clicks"),
    prevent_initial_call=True,
)

# After ~60ms (overlay has painted), open the heavy modal.
clientside_callback(
    """function(n) {
        if (!n) return [window.dash_clientside.no_update,
                         window.dash_clientside.no_update];
        return [true, true];
    }""",
    Output("diag-mgr-modal", "opened"),
    Output("diag-mgr-delay", "disabled", allow_duplicate=True),
    Input("diag-mgr-delay", "n_intervals"),
    prevent_initial_call=True,
)

# Hide overlay after the modal commits its first paint.
clientside_callback(
    """function(opened) {
        if (!opened) return window.dash_clientside.no_update;
        requestAnimationFrame(function() {
            setTimeout(function() {
                var el = document.getElementById('diag-mgr-overlay');
                if (el) el.className = 'heavy-modal-overlay hidden';
            }, 50);
        });
        return window.dash_clientside.no_update;
    }""",
    Output("diag-mgr-overlay", "className", allow_duplicate=True),
    Input("diag-mgr-modal", "opened"),
    prevent_initial_call=True,
)


@callback(
    Output("diag-mgr-grid", "rowData"),
    Output("diag-mgr-full-store", "data"),
    Output("diag-mgr-stats", "children"),
    Output("diag-mgr-unreviewed-toggle", "checked"),
    Input("diag-mgr-btn", "n_clicks"),
    prevent_initial_call=True,
)
def _diag_mgr_open(n):
    if not n:
        return (dash.no_update,) * 4
    if not can_see_manager_modals():
        return (dash.no_update,) * 4
    rows, stats = _build_diag_mgr_data()
    return rows, rows, stats, False


# Role gate: hide the Diagnosis Classification Manager trigger for non-admins.
@callback(
    Output("diag-mgr-btn", "style"),
    Input("diag-mgr-btn", "id"),
)
def _diag_mgr_role_gate(_id):
    if can_see_manager_modals():
        return dash.no_update
    return {"display": "none"}


@callback(
    Output("diag-mgr-grid", "rowData", allow_duplicate=True),
    Output("diag-mgr-full-store", "data", allow_duplicate=True),
    Output("diag-mgr-stats", "children", allow_duplicate=True),
    Input("diag-mgr-grid", "cellValueChanged"),
    State("diag-mgr-full-store", "data"),
    State("diag-mgr-unreviewed-toggle", "checked"),
    prevent_initial_call=True,
)
def _diag_mgr_save_edit(changed, full_data, unreviewed_only):
    """Save a category, subcategory, or reviewed edit to SQLite."""
    if not changed:
        return dash.no_update, dash.no_update, dash.no_update
    from data.reviews_db import upsert_diagnosis_override, set_diagnosis_reviewed_bulk

    row_data = full_data or []
    row = changed[0].get("data", {}) if isinstance(changed, list) else changed.get("data", {})
    code = row.get("icd_code", "")
    if not code:
        return dash.no_update, dash.no_update, dash.no_update

    col = changed[0].get("colId", "") if isinstance(changed, list) else changed.get("colId", "")
    cat = row.get("category", "")
    sub = row.get("subcategory", "")
    reviewed = row.get("reviewed", False)

    upsert_diagnosis_override(code, category=cat, subcategory=sub, source="manual")
    if col == "reviewed":
        set_diagnosis_reviewed_bulk([code], reviewed=bool(reviewed))
    _invalidate_c2b_cache()

    for r in row_data:
        if r["icd_code"] == code:
            r["category"] = cat
            r["subcategory"] = sub
            r["reviewed"] = reviewed
            r["source"] = "manual"
            break

    total = len(row_data)
    categorized = sum(1 for r in row_data if r.get("category"))
    reviewed_n = sum(1 for r in row_data if r.get("reviewed"))
    stats = (
        f"{total:,} codes  |  {categorized:,} categorized  |  "
        f"{reviewed_n:,} reviewed  |  {total - reviewed_n:,} unreviewed"
    )
    visible = [r for r in row_data if not r.get("reviewed")] if unreviewed_only else row_data
    return visible, row_data, stats


@callback(
    Output("diag-mgr-download", "data"),
    Input("diag-mgr-export-btn", "n_clicks"),
    State("diag-mgr-grid", "rowData"),
    prevent_initial_call=True,
)
def _diag_mgr_export(n, diag_data):
    """Export diagnosis classification as CSV."""
    if not n or not diag_data:
        return dash.no_update
    df = pd.DataFrame(diag_data)[["icd_code", "description", "category", "subcategory", "patients", "source"]]
    df.columns = ["ICD Code", "Description", "Category", "Subcategory", "Patients", "Source"]
    return dcc.send_data_frame(df.to_csv, "diagnosis_classifications.csv", index=False)


# --- Diagnosis Manager: Mark Reviewed ---
@callback(
    Output("diag-mgr-grid", "rowData", allow_duplicate=True),
    Output("diag-mgr-full-store", "data", allow_duplicate=True),
    Output("diag-mgr-stats", "children", allow_duplicate=True),
    Input("diag-mgr-reviewed-btn", "n_clicks"),
    State("diag-mgr-full-store", "data"),
    State("diag-mgr-grid", "selectedRows"),
    State("diag-mgr-unreviewed-toggle", "checked"),
    prevent_initial_call=True,
)
def _diag_mgr_mark_reviewed(n, full_data, selected_rows, unreviewed_only):
    if not n or not full_data or not selected_rows:
        return dash.no_update, dash.no_update, dash.no_update
    from data.reviews_db import set_diagnosis_reviewed_bulk

    row_data = full_data
    codes = [r["icd_code"] for r in selected_rows if r.get("icd_code")]
    if codes:
        set_diagnosis_reviewed_bulk(codes, reviewed=True)

    target_codes = {r["icd_code"] for r in selected_rows if r.get("icd_code")}
    for r in row_data:
        if r.get("icd_code") in target_codes:
            r["reviewed"] = True

    total = len(row_data)
    reviewed_n = sum(1 for r in row_data if r.get("reviewed"))
    categorized = sum(1 for r in row_data if r.get("category"))
    stats = (
        f"{total:,} codes  |  {categorized:,} categorized  |  "
        f"{reviewed_n:,} reviewed  |  {total - reviewed_n:,} unreviewed"
    )
    visible = [r for r in row_data if not r.get("reviewed")] if unreviewed_only else row_data
    return visible, row_data, stats


# --- Diagnosis Manager: Delete Selected ---
@callback(
    Output("diag-mgr-grid", "rowData", allow_duplicate=True),
    Output("diag-mgr-full-store", "data", allow_duplicate=True),
    Output("diag-mgr-stats", "children", allow_duplicate=True),
    Input("diag-mgr-delete-btn", "n_clicks"),
    State("diag-mgr-full-store", "data"),
    State("diag-mgr-grid", "selectedRows"),
    State("diag-mgr-unreviewed-toggle", "checked"),
    prevent_initial_call=True,
)
def _diag_mgr_delete(n, full_data, selected_rows, unreviewed_only):
    if not n or not full_data or not selected_rows:
        return dash.no_update, dash.no_update, dash.no_update
    import csv as csv_mod
    from pathlib import Path

    codes_to_delete = {r["icd_code"] for r in selected_rows if r.get("icd_code")}
    if not codes_to_delete:
        return dash.no_update, dash.no_update, dash.no_update

    # Remove from in-memory data
    row_data = [r for r in full_data if r.get("icd_code") not in codes_to_delete]

    # Remove from CSV file
    csv_path = Path(__file__).resolve().parent.parent / "data" / "diagnosis_subcategories.csv"
    if csv_path.exists():
        with open(csv_path, newline="", encoding="utf-8") as f:
            reader = csv_mod.DictReader(f)
            fieldnames = reader.fieldnames
            kept = [row for row in reader if row["icd_code"].strip() not in codes_to_delete]
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv_mod.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(kept)

    # Remove any DB overrides for deleted codes
    try:
        from data.reviews_db import delete_diagnosis_override
        for code in codes_to_delete:
            delete_diagnosis_override(code)
    except Exception:
        pass

    _invalidate_c2b_cache()

    total = len(row_data)
    categorized = sum(1 for r in row_data if r.get("category"))
    reviewed_n = sum(1 for r in row_data if r.get("reviewed"))
    stats = (
        f"{total:,} codes  |  {categorized:,} categorized  |  "
        f"{reviewed_n:,} reviewed  |  {total - reviewed_n:,} unreviewed"
    )
    visible = [r for r in row_data if not r.get("reviewed")] if unreviewed_only else row_data
    return visible, row_data, stats


# --- Diagnosis Manager: Detail Panel ---
@callback(
    Output("diag-mgr-detail-panel", "style"),
    Output("diag-mgr-detail-title", "children"),
    Output("diag-mgr-detail-grid", "rowData"),
    Input("diag-mgr-detail-store", "data"),
    Input("diag-mgr-detail-close", "n_clicks"),
    prevent_initial_call=True,
)
def _diag_mgr_show_detail(store_data, close_clicks):
    from dash import ctx
    if ctx.triggered_id == "diag-mgr-detail-close":
        return {"display": "none"}, "", []
    if not store_data:
        return dash.no_update, dash.no_update, dash.no_update

    icd_code = store_data.get("icd_code", "")
    if not icd_code:
        return {"display": "none"}, "", []

    from data.loader import load_clinic_visits
    cv = load_clinic_visits()
    if cv.empty or "DiagnosisCodes" not in cv.columns:
        return {"display": "none"}, "", []

    mask = cv["DiagnosisCodes"].fillna("").str.contains(icd_code, case=False, na=False)
    detail = cv[mask].copy()

    cols = ["ScheduledDateTime", "PatientId", "PatientFullName", "ActivityName",
            "DiagnosisCodes", "Department"]
    detail = detail[[c for c in cols if c in detail.columns]]
    if "ScheduledDateTime" in detail.columns:
        detail["ScheduledDateTime"] = detail["ScheduledDateTime"].dt.strftime("%m/%d/%Y").fillna("")

    desc = store_data.get("description", "")[:40]
    title = f"Patients with {icd_code} — {desc} — {len(detail)} records"
    return {"display": "block", "marginTop": "6px"}, title, detail.fillna("").to_dict("records")
