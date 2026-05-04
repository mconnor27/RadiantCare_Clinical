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
- **Size:** ~463 KB
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
| `FxOverride` | int | Fraction override count (0 if none) |
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

### Availability (legacy — superseded by ScheduleUpcoming)

- **File:** `Complete/Availability.csv`
- **Size:** ~53 KB
- **Refresh:** Legacy live feed (~30–60 min cadence) via Power Automate → R2; nightly full replace on disk. **No longer the active source for any page.**
- **Used by:** Nothing in the current code path. `load_availability()` is retained for back-compat reference but Home, Operations, and Scheduling all moved to `load_schedule_upcoming()`.

| Column | Type | Description |
|--------|------|-------------|
| `UniqueRowID` | int | Row identifier (full-refresh snapshot — not used for dedup) |
| `Category` | string | Appointment category (Exam, Simulation) |
| `DepartmentName` | string | Department name |
| `AppointmentDateTime` | datetime (M/D/YYYY H:MM:SS AM/PM) | Appointment start |
| `ScheduledEndTime` | datetime (M/D/YYYY H:MM:SS AM/PM) | Appointment end |
| `DurationMinutes` | int | Duration in minutes |
| `AppointmentNotes` | string | Free text scheduling notes (dropped at sanitize → `HasNote` boolean) |
| `ActivityName` | string | Hold/block type (HOLD SIM TIME, HOLD CONSULT, HOLD RE EVAL/2 FOLLOW UPS) |
| `AssignedResource` | string | Physician name or machine/room (e.g., CT_RC_LACEY) |
| `SlotTaken` | string | Whether the slot has been filled (Yes/No) |

**Business rules:**
- Shows future availability slots and holds (typically a two-month forward window)
- `AssignedResource` can be either a physician name or a machine identifier
- `SlotTaken` indicates if a hold has been converted to an actual appointment
- Used to analyze scheduling lead times and find openings
- Full-refresh snapshot — each export replaces the prior file (no incremental concatenation)

---

### Daily Volume - Future

- **File:** `Complete/Daily Volume - Future.csv`
- **Size:** ~11 KB
- **Refresh:** Nightly full replace
- **Used by:** Operations page

| Column | Type | Description |
|--------|------|-------------|
| `Site` | string | Site name (Aberdeen, Centralia, Lacey) — currently empty, site derived from `Resource` |
| `Category` | string | Row category: Treatment, Simulation, or Total |
| `Date` | date (MM/DD/YYYY) | Scheduled date |
| `Resource` | string | Machine or resource name (21EX, 21iX_AB, 21iX_CEN, TrueBeamNorth, CT_CEN, CT_Sim, 6EX) |
| `FirstScheduledStart` | time (HH:MM) | Earliest scheduled appointment start |
| `LastScheduledEnd` | time (HH:MM) | Latest scheduled appointment end |
| `AppointmentCount` | int | Number of scheduled appointments |
| `FirstActualStart` | time (HH:MM) | Always empty for future dates |
| `LastActualEnd` | time (HH:MM) | Always empty for future dates |
| `NewStartCount` | int | Number of new treatment starts (Future only) |
| `ScheduledActiveMinutes` | int | Total scheduled active minutes (sum of scheduled durations) |
| `ActualActiveMinutes` | int | Total actual active minutes (empty for future) |
| `ApptActualMinutes` | int | Actual appointment minutes (empty for future) |

**Business rules:**
- `Site` column is currently unpopulated — derive site from `Resource` using machine-to-department mapping
- `Category` = "Total" rows aggregate Treatment + Simulation for a given date/resource
- `NewStartCount` is only present in the Future file, not Past

---

### Daily Volume - Past

- **File:** `Complete/Daily Volume - Past.csv`
- **Size:** ~3.5 MB
- **Refresh:** Nightly full replace
- **Used by:** Operations page

