# Page: Operations

## Purpose
Daily treatment operations view. Combines past volume, future schedule, and upcoming availability into a unified operational picture. Answers: "How busy are we? How busy will we be? Where are the openings?"

## Data Sources
- `Daily Volume - Past.csv` — historical daily volume with actual times
- `Daily Volume - Future.csv` — scheduled future volume
- `Treatment.csv` — daily aggregates by location with technique breakdowns, new starts by course
- `ScheduleUpcoming.csv` — future appointment holds and open slots (Exam + Simulation categories) — successor to the legacy `Availability.csv`

## Layout
Template C (timeline/band chart)

## Filter Bar
- Date range: presets (Today, This Week, Next 2 Weeks, This Month, Last 3 Months, YTD, All)
- Department: multi-select pills (Lacey, Centralia, Aberdeen) with department colors
- Machine: multi-select dropdown (TrueBeamNorth, 21EX, 21iX_CEN, 21iX_AB)

## KPI Cards

| KPI | Source | Calculation |
|-----|--------|-------------|
| Treatments Today | Daily Volume - Past | `AppointmentCount` for today, all locations |
| Avg Daily Volume (30d) | Daily Volume - Past | Mean `AppointmentCount` over last 30 days |
| Next Available Slot | ScheduleUpcoming | Earliest future date with open capacity (`BookingStatus = "Available"`) |
| Scheduled This Week | Daily Volume - Future | Sum `AppointmentCount` for current week |
| New Starts This Week | Treatment | Sum `NewStarts_ByCourseFirstTreatmentDate` for current week (counted by course, not by fraction) |

## Charts

### Treatment Appointments (completed) (half-width)
- **Type:** Line chart
- **X-axis:** Date
- **Y-axis:** Completed appointment count
- **Series:** One line per location (department colors)
- **Source:** Daily Volume - Past, `AppointmentCount` by `Location` (site-level only: Aberdeen, Centralia, Lacey)
- **Inline controls:** Aggregation (Daily / Weekly / Monthly), smoothing toggle
- **Purpose:** Historical treatment volume trend — "How busy have we been?"

### Upcoming 2 Weeks Heatmap (half-width)
- **Type:** Heatmap (graphical, NOT a table)
- **X-axis:** Day (next 14 calendar days, labeled with day-of-week + date)
- **Y-axis:** Rows for each location/category combination:
  - `TrueBeamNorth` (treatment)
  - `21EX` (treatment)
  - `21iX_CEN` (treatment)
  - `21iX_AB` (treatment)
  - `Exam` (from ScheduleUpcoming.csv, `ActivityCategory = "Exam"`)
  - `Simulation` (from ScheduleUpcoming.csv, `ActivityCategory = "Simulation"`)
- **Color intensity:** Number of scheduled appointments per cell. Use a sequential color scale (light = few/open, dark = heavily booked)
- **Cell annotation:** Show the appointment count number inside each heatmap cell
- **Source:** Merge `Daily Volume - Future` (treatment rows by machine/location) with `ScheduleUpcoming.csv` (Exam and Simulation rows, filtered to `BookingStatus = "Available"`, aggregated by day and category)
- **Hover:** Show location, date, appointment count, and any available slot info
- **Purpose:** Single visual combining future schedule density + exam/sim availability. Replaces the former Future Schedule Lookahead, Availability Calendar, and Scheduling Lead Time charts

### Operating Hours Ribbon (main chart, full-width, ~500px height)
- **Type:** Ribbon chart with 3 vertically stacked subplots (one per site), sharing a single X-axis
- **X-axis:** Date (spanning full date range of data, potentially multiple years)
- **Y-axis:** Time of day (7:00 AM to 6:00 PM) — shared scale across all 3 subplots
- **Subplot 1 — Lacey:** Two overlaid machine ribbons:
  - **TrueBeamNorth ribbon:** `go.Scatter` with `fill='tonexty'` area from `FirstScheduledStart` to `LastScheduledEnd` (scheduled, lighter fill) and `FirstActualStart` to `LastActualEnd` (actual, darker fill)
  - **21EX ribbon:** Same approach, different color. Overlaid on the same subplot so both machines are visible simultaneously
  - Use semi-transparent fills so overlapping regions are visible
