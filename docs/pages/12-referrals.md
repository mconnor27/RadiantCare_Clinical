# Page: Referrals

## Purpose
Analyze referring physician patterns — who sends patients, from where, what specialties, and volume trends. Per-consult referral analysis with geographic mapping.

## Data Sources
- `Clinic Visits.csv` — consult records with referring physician FK
- `Lookup - Referring.csv` — referring physician details (name, specialty, institution, address, NPI)

## Layout
Template B (full-width feature)

## Filter Bar
- Date range: based on `ScheduledDateTime` in Clinic Visits
- Department: multi-select pills
- Specialty: multi-select dropdown (`ReferringPhysicianSpecialty` or `DoctorSpecialty`)
- Visit type: pills (Consult / All) — most referral analysis focuses on consults

## KPI Cards

| KPI | Source | Calculation |
|-----|--------|-------------|
| Total Referrals (period) | Clinic Visits | Count of consults with a referring physician |
| Unique Referring MDs | Clinic Visits + Referring | Distinct `ReferringPhysicianDimDoctorID` count |
| Top Referrer | Referring | Physician with most consults in period |
| Top Specialty | Referring | Specialty with most consults |
| New Referrers (period) | Clinic Visits | Referring MDs whose first referral is within the period |

## Charts

### Referral Source Map (main chart, full-width, 500px+)
- **Type:** `go.Scattermapbox`
- **Map style:** Mapbox light
- **Markers:** Referring physician locations (geocoded from `DoctorCompleteAddress`)
- **Size:** By patient count (`PatientCount` or live count from Clinic Visits)
- **Color:** By specialty
- **Flow lines:** From referring physician location to department location (Lacey/Centralia/Aberdeen)
- **Hover:** Doctor name, specialty, institution, patient count
- **Inline controls:** Color by (Specialty / Institution / Volume), show flow lines toggle

### Top Referring Physicians (half-width)
- **Type:** Horizontal bar chart
- **Y-axis:** Physician name
- **X-axis:** Consult count in period
- **Top 20**
- **Color:** By specialty

### Referral by Specialty (half-width)
- **Type:** Donut or horizontal bar
- **Values:** Consult count by `DoctorSpecialty`
- **Top 10 + Other**

### Referral Volume Trend (half-width)
- **Type:** Line chart
- **X-axis:** Month
- **Y-axis:** Consult count
- **Series:** By top 5 referring physicians, or by specialty
- **Purpose:** Are specific referral sources growing or shrinking?

### Institution Analysis (half-width)
- **Type:** Horizontal bar or treemap
- **Values:** Consult count by `DoctorInstitution`
- **Purpose:** Which institutions send the most patients?

### New Referrer Trend (half-width)
- **Type:** Bar chart
- **X-axis:** Month
- **Y-axis:** Count of referring MDs making their first referral in that month
- **Purpose:** Are we gaining new referral sources?

## Tables

### Referral Detail (full-width)
- **Columns:** Consult Date, Patient, Department, Referring MD, Specialty, Institution, NPI, Diagnosis, Visit Type
- **Sortable, filterable**
- **Export:** CSV

### Referring Physician Directory (full-width, secondary tab or toggle)
- **Columns:** Physician Name, Specialty, Institution, Phone, Fax, Email, Patient Count, First Referral Date, Last Referral Date
- **Sortable by patient count**
- **Purpose:** Reference directory for outreach

## Implementation Notes

### Geocoding Referring Physicians
- `DoctorCompleteAddress` is a comma-delimited string (street, city, state, zip) in a single field
- Parse into components, geocode to lat/lon
- Cache in a geocoding lookup alongside patient geocoding
- Many addresses may be incomplete — handle gracefully (skip from map, show in table)

### Join Logic
```
Clinic Visits.ReferringPhysicianDimDoctorID → Lookup - Referring.DimDoctorID
```
- Not all visits have a referring physician — filter nulls
- Some referring MDs may have multiple addresses — use `IsPrimaryDoctorAddress` to select
