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
    PHYSICIANS, DEPARTMENTS, DEPARTMENT_COLORS, CHART_COLORWAY, PRIMARY,
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

dash.register_page(__name__, path="/billing", name="Billing", order=7)

PAGE_ID = "billing"
_DEFAULT_DATE_PRESET = "12mo"


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
    },
    "Simulation": {
        "77280", "77285", "77290", "77293", "77011", "76370",
    },
    "Treatment Planning": {
        "77261", "77263", "77295", "77300", "77301",
        "77305", "77306", "77307", "77310", "77315", "77316", "77318",
        "77321", "77328",
    },
    "Physics & Devices": {
        "77331", "77332", "77333", "77334", "77336", "77338", "77370", "77399",
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

CATEGORY_NAMES = list(CPT_CATEGORIES.keys())

CATEGORY_SLUGS = {
    "E&M": "em", "Simulation": "simulation", "Treatment Planning": "planning",
    "Physics & Devices": "physics", "Treatment Delivery": "delivery",
    "Image Guidance": "igrt", "Treatment Management": "management",
    "Brachytherapy": "brachy", "Procedures": "procedures",
    "Drug Administration": "drugs", "Radiopharmaceutical": "radiopharm",
}
SLUG_TO_CATEGORY = {v: k for k, v in CATEGORY_SLUGS.items()}

CATEGORY_COLORS = {}
for _i, _cat in enumerate(CATEGORY_NAMES):
    CATEGORY_COLORS[_cat] = CHART_COLORWAY[_i % len(CHART_COLORWAY)]


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
    if any(kw in nl for kw in ("medicaid", "apple health", "molina")):
        return "Medicaid"
    return "Private"


def _merge_rvu(df, rvu):
    """Add wRVU and Fac_Total_RVU columns to billing dataframe."""
    if df.empty:
        df["wRVU"] = 0.0
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

    # Exact match
    exact_key = df["_base"] + "|" + df["_mod"] + "|" + df["_yr"].astype(str)
    df["wRVU"] = exact_key.map(wrvu_dict)
    df["Fac_Total_RVU"] = exact_key.map(total_dict)

    # Fallback to Global for unmatched
    mask = df["wRVU"].isna()
    if mask.any():
        global_key = df.loc[mask, "_base"] + "||" + df.loc[mask, "_yr"].astype(str)
        df.loc[mask, "wRVU"] = global_key.map(wrvu_dict)
        df.loc[mask, "Fac_Total_RVU"] = global_key.map(total_dict)

    df["wRVU"] = df["wRVU"].fillna(0)
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
                       value_col=None, agg="sum", y_title="Count", stacked=True):
    """Build census-format store data for smoothChartWithType.

    If value_col is None, counts rows per group per month.
    If value_col is given, sums that column per group per month.
    """
    if df.empty or date_col not in df.columns:
        return None

    df = df.copy()
    df["_month"] = df[date_col].dt.to_period("M").dt.to_timestamp()

    months = pd.date_range(df["_month"].min(), df["_month"].max(), freq="MS")
    dates = [d.strftime("%Y-%m-%d") for d in months]

    series = []
    for name in group_names:
        sub = df[df[group_col] == name] if group_col in df.columns else df
        if value_col and value_col in sub.columns:
            monthly = sub.groupby("_month")[value_col].sum()
        else:
            monthly = sub.groupby("_month").size()
        monthly = monthly.reindex(months, fill_value=0)
        series.append({
            "name": name,
            "values": monthly.tolist(),
            "color": group_colors.get(name, CHART_COLORWAY[len(series) % len(CHART_COLORWAY)]),
        })

    return {
        "dates": dates,
        "series": series,
        "yTitle": y_title,
        "stacked": stacked,
        "height": 380,
    }