| Column | Type | Description |
|--------|------|-------------|
| `Site` | string | Site name — currently empty, site derived from `Resource` |
| `Category` | string | Row category: Treatment, Simulation, or Total |
| `Date` | date (MM/DD/YYYY) | Scheduled date |
| `Resource` | string | Machine or resource name (21EX, 21iX_AB, 21iX_CEN, TrueBeamNorth, CT_CEN, CT_Sim, 6EX) |
| `FirstScheduledStart` | time (HH:MM) | Earliest scheduled appointment start |
| `LastScheduledEnd` | time (HH:MM) | Latest scheduled appointment end |
| `AppointmentCount` | int | Number of scheduled appointments |
| `FirstActualStart` | time (HH:MM) | Earliest actual appointment start |
| `LastActualEnd` | time (HH:MM) | Latest actual appointment end |
| `ScheduledActiveMinutes` | int | Total scheduled active minutes |
| `ActualActiveMinutes` | int | Total actual active minutes |
| `ApptActualMinutes` | int | Actual appointment minutes |

**Business rules:**
- Same schema as Future but without `NewStartCount`, and actual time fields are populated
- `Site` is empty — derive site from `Resource` using machine-to-department mapping
- `Category` rows allow filtering Treatment vs Simulation vs Total aggregates
- Compare `ScheduledActiveMinutes` vs `ActualActiveMinutes` for utilization analysis

---

### Machine Errors

- **File:** `Complete/Machine Errors.csv`
- **Size:** ~811 KB
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
| `FxOverride` | int | Fraction override count (0 if none) |
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
- **Size:** ~2.4 MB
- **Refresh:** Nightly full replace
- **Used by:** Tasks page (cross-reference only, no dedicated page)

| Column | Type | Description |
|--------|------|-------------|
| `ActivityName` | string | Schedule activity (OFF, WEEKEND CALL, etc.) |
| `ScheduledDate` | date (MM/DD/YYYY) | Date of the schedule block |
| `ScheduledStartDateTime` | datetime (M/D/YYYY H:MM:SS AM/PM) | Start time |
| `ScheduledEndDateTime` | datetime (M/D/YYYY H:MM:SS AM/PM) | End time |
| `PhysicianName` | string | Physician name (Last, First) |
| `DepartmentName` | string | Department name (prefixed with `*`, e.g., `*Lacey`) |
| `ActivityNote` | string | Free text (e.g., "CLOSED - LABOR DAY") |

**Business rules:**
- Used to cross-reference task completion — identify work done while a physician was OFF or on WEEKEND CALL
- Data extends months into the future
- Four physicians: Allen Gregory, Connor Michael, Suszko Justin, Tinnel Brent
- `DepartmentName` has `*` prefix — strip for display/joining

---

### Schedule Upcoming

- **File:** `Complete/ScheduleUpcoming.csv`
- **Size:** ~85 KB
- **Refresh:** Live feed — ARIA writes the CSV directly to R2 (no Power Automate / no sanitize / no daily tarball). The dashboard loader fetches it with a 5-minute TTL.
- **Used by:** Home page, Operations page, Scheduling page

| Column | Type | Description |
|--------|------|-------------|
| `UniqueRowID` | int | Row identifier (full-refresh snapshot — not used for dedup) |
| `BookingStatus` | string | `Available` (open hold) or `Booked` (already-scheduled appointment) |
| `WorkflowType` | string | `Simulation` or `Consult` |
| `ActivityName` | string | Slot type / appointment name (HOLD SIM TIME, HOLD CONSULT, HOLD RE EVAL/2 FOLLOW UPS, Initial Simulation, Consult, …) |
| `ActivityCategory` | string | `Exam` or `Simulation` (renamed to `Category` by the loader) |
| `DepartmentName` | string | Department name (renamed to `Department` by the loader) |
| `ScheduledDateTime` | datetime (M/D/YYYY H:MM:SS AM/PM) | Slot start (renamed to `AppointmentDateTime` by the loader) |
| `ScheduledEndTime` | datetime (M/D/YYYY H:MM:SS AM/PM) | Slot end |
| `DurationMinutes` | int | Duration in minutes |
| `AssignedResource` | string | Physician name (exam rows) or scanner identifier (simulation rows) |
| `ActivityStatus` | string | `Open` for booked rows; blank for available holds |
| `SlotTaken` | string | `No` for available holds; blank for booked rows. The loader overrides this from BookingStatus to give callers a stable Yes/No filter — see below. |

