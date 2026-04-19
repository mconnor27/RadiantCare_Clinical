"""Mobile-only condensed home page — metric toggle + trend/cumulative + availability."""

import dash
import dash_mantine_components as dmc
from dash import callback, clientside_callback, Input, Output, State, dcc, html, no_update
from dash_iconify import DashIconify
import plotly.graph_objects as go
import pandas as pd
import numpy as np

from config.settings import PRIMARY, PRIMARY_DARK, CHART_COLORWAY, FONT_FAMILY, DEPARTMENTS, PHYSICIANS
from utils.charts import apply_default_layout
from statsmodels.nonparametric.smoothers_lowess import lowess as _lowess

from pages.home import (
    _metric_df_tx,
    _metric_df_consults,
    _metric_df_sims,
    _metric_df_refs,
    _build_availability_calendar,
)

dash.register_page(__name__, path="/mobile", name="Mobile", order=99)

PAGE_ID = "mobilehome"

_METRICS = [
    {"value": "tx",       "label": "Treatments", "color": CHART_COLORWAY[0], "date_col": "ScheduledDateTime", "frame_fn": _metric_df_tx,       "physician_col": "TreatingPhysician"},
    {"value": "consults", "label": "Consults",   "color": CHART_COLORWAY[2], "date_col": "ScheduledDateTime", "frame_fn": _metric_df_consults, "physician_col": "AppointmentPhysician"},
    {"value": "sims",     "label": "Sims",       "color": CHART_COLORWAY[1], "date_col": "ScheduledDateTime", "frame_fn": _metric_df_sims,     "physician_col": "ConsultPhysician"},
    {"value": "refs",     "label": "Referrals",  "color": PRIMARY,           "date_col": "Created",           "frame_fn": _metric_df_refs,     "physician_col": None},
]
_METRIC_BY_VALUE = {m["value"]: m for m in _METRICS}

_RANGES = [
    {"value": "ytd", "label": "YTD"},
    {"value": "py",  "label": "Prior Yr"},
    {"value": "12m", "label": "12mo"},
    {"value": "6m",  "label": "6mo"},
    {"value": "3m",  "label": "3mo"},
]


def _resolve_range(range_key, last_date):
    """Return (start, end) timestamps for the selected range, anchored on data's last date."""
    last = pd.Timestamp(last_date).normalize()
    this_year = last.year
    if range_key == "ytd":
        return pd.Timestamp(year=this_year, month=1, day=1), last
    if range_key == "py":
        return pd.Timestamp(year=this_year - 1, month=1, day=1), pd.Timestamp(year=this_year - 1, month=12, day=31)
    if range_key == "12m":
        return last - pd.Timedelta(days=365), last
    if range_key == "6m":
        return last - pd.Timedelta(days=182), last
    if range_key == "3m":
        return last - pd.Timedelta(days=91), last
    return last - pd.Timedelta(days=180), last


def _resolve_prior_range(range_key, last_date):
    """Return (start, end) for the comparison period immediately preceding the selected range."""
    return _resolve_range_offset(range_key, last_date, 1)


def _resolve_range_offset(range_key, last_date, offset):
    """Return (start, end) for the Nth period back (offset=0 current, 1 prior, 2 two-ago, ...)."""
    last = pd.Timestamp(last_date).normalize()
    this_year = last.year
    if offset == 0:
        return _resolve_range(range_key, last)
    if range_key == "ytd":
        y = this_year - offset
        return (pd.Timestamp(year=y, month=1, day=1),
                pd.Timestamp(year=y, month=last.month, day=last.day))
    if range_key == "py":
        y = this_year - 1 - offset
        return (pd.Timestamp(year=y, month=1, day=1),
                pd.Timestamp(year=y, month=12, day=31))
    if range_key == "12m":
        return last - pd.Timedelta(days=365 * (offset + 1)), last - pd.Timedelta(days=365 * offset)
    if range_key == "6m":
        return last - pd.Timedelta(days=182 * (offset + 1)), last - pd.Timedelta(days=182 * offset)
    if range_key == "3m":
        return last - pd.Timedelta(days=91 * (offset + 1)), last - pd.Timedelta(days=91 * offset)
    return None, None


