"""Machine Statistics page — lifetime and yearly performance metrics per linac."""

import dash
import dash_mantine_components as dmc
from dash import callback, clientside_callback, ClientsideFunction, Input, Output, State, dcc, html
from dash_iconify import DashIconify
import plotly.graph_objects as go
import pandas as pd
import numpy as np

from config.settings import (
    CHART_COLORWAY, PRIMARY, MACHINE_DEPT, MACHINE_COLORS,
    DEFAULT_LAYOUT, FONT_FAMILY, NEUTRAL,
)
from data.loader import load_machine_statistics
from components.kpi_card import kpi_card, kpi_placeholder
from components.chart_card import chart_card, register_chart_callbacks
from utils.charts import empty_figure

dash.register_page(__name__, path="/machine-statistics", name="Machine Statistics", order=9)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PAGE_ID = "mstats"

ALL_MACHINES = ["TrueBeamNorth", "21EX", "21iX_CEN", "21iX_AB", "6EX"]
ACTIVE_MACHINES = ["TrueBeamNorth", "21EX", "21iX_CEN", "21iX_AB"]

MACHINE_DISPLAY = {
    "TrueBeamNorth": "TrueBeam North",
    "21EX": "21EX",
    "21iX_CEN": "21iX Centralia",
    "21iX_AB": "21iX Aberdeen",
    "6EX": "6EX (Retired)",
}

CHIP_COLORS = {
    "TrueBeamNorth": "blue", "21EX": "blue",
    "21iX_CEN": "red", "21iX_AB": "green", "6EX": "gray",
}


def _machine_color(machine):
    return MACHINE_COLORS.get(machine, CHART_COLORWAY[0])


def _fmt_number(n):
    """Format large numbers with commas."""
    if pd.isna(n):
        return "—"
    return f"{int(n):,}"


def _fmt_dose(n):
    """Format dose in Gy."""
    if pd.isna(n):
        return "—"
    return f"{n:,.0f} Gy"


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------

