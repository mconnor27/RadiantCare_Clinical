# Page: Workflow

## Purpose
Visualize the complete patient treatment pipeline from consult through first treatment. Identify bottlenecks, measure throughput, and track timing at each step.

## Data Sources
- `Workflow.csv` — end-to-end patient workflow tracking (46 columns)
- `Lookup - Diagnosis.csv` — join for diagnosis grouping (via `DiagnosisCodes`)

## Layout
Template B (full-width feature)

## Filter Bar
- Date range: based on `ScheduledDateTime` (consult date)
- Department: multi-select pills
- Physician: multi-select dropdown (treating physician)
- Diagnosis: multi-select dropdown (join `DiagnosisCodes` to `Lookup - Diagnosis` for `BodySystemDesc` or `SiteDesc` grouping; comma-separated codes must be split before join)
- Activity type: Consult only / All (follow-ups don't have workflow data)

## KPI Cards

| KPI | Source | Calculation |
|-----|--------|-------------|
| Median Consult-to-Sim (days) | Workflow | Median of `DaysToSimulation` |
| Median Sim-to-Treatment (days) | Workflow | Median of `DaysFromReviewToTreatment` + review time |
| Median Total Pipeline (days) | Workflow | Median of days from `ScheduledDateTime` to `FirstTreatmentDate` |
| Patients in Pipeline | Workflow | Count where consult exists but `FirstTreatmentDate` is empty |

## Charts

### Sankey Diagram (main chart, full-width, 500px+ height)
- **Type:** `go.Sankey`
- **Nodes:** Consult → Simulation → Draw Volumes → Isodose Plan → Review Plan → First Treatment
- **Links:** Width proportional to patient volume flowing between stages
- **Drop-offs:** Show patients who haven't reached the next stage as a separate "Pending" or "Not yet" node
- **Node colors:** Chart color sequence
- **Link colors:** Translucent version of source node color (opacity 0.3)
- **Hover:** Show count, median days between stages
- **Inline controls:** Time period for the cohort

### Stage Duration Violin Plots (half-width)
- **Type:** Violin plot (`go.Violin`)
- **X-axis:** Pipeline stage (Consult→Sim, Sim→Draw, Draw→Isodose, Isodose→Review, Review→Treatment)
- **Y-axis:** Days
- **Purpose:** Show full distribution shape of time at each stage, including density, median, and outliers. Violin plots provide richer distributional insight than box plots — they reveal multimodality (e.g., bimodal patterns from weekday vs weekend completions) and skew
- **Source:** `DaysToSimulation`, `DaysFromSimToIsodose`, `DaysFromSimToReview`, `DaysFromReviewToTreatment`
- **Configuration:**
  - `box_visible=True` (show inner box plot with median line)
  - `meanline_visible=True` (show mean as dashed line)
  - `points="outliers"` (show individual outlier points)
  - One violin per stage, colored by chart color sequence

### Pipeline Trend (half-width)
- **Type:** Line chart
- **X-axis:** Month (consult month cohort)
- **Y-axis:** Median days (consult to treatment)
- **Series:** Overall median, plus individual stage medians
- **Purpose:** "Are we getting faster or slower over time?"

## Tables

### Patient Pipeline Detail (full-width)
- **Columns:** Patient, Consult Date, Sim Date, Days to Sim, Draw Completed, Isodose Completed, Review Completed, First Treatment, Total Days, Status (Completed / In Progress), Diagnosis
- **Sortable by any column**
- **Highlight:** Rows where any stage exceeds 2x the median in `--warning` color
- **Export:** CSV