def _period_label(range_key, start, end):
    # Short, single-line labels so they read horizontally on a narrow mobile chart.
    if range_key in ("ytd", "py"):
        return str(start.year)
    # m/yy–m/yy range for 12mo / 6mo / 3mo (e.g. "4/25–4/26").
    return f"{start.month}/{start.strftime('%y')}–{end.month}/{end.strftime('%y')}"


def _empty_fig(title):
    fig = go.Figure()
    apply_default_layout(fig, title=title)
    fig.update_layout(
        annotations=[dict(text="No data", x=0.5, y=0.5, xref="paper", yref="paper", showarrow=False, font=dict(size=13, color="#888"))],
        height=240,
        margin=dict(l=10, r=10, t=36, b=28),
    )
    return fig


def _counts_between(df, date_col, start, end):
    """Daily counts for df[date_col] between start..end, reindexed to fill gaps."""
    if df is None or df.empty or date_col not in df.columns or start is None or end is None:
        return None
    idx = pd.date_range(start=start, end=end, freq="D")
    sub = df[(df[date_col] >= start) & (df[date_col] <= end + pd.Timedelta(days=1))]
    if sub.empty:
        return pd.Series(0, index=idx)
    return (
        sub.groupby(sub[date_col].dt.normalize())
        .size()
        .reindex(idx, fill_value=0)
    )


def _daily_counts(df, date_col, range_key):
    if df is None or df.empty or date_col not in df.columns:
        return None, None
    s = df[date_col].dropna()
    if s.empty:
        return None, None
    last = s.dt.normalize().max()
    start, end = _resolve_range(range_key, last)
    counts = _counts_between(df, date_col, start, end)
    return counts, (start, end)


def _loess_line(counts, frac=0.15):
    if counts is None or len(counts) < 3:
        return None
    x = np.arange(len(counts))
    y = counts.values.astype(float)
    # When there are few points, force a higher frac so LOESS has enough
    # neighbours to actually smooth (otherwise it no-ops or errors).
    effective_frac = max(frac, 3.0 / len(counts))
    effective_frac = min(effective_frac, 1.0)
    try:
        smoothed = _lowess(y, x, frac=effective_frac, return_sorted=False)
        return pd.Series(smoothed, index=counts.index)
    except Exception:
        return None


_RANGE_LABEL = {r["value"]: r["label"] for r in _RANGES}

_TITLE_OPTS = dict(
    font=dict(family=FONT_FAMILY, size=15, weight=600),
    x=0.02, xanchor="left",
    y=0.95, yanchor="top",
)


_AGG_CYCLE = {"D": "W", "W": "M", "M": "D"}
_AGG_LABEL = {"D": "Daily", "W": "Weekly", "M": "Monthly"}