def _build_cumulative_data(df, date_col, start, end, date_preset, y_title="Cumulative"):
    """Build prior-period overlay cumulative data for renderCumulative."""
    if df.empty or date_col not in df.columns:
        return None

    today = pd.Timestamp.now().normalize()
    end_norm = min(end.normalize(), today)
    start_norm = start.normalize()
    period_days = (end_norm - start_norm).days + 1
    if period_days < 2:
        return None

    day_indices = list(range(period_days))

    def _cum_for_window(w_start, w_end):
        sub = df[(df[date_col] >= w_start) & (df[date_col] <= w_end)]
        daily = sub.groupby(sub[date_col].dt.normalize()).size()
        idx = pd.date_range(w_start.normalize(), w_end.normalize(), freq="D")
        daily = daily.reindex(idx, fill_value=0)
        return daily.cumsum().tolist()

    def _cum_rvu_for_window(w_start, w_end):
        sub = df[(df[date_col] >= w_start) & (df[date_col] <= w_end)]
        if "wRVU" not in sub.columns:
            return _cum_for_window(w_start, w_end)
        daily = sub.groupby(sub[date_col].dt.normalize())["wRVU"].sum()
        idx = pd.date_range(w_start.normalize(), w_end.normalize(), freq="D")
        daily = daily.reindex(idx, fill_value=0)
        return daily.cumsum().tolist()

    current_vals = _cum_for_window(start, end_norm)

    # Build tick labels
    tick_positions = []
    tick_labels = []
    d = start_norm
    while d <= end_norm:
        pos = (d - start_norm).days
        if d.day == 1:
            tick_positions.append(pos)
            tick_labels.append(d.strftime("%b"))
        d += timedelta(days=1)

    # Prior periods
    data_min = df[date_col].min() if not df.empty else start
    prior = []
    if date_preset != "all":
        for i in range(1, 6):
            try:
                p_start = start - pd.DateOffset(years=i)
                p_end = end_norm - pd.DateOffset(years=i)
            except Exception:
                continue
            if p_end < data_min:
                break
            vals = _cum_for_window(p_start, p_end)
            if vals and any(v > 0 for v in vals):
                if len(vals) < period_days:
                    vals = vals + [vals[-1] if vals else 0] * (period_days - len(vals))
                elif len(vals) > period_days:
                    vals = vals[:period_days]
                label = f"{p_start.year}" if date_preset in ("ytd", "last_year") else p_start.strftime("%b '%y")
                prior.append({"label": label, "values": vals, "color": "#D1D5DB"})

    current_label = f"{start.year}" if date_preset in ("ytd", "last_year") else start.strftime("%b '%y")
    if len(current_vals) < period_days:
        current_vals = current_vals + [None] * (period_days - len(current_vals))

    return {
        "mode": "prior",
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
        "sliceBreakdown": {"periods": [], "slices": []},
        "height": 350,
        "yTitle": y_title,
    }