- **Subplot 2 — Centralia (21iX_CEN):** Single machine ribbon, same scheduled vs actual approach
- **Subplot 3 — Aberdeen (21iX_AB):** Single machine ribbon, same scheduled vs actual approach
- **Colors:** Each machine gets a distinct color pair (lighter = scheduled window, darker = actual window). Use department color as base with opacity variations
- **Source:** `Daily Volume - Past` (for dates with actual times) and `Daily Volume - Future` (for scheduled-only future dates). Join on `Location` + `Date`
  - Map `Location` values to subplots: `Lacey - TrueBeamNorth` / `TrueBeamNorth` to Lacey subplot, `Lacey - 21EX` / `21EX` to Lacey subplot, `21iX_CEN` / `Centralia` to Centralia subplot, `21iX_AB` / `Aberdeen` to Aberdeen subplot
- **Inline controls:** Date range navigation (scroll/zoom), toggle scheduled vs actual
- **Purpose:** Visual timeline of when each machine/site was operating across the full history. Shows start-of-day to end-of-day windows, making it easy to spot schedule creep, early starts, late finishes, and utilization gaps between machines at Lacey

## Tables

### Daily Detail Table (full-width)
- **Columns:** Date, Location, Scheduled Appointments, Actual Start, Actual End, Duration (hrs), New Starts (by course)
- **Source:** Daily Volume - Past joined with Treatment
- **Sortable, filterable**
- **Export:** CSV download button

---

## Implementation Notes

**Reference file:** `pages/operations.py` (~387 lines)

### Upgrade Needed

Current implementation uses server-side rendering only. Upgrade to home.py patterns:
- [ ] Add `dcc.Store` for ribbon chart raw data
- [ ] Add clientside callback for smoothing slider on ribbon
- [ ] Add `chart_settings_popover()` to treatment and ribbon charts
- [ ] Add KPI sparklines

### Current Architecture

- **No stores or clientside callbacks** — all server-side rendering
- Single main callback with `dcc.Interval` (300s refresh) + 4 filter inputs
- Physician filter accepted but not applied to Treatment data (aggregated by department)

### Key Data Loaders

```python
from data.loader import load_treatment, load_daily_volume, load_daily_volume_future, load_schedule_upcoming
```

### Operating Hours Ribbon Implementation

Uses `make_subplots(rows=len(sites))` with stacked scatter fills:

```python
# Convert time columns to decimal hours for Y-axis
site_data["start_hour"] = site_data["FirstActualStart"].dt.hour + site_data["FirstActualStart"].dt.minute / 60
site_data["end_hour"] = site_data["LastActualEnd"].dt.hour + site_data["LastActualEnd"].dt.minute / 60

# Create ribbon with fill between start and end
fig.add_trace(go.Scatter(x=dates, y=start_hours, fill=None, ...))
fig.add_trace(go.Scatter(x=dates, y=end_hours, fill='tonexty', ...))
```

### Site-Level Department Filtering

Treatment.csv contains both site-level (`Lacey`) and machine-level (`Lacey - 21EX`) entries:

```python
site_depts = [d for d in tx["Department"].unique() if d in DEPARTMENTS]
```

### Schedule Upcoming Grouping

Groups by `Category` column (Exam vs Simulation, normalized from `ActivityCategory` by the loader) when present. Filter to `SlotTaken != "Yes"` (or equivalently `BookingStatus == "Available"`) to count only open holds.

### Filter Wiring

```python
@callback(
    Output("operations-kpi-row", "children"),
    # ... other outputs
    Input("operations-interval", "n_intervals"),
    Input("operations-filter-date-preset", "value"),
    Input("operations-filter-department", "value"),
    Input("operations-filter-machine", "value"),
)
```
