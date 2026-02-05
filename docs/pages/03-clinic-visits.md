# Page: Clinic Visits

## Purpose
Track consult and follow-up appointment volume, lead times, and conversion to treatment. Answers: "How many consults are we doing? How quickly can patients get in? What fraction proceed to treatment?"

## Data Sources
- `Clinic Visits.csv` — consult and follow-up details
- `Lookup - Patients.csv` — join for payor mix per visit
- `Lookup - Diagnosis.csv` — join for diagnosis grouping

## Layout
Template A (KPI + Charts + Table)

## Filter Bar
- Date range: based on `ScheduledDateTime`
- Department: multi-select pills
- Physician: multi-select dropdown (`AppointmentPhysician`)
- Visit type: pills (All / Consult / Follow-Up / Virtual)
- Status: pills (Completed / Cancelled / All)

## KPI Cards (6 total, each with sparkline)

All KPI cards include a small inline sparkline (approx 80px x 24px) showing the recent trend. Solid line for historical data, dotted line for projected/future data where applicable.

| KPI | Source | Calculation | Sparkline |
|-----|--------|-------------|-----------|
| Total Visits | Clinic Visits | Count for filtered period | Solid line, weekly count over last 12 weeks |
| Consults | Clinic Visits | Count where `ActivityName = "Consult"` | Solid line, weekly count over last 12 weeks |
| Follow-Ups | Clinic Visits | Count where `ActivityName = "Follow-Up"` | Solid line, weekly count over last 12 weeks |
| Median Lead Time (days) | Clinic Visits | Median of `DaysFromCreatedToAppt` | Solid line, monthly median over last 6 months |
| Sim Conversion Rate | Clinic Visits | % of consults where `HasSimulationWithin180Days = 1` | Solid line, monthly % over last 6 months |
| Median Days to Sim | Clinic Visits | Median of `DaysToSimulation` (consults only) | Solid line, monthly median over last 6 months |

## Charts

### Visit Volume Trend (half-width)
- **Type:** Line or bar chart
- **X-axis:** Month
- **Y-axis:** Visit count
- **Series:** Consult, Follow-Up, Virtual (stacked or grouped)
- **Inline controls:** Aggregation (Weekly / Monthly), chart type (line / bar)

### Lead Time Trend (half-width)
- **Type:** Line chart
- **X-axis:** Month
- **Y-axis:** Median `DaysFromCreatedToAppt`
- **Series:** One line per department or overall
- **Purpose:** "How long are patients waiting to get an appointment?"

### Consult-to-Sim Conversion (full-width)
- **Type:** Line chart or bar chart
- **X-axis:** Month (consult month)
- **Y-axis:** Conversion rate (%)
- **Series:** Overall, by department
- **Purpose:** "What % of consults lead to simulation within 180 days?"
- **Note:** Promoted to full-width for emphasis as a key operational metric

### Cancel/No-Show Rate (one-third width, bottom row)
- **Type:** Line chart (monthly % trend)
- **X-axis:** Month
- **Y-axis:** Cancellation / no-show rate (%)
- **Calculation:** Count where `ActivityStatus = "Cancelled"` divided by total visits for that month, expressed as a percentage
- **Series:** Single overall line, optionally by department
- **Purpose:** Track appointment reliability over time — "Are cancellations trending up or down?"

### Diagnosis Mix (one-third width, bottom row)
- **Type:** Horizontal bar chart
- **Y-axis:** Diagnosis group (join `DiagnosisCodes` to `Lookup - Diagnosis` for `BodySystemDesc` or `SiteDesc`; split comma-separated codes before joining)
- **X-axis:** Visit count
- **Top 10-15 diagnosis groups**
- **Purpose:** "What diagnoses are driving our clinic volume?"
- **Colors:** Chart color sequence

### Physician Visit Load (one-third width, bottom row)
- **Type:** Grouped bar chart
- **X-axis:** Physician (`AppointmentPhysician`)
- **Y-axis:** Visit count
- **Series:** Two bars per physician — Consult count vs Follow-Up count (grouped, not stacked)
- **Colors:** Distinct color for Consult vs Follow-Up
- **Purpose:** Compare workload distribution across physicians and the balance between new consults and follow-up visits
- **Source:** `Clinic Visits`, group by `AppointmentPhysician` and `ActivityName` (mapping "Consult" and "Follow-Up")

## Tables

### Visit Detail (full-width)
- **Columns:** Date, Patient, Department, Physician, Visit Type, Duration, Lead Time (days), Has Sim, Days to Sim, Diagnosis, Payor
- **Sortable, filterable**
- **Export:** CSV
