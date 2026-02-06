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

## Reference Implementation

**`pages/home.py` is the reference implementation.** Before building or modifying any page, read home.py to understand:
- Server/clientside callback split pattern
- KPI card with sparkline wiring
- Census data builder structure
- Filter callback input requirements
- Date filtering helpers (`_spark_start`, `_preset_start`, `_prior_range`)

### Pages Needing Upgrade

Pages 01-05 (Operations, Workflow, Clinic Visits, Simulations, Tasks) were built earlier without the clientside pattern. They need refactoring to add:
- `dcc.Store` for raw chart data
- Clientside callbacks for smoothing/chart type switching
- `chart_settings_popover()` for interactive controls (gear icon)
- KPI sparklines where appropriate

**When modifying these pages, upgrade them to match home.py patterns.**

## Page Building Checklist

When building a new page from stub:

1. **Read the page spec** in `docs/pages/NN-pagename.md`
2. **Verify data columns** — Before referencing any column, confirm it exists in the loader output:
   ```python
   df = load_<dataset>()
   print(df.columns.tolist())  # Verify column names
   ```
3. **Create layout structure:**
   - Page title (centered, purple `#7C2A83`, bold)
   - Filter bar with page-appropriate filters
   - KPI grid (4-6 cards, span 2.4 each on md+)
   - Chart rows (half-width pairs in `dmc.Grid`)
   - Optional data table (full-width)
   - `dcc.Interval` for refresh + `dcc.Store` for raw data

4. **Wire callback with ALL filter IDs as Inputs** — Even unused ones:
   ```python
   @callback(
       Output("page-kpi-row", "children"),
       Input("page-interval", "n_intervals"),
       Input("page-filter-date-preset", "value"),
       Input("page-filter-daterange", "value"),
       Input("page-filter-department", "value"),
       Input("page-filter-physician", "value"),  # MUST include even if page can't filter by physician
   )
   ```

5. **For interactive charts, use clientside callbacks:**
   - Server callback outputs raw data to `dcc.Store`
   - Clientside callback reads store + settings, outputs figure
   - Add functions to `assets/clientside_smooth.js` namespace

## Data Loading Verification

**Before using any column, verify it exists.** Common column mapping issues:

| Source Column | Normalized Column | File |
|---------------|-------------------|------|
| `Location` | `Department` | Treatment, Daily Volume |
| `DepartmentName` | `Department` | Clinic Visits, Billing, Availability |
| `TreatmentDate` | `ScheduledDateTime` | Treatment-Detail |
| `PatientMRN` | `PatientId` | Treatment-Detail |
| `ActivityStatus` | `Status` | Clinic Visits, Simulations |
| `Departments` | `Department` | Courses, Plans (comma-separated, take first) |

**Datasets without Department column** (must merge via `_patient_department_map()`):
- Workflow.csv
- Simulations.csv

## Date Filtering Pattern

Always use **data-relative dates**, not `pd.Timestamp.now()`:

```python
last_date = df["ScheduledDateTime"].dt.normalize().max()
start = last_date - pd.Timedelta(days=30)  # Relative to last data date
```

This handles data lag gracefully (data may be 1-2 days behind "today").

## Common Pitfalls

| Issue | Cause | Fix |
|-------|-------|-----|
| Filter doesn't update chart | Filter ID not in callback Inputs | Add ALL filter IDs as Inputs |
| Department filter shows nothing | `*` prefix not stripped | Use `_clean_department()` |
| Physician filter empty | NaN values in dropdown | Use `.dropna().unique()` |
| Sparkline not updating | Wrong store/callback wiring | Check store ID matches clientside input |
| Slow chart interaction | Server-side smoothing | Move to clientside callback |
| Missing Department column | Dataset doesn't have it | Merge via `_patient_department_map()` |
| Wrong date range | Using `now()` instead of data max | Use `df["date_col"].max()` as reference |

## Stub Pages to Complete

| Page | Primary Dataset | Key Metrics | Complexity |
|------|-----------------|-------------|------------|
| Billing | Billing.csv | Revenue, charges, procedures | Medium |
| Courses | Courses.csv | Treatment courses, durations | Medium |
| Machines | Machine Errors.csv | Downtime, error rates | Medium |
| Plans | Plans.csv | Plan complexity, approval times | Medium |
| Patients | Treatment-Detail + Referrals | Geography, demographics | High (Mapbox) |
| Referrals | Referrals.csv | Sources, conversion | High (Mapbox) |
| OTVs | OTV Audit.csv | Compliance, discrepancies | Low |

## Counting Semantics

When counting appointments/visits/treatments, clarify what's being counted:
- **Appointment records**: Count rows where `AppointmentInstanceFlag = 1`
- **Treatment sessions**: Count unique `SessionUniqueID`
- **Patients**: Count unique `PatientId`
- **Courses**: Count unique `CourseId`

Do NOT count individual fields within a treatment (inflates numbers).
