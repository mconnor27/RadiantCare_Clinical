# Page: Simulations

## Purpose
Track simulation volume, types, and timing intervals. Answers: "How many sims are we doing? How long from consult to sim? How long from sim to first treatment?"

## Data Sources
- `Simulations.csv` — simulation appointment details with timing metrics

## Layout
Template A (KPI + Charts + Table)

## Filter Bar
- Date range: based on `ScheduledDateTime`
- Department: derived from sim type or supervising physician's department
- Physician: multi-select dropdown (`SupervisingPhysician`)
- Sim type: multi-select (Initial Simulation, Stereotactic Simulation, Re-Simulation, Initial Centralia-in Lacey, Initial Aberdeen Simulation)
- Status: pills (Completed / All)

## KPI Cards

| KPI | Source | Calculation |
|-----|--------|-------------|
| Total Simulations | Simulations | Count for filtered period |
| Median Consult-to-Sim (days) | Simulations | Median of `DaysFromClinicExamToSimulation` |
| Median Sim-to-Treatment (days) | Simulations | Median of `DaysFromSimToTreatment` |
| Median Consult-to-Treatment (days) | Simulations | Median of `DaysFromClinicExamToTreatment` |
| Re-Sim Rate | Simulations | % where `ActivityName` contains "Re-Simulation" |

## Charts

### Simulation Volume Trend (half-width)
- **Type:** Line or bar chart
- **X-axis:** Month
- **Y-axis:** Count
- **Series:** By sim type (stacked or grouped)
- **Inline controls:** Aggregation (Weekly / Monthly), chart type

### Timing Intervals (half-width)
- **Type:** Multi-line chart
- **X-axis:** Month (sim month)
- **Y-axis:** Median days
- **Series:** Consult→Sim, Sim→Treatment, Consult→Treatment
- **Purpose:** Track whether timing is improving or degrading

### Sim Type Distribution (half-width)
- **Type:** Donut or horizontal bar
- **Values:** Count per `ActivityName`
- **Purpose:** Mix of simulation types

### Simulation Schedule Ribbon (half-width)
- **Type:** Ribbon / area chart showing the daily simulation operating window
- **X-axis:** Date (spanning full date range of data, potentially multiple years)
- **Y-axis:** Time of day (e.g., 7:00 AM to 5:00 PM)
- **Implementation:** For each day that has simulation appointments, plot two `go.Scatter` traces:
  - Trace 1 (upper bound): earliest `ScheduledDateTime` time-of-day per day — this forms the top edge
  - Trace 2 (lower bound): latest `ScheduledDateTime` time-of-day + `DurationMinutes` per day — this forms the bottom edge
  - Use `fill='tonexty'` on the second trace to create a filled ribbon area between the earliest and latest sim times
- **Color:** Single semi-transparent fill color (e.g., the Simulations page accent color at 0.3 opacity)
- **Source:** `Simulations.csv` — extract time-of-day from `ScheduledDateTime`. For each unique date, compute:
  - `earliest_time = min(time_of_day(ScheduledDateTime))`
  - `latest_time = max(time_of_day(ScheduledDateTime) + DurationMinutes)`
- **Hover:** Show date, earliest sim time, latest sim end time, number of sims that day
- **Purpose:** Visualize when simulations are being scheduled across the full history — shows the daily "sim window" as a filled band. Makes it easy to spot schedule compression, expansion, or shifts in sim timing. Replaces the former Duration Analysis bar chart

## Tables

### Simulation Detail (full-width)
- **Columns:** Date, Patient, Sim Type, Duration (min), Physician, Days from Consult, Days to Treatment, CPT Codes
- **Sortable, filterable**
- **Export:** CSV

---

## Implementation Notes

**Reference file:** `pages/simulations.py` (~576 lines)

### Upgrade Needed

Current implementation uses server-side rendering only. Upgrade to home.py patterns:
- [ ] Add `dcc.Store` for volume/timing/ribbon raw data
- [ ] Add clientside callbacks for smoothing
- [ ] Add `chart_settings_popover()` to volume and timing charts
- [ ] Consider KPI sparklines for interval metrics

### Current Architecture

- **No stores or clientside callbacks** — all server-side rendering
- Two callbacks: one populates sim type dropdown from `ActivityName`, main callback with 8 inputs
- Uses all historical data for ribbon chart (ignores date filter for that chart)

### Key Data Loader

```python
from data.loader import load_simulations

sims = load_simulations()  # Incremental/Simulations/ — Department pre-merged
```

### Department Column

Simulations data has **Department pre-merged** in loader via `_patient_department_map()` (merges from Treatment-Detail by PatientId).

### Schedule Ribbon Implementation

**Important:** Ribbon spans ALL historical data, not just filtered date range:

```python
# Uses unfiltered data for ribbon
df_all_dates = sims.copy()

# Extract time of day as decimal hours
df_all_dates["start_hour"] = df_all_dates["ScheduledDateTime"].dt.hour + df_all_dates["ScheduledDateTime"].dt.minute / 60

# Duration end = start + duration minutes
df_all_dates["end_hour"] = df_all_dates["start_hour"] + df_all_dates["Duration"] / 60

# Clip to visible range
df_all_dates["start_hour"] = df_all_dates["start_hour"].clip(lower=6, upper=20)
df_all_dates["end_hour"] = df_all_dates["end_hour"].clip(lower=6, upper=20)
```

Single Scatter with `fill='tonexty'` (no subplots like Operations).

### Key Columns

| Column | Usage |
|--------|-------|
| `ScheduledDateTime` | Date filtering, ribbon X-axis |
| `SupervisingPhysician` | Physician filter |
| `ActivityName` | Sim type filter, re-sim detection |
| `Status` | Completed filter |
| `Duration` | Ribbon end time, detail table |
| `DaysFromClinicExamToSimulation` | Consult→Sim interval |
| `DaysFromSimToTreatment` | Sim→Treatment interval |
| `DaysFromClinicExamToTreatment` | Total pipeline |

### Re-Sim Rate Calculation

```python
resim_count = sims[sims["ActivityName"].str.contains("Re-Simulation", case=False, na=False)]
resim_rate = len(resim_count) / len(sims) * 100
```

### Status Filter

```python
if status == "completed":
    sims = sims[sims["Status"].str.lower() == "completed"]
# else: show all
```