layout = dmc.Stack(
    gap=16,
    className="page-content",
    children=[
        # --- Header ---
        dmc.Box(
            className="page-sticky-header",
            children=[
                dmc.Title("Machine Statistics", order=2, className="page-title"),
                dmc.Paper(
                    children=[
                        dmc.Group(
                            children=[
                                # Machine filter
                                dmc.Group(gap=8, align="center", children=[
                                    dmc.Text("Machine", size="sm", c="#9CA3AF", fw=500),
                                    dmc.ChipGroup(
                                        id=f"{PAGE_ID}-filter-machine",
                                        children=[
                                            dmc.Chip(
                                                MACHINE_DISPLAY.get(m, m),
                                                value=m, size="sm", variant="filled",
                                                color=CHIP_COLORS.get(m, "blue"),
                                            )
                                            for m in ALL_MACHINES
                                        ],
                                        value=list(ACTIVE_MACHINES),
                                        multiple=True,
                                    ),
                                ]),
                                # Data section toggle
                                dmc.Group(gap=8, align="center", children=[
                                    dmc.Text("Data", size="sm", c="#9CA3AF", fw=500),
                                    dmc.SegmentedControl(
                                        id=f"{PAGE_ID}-filter-section",
                                        data=[
                                            {"value": "real", "label": "Real Patients"},
                                            {"value": "all", "label": "All Data"},
                                        ],
                                        value="real", size="xs",
                                    ),
                                ]),
                                # Current year handling
                                dmc.Group(gap=8, align="center", children=[
                                    dmc.Text("Current Year", size="sm", c="#9CA3AF", fw=500),
                                    dmc.SegmentedControl(
                                        id=f"{PAGE_ID}-filter-ytd",
                                        data=[
                                            {"value": "project", "label": "Project YTD"},
                                            {"value": "actual", "label": "Actual YTD"},
                                            {"value": "exclude", "label": "Exclude"},
                                        ],
                                        value="project", size="xs",
                                    ),
                                ]),
                            ],
                            gap="lg", wrap="wrap",
                        ),
                    ],
                    p="sm", px="md", radius="md", shadow="xs", withBorder=True,
                ),
            ],
        ),

        # --- Aggregate KPI row ---
        dmc.Grid(id=f"{PAGE_ID}-kpi-row", gutter=16, children=[
            dmc.GridCol(kpi_placeholder(), span={"base": 12, "sm": 6, "md": 3}) for _ in range(4)
        ]),

        # --- Machine cards ---
        dmc.Grid(id=f"{PAGE_ID}-machine-cards", gutter=16, children=[]),

        # --- Machine age timeline ---
        dmc.Paper(
            id=f"{PAGE_ID}-timeline-paper",
            children=[
                dmc.Text("Machine Age Timeline", size="sm", fw=500, c=NEUTRAL["text_secondary"], mb=8),
                html.Div(id=f"{PAGE_ID}-timeline-container"),
            ],
            p="sm", pb=8, radius="md", shadow="xs", withBorder=True,
        ),

        # --- Yearly trend charts ---
        dmc.Grid(gutter=16, children=[
            dmc.GridCol(
                chart_card(
                    f"{PAGE_ID}-chart-sessions", "Sessions by Year",
                    chart_types=[
                        {"value": "area", "label": "Area"},
                        {"value": "line", "label": "Line"},
                        {"value": "bar", "label": "Bar"},
                    ],
                    show_smooth=True, smooth_max=10, smooth_default=3,
                    store_data=True,
                    extra_controls_left=[
                        dmc.SegmentedControl(
                            id=f"{PAGE_ID}-sessions-metric",
                            data=[
                                {"value": "sessions", "label": "Sessions"},
                                {"value": "fractions", "label": "Fractions"},
                            ],
                            value="sessions", size="xs",
                        ),
                    ],
                ),
                span={"base": 12, "md": 6},
            ),
            dmc.GridCol(
                chart_card(
                    f"{PAGE_ID}-chart-patients", "Patients by Year",
                    chart_types=[
                        {"value": "area", "label": "Area"},
                        {"value": "line", "label": "Line"},
                        {"value": "bar", "label": "Bar"},
                    ],
                    show_smooth=True, smooth_max=10, smooth_default=3,
                    store_data=True,
                ),
                span={"base": 12, "md": 6},
            ),
        ]),
        dmc.Grid(gutter=16, children=[
            dmc.GridCol(
                chart_card(
                    f"{PAGE_ID}-chart-dose-per-fx", "Avg Dose per Fraction (Gy)",
                    chart_types=[
                        {"value": "line", "label": "Line"},
                        {"value": "area", "label": "Area"},
                        {"value": "bar", "label": "Bar"},
                    ],
                    show_smooth=True, smooth_max=10, smooth_default=3,
                    show_grouping=False,
                    store_data=True,
                ),
                span={"base": 12, "md": 6},
            ),
            dmc.GridCol(
                chart_card(
                    f"{PAGE_ID}-chart-fields-per-fx",
                    "Fields per Fraction",
                    chart_types=[
                        {"value": "line", "label": "Line"},
                        {"value": "area", "label": "Area"},
                        {"value": "bar", "label": "Bar"},
                    ],
                    show_smooth=True, smooth_max=10, smooth_default=3,
                    show_grouping=False,
                    store_data=True,
                ),
                span={"base": 12, "md": 6},
            ),
        ]),

        # --- Stores & Interval ---
        dcc.Interval(id=f"{PAGE_ID}-interval", interval=600_000, n_intervals=0, max_intervals=0),  # fires once on mount; no background refresh (daily data + global refresh button)
    ],
)