def _build_trend_fig(counts, label, color, range_key, agg="D"):
    title_text = f"{label} — Trend"
    if counts is None:
        return _empty_fig(title_text)

    # Daily business-day series — drives the smoothed line regardless of agg.
    daily_nz = counts[(counts > 0) & (counts.index.weekday < 5)]
    zero_weekdays = []
    if agg == "D":
        nz = daily_nz
        zero_weekdays = counts[(counts == 0) & (counts.index.weekday < 5)].index
    elif agg == "W":
        nz = counts.resample("W-SUN").sum()
        nz = nz[nz > 0]
    else:  # "M"
        nz = counts.resample("MS").sum()
        nz = nz[nz > 0]
    if nz.empty:
        return _empty_fig(title_text)
    fig = go.Figure()

    if agg in ("W", "M"):
        # Use numeric x + custom tick labels so bars are perfectly equidistant.
        # (A datetime axis spaces bars by actual day-gap, giving uneven visual
        # spacing for weeks/months of different lengths.)
        x_idx = list(range(len(nz)))
        if agg == "M":
            labels = [d.strftime("%b '%y") for d in nz.index]
        else:
            labels = [d.strftime("%b %d") for d in nz.index]
        fig.add_trace(go.Bar(
            x=x_idx, y=nz.values,
            customdata=labels,
            marker_color=color, marker_line_width=0,
            opacity=0.45,
            hovertemplate="%{customdata}<br>%{y}<extra></extra>",
            name=_AGG_LABEL[agg],
        ))
    else:
        fig.add_trace(go.Bar(
            x=nz.index, y=nz.values,
            marker_color=color, marker_line_width=0,
            opacity=0.45,
            hovertemplate="%{x|%b %d}<br>%{y}<extra></extra>",
            name=_AGG_LABEL[agg],
        ))

    # Monthly-mode: label each bar with its total. When many bars, drop to a
    # smaller font and skip every other label (anchored to the most recent).
    bar_annotations = []
    if agg == "M":
        n = len(nz)
        dense = n > 8
        font_size = 10 if dense else 11
        keep = set(range(n)) if not dense else {i for i in range(n) if (n - 1 - i) % 2 == 0}
        for i, y_val in enumerate(nz.values):
            if i not in keep:
                continue
            bar_annotations.append(dict(
                x=i, y=y_val,
                text=f"{int(round(y_val)):,}",
                showarrow=False,
                yshift=8,
                font=dict(family=FONT_FAMILY, size=font_size),
            ))
    # Smoothed line only in daily mode.
    if agg == "D":
        line = _loess_line(daily_nz, frac=0.15)
        if line is not None:
            fig.add_trace(go.Scatter(
                x=line.index, y=line.values,
                mode="lines", line=dict(color=color, width=2.5),
                hoverinfo="skip",
                name="Smoothed",
            ))
    apply_default_layout(fig, title=dict(text=title_text, **_TITLE_OPTS))
    if agg == "D":
        xaxis_opts = dict(
            showgrid=False, title=None, tickformat="%b '%y",
            rangebreaks=[
                dict(bounds=["sat", "mon"]),
                dict(values=[d.strftime("%Y-%m-%d") for d in zero_weekdays]),
            ],
        )
    else:
        # Categorical axis — thin out labels when dense so they don't collide.
        n = len(nz)
        if n <= 6:
            keep_ticks = list(range(n))
        elif n <= 12:
            keep_ticks = [i for i in range(n) if (n - 1 - i) % 2 == 0]
        else:
            step = max(1, (n + 5) // 6)
            keep_ticks = list(range(n - 1, -1, -step))[::-1]
        xaxis_opts = dict(
            showgrid=False, title=None,
            tickmode="array",
            tickvals=keep_ticks,
            ticktext=[labels[i] for i in keep_ticks],
            tickangle=0,
            range=[-0.5, n - 0.5],
            zeroline=False,
        )
    fig.update_layout(
        showlegend=False,
        height=240,
        margin=dict(l=10, r=10, t=48, b=28),
        xaxis=xaxis_opts,
        yaxis=dict(title=None),
        bargap=0.1,
        annotations=bar_annotations,
    )
    return fig


_PRIOR_COLOR = "#9CA3AF"
_PRIOR_COLORS_BAR = ["#D1D5DB", "#B3B8C0", "#9CA3AF"]  # oldest → most recent prior
_PRIOR_TEXT_COLORS = ["#4B5563", "#374151", "#1F2937"]  # darker than each bar


def _smoothed_cum(cum, frac=0.05):
    """Return a lightly-smoothed copy of a cumulative series with endpoints pinned."""
    if cum is None or len(cum) < 8:
        return cum
    y = cum.values.astype(float)
    x = np.arange(len(cum))
    try:
        smoothed = _lowess(y, x, frac=frac, return_sorted=False)
    except Exception:
        return cum
    # Pin first and last points to raw values so the displayed line lands
    # exactly on the annotated total and the known origin.
    smoothed[0] = y[0]
    smoothed[-1] = y[-1]
    return pd.Series(smoothed, index=cum.index)


def _build_cum_line_fig(counts, label, color, range_key, prior_counts, prior_shift):
    title_text = f"{label} — Cumulative"
    if counts is None or counts.empty:
        return _empty_fig(title_text)
    cum = counts.cumsum()
    display_cum = _smoothed_cum(cum)
    fig = go.Figure()
    # Prior-period trace — gray, thin, aligned onto current range's x-axis.
    if prior_counts is not None and not prior_counts.empty and prior_shift is not None:
        prior_cum = prior_counts.cumsum()
        prior_display = _smoothed_cum(prior_cum)
        prior_display = prior_display.copy()
        prior_display.index = prior_display.index + prior_shift
        # Raw shifted (for hover values)
        raw_shift = prior_cum.copy()
        raw_shift.index = raw_shift.index + prior_shift
        fig.add_trace(go.Scatter(
            x=prior_display.index, y=prior_display.values,
            customdata=raw_shift.values,
            mode="lines", line=dict(color=_PRIOR_COLOR, width=1.5),
            hovertemplate="%{x|%b %d}<br>%{customdata:,}<extra>prior</extra>",
            name="Prior",
        ))
    # Current trace
    fig.add_trace(go.Scatter(
        x=display_cum.index, y=display_cum.values,
        customdata=cum.values,
        mode="lines", line=dict(color=color, width=2.5),
        hovertemplate="%{x|%b %d}<br>%{customdata:,}<extra></extra>",
        name="Current",
    ))
    # Last-point annotation uses the raw endpoint.
    end_y_raw = cum.iloc[-1]
    end_x = cum.index[-1]
    total_annotation = dict(
        x=end_x, y=end_y_raw,
        text=f"<b>{int(round(end_y_raw)):,}</b>",
        showarrow=False,
        xanchor="right", yanchor="bottom",
        xshift=-4, yshift=4,
        font=dict(family=FONT_FAMILY, size=13, color=color),
    )
    apply_default_layout(fig, title=dict(text=title_text, **_TITLE_OPTS))
    fig.update_layout(
        showlegend=False,
        height=240,
        margin=dict(l=10, r=10, t=48, b=28),
        xaxis=dict(showgrid=False, title=None, tickformat="%b '%y"),
        yaxis=dict(title=None),
        annotations=[total_annotation],
    )
    return fig


def _build_cum_bar_fig(df, date_col, label, color, range_key, n_periods=4):
    """Totals for current + (n_periods-1) prior equivalents as bars, with YTD projection stack."""
    title_text = f"{label} — Cumulative"
    if df is None or df.empty or date_col not in df.columns:
        return _empty_fig(title_text)
    s = df[date_col].dropna()
    if s.empty:
        return _empty_fig(title_text)
    last = s.dt.normalize().max()

    periods = []
    for offset in range(n_periods):
        start, end = _resolve_range_offset(range_key, last, offset)
        if start is None:
            break
        counts = _counts_between(df, date_col, start, end)
        total = int(counts.sum()) if counts is not None else 0
        period = {
            "label": _period_label(range_key, start, end),
            "total": total,
            "is_current": offset == 0,
            "start": start, "end": end,
            "full_year_total": total,  # filled in below for YTD priors
            "rest_of_year": 0,
        }
        # For YTD mode, also compute the rest-of-year actual for prior periods so
        # we can stack each bar up to that year's full-year total.
        if range_key == "ytd" and offset > 0:
            year = start.year
            year_end = pd.Timestamp(year=year, month=12, day=31)
            full_counts = _counts_between(df, date_col, start, year_end)
            fy_total = int(full_counts.sum()) if full_counts is not None else total
            period["full_year_total"] = fy_total
            period["rest_of_year"] = max(0, fy_total - total)
        periods.append(period)
    if not periods:
        return _empty_fig(title_text)
    # Render oldest → newest so the current bar sits on the right.
    periods = list(reversed(periods))

    xs = [p["label"] for p in periods]
    ys = [p["total"] for p in periods]
    rest_ys = [p["rest_of_year"] for p in periods]

    # YTD projection: linear extrapolation of current-year pace to year-end.
    projection_remainder = 0
    projected_end = None
    if range_key == "ytd":
        current = periods[-1]
        year = current["start"].year
        days_elapsed = (last - current["start"]).days + 1
        days_in_year = 366 if pd.Timestamp(year=year, month=1, day=1).is_leap_year else 365
        if days_elapsed > 0:
            rate = current["total"] / days_elapsed
            projected_end = current["total"] + rate * (days_in_year - days_elapsed)
            projection_remainder = max(0, int(round(projected_end - current["total"])))

    # Use numeric x-positions to avoid Plotly's categorical-axis quirks when
    # stacking — map back to labels via tickvals/ticktext.
    idx = list(range(len(xs)))
    fig = go.Figure()

    prior_colors = [_PRIOR_COLORS_BAR[i % len(_PRIOR_COLORS_BAR)] for i in range(len(periods) - 1)]
    bar_colors = prior_colors + [color]
    fig.add_trace(go.Bar(
        x=idx, y=ys,
        marker_color=bar_colors,
        marker_line_width=0,
        customdata=xs,
        hovertemplate="<b>%{customdata}</b><br>%{y:,}<extra></extra>",
        name="Total",
    ))

    bar_annotations = []
    for i, p, y_val in zip(idx, periods, ys):
        # Inner-bar label — YTD-equivalent total. Omit color so annotation
        # inherits layout.font.color, which assets/02_theme.js swaps per theme.
        bar_annotations.append(dict(
            x=i, y=y_val,
            text=f"<b>{y_val:,}</b>",
            showarrow=False,
            yshift=8,
            font=dict(family=FONT_FAMILY, size=11),
        ))

    # YTD: stack each prior bar's rest-of-year actuals on top, lighter shade.
    if range_key == "ytd" and any(r > 0 for r in rest_ys):
        # Per-bar colors — lighter shade of each underlying bar's color.
        rest_colors = []
        for p, base_c in zip(periods, bar_colors):
            if p["is_current"]:
                rest_colors.append(base_c)  # not used but keeps length equal
            else:
                rest_colors.append(base_c)
        fig.add_trace(go.Bar(
            x=idx, y=rest_ys,
            base=ys,
            marker=dict(color=bar_colors, opacity=0.45, line=dict(width=0)),
            customdata=[p["full_year_total"] for p in periods],
            hovertemplate="<b>%{x}</b><br>Full-year: %{customdata:,}<extra></extra>",
            name="Rest of year",
        ))
        # Top-of-full-year annotations for prior bars (non-italic, theme-inherited).
        for i, p in zip(idx, periods):
            if p["is_current"] or p["rest_of_year"] <= 0:
                continue
            bar_annotations.append(dict(
                x=i, y=p["full_year_total"],
                text=f"{p['full_year_total']:,}",
                showarrow=False,
                yshift=8,
                font=dict(family=FONT_FAMILY, size=10),
            ))

    # YTD projection overlay — transparent extension on the current bar only.
    if range_key == "ytd" and projection_remainder > 0:
        fig.add_trace(go.Bar(
            x=[idx[-1]], y=[projection_remainder],
            base=[ys[-1]],
            marker=dict(color=color, opacity=0.25, line=dict(width=0)),
            hovertemplate=f"Projected year-end: <b>{int(round(projected_end)):,}</b><extra></extra>",
            name="Projected",
        ))
        bar_annotations.append(dict(
            x=idx[-1], y=projected_end,
            text=f"<i>{int(round(projected_end)):,}</i>",
            showarrow=False,
            yshift=8,
            font=dict(family=FONT_FAMILY, size=10),
            opacity=0.65,
        ))

    apply_default_layout(fig, title=dict(text=title_text, **_TITLE_OPTS))
    top_val = max(ys + [projected_end or 0] + [p["full_year_total"] for p in periods])
    fig.update_layout(
        barmode="stack",
        showlegend=False,
        height=240,
        margin=dict(l=10, r=10, t=48, b=28),
        xaxis=dict(
            showgrid=False, title=None,
            tickmode="array",
            tickvals=idx, ticktext=xs,
            tickangle=0,
            range=[-0.5, len(xs) - 0.5],
            zeroline=False,
        ),
        yaxis=dict(title=None, range=[0, top_val * 1.15], zeroline=False),
        bargap=0.25,
        annotations=bar_annotations,
    )
    return fig


_SETTINGS_BTN_ID = f"{PAGE_ID}-filters-open"
_SETTINGS_DRAWER_ID = f"{PAGE_ID}-settings-drawer"
_SETTINGS_STORE_ID = f"{PAGE_ID}-settings-store"
_SETTINGS_DEPT_ID = f"{PAGE_ID}-settings-dept"
_SETTINGS_PHYS_ID = f"{PAGE_ID}-settings-phys"


def layout():
    return dmc.Container(
        size="sm", px="xs", pt=4, pb="md",
        children=[
            dcc.Interval(id=f"{PAGE_ID}-interval", interval=5 * 60 * 1000, n_intervals=0),
            dcc.Store(id=_SETTINGS_STORE_ID, data={"dept": "all", "physician": "all"}),

            # Settings button (fixed top-left, mobile only). z-index is below
            # Mantine's modal layer (200) so the drawer overlay naturally hides
            # the gear when opened — no extra callback needed.
            html.Button(
                DashIconify(
                    id=f"{PAGE_ID}-settings-icon",
                    icon="tabler:settings",
                    width=22,
                    color="#000000",
                ),
                id=_SETTINGS_BTN_ID,
                n_clicks=0,
                style={
                    "position": "fixed",
                    "top": 12,
                    "left": 14,
                    "zIndex": 50,
                    "background": "transparent",
                    "border": "none",
                    "padding": "6px",
                    "cursor": "pointer",
                    "outline": "none",
                    "display": "inline-flex",
                    "alignItems": "center",
                    "justifyContent": "center",
                },
            ),

            dmc.Drawer(
                id=_SETTINGS_DRAWER_ID,
                title="Filters",
                position="left",
                size="85%",
                opened=False,
                padding="md",
                children=[
                    dmc.Stack(gap="md", children=[
                        dmc.Stack(gap=4, children=[
                            dmc.Text("Department", size="sm", fw=600, c="dimmed"),
                            dmc.SegmentedControl(
                                id=_SETTINGS_DEPT_ID,
                                value="all",
                                data=[
                                    {"value": "all",       "label": "All"},
                                    {"value": "Lacey",     "label": "Lacey"},
                                    {"value": "Centralia", "label": "Centralia"},
                                    {"value": "Aberdeen",  "label": "Aberdeen"},
                                ],
                                fullWidth=True,
                                color="gray",
                                size="xs",
                            ),
                        ]),
                        dmc.Stack(gap=4, children=[
                            dmc.Group(justify="space-between", children=[
                                dmc.Text("Physician", size="sm", fw=600, c="dimmed"),
                                dmc.Text(id=f"{PAGE_ID}-settings-phys-hint",
                                         size="xs", c="dimmed"),
                            ]),
                            dmc.Select(
                                id=_SETTINGS_PHYS_ID,
                                value="all",
                                data=[{"value": "all", "label": "All"}],
                                clearable=False,
                                size="sm",
                            ),
                        ]),
                    ]),
                ],
            ),

            dmc.Group(
                justify="center",
                mt=0,
                mb="xs",
                children=html.Img(
                    src="/assets/radiantcare.png",
                    style={"height": "38px", "objectFit": "contain"},
                ),
            ),

            dmc.SegmentedControl(
                id=f"{PAGE_ID}-metric",
                value="tx",
                data=[{"value": m["value"], "label": m["label"]} for m in _METRICS],
                fullWidth=True,
                size="sm",
                mb="xs",
                className="mobile-primary-seg",
                styles={"indicator": {"backgroundColor": PRIMARY}},
            ),

            dmc.SegmentedControl(
                id=f"{PAGE_ID}-range",
                value="ytd",
                data=[{"value": r["value"], "label": r["label"]} for r in _RANGES],
                fullWidth=True,
                color="gray",
                size="xs",
                mb="sm",
            ),

            dcc.Loading(
                type="circle",
                children=[
                    dmc.Paper(
                        withBorder=True, radius="md", shadow="xs", p=4, mb="sm",
                        style={"position": "relative"},
                        children=[
                            dmc.Button(
                                "Daily",
                                id=f"{PAGE_ID}-trend-agg-btn",
                                size="compact-xs",
                                radius="sm",
                                style={
                                    "position": "absolute",
                                    "top": 10,
                                    "right": 10,
                                    "zIndex": 2,
                                    "minWidth": "64px",
                                    "backgroundColor": PRIMARY,
                                    "color": "#FFFFFF",
                                    "border": "none",
                                },
                            ),
                            dcc.Store(id=f"{PAGE_ID}-trend-agg", data="D"),
                            dcc.Graph(
                                id=f"{PAGE_ID}-trend",
                                config={"displayModeBar": False, "responsive": True},
                                style={"height": "240px"},
                            ),
                        ],
                    ),
                    dmc.Paper(
                        withBorder=True, radius="md", shadow="xs", p=4, mb="sm",
                        style={"position": "relative"},
                        children=[
                            dmc.Button(
                                "Line",
                                id=f"{PAGE_ID}-cum-mode-btn",
                                size="compact-xs",
                                radius="sm",
                                style={
                                    "position": "absolute",
                                    "top": 10,
                                    "right": 10,
                                    "zIndex": 2,
                                    "minWidth": "64px",
                                    "backgroundColor": PRIMARY,
                                    "color": "#FFFFFF",
                                    "border": "none",
                                },
                            ),
                            dcc.Store(id=f"{PAGE_ID}-cum-mode", data="line"),
                            dcc.Graph(
                                id=f"{PAGE_ID}-cum",
                                config={"displayModeBar": False, "responsive": True},
                                style={"height": "240px"},
                            ),
                        ],
                    ),
                ],
            ),

            dmc.SegmentedControl(
                id=f"{PAGE_ID}-avail-view",
                value="consults",
                data=[
                    {"value": "consults", "label": "Consults"},
                    {"value": "sims",     "label": "Sims"},
                ],
                fullWidth=True,
                size="xs",
                mb="xs",
                className="mobile-primary-seg",
                styles={"indicator": {"backgroundColor": PRIMARY}},
            ),

            dmc.Paper(
                withBorder=True, radius="md", shadow="xs", p=4,
                children=dcc.Graph(
                    id=f"{PAGE_ID}-avail",
                    config={"displayModeBar": False, "responsive": True},
                    style={"height": "300px"},
                ),
            ),
        ],
    )


def _apply_page_filters(df, spec, settings):
    """Apply settings-panel dept + physician filters to a metric dataframe."""
    settings = settings or {}
    dept = settings.get("dept", "all")
    phys = settings.get("physician", "all")
    departments = [dept] if dept and dept != "all" else None
    # Dept filter goes through the frame_fn itself (so refs can map via _OurDept).
    try:
        df = spec["frame_fn"](departments)
    except Exception:
        df = pd.DataFrame()
    # Physician filter — applied post-load on the metric's designated column.
    phys_col = spec.get("physician_col")
    if phys and phys != "all" and phys_col and not df.empty and phys_col in df.columns:
        df = df[df[phys_col] == phys]
    return df


@callback(
    Output(f"{PAGE_ID}-trend", "figure"),
    Output(f"{PAGE_ID}-cum", "figure"),
    Input(f"{PAGE_ID}-metric", "value"),
    Input(f"{PAGE_ID}-range", "value"),
    Input(f"{PAGE_ID}-trend-agg", "data"),
    Input(f"{PAGE_ID}-cum-mode", "data"),
    Input(_SETTINGS_STORE_ID, "data"),
    Input(f"{PAGE_ID}-interval", "n_intervals"),
)
def update_metric_charts(metric, range_key, agg, cum_mode, settings, _n):
    spec = _METRIC_BY_VALUE.get(metric) or _METRICS[0]
    df = _apply_page_filters(None, spec, settings)
    counts, rng = _daily_counts(df, spec["date_col"], range_key)
    agg = agg if agg in _AGG_CYCLE else "D"
    trend_fig = _build_trend_fig(counts, spec["label"], spec["color"], range_key, agg=agg)

    if cum_mode == "bar":
        cum_fig = _build_cum_bar_fig(df, spec["date_col"], spec["label"], spec["color"], range_key)
    else:
        # Line mode — need prior period series shifted onto current x-axis.
        prior_counts = None
        prior_shift = None
        if rng is not None:
            start, _end = rng
            last = df[spec["date_col"]].dropna().dt.normalize().max() if (df is not None and spec["date_col"] in df.columns) else None
            if last is not None:
                p_start, p_end = _resolve_prior_range(range_key, last)
                if p_start is not None:
                    prior_counts = _counts_between(df, spec["date_col"], p_start, p_end)
                    prior_shift = start - p_start
        cum_fig = _build_cum_line_fig(counts, spec["label"], spec["color"], range_key,
                                      prior_counts=prior_counts, prior_shift=prior_shift)
    return trend_fig, cum_fig


clientside_callback(
    """function(n, current) {
        var cycle = {"D": "W", "W": "M", "M": "D"};
        return cycle[current || "D"] || "D";
    }""",
    Output(f"{PAGE_ID}-trend-agg", "data"),
    Input(f"{PAGE_ID}-trend-agg-btn", "n_clicks"),
    State(f"{PAGE_ID}-trend-agg", "data"),
    prevent_initial_call=True,
)


clientside_callback(
    """function(mode) {
        var labels = {"D": "Daily", "W": "Weekly", "M": "Monthly"};
        return labels[mode || "D"] || "Daily";
    }""",
    Output(f"{PAGE_ID}-trend-agg-btn", "children"),
    Input(f"{PAGE_ID}-trend-agg", "data"),
)


clientside_callback(
    """function(n, current) {
        return (current || "line") === "line" ? "bar" : "line";
    }""",
    Output(f"{PAGE_ID}-cum-mode", "data"),
    Input(f"{PAGE_ID}-cum-mode-btn", "n_clicks"),
    State(f"{PAGE_ID}-cum-mode", "data"),
    prevent_initial_call=True,
)


clientside_callback(
    """function(mode) {
        return (mode === "bar") ? "Bar" : "Line";
    }""",
    Output(f"{PAGE_ID}-cum-mode-btn", "children"),
    Input(f"{PAGE_ID}-cum-mode", "data"),
)


@callback(
    Output(f"{PAGE_ID}-avail", "figure"),
    Input(f"{PAGE_ID}-avail-view", "value"),
    Input(_SETTINGS_STORE_ID, "data"),
    Input(f"{PAGE_ID}-interval", "n_intervals"),
)
def update_availability(view, settings, _n):
    view = view if view in ("consults", "sims") else "consults"
    settings = settings or {}
    dept = settings.get("dept", "all")
    departments = [dept] if view == "consults" and dept and dept != "all" else None
    try:
        fig = _build_availability_calendar(departments, consults_only=True, view=view)
        fig.update_layout(
            height=300,
            margin=dict(l=56, r=8, t=24, b=32),
            font=dict(family=FONT_FAMILY, size=10),
        )
        # Nudge the "Next available" annotation down a bit so it doesn't hug
        # the bottom row of cells on the compact mobile chart.
        for ann in fig.layout.annotations:
            if "Next available" in (ann.text or ""):
                ann.y = -0.14
        return fig
    except Exception:
        return _empty_fig("Availability")


# --- Settings drawer wiring -----------------------------------------------
# Re-enable incrementally while debugging JS callback error.

# Group A: icon theme-color swaps.
clientside_callback(
    """function(theme) {
        return (theme === 'dark') ? '#D1D5DB' : '#4B5563';
    }""",
    Output(f"{PAGE_ID}-settings-icon", "color"),
    Input("global-theme-store", "data"),
)

clientside_callback(
    """function(theme) {
        return (theme === 'dark') ? '#D1D5DB' : '#4B5563';
    }""",
    Output("global-theme-icon", "color"),
    Input("global-theme-store", "data"),
)

# Group B: settings-store update.
clientside_callback(
    """function(dept, phys) {
        return {"dept": dept || "all", "physician": phys || "all"};
    }""",
    Output(_SETTINGS_STORE_ID, "data"),
    Input(_SETTINGS_DEPT_ID, "value"),
    Input(_SETTINGS_PHYS_ID, "value"),
)

# Group C: drawer toggle.
clientside_callback(
    """function(n, opened) { return !opened; }""",
    Output(_SETTINGS_DRAWER_ID, "opened"),
    Input(_SETTINGS_BTN_ID, "n_clicks"),
    State(_SETTINGS_DRAWER_ID, "opened"),
    prevent_initial_call=True,
)


@callback(
    Output(_SETTINGS_PHYS_ID, "data"),
    Output(_SETTINGS_PHYS_ID, "value"),
    Output(_SETTINGS_PHYS_ID, "disabled"),
    Output(f"{PAGE_ID}-settings-phys-hint", "children"),
    Input(f"{PAGE_ID}-metric", "value"),
    State(_SETTINGS_PHYS_ID, "value"),
)
def update_physician_options(metric, current_phys):
    spec = _METRIC_BY_VALUE.get(metric) or _METRICS[0]
    phys_col = spec.get("physician_col")
    if not phys_col:
        # Referrals — no physician filter applies.
        return ([{"value": "all", "label": "N/A for Referrals"}],
                "all", True, "no physician filter")

    try:
        df = spec["frame_fn"](None)
    except Exception:
        df = pd.DataFrame()
    if df.empty or phys_col not in df.columns:
        return ([{"value": "all", "label": "All"}], "all", False, "")

    # Restrict to the four named radiation oncologists (CLAUDE.md),
    # filter to ones that actually appear in this metric's data.
    present = set(df[phys_col].dropna().astype(str).unique())
    names = [n for n in PHYSICIANS if n in present]
    data = [{"value": "all", "label": "All"}] + [{"value": n, "label": n} for n in names]
    next_val = current_phys if any(o["value"] == current_phys for o in data) else "all"
    return data, next_val, False, ""
