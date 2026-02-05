# Page: Home

## Purpose
At-a-glance KPI summary across all domains. Landing page for all users. Features rolling physician census charts as the centerpiece with sparkline-equipped KPI cards.

## Data Sources
- `Treatment - Detail.csv` — physician census (aggregate daily unique patients per TreatingPhysician), treatment appointment counts
- `Simulations.csv` — weekly simulation counts
- `Clinic Visits.csv` — consult counts (past + future)
- `OTV Audit.csv` — audit pass rate
- `Availability.csv` — open slot counts by category
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
| Open Slots in Next 2 Weeks | Availability | Count of open/unbooked slots from `Availability.csv` in the next 14 days, broken down by `Category` (Exam vs Simulation) displayed as sub-values on the card | Dotted line (all future), daily open count over next 14 days |
| Active Courses | Courses | Count where `ClinicalStatus = "ACTIVE"` | Solid line, daily active count over last 30 days |

### Sparkline Implementation Notes
- Sparklines are small (approx 80px wide x 24px tall) inline line charts rendered inside each KPI card
- Use the same color as the KPI accent/border color
- Solid line (`dash="solid"`) for historical/actual data
- Dotted line (`dash="dot"`) for future/projected data where applicable
- No axis labels, ticks, or grid — just the line shape to convey trend direction

## Charts

### Active Patients by Physician (main chart, full-width, ~400px height)
- **Type:** Line chart, one line per physician + a bold total line
- **X-axis:** Date (rolling 90 days default)
- **Y-axis:** Unique patients treated that day (90-day rolling average)
- **Series:** One line per `TreatingPhysician`, each using chart color sequence. Plus a thicker/bold "Total" line summing all physicians
- **Smoothing:** 90-day rolling average applied to each series
- **Inline controls:** Time range (30d / 60d / 90d / 6mo / 1y / All), raw vs smoothed toggle
- **Colors:** Chart color sequence, one per MD; Total line in dark gray or black
- **Business logic:** From `Treatment - Detail`, group by `TreatingPhysician` + `TreatmentDate`, count distinct `PatientMRN`. Total line = sum of all physicians' daily counts. Apply 90-day rolling mean to each series
- **Hover:** Show date, physician name, patient count (raw and smoothed)

### Active Patients by Site (secondary chart, full-width, ~350px height)
- **Type:** Line chart, one line per site/department + a bold total line
- **X-axis:** Date (rolling 90 days default, synced with physician chart if possible)
- **Y-axis:** Unique patients treated that day (90-day rolling average)
- **Series:** One line per department (Lacey, Centralia, Aberdeen), each using department colors. Plus a thicker/bold "Total" line
- **Smoothing:** 90-day rolling average applied to each series
- **Inline controls:** Same time range as physician chart, raw vs smoothed toggle
- **Colors:** Department colors (Lacey, Centralia, Aberdeen); Total line in dark gray or black
- **Business logic:** From `Treatment - Detail`, strip `*` prefix from `Department`, group by department + `TreatmentDate`, count distinct `PatientMRN`. Total line = sum of all departments' daily counts. Apply 90-day rolling mean
- **Hover:** Show date, department name, patient count (raw and smoothed)

## Tables
None on Home page — keep it visual.
