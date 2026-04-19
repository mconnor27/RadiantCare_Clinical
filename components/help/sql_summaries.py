"""Detailed summaries of the 18 production SQL scripts that feed the dashboard.

Each entry is keyed by script filename (without .sql extension) and contains:
  purpose:       What the report is for, in human terms.
  unique_logic:  List of bullet points describing non-obvious logic.
  output_cols:   String listing output columns (or a description of them).
  date_range:    Default date range for the report.
  total:         Total file lines (SQL + comments + blank).
  sql:           SQL code lines (excludes comments and blanks).
"""

SQL_SCRIPTS = {
    "Availability": {
        "total": 162, "sql": 90,
        "purpose": (
            "Forward-looking capacity report that surfaces unbooked HOLD slots, "
            "scheduleable blocks, and dedicated exam/simulation time on the schedule "
            "so front-desk staff and operational managers can see, at a glance, where "
            "the department has room to add patients over the coming two months. "
            "The report distinguishes between slots that are genuinely open and HOLD "
            "slots that already have a real patient booked against them (the HOLD was "
            "not released) — a common failure mode in the schedule that otherwise looks "
            "like free capacity."
        ),
        "unique_logic": [
            "Filters to 5 specific activity names: HOLD SIM TIME, LUNCH- SIM DOWN, "
            "SCHEDULEABLE, HOLD CONSULT, HOLD RE EVAL/2 FOLLOW UPS in Exam or Simulation categories.",
            "SlotTaken flag: detects HOLD slots where a real patient is already booked "
            "at the same resource/time/duration (ignores cancelled/deleted overlaps). "
            "Surfaces \"phantom availability\".",
            "Excludes slots held for real patients via a NOT(…) predicate on PatientId plus name validation.",
            "Assigned-resource logic differs by category: physician for Exam rows (who's free for a consult), "
            "machine for Simulation rows (which sim scanner is idle).",
        ],
        "output_cols": (
            "UniqueRowID, ActivityName, Category, DepartmentName, AppointmentDateTime, "
            "ScheduledEndTime, DurationMinutes, AppointmentNotes, AssignedResource, SlotTaken."
        ),
        "date_range": "Hardcoded GETDATE() → +2 months (always \"what's open right now going forward\").",
    },

    "Billing": {
        "total": 400, "sql": 201,
        "purpose": (
            "Comprehensive CPT billing report that lists every charge that has reached "
            "at least Completed status and pairs it with the full billing-lifecycle "
            "picture (completed → marked completed → reviewed → exported), the "
            "supervising/attending/referring physicians, linked diagnoses, payor, and "
            "any credit/waive adjustments. This is the primary revenue-cycle export "
            "used to reconcile charges against claims, validate coding, and audit the "
            "review/export workflow."
        ),
        "unique_logic": [
            "#FilteredBilling materialized temp table prevents re-scans of FactActivityBilling "
            "(one of the largest fact tables).",
            "#BillingDiagnosis normalizes ctrDiagnosisSer into sorted/deduplicated diagnosis keys — "
            "eliminates duplicate output rows when the same charge has multiple billing records whose "
            "diagnoses are stored in different orders (e.g., \"A01,B02\" vs \"B02,A01\").",
            "AggregatedCharges rolls up identical rows using COUNT(DISTINCT ctrActInstProcCodeSer) "
            "as Quantity — one CPT line per appointment even if ARIA recorded it as multiple billing rows.",
            "Four independent lifecycle status columns (Completed, MarkedCompleted, Reviewed, Exported) "
            "so the front end can distinguish between \"done\" and \"fully exported for payment\".",
            "Management-code exception: CPT codes 77427% and 77431% (weekly treatment management) are "
            "exempted from the completed-status requirement because they follow a separate weekly workflow "
            "and frequently appear before the underlying treatment charges are finalized.",
            "PayorName uses a 2-tier fallback: charge-level payor > patient primary payor "
            "(covers charges where the payor wasn't attached at the line level).",
            "Credited and Waived indicator columns surface charge adjustments without filtering them out.",
        ],
        "output_cols": (
            "UniqueRowID, PatientId, PatientFullName, DateOfService, ActivityName, ActivityCategory, "
            "ActivityDateTime, SourceActivitySer, DepartmentName, ProcedureCode, ProcedureCodeDescription, "
            "CodeType, Quantity, Modifiers, Completed, MarkedCompleted, Reviewed, Exported, Credited, "
            "Waived, SupervisingPhysician, AttendingPhysician, ReferringPhysician (ID/name/specialty), "
            "DiagnosisCodes, DiagnosisDescriptions, PayorName."
        ),
        "date_range": "2 months back → today.",
    },

    "Clinic_Visits": {
        "total": 840, "sql": 529,
        "purpose": (
            "Consult, follow-up, and re-evaluation exam report with a 180-day forward "
            "simulation lookup so each clinic visit is paired with the downstream CT "
            "simulation (if any), along with how long the patient waited between the "
            "consult and the sim. Designed to answer operational questions like \"how "
            "many new consults did we see, and how many converted to a simulated "
            "treatment plan?\" — and to do so without dropping any workflow where the "
            "consult and the sim fall in different halves of the reporting window."
        ),
        "unique_logic": [
            "#FilteredActivities materialized temp table uses overlap logic so consults whose simulation "
            "falls in the reporting window are still captured (pulls consults from 180 days before "
            "@StartDate). Standard BETWEEN @StartDate AND @EndDate filtering would drop consults on "
            "the edge whose sim happened inside the window.",
            "Three separate OUTER APPLY blocks cover simulation status — Completed, Scheduled, Cancelled — "
            "each using a 3-path detection (real sims with standard activity names, rare sims identified "
            "by CPT codes billed against non-sim activities, and Volume Studies as pseudo-sims for brachy).",
            "Dedicated Pluvicto-injection detection (Pluvicto follows a non-standard workflow with no sim).",
            "ModalityType column (EBRT / Brachytherapy / Pluvicto / Cancelled / No Imaging) enforces "
            "chronological ordering so modality assignments respect event sequence — a patient whose "
            "brachy implant preceded a later EBRT course is not mis-classified.",
            "SimVisitRank deduplicates consults that tie to the same simulation (when a patient has "
            "multiple pre-sim exams, only the closest one is ranked 1).",
            "4-tier billing cascade (reviewed+exported > reviewed > marked complete > completed) for "
            "physician/procedure data.",
            "2-tier diagnosis fallback (billing-linked > activity-level via FactActivityDiagnosis).",
        ],
        "output_cols": (
            "UniqueRowID, PatientId, PatientFullName, DepartmentName, AppointmentCreatedDate, "
            "ScheduledDateTime, DaysFromCreatedToAppt, DurationMinutes, ActivityName, ActivityStatus, "
            "AppointmentNotes, InPatientFlag, AppointmentPhysician, SupervisingPhysician, AttendingPhysician, "
            "ReferringPhysician (ID/name/specialty), ProcedureCodes, ProcedureDescriptions, DiagnosisCodes, "
            "DiagnosisDescriptions, SimulationStatus, SimTransactionID, SimActivityName, SimulationDateTime, "
            "DaysToSimulation, SimVisitRank, ModalityType."
        ),
        "date_range": "180 days back, 30 days forward.",
    },

    "Courses": {
        "total": 1844, "sql": 1110,
        "purpose": (
            "Course-level census of active clinical workload. A course in radiation "
            "oncology is the full arc of a patient's treatment for one condition — it "
            "may span weeks and include multiple plans (initial + boost, APBI + tumor "
            "bed, etc.). This report answers the question \"who was actively under care "
            "during this window?\" including patients who had gap weeks with zero "
            "treatments. Each row shows the technique mix across plans in the course, "
            "treating/consulting/referring physicians, prescribed fractions and "
            "frequency (Daily, BID, Weekly), actual delivered fractions and sessions, "
            "diagnosis, department/machine used, and flags for the last day of the "
            "course and for discharge activities."
        ),
        "unique_logic": [
            "\"Active Course\" inclusion rule: CourseStart ≤ @EndDate AND LastActivity ≥ @StartDate. "
            "Includes courses mid-flight even if nothing happened during the reporting window itself.",
            "Entity-first filtering architecture (filter courses first, then pull treatments, then aggregate, "
            "then apply date filter) minimizes redundant scans of FactTreatmentHistory.",
            "Hybrid session counting: combines FractionNumber cross-check with a wasted-session correction "
            "so continuations and aborted sessions don't double-count. Single-plan courses use "
            "COUNT(DISTINCT FractionNumber); multi-plan courses use cross-check sessions minus wasted sessions.",
            "10-tier treatment technique classification (most-specific → most-general): Prescription technique "
            "→ Electron → Plan-name keywords → Course+Fractionation rule → Field mix → SRS arc technique → "
            "RapidArc → MLC type → Billing fallback → Field count → Unknown.",
            "2-tier physician determination: Most Frequent Billing Physician (Treatment + PlanCHG scoped "
            "to FirstTreatmentDate → LastTreatmentDate) > Prior Exam Physician.",
            "2-tier diagnosis (treatment billing > PlanCHG/Exam fallback with 180-day lookback before first treatment).",
            "InPatientFlag uses a 4-tier billing cascade plus admission fallback.",
            "LastDayActivityFlag and DCActivityFlag surface end-of-course events.",
            "RxFrequency comma-delimited unique prescribed frequencies from DimPrescriptionProperty "
            "(PropertyType=7), with PRIMARY phase listed first (e.g., 'Daily', 'Daily, BID', 'Weekly').",
            "Excludes %DNU% plan names and z%, T1, SRS TEST, COUCH TEST, and PrimaryRefPointPlanned ≤ 2 "
            "(trivial-dose test deliveries).",
        ],
        "output_cols": (
            "PatientId, PatientName, CourseId, CourseStartDateTime, ClinicalStatus, PlanCount, "
            "technique-by-plan breakdowns, TotalFractionsDelivered, SessionBasedFractionCount, "
            "FirstTreatmentDate, LastTreatmentDate, Department, Machine, TreatingPhysician, "
            "ConsultPhysician, ReferringPhysician, DiagnosisCodes, DiagnosisDescriptions, "
            "InPatientFlag, LastDayActivityFlag, DCActivityFlag, RxFrequency, CourseSessionsPlanned/Delivered."
        ),
        "date_range": "2 months back → today.",
    },

    "DailyVolume_Future": {
        "total": 1171, "sql": 657,
        "purpose": (
            "Forward-looking daily volume projection. For each future date the report "
            "gives one row per machine (plus site rollups) with the earliest/latest "
            "scheduled appointment, total appointment count, and projected "
            "NewStartCount — patients whose first-fraction treatment is scheduled on "
            "that day. The operations-planning counterpart to DailyVolume_Past.sql; "
            "used for capacity forecasting, staffing, and anticipating new-start-heavy "
            "days where workload spikes."
        ),
        "unique_logic": [
            "Structurally identical to DailyVolume_Past.sql (3 temp tables: #TreatmentData, "
            "#ScheduledTreatmentData, #SimulationData).",
            "Includes non-cancelled appointments (not restricted to completed) since the data is forward-looking.",
            "Unique to this script: NewStartCount — detects upcoming new treatment starts by matching on a "
            "curated list of new-start activity names AND verifying via NOT EXISTS on FactTreatmentHistory "
            "that the patient's most recent course has zero delivered treatments. Avoids counting re-starts, "
            "boost plans, or continuations as new starts.",
        ],
        "output_cols": (
            "Site, Category (Treatment/Simulation/Total), Resource (machine or NULL for rollups), Date, "
            "FirstScheduledStart, LastScheduledEnd, AppointmentCount, FirstActualStart, LastActualEnd, "
            "ScheduledActiveMinutes, ActualActiveMinutes, BeamOnMinutes, ApptActualMinutes, NewStartCount."
        ),
        "date_range": "Today → +1 month.",
    },

    "DailyVolume_Past": {
        "total": 1109, "sql": 631,
        "purpose": (
            "Historical daily summary of treatment and simulation volume across 3 "
            "sites (Lacey, Centralia, Aberdeen). For each day the report produces 10 "
            "rows — individual Lacey machines (21EX, TrueBeamNorth, 6EX), "
            "single-machine sites (Centralia, Aberdeen), Simulation, a Lacey Treatment "
            "rollup, and site-level Totals. Each row reports four distinct time "
            "metrics that answer different operational questions."
        ),
        "unique_logic": [
            "Four time metrics that each answer a different question: "
            "ScheduledActiveMinutes (how much of the day did we plan to use this machine), "
            "ActualActiveMinutes (how long was the machine actually in use with patients, including "
            "imaging/setup time), "
            "BeamOnMinutes (how long was the machine actually delivering radiation — excludes setup, "
            "imaging, between-beam pauses), "
            "ApptActualMinutes (how long were patients documented as being at the machine — full "
            "appointment duration including room-in/room-out).",
            "The gap between these metrics tells the operational story: ScheduledActive vs ApptActual "
            "reveals scheduling accuracy; ApptActual vs ActualActive reveals room-turnover time; "
            "ActualActive vs BeamOn reveals imaging/setup overhead.",
            "Three temp tables scan their source exactly once.",
            "CBCT imaging pulled from FactPatientImage via a temporal EXISTS filter: images must fall "
            "within 30 minutes before the patient's first beam through their last beam end on the same "
            "machine+date. Excludes QA imaging, stray off-hours images, and imaging-only visits.",
            "3-trigger session detection for ActualActiveMinutes: (1) first field for a patient on a "
            "machine/date, (2) >60-min gap since that patient's previous field, (3) another patient was "
            "treated between this patient's consecutive fields (interleaving trigger — prevents Patient A's "
            "8:00 and 8:55 fields from merging into one 55-min session when Patient B was treated at 8:25).",
            "Reference-point deduplication: a single VMAT/IMRT beam produces multiple FactTreatmentHistory "
            "rows (one per reference point). SELECT DISTINCT collapses these before interval merging to "
            "prevent 10–20× inflation of BeamOnMinutes.",
            "Known data transition at Oct 6, 2025: before this date FactPatientImage only stored "
            "DRRs/portal images; after it captures CBCT volumetric reconstructions for nearly every patient. "
            "ActualActiveMinutes jumps 2–4× across the transition. Headers recommend using BeamOnMinutes "
            "for long-term trend analysis and ActualActiveMinutes only for post-Oct-6 operational insights.",
            "IsScheduled/AppointmentInstanceFlag exclude to-do tasks; AppointmentResourceStatus = 'Active' "
            "excludes moved/deleted appointments.",
        ],
        "output_cols": (
            "Site, Category, Resource (machine or NULL for rollups), Date, FirstScheduledStart, "
            "LastScheduledEnd, AppointmentCount, FirstActualStart, LastActualEnd, "
            "ScheduledActiveMinutes, ActualActiveMinutes, BeamOnMinutes, ApptActualMinutes."
        ),
        "date_range": "All past data through yesterday.",
    },

    "Downtime_FieldTicks": {
        "total": 403, "sql": 233,
        "purpose": (
            "Individual field-delivery ticks and imaging events for machine-timeline "
            "visualization — the data that sits under a Gantt-style view of a day's "
            "activity on a linac. Each row is either a point (a CBCT imaging event) or "
            "an interval (a treatment beam or a port film with start/end times). "
            "Companion to Downtime_Gaps.sql (downtime bands overlaying the same "
            "timeline) and Machine_Error.sql (error markers). Full-history exports run "
            "in ~1–2 min and produce ~750K–1M rows; a single-day drill-through is "
            "~150–300 rows."
        ),
        "unique_logic": [
            "Single scan of FactTreatmentHistory covers both treatment fields (IsImage=0) and port films "
            "(IsImage=1) via a CASE on IsImage — produces both record types from one pass over the "
            "largest fact table.",
            "ROW_NUMBER() PARTITION BY (DimFieldID, TreatmentStartTime) deduplicates reference-point rows "
            "on 2 columns instead of hashing all 27 — significant speedup on large ranges.",
            "Three record types from one query: Treatment (beam delivery interval), PortFilm (MV/kV "
            "verification-image interval), Image (CBCT/kV volumetric imaging point event from FactPatientImage).",
            "CBCT imaging pulled from FactPatientImage with a join to #TxBounds (pre-aggregated per-patient "
            "session boundaries).",
            "Sargable date filters (TreatmentStartTime >= X AND < Y, not CAST AS DATE = Z) and OPTION(RECOMPILE) "
            "address plan-caching issues on variable date ranges.",
        ],
        "output_cols": (
            "RecordType, Site, Machine, ActivityDate, StartTime, EndTime, StartDateTime, EndDateTime, "
            "DurationSeconds, PatientId, PatientName, CourseId, CourseStartDate, PlannedFractions, "
            "DeliveredFractions, PlanName, TreatmentTechnique, FieldId, FractionNumber, PlannedMU, "
            "DeliveredMU, FieldStatus, TerminationStatus, TreatmentDeliveryType, RadiationType, EnergyMV, "
            "FieldCategory, GatingFlag, ImageType."
        ),
        "date_range": "3 months back → yesterday.",
    },

    "Downtime_Gaps": {
        "total": 2183, "sql": 1668,
        "purpose": (
            "Minute-level machine-downtime detection inferred from inter-treatment "
            "gaps. Where DailyVolume_Past.sql answers \"how much did the machine run?\" "
            "and Machine_Error.sql answers \"which fields errored out?\", this script "
            "answers the harder question: \"when was the machine broken, how long was "
            "it down, and which patients were affected?\" It synthesizes signals across "
            "beam deliveries, imaging, scheduled appointments, cancelled appointments, "
            "machine-down notes, MACHINE-termination errors, and cross-machine activity "
            "to produce a per-gap downtime assessment with patient impact "
            "classification and a confidence score. Output is at per-patient grain — "
            "one row per affected patient per gap — so downstream aggregation can roll "
            "up to gap, day, month, year, patient, course, or machine level."
        ),
        "unique_logic": [
            "Four gap classifications: "
            "Downtime (mid-day gaps between machine busy blocks exceeding @MinGapMinutes, default 10 min); "
            "FullDay (zero-treatment days on a machine where other machines at the same site were active — "
            "rules out holidays/closures); "
            "EndOfDayDown (machine failed during or after the last patient of the day — detected via "
            "machine error on last field, cancelled appointments after last treatment, or other machines "
            "still treating after this one stopped); "
            "StartOfDayDown (machine started significantly later than expected — uses a hybrid baseline of "
            "30-day rolling median first-treatment time, earliest peer-machine start at the same site, and "
            "the earliest cancelled appointment before first beam).",
            "Patient outcome attribution (three-way): Rerouted (treated on a different machine the same day), "
            "Delayed (treated on the same machine after the gap resolved), Missed (not treated that day).",
            "Confidence scoring: High (downtime notes > 0 OR machine errors > 0, AND other machines active, "
            "OR ≥ 3 cancellations with other machines active); Medium (cancellations with other machines "
            "active, OR errors alone, OR notes alone); Low (gap with no corroborating signals, OR full-day "
            "down with no other-machine activity).",
            "Start-of-day hybrid baseline: four independent trigger signals (no peer machines required) — "
            "cancelled appointments before first treatment, machine errors in first block, started > 60 min "
            "after rolling median, started > 60 min after earliest peer. Makes the logic work for "
            "single-machine sites (Centralia, Aberdeen) as well as Lacey.",
            "Imaging included in gap detection: #FieldData includes both beam deliveries and CBCT/kV imaging "
            "via a temporal join to #TxBoundsGap, so machine busy blocks start at imaging time, not "
            "first beam-on. Produces more accurate gap durations.",
            "No lunch classification: all gaps are treated equally. GapStartTime is output so the front end "
            "can apply its own time-of-day logic if desired.",
            "All appointments scanned (not just cancelled) — enables appointment-success-rate calculation "
            "during gaps and uses completed-during-gap appointments as counter-evidence against downtime.",
            "Raw signal columns exposed for frontend confidence override (CancelledInGap, DowntimeNotesInGap, "
            "MachineErrorsNearGap, OtherMachinesActive, CompletedInGap, TotalApptsInGap).",
            "RowKey = SHA2_256 hash of natural business keys (RowType|Machine|Date|GapStart|PatientId) "
            "for frontend upsert/dedup on overlapping incremental loads.",
            "~18 temp tables stage raw signals, full-day down events, end-of-day events, start-of-day "
            "events, course boundaries, and patient attribution separately.",
        ],
        "output_cols": (
            "RowKey (SHA2_256), Machine, Site, Date, GapType, GapStartTime, GapEndTime, GapMinutes, "
            "PatientId, PatientName, PatientOutcome, CourseId, PlannedFractions, DeliveredFractions, "
            "ConfidenceLevel, CancelledInGap, DowntimeNotesInGap, MachineErrorsNearGap, "
            "OtherMachinesActive, CompletedInGap, TotalApptsInGap."
        ),
        "date_range": "3 months back → yesterday.",
    },

    "Machine_Error": {
        "total": 290, "sql": 115,
        "purpose": (
            "Surfaces every treatment field that ended in a machine error "
            "(TerminationStatus = 'MACHINE') for QA, troubleshooting, and safety "
            "analysis. Each row shows planned vs delivered MU (so the clinical team "
            "can see how far into the delivery the error occurred), which plan and "
            "field errored, and how long the machine was unavailable afterward via "
            "ElapsedTimeToNextTreatment. That value gives engineering a minute-level "
            "recovery-time indicator for every error event, and distinguishes between "
            "errors where the next patient was treated a few minutes later (transient) "
            "vs hours later (real hardware down). Field-technique classification helps "
            "identify whether certain techniques (Arc, DynamicMLC, Electron) are "
            "disproportionately represented in error events."
        ),
        "unique_logic": [
            "Filters FactTreatmentHistory for FieldStatus IN ('Treated','Pt. Treated'), IsImage=0, "
            "TerminationStatus='MACHINE'.",
            "OUTER APPLY finds the next normal treatment on the same machine, returning "
            "ElapsedTimeToNextTreatment in minutes via DATEDIFF(SECOND)/60.0 with ROUND(…,2) for "
            "two-decimal precision.",
            "5-tier field-technique classification: Electron (RadiationType = 'E'), Arc (GantryRtnDirection "
            "CW/CC or IMRTOrRapidArc = 'RapidArc'), StaticMLC (MLCPlanType = 'StdMLCPlan' or photon fallback), "
            "DynamicMLC (MLCPlanType = 'DynMLCPlan', non-arc), Other.",
            "Patient/course/plan quality filters are reapplied inside the next-normal OUTER APPLY so the "
            "\"recovery\" record also passes quality gates — prevents a QA/test field from masquerading as "
            "the next normal treatment and understating recovery time.",
        ],
        "output_cols": (
            "UniqueRowID, PatientId, PatientName, CourseId, PlanName, FieldId, FractionNumber, "
            "TreatmentStartTime, TreatmentEndTime, PlannedMU, DeliveredMU, Machine, FieldCategory, "
            "ElapsedTimeToNextTreatment."
        ),
        "date_range": "5 days back → today (short-window operational report).",
    },

    "Machine_Statistics": {
        "total": 406, "sql": 274,
        "purpose": (
            "Per-machine lifetime and per-year statistics — the asset-level report "
            "that answers \"what has each linac done over its operating life, and how "
            "has volume trended year over year?\" Output is a 4-section UNION ALL: All "
            "Data (lifetime, minimal filters), All Data by Year, Real Patients "
            "(lifetime, full quality filters), and Real Patients by Year. The "
            "difference between \"All Data\" and \"Real Patients\" sections highlights "
            "the QA/commissioning/training load on each machine vs actual patient "
            "throughput."
        ),
        "unique_logic": [
            "Temp tables with clustered indexes (#RawFields, #FilteredFields) instead of CTEs — "
            "FactTreatmentHistory is scanned exactly twice (once for raw, once for quality-filtered) "
            "instead of being re-evaluated per UNION ALL section.",
            "Reference-point deduplication: GROUP BY (Plan, Fraction, Field, Machine, Patient) with "
            "MAX(DoseDeliveredPerFraction) collapses the multiple control-point rows that VMAT/IMRT plans "
            "generate into one row per field delivery.",
            "Session counting: 240-min (4-hour) gap threshold, matching Treatment.sql. Within each "
            "(Patient, Machine, Date), fields are ordered by time and a gap > 240 min between consecutive "
            "starts counts as a new session boundary.",
            "Session counts pre-aggregated into #RawSessionAgg / #FilteredSessionAgg (and per-year "
            "equivalents) so the final SELECT uses simple JOINs instead of 4 correlated subqueries.",
            "OperatingLife = first treatment date on the machine; MostRecentTreatment = last treatment date. "
            "Together they define the asset's operational span.",
            "Date columns use CONVERT(VARCHAR(10), …, 101) to force MM/DD/YYYY display in UNION ALL context "
            "(CAST AS DATE still showed timestamps).",
        ],
        "output_cols": (
            "Section, Machine, DataYear, TotalFields, TotalDose_Gy, TotalFractions, AvgDosePerFx_Gy, "
            "TotalSessions, TotalPatients, OperatingLife, MostRecentTreatment."
        ),
        "date_range": "None — all-time query with 4-section UNION ALL.",
    },

    "Plans": {
        "total": 1450, "sql": 866,
        "purpose": (
            "Plan-level summary — one row per treatment plan — with the full \"plan "
            "life\" picture: prescribed vs planned vs delivered vs remaining fractions, "
            "prescribed frequency (Daily, BID, Weekly), sessions, first and last "
            "treatment dates, treatment duration, 10-tier technique classification, "
            "prescription site(s), department(s) and machine(s) used, diagnosis, and "
            "treating/consult/referring physician attribution. The granular companion "
            "to Courses.sql: a course rolls up plans, so the two must agree on "
            "technique, physician, and fraction counts."
        ),
        "unique_logic": [
            "Entity-first filtering: filter plans first → pull treatments → aggregate → apply date filter.",
            "FractionNumber-based fraction counting (not raw row counts) — ARIA's native per-plan fraction "
            "identifier is reliable within a single plan and avoids the 240-min session-gap approach's "
            "edge cases.",
            "10-tier technique classification split by materialization strategy: tiers 1–7 materialized "
            "into #PlanTier1to7 (small result set, heavy computation); tiers 8–12 computed in a "
            "TechniqueInfo CTE (cheaper, doesn't need materialization).",
            "2-tier physician determination — Most Frequent Billing Physician (Treatment + Weekly exams "
            "scoped to CourseFirstTreatmentDate → CourseLastTreatmentDate) > Prior Exam Physician (with "
            "3-tier fallback of Completed > Billing > Any status).",
            "Diagnosis: treatment-billing primary, PlanCHG (CPT 77261-77263, 77306-77307) fallback.",
            "RxFrequency from DimPrescriptionProperty (PropertyType=7), PRIMARY phase listed first, "
            "scoped to plan-specific prescriptions via LinkedPlans.",
            "BillingPhysicianCounts uses an explicit 21-item activity-name list (not LIKE '%treatment%') "
            "so \"New Start\", \"Complex Setup New Start\", and similar non-\"treatment\"-named billed "
            "activities contribute to physician attribution.",
            "11 temp tables total.",
        ],
        "output_cols": (
            "UniqueRowID, PatientId, PatientName, CourseId, CourseStartDateTime, ClinicalStatus, "
            "PlanSetupId, PlanCreationDate, PlanStatus, NoFractionsPlanned/Delivered/Remaining, "
            "FractionsPrescribed, RxFrequency, NoSessionPlanned, SessionBasedFractionCount, "
            "FirstTreatmentDate, LastTreatmentDate, TreatmentDurationDays, TreatmentTechnique, "
            "PrescriptionSite, Departments, Machines, DiagnosisCodes, DiagnosisDescriptions, "
            "TreatingPhysician, ConsultPhysician, ReferringPhysician (ID/name/specialty)."
        ),
        "date_range": "2 months back → today.",
    },

    "Procedures": {
        "total": 401, "sql": 256,
        "purpose": (
            "Specialty-procedure appointment tracker — Prostate LDR implants, Gold "
            "Seeds (fiducial marker placement), Rectal Spacer (SpaceOAR) insertion, "
            "Volume Study imaging, Lupron injections, Pluvicto injections. Thirteen "
            "distinct activity names are mapped to 6 ProcedureCategory values, and "
            "each appointment is paired with the supervising/attending/referring "
            "physicians, CPT codes, and diagnoses so procedure workloads can be "
            "tracked independently from EBRT volumes. Past appointments are shown "
            "only if completed; future appointments are shown regardless of status "
            "(so upcoming implants appear even when scheduled weeks out)."
        ),
        "unique_logic": [
            "Structure borrowed from Clinic_Visits.sql.",
            "Multi-resource deduplication prefers physician-assigned resources when a procedure has "
            "multiple resource assignments (a common pattern where both the MD and the OR/nursing resource "
            "are booked).",
            "4-tier billing cascade (reviewed+exported > reviewed > marked complete > completed).",
            "Diagnosis resolution via ctrDiagnosisSer parsing.",
            "Asymmetric status filter: past appointments must be Completed; future appointments are "
            "included regardless of status.",
            "InPatient flag uses OR logic (billing signal + admission fallback) — catches inpatient "
            "procedures whether or not they were billed as inpatient.",
        ],
        "output_cols": (
            "UniqueRowID, PatientId, PatientFullName, DepartmentName, AppointmentCreatedDate, "
            "ScheduledDateTime, DaysFromCreatedToAppt, DurationMinutes, ActivityName, ProcedureCategory, "
            "ActivityStatus, AppointmentNotes, InPatientFlag, AppointmentPhysician, SupervisingPhysician, "
            "AttendingPhysician, ReferringPhysician (ID/name/specialty), ProcedureCodes, "
            "ProcedureDescriptions, DiagnosisCodes, DiagnosisDescriptions."
        ),
        "date_range": "180 days back, 2 months forward.",
    },

    "Simulations": {
        "total": 1226, "sql": 741,
        "purpose": (
            "Comprehensive CT-simulation workflow tracking. Each row is a simulation "
            "appointment linked backward to the prior clinic exam (so you can see "
            "days-from-consult-to-sim) and forward to treatment initiation "
            "(days-from-sim-to-treatment, and which modality: EBRT first fraction, "
            "or a brachytherapy implant). Shows simulation machine used, scheduling "
            "metrics, physicians, procedure codes, diagnoses, and an explicit "
            "TreatmentStatus of Completed / Scheduled / Cancelled / None so ops can "
            "monitor the sim-to-treat conversion funnel."
        ),
        "unique_logic": [
            "#FilteredActivities uses overlap logic, pulling sims as far back as 90 days before @StartDate.",
            "#FirstTreatmentAfterSim materialized temp table captures the first EBRT FractionNumber=1 OR "
            "brachytherapy implant within 180 days, with intervening-simulation checks to prevent "
            "cross-attribution when a patient had two sims for different courses.",
            "Multi-modality detection via UNION ALL of two treatment paths: EBRT path "
            "(FactTreatmentHistory FractionNumber=1) and Brachy path (Completed implant appointments — "
            "Prostate Implant, Brachytherapy implant @ SPH, implant @ SPH, implant (SPH); the word "
            "\"Implant\" alone is excluded because it's used for pacemaker notes). "
            "TOP 1 ORDER BY FirstTreatmentDate ASC picks the earliest treatment regardless of modality.",
            "4-tier department attribution: treatment-machine department > simulation-resource department "
            "(DimResourceID 1 = Lacey CT_Sim, 17 = Centralia CT_CEN) > consult-exam department > "
            "patient default department.",
            "4-tier billing cascade for physician/procedure data.",
            "2-tier diagnosis fallback (billing-linked via ctrDiagnosisSer > activity-level via "
            "FactActivityDiagnosis with IsPrimary=1). Front end can distinguish source: if ProcedureCodes "
            "is populated, diagnoses came from billing; if NULL, diagnoses are patient-level fallback.",
            "SimulationResource joins DimResource → DimMachine via ctrResourceSer to show real machine "
            "names (CT_Sim, CT_CEN, 21EX, TrueBeamNorth) instead of numeric resource IDs or "
            "scheduling-room names from DimConstantResource.",
            "Machine filter excludes non-equipment scheduling resources (Communications Room, Lacey Nursing) "
            "that have no MachineFullName.",
            "Electron-CSU appointments exempted from the resource filter because they're performed on "
            "treatment machines (not CT simulators) and would otherwise be dropped.",
            "MostRecentExamBeforeSim has a 365-day lower bound on the backward scan — a consult > 1 year "
            "before sim is almost certainly a different treatment episode.",
            "@ModalityType parameter filters to EBRT, Brachytherapy, or All.",
        ],
        "output_cols": (
            "UniqueRowID, SimulationResource, PatientId, PatientFullName, AppointmentCreatedDate, "
            "ScheduledDateTime, DaysFromCreatedToAppt, DurationMinutes, ActivityName, ActivityStatus, "
            "ActivityNote, InPatientFlag, PriorClinicExamActivityName, PriorClinicExamAppointmentDate, "
            "DaysFromClinicExamToSimulation, ConsultPhysician, TreatmentStatus, FirstTreatmentDate, "
            "DaysFromSimToTreatment, TreatmentModality, ScheduledTreatmentDate, DaysToScheduledTreatment, "
            "DaysFromClinicExamToTreatment, SupervisingPhysician, AttendingPhysician, "
            "ReferringPhysician (ID/name/specialty), ProcedureCodes, ProcedureDescriptions, "
            "DiagnosisCodes, DiagnosisDescriptions, Department."
        ),
        "date_range": "120 days back, 30 days forward.",
    },

    "Tasks": {
        "total": 794, "sql": 413,
        "purpose": (
            "Physician and dosimetrist planning-task tracking — the four major "
            "treatment-planning steps: Draw Volumes (contouring), Contour Review "
            "(peer review, often assigned to multiple MDs simultaneously), Create "
            "Isodose Plan (dosimetry), Review Plan (MD sign-off). Each row shows who "
            "the task is assigned to, who completed it, when it was started/due/"
            "completed, how many minutes it took from the prior-step baseline, and "
            "whether the prior step is complete. Powers workload dashboards and "
            "on-time-completion metrics for the planning pipeline."
        ),
        "unique_logic": [
            "Early deduplication: #BaseActivities is materialized and deduplicated via DELETE statements "
            "before the expensive joins run. Contour Review is often assigned to multiple physicians "
            "simultaneously — without early dedup this would fan out by physician count through the rest "
            "of the pipeline.",
            "#PriorExams, #PriorSteps, and #DrawCreation are each materialized for reuse (one scan, indexed).",
            "Prior-step baselines are pre-computed via UPDATE statements on #BaseActivities (self-joins "
            "on a small indexed table instead of correlated subqueries in the final SELECT).",
            "Draw baseline priority cascade: task creation datetime from DimActivityTransactionHistory > "
            "sim actual end > sim scheduled end > draw task start. Creation datetime is most accurate for "
            "replans and new care paths where the sim-to-draw gap is misleading.",
            "Isodose baseline: Contour Review end > Draw end > task start — matches Workflow_Events.sql "
            "(always prefers Contour Review when available).",
            "3-tier prior-exam physician fallback: Completed appointments > billing physician > any status "
            "(catches cancelled inpatient consults).",
            "TaskStatus resolved via DimLookup (Open / Completed / Approved / etc.).",
            "PriorStepComplete flag indicates whether the preceding stage has finished.",
            "Asymmetric date filter: only completed tasks are date-bounded by @StartDate/@EndDate; "
            "open/incomplete tasks are always included regardless of date range. Uses a 30-day rolling "
            "@OpenTaskCutoff to surface stale tasks independent of the date parameters.",
            "CompletingUser from DimUser.DisplayName for non-MD tasks (Isodose completed by dosimetrists "
            "whose doctor columns will be NULL).",
            "AssignedUser deliberately NOT output because the resource-to-user join fans out on group "
            "resources (e.g., Dosimetry) causing massive row duplication — CompletingUser (1:1 FK) is sufficient.",
        ],
        "output_cols": (
            "DimActivityTransactionID, PatientId, PatientName, ActivityCode, ActivityName, StartDateTime, "
            "DueDateTime, CompletedDateTime, PriorStepBaseline, MinutesToComplete, MinutesAllowed, "
            "MinutesFromSimToDrawCompletion, DrawCreationDateTime, SimulationDateTime, "
            "SimScheduledEndDateTime, SimActualEndDateTime, AssignedMD, CompletingMD, CompletingUser, "
            "TreatingPhysician, PriorExamPhysician, TaskStatus, PriorStepComplete, DiagnosisCodes, "
            "DiagnosisDescriptions."
        ),
        "date_range": "2 months back → today (completed); 30-day rolling (open).",
    },

    "Treatment": {
        "total": 1550, "sql": 619,
        "purpose": (
            "Daily aggregated treatment statistics at the date × location × machine "
            "grain, with the full 10-tier plan-level technique classification. For "
            "each daily row the report reports total patients, plans, fractions, and "
            "fields — plus Plans_*, Patients_*, and Fields_* broken out by technique "
            "category. Physician data is explicitly removed here (it lives in "
            "Treatment_Detail.sql) so the aggregate counts aren't fanned out by "
            "physician attribution."
        ),
        "unique_logic": [
            "Materialized temp tables: #TreatmentsByLocation (referenced 7× — previously re-evaluated "
            "every time as a CTE), #TreatedPlans, #PlanTechnique.",
            "4-tier field-level classification (Electron → Arc → StaticMLC → DynamicMLC with photon "
            "fallback) drives the Fields_* columns. Arc is checked before MLC types because arc fields "
            "may use either StdMLCPlan or DynMLCPlan.",
            "Plan-level 10-tier technique classification drives Plans_* and Patients_*: Prescription > "
            "Electron > Plan-name keywords > Course+Fractionation > Field Mix > SRS Arc > RapidArc > "
            "MLC Type > Billing > Field Count > Unknown. A patient is counted once per technique if ANY "
            "of their plans have that technique.",
            "Session counting replaced by direct SUM(NumTreatmentSessions) from FactTreatmentHistory "
            "(2026-04-17 refactor) — dropped the appointment-side session-matching pipeline and its "
            "240-min gap / CONTINUATION / FractionNumber cross-check logic. Net reduction of 203 file "
            "lines (1,753 → 1,550) while preserving every output column. Treatment_Detail.sql retains "
            "the gap-based session detector for per-row drill-through.",
            "Reference-point deduplication: COUNT(DISTINCT DimFieldID) in PlanFieldInfo; SELECT DISTINCT "
            "with DimFieldID in FieldTechnique CTE — same fix as DailyVolume_Past.sql.",
            "Aggregation key: date × location × machine. DoseDeliveredPerFraction pre-included in "
            "#TreatmentsByLocation to eliminate a re-join to FactTreatmentHistory in PlanFieldFractionDose.",
            "OPTION(RECOMPILE) for parameter-sniffing optimization across variable date ranges.",
        ],
        "output_cols": (
            "Date, Location, Machine-level counts (TotalPatients, TotalPlans, TotalFractions, TotalFields), "
            "plus Plans_* / Patients_* / Fields_* broken out by technique, and appointment session counts."
        ),
        "date_range": "2 months back → today.",
    },

    "Treatment_Detail": {
        "total": 1746, "sql": 1086,
        "purpose": (
            "Row-level treatment detail — one row per plan × treatment date × machine "
            "× patient. The drill-through companion to Treatment.sql: where Treatment.sql "
            "aggregates, this one leaves every row intact so the front end can filter/"
            "group/pivot by physician, technique, plan name, course, diagnosis, or any "
            "other dimension. Used anywhere Treatment.sql's pre-aggregated numbers need "
            "to be decomposed."
        ),
        "unique_logic": [
            "Entity-first filtering architecture matching Courses.sql.",
            "FractionNumber-based counting (not raw row counts).",
            "10-tier technique classification (same cascade as Treatment.sql and Plans.sql).",
            "Session detection with CONTINUATION suppression and FractionNumber cross-check.",
            "2-tier physician determination via COALESCE (Most Frequent Billing > Prior Exam).",
            "Full patient / course / plan / field / dose / machine detail per row.",
        ],
        "output_cols": "Row-level — patient, course, plan, field, date, machine, dose, physician, technique.",
        "date_range": "2 months back → today.",
    },

    "Weekly_Visits": {
        "total": 722, "sql": 472,
        "purpose": (
            "Tracks the weekly-management exam visits that occur during active "
            "radiation treatment (CPT 77427/77431 workflow) — essentially the \"weekly "
            "check-in\" during a course where the treating MD evaluates the patient "
            "mid-treatment. Each row is one such visit with its physician attribution "
            "(treating, consult, referring), procedure/diagnosis detail, department, "
            "and in-patient status."
        ),
        "unique_logic": [
            "#FilteredActivities materialized temp table.",
            "Modern 4-tier TreatingPhysician cascade: Most Frequent Billing Physician > Prior Exam "
            "Completed > Prior Exam Billing > Prior Exam Any. Separate 3-tier ConsultPhysician fallback.",
            "Multi-resource dedup prefers physician-assigned resources.",
            "2-tier diagnosis fallback (billing-linked > activity-level via FactActivityDiagnosis).",
            "Unique: includes ALL active billing records (no reviewed/exported filter) — weekly visits "
            "frequently bill against records that are still in-process, so filtering on reviewed+exported "
            "would drop the bulk of relevant rows.",
            "Course identification uses the most recent course prior to the visit date.",
        ],
        "output_cols": (
            "UniqueRowID, PatientId, PatientFullName, AppointmentDateTime, DurationMinutes, ActivityName, "
            "ActivityStatus, DepartmentName, InPatientFlag, AppointmentPhysician, TreatingPhysician, "
            "ConsultPhysician, ReferringPhysician (ID/name/specialty), ProcedureCodes, "
            "ProcedureDescriptions, DiagnosisCodes, DiagnosisDescriptions."
        ),
        "date_range": "2 months back → today.",
    },

    "Workflow_Events": {
        "total": 2322, "sql": 1677,
        "purpose": (
            "Normalized event log for the consult-to-treatment timeline — one row per "
            "workflow stage per exam. The \"exam\" is the anchor (initial consult / "
            "follow-up / re-eval), and every downstream event (simulation, draw, "
            "contour review, isodose, review plan, first fraction, or Pluvicto "
            "injection) gets its own row with an ordered StageTypeOrder so the data is "
            "directly consumable by a Flow-Gantt frontend. Repeated stages "
            "(resimulations, replans) appear as multiple rows with StageOccurrence > 1 "
            "— rendered as loop-back arcs on the Gantt, making mid-course replans "
            "immediately visible. Where the columnar Workflow.sql gives one row per "
            "exam with first-of-each-type only, this script gives every occurrence so "
            "resimulations and replans aren't hidden."
        ),
        "unique_logic": [
            "Supported workflows: EBRT / Brachytherapy (7 stages: Exam → Simulation → Draw Volumes → "
            "Contour Review → Isodose Plan → Review Plan → Treatment (F1)); "
            "Pluvicto (2 stages: Exam → Pluvicto Injection, up to 6 per course, ~6 weeks apart).",
            "Exam-anchored, not sim-anchored — each exam starts a workflow chain, the right mental model "
            "when a patient has multiple separate treatment courses.",
            "Workflow-scoped UniqueRowID: UniqueRowID = ExamActivityTransactionID, shared by all events "
            "in a workflow chain. Enables atomic batch upsert: DELETE + re-INSERT by UniqueRowID refreshes "
            "an entire workflow atomically. Not per-row unique by design.",
            "15 temp tables with clustered indexes; one scan per large table (6 scans of "
            "DimActivityTransaction, 1 scan each of FactActivityBilling, FactTreatmentHistory, "
            "DimActivityTransactionHistory).",
            "Sim attribution uses JOIN + ROW_NUMBER (set-based) instead of correlated OUTER APPLY — "
            "each task is explicitly linked to its nearest preceding completed sim via AttributedSimOccurrence.",
            "Multi-resource dedup is consistent across sims, workflow tasks, and treatments "
            "(MAX OVER + ROW_NUMBER by exam+datetime) — prevents false duplicates and false cancellations.",
            "BaselineDateTime is pre-computed via UPDATE on the temp table, so the frontend can compute "
            "MinutesToComplete as a simple DATEDIFF(StageEndDateTime, BaselineDateTime) without re-querying.",
            "Overlap filter captures workflows where consult, sim, OR treatment falls in the reporting "
            "window — pre-computed into #QualifyingExams.",
            "Centralized modality inference via #ExamModality temp table so EBRT vs Brachy vs Pluvicto "
            "classification is computed once, not re-derived per join.",
            "SimVisitRank handles shared-sim dedup: 1 = closest exam before the sim, NULL = no completed sim.",
            "Four status states — Completed / Open / Scheduled / Cancelled — emitted as event rows instead "
            "of cascade CASE logic.",
        ],
        "output_cols": (
            "36 columns: UniqueRowID (ExamActivityTransactionID), PatientId, PatientName, StageName, "
            "StageTypeOrder, StageActivityName, StageDateTime, StageEndDateTime, StageDueDateTime, "
            "StageCreationDateTime, CompletedBy, StageStatus, BaselineDateTime, AttributedSimOccurrence, "
            "DimCourseID, CourseId, ExamCreatedDate, ExamDurationMinutes, ExamActivityStatus, ExamNotes, "
            "AppointmentPhysician, TreatingPhysician, ReferringPhysician (ID/name/specialty), "
            "ProcedureCodes, ProcedureDescriptions, DiagnosisCodes, DiagnosisDescriptions, Department, "
            "FuturePipelineTaskList, ExamDateTime, StageOccurrence (loop-back detection), StageOrder, "
            "SimVisitRank."
        ),
        "date_range": "180 days back → yesterday.",
    },
}


