# Page: Physicians

## Purpose
Track physician manpower, site assignments, after-hours work, and cross-coverage patterns. Cross-reference physician schedules with task completion to identify work done outside normal hours or for other physicians' patients.

## Data Sources
- `Physician Schedule.csv` — Daily physician assignments and status
- `Tasks.csv` — Task completion for after-hours and cross-coverage analysis

## Layout
Template A (KPI + Charts + Table)

## Filter Bar
- Date range: based on `Date` (schedule) or `CompletedDateTime` (tasks)
- Physician: multi-select dropdown

## KPI Cards

| KPI | Source | Calculation |
|-----|--------|-------------|
| Avg Daily Coverage | Physician Schedule | Mean count of MDs with status ON/ON CALL/WEEKEND CALL per day |
| After-Hours Tasks | Tasks | Count of tasks completed 5pm-8am or on weekends |
| Cross-Coverage Tasks | Tasks | Count where `CompletingMD != AssignedMD` |
| Off/Vacation Days | Physician Schedule | Count of records with status OFF/VACATION/SICK |
| Weekend Calls | Physician Schedule | Count of WEEKEND CALL assignments |

## Charts

### Manpower Over Time (half-width)
- **Type:** Area chart
- **X-axis:** Date
- **Y-axis:** Count of MDs on duty
- **Purpose:** Show staffing levels over time, identify coverage gaps

### Site Assignments (half-width)
- **Type:** Bar chart
- **X-axis:** Department (Lacey, Centralia, Aberdeen)
- **Y-axis:** Assignment days
- **Colors:** Department colors
- **Purpose:** Distribution of physician time across sites

### After-Hours Task Completions (half-width)
- **Type:** Horizontal bar chart
- **X-axis:** Task count
- **Y-axis:** Physician
- **Color:** Warning color (indicates out-of-hours work)
- **Definition:** Tasks completed:
  - Before 8am or after 5pm, OR
  - On weekends (Saturday/Sunday), OR
  - When physician status was OFF/VACATION/SICK

### Cross-Coverage (half-width)
- **Type:** Horizontal bar chart
- **X-axis:** Task count
- **Y-axis:** Physician (completing)
- **Purpose:** Show which MDs are picking up others' work
- **Definition:** Tasks where `CompletingMD != AssignedMD`

### Physician Schedule Calendar (full-width)
- **Type:** Heatmap
- **X-axis:** Date
- **Y-axis:** Physician
- **Color scale:**
  - Green: ON/ON CALL (working)
  - Yellow: WEEKEND CALL
  - Gray: OFF
  - Red: VACATION/SICK
- **Purpose:** Visual overview of who's where and when

## Tables

### Schedule Detail (full-width)
- **Columns:** Date, Physician, Status, Department
- **Sortable, filterable**
- **Export:** CSV

---

## Implementation Notes

**Reference file:** `pages/physicians.py`

### Key Data Loaders

```python
from data.loader import load_physician_schedule, load_tasks

schedule = load_physician_schedule()  # Complete/Physician Schedule.csv
tasks = load_tasks()                   # Complete/Tasks.csv
```

### Key Columns - Physician Schedule

| Column | Usage |
|--------|-------|
| `Date` | Date filtering, calendar x-axis |
| `Physician` | Filter, grouping |
| `Status` | ON, OFF, VACATION, SICK, WEEKEND CALL, ON CALL |
| `Department` | Site assignment (Lacey = "On Call") |

### Key Columns - Tasks

| Column | Usage |
|--------|-------|
| `CompletedDateTime` | After-hours detection (hour, day of week) |
| `CompletingMD` | Who completed the task |
| `AssignedMD` | Who was assigned the task |

### After-Hours Logic

```python
# Time-based after-hours
after_hours = (
    (tasks["CompletedDateTime"].dt.hour < 8) |
    (tasks["CompletedDateTime"].dt.hour >= 17) |
    (tasks["CompletedDateTime"].dt.dayofweek >= 5)  # Weekend
)

# Schedule-based after-hours (optional enhancement)
# Join tasks to schedule by CompletingMD + date
# Flag where status was OFF/VACATION/SICK
```

### Cross-Coverage Logic

```python
cross_coverage = tasks[tasks["CompletingMD"] != tasks["AssignedMD"]]
```

### Status Mapping

| Status | Meaning | On Duty |
|--------|---------|---------|
| ON | Working at assigned site | Yes |
| ON CALL | On call (typically Lacey) | Yes |
| WEEKEND CALL | Weekend coverage | Yes |
| OFF | Day off | No |
| VACATION | Vacation | No |
| SICK | Sick leave | No |