# ---------------------------------------------------------------------------
# Register chart settings callbacks
# ---------------------------------------------------------------------------
register_chart_callbacks([
    (f"{PAGE_ID}-chart-sessions", f"{PAGE_ID}-chart-sessions", f"{PAGE_ID}-chart-sessions-store"),
    (f"{PAGE_ID}-chart-patients", f"{PAGE_ID}-chart-patients", f"{PAGE_ID}-chart-patients-store"),
    {"sid": f"{PAGE_ID}-chart-dose-per-fx", "gid": f"{PAGE_ID}-chart-dose-per-fx",
     "store_id": f"{PAGE_ID}-chart-dose-per-fx-store", "show_grouping": False},
    {"sid": f"{PAGE_ID}-chart-fields-per-fx", "gid": f"{PAGE_ID}-chart-fields-per-fx",
     "store_id": f"{PAGE_ID}-chart-fields-per-fx-store", "show_grouping": False},
])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_data(section_filter):
    """Load and split machine statistics by section."""
    df = load_machine_statistics()
    if df.empty:
        return pd.DataFrame(), pd.DataFrame()

    prefix = "3-Real Patients" if section_filter == "real" else "1-All Data"
    yearly_prefix = "4-Real Patients by Year" if section_filter == "real" else "2-All Data by Year"

    lifetime = df[df["Section"] == prefix].copy()
    yearly = df[df["Section"] == yearly_prefix].copy()
    return lifetime, yearly


def _apply_ytd(mdf, ytd_mode, current_year, year_fraction):
    """Apply current-year handling (project / actual / exclude) to a per-machine
    yearly frame. Returns a frame; does not mutate the input."""
    if ytd_mode == "exclude":
        return mdf[mdf["DataYear"] != current_year]
    if ytd_mode == "project" and year_fraction > 0:
        is_current = mdf["DataYear"] == current_year
        if is_current.any():
            mdf = mdf.copy()
            scale = 1 / year_fraction
            for col in ["TotalFields", "TotalDose_Gy", "TotalFractions",
                        "TotalSessions", "TotalPatients"]:
                if col in mdf.columns:
                    mdf.loc[is_current, col] = (mdf.loc[is_current, col] * scale).round(0)
            fx = mdf.loc[is_current, "TotalFractions"]
            dose = mdf.loc[is_current, "TotalDose_Gy"]
            mdf.loc[is_current, "AvgDosePerFx_Gy"] = (dose / fx.replace(0, np.nan)).round(4)
    return mdf


# ---------------------------------------------------------------------------
# Main callback — KPIs + machine cards + timeline
# ---------------------------------------------------------------------------