# Shared conventions that apply to every script
SHARED_CONVENTIONS = [
    "Target: Varian ARIA data warehouse (SQL Server).",
    "All scripts use Report Builder @StartDate / @EndDate parameters.",
    "SET TRANSACTION ISOLATION LEVEL READ UNCOMMITTED (no blocking on the live warehouse).",
    "Standard patient / course / plan quality filters exclude test / QA / DNU / demo data.",
]


# ---------------------------------------------------------------------------
# Dynamic recount — if the production SQL directory is reachable, re-count
# every script's `total` and `sql` line counts in place so the help modal
# always reflects the current source. Falls back silently to the hardcoded
# values above if the directory is missing (e.g., running on a host that
# doesn't have the ARIA scripts synced).
# ---------------------------------------------------------------------------
import os
import re
from pathlib import Path


def _count_sql_lines(text: str) -> tuple[int, int]:
    """Return (total_lines, sql_code_lines). SQL excludes blank lines,
    single-line `--` comments, and `/* ... */` block comments."""
    lines = text.splitlines()
    total = len(lines)
    sql = 0
    in_block = False
    for raw in lines:
        s = raw.strip()
        if not s:
            continue
        if in_block:
            if "*/" in s:
                in_block = False
                rest = s.split("*/", 1)[1].strip()
                if rest and not rest.startswith("--"):
                    sql += 1
            continue
        if s.startswith("--"):
            continue
        if s.startswith("/*"):
            if "*/" in s:
                stripped = re.sub(r"/\*.*?\*/", "", s).strip()
                if stripped and not stripped.startswith("--"):
                    sql += 1
            else:
                in_block = True
            continue
        sql += 1
    return total, sql


