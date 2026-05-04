# Page: Home

## Purpose
At-a-glance KPI summary across all domains. Landing page for all users. Features rolling physician census charts as the centerpiece with sparkline-equipped KPI cards.

## Data Sources
- `Treatment - Detail.csv` — physician census (aggregate daily unique patients per TreatingPhysician), treatment appointment counts
- `Simulations.csv` — weekly simulation counts
- `Clinic Visits.csv` — consult counts (past + future)
- `OTV Audit.csv` — audit pass rate
- `ScheduleUpcoming.csv` — open slot counts by category (forward-looking schedule)
- `Courses.csv` — active course counts
- KPIs pulled from multiple sources (see below)

## Layout
Template B (full-width feature)

## Filter Bar
- Date range only (preset: Today / This Week / This Month / YTD)
- No department or physician filter — Home shows everything

## KPI Cards (top row, each with sparkline)

All KPI cards include a small inline sparkline showing the recent trend. For metrics with historical data only, the sparkline is a solid line. For metrics that include future projections (e.g., Consults per Week, Open Slots), the sparkline uses a solid line for past values and a dotted line for future/projected values.

| KPI | Source | Calculation | Sparkline |
|-----|--------|-------------|-----------|
| Treatment Appointments Today | Treatment - Detail | Count of distinct `SessionUniqueID` for today's date across all locations | Solid line, daily count over last 30 days |
| Simulations per Week | Simulations | Count of simulations in the current calendar week (by `ScheduledDateTime`) | Solid line, weekly count over last 12 weeks |
| Consults per Week | Clinic Visits | Count where `ActivityName = "Consult"` in the current calendar week; includes both past (completed) and future (scheduled) consults | Solid past + dotted future, weekly over last 8 weeks + next 4 weeks |
| OTV Audit Pass Rate | OTV Audit | % where `AuditResult = "OK"` for courses with `FirstTreatmentDate` in YTD period | Solid line, monthly % over last 6 months |
| Open Slots in Next 2 Weeks | ScheduleUpcoming | Count of open/unbooked slots from `ScheduleUpcoming.csv` (`BookingStatus = "Available"`) in the next 14 days, broken down by `Category` (Exam vs Simulation) displayed as sub-values on the card | Dotted line (all future), daily open count over next 14 days |
| Active Courses | Courses | Count where `ClinicalStatus = "ACTIVE"` | Solid line, daily active count over last 30 days |

### Sparkline Implementation Notes
- Sparklines are 34px tall inline line charts rendered inside each KPI card
- Use the same color as the KPI accent/border color
- Solid line (`dash="solid"`) for historical/actual data
- Dotted line (`dash="dot"`) for future/projected data where applicable
- No axis labels, ticks, or grid — just the line shape to convey trend direction
- Data stored in `dcc.Store`, rendered via clientside callback for responsive smoothing

## Charts

### Active Patients by Physician (main chart, full-width, ~400px height)
- **Type:** Line chart, one line per physician + a bold total line
- **X-axis:** Date (rolling 90 days default)
- **Y-axis:** Unique patients treated that day (90-day rolling average)
- **Series:** One line per `TreatingPhysician`, each using chart color sequence. Plus a thicker/bold "Total" line summing all physicians
- **Smoothing:** LOESS smoothing via clientside callback (slider 0-100%)
- **Inline controls:** Time range (30d / 60d / 90d / 6mo / 1y / All), chart type (Area/Line/Bar), smoothing slider
- **Colors:** Chart color sequence, one per MD; Total line in dark gray or black
- **Business logic:** From `Treatment - Detail`, group by `TreatingPhysician` + `TreatmentDate`, count distinct `PatientMRN`. Total line = sum of all physicians' daily counts. Apply 90-day rolling mean to each series
- **Hover:** Show date, physician name, patient count (raw and smoothed)

### Active Patients by Site (secondary chart, full-width, ~350px height)
- **Type:** Line chart, one line per site/department + a bold total line
- **X-axis:** Date (rolling 90 days default, synced with physician chart if possible)
- **Y-axis:** Unique patients treated that day (90-day rolling average)
- **Series:** One line per department (Lacey, Centralia, Aberdeen), each using department colors. Plus a thicker/bold "Total" line
- **Smoothing:** LOESS smoothing via clientside callback (slider 0-100%)
- **Inline controls:** Same time range as physician chart, chart type toggle, smoothing slider
- **Colors:** Department colors (Lacey, Centralia, Aberdeen); Total line in dark gray or black
- **Business logic:** From `Treatment - Detail`, strip `*` prefix from `Department`, group by department + `TreatmentDate`, count distinct `PatientMRN`. Total line = sum of all departments' daily counts. Apply 90-day rolling mean
- **Hover:** Show date, department name, patient count (raw and smoothed)

## Tables
None on Home page — keep it visual.

---

## Implementation Notes

**Reference file:** `pages/home.py` (~1500 lines)

### Architecture Pattern

Home page uses the **server/clientside split** pattern:

1. **Server callbacks** compute raw data on filter/interval change → output to `dcc.Store`
2. **Clientside callbacks** (JS) read stores + settings → render charts with smoothing

This enables instant slider response without server round-trips.

### Key Components

| Component ID | Purpose |
|--------------|---------|
| `home-interval` | 5-minute refresh trigger |
| `home-store-kpi-sparklines` | Raw sparkline data for all KPIs |
| `home-store-md-census` | Physician census raw data |
| `home-store-dept-census` | Department census raw data |
| `home-md-settings-smooth` | Physician chart smoothing slider |
| `home-md-settings-type` | Physician chart type toggle |

### Consult Classification Logic

Clinic visits are classified as Consult vs Follow-Up using a decision tree in `_is_consult()`:

1. Duration > 60 min → Consult
2. Activity name in `{"consult", "consult - special request", "consult- add on"}` → Consult (unless notes match follow-up pattern)
3. Virtual Consult/Follow Up + duration < 60 min → check notes, default Follow-Up
4. Virtual Consult/Follow Up + duration = 60 min → check notes, default Consult
5. "Consult" anywhere in activity name → Consult
6. Otherwise → Follow-Up

### Date Filtering Helpers

Three helper functions handle date range logic relative to **last data date** (not today):

- `_spark_start(last_date, preset)` — how far back for sparkline data
- `_preset_start(last_date, preset)` — main period start for KPIs
- `_prior_range(last_date, preset)` — prior period for trend comparison

### Census Data Builder

`_build_census_data()` transforms grouped data into clientside-ready format:

```python
{
    "dates": ["2025-01-06", ...],  # ISO dates, business days only
    "series": [
        {"name": "Allen, Gregory", "values": [...], "color": "#7C2A83"},
        ...
    ],
    "height": 380,
    "yTitle": "Unique Patients",
}
```

### Callback Wiring

Home page uses only date preset filter (no department/physician). All filter IDs must still be declared as Inputs even if the page doesn't use them.