@callback(
    Output(f"{PAGE_ID}-kpi-row", "children"),
    Output(f"{PAGE_ID}-machine-cards", "children"),
    Output(f"{PAGE_ID}-timeline-container", "children"),
    Output(f"{PAGE_ID}-timeline-paper", "h"),
    Input(f"{PAGE_ID}-interval", "n_intervals"),
    Input(f"{PAGE_ID}-filter-machine", "value"),
    Input(f"{PAGE_ID}-filter-section", "value"),
    Input(f"{PAGE_ID}-filter-ytd", "value"),
)
def update_kpis_cards_timeline(_, machines, section, ytd_mode):
    if not machines:
        empty_graph = dcc.Graph(figure=empty_figure("Select at least one machine"),
                                config={"displayModeBar": False}, style={"height": "100px"})
        return [], [], empty_graph, 150

    lifetime, yearly = _get_data(section)
    if lifetime.empty:
        empty_graph = dcc.Graph(figure=empty_figure("No data available"),
                                config={"displayModeBar": False}, style={"height": "100px"})
        return [], [], empty_graph, 150

    lt = lifetime[lifetime["Machine"].isin(machines)]

    # --- Aggregate KPIs ---
    total_patients = lt["TotalPatients"].sum()
    total_sessions = lt["TotalSessions"].sum()
    total_fractions = lt["TotalFractions"].sum()
    total_dose = lt["TotalDose_Gy"].sum()
    total_fields = lt["TotalFields"].sum()

    kpi_children = [
        dmc.GridCol(kpi_card(
            "Total Patients", _fmt_number(total_patients),
            accent_color=PRIMARY,
        ), span={"base": 6, "md": 2.4}),
        dmc.GridCol(kpi_card(
            "Total Sessions", _fmt_number(total_sessions),
            accent_color=CHART_COLORWAY[1],
        ), span={"base": 6, "md": 2.4}),
        dmc.GridCol(kpi_card(
            "Total Fractions", _fmt_number(total_fractions),
            accent_color=CHART_COLORWAY[4],
        ), span={"base": 6, "md": 2.4}),
        dmc.GridCol(kpi_card(
            "Total Dose", _fmt_dose(total_dose),
            accent_color=CHART_COLORWAY[2],
        ), span={"base": 6, "md": 2.4}),
        dmc.GridCol(kpi_card(
            "Total Fields", _fmt_number(total_fields),
            accent_color=CHART_COLORWAY[3],
        ), span={"base": 6, "md": 2.4}),
    ]

    # --- Machine cards (ordered to match chip order) ---
    current_year = pd.Timestamp.now().year
    year_fraction = pd.Timestamp.now().timetuple().tm_yday / 365.25
    machine_cards = []
    lt_indexed = lt.set_index("Machine")
    for m in ALL_MACHINES:
        if m not in machines or m not in lt_indexed.index:
            continue
        row = lt_indexed.loc[m]
        color = _machine_color(m)
        dept = MACHINE_DEPT.get(m, "")

        # Operating life
        op_start = row.get("OperatingLife")
        last_tx = row.get("MostRecentTreatment")
        if pd.notna(op_start):
            years_active = (pd.Timestamp.now() - op_start).days / 365.25
            op_str = f"Since {op_start.strftime('%b %Y')}"
            years_str = f"{years_active:.1f} years"
        else:
            op_str = "—"
            years_str = ""

        # Check if retired (last treatment > 1 year ago)
        is_retired = False
        if pd.notna(last_tx):
            days_since = (pd.Timestamp.now() - last_tx).days
            is_retired = days_since > 365

        # Mini sparkline from yearly data (respects current-year handling)
        m_yearly = yearly[yearly["Machine"] == m].sort_values("DataYear")
        m_yearly = _apply_ytd(m_yearly, ytd_mode, current_year, year_fraction)
        spark_vals = m_yearly["TotalSessions"].tolist() if not m_yearly.empty else None
        spark_labels = m_yearly["DataYear"].astype(int).astype(str).tolist() if not m_yearly.empty else None

        status_badge = dmc.Badge(
            "Retired" if is_retired else "Active",
            color="gray" if is_retired else "green",
            variant="light", size="sm",
        )

        card = dmc.Paper(
            children=[
                dmc.Group(justify="space-between", mb=4, children=[
                    dmc.Group(gap="xs", children=[
                        dmc.Box(
                            style={"width": 12, "height": 12, "borderRadius": "50%",
                                   "backgroundColor": color, "flexShrink": 0},
                        ),
                        dmc.Text(MACHINE_DISPLAY.get(m, m), fw=600, size="md"),
                    ]),
                    status_badge,
                ]),
                dmc.Text(f"{dept} Department", size="xs", c=NEUTRAL["text_muted"], mb=8),
                dmc.SimpleGrid(
                    cols=3, spacing="xs", verticalSpacing=4,
                    children=[
                        dmc.Stack(gap=0, children=[
                            dmc.Text("Patients", size="xs", c=NEUTRAL["text_muted"]),
                            dmc.Text(_fmt_number(row["TotalPatients"]), fw=600, size="sm"),
                        ]),
                        dmc.Stack(gap=0, children=[
                            dmc.Text("Sessions", size="xs", c=NEUTRAL["text_muted"]),
                            dmc.Text(_fmt_number(row["TotalSessions"]), fw=600, size="sm"),
                        ]),
                        dmc.Stack(gap=0, children=[
                            dmc.Text("Fractions", size="xs", c=NEUTRAL["text_muted"]),
                            dmc.Text(_fmt_number(row["TotalFractions"]), fw=600, size="sm"),
                        ]),
                        dmc.Stack(gap=0, children=[
                            dmc.Text("Dose", size="xs", c=NEUTRAL["text_muted"]),
                            dmc.Text(_fmt_dose(row["TotalDose_Gy"]), fw=600, size="sm"),
                        ]),
                        dmc.Stack(gap=0, children=[
                            dmc.Text("Fields", size="xs", c=NEUTRAL["text_muted"]),
                            dmc.Text(_fmt_number(row["TotalFields"]), fw=600, size="sm"),
                        ]),
                        dmc.Stack(gap=0, children=[
                            dmc.Text("Avg Gy/Fx", size="xs", c=NEUTRAL["text_muted"]),
                            dmc.Text(f"{row['AvgDosePerFx_Gy']:.2f}", fw=600, size="sm"),
                        ]),
                    ],
                ),
                dmc.Divider(my=8),
                dmc.Group(gap="xs", children=[
                    DashIconify(icon="tabler:clock", width=14, color=NEUTRAL["text_muted"]),
                    dmc.Text(op_str, size="xs", c=NEUTRAL["text_secondary"]),
                    dmc.Text(f"({years_str})", size="xs", c=NEUTRAL["text_muted"]) if years_str else None,
                ]),
                # Mini sparkline
                *(
                    [dcc.Graph(
                        figure=_mini_sparkline(spark_vals, spark_labels, color),
                        config={"displayModeBar": False, "scrollZoom": False},
                        style={"height": "50px", "marginTop": "8px"},
                    )] if spark_vals and len(spark_vals) > 1 else []
                ),
            ],
            p="md", radius="md", shadow="xs", withBorder=True,
            style={"borderLeft": f"4px solid {color}"},
        )
        machine_cards.append(
            dmc.GridCol(card, span={"base": 12, "sm": 6, "lg": 2.4 if len(machines) >= 5 else 3})
        )

    # --- Machine age timeline ---
    BAR_HEIGHT_PX = 56
    PAPER_OVERHEAD_PX = 40
    n_machines = len([m for m in machines if m in lt_indexed.index])
    chart_h = n_machines * BAR_HEIGHT_PX
    paper_h = chart_h + PAPER_OVERHEAD_PX

    timeline_fig = _build_timeline(lifetime, machines, chart_height=chart_h)

    timeline_graph = dcc.Graph(
        figure=timeline_fig,
        config={"displayModeBar": False, "scrollZoom": False},
        style={"height": f"{chart_h}px"},
    )

    return kpi_children, machine_cards, timeline_graph, paper_h