def _find_sql_dir() -> Path | None:
    candidates = [
        os.environ.get("ARIA_SQL_DIR"),
        "~/Aria/Production",
        "~/Library/CloudStorage/OneDrive-ProvidenceSt.JosephHealth/Aria/Production",
    ]
    for c in candidates:
        if not c:
            continue
        p = Path(os.path.expanduser(c))
        if p.is_dir():
            return p
    return None


_sql_dir = _find_sql_dir()
if _sql_dir is not None:
    for _name, _entry in SQL_SCRIPTS.items():
        _file = _sql_dir / f"{_name}.sql"
        if not _file.is_file():
            continue
        try:
            _text = _file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        _total, _sql = _count_sql_lines(_text)
        _entry["total"] = _total
        _entry["sql"] = _sql


# Aggregate project-level stats — used by the Overview help page.
TOTAL_SCRIPTS = len(SQL_SCRIPTS)
TOTAL_FILE_LINES = sum(s["total"] for s in SQL_SCRIPTS.values())
TOTAL_SQL_LINES = sum(s["sql"] for s in SQL_SCRIPTS.values())
TOTAL_COMMENT_LINES = TOTAL_FILE_LINES - TOTAL_SQL_LINES
SQL_SHARE = TOTAL_SQL_LINES / TOTAL_FILE_LINES
LARGEST_SCRIPT = max(SQL_SCRIPTS.items(), key=lambda kv: kv[1]["total"])
SMALLEST_SCRIPT = min(SQL_SCRIPTS.items(), key=lambda kv: kv[1]["total"])
SQL_FIRST_COMMIT = "2025-11-17"
SQL_LATEST_COMMIT = "2026-04-17"
