# Page: OTVs

## Purpose
Monitor on-treatment visit compliance and weekly check activity. Answers: "Are physicians seeing patients the right number of times during treatment? Who has extra or missing visits?"

## Data Sources
- `OTV Audit.csv` — on-treatment visit compliance audit
- `Weekly Visits.csv` — individual weekly check appointments

## Layout
Template A (KPI + Charts + Table)

## Filter Bar
- Date range: based on `FirstTreatmentDate` (OTV) or `AppointmentDateTime` (Weekly Visits)
- Department: multi-select pills
- Physician: multi-select dropdown
- Status: pills (Active / Completed / All) — based on `ClinicalStatus`
- Audit result: pills (All / OK / Extra / Too Few)

## KPI Cards

| KPI | Source | Calculation |
|-----|--------|-------------|
| Total Courses Audited | OTV Audit | Count for filtered period |
| Compliance Rate | OTV Audit | % where `AuditResult = "OK"` |
| Extra Visit Rate | OTV Audit | % where `AuditResult = "Extra Visit(s)"` |
| Too Few Rate | OTV Audit | % where `AuditResult = "Too Few"` |
| Weekly Checks (period) | Weekly Visits | Count for filtered period |

## Charts

### Audit Result Distribution (half-width)
- **Type:** Donut chart or horizontal stacked bar
- **Values:** OK, Extra Visit(s), Too Few
- **Colors:** `--success`, `--warning`, `--error`

### Compliance by Physician (half-width)
- **Type:** Grouped bar chart
- **X-axis:** Physician
- **Y-axis:** Count or %
- **Series:** OK, Extra, Too Few
- **Purpose:** Which physicians have compliance issues?

### Compliance Trend (half-width)
- **Type:** Line chart
- **X-axis:** Month
- **Y-axis:** Compliance rate (%)
- **Series:** By department or overall

### Weekly Visit Volume (half-width)
- **Type:** Bar chart
- **X-axis:** Week
- **Y-axis:** Weekly check count
- **Series:** By department (department colors)
- **Source:** Weekly Visits, count by week

### Coverage Analysis (half-width)
- **Type:** Heatmap or table
- **Rows:** Treating Physician
- **Columns:** Appointment Physician
- **Values:** Count of weekly visits
- **Purpose:** How often does a covering physician do the weekly check vs the treating physician?
- **Source:** Weekly Visits, `TreatingPhysician` vs `AppointmentPhysician`

## Tables

### OTV Audit Detail (full-width)
- **Columns:** Patient, Course, Department, Status, Prescribed Fractions, Delivered, Allowed OTVs, Actual Visits, Management CPTs, Audit Result
- **Highlight:** `Extra Visit(s)` rows in `--warning`, `Too Few` in `--error`
- **Sortable, filterable**
- **Export:** CSV

---

## Implementation Guidance

**Complexity:** Low — straightforward data, no Department merge needed, simple charts

### Data Loading

```python
from data.loader import load_otv_audit, load_weekly_visits

otv = load_otv_audit()  # Complete/OTV Audit.csv
weekly = load_weekly_visits()  # Incremental/WeeklyVisits/
```

### Key Columns

| Column | Type | Notes |
|--------|------|-------|
| `AuditResult` | string | Values: "OK", "Extra Visit(s)", "Too Few" |
| `Department` | string | Already clean (no `*` prefix) |
| `ClinicalStatus` | string | "ACTIVE" or "COMPLETED" |
| `FirstTreatmentDate` | date | Use for date filtering |
| `TreatingPhysician` | string | For physician filter |

### Filter Wiring

```python
@callback(
    Output("otvs-kpi-row", "children"),
    Output("otvs-chart-distribution", "figure"),
    # ... other outputs
    Input("otvs-interval", "n_intervals"),
    Input("otvs-filter-date-preset", "value"),
    Input("otvs-filter-daterange", "value"),
    Input("otvs-filter-department", "value"),
    Input("otvs-filter-physician", "value"),
    Input("otvs-filter-status", "value"),
    Input("otvs-filter-result", "value"),
)
```

### Suggested Approach

1. Start with KPIs (simple counts/percentages)
2. Add distribution donut chart
3. Add compliance by physician bar chart
4. Add table with row highlighting
5. No clientside callbacks needed (no smoothing sliders)
