# Page: OTV Audit

## Purpose
Track on-treatment visit (OTV) compliance — identifying courses with too many or too few weekly management visits. OTVs are required billing visits (CPT 77427) that must occur at appropriate intervals during radiation treatment.

## Data Sources
- `OTV Audit.csv` — Course-level OTV compliance audit results

## Layout
Template A (KPI + Charts + Table)

## Filter Bar
- Date range: based on `FirstTreatmentDate` or `LastTreatmentDate`
- Department: multi-select dropdown

## KPI Cards

| KPI | Source | Calculation |
|-----|--------|-------------|
| Total Courses | OTV Audit | Count of courses in filtered range |
| Compliance Rate | OTV Audit | % where `AuditResult = "OK"` |
| Extra Visits | OTV Audit | Count where `AuditResult = "Extra Visit(s)"` |
| Too Few Visits | OTV Audit | Count where `AuditResult = "Too Few"` |
| Avg Discrepancy | OTV Audit | Mean of `ManagementCPTs_Total - AllowedOTVs` for non-OK |

## Charts

### Compliance by Department (half-width)
- **Type:** Stacked bar chart
- **X-axis:** Department
- **Y-axis:** Course count
- **Series:** OK (green), Extra (warning), Too Few (error)
- **Purpose:** Compare compliance across sites

### Compliance Trend (half-width)
- **Type:** Line chart
- **X-axis:** Month (based on `LastTreatmentDate`)
- **Y-axis:** Compliance rate (%)
- **Series:** By department or overall
- **Purpose:** Track improvement over time

### Audit Result Distribution (half-width)
- **Type:** Pie or donut chart
- **Segments:** OK, Extra Visit(s), Too Few
- **Colors:** Success/Warning/Error semantic colors
- **Purpose:** Overall distribution at a glance

### Discrepancy Distribution (half-width)
- **Type:** Histogram
- **X-axis:** Discrepancy (Actual - Allowed)
- **Y-axis:** Course count
- **Purpose:** See magnitude of over/under billing

## Tables

### OTV Audit Detail (full-width)
- **Columns:**
  - Patient Name
  - Course ID
  - Department
  - First Treatment Date
  - Last Treatment Date
  - Prescribed Fractions
  - Allowed OTVs
  - Actual OTVs (ManagementCPTs_Total)
  - Audit Result
- **Highlight:**
  - Extra Visit(s) in warning color
  - Too Few in error color
- **Sortable, filterable**
- **Export:** CSV

---

## Implementation Notes

**Reference file:** `pages/otv_audit.py`

### Key Data Loader

```python
from data.loader import load_otv_audit

otv = load_otv_audit()  # Complete/OTV Audit.csv
```

### Key Columns

| Column | Usage |
|--------|-------|
| `Department` | Filter, grouping (no * prefix) |
| `FirstTreatmentDate` | Date filtering |
| `LastTreatmentDate` | Date filtering, trend grouping |
| `PrescribedFractions` | Context for allowed calculation |
| `AllowedOTVs` | Expected OTV count |
| `ManagementCPTs_Total` | Actual OTV count |
| `AuditResult` | "OK", "Extra Visit(s)", "Too Few" |
| `PatientName` | Display |
| `CourseId` | Display |

### Audit Result Values

| Value | Meaning | Color |
|-------|---------|-------|
| OK | Correct number of OTVs | Success (green) |
| Extra Visit(s) | More OTVs than allowed (over-billing risk) | Warning (amber) |
| Too Few | Fewer OTVs than allowed (missed billing) | Error (red) |

### Compliance Calculation

```python
total = len(otv)
ok_count = (otv["AuditResult"] == "OK").sum()
compliance_rate = ok_count / total * 100

extra_count = (otv["AuditResult"] == "Extra Visit(s)").sum()
too_few_count = (otv["AuditResult"] == "Too Few").sum()
```

### Discrepancy Calculation

```python
otv["Discrepancy"] = otv["ManagementCPTs_Total"] - otv["AllowedOTVs"]
# Positive = extra visits, Negative = too few
```

### Business Context
- OTVs are billed as CPT 77427 ("Radiation treatment management, five treatments")
- Typically 1 OTV is allowed per 5 fractions
- Too many OTVs = potential over-billing (compliance risk)
- Too few OTVs = missed revenue opportunity
