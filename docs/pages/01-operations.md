# Page: Operations

## Purpose
Daily treatment operations view. Combines past volume, future schedule, and availability into a unified operational picture. Answers: "How busy are we? How busy will we be? Where are the openings?"

## Data Sources
- `Daily Volume - Past.csv` — historical daily volume with actual times
- `Daily Volume - Future.csv` — scheduled future volume
- `Treatment.csv` — daily aggregates by location with technique breakdowns, new starts by course
- `Availability.csv` — future appointment holds and open slots (Exam + Simulation categories)

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
| Next Available Slot | Availability | Earliest future date with open capacity |
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
  - `Exam` (from Availability.csv, `Category = "Exam"`)
  - `Simulation` (from Availability.csv, `Category = "Simulation"`)
- **Color intensity:** Number of scheduled appointments per cell. Use a sequential color scale (light = few/open, dark = heavily booked)
- **Cell annotation:** Show the appointment count number inside each heatmap cell
- **Source:** Merge `Daily Volume - Future` (treatment rows by machine/location) with `Availability.csv` (Exam and Simulation rows, aggregated by day and category)
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
