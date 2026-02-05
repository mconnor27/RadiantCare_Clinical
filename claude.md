# Claude Agent Instructions

## Project Overview

RadiantCare Clinical Dashboard — a Dash-based analytics dashboard for a radiation oncology department. Data comes from ARIA (Varian) SQL data warehouse via automated exports.

## Documentation

Read these before making changes:

- `docs/data-dictionary.md` — All 20 CSV data sources, columns, types, joins, business rules
- `docs/design-spec.md` — Colors, layout, components, chart conventions, navigation
- `docs/tech-stack.md` — Dependencies, versions, DMC components, AG Grid config, Plotly defaults
- `docs/decisions.md` — Architectural decision log
- `docs/legacy-logic.md` — Preserved business logic from original app
- `docs/pages/*.md` — Individual page specs (13 pages)

## Architecture

- **Framework:** Dash 3.4+ (Python)
- **UI library:** Dash Mantine Components (DMC) — NOT dash-bootstrap-components
- **Tables:** dash-ag-grid — NOT dash_table (deprecated)
- **Charts:** Plotly 6.5+
- **Icons:** dash-iconify
- **Navigation:** Left sidebar via `dmc.AppShell` + `dmc.NavLink`
- **Layout:** Dark nav sidebar (60px collapsed / 200px expanded) + content area with filter bar + chart grid
- **Data source:** CSV files from `/Users/Mike/Library/CloudStorage/OneDrive-ProvidenceSt.JosephHealth/AURA_Reports/`
- **Mapbox:** Required for Patients and Referrals pages. Token via `MAPBOX_TOKEN` env var.
- **Full stack details:** See `docs/tech-stack.md`

## Project Structure

```
dash_app.py              # Main app entry point
config/settings.py       # Centralized configuration
data/loader.py           # Data loading and preprocessing
components/              # Reusable UI components (nav, filter bar, cards, chart cards)
pages/                   # One file per page (home.py, operations.py, workflow.py, etc.)
utils/charts.py          # Plotly defaults and chart helpers
utils/stats.py           # LOWESS, statistics, projections
assets/                  # Custom CSS and JS (auto-loaded by Dash)
docs/                    # Specs and documentation
```

## Conventions

### Naming
- Page files: lowercase, no spaces (e.g., `pages/clinic_visits.py`)
- Callback IDs: `{page}-{component}-{property}` (e.g., `operations-volume-chart`, `billing-filter-department`)
- Store IDs: `{page}-store-{name}` (e.g., `home-store-filters`)

### Component Patterns
- All charts go in a Chart Card component (title + optional inline controls + plotly figure)
- All KPIs go in a KPI Card component (label + value + optional trend)
- All tables use dash-ag-grid (NOT dash_table) wrapped in a dmc.Paper with title + optional export button
- Page-level filters go in a Filter Bar component at the top of the content area
- Chart-specific controls (type toggle, smoothing, grouping) go inline in the chart card title row

### Plotly Charts
- Always use the default layout from design-spec.md (`DEFAULT_LAYOUT`)
- Use department colors for department-segmented data (Lacey=#2196F3, Centralia=#F44336, Aberdeen=#4CAF50)
- Use the chart color sequence for non-department series
- Horizontal legend above chart, not to the right
- No vertical grid lines, light horizontal grid only

### Data Processing
- Strip `*` prefix from Department column before display or joining
- Deduplicate incremental files by `UniqueRowID` (keep latest)
- Handle comma-separated `DiagnosisCodes` — split before joining to Lookup - Diagnosis
- Handle varying referring physician FK column names (see data-dictionary.md Join Map)
- `PatientMRN` (Treatment Detail) ≠ `PatientId` (other tables) — verify join logic

### What NOT to Do
- Do NOT add dependencies without asking
- Do NOT change the navigation structure without approval
- Do NOT store sensitive data (patient PII) in client-side stores — keep server-side
- Do NOT use top tabs for page navigation (use left sidebar nav only)
- Do NOT add emojis to the UI
- Do NOT create new documentation files without being asked

## Data Processing Transparency

When data processing logic is added or modified, update the help modal to reflect the changes.

### Help Modal Location
- File: `components/header.py` (or equivalent in rebuild)
- Ensure processing notes are clear, concise, and user-friendly

## Four Physicians

All physician filtering/display should recognize these four radiation oncologists:
- Allen, Gregory
- Connor, Michael
- Suszko, Justin
- Tinnel, Brent

## Three Departments

| Department | Color | Machines |
|-----------|-------|---------|
| Lacey | #2196F3 (blue) | TrueBeamNorth, 21EX |
| Centralia | #F44336 (red) | 21iX_CEN |
| Aberdeen | #4CAF50 (green) | 21iX_AB |
