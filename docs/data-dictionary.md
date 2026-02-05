# Data Dictionary

## Source System

All data originates from **ARIA** (Varian) via automated SQL data warehouse exports to:

```
/Users/Mike/Library/CloudStorage/OneDrive-ProvidenceSt.JosephHealth/AURA_Reports/
```

### Folder Structure

| Folder | Behavior | Contents |
|--------|----------|---------|
| `Complete/` | Replaced nightly (full refresh) | Aggregated/complete datasets |
| `Incremental/` | Appended (deduplicate by `UniqueRowID`) | Transactional data, one subfolder per domain |
| `Lookup/` | Reference tables (complete, rarely change) | Dimension tables for joining |

### Refresh Schedule

- **Complete/** files: Fully replaced each night
- **Incremental/** files: New rows appended. Use `UniqueRowID` to deduplicate
- **Lookup/** files: Complete reference tables, updated as new records enter the system

---

## Complete Files

### 2026 CPT Delivery Audit

- **File:** `Complete/2026 CPT Delivery Audit.csv`
- **Size:** ~278 KB
- **Refresh:** Nightly full replace
- **Used by:** Billing page

| Column | Type | Description |
|--------|------|-------------|
| `SessionUniqueID` | int | Unique treatment session identifier |
| `TreatmentDate` | date (MM/DD/YYYY) | Date of treatment delivery |
| `Machine` | string | Treatment machine name (TrueBeamNorth, 21EX, 21iX_CEN, 21iX_AB) |
| `Department` | string | Department name, prefixed with `*` (e.g., `*Lacey`) |
| `PatientMRN` | string | Patient medical record number |
| `PatientName` | string | Patient name (LAST, FIRST) |
| `CourseName` | string | Course identifier (e.g., C1_H&N, C2_BilatHips) |
| `PlanName` | string | Plan name |
| `RadiationType` | string | Radiation type code (e.g., `X`) |
| `UniqueIsocenters` | int | Number of unique isocenters |
| `FieldGating` | int (0/1) | Whether field-level gating was used |
| `RxGating` | string | Gating type (e.g., "OSMS") or empty |
| `TotalFractions` | int | Total prescribed fractions |
| `FractionsDelivered` | int | Fractions delivered so far |
| `RxTechnique_Course` | string | Technique at course level (IMRT, SBRT, VMAT, 3D) |
| `PrimaryInsurer` | string | Primary insurance carrier |
| `RxTechnique_Day` | string | Technique used on that specific day |
| `PlanCHG_CPT` | string | Charge CPT code from plan |
| `CPT_Correct` | string | Correct CPT code per audit logic |
| `CPT_Billed` | string | Actually billed CPT code(s), can be comma-separated |
| `AuditResult` | string | PASS or FAIL |

**Business rules:**
- A `FAIL` means the billed CPT does not match the correct CPT
- `CPT_Billed` can contain multiple comma-separated codes within quotes
- Department names have `*` prefix — strip for display/joining

---

### Daily Volume - Future

- **File:** `Complete/Daily Volume - Future.csv`
- **Size:** ~5 KB
- **Refresh:** Nightly full replace
- **Used by:** Operations page

| Column | Type | Description |
|--------|------|-------------|
| `Location` | string | Machine or site name (21EX, Aberdeen, Centralia, Lacey, Simulation, TrueBeamNorth, 6EX) |
| `Date` | date (MM/DD/YYYY) | Scheduled date |
| `FirstScheduledStart` | time (HH:MM) | Earliest scheduled appointment start |
| `LastScheduledEnd` | time (HH:MM) | Latest scheduled appointment end |
| `AppointmentCount` | int | Number of scheduled appointments |
| `FirstActualStart` | time (HH:MM) | Always empty for future dates |
| `LastActualEnd` | time (HH:MM) | Always empty for future dates |

---

### Daily Volume - Past

- **File:** `Complete/Daily Volume - Past.csv`
- **Size:** ~1.6 MB
- **Refresh:** Nightly full replace
- **Used by:** Operations page

Same schema as Daily Volume - Future, but `FirstActualStart` and `LastActualEnd` are populated.

**Business rules:**
- `6EX` consistently shows no appointments (decommissioned or inactive machine)
- Lacey has the highest appointment counts across locations
- Compare scheduled vs actual times to measure punctuality

---

### Machine Errors

- **File:** `Complete/Machine Errors.csv`
- **Size:** ~808 KB
- **Refresh:** Nightly full replace
- **Used by:** Machine Performance page

| Column | Type | Description |
|--------|------|-------------|
| `UniqueRowID` | int | Unique identifier |
| `PatientId` | string | Patient identifier |
| `PatientName` | string | Patient name (LAST, FIRST) |
| `CourseId` | string | Course identifier |
| `PlanName` | string | Plan name |
| `FieldId` | string | Treatment field identifier |
| `FractionNumber` | int | Fraction number |
| `TreatmentStartTime` | datetime (M/D/YYYY H:MM:SS AM/PM) | When treatment started |
| `TreatmentEndTime` | datetime (M/D/YYYY H:MM:SS AM/PM) | When treatment ended |
| `PlannedMU` | float | Planned monitor units |
| `DeliveredMU` | float | Actually delivered monitor units |
| `Machine` | string | Machine name (21iX_CEN, 21EX, 21iX_AB) |
| `FieldCategory` | string | Field type (DynamicMLC, Arc) |
| `ElapsedTimeToNextTreatment` | float | Minutes until next treatment (recovery time) |

**Business rules:**
- An "error" is indicated by `DeliveredMU` significantly less than `PlannedMU`
- `ElapsedTimeToNextTreatment` measures recovery/downtime impact

---

### OTV Audit

- **File:** `Complete/OTV Audit.csv`
- **Size:** ~2.3 MB
- **Refresh:** Nightly full replace
- **Used by:** OTVs page

| Column | Type | Description |
|--------|------|-------------|
| `DimCourseID` | int | Course dimension ID |
| `CourseId` | string | Course identifier (e.g., C1_RUL) |
| `PatientId` | string | Patient identifier |
| `PatientName` | string | Patient name (LAST, FIRST) |
| `Department` | string | Department name (no `*` prefix) |
| `DiagnosisCodes` | string | ICD diagnosis codes |
| `DiagnosisDescriptions` | string | Diagnosis descriptions |
| `ClinicalStatus` | string | ACTIVE or COMPLETED |
| `FirstTreatmentDate` | date (MM/DD/YYYY) | First treatment date |
| `LastTreatmentDate` | date (MM/DD/YYYY) | Last treatment date |
| `TreatmentDurationDays` | int | Duration of treatment in days |
| `SessionCount_Delivery` | int | Number of delivery sessions |
| `PrescribedFractions` | int | Total prescribed fractions |
| `PrimaryFractions` | int | Primary phase fractions |
| `BoostFractions` | int | Boost phase fractions |
| `TotalPlanCount` | int | Number of plans in course |
| `PrimaryPhaseCount` | int | Number of primary phase plans |
| `BoostPhaseCount` | int | Number of boost phase plans |
| `AllowedOTVs` | int | Allowed on-treatment visits |
| `WeeklyExamActivities` | int | Weekly exam activities recorded |
| `ManagementCPTs_ExcludingNC` | int | Management CPTs excluding no-charge |
| `ManagementCPTs_WithNC` | int | Management CPTs with no-charge |
| `ManagementCPTs_Total` | int | Total management CPTs |
| `AuditResult` | string | OK, Extra Visit(s), or Too Few |

**Business rules:**
- `AllowedOTVs` is calculated from prescribed fractions (typically 1 per 5 fractions)
- `AuditResult` compares actual visits against allowed visits

---

### Physician Schedule

- **File:** `Complete/Physician Schedule.csv`
- **Size:** ~2.1 MB
- **Refresh:** Nightly full replace
- **Used by:** Tasks page (cross-reference only, no dedicated page)

| Column | Type | Description |
|--------|------|-------------|
| `ActivityName` | string | Schedule activity (OFF, WEEKEND CALL, etc.) |
| `ScheduledDate` | date (MM/DD/YYYY) | Date of the schedule block |
| `ScheduledStartDateTime` | datetime (M/D/YYYY H:MM:SS AM/PM) | Start time |
| `ScheduledEndDateTime` | datetime (M/D/YYYY H:MM:SS AM/PM) | End time |
| `PhysicianName` | string | Physician name (Last, First) |
| `ActivityNote` | string | Free text (e.g., "CLOSED - LABOR DAY") |

**Business rules:**
- Used to cross-reference task completion — identify work done while a physician was OFF or on WEEKEND CALL
- Data extends months into the future
- Four physicians: Allen Gregory, Connor Michael, Suszko Justin, Tinnel Brent

---

### Tasks

- **File:** `Complete/Tasks.csv`
- **Size:** ~8.3 MB
- **Refresh:** Nightly full replace
- **Used by:** Tasks page

| Column | Type | Description |
|--------|------|-------------|
| `DimActivityTransactionID` | int | Unique task identifier |
| `PatientId` | string | Patient identifier |
| `PatientName` | string | Patient name (LAST, FIRST) |
| `ActivityCode` | string | Task code (Draw Volumes SRS, Draw Volumes/MLC, Review Plan xxx) |
| `ActivityName` | string | Full task name (Draw Volumes / Add Rx, Review Plan/Rounds) |
| `StartDateTime` | datetime (M/D/YYYY H:MM:SS AM/PM) | When task was created/started |
| `DueDateTime` | datetime (M/D/YYYY H:MM:SS AM/PM) | SLA deadline |
| `CompletedDateTime` | datetime (M/D/YYYY H:MM:SS AM/PM) | When task was completed (empty if pending) |
| `MinutesToComplete` | float | Actual minutes to complete (empty if pending) |
| `MinutesAllowed` | float | SLA: minutes from start to deadline |
| `AssignedMD` | string | Physician assigned the task |
| `CompletingMD` | string | Physician who completed it ("NA" if pending) |
| `TreatingPhysician` | string | Treating physician for the patient |
| `PriorExamPhysician` | string | Physician from prior exam |
| `DiagnosisCodes` | string | ICD codes |
| `DiagnosisDescriptions` | string | Diagnosis descriptions |

**Business rules:**
- `CompletingMD = "NA"` means the task is still open
- `MinutesToComplete` is blank for uncompleted tasks
- `MinutesAllowed` is the SLA window in minutes from `StartDateTime`
- Cross-reference with Physician Schedule to identify after-hours or off-day completions

---

## Incremental Files

All incremental files use `UniqueRowID` as the deduplication key. New rows are appended; existing rows may be updated. Always deduplicate on `UniqueRowID`, keeping the latest version.

### Availability

- **File:** `Incremental/Availability/Availability.csv`
- **Size:** ~54 KB
- **Used by:** Operations page

| Column | Type | Description |
|--------|------|-------------|
| `Category` | string | Appointment category (Exam, Simulation) |
| `DepartmentName` | string | Department name |
| `AppointmentDateTime` | datetime (M/D/YYYY H:MM:SS AM/PM) | Appointment start |
| `ScheduledEndTime` | datetime (M/D/YYYY H:MM:SS AM/PM) | Appointment end |
| `DurationMinutes` | int | Duration in minutes |
| `AppointmentNotes` | string | Free text scheduling notes |
| `AssignedResource` | string | Physician name or machine/room (e.g., CT_RC_LACEY) |
| `ActivityName` | string | Hold/block type (HOLD SIM TIME, HOLD RE EVAL/2 FOLLOW UPS) |

**Business rules:**
- Shows future availability slots and holds
- `AssignedResource` can be either a physician name or a machine identifier
- Used to analyze scheduling lead times and find openings

---

### Billing

- **File:** `Incremental/Billing/Billing.csv`
- **Size:** ~56 MB
- **Used by:** Billing page

| Column | Type | Description |
|--------|------|-------------|
| `UniqueRowID` | int | Deduplication key |
| `PatientId` | string | Patient identifier |
| `PatientFullName` | string | Patient name (LAST, FIRST) |
| `DateOfService` | date (MM/DD/YYYY) | Service date |
| `DepartmentName` | string | Department name |
| `ProcedureCode` | string | CPT procedure code |
| `ProcedureCodeDescription` | string | CPT description |
| `CodeType` | string | Global, Technical, or Professional |
| `Quantity` | int | Number of units |
| `Modifiers` | string | CPT modifiers (26, TC, or empty) |
| `Credited` | string | "No" (boolean-like) |
| `Waived` | string | "No" (boolean-like) |
| `SupervisingPhysician` | string | Supervising physician |
| `AttendingPhysician` | string | Attending physician |
| `ReferringPhysicianDimDoctorID` | int | FK to Lookup - Referring |
| `ReferringPhysician` | string | Referring physician name |
| `ReferringPhysicianSpecialty` | string | Referring physician specialty |
| `DiagnosisCodes` | string | ICD codes |
| `DiagnosisDescriptions` | string | Diagnosis descriptions |

**Business rules:**
- `CodeType` determines the billing split: Professional (physician), Technical (facility), Global (both)
- `Modifiers`: 26 = professional component, TC = technical component
- Join to `Lookup - Patients` via `PatientId` for payor mix analysis
- Join to `Lookup - Referring` via `ReferringPhysicianDimDoctorID` for referral billing

---

### Clinic Visits

- **File:** `Incremental/ClinicVisits/Clinic Visits.csv`
- **Size:** ~11 MB
- **Used by:** Clinic Visits page, Referrals page

| Column | Type | Description |
|--------|------|-------------|
| `UniqueRowID` | int | Deduplication key |
| `PatientId` | string | Patient identifier |
| `PatientFullName` | string | Patient name (LAST, FIRST) |
| `DepartmentName` | string | Department name |
| `AppointmentCreatedDate` | date (MM/DD/YYYY) | When the appointment was created |
| `ScheduledDateTime` | datetime (M/D/YYYY H:MM:SS AM/PM) | Scheduled appointment time |
| `DaysFromCreatedToAppt` | int | Lead time in days |
| `DurationMinutes` | int | Appointment duration |
| `ActivityName` | string | Visit type (Consult, Follow-Up, Virtual Consult/Follow Up) |
| `ActivityStatus` | string | Status (Manually Completed, Cancelled) |
| `AppointmentNotes` | string | Clinical notes |
| `SupervisingPhysician` | string | Supervising physician |
| `AppointmentPhysician` | string | Physician on the appointment |
| `AttendingPhysician` | string | Attending physician |
| `ReferringPhysicianDimDoctorID` | int | FK to Lookup - Referring |
| `ReferringPhysicianSpecialty` | string | Referring physician specialty |
| `ReferringPhysician` | string | Referring physician name |
| `DiagnosisCodes` | string | ICD codes |
| `DiagnosisDescriptions` | string | Diagnosis descriptions |
| `ProcedureCodes` | string | CPT codes (can be comma-separated) |
| `ProcedureDescriptions` | string | CPT descriptions |
| `CPT_Types` | string | CPT type classification |
| `HasSimulationWithin180Days` | int (0/1) | Whether patient had a sim within 180 days |
| `SimulationDateTime` | datetime | Date of linked simulation |
| `DaysToSimulation` | int | Days from visit to simulation |

**Business rules:**
- `ActivityName` determines visit type: Consult, Follow-Up, Virtual Consult/Follow Up
- `HasSimulationWithin180Days` indicates consult-to-treatment conversion
- Join to `Lookup - Referring` via `ReferringPhysicianDimDoctorID` for referral analysis
- Join to `Lookup - Patients` via `PatientId` for payor mix per consult

---

### Courses

- **File:** `Incremental/Courses/Courses.csv`
- **Size:** ~5.1 MB
- **Used by:** Courses page, Billing (payor mix per course)

| Column | Type | Description |
|--------|------|-------------|
| `UniqueRowID` | int | Deduplication key |
| `PatientId` | string | Patient identifier |
| `PatientName` | string | Patient name (LAST, FIRST) |
| `CourseId` | string | Course identifier (e.g., C1_H&N, C2_BilatHips) |
| `CourseStartDateTime` | datetime (M/D/YYYY H:MM:SS AM/PM) | Course start |
| `ClinicalStatus` | string | ACTIVE or COMPLETED |
| `FirstTreatmentDate` | datetime | First treatment date |
| `LastTreatmentDate` | datetime | Last treatment date |
| `TreatmentDurationDays` | int | Treatment duration in days |
| `FractionsDelivered` | int | Fractions delivered |
| `TreatingPhysician` | string | Treating physician |
| `FractionsPrescribed` | int | Prescribed fractions |
| `ConsultPhysician` | string | Consult physician |
| `ReferringPhysicianID` | int | FK to Lookup - Referring |
| `PlanCount` | int | Number of plans in course |
| `TreatmentTechniques` | string | Technique(s): IMRT, VMAT, 3D |
| `ReferringPhysician` | string | Referring physician name |
| `PrescriptionSites` | string | Anatomical treatment sites |
| `ReferringPhysicianSpecialty` | string | Referring physician specialty |
| `PlanNames` | string | Plan name(s) |
| `Departments` | string | Department(s), can be comma-separated |
| `Machines` | string | Machine(s), can be comma-separated |
| `DiagnosisCodes` | string | ICD codes |
| `DiagnosisDescriptions` | string | Diagnosis descriptions |

**Business rules:**
- `CourseId` follows pattern: `C{N}_{Site}` (e.g., C1_H&N = first course, head & neck)
- `Departments` and `Machines` can be multi-valued for patients who transfer sites
- `TreatmentTechniques`: 3D, IMRT, VMAT
- Join to `Lookup - Patients` via `PatientId` for payor mix per course

---

### Plans

- **File:** `Incremental/Plans/Plans.csv`
- **Size:** ~9.5 MB
- **Used by:** Plans page

| Column | Type | Description |
|--------|------|-------------|
| `UniqueRowID` | int | Deduplication key |
| `PatientId` | string | Patient identifier |
| `PatientName` | string | Patient name (LAST, FIRST) |
| `CourseId` | string | Course identifier |
| `CourseStartDateTime` | datetime (M/D/YYYY H:MM:SS AM/PM) | Course start |
| `ClinicalStatus` | string | ACTIVE or COMPLETED |
| `PlanSetupId` | string | Plan name/identifier (descriptive, not numeric) |
| `PlanCreationDate` | datetime | When plan was created |
| `PlanStatus` | string | Plan status (Treatment Approved) |
| `NoFractionsPlanned` | int | Planned fractions |
| `NoFractionsDelivered` | int | Delivered fractions |
| `NoFractionsRemaining` | int | Remaining fractions |
| `NoSessionPlanned` | int | Planned sessions |
| `SessionBasedFractionCount` | int | Session-based fraction count |
| `FractionsPrescribed` | int | Prescribed fractions |
| `FirstTreatmentDate` | datetime | First treatment date |
| `LastTreatmentDate` | datetime | Last treatment date |
| `TreatmentDurationDays` | int | Treatment duration in days |
| `TreatmentTechnique` | string | Technique (IMRT, VMAT, 3D) |
| `DiagnosisCodes` | string | ICD codes |
| `DiagnosisDescriptions` | string | Diagnosis descriptions |
| `PrescriptionSite` | string | Anatomical treatment site |
| `Departments` | string | Department(s) |
| `Machines` | string | Machine(s) |
| `ReferringPhysician` | string | Referring physician name |
| `TreatingPhysician` | string | Treating physician |
| `ReferringPhysicianSpecialty` | string | Referring specialty |
| `ConsultPhysician` | string | Consult physician |
| `ReferringPhysicianID` | int | FK to Lookup - Referring |

**Business rules:**
- Plan is a child of Course (join via `CourseId` + `PatientId`)
- `NoFractionsRemaining = NoFractionsPlanned - NoFractionsDelivered`
- `PlanSetupId` is descriptive (e.g., "H&N", "Pros/ProxSV", "LUL Lung")
- `Departments` and `Machines` can be multi-valued

---

### Simulations

- **File:** `Incremental/Simulations/Simulations.csv`
- **Size:** ~5.8 MB
- **Used by:** Simulations page

| Column | Type | Description |
|--------|------|-------------|
| `UniqueRowID` | int | Deduplication key |
| `PatientId` | string | Patient identifier |
| `PatientFullName` | string | Patient name (LAST, FIRST) |
| `AppointmentCreatedDate` | date (MM/DD/YYYY) | When appointment was created |
| `ScheduledDateTime` | datetime (M/D/YYYY H:MM:SS AM/PM) | Scheduled sim time |
| `DurationMinutes` | int | Duration (60 or 90 minutes) |
| `DaysFromCreatedToAppt` | int | Lead time in days |
| `ActivityName` | string | Sim type (Initial Simulation, Stereotactic Simulation, Initial Centralia-in Lacey, Initial Aberdeen Simulation, Re-Simulation) |
| `ActivityStatus` | string | Status (Manually Completed) |
| `PriorClinicExamActivityName` | string | Prior clinic exam type |
| `PriorClinicExamAppointmentDate` | date | Prior clinic exam date |
| `SupervisingPhysician` | string | Supervising physician |
| `ConsultPhysician` | string | Consult physician |
| `DaysFromClinicExamToSimulation` | int | Days from consult to sim |
| `AttendingPhysician` | string | Attending physician |
| `FirstTreatmentDate` | datetime | First treatment date |
| `DaysFromClinicExamToTreatment` | int | Days from consult to first treatment |
| `DaysFromSimToTreatment` | int | Days from sim to first treatment |
| `ReferringPhysicianDimDoctorID` | int | FK to Lookup - Referring |
| `ProcedureCodes` | string | CPT codes |
| `ReferringPhysician` | string | Referring physician name |
| `ProcedureDescriptions` | string | CPT descriptions |
| `ReferringPhysicianSpecialty` | string | Referring specialty |
| `DiagnosisCodes` | string | ICD codes |
| `DiagnosisDescriptions` | string | Diagnosis descriptions |

**Business rules:**
- `ActivityName` indicates simulation type and cross-site patterns
- "Initial Centralia-in Lacey" = Centralia patient simulated at Lacey
- Key timing metrics: exam→sim, sim→treatment, exam→treatment
- Duration: 60 min (standard) or 90 min (complex/cross-site)

---

### Treatment

- **File:** `Incremental/Treatment/Treatment.csv`
- **Size:** ~1.8 MB
- **Used by:** Operations page

| Column | Type | Description |
|--------|------|-------------|
| `Location` | string | Site or machine (Aberdeen, Centralia, Lacey, Lacey - 21EX, Lacey - TrueBeamNorth) |
| `Date` | date (MM/DD/YYYY) | Treatment date |
| `CompletedAppointments` | int | Completed appointment count |
| `UniquePatients` | int | Unique patients treated |
| `UniquePlans` | int | Unique plans treated |
| `NewStarts_ByFraction` | int | New starts (first fraction) |
| `NewStarts_ByCourseFirstTreatmentDate` | int | New starts (by course start) |
| `Fields_Electron` | int | Electron field count |
| `Fields_StaticMLC` | int | Static MLC field count |
| `Fields_DynamicMLC` | int | Dynamic MLC field count |
| `Fields_Arc` | int | Arc field count |
| `Patients_IMRT` | int | IMRT patient count |
| `Patients_Electron` | int | Electron patient count |
| `Patients_VMAT` | int | VMAT patient count |
| `Patients_3D` | int | 3D patient count |
| `Patients_SRS` | int | SRS patient count |
| `Plans_IMRT` | int | IMRT plan count |
| `Plans_VMAT` | int | VMAT plan count |
| `Plans_Electron` | int | Electron plan count |
| `Plans_3D` | int | 3D plan count |
| `Patients_SBRT` | int | SBRT patient count |
| `Plans_SRS` | int | SRS plan count |
| `Plans_SBRT` | int | SBRT plan count |

**Business rules:**
- `Location` includes both site-level (Aberdeen, Centralia, Lacey) and machine-level (Lacey - 21EX, Lacey - TrueBeamNorth) breakdowns
- Two new-start definitions: by fraction number vs by course first treatment date
- All columns are daily aggregates

---

### Treatment - Detail

- **File:** `Incremental/TreatmentDetail/Treatment - Detail.csv`
- **Size:** ~141 MB (largest file)
- **Used by:** Home page (physician census), Operations (drilldown)

| Column | Type | Description |
|--------|------|-------------|
| `SessionUniqueID` | int | Unique treatment session ID |
| `TreatmentDate` | date (MM/DD/YYYY) | Treatment date |
| `Machine` | string | Machine name |
| `Department` | string | Department (prefixed with `*`) |
| `PatientMRN` | string | Patient MRN |
| `PatientName` | string | Patient name (LAST, FIRST) |
| `CourseName` | string | Course identifier |
| `PlanNames` | string | Plan name(s) |
| `AppointmentDateTime` | datetime | Appointment time |
| `TreatmentStartTime` | datetime | Actual treatment start |
| `TreatmentEndTime` | datetime | Actual treatment end |
| `ElapsedMinutes` | float | Treatment duration in decimal minutes |
| `FieldCount` | int | Number of fields |
| `RadiationType` | string | Radiation type code |
| `PlanTechniques` | string | Technique (VMAT, IMRT, 3D) |
| `Fields_Electron` | int | Electron field count |
| `Fields_Arc` | int | Arc field count |
| `Fields_StaticMLC` | int | Static MLC field count |
| `Fields_DynamicMLC` | int | Dynamic MLC field count |
| `FieldGating` | int (0/1) | Field gating flag |
| `RxGating` | string | Gating type ("BREATH HOLD" or empty) |
| `HasOSMS` | int (0/1) | Optical surface monitoring flag |
| `TotalFractions` | int | Total prescribed fractions |
| `FractionNumber` | int | Current fraction number |
| `FractionsDelivered` | int | Fractions delivered so far |
| `UniqueIsocenters` | int | Number of isocenters |
| `IsNewStart_ByFraction` | int (0/1) | New start flag (by fraction) |
| `IsNewStart_ByCourse` | int (0/1) | New start flag (by course) |
| `TreatingPhysician` | string | Treating physician |
| `BillingPhysician` | string | Billing physician |
| `ConsultPhysician` | string | Consult physician |
| `ReferringPhysician` | string | Referring physician name |
| `ReferringSpecialty` | string | Referring specialty |
| `DiagnosisCodes` | string | ICD codes |
| `DiagnosisDescriptions` | string | Diagnosis descriptions |
| `PrimaryInsurer` | string | Primary insurance carrier |
| `CPT_Billed` | string | Billed CPT code |

**Business rules:**
- One row per treatment session (most granular treatment data)
- `Department` has `*` prefix — strip for display/joining
- `ElapsedMinutes` is decimal (e.g., 1.13, 4.93)
- Aggregate by `TreatingPhysician` + `TreatmentDate` to get daily patient count per MD (for Home page physician census chart)

---

### Weekly Visits

- **File:** `Incremental/WeeklyVisits/Weekly Visits.csv`
- **Size:** ~19 MB
- **Used by:** OTVs page

| Column | Type | Description |
|--------|------|-------------|
| `UniqueRowID` | int | Deduplication key |
| `PatientId` | string | Patient identifier |
| `PatientFullName` | string | Patient name (LAST, FIRST) |
| `AppointmentDateTime` | datetime (M/D/YYYY H:MM:SS AM/PM) | Appointment time |
| `DurationMinutes` | int | Duration (typically 5 minutes) |
| `ActivityName` | string | Activity type (e.g., "Weekly check oncochart") |
| `ActivityStatus` | string | Status (Manually Completed) |
| `DepartmentName` | string | Department name |
| `AppointmentPhysician` | string | Physician on the appointment |
| `TreatingPhysician` | string | Treating physician |
| `ConsultPhysician` | string | Consult physician |
| `ReferringPhysicianID` | int | FK to Lookup - Referring |
| `ReferringPhysician` | string | Referring physician name |
| `ReferringPhysicianSpecialty` | string | Referring specialty |
| `ProcedureCodes` | string | CPT code (typically 77427) |
| `ProcedureDescriptions` | string | CPT description |
| `DiagnosisCodes` | string | ICD codes |
| `DiagnosisDescriptions` | string | Diagnosis descriptions |

**Business rules:**
- CPT 77427 = "Radiation treatment management, five treatments"
- Duration is consistently 5 minutes
- `AppointmentPhysician` vs `TreatingPhysician` can differ (coverage model)
- Pairs with OTV Audit for compliance analysis

---

### Workflow

- **File:** `Incremental/Workflow/Workflow.csv`
- **Size:** ~15 MB
- **Used by:** Workflow page

| Column | Type | Description |
|--------|------|-------------|
| `UniqueRowID` | int | Deduplication key |
| `PatientId` | string | Patient identifier |
| `PatientFullName` | string | Patient name (LAST, FIRST) |
| `AppointmentCreatedDate` | date | Appointment creation date |
| `ScheduledDateTime` | datetime | Scheduled appointment time |
| `DurationMinutes` | int | Appointment duration |
| `DaysFromCreatedToAppt` | int | Lead time in days |
| `ActivityName` | string | Visit type (Consult, Follow-Up, Virtual Consult/Follow Up) |
| `ActivityStatus` | string | Status (Manually Completed, Cancelled) |
| `AppointmentNotes` | string | Clinical notes |
| `AppointmentPhysician` | string | Appointment physician |
| `TreatingPhysician` | string | Treating physician |
| `ReferringPhysician` | string | Referring physician |
| `ReferringPhysicianSpecialty` | string | Referring specialty |
| `ReferringPhysicianRecordID` | int | FK to Lookup - Referring |
| `ProcedureCodes` | string | CPT codes |
| `DiagnosisCodes` | string | ICD codes |
| `ProcedureDescriptions` | string | CPT descriptions |
| `DiagnosisDescriptions` | string | Diagnosis descriptions |
| `SimulationActivityName` | string | Linked simulation type |
| `SimulationCreatedDate` | date | Sim creation date |
| `SimulationDateTime` | datetime | Sim appointment time |
| `DaysToSimulation` | int | Days from consult to sim |
| `DrawStartDateTime` | datetime | Draw volumes task start |
| `DrawDueDateTime` | datetime | Draw volumes task deadline |
| `DrawCompletedDateTime` | datetime | Draw volumes completion |
| `DrawMinutesToComplete` | float | Draw volumes actual minutes |
| `DrawMinutesAllowed` | float | Draw volumes SLA minutes |
| `DrawCompletingMD` | string | MD who completed draw volumes |
| `MinutesFromSimToDrawCompletion` | float | Minutes from sim to draw completion |
| `IsodosePlanStartDateTime` | datetime | Isodose plan task start |
| `IsodosePlanDueDateTime` | datetime | Isodose plan deadline |
| `IsodosePlanCompletedDateTime` | datetime | Isodose plan completion |
| `IsodosePlanMinutesToComplete` | float | Isodose plan actual minutes (wall-clock) |
| `IsodosePlanMinutesAllowed` | float | Isodose plan SLA minutes |
| `IsodosePlanCompletingUser` | string | User who completed isodose plan |
| `DaysFromSimToIsodose` | int | Days from sim to isodose completion |
| `ReviewPlanStartDateTime` | datetime | Review plan task start |
| `ReviewPlanDueDateTime` | datetime | Review plan deadline |
| `ReviewPlanCompletedDateTime` | datetime | Review plan completion |
| `ReviewPlanMinutesToComplete` | float | Review plan actual minutes |
| `ReviewPlanMinutesAllowed` | float | Review plan SLA minutes |
| `ReviewPlanCompletingMD` | string | MD who completed review |
| `DaysFromSimToReview` | int | Days from sim to review completion |
| `FirstTreatmentDate` | datetime | First treatment date |
| `DaysFromReviewToTreatment` | int | Days from review to first treatment |

**Business rules:**
- Tracks the complete patient journey: Consult → Sim → Draw → Isodose → Review → Treatment
- Each workflow step has start/due/completed datetimes plus minutes to complete and SLA
- `IsodosePlanMinutesToComplete` is wall-clock elapsed time, not active work time (can be thousands of minutes = days)
- Many fields are empty for Follow-Up visits (no new treatment workflow triggered)
- Only Consult rows with downstream sim/treatment data are relevant for Sankey/funnel analysis

---

## Lookup / Reference Tables

### Lookup - Diagnosis

- **File:** `Lookup/Lookup - Diagnosis.csv`
- **Size:** ~204 KB
- **Join key:** `DiagnosisCode` (join to `DiagnosisCodes` column in other tables — note: other tables may have comma-separated codes)

| Column | Type | Description |
|--------|------|-------------|
| `DiagnosisCode` | string | ICD-9 or ICD-10 code |
| `DiagnosisDescription` | string | Short description |
| `DiagnosisFullTitle` | string | Full title |
| `DiagnosisTable` | string | Code system (ICD-9-CM, ICD-10) |
| `SiteDesc` | string | Cancer site (e.g., Pharynx, Lip and Oral Cavity) or "NA" |
| `BodySystemDesc` | string | Body system (e.g., Head & Neck, Thorax) or "NA" |
| `DiagnosisStatus` | string | Active or Inactive |
| `DiagnosisRanking` | string | Primary (and others) |
| `Laterality` | string | Left, Right, Bilateral, or NA |
| `Stage` | string | Cancer stage |
| `ICDSchemeID` | int | ICD scheme identifier |
| `PatientCount` | int | Number of patients with this diagnosis |
| `DimDiagnosisCodeID` | int | Surrogate key |

**Business rules:**
- Use `SiteDesc` and `BodySystemDesc` for cancer site analysis
- Mixed ICD-9 and ICD-10 codes — both are valid
- Non-cancer diagnoses may have "NA" for site/body system
- `DiagnosisCodes` in other tables can be comma-separated — split before joining

---

### Lookup - Patients

- **File:** `Lookup/Lookup - Patients.csv`
- **Size:** ~2.6 MB
- **Join key:** `PatientId`

| Column | Type | Description |
|--------|------|-------------|
| `PatientId` | string | Patient identifier (varies: 11-digit or shorter legacy) |
| `PatientName` | string | Patient name (Last, First — mixed case) |
| `FirstAppointment` | date (MM/DD/YYYY) | First appointment date |
| `LastAppointment` | date (MM/DD/YYYY) | Last appointment date |
| `DateOfBirth` | date (MM/DD/YYYY) | Date of birth |
| `PatientAddressLine1` | string | Street address |
| `City` | string | City |
| `PatientAddressLine2` | string | Address line 2 |
| `Zip` | string | ZIP code |
| `County` | string | County (can be empty) |
| `PrimaryInsurance` | string | Primary insurance carrier |
| `OtherInsurers` | string | Other insurers (can be comma-separated) |
| `Department` | string | Primary department (some with `*` prefix) |

**Business rules:**
- Contains PII — handle appropriately
- Use `City`, `County`, `Zip` for geographic mapping (Patients page)
- Use `PrimaryInsurance` for payor mix analysis (Billing page)
- `Department` prefix `*` is inconsistent — strip for joining
- `PatientId` format varies between modern (60xxxxxxxxx) and legacy (short numeric)

---

### Lookup - Referring

- **File:** `Lookup/Lookup - Referring.csv`
- **Size:** ~916 KB
- **Join key:** `DimDoctorID` (matches `ReferringPhysicianDimDoctorID` or `ReferringPhysicianID` in other tables)

| Column | Type | Description |
|--------|------|-------------|
| `DimDoctorID` | int | Surrogate key (join target) |
| `DoctorFullName` | string | Full name |
| `DoctorFirstName` | string | First name |
| `DoctorLastName` | string | Last name |
| `DoctorSpecialty` | string | Medical specialty |
| `DoctorId` | string | NPI number (10-digit) |
| `DoctorCompleteAddress` | string | Full address (comma-delimited in single field) |
| `IsPrimaryDoctorAddress` | string | Primary address flag |
| `DoctorAddressType` | string | Address type |
| `DoctorPrimaryPhoneNumber` | string | Phone number |
| `DoctorSecondaryPhoneNumber` | string | Secondary phone |
| `PatientCount` | int | Number of referred patients |
| `DoctorPagerNumber` | string | Pager number |
| `DoctorFaxNumber` | string | Fax number |
| `DoctorEMailAddress` | string | Email |
| `DoctorInstitution` | string | Institution (e.g., Providence, Seattle Childrens Hospital) |
| `ResourceObjectStatus` | string | Active status |
| `DoctorOriginationDate` | datetime (M/D/YYYY H:MM:SS AM/PM) | When record was created |
| `DoctorTerminationDate` | datetime | When record was terminated |
| `Schedulable` | string | Whether schedulable (typically "No" for referring MDs) |
| `ResourceType` | string | Resource type (Referring Physician) |
| `DoctorComment` | string | Free text comments |
| `DoctorAddressComment` | string | Address notes |
| `ctrResourceSer` | int | ARIA resource serial |

**Business rules:**
- `DimDoctorID` is the FK used across Clinic Visits, Billing, Simulations, Courses, etc.
- Different tables use different FK column names: `ReferringPhysicianDimDoctorID`, `ReferringPhysicianID`, `ReferringPhysicianRecordID`
- `DoctorCompleteAddress` needs parsing (comma-delimited: street, city, state, zip)
- `DoctorId` is the NPI — useful for external lookups
- `PatientCount` is a snapshot count, not a live aggregate

---

## Join Map

```
Lookup - Patients (PatientId)
  ├── Clinic Visits (PatientId)
  ├── Billing (PatientId)
  ├── Courses (PatientId)
  ├── Plans (PatientId)
  ├── Simulations (PatientId)
  ├── Weekly Visits (PatientId)
  ├── Workflow (PatientId)
  ├── Treatment - Detail (PatientMRN)  ← different column name
  └── Machine Errors (PatientId)

Lookup - Referring (DimDoctorID)
  ├── Clinic Visits (ReferringPhysicianDimDoctorID)
  ├── Billing (ReferringPhysicianDimDoctorID)
  ├── Simulations (ReferringPhysicianDimDoctorID)
  ├── Courses (ReferringPhysicianID)           ← different name
  ├── Plans (ReferringPhysicianID)             ← different name
  ├── Weekly Visits (ReferringPhysicianID)     ← different name
  └── Workflow (ReferringPhysicianRecordID)    ← different name

Lookup - Diagnosis (DiagnosisCode)
  └── All tables with DiagnosisCodes column (comma-separated, split before join)

Courses (CourseId + PatientId)
  └── Plans (CourseId + PatientId)
```

**Join pitfalls:**
- `PatientId` vs `PatientMRN` — Treatment Detail uses `PatientMRN` instead of `PatientId`
- Referring FK column name varies across tables (see above)
- `DiagnosisCodes` is comma-separated in transactional tables — split before joining to Lookup
- `Department` naming: some tables prefix with `*`, some don't — normalize before cross-table joins

---

## Known Physicians

Four radiation oncologists appear across all data:

| Name | Format variations |
|------|-------------------|
| Allen, Gregory | Allen, Gregory |
| Connor, Michael | Connor, Michael |
| Suszko, Justin | Suszko, Justin |
| Tinnel, Brent | Tinnel, Brent |

---

## Departments / Locations

| Department | Machines | Notes |
|-----------|----------|-------|
| Lacey | TrueBeamNorth, 21EX | Main site, highest volume. Sometimes prefixed with `*` |
| Centralia | 21iX_CEN | |
| Aberdeen | 21iX_AB | |

Additional location values in Daily Volume / Treatment:
- `Simulation` (CT sim room)
- `6EX` (appears inactive — no appointments)
- `Lacey - 21EX`, `Lacey - TrueBeamNorth` (machine-level breakdowns)