**Business rules:**
- Successor to the legacy Availability extract — combines open holds AND already-booked appointments in a single feed
- Two-month forward window (hard-coded `GETDATE() → +2 months` at extract time)
- Loader normalizes column names to the legacy Availability schema (`Department`, `Category`, `AppointmentDateTime`) so downstream consumers don't need to learn a second vocabulary
- Loader rewrites `SlotTaken` from `BookingStatus` (`Booked → "Yes"`, `Available → "No"`) so the existing `df["SlotTaken"] != "Yes"` "open only" filter keeps meaning what it always did
- Loader handling of `ActivityStatus = "Cancelled"` rows is informative-aware: if some other (non-cancelled) row covers the same (`AppointmentDateTime`, `AssignedResource`) the cancellation is dropped as redundant; if nothing else covers that time block — staff didn't recreate a placeholder — the cancellation is restored as an Available HOLD (with `ActivityName` remapped via `Consult → HOLD CONSULT`, `Re-eval`/`Follow-Up → HOLD RE EVAL/2 FOLLOW UPS`, and any Simulation-workflow row → `HOLD SIM TIME`) so the slot stays visible in open-capacity views. The daily 8:00 AM 30-minute `HOLD SIM TIME` warm-up placeholder is always dropped (not a bookable slot — it just exists to warm the linac).
- No `AppointmentNotes` column → no PHI to scrub → no sanitize step. Production reads the CSV from R2 directly; local dev reads it from the OneDrive `Complete/` folder. In PHI_MODE, the disk loader falls back to the raw OneDrive folder since the sanitized tree never gets a copy.

---

### Tasks

- **File:** `Complete/Tasks.csv`
- **Size:** ~10 MB
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
| `MinutesFromSimToDrawCompletion` | float | Minutes from simulation end to draw volumes completion |
| `CompletingMD` | string | Physician who completed it ("NA" if pending) |
| `DrawCreationDateTime` | datetime (M/D/YYYY H:MM:SS AM/PM) | When the draw volumes task was created |
| `SimulationDateTime` | datetime (M/D/YYYY H:MM:SS AM/PM) | Linked simulation appointment time |
| `TreatingPhysician` | string | Treating physician for the patient |
| `SimScheduledEndDateTime` | datetime (M/D/YYYY H:MM:SS AM/PM) | Scheduled end time of the linked simulation |
| `PriorExamPhysician` | string | Physician from prior exam |
| `SimActualEndDateTime` | datetime (M/D/YYYY H:MM:SS AM/PM) | Actual end time of the linked simulation |
| `DiagnosisCodes` | string | ICD codes |
| `DiagnosisDescriptions` | string | Diagnosis descriptions |

**Business rules:**
- `CompletingMD = "NA"` means the task is still open
- `MinutesToComplete` is blank for uncompleted tasks
- `MinutesAllowed` is the SLA window in minutes from `StartDateTime`
- `MinutesFromSimToDrawCompletion` links draw tasks to their triggering simulation — useful for measuring sim→draw turnaround
- `SimulationDateTime`, `SimScheduledEndDateTime`, `SimActualEndDateTime` provide simulation context for draw/review tasks
- `DrawCreationDateTime` tracks when the draw task was spawned (may differ from `StartDateTime`)
- Cross-reference with Physician Schedule to identify after-hours or off-day completions

---

## Incremental Files

All incremental files use `UniqueRowID` as the deduplication key. New rows are appended; existing rows may be updated. Always deduplicate on `UniqueRowID`, keeping the latest version.

### Billing

- **File:** `Incremental/Billing/Billing.csv`
- **Size:** ~201 MB
- **Used by:** Billing page

