# Page: Machine Performance

## Purpose
Monitor treatment machine errors, delivery discrepancies, and recovery times. Answers: "Which machines are having problems? How severe? How long to recover?"

## Data Sources
- `Machine Errors.csv` — treatment delivery errors with MU discrepancies

## Layout
Template A (KPI + Charts + Table)

## Filter Bar
- Date range: based on `TreatmentStartTime`
- Machine: multi-select pills (21EX, 21iX_CEN, 21iX_AB, TrueBeamNorth)
- Field category: pills (All / DynamicMLC / Arc)

## KPI Cards

| KPI | Source | Calculation |
|-----|--------|-------------|
| Total Errors (period) | Machine Errors | Count for filtered period |
| Avg Errors/Day | Machine Errors | Count / distinct treatment days |
| Median Recovery Time (min) | Machine Errors | Median of `ElapsedTimeToNextTreatment` |
| Worst Machine (period) | Machine Errors | Machine with highest error count |
| Avg MU Deficit (%) | Machine Errors | Mean of `(PlannedMU - DeliveredMU) / PlannedMU * 100` |

## Charts

### Error Count by Machine (half-width)
- **Type:** Bar chart
- **X-axis:** Machine
- **Y-axis:** Error count
- **Color:** Department colors mapped to machine (21EX/TrueBeamNorth = Lacey blue, 21iX_CEN = Centralia red, 21iX_AB = Aberdeen green)

### Error Trend (half-width)
- **Type:** Line chart
- **X-axis:** Week or month
- **Y-axis:** Error count
- **Series:** One line per machine
- **Inline controls:** Aggregation (Weekly / Monthly)

### MU Delivery Analysis (half-width)
- **Type:** Scatter plot
- **X-axis:** Planned MU
- **Y-axis:** Delivered MU
- **Ideal:** 45-degree line (Delivered = Planned)
- **Color:** By machine
- **Purpose:** Visualize severity — points far from the line are severe errors

### Recovery Time Distribution (half-width)
- **Type:** Histogram or box plot
- **X-axis:** Recovery time (minutes)
- **Y-axis:** Count
- **Series:** By machine
- **Purpose:** How long are errors delaying subsequent patients?

### Error Rate by Field Category (half-width)
- **Type:** Grouped bar
- **X-axis:** Field category (DynamicMLC, Arc)
- **Y-axis:** Error count or error rate
- **Series:** By machine

## Tables

### Error Detail (full-width)
- **Columns:** Date/Time, Patient, Machine, Plan, Field, Fraction, Planned MU, Delivered MU, MU Deficit (%), Field Category, Recovery Time (min)
- **Highlight:** Severe deficits (> 50% MU gap) in `--error`
- **Sortable by any column**
- **Export:** CSV

---

## Implementation Guidance

**Complexity:** Medium — no Department column, date from datetime

### Data Loading

```python
from data.loader import load_machine_errors

errors = load_machine_errors()  # Complete/Machine Errors.csv
```

### Key Columns

| Column | Type | Notes |
|--------|------|-------|
| `TreatmentStartTime` | datetime | Use for date filtering (no `Date` column) |
| `Machine` | string | 21EX, 21iX_CEN, 21iX_AB (no TrueBeamNorth in this file) |
| `PlannedMU` | float | Monitor units planned |
| `DeliveredMU` | float | Monitor units actually delivered |
| `ElapsedTimeToNextTreatment` | float | Recovery time in minutes |
| `FieldCategory` | string | DynamicMLC, Arc |

### Machine → Department Mapping

No Department column — derive from Machine:

```python
MACHINE_DEPT = {
    "21EX": "Lacey",
    "TrueBeamNorth": "Lacey",
    "21iX_CEN": "Centralia",
    "21iX_AB": "Aberdeen",
}
errors["Department"] = errors["Machine"].map(MACHINE_DEPT)
```

### Date Extraction

Extract date from datetime for filtering/grouping:

```python
errors["Date"] = pd.to_datetime(errors["TreatmentStartTime"]).dt.date
```

### Computed Columns

```python
errors["MU_Deficit_Pct"] = (
    (errors["PlannedMU"] - errors["DeliveredMU"]) / errors["PlannedMU"] * 100
)
```

### Filter Wiring

Standard pattern — machine filter instead of department.
