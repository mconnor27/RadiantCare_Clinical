# Page: Billing

## Purpose
Analyze billing activity, CPT code distribution, audit compliance, and payor mix. Answers: "What are we billing? Are we billing correctly? What's our payor mix?"

## Data Sources
- `Billing.csv` — detailed billing transactions
- `2026 CPT Delivery Audit.csv` — CPT audit results
- `Lookup - Patients.csv` — join for payor mix per patient
- `Clinic Visits.csv` — join for payor mix per consult
- `Courses.csv` — join for payor mix per course

## Layout
Template A (KPI + Charts + Table)

## Filter Bar
- Date range: based on `DateOfService` (Billing) or `TreatmentDate` (Audit)
- Department: multi-select pills
- Physician: multi-select dropdown (`SupervisingPhysician` or `AttendingPhysician`)
- Code type: pills (All / Professional / Technical / Global)
- View: toggle (Billing Activity / CPT Audit / Payor Mix)

## KPI Cards

| KPI | Source | Calculation |
|-----|--------|-------------|
| Total Billing Events | Billing | Count for filtered period |
| Unique CPT Codes | Billing | Distinct `ProcedureCode` count |
| Audit Pass Rate | CPT Audit | % where `AuditResult = "PASS"` |
| Audit Failures (period) | CPT Audit | Count where `AuditResult = "FAIL"` |
| Top CPT Code | Billing | Most frequent `ProcedureCode` |

## Charts

### Billing Activity View

#### CPT Code Distribution (half-width)
- **Type:** Horizontal bar chart
- **Y-axis:** CPT code + description
- **X-axis:** Count
- **Top 15 codes, sorted by frequency**
- **Color:** By `CodeType` (Professional / Technical / Global)

#### Billing Volume Trend (half-width)
- **Type:** Line or stacked area chart
- **X-axis:** Month
- **Y-axis:** Billing event count
- **Series:** By `CodeType`

### CPT Audit View

#### Audit Results by Machine (half-width)
- **Type:** Grouped bar chart
- **X-axis:** Machine
- **Y-axis:** Count
- **Series:** PASS, FAIL (green, red)

#### Audit Results by Technique (half-width)
- **Type:** Grouped bar chart
- **X-axis:** `RxTechnique_Course` (IMRT, VMAT, SBRT, 3D)
- **Y-axis:** Count
- **Series:** PASS, FAIL

#### Audit Failure Detail
- **Type:** Table showing only FAIL rows
- **Columns:** Date, Patient, Machine, Technique, CPT Correct, CPT Billed, Difference
- **Purpose:** Actionable list for billing correction

### Payor Mix View

#### Payor Distribution - Per Patient (half-width)
- **Type:** Donut or treemap
- **Source:** `Lookup - Patients.PrimaryInsurance`
- **Values:** Patient count by insurer
- **Top 10 + "Other"**

#### Payor Distribution - Per Consult (half-width)
- **Type:** Donut or treemap
- **Source:** `Clinic Visits` joined to `Lookup - Patients` via `PatientId`
- **Values:** Consult count by insurer

#### Payor Distribution - Per Course (half-width)
- **Type:** Donut or treemap
- **Source:** `Courses` joined to `Lookup - Patients` via `PatientId`
- **Values:** Course count by insurer

#### Payor Distribution - Per Billed Activity (half-width)
- **Type:** Horizontal bar
- **Source:** Billing joined to `Lookup - Patients` via `PatientId`
- **Values:** Billing event count by insurer

#### Payor Trend (full-width)
- **Type:** Stacked area chart
- **X-axis:** Month
- **Y-axis:** % or count
- **Series:** Top 5 insurers + Other
- **Purpose:** Is the payor mix shifting over time?

## Tables

### Billing Detail (full-width)
- **Columns:** Date of Service, Patient, Department, CPT Code, Description, Code Type, Modifier, Supervising MD, Referring MD, Diagnosis
- **Sortable, filterable**
- **Export:** CSV