| Column | Type | Description |
|--------|------|-------------|
| `UniqueRowID` | int | Deduplication key |
| `PatientId` | string | Patient identifier |
| `PatientFullName` | string | Patient name (LAST, FIRST) |
| `DateOfService` | date (MM/DD/YYYY) | Service date |
| `ActivityName` | string | Activity type (Daily Treatment, Consult, etc.) |
| `DepartmentName` | string | Department name |
| `ActivityCategory` | string | Category: Treatment, Exam, Simulation, Nursing, Physics, Planning Tasks, Office Tasks, Physics Weekly Chart Checks |
| `ProcedureCode` | string | CPT procedure code |
| `ActivityDateTime` | datetime (M/D/YYYY H:MM:SS AM/PM) | Activity timestamp |
| `ProcedureCodeDescription` | string | CPT description |
| `SourceActivitySer` | int | Source activity serial number (ARIA internal key) |
| `CodeType` | string | Global, Technical, or Professional |
| `Quantity` | int | Number of units |
| `Modifiers` | string | CPT modifiers (26, TC, or empty) |
| `Credited` | string | Whether credited (Yes/No) |
| `Waived` | string | Whether waived (Yes/No) |
| `SupervisingPhysician` | string | Supervising physician |
| `AttendingPhysician` | string | Attending physician |
| `Completed` | string | Whether completed (Yes/No) |
| `ReferringPhysicianDimDoctorID` | int | FK to Lookup - Referring |
| `MarkedCompleted` | string | Whether marked completed (Yes/No) |
| `ReferringPhysician` | string | Referring physician name |
| `Reviewed` | string | Whether reviewed (Yes/No) |
| `ReferringPhysicianSpecialty` | string | Referring physician specialty |
| `Exported` | string | Whether exported to billing system (Yes/No) |
| `DiagnosisCodes` | string | ICD codes |
| `DiagnosisDescriptions` | string | Diagnosis descriptions |

**Business rules:**
- `CodeType` determines the billing split: Professional (physician), Technical (facility), Global (both)
- `Modifiers`: 26 = professional component, TC = technical component
- `ActivityCategory` enables filtering by department function (Treatment, Exam, Simulation, etc.)
- `Completed`, `MarkedCompleted`, `Reviewed`, `Exported` track the billing workflow state
- Join to `Lookup - Patients` via `PatientId` for payor mix analysis
- Join to `Lookup - Referring` via `ReferringPhysicianDimDoctorID` for referral billing

---

### Clinic Visits

- **File:** `Incremental/ClinicVisits/Clinic Visits.csv`
- **Size:** ~13 MB
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
| `ActivityName` | string | Visit type (Consult, Follow-Up, Re-eval, Virtual Consult/Follow Up) |
| `ActivityStatus` | string | Status (Manually Completed, Cancelled, Open) |
| `AppointmentNotes` | string | Clinical notes |
| `SupervisingPhysician` | string | Supervising physician |
| `InPatientFlag` | string | Whether patient is inpatient (Yes/No) |
| `AppointmentPhysician` | string | Physician on the appointment |
| `AttendingPhysician` | string | Attending physician |
| `ReferringPhysicianDimDoctorID` | int | FK to Lookup - Referring |
| `ReferringPhysicianSpecialty` | string | Referring physician specialty |
| `ReferringPhysician` | string | Referring physician name |
| `DiagnosisCodes` | string | ICD codes |
| `DiagnosisDescriptions` | string | Diagnosis descriptions |
| `ProcedureCodes` | string | CPT codes (can be comma-separated) |
| `ProcedureDescriptions` | string | CPT descriptions |
| `SimulationStatus` | string | Simulation linkage status: None, Scheduled, Completed, Cancelled |
| `SimTransactionID` | int | Transaction ID of the linked simulation record |
| `SimulationDateTime` | datetime | Date of linked simulation |
| `DaysToSimulation` | int | Days from visit to simulation |
| `SimActivityName` | string | Linked simulation activity type (Initial Simulation, HOLD SIM TIME, etc.) |
| `SimVisitRank` | int | Ranking of simulation visit linkage |
| `ModalityType` | string | Treatment modality: EBRT, Brachytherapy, Cancelled, No Imaging |

**Business rules:**
- `ActivityName` determines visit type: Consult, Follow-Up, Re-eval, Virtual Consult/Follow Up
- `SimulationStatus` replaces the old `HasSimulationWithin180Days` boolean — provides richer status tracking
- `ModalityType` indicates the treatment pathway (EBRT vs Brachytherapy vs no treatment)
- Join to `Lookup - Referring` via `ReferringPhysicianDimDoctorID` for referral analysis
- Join to `Lookup - Patients` via `PatientId` for payor mix per consult

---

### Courses

