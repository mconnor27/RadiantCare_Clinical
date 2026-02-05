# Tech Stack Specification

## Runtime

| Component | Version | Notes |
|-----------|---------|-------|
| Python | 3.13.3 | Already installed |
| Virtual env | `.venv/` | In project root |

## Core Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| `dash` | ~=3.4.0 | Web framework (includes Dash Core Components, Dash HTML Components) |
| `plotly` | ~=6.5 | Charting library (scatter, line, bar, sankey, mapbox, etc.) |
| `dash-mantine-components` | ~=0.15 | UI component library (layout, nav, cards, inputs, modals, theming) |
| `dash-iconify` | ~=0.1 | Icon components (Material Symbols, Tabler, etc.) |
| `dash-ag-grid` | ~=33.3 | Data tables (replaces deprecated `dash_table`) |
| `pandas` | ~=2.2 | Data loading and processing |
| `numpy` | ~=2.2 | Numerical operations |
| `statsmodels` | ~=0.14 | LOWESS smoothing, statistical analysis |
| `gunicorn` | ~=23.0 | Production WSGI server |

## Optional / As-Needed

| Package | Version | Purpose |
|---------|---------|---------|
| `geopy` | latest | Geocoding for patient/referral maps (City/Zip → lat/lon) |
| `openpyxl` | latest | Excel export if needed |

## What NOT to Use

| Package | Why |
|---------|-----|
| `dash-bootstrap-components` | Replaced by DMC for the rebuild |
| `dash_table.DataTable` | Deprecated by Plotly — use `dash-ag-grid` instead |
| `Font Awesome CDN` | Replaced by `dash-iconify` for icons |

## Dash Mantine Components (DMC) — Key Components

### Layout
- `dmc.AppShell` — main app structure (navbar + content area)
- `dmc.NavLink` — sidebar navigation items
- `dmc.Grid` / `dmc.GridCol` — responsive grid (replaces DBC Row/Col)
- `dmc.Stack` — vertical spacing
- `dmc.Group` — horizontal spacing
- `dmc.Paper` — card/panel container (replaces DBC Card)
- `dmc.Divider` — section separators

### Inputs / Filters
- `dmc.SegmentedControl` — toggle buttons (e.g., YTD / 12mo / All)
- `dmc.MultiSelect` — multi-select dropdown (e.g., physician filter)
- `dmc.Select` — single-select dropdown
- `dmc.DateRangePicker` — date range selection (replaces custom date controls)
- `dmc.Chip` / `dmc.ChipGroup` — department filter pills
- `dmc.Slider` — smoothing control
- `dmc.Switch` — toggle switches

### Display
- `dmc.Text` — text with consistent styling
- `dmc.Title` — headings
- `dmc.Badge` — status badges (PASS/FAIL, Active/Completed)
- `dmc.Tooltip` — hover tooltips
- `dmc.Modal` — help modal and dialogs
- `dmc.Accordion` — collapsible sections
- `dmc.Skeleton` — loading placeholders
- `dmc.Alert` — inline notifications

### Navigation
- `dmc.Tabs` — sub-tabs within a page (e.g., Billing sub-views)
- `dmc.Breadcrumbs` — if needed for drilldowns

## DMC Theming

DMC uses a centralized theme object. Define once, applied everywhere:

```python
theme = dmc.DEFAULT_THEME.copy()
theme.update({
    "primaryColor": "violet",  # closest to #7C2A83
    "colors": {
        "violet": [
            "#F3E8F5", "#E5CCE9", "#D4A9D9", "#C186C9", "#AE63B9",
            "#9B40A9", "#7C2A83", "#6B2472", "#5A1D60", "#49174F"
        ],
    },
    "fontFamily": "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
    "headings": {
        "fontFamily": "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
    },
})
```

Department colors remain as explicit values (not part of the Mantine theme):
```python
DEPARTMENT_COLORS = {
    "Lacey": "#2196F3",
    "Centralia": "#F44336",
    "Aberdeen": "#4CAF50",
}
```

## AG Grid Configuration

Default column definitions for all tables:

```python
DEFAULT_COLUMN_DEFS = {
    "sortable": True,
    "filter": True,
    "resizable": True,
    "floatingFilter": False,  # enable per-page if needed
}

DEFAULT_GRID_OPTIONS = {
    "pagination": True,
    "paginationPageSize": 50,
    "domLayout": "autoHeight",
    "rowSelection": "single",
    "animateRows": True,
}
```

Export button uses AG Grid's built-in `exportDataAsCsv()` — no custom export logic needed.

## Plotly Configuration

### Plotly Layout Defaults

```python
DEFAULT_LAYOUT = dict(
    font=dict(
        family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
        size=13,
    ),
    plot_bgcolor="#FFFFFF",
    paper_bgcolor="#FFFFFF",
    margin=dict(l=48, r=16, t=32, b=48),
    xaxis=dict(gridcolor="#F0F0F0", linecolor="#E0E0E0", showgrid=False),
    yaxis=dict(gridcolor="#F0F0F0", linecolor="#E0E0E0", showgrid=True),
    legend=dict(
        orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0,
        font=dict(size=12),
    ),
    hoverlabel=dict(
        bgcolor="#FFFFFF", bordercolor="#E0E0E0",
        font=dict(size=13, color="#1A1A2E"),
    ),
    colorway=[
        "#7C2A83", "#2196F3", "#F44336", "#4CAF50",
        "#FF9800", "#00BCD4", "#9C27B0", "#795548",
    ],
)
```

### Mapbox

- Style: `"light"` (Mapbox light)
- Token: via `MAPBOX_TOKEN` environment variable
- Default center: `lat=47.0, lon=-122.9` (Olympia/Lacey area)
- Default zoom: `7` (shows western Washington)

## Deployment

| Setting | Value |
|---------|-------|
| Platform | Railway |
| Build | Nixpacks |
| Server | `gunicorn --bind 0.0.0.0:$PORT dash_app:server` |
| Restart | On failure, max 10 retries |

## File Structure

```
RadiantCare_Clinical/
├── dash_app.py              # App entry point, theme, AppShell layout
├── requirements.txt         # Pinned dependencies
├── railway.json             # Deployment config
├── .env                     # MAPBOX_TOKEN, DATA_DIR (not committed)
├── config/
│   └── settings.py          # Constants, paths, physician list, department colors
├── data/
│   └── loader.py            # Data loading, preprocessing, caching
├── components/
│   ├── nav.py               # Sidebar navigation
│   ├── filter_bar.py        # Page-level filter bar
│   ├── kpi_card.py          # KPI card component
│   ├── chart_card.py        # Chart wrapper with title + inline controls
│   └── help_modal.py        # Help/about modal
├── pages/
│   ├── home.py
│   ├── operations.py
│   ├── workflow.py
│   ├── clinic_visits.py
│   ├── simulations.py
│   ├── tasks.py
│   ├── otvs.py
│   ├── billing.py
│   ├── machines.py
│   ├── courses.py
│   ├── plans.py
│   ├── patients.py
│   └── referrals.py
├── utils/
│   ├── charts.py            # Plotly defaults, helper functions
│   └── stats.py             # LOWESS, statistics, projections
├── assets/
│   └── custom.css            # Minimal overrides (DMC handles most styling)
├── docs/                     # Specs (not deployed)
└── archive/                  # Old app code (not deployed)
```