def _mini_sparkline(values, labels, color):
    """Tiny inline sparkline for machine cards."""
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=labels, y=values,
        mode="lines",
        line=dict(color=color, width=1.5),
        fill="tozeroy",
        fillcolor=f"rgba({int(color[1:3], 16)},{int(color[3:5], 16)},{int(color[5:7], 16)},0.1)",
        hovertemplate="%{x}: %{y:,.0f}<extra></extra>",
    ))
    fig.update_layout(
        margin=dict(l=0, r=0, t=0, b=0),
        height=50,
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(visible=False),
        yaxis=dict(visible=False),
        showlegend=False,
        dragmode=False,
        hovermode="x",
        hoverlabel=dict(
            bgcolor=color, font=dict(color="white", size=10),
            bordercolor=color,
        ),
    )
    return fig


def _build_timeline(lifetime, machines, chart_height=None):
    """Build horizontal machine age timeline chart."""
    fig = go.Figure()

    lt = lifetime[lifetime["Machine"].isin(machines)].copy()
    if lt.empty:
        return empty_figure("No data")

    # Sort by operating life start (oldest first at top)
    lt = lt.sort_values("OperatingLife", ascending=True)
    now = pd.Timestamp.now().normalize()

    machines_data = []
    for _, row in lt.iterrows():
        m = row["Machine"]
        color = _machine_color(m)
        start = row["OperatingLife"]
        end = row["MostRecentTreatment"]

        if pd.isna(start):
            continue
        if pd.isna(end):
            end = now

        days_since = (now - end).days
        is_retired = days_since > 365
        years = (end - start).days / 365.25
        display_name = MACHINE_DISPLAY.get(m, m)
        machines_data.append((display_name, start, end, years, is_retired, color, row))

    # Build using scatter + shapes for reliable date-axis bars
    for i, (display_name, start, end, years, is_retired, color, row) in enumerate(machines_data):
        opacity = 0.35 if is_retired else 0.85
        # Add a shape for the bar
        fig.add_shape(
            type="rect",
            x0=start, x1=end,
            y0=i - 0.35, y1=i + 0.35,
            fillcolor=color,
            opacity=opacity,
            line=dict(width=0),
            layer="below",
        )

        # Invisible scatter for hover
        mid = start + (end - start) / 2
        fig.add_trace(go.Scatter(
            x=[mid], y=[i],
            mode="markers",
            marker=dict(size=0.1, color="rgba(0,0,0,0)"),
            hovertemplate=(
                f"<b>{display_name}</b><br>"
                f"{'Retired' if is_retired else 'Active'}<br>"
                f"{start.strftime('%b %Y')} — {end.strftime('%b %Y')}<br>"
                f"{years:.1f} years<br>"
                f"{_fmt_number(row['TotalSessions'])} sessions"
                "<extra></extra>"
            ),
            showlegend=False,
        ))

        # Label inside bar
        fig.add_annotation(
            x=mid, y=i,
            text=f"{years:.0f} yrs",
            showarrow=False,
            font=dict(
                color="white" if not is_retired else "#666",
                size=13, family=FONT_FAMILY, weight="bold" if not is_retired else "normal",
            ),
        )

    y_labels = [d[0] for d in machines_data]
    # Compute x-axis range: earliest start to now + small padding
    all_starts = [d[1] for d in machines_data]
    x_min = min(all_starts) - pd.Timedelta(days=180)
    x_max = now + pd.Timedelta(days=180)

    fig.update_layout(
        font=DEFAULT_LAYOUT["font"],
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        hoverlabel=DEFAULT_LAYOUT["hoverlabel"],
        xaxis=dict(
            type="date",
            showgrid=False,
            showline=False,
            dtick="M24",
            tickformat="%Y",
            range=[x_min, x_max],
        ),
        yaxis=dict(
            tickvals=list(range(len(y_labels))),
            ticktext=y_labels,
            showgrid=False,
            showline=False,
            zeroline=False,
        ),
        margin=dict(l=120, r=20, t=8, b=20),
        showlegend=False,
        transition={"duration": 0},
        **({"height": chart_height} if chart_height else {}),
    )
    return fig


