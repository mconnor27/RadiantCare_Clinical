# Page: CPT Audit

## Purpose
Track CPT coding compliance for radiation treatment delivery under 2026 coding rules. Identify sessions where the billed CPT code doesn't match the correct code based on technique, modifiers, and treatment parameters.

## Data Sources
- `2026 CPT Delivery Audit.csv` — Session-level CPT code audit results

## Layout
Template A (KPI + Charts + Table)

## Filter Bar
- Date range: based on `TreatmentDate`
- Department: multi-select dropdown
- Machine: multi-select dropdown (optional)
- Audit Result: pills (All / Pass / Fail)

## KPI Cards

| KPI | Source | Calculation |
|-----|--------|-------------|
| Total Sessions | 2026 CPT Audit | Count of sessions in filtered range |
| Pass Rate | 2026 CPT Audit | % where `AuditResult = "PASS"` |
| Fail Count | 2026 CPT Audit | Count where `AuditResult = "FAIL"` |
| Unique Patients | 2026 CPT Audit | Distinct patients with failures |
| Most Common Error | 2026 CPT Audit | Most frequent CPT_Correct vs CPT_Billed mismatch |

## Charts

### Pass/Fail by Department (half-width)
- **Type:** Stacked bar chart
- **X-axis:** Department
- **Y-axis:** Session count
- **Series:** PASS (green), FAIL (red)
- **Purpose:** Compare compliance across sites

### Compliance Trend (half-width)
- **Type:** Line chart
- **X-axis:** Week or month (based on `TreatmentDate`)
- **Y-axis:** Pass rate (%)
- **Series:** By department or overall
- **Purpose:** Track improvement over time

### Failures by Technique (half-width)
- **Type:** Bar chart
- **X-axis:** RxTechnique_Day (IMRT, VMAT, 3D, SBRT)
- **Y-axis:** Fail count
- **Purpose:** Identify which techniques have coding issues

### CPT Mismatch Breakdown (half-width)
- **Type:** Horizontal bar chart or table
- **X-axis:** Count
- **Y-axis:** CPT_Correct → CPT_Billed pair
- **Purpose:** Show specific coding errors

## Tables

### CPT Audit Detail (full-width)
- **Columns:**
  - Treatment Date
  - Patient ID
  - Department
  - Machine
  - Technique (RxTechnique_Day)
  - Plan CPT
  - Correct CPT
  - Billed CPT
  - Audit Result
- **Highlight:**
  - FAIL rows in error color
- **Sortable, filterable**
- **Export:** CSV

---

## Implementation Notes

**Reference file:** `pages/cpt_audit.py`

### Key Data Loader

```python
from data.loader import load_cpt_audit

cpt = load_cpt_audit()  # Complete/2026 CPT Delivery Audit.csv
```

### Key Columns

| Column | Usage |
|--------|-------|
| `SessionUniqueID` | Unique session identifier |
| `TreatmentDate` | Date filtering, trend grouping |
| `Machine` | Filter, grouping |
| `Department` | Filter, grouping (has * prefix — strip) |
| `RxTechnique_Day` | Technique used that day |
| `PlanCHG_CPT` | CPT from treatment plan |
| `CPT_Correct` | Correct CPT per audit logic |
| `CPT_Billed` | Actually billed CPT(s) |
| `AuditResult` | "PASS" or "FAIL" |

### Department Cleaning

```python
# Department has * prefix
cpt["Department"] = cpt["Department"].str.lstrip("*")
```

### Audit Result Values

| Value | Meaning | Color |
|-------|---------|-------|
| PASS | Billed CPT matches correct CPT | Success (green) |
| FAIL | Billed CPT doesn't match correct CPT | Error (red) |

### Pass Rate Calculation

```python
total = len(cpt)
pass_count = (cpt["AuditResult"] == "PASS").sum()
pass_rate = pass_count / total * 100

fail_count = (cpt["AuditResult"] == "FAIL").sum()
```

### Mismatch Analysis

```python
failures = cpt[cpt["AuditResult"] == "FAIL"]
mismatch_counts = failures.groupby(["CPT_Correct", "CPT_Billed"]).size()
```

### Business Context
- 2026 CPT coding changes affect how radiation treatments are billed
- IMRT, VMAT, SBRT, 3D techniques have different code requirements
- Gating and other modifiers affect correct code selection
- Failures indicate potential billing errors requiring correction
- `CPT_Billed` can contain multiple comma-separated codes