def _build_cumulative_rvu_data(df, date_col, start, end, date_preset, y_title="Cumulative wRVU"):
    """Build prior-period overlay cumulative wRVU data."""
    if df.empty or date_col not in df.columns or "wRVU" not in df.columns:
        return None

    today = pd.Timestamp.now().normalize()
    end_norm = min(end.normalize(), today)
    start_norm = start.normalize()
    period_days = (end_norm - start_norm).days + 1
    if period_days < 2:
        return None

    day_indices = list(range(period_days))

    def _cum_for_window(w_start, w_end):
        sub = df[(df[date_col] >= w_start) & (df[date_col] <= w_end)]
        daily = sub.groupby(sub[date_col].dt.normalize())["wRVU"].sum()
        idx = pd.date_range(w_start.normalize(), w_end.normalize(), freq="D")
        daily = daily.reindex(idx, fill_value=0)
        return daily.cumsum().tolist()

    current_vals = _cum_for_window(start, end_norm)

    tick_positions = []
    tick_labels = []
    d = start_norm
    while d <= end_norm:
        pos = (d - start_norm).days
        if d.day == 1:
            tick_positions.append(pos)
            tick_labels.append(d.strftime("%b"))
        d += timedelta(days=1)

    data_min = df[date_col].min() if not df.empty else start
    prior = []
    if date_preset != "all":
        for i in range(1, 6):
            try:
                p_start = start - pd.DateOffset(years=i)
                p_end = end_norm - pd.DateOffset(years=i)
            except Exception:
                continue
            if p_end < data_min:
                break
            vals = _cum_for_window(p_start, p_end)
            if vals and any(v > 0 for v in vals):
                if len(vals) < period_days:
                    vals = vals + [vals[-1] if vals else 0] * (period_days - len(vals))
                elif len(vals) > period_days:
                    vals = vals[:period_days]
                label = f"{p_start.year}" if date_preset in ("ytd", "last_year") else p_start.strftime("%b '%y")
                prior.append({"label": label, "values": vals, "color": "#D1D5DB"})

    current_label = f"{start.year}" if date_preset in ("ytd", "last_year") else start.strftime("%b '%y")
    if len(current_vals) < period_days:
        current_vals = current_vals + [None] * (period_days - len(current_vals))

    return {
        "mode": "prior",
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
        "sliceBreakdown": {"periods": [], "slices": []},
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
    broad_order = ["Medicare", "Medicaid", "Private", "Other/Unknown"]
    broad_colors_map = {
        "Medicare": "#2196F3", "Medicaid": "#4CAF50",
        "Private": "#FF9800", "Other/Unknown": "#9CA3AF",
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
# Filter Bar
# ---------------------------------------------------------------------------

def _build_filter_bar():
    """Two-row filter bar: dimension filters + date controls."""
    return dmc.Paper(
        children=[
            # Row 1: dimension filters
            dmc.Group(
                children=[
                    department_chips(PAGE_ID),
                    dmc.Select(
                        id=f"{PAGE_ID}-filter-physician",
                        data=[{"value": p, "label": p} for p in PHYSICIANS],
                        placeholder="Physician",
                        clearable=True,
                        size="sm",
                        w=200,
                    ),
                    dmc.SegmentedControl(
                        id=f"{PAGE_ID}-filter-codetype",
                        data=[
                            {"value": "all", "label": "All"},
                            {"value": "Professional", "label": "Prof"},
                            {"value": "Technical", "label": "Tech"},
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
                    dmc.MultiSelect(
                        id=f"{PAGE_ID}-filter-category",
                        data=[{"value": c, "label": c} for c in CATEGORY_NAMES],
                        placeholder="All Categories",
                        clearable=True,
                        size="sm",
                        w=250,
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
    {"value": "category", "label": "By Category"},
    {"value": "department", "label": "By Department"},
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
                dmc.Title("Billing", order=2, className="page-title"),
                _build_filter_bar(),
            ],
        ),

        # KPI row — dynamic (zero-count categories hidden)
        dmc.Grid(id=f"{PAGE_ID}-kpi-row", gutter="sm"),

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
                        extra_controls=[
                            dmc.SegmentedControl(
                                id=f"{PAGE_ID}-vol-slice",
                                data=_SLICE_TOGGLE, value="category", size="xs",
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
                                id=f"{PAGE_ID}-volcum-slice",
                                data=_SLICE_TOGGLE, value="category", size="xs",
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
                        extra_controls=[
                            dmc.SegmentedControl(
                                id=f"{PAGE_ID}-rvu-slice",
                                data=_SLICE_TOGGLE, value="category", size="xs",
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
                                id=f"{PAGE_ID}-rvucum-slice",
                                data=_SLICE_TOGGLE, value="category", size="xs",
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
                        ],
                    ),
                    span={"base": 12, "md": 6},
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
    # Store outputs (7)
    Output(f"{PAGE_ID}-store-kpi-sparklines", "data"),
    Output(f"{PAGE_ID}-store-volume", "data"),
    Output(f"{PAGE_ID}-store-volume-cum", "data"),
    Output(f"{PAGE_ID}-store-rvu", "data"),
    Output(f"{PAGE_ID}-store-rvu-cum", "data"),
    Output(f"{PAGE_ID}-store-payor-event", "data"),
    Output(f"{PAGE_ID}-store-payor-patient", "data"),
    # Inputs
    Input(f"{PAGE_ID}-interval", "n_intervals"),
    Input(f"{PAGE_ID}-filter-daterange", "start_date"),
    Input(f"{PAGE_ID}-filter-daterange", "end_date"),
    Input(f"{PAGE_ID}-filter-department", "value"),
    Input(f"{PAGE_ID}-filter-physician", "value"),
    Input(f"{PAGE_ID}-filter-codetype", "value"),
    Input(f"{PAGE_ID}-filter-charge-status", "value"),
    Input(f"{PAGE_ID}-filter-category", "value"),
    Input(f"{PAGE_ID}-filter-date-preset", "value"),
)
def update_billing(_n, start_date, end_date, departments, physician,
                   codetype, charge_status, categories, date_preset):
    """Master callback: KPIs, sparklines, volume, RVU, payor stores."""
    from data.loader import load_billing, load_patients, load_rvu_lookup

    n_kpis = len(CATEGORY_SLUGS)
    empty_stores = [None] * 7

    # ------------------------------------------------------------------
    # Load data
    # ------------------------------------------------------------------
    try:
        billing = load_billing()
    except Exception:
        return [], *empty_stores

    if billing.empty or "DateOfService" not in billing.columns:
        return [], *empty_stores

    try:
        rvu = load_rvu_lookup()
    except Exception:
        rvu = pd.DataFrame()

    try:
        patients = load_patients()
    except Exception:
        patients = pd.DataFrame()

    # ------------------------------------------------------------------
    # Enrich billing data
    # ------------------------------------------------------------------
    df = billing.copy()

    # Category + charge status
    df["_base_code"] = df["ProcedureCode"].apply(_strip_modifier)
    df["Category"] = df["_base_code"].apply(_assign_category)
    df["ChargeStatus"] = df["ProcedureCode"].apply(_derive_charge_status)

    # RVU
    if not rvu.empty:
        df = _merge_rvu(df, rvu)
    else:
        df["wRVU"] = 0.0
        df["Fac_Total_RVU"] = 0.0

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
    mask = (df["DateOfService"] >= start) & (df["DateOfService"] <= end)
    if departments and "Department" in df.columns:
        mask &= df["Department"].isin(departments)
    if physician:
        phys_mask = pd.Series(False, index=df.index)
        for col in ("SupervisingPhysician", "AttendingPhysician"):
            if col in df.columns:
                phys_mask |= df[col] == physician
        mask &= phys_mask
    if codetype and codetype != "all" and "CodeType" in df.columns:
        mask &= df["CodeType"] == codetype
    if charge_status and charge_status != "all":
        mask &= df["ChargeStatus"] == charge_status
    if categories:
        mask &= df["Category"].isin(categories)

    bf = df.loc[mask].copy()

    # Prior period for trend comparison
    p_start, p_end = _prior_range(start, end, date_preset or "12mo")
    prior_mask = (df["DateOfService"] >= p_start) & (df["DateOfService"] <= p_end)
    if departments and "Department" in df.columns:
        prior_mask &= df["Department"].isin(departments)
    if physician:
        phys_mask_p = pd.Series(False, index=df.index)
        for col in ("SupervisingPhysician", "AttendingPhysician"):
            if col in df.columns:
                phys_mask_p |= df[col] == physician
        prior_mask &= phys_mask_p
    if codetype and codetype != "all" and "CodeType" in df.columns:
        prior_mask &= df["CodeType"] == codetype
    if charge_status and charge_status != "all":
        prior_mask &= df["ChargeStatus"] == charge_status
    if categories:
        prior_mask &= df["Category"].isin(categories)
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

    # Wrap cards in GridCols with equal width to fit one row
    n_active = len(kpi_children)
    if n_active > 0:
        # 12-col grid: compute span to fit all in one row
        span_md = max(1, round(12 / n_active, 1))
        kpi_children = [
            dmc.GridCol(
                card,
                span={"base": 6, "sm": 4, "md": span_md},
                style={"display": "flex"},
            )
            for card in kpi_children
        ]

    # ------------------------------------------------------------------
    # Volume stores (by category + by department)
    # ------------------------------------------------------------------
    vol_by_cat = _build_census_data(
        bf, "DateOfService", start, end,
        "Category", [c for c in CATEGORY_NAMES if c in bf["Category"].unique()],
        CATEGORY_COLORS, y_title="Billing Events",
    )
    dept_names = [d for d in DEPARTMENTS if d in bf["Department"].unique()] if "Department" in bf.columns else []
    vol_by_dept = _build_census_data(
        bf, "DateOfService", start, end,
        "Department", dept_names, DEPARTMENT_COLORS, y_title="Billing Events",
    )
    volume_store = {"byCategory": vol_by_cat, "byDepartment": vol_by_dept}

    # Cumulative volume
    vol_cum = _build_cumulative_data(bf, "DateOfService", start, end, date_preset or "12mo",
                                     y_title="Cumulative Events")

    # ------------------------------------------------------------------
    # RVU stores (by category + by department)
    # ------------------------------------------------------------------
    rvu_by_cat = _build_census_data(
        bf, "DateOfService", start, end,
        "Category", [c for c in CATEGORY_NAMES if c in bf["Category"].unique()],
        CATEGORY_COLORS, value_col="wRVU", y_title="wRVU",
    )
    rvu_by_dept = _build_census_data(
        bf, "DateOfService", start, end,
        "Department", dept_names, DEPARTMENT_COLORS,
        value_col="wRVU", y_title="wRVU",
    )
    rvu_store = {"byCategory": rvu_by_cat, "byDepartment": rvu_by_dept}

    # Cumulative wRVU
    rvu_cum = _build_cumulative_rvu_data(bf, "DateOfService", start, end, date_preset or "12mo",
                                         y_title="Cumulative wRVU")

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

    return (*kpi_cards, sparkline_data, volume_store, vol_cum,
            rvu_store, rvu_cum, payor_event, payor_patient)


# ---------------------------------------------------------------------------
# Clientside: Volume & RVU Charts (with slice toggle)
# ---------------------------------------------------------------------------

# Wrapper JS to select byCategory/byDepartment from store, then pass to census
_SLICE_JS = """
function(storeData, sliceMode, smoothPct, chartType, currentFig) {
    if (!storeData) return window.dash_clientside.no_update;
    var key = sliceMode === "department" ? "byDepartment" : "byCategory";
    var rawData = storeData[key];
    if (!rawData) return window.dash_clientside.no_update;
    return window.dash_clientside.census.smoothChartWithType(rawData, smoothPct, chartType, currentFig);
}
"""

clientside_callback(
    _SLICE_JS,
    Output(f"{PAGE_ID}-chart-vol-trend", "figure"),
    Input(f"{PAGE_ID}-store-volume", "data"),
    Input(f"{PAGE_ID}-vol-slice", "value"),
    Input(f"{PAGE_ID}-vol-settings-smooth", "value"),
    Input(f"{PAGE_ID}-vol-settings-type", "value"),
    State(f"{PAGE_ID}-chart-vol-trend", "figure"),
)

clientside_callback(
    _SLICE_JS,
    Output(f"{PAGE_ID}-chart-rvu-trend", "figure"),
    Input(f"{PAGE_ID}-store-rvu", "data"),
    Input(f"{PAGE_ID}-rvu-slice", "value"),
    Input(f"{PAGE_ID}-rvu-settings-smooth", "value"),
    Input(f"{PAGE_ID}-rvu-settings-type", "value"),
    State(f"{PAGE_ID}-chart-rvu-trend", "figure"),
)

# Cumulative charts (no smooth slider — pass 0 for smoothPct)
_CUM_JS = """
function(rawData, chartType, currentFig) {
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
function(storeData, mode) {
    if (!storeData) return window.dash_clientside.no_update;
    var d = storeData[mode] || storeData["actual"];
    if (!d || !d.labels || d.labels.length === 0) {
        return {data: [], layout: Object.assign({}, window.dmc_default_layout || {}, {
            xaxis: {visible: false}, yaxis: {visible: false},
            annotations: [{text: "No payor data", xref: "paper", yref: "paper",
                x: 0.5, y: 0.5, showarrow: false, font: {size: 14, color: "#9CA3AF"}}],
            height: 350, margin: {l: 40, r: 20, t: 20, b: 40}
        })};
    }
    var labels = d.labels.slice().reverse();
    var values = d.values.slice().reverse();
    var colors = d.colors.slice().reverse();
    return {
        data: [{
            y: labels, x: values, orientation: "h", type: "bar",
            marker: {color: colors},
            hovertemplate: "%{y}: %{x:,}<extra></extra>"
        }],
        layout: Object.assign({}, window.dmc_default_layout || {}, {
            height: 380,
            margin: {l: 160, r: 16, t: 8, b: 40},
            xaxis: {title: {text: "Count"}, showgrid: true, gridcolor: "#F0F0F0"},
            yaxis: {showgrid: false},
        })
    };
}
"""

clientside_callback(
    _PAYOR_BAR_JS,
    Output(f"{PAGE_ID}-chart-payor-event", "figure"),
    Input(f"{PAGE_ID}-store-payor-event", "data"),
    Input(f"{PAGE_ID}-payor-event-mode", "value"),
)

clientside_callback(
    _PAYOR_BAR_JS,
    Output(f"{PAGE_ID}-chart-payor-patient", "figure"),
    Input(f"{PAGE_ID}-store-payor-patient", "data"),
    Input(f"{PAGE_ID}-payor-patient-mode", "value"),
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