# ---------------------------------------------------------------------------
# Yearly trend charts — server callback outputs store data
# ---------------------------------------------------------------------------

@callback(
    Output(f"{PAGE_ID}-chart-sessions-store", "data"),
    Output(f"{PAGE_ID}-chart-patients-store", "data"),
    Output(f"{PAGE_ID}-chart-dose-per-fx-store", "data"),
    Output(f"{PAGE_ID}-chart-fields-per-fx-store", "data"),
    Input(f"{PAGE_ID}-interval", "n_intervals"),
    Input(f"{PAGE_ID}-filter-machine", "value"),
    Input(f"{PAGE_ID}-filter-section", "value"),
    Input(f"{PAGE_ID}-filter-ytd", "value"),
    Input(f"{PAGE_ID}-sessions-metric", "value"),
    running=[
        (Output(f"{PAGE_ID}-chart-sessions-loading", "visible"), True, False),
        (Output(f"{PAGE_ID}-chart-patients-loading", "visible"), True, False),
        (Output(f"{PAGE_ID}-chart-dose-per-fx-loading", "visible"), True, False),
        (Output(f"{PAGE_ID}-chart-fields-per-fx-loading", "visible"), True, False),
    ],
)
def update_yearly_stores(_, machines, section, ytd_mode, metric):
    empty = {}
    if not machines:
        return empty, empty, empty, empty

    _, yearly = _get_data(section)
    if yearly.empty:
        return empty, empty, empty, empty

    yr = yearly[yearly["Machine"].isin(machines)].copy()
    yr = yr.sort_values("DataYear")

    current_year = pd.Timestamp.now().year
    day_of_year = pd.Timestamp.now().timetuple().tm_yday
    year_fraction = day_of_year / 365.25

    # Process each machine (apply YTD logic)
    processed = {}
    for m in machines:
        mdf = yr[yr["Machine"] == m].copy()
        if mdf.empty:
            continue
        mdf = _apply_ytd(mdf, ytd_mode, current_year, year_fraction)
        if not mdf.empty:
            processed[m] = mdf

    if not processed:
        return empty, empty, empty, empty

    # Union of all years across machines → shared x-axis
    all_years = sorted(set().union(*(df["DataYear"].unique() for df in processed.values())))
    dates = [f"{int(y)}-01-01" for y in all_years]

    def _build_census(value_col, y_title, fill_zero=True, chart_id=None, hover_decimals=None):
        series = []
        for m in machines:
            if m not in processed:
                continue
            mdf = processed[m].set_index("DataYear").reindex(all_years)
            raw = mdf[value_col]
            if fill_zero:
                raw = raw.fillna(0)
            vals = [None if pd.isna(v) else round(float(v), 3) for v in raw]
            series.append({
                "name": MACHINE_DISPLAY.get(m, m),
                "values": vals,
                "color": _machine_color(m),
            })
        return {"dates": dates, "series": series, "yTitle": y_title,
                "stacked": True, "chartId": chart_id, "hoverDecimals": hover_decimals}

    # Sessions / Fractions (toggle via metric input)
    sessions_col = "TotalFractions" if metric == "fractions" else "TotalSessions"
    sessions_label = "Fractions" if metric == "fractions" else "Sessions"
    sessions_data = _build_census(sessions_col, sessions_label,
                                  chart_id=f"{PAGE_ID}-chart-sessions")
    patients_data = _build_census("TotalPatients", "Patients",
                                  chart_id=f"{PAGE_ID}-chart-patients")
    dose_fx_data = _build_census("AvgDosePerFx_Gy", "Avg Dose/Fx (Gy)", fill_zero=False,
                                 chart_id=f"{PAGE_ID}-chart-dose-per-fx", hover_decimals=2)

    # Fields per fraction — computed ratio
    fpf_series = []
    for m in machines:
        if m not in processed:
            continue
        mdf = processed[m].set_index("DataYear").reindex(all_years)
        fpf = (mdf["TotalFields"] / mdf["TotalFractions"].replace(0, np.nan)).round(3)
        fpf_series.append({
            "name": MACHINE_DISPLAY.get(m, m),
            "values": [None if pd.isna(v) else round(float(v), 3) for v in fpf],
            "color": _machine_color(m),
        })
    fields_fx_data = {"dates": dates, "series": fpf_series, "yTitle": "Fields / Fraction",
                      "stacked": True, "chartId": f"{PAGE_ID}-chart-fields-per-fx",
                      "hoverDecimals": 2}

    return sessions_data, patients_data, dose_fx_data, fields_fx_data