- **File:** `Incremental/Courses/Courses.csv`
- **Size:** ~5.3 MB
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
| `FxOverride` | int | Fraction override count (0 if none) |
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
| `InPatientFlag` | string | Whether patient is inpatient |
| `LastDayActivityFlag` | string | Flag for last-day-of-treatment activity |
| `DCActivityFlag` | string | Flag for discontinuation activity |

**Business rules:**
- `CourseId` follows pattern: `C{N}_{Site}` (e.g., C1_H&N = first course, head & neck)
- `Departments` and `Machines` can be multi-valued for patients who transfer sites
- `TreatmentTechniques`: 3D, IMRT, VMAT
- `LastDayActivityFlag` and `DCActivityFlag` track end-of-course events
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

### Procedures

- **File:** `Incremental/Procedures/Procedures.csv`
- **Size:** ~617 KB (~2,200 rows)
- **Refresh:** Incremental append
- **Used by:** TBD (new dataset)

| Column | Type | Description |
|--------|------|-------------|
| `UniqueRowID` | int | Deduplication key |
| `ActivityName` | string | Procedure name (e.g., "SBRT Prostate (SpaceOAR/Fiducial) implant @ SPH", "Lupron", "Gold Seed Placement") |
| `PatientId` | string | Patient identifier |
| `PatientFullName` | string | Patient name (LAST, FIRST) |
| `DepartmentName` | string | Department name |
| `AppointmentCreatedDate` | date (MM/DD/YYYY) | When appointment was created |
| `ScheduledDateTime` | datetime (M/D/YYYY H:MM:SS AM/PM) | Scheduled procedure time |
| `DaysFromCreatedToAppt` | int | Lead time in days |
| `DurationMinutes` | int | Procedure duration (typically 30 or 60 minutes) |
| `ProcedureCategory` | string | Category: Rectal Spacer, Lupron, Gold Seeds, Prostate LDR, Volume Study |
| `ActivityStatus` | string | Status (Manually Completed, Open, Cancelled) |
| `AppointmentNotes` | string | Clinical notes |
| `InPatientFlag` | string | Whether patient is inpatient (Yes/No) |
| `AppointmentPhysician` | string | Physician performing procedure |
| `SupervisingPhysician` | string | Supervising physician |
| `AttendingPhysician` | string | Attending physician |
| `ReferringPhysicianDimDoctorID` | int | FK to Lookup - Referring |
| `ReferringPhysician` | string | Referring physician name |
| `ReferringPhysicianSpecialty` | string | Referring physician specialty |
| `ProcedureCodes` | string | CPT codes (can be comma-separated) |
| `ProcedureDescriptions` | string | CPT descriptions |
| `DiagnosisCodes` | string | ICD codes |
| `DiagnosisDescriptions` | string | Diagnosis descriptions |

**Business rules:**
- Tracks ancillary procedures performed alongside radiation treatment courses
- `ProcedureCategory` groups procedures: Rectal Spacer (SpaceOAR), Lupron injections, Gold Seed fiducial placement, Prostate LDR brachytherapy, Volume Studies
- Small dataset — these are supplementary procedures, not daily treatments
- Join to `Lookup - Referring` via `ReferringPhysicianDimDoctorID`

---

### Simulations

- **File:** `Incremental/Simulations/Simulations.csv`
- **Size:** ~11 MB
- **Used by:** Simulations page

