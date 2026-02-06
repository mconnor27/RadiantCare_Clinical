# Page: Tasks

## Purpose
Track physician task workload (draw volumes, plan reviews) against SLA deadlines. Cross-reference with physician schedule to identify after-hours or off-day work.

## Data Sources
- `Tasks.csv` — MD tasks with SLA tracking
- `Physician Schedule.csv` — cross-reference for off/on-call status

## Layout
Template A (KPI + Charts + Table)

## Filter Bar
- Date range: based on `StartDateTime`
- Physician: multi-select dropdown (`AssignedMD` or `CompletingMD`)
- Task type: pills (Draw Volumes / Review Plan / All)
- Status: pills (Completed / Open / All)

## KPI Cards

| KPI | Source | Calculation |
|-----|--------|-------------|
| Open Tasks | Tasks | Count where `CompletingMD = "NA"` |
| Completed (period) | Tasks | Count where `CompletedDateTime` in filtered range |
| Median Time to Complete (min) | Tasks | Median of `MinutesToComplete` for completed tasks |
| SLA Compliance Rate | Tasks | % where `MinutesToComplete <= MinutesAllowed` |
| After-Hours Completions | Tasks + Physician Schedule | Count of tasks completed when physician was OFF or on WEEKEND CALL |

## Charts

### Task Volume Trend (half-width)
- **Type:** Bar chart, stacked by task type
- **X-axis:** Week or month
- **Y-axis:** Task count
- **Series:** Draw Volumes, Review Plan

### Time to Complete Distribution (half-width)
- **Type:** Histogram or box plot
- **X-axis:** Minutes to complete
- **Y-axis:** Count
- **Series:** By task type or by physician
- **Overlay:** Vertical line at median, vertical line at SLA threshold
- **Purpose:** Are tasks being completed within SLA? Where's the distribution?

### Physician Comparison (half-width)
- **Type:** Grouped bar chart
- **X-axis:** Physician
- **Y-axis:** Median minutes to complete
- **Series:** Draw Volumes, Review Plan
- **Purpose:** Compare turnaround across MDs

### SLA Compliance Trend (half-width)
- **Type:** Line chart
- **X-axis:** Month
- **Y-axis:** SLA compliance rate (%)
- **Series:** By physician or overall
- **Purpose:** Track improvement or degradation over time

### After-Hours Work Indicator
- **Type:** Scatter or heatmap overlay
- **Logic:** Cross-reference `CompletedDateTime` with `Physician Schedule` to identify tasks completed during OFF, WEEKEND CALL, or outside 8 AM - 5 PM
- **Display:** Could be a flag column in the table, or a small chart showing % of work done after hours by physician

## Tables

### Task Detail (full-width)
- **Columns:** Start Date, Due Date, Completed Date, Patient, Task Type, Assigned MD, Completing MD, Minutes to Complete, SLA (min), On Time (Y/N), After Hours (Y/N)
- **Highlight:** Overdue tasks in `--error`, after-hours in `--warning`
- **Sortable, filterable**
- **Export:** CSV

---

## Implementation Notes

**Reference file:** `pages/tasks.py` (~395 lines)

### Upgrade Needed

Current implementation uses server-side rendering only. Upgrade to home.py patterns:
- [ ] Add `dcc.Store` for volume/SLA trend raw data
- [ ] Add clientside callbacks for smoothing
- [ ] Add `chart_settings_popover()` to volume and SLA trend charts
- [ ] Consider KPI sparklines for open tasks / SLA rate

### Current Architecture

- **No stores or clientside callbacks** — all server-side rendering
- Single main callback with 5 filter inputs
- After-hours detection via simple hour check (no Physician Schedule join currently)

### Key Data Loader

```python
from data.loader import load_tasks

tasks = load_tasks()  # Complete/Tasks.csv
```

### Key Columns

| Column | Usage |
|--------|-------|
| `StartDateTime` | Date filtering |
| `DueDateTime` | SLA deadline |
| `CompletedDateTime` | Status detection, after-hours check |
| `ActivityName` | Task type classification |
| `AssignedMD` | Physician filter |
| `CompletingMD` | "NA" = open task |
| `MinutesToComplete` | Actual completion time |
| `MinutesAllowed` | SLA threshold |

### Task Type Classification

Uses `ActivityName` substring matching:

```python
if task_type == "draw":
    tasks = tasks[tasks["ActivityName"].str.contains("Draw", case=False, na=False)]
elif task_type == "review":
    tasks = tasks[tasks["ActivityName"].str.contains("Review", case=False, na=False)]
```

### Status Filter Logic

```python
if status == "open":
    tasks = tasks[tasks["CompletedDateTime"].isna()]
elif status == "done":
    tasks = tasks[tasks["CompletedDateTime"].notna()]
```

### SLA Compliance Calculation

For completed tasks only:

```python
completed = tasks[tasks["CompletedDateTime"].notna()]
on_time = completed[completed["MinutesToComplete"] <= completed["MinutesAllowed"]]
sla_rate = len(on_time) / len(completed) * 100
```

### After-Hours Detection

Simple hour check (not using Physician Schedule cross-reference):

```python
after_hours = tasks[
    (tasks["CompletedDateTime"].dt.hour < 8) |
    (tasks["CompletedDateTime"].dt.hour >= 17)
]
```

### Physician Name Formatting

Physician names in x-axis are split by comma (shows first part only for readability).