# ---------------------------------------------------------------------------
# Yearly chart clientside callbacks (census pattern)
# ---------------------------------------------------------------------------

_CENSUS_JS = """function(data, smooth, chartType, stack, fig) {
    return window.dash_clientside.census.smoothChartWithType(
        data, smooth, chartType, fig, stack
    );
}"""

_CENSUS_JS_NO_STACK = """function(data, smooth, chartType, fig) {
    return window.dash_clientside.census.smoothChartWithType(
        data, smooth, chartType, fig, "grouped"
    );
}"""

# Top row — sessions & patients (stackable)
for _cid in [f"{PAGE_ID}-chart-sessions", f"{PAGE_ID}-chart-patients"]:
    clientside_callback(
        _CENSUS_JS,
        Output(_cid, "figure"),
        Input(f"{_cid}-store", "data"),
        Input(f"{_cid}-settings-smooth", "value"),
        Input(f"{_cid}-settings-type", "value"),
        Input(f"{_cid}-settings-stack", "value"),
        State(_cid, "figure"),
        prevent_initial_call=True,
    )

# Bottom row — per-fraction ratios (always grouped, no stack toggle)
for _cid in [f"{PAGE_ID}-chart-dose-per-fx", f"{PAGE_ID}-chart-fields-per-fx"]:
    clientside_callback(
        _CENSUS_JS_NO_STACK,
        Output(_cid, "figure"),
        Input(f"{_cid}-store", "data"),
        Input(f"{_cid}-settings-smooth", "value"),
        Input(f"{_cid}-settings-type", "value"),
        State(_cid, "figure"),
        prevent_initial_call=True,
    )
