# Page: Plans

## Purpose
Track treatment plans — fraction progress, technique usage, plan status. Plan-level detail below the course level.

## Data Sources
- `Plans.csv` — plan-level detail with fraction tracking
- `Lookup - Diagnosis.csv` — join for diagnosis grouping

## Layout
Template A (KPI + Charts + Table)

## Filter Bar
- Date range: based on `FirstTreatmentDate` or `PlanCreationDate`
- Department: multi-select pills (from `Departments` column)
- Physician: multi-select dropdown (`TreatingPhysician`)
- Status: pills (Active / Completed / All) — based on `ClinicalStatus`
- Technique: multi-select (IMRT, VMAT, 3D)

## KPI Cards

| KPI | Source | Calculation |
|-----|--------|-------------|
| Active Plans | Plans | Count where fractions remaining > 0 |
| Total Plans (period) | Plans | Count for filtered period |
| Median Fractions Planned | Plans | Median of `NoFractionsPlanned` |
| Avg Fractions Remaining | Plans | Mean of `NoFractionsRemaining` for active plans |
| Multi-Machine Plans | Plans | Count where `Machines` contains comma |

## Charts

### Fraction Progress (half-width)
- **Type:** Grouped horizontal bar chart
- **Y-axis:** Plan (patient name + plan name), limited to active plans
- **X-axis:** Fraction count
- **Bars:** Delivered (filled) vs Remaining (outlined or lighter)
- **Purpose:** Visual progress tracker for active plans
- **Inline controls:** Sort by (% complete, remaining, patient name)

### Plan Technique Mix (half-width)
- **Type:** Donut chart
- **Values:** Count by `TreatmentTechnique`

### Plans Created Over Time (half-width)
- **Type:** Line or bar chart
- **X-axis:** Month (by `PlanCreationDate`)
- **Y-axis:** Plan count
- **Series:** By technique

### Treatment Duration by Technique (half-width)
- **Type:** Box plot
- **X-axis:** Technique
- **Y-axis:** `TreatmentDurationDays`
- **Purpose:** How long do different technique plans take to deliver?

## Tables

### Plan Detail (full-width)
- **Columns:** Patient, Course, Plan Name, Created Date, Status, Technique, Planned Fx, Delivered Fx, Remaining Fx, % Complete, Duration (days), Department(s), Machine(s), Prescription Site
- **Highlight:** Plans at > 90% completion in `--success`, plans with 0 delivered in `--warning`
- **Sortable, filterable**
- **Export:** CSV

---

## Implementation Guidance

**Complexity:** Medium — similar to Courses, comma-separated Departments

### Data Loading

```python
from data.loader import load_plans

plans = load_plans()  # Incremental/Plans/
```

### Key Columns

| Column | Type | Notes |
|--------|------|-------|
| `Departments` | string | Comma-separated — take first for filtering |
| `PatientName` | string | Normalized to `PatientFullName` by loader |
| `FirstTreatmentDate` | date | Use for date filtering |
| `PlanCreationDate` | date | Alternative date filter |
| `ClinicalStatus` | string | For status filter |
| `TreatmentTechnique` | string | IMRT, VMAT, 3D |
| `NoFractionsPlanned` | int | Planned fractions |
| `NoFractionsRemaining` | int | Remaining fractions |

### Department Extraction

Same as Courses:

```python
plans["Department"] = plans["Departments"].str.split(",").str[0].str.strip()
```

### Computed Columns

```python
plans["FractionsDelivered"] = plans["NoFractionsPlanned"] - plans["NoFractionsRemaining"]
plans["PctComplete"] = (plans["FractionsDelivered"] / plans["NoFractionsPlanned"] * 100).round(1)
plans["IsActive"] = plans["NoFractionsRemaining"] > 0
```

### DNU Plan Filtering

Exclude "Do Not Use" plans:

```python
plans = plans[~plans["PlanName"].str.contains("DNU", case=False, na=False)]
```

### Filter Wiring

Standard pattern with Status and Technique filters.