| Column | Type | Description |
|--------|------|-------------|
| `UniqueRowID` | int | Deduplication key |
| `SimulationResource` | string | Simulation resource (CT_Sim) |
| `PatientId` | string | Patient identifier |
| `PatientFullName` | string | Patient name (LAST, FIRST) |
| `AppointmentCreatedDate` | date (MM/DD/YYYY) | When appointment was created |
| `ScheduledDateTime` | datetime (M/D/YYYY H:MM:SS AM/PM) | Scheduled sim time |
| `DaysFromCreatedToAppt` | int | Lead time in days |
| `DurationMinutes` | int | Duration (30, 60, or 90 minutes) |
| `ActivityName` | string | Sim type (Initial Simulation, HOLD SIM TIME, Treatment Device Fabrication, Re-Simulation, Initial Aberdeen Simulation, Initial Centralia-in Lacey, etc.) |
| `ActivityStatus` | string | Status (Manually Completed, Open, Cancelled) |
| `ActivityNote` | string | Free text clinical notes about the simulation |
| `InPatientFlag` | string | Whether patient is inpatient (Yes/No) |
| `PriorClinicExamActivityName` | string | Prior clinic exam type (Consult, Re-eval) |
| `PriorClinicExamAppointmentDate` | date | Prior clinic exam date |
| `DaysFromClinicExamToSimulation` | int | Days from consult to sim |
| `ConsultPhysician` | string | Consult physician |
| `TreatmentStatus` | string | Downstream treatment status: None, Scheduled, Completed, Cancelled |
| `FirstTreatmentDate` | datetime | First treatment date |
| `DaysFromSimToTreatment` | int | Days from sim to first treatment |
| `TreatmentModality` | string | Treatment modality: EBRT, Brachytherapy, or empty |
| `ScheduledTreatmentDate` | datetime | Scheduled first treatment date (may be future) |
| `DaysToScheduledTreatment` | int | Days from sim to scheduled treatment |
| `DaysFromClinicExamToTreatment` | int | Days from consult to first treatment |
| `SupervisingPhysician` | string | Supervising physician |
| `AttendingPhysician` | string | Attending physician |
| `ReferringPhysicianDimDoctorID` | int | FK to Lookup - Referring |
| `ReferringPhysician` | string | Referring physician name |
| `ReferringPhysicianSpecialty` | string | Referring specialty |
| `ProcedureCodes` | string | CPT codes |
| `ProcedureDescriptions` | string | CPT descriptions |
| `DiagnosisCodes` | string | ICD codes |
| `DiagnosisDescriptions` | string | Diagnosis descriptions |
| `Department` | string | Department name (no `*` prefix) |

**Business rules:**
- `ActivityName` indicates simulation type and cross-site patterns
- "Initial Centralia-in Lacey" = Centralia patient simulated at Lacey
- Key timing metrics: exam→sim, sim→treatment, exam→treatment
- `TreatmentStatus` tracks whether the simulation led to actual treatment (None, Scheduled, Completed, Cancelled)
- `TreatmentModality` indicates EBRT vs Brachytherapy pathway
- `ScheduledTreatmentDate` + `DaysToScheduledTreatment` enable forward-looking pipeline analysis
- `Department` is now included directly in the source (previously had to merge via `_patient_department_map()`)

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
- **Size:** ~166 MB (largest file)
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
| `InPatientFlag` | string | Whether patient is inpatient (Yes/No) |
| `TotalFractions` | int | Total prescribed fractions |
| `FractionNumber` | int | Current fraction number |
| `FxOverride` | int | Fraction override count (0 if none) |
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
- **Size:** ~20 MB
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
| `InPatientFlag` | string | Whether patient is inpatient (Yes/No) |
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
- **Size:** ~36 MB
- **Used by:** Workflow page

