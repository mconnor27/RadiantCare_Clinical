# Page: Courses

## Purpose
Track treatment courses — status, technique mix, duration, fraction tracking. Course-level view of the patient treatment lifecycle.

## Data Sources
- `Courses.csv` — course-level summaries
- `Lookup - Diagnosis.csv` — join for diagnosis grouping

## Layout
Template A (KPI + Charts + Table)

## Filter Bar
- Date range: based on `CourseStartDateTime` or `FirstTreatmentDate`
- Department: multi-select pills (from `Departments` column)
- Physician: multi-select dropdown (`TreatingPhysician`)
- Status: pills (Active / Completed / All)
- Technique: multi-select (IMRT, VMAT, 3D)

## KPI Cards

| KPI | Source | Calculation |
|-----|--------|-------------|
| Active Courses | Courses | Count where `ClinicalStatus = "ACTIVE"` |
| Completed (period) | Courses | Count where `ClinicalStatus = "COMPLETED"` in period |
| Median Treatment Duration (days) | Courses | Median of `TreatmentDurationDays` for completed courses |
| Median Fractions | Courses | Median of `FractionsPrescribed` |
| Multi-Site Courses | Courses | Count where `Departments` contains comma |

## Charts

### Course Volume Trend (half-width)
- **Type:** Bar chart, stacked by status
- **X-axis:** Month (by `CourseStartDateTime`)
- **Y-axis:** Course count
- **Series:** Active, Completed

### Technique Mix (half-width)
- **Type:** Donut or stacked bar
- **Values:** Count by `TreatmentTechniques`
- **Purpose:** Distribution of IMRT vs VMAT vs 3D

### Treatment Site Distribution (half-width)
- **Type:** Horizontal bar chart
- **Y-axis:** `PrescriptionSites` (grouped by body system from Lookup - Diagnosis)
- **X-axis:** Count
- **Top 15 sites**
- **Purpose:** What are we treating most?

### Treatment Duration Distribution (half-width)
- **Type:** Histogram
- **X-axis:** Duration in days
- **Y-axis:** Count
- **Purpose:** How long do courses last? Identify outliers

### Courses by Physician (half-width)
- **Type:** Grouped bar
- **X-axis:** Physician
- **Y-axis:** Course count
- **Series:** By technique

## Tables

### Course Detail (full-width)
- **Columns:** Patient, Course ID, Start Date, Status, Treating MD, Technique, Prescribed Fx, Delivered Fx, Duration (days), Department(s), Machine(s), Diagnosis, Prescription Site
- **Sortable, filterable**
- **Export:** CSV

---

## Implementation Guidance

**Complexity:** Medium — comma-separated Departments, diagnosis join

### Data Loading

```python
from data.loader import load_courses, load_diagnosis_lookup

courses = load_courses()  # Incremental/Courses/
diagnosis = load_diagnosis_lookup()  # Lookup/Lookup - Diagnosis.csv
```

### Key Columns

| Column | Type | Notes |
|--------|------|-------|
| `Departments` | string | Comma-separated (e.g., "Lacey, Centralia") — take first for filtering |
| `CourseStartDateTime` | datetime | Normalized to `CourseStartDate` by loader |
| `ClinicalStatus` | string | "ACTIVE" or "COMPLETED" |
| `TreatingPhysician` | string | For physician filter |
| `TreatmentTechniques` | string | Comma-separated techniques |
| `DiagnosisCodes` | string | Comma-separated ICD codes |

### Department Extraction

Departments is comma-separated — extract primary:

```python
courses["Department"] = courses["Departments"].str.split(",").str[0].str.strip()
```

### Multi-Site Detection

```python
courses["IsMultiSite"] = courses["Departments"].str.contains(",", na=False)
```

### Diagnosis Join

DiagnosisCodes may be comma-separated — split before joining:

```python
# Explode to join each code
course_dx = courses.assign(
    DiagnosisCode=courses["DiagnosisCodes"].str.split(",")
).explode("DiagnosisCode")
course_dx["DiagnosisCode"] = course_dx["DiagnosisCode"].str.strip()
course_dx = course_dx.merge(diagnosis, on="DiagnosisCode", how="left")
```

### Filter Wiring

Standard pattern with additional Status and Technique filters.
