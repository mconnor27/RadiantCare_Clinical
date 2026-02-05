# Page: Patients

## Purpose
Geographic visualization of patient origins and how they flow to each department. Answers: "Where do our patients come from? Which communities feed which departments?"

## Data Sources
- `Lookup - Patients.csv` — patient demographics with City, County, Zip, Department

## Layout
Template B (full-width feature)

## Filter Bar
- Date range: based on `FirstAppointment` or `LastAppointment`
- Department: multi-select pills
- Insurance: multi-select dropdown (`PrimaryInsurance`)

## KPI Cards

| KPI | Source | Calculation |
|-----|--------|-------------|
| Total Patients | Patients | Count for filtered period |
| Unique Cities | Patients | Distinct `City` count |
| Unique Counties | Patients | Distinct `County` count |
| Top City | Patients | City with most patients |

## Charts

### Patient Origin Map (main chart, full-width, 500px+)
- **Type:** `px.scatter_mapbox` or `go.Scattermapbox`
- **Map style:** Mapbox light
- **Center:** Washington State, centered on Olympia/Lacey area
- **Markers:** Patient locations plotted by City or Zip (geocoded)
- **Color:** By department (which department the patient belongs to)
- **Size:** By patient count at that location
- **Flow lines:** Lines from patient origin clusters to department location, with line width proportional to patient count
- **Department markers:** Fixed markers at Lacey, Centralia, Aberdeen with department colors and labels
- **Inline controls:** Color by (Department / Insurance), group by (City / Zip / County)
- **Requires:** Geocoding of City/Zip to lat/lon. Pre-compute a geocoding lookup from the unique City+State or Zip values.

### Department Distribution (half-width)
- **Type:** Donut chart
- **Values:** Patient count by `Department`
- **Colors:** Department colors

### Top Cities / Counties (half-width)
- **Type:** Horizontal bar chart
- **Y-axis:** City or County name
- **X-axis:** Patient count
- **Top 20**
- **Color:** By department

### Patient Volume by County Choropleth (full-width, optional)
- **Type:** Choropleth map of Washington State counties
- **Color intensity:** Patient count per county
- **Purpose:** Alternative to scatter map for geographic distribution

## Tables

### Patient Geographic Summary (full-width)
- **Columns:** City, County, Zip, Department, Patient Count, % of Total
- **Grouped by City or County**
- **Sortable, filterable**
- **Export:** CSV

## Implementation Notes

### Geocoding
- Build a lookup table mapping unique `City` + `Zip` combinations to latitude/longitude
- Use a geocoding service or a static lookup for Washington State cities
- Cache the results — this only needs to run when new cities appear in the data
- Store as `data/geocode_cache.csv` or similar

### Department Coordinates
| Department | Latitude | Longitude |
|-----------|----------|-----------|
| Lacey | 47.0343 | -122.8231 |
| Centralia | 46.7162 | -122.9543 |
| Aberdeen | 46.9754 | -123.8157 |

### Mapbox Token
- Requires `MAPBOX_TOKEN` environment variable
- Free tier is sufficient for this use case