| Column | Type | Description |
|--------|------|-------------|
| `UniqueRowID` | int | Deduplication key |
| `PatientId` | string | Patient identifier |
| `PatientName` | string | Patient name (LAST, FIRST) |
| `StageName` | string | Workflow stage: Exam, Simulation, Draw, ContourReview, Isodose, ReviewPlan, Treatment |
| `StageTypeOrder` | int | Stage type ordering (1=Exam, 2=Simulation, 3=Draw, 4=ContourReview, 5=Isodose, 6=ReviewPlan, 7=Treatment) |
| `StageActivityName` | string | Activity name within the stage (e.g., Consult, Follow-Up, Initial Simulation, Draw Volumes / Add Rx) |
| `StageDateTime` | datetime (M/D/YYYY H:MM:SS AM/PM) | When the stage occurred/is scheduled |
| `StageEndDateTime` | datetime (M/D/YYYY H:MM:SS AM/PM) | Stage end time (if applicable) |
| `StageDueDateTime` | datetime (M/D/YYYY H:MM:SS AM/PM) | SLA deadline for this stage |
| `StageCreationDateTime` | datetime (M/D/YYYY H:MM:SS AM/PM) | When this stage record was created |
| `CompletedBy` | string | Person who completed this stage |
| `StageStatus` | string | Status: Manually Completed, Completed, Open, Scheduled, In Progress, Cancelled, Cancelled - Patient No-Show, Deleted |
| `BaselineDateTime` | datetime | Baseline reference datetime for SLA calculations |
| `AttributedSimOccurrence` | int | Which simulation occurrence this stage is attributed to |
| `DimCourseID` | int | Course dimension ID |
| `ExamCreatedDate` | date (MM/DD/YYYY) | When the originating exam was created |
| `ExamDurationMinutes` | int | Duration of the originating exam |
| `ExamActivityStatus` | string | Status of the originating exam |
| `ExamNotes` | string | Clinical notes from the originating exam |
| `AppointmentPhysician` | string | Appointment physician |
| `TreatingPhysician` | string | Treating physician |
| `ReferringPhysician` | string | Referring physician |
| `ReferringPhysicianSpecialty` | string | Referring specialty |
| `ReferringPhysicianRecordID` | int | FK to Lookup - Referring |
| `ProcedureCodes` | string | CPT codes |
| `ProcedureDescriptions` | string | CPT descriptions |
| `DiagnosisCodes` | string | ICD codes |
| `DiagnosisDescriptions` | string | Diagnosis descriptions |
| `Department` | string | Department name (no `*` prefix) |
| `ExamDateTime` | datetime (M/D/YYYY H:MM:SS AM/PM) | Originating exam appointment datetime |
| `ModalityType` | string | Treatment modality: EBRT, Brachytherapy, or Undetermined |
| `StageOccurrence` | int | Occurrence number for repeated stages |
| `StageOrder` | int | Ordering within the patient's workflow sequence |

**Business rules:**
- **Restructured format:** Each row represents one stage in the patient workflow (previously each row contained all stages as separate column groups)
- Tracks the complete patient journey: Exam → Simulation → Draw → ContourReview → Isodose → ReviewPlan → Treatment
- `StageTypeOrder` provides canonical stage ordering (1-7)
- `StageOccurrence` handles patients with multiple simulations/courses — groups related stages
- `StageOrder` provides sequence ordering within a patient's full workflow
- To reconstruct the old per-patient timeline view, pivot on `PatientId` + `StageOccurrence` with `StageName` as columns
- `ExamCreatedDate`, `ExamDurationMinutes`, `ExamActivityStatus`, `ExamNotes`, `ExamDateTime` carry forward the originating exam context to all downstream stages
- `Department` is now included directly (previously had to merge via `_patient_department_map()`)
- `ModalityType` classifies the treatment pathway (EBRT vs Brachytherapy)

---

## Lookup / Reference Tables

### Lookup - Diagnosis

- **File:** `Lookup/Lookup - Diagnosis.csv`
- **Size:** ~205 KB
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
- **Size:** ~917 KB
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
  ├── Procedures (PatientId)
  ├── Treatment - Detail (PatientMRN)  ← different column name
  └── Machine Errors (PatientId)

Lookup - Referring (DimDoctorID)
  ├── Clinic Visits (ReferringPhysicianDimDoctorID)
  ├── Billing (ReferringPhysicianDimDoctorID)
  ├── Simulations (ReferringPhysicianDimDoctorID)
  ├── Procedures (ReferringPhysicianDimDoctorID)
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
- `Simulation` / `CT_Sim` / `CT_CEN` (CT sim rooms)
- `6EX` (appears inactive — no appointments)
- `Lacey - 21EX`, `Lacey - TrueBeamNorth` (machine-level breakdowns in Treatment.csv)

---

## Common New Columns Across Files

Several columns were added across multiple datasets in recent CSV format updates:

| Column | Found in | Description |
|--------|----------|-------------|
| `FxOverride` | CPT Audit, OTV Audit, Courses, Treatment Detail | Fraction override count — indicates manual fraction adjustments |
| `InPatientFlag` | Clinic Visits, Courses, Simulations, Procedures, Treatment Detail, Weekly Visits | Whether patient is inpatient (Yes/No) |
| `Department` | Simulations, Workflow | Department added directly to source (previously required merge via `_patient_department_map()`) |
| `ModalityType` | Clinic Visits, Workflow | Treatment modality classification (EBRT, Brachytherapy) |
